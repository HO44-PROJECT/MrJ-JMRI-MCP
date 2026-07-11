"""Shared speed-ramping primitives, built on top of JmriWsClient.

Used by both cli/throttle.py (one-shot and shell modes) and
tools/throttle.py's set_speed_ramped MCP tool, so a ramp behaves
identically regardless of which surface triggered it. Lives here (not in
cli/ or tools/) because it depends only on JmriWsClient, and both cli and
tools depend on it — this is the lowest common module for the two.
"""

import asyncio
from typing import Any, Awaitable, Callable

from jmri_mcp.constants.client_tuning import RAMP_STEPS_PER_SECOND
from jmri_mcp.constants.protocol import FIELD_FORWARD, FIELD_SPEED
from jmri_mcp.jmri_ws import JmriWsClient


async def ramp_speed(
    client: JmriWsClient,
    throttle_id: str,
    from_fraction: float,
    to_fraction: float,
    seconds: float,
    *,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    steps_per_second: float = RAMP_STEPS_PER_SECOND,
) -> None:
    """Linearly ramp speed from `from_fraction` to `to_fraction` over `seconds`.

    Sends intermediate `set_speed` calls at roughly `steps_per_second`
    steps/sec, always finishing with one exact final `set_speed(to_fraction)`
    call so floating-point step accumulation never leaves the throttle short
    of the target. `seconds <= 0` (or the endpoints already matching) skips
    straight to that final call — this is what "no ramp requested"
    degenerates to, so callers never need to branch on "was a ramp
    requested".

    `sleep` is resolved fresh on each call (not a bound default parameter)
    so `monkeypatch.setattr(".../ramp.asyncio.sleep", ...)` in tests
    affects it — a bound default would capture `asyncio.sleep` at import
    time, before any test patch is applied.
    """
    sleep = sleep or asyncio.sleep
    if seconds <= 0 or from_fraction == to_fraction:
        await client.set_speed(throttle_id, to_fraction)
        return
    steps = max(1, int(seconds * steps_per_second))
    for i in range(1, steps + 1):
        fraction = from_fraction + (to_fraction - from_fraction) * (i / steps)
        await client.set_speed(throttle_id, fraction)
        if i < steps:
            await sleep(seconds / steps)
    await client.set_speed(throttle_id, to_fraction)


async def execute_speed_change(
    client: JmriWsClient,
    throttle_id: str,
    *,
    target_forward: bool | None,
    target_fraction: float,
    rampup: float | None,
    rampdown: float | None,
    hold_seconds: float | None,
) -> dict[str, Any]:
    """Shared state machine behind every ramped speed/direction/stop change.

    Sequence: ramp down first if a direction flip is needed (or the target
    is simply lower and rampdown was given) -> flip direction if needed ->
    ramp up to the final target (if rampup was given) -> hold for
    hold_seconds, if given -> ramp back down to 0 if a bounded hold just
    ended at a nonzero speed. This auto-stop applies unconditionally to
    every caller: a bounded hold of N seconds always means "hold this
    speed for N seconds, then stop", whether called one-shot, from the CLI
    shell, or from the set_speed_ramped MCP tool.

    A Ctrl-C (or task cancellation) during the hold is caught so the
    locomotive is ramped/jumped back to 0 before the interrupt propagates,
    rather than leaving it coasting at whatever speed it had at the moment
    of interruption — deliberately the ONE place in this whole design with
    interrupt handling; everywhere else a Ctrl-C propagates normally.

    Reads current state via `client.throttle_state()` (never a private
    attribute) and returns the same, re-read once at the end, as the single
    source of truth for the caller's reported result.
    """
    info = client.throttle_state(throttle_id) or {}
    current_fraction = info.get(FIELD_SPEED) or 0.0
    current_forward = info.get(FIELD_FORWARD, True)

    needs_flip = target_forward is not None and target_forward != current_forward

    if needs_flip and current_fraction > 0.0:
        await ramp_speed(client, throttle_id, current_fraction, 0.0, rampdown or 0.0)
        current_fraction = 0.0
    elif rampdown is not None and target_fraction < current_fraction:
        await ramp_speed(client, throttle_id, current_fraction, target_fraction, rampdown)
        current_fraction = target_fraction

    if needs_flip:
        await client.set_direction(throttle_id, target_forward)

    if target_fraction > current_fraction:
        await ramp_speed(client, throttle_id, current_fraction, target_fraction, rampup or 0.0)
    elif target_fraction != current_fraction:
        await client.set_speed(throttle_id, target_fraction)

    if hold_seconds:
        try:
            await asyncio.sleep(hold_seconds)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await ramp_speed(client, throttle_id, target_fraction, 0.0, rampdown or 0.0)
            raise

    if hold_seconds is not None and target_fraction > 0.0:
        await ramp_speed(client, throttle_id, target_fraction, 0.0, rampdown or 0.0)

    return client.throttle_state(throttle_id) or {}
