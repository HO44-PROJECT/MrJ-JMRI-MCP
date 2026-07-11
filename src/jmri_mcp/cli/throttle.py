"""Throttle commands: `jmri-cli throttle [acquire|release|speed|stop|estop|direction|on|off|sniff]`.

Talks to jmri_ws.py. Two connection modes now coexist:
  - One-shot (the default: `client=None`): a fresh WebSocket connection is
    opened for the one command, then closed — see module docstring in
    jmri_mcp.cli for why this differs from the MCP server's single
    long-lived connection. Because that connection closes right after
    acting, JMRI itself has nothing left to query between two `jmri-cli
    throttle` invocations — state.py's local cache is what `throttle`
    (bare) and `speed <loco>` (no value) read back.
  - Shared (`client=<JmriWsClient>`, passed by cli/shell.py): the caller
    owns a long-lived connection across many commands, so a nonzero speed
    genuinely keeps the locomotive moving instead of being released the
    instant one command's connection closes — see `_client_scope()`.

Every WS-based command function below accepts an optional `client` keyword
for this reason. `speed`/`stop`/`forward`/`reverse` additionally support
ramping (`--rampup`/`--rampdown`) and, in one-shot mode only, a mandatory
`--hold` whenever the resulting speed is nonzero — seeing this
project's history of a "hold the connection open a fixed number of
seconds" hack not being a real fix (a throttle held open for exactly N
seconds just stops the locomotive at second N, not on command), one-shot
mode never holds a nonzero speed indefinitely; only the shell does.

Naming convention used throughout this module: `speed_percent` is the
CLI-facing value (a float that MAY be negative, as shorthand for
"reverse at this magnitude" — see throttle_speed), and is NEVER passed
directly to JmriWsClient. Only a resolved `*_fraction` value (always
0.0-1.0, or literally -1.0 inside throttle_estop only) ever reaches
`client.set_speed()`. This keeps the CLI-only negative-percent shorthand
strictly separate from JMRI's real wire-level emergency-stop sentinel.
"""

import argparse
import asyncio
import contextlib
import datetime
import json
import sys
from typing import Any, Awaitable, Callable

from tabulate import tabulate

from jmri_mcp.cli import state as _state
from jmri_mcp.cli._common import cli_throttle_id
from jmri_mcp.cli.constants import (
    IDLE_POLL_SECONDS,
    MAX_FUNCTION_NUMBER,
    MAX_SPEED_PERCENT,
    MIN_FUNCTION_NUMBER,
    MIN_SPEED_PERCENT,
    RAMP_STEPS_PER_SECOND,
    SNIFF_THROTTLE_ID_PREFIX,
)
from jmri_mcp.jmri_client import JmriError as JmriHttpError
from jmri_mcp.jmri_client import get_roster, get_roster_function_labels, resolve_roster_entry
from jmri_mcp.jmri_ws import JmriError as JmriWsError
from jmri_mcp.jmri_ws import JmriWsClient

_SECONDS_REQUIRED_MESSAGE = (
    "Error: --hold is required when setting a nonzero speed outside the "
    "interactive shell (use the bare `jmri-cli` shell for an indefinite hold)."
)


async def _resolve_address(loco: str) -> int:
    """Resolve a CLI-typed locomotive reference to a DCC address.

    Accepts a bare DCC address ("3"), a roster name, or an unambiguous
    fragment of one ("autorail"). A numeric value not found in the roster
    is still accepted as a raw address — this project has no server-side
    scan of what's actually on the DCC bus (verified live, see
    CLAUDE.md), so hardware never added to JMRI's roster must stay
    reachable by address alone.
    """
    stripped = loco.strip()
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(stripped, roster)
        return entry["address"]
    except JmriHttpError:
        if stripped.lstrip("-").isdigit():
            return int(stripped)
        raise


def _direction_name(forward: bool) -> str:
    return "forward" if forward else "reverse"


@contextlib.asynccontextmanager
async def _client_scope(client: JmriWsClient | None):
    """Yield `client` if given (shell mode — caller owns its lifecycle,
    never closed here), else construct and close a fresh one-shot client.

    Every WS-based throttle_* function routes its JMRI calls through this,
    so the same function body works identically whether called one-shot
    (client=None, from a plain `jmri-cli throttle ...` invocation) or from
    the interactive shell (client=<shared JmriWsClient>, see shell.py).
    """
    if client is not None:
        yield client
        return
    owned = JmriWsClient()
    try:
        yield owned
    finally:
        await owned.close()


async def _ramp_speed(
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
    straight to that final call — this is what "no --rampup/--rampdown
    given" degenerates to, so callers never need to branch on "was a ramp
    requested".

    `sleep` is resolved fresh on each call (not a bound default parameter)
    so `monkeypatch.setattr("jmri_mcp.cli.throttle.asyncio.sleep", ...)`
    in tests affects it — a bound default would capture `asyncio.sleep` at
    import time, before any test patch is applied.
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


async def _execute_speed_change(
    client: JmriWsClient,
    throttle_id: str,
    *,
    target_forward: bool | None,
    target_fraction: float,
    rampup: float | None,
    rampdown: float | None,
    hold_seconds: float | None,
) -> dict[str, Any]:
    """Shared state machine behind throttle_speed/throttle_direction/throttle_stop.

    Sequence: ramp down first if a direction flip is needed (or the target
    is simply lower and --rampdown was given) -> flip direction if needed
    -> ramp up to the final target (if --rampup was given) -> hold for
    hold_seconds, if given -> ramp back down to 0 if a bounded hold just
    ended at a nonzero speed. This auto-stop applies unconditionally,
    whether called one-shot or from the shell: a caller that bounds a
    speed with --hold N means "hold this speed for N seconds, then
    stop" either way — the shell case matters just as much as one-shot,
    since the shell's shared connection makes a nonzero speed persist
    indefinitely otherwise (bug found live: `throttle speed 4 10 --hold
    2` inside the shell held correctly for 2s but then left the
    locomotive at 10% forever, since this step used to be gated on a
    one_shot flag that's now removed).

    A Ctrl-C (or task cancellation) during the hold is caught so the
    locomotive is ramped/jumped back to 0 before the interrupt propagates,
    rather than leaving it coasting at whatever speed it had at the moment
    of interruption — deliberately the ONE place in this whole design with
    interrupt handling; everywhere else a Ctrl-C propagates normally.

    Reads current state via `client.throttle_state()` (never a private
    attribute) and returns the same, re-read once at the end, as the single
    source of truth for the caller's printed output.
    """
    info = client.throttle_state(throttle_id) or {}
    current_fraction = info.get("speed") or 0.0
    current_forward = info.get("forward", True)

    needs_flip = target_forward is not None and target_forward != current_forward

    if needs_flip and current_fraction > 0.0:
        await _ramp_speed(client, throttle_id, current_fraction, 0.0, rampdown or 0.0)
        current_fraction = 0.0
    elif rampdown is not None and target_fraction < current_fraction:
        await _ramp_speed(client, throttle_id, current_fraction, target_fraction, rampdown)
        current_fraction = target_fraction

    if needs_flip:
        await client.set_direction(throttle_id, target_forward)

    if target_fraction > current_fraction:
        await _ramp_speed(client, throttle_id, current_fraction, target_fraction, rampup or 0.0)
    elif target_fraction != current_fraction:
        await client.set_speed(throttle_id, target_fraction)

    if hold_seconds:
        try:
            await asyncio.sleep(hold_seconds)
        except (KeyboardInterrupt, asyncio.CancelledError):
            await _ramp_speed(client, throttle_id, target_fraction, 0.0, rampdown or 0.0)
            raise

    if hold_seconds is not None and target_fraction > 0.0:
        await _ramp_speed(client, throttle_id, target_fraction, 0.0, rampdown or 0.0)

    return client.throttle_state(throttle_id) or {}


async def throttle_list(args: argparse.Namespace) -> int:
    """Print last-known speed/direction/functions for every locomotive this CLI has touched.

    Reads state.py's local cache, not a live JMRI query — see this
    module's docstring for why a fresh CLI connection has nothing live to
    ask between invocations. Empty until at least one `throttle speed`/
    `direction`/`on`/`off`/etc has been run.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 always (an empty cache is not an error).
    """
    cache = _state.load_state()
    if not cache:
        print("No locomotives touched yet by this CLI. Run e.g. `jmri-cli throttle speed <loco> <value>` first.")
        return 0

    rows = []
    for address, info in sorted(cache.items(), key=lambda kv: int(kv[0])):
        speed = info.get("speed")
        speed_display = "-" if speed is None else f"{speed * 100:.0f}%"
        direction = info.get("forward")
        direction_display = "-" if direction is None else _direction_name(direction)
        functions = info.get("functions", {})
        on_functions = sorted(int(n) for n, v in functions.items() if v)
        functions_display = ", ".join(f"F{n}" for n in on_functions) or "-"
        rows.append([address, speed_display, direction_display, functions_display])
    print(tabulate(rows, headers=["Address", "Speed", "Direction", "Functions on"]))
    return 0


async def throttle_acquire(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Acquire a loco by name/fragment/address.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address) and `args.prefix` (optional command station prefix).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire is rejected.
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        async with _client_scope(client) as c:
            data = await c.acquire_throttle(cli_throttle_id(address), address, args.prefix)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _state.update_address(address, speed=data.get("speed"), forward=data.get("forward"))
    print(f"address={address} speed={data.get('speed')} "
          f"forward={data.get('forward')} (acquired)")
    return 0


async def throttle_release(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Acquire then immediately release a loco by name/fragment/address.

    A throttle is only meaningfully released on the connection that holds
    it — a fresh CLI connection never holds another session's throttle, so
    this acquires (JMRI just re-confirms if already held elsewhere) then
    releases on this same connection, mirroring what closing that other
    connection would do. Inside the shell, this releases it on the shell's
    own shared connection instead, which is the one actually holding it.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire/release is
        rejected.
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        async with _client_scope(client) as c:
            await c.acquire_throttle(cli_throttle_id(address), address)
            await c.release_throttle(cli_throttle_id(address))
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"address={address} released")
    return 0


async def throttle_speed(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Get or set a loco's speed.

    With no `args.speed_percent`, this acquires the loco (which resyncs on
    JMRI's real current speed) and prints it without sending any speed
    command — a read, not a write. With a value, it sets speed as 0-100%
    of maximum; a NEGATIVE value is CLI-only shorthand for "reverse at
    |value|%" (e.g. `-40` means direction=reverse, speed=40%) — this is
    resolved entirely client-side and is unrelated to JMRI's own -1.0
    emergency-stop sentinel, which only `throttle_estop` ever sends.

    In one-shot mode (client=None), setting a nonzero speed WITHOUT
    `args.seconds` is a hard, upfront error — see module docstring for why
    a one-shot connection can never reliably hold a nonzero speed, no
    matter how long it delays before closing. Inside the shell,
    `args.seconds` is optional — omitting it holds the speed indefinitely
    (until another command or shell exit), same as today.

    Whenever `args.seconds` IS given (one-shot or shell), the loco holds
    that speed for that long, then always auto-stops before this function
    returns (ramped via `args.rampdown` if given, else instantly) — this
    applies in both modes: a one-shot invocation must never exit leaving
    the layout moving with no connection left to control it, and inside
    the shell `--hold N` means "hold for N seconds, then stop", not
    "hold forever after N seconds" (bug found live: it used to only
    auto-stop in one-shot mode, silently leaving the loco moving forever
    after the hold when run inside the shell).

    Args:
        args: Parsed CLI arguments; uses `args.loco`, `args.speed_percent`
            (0-100, may be negative, or None to just read), `args.rampup`,
            `args.rampdown`, `args.seconds` (all seconds, optional).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection,
            and enforces the mandatory-`--hold` rule above.

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected,
        2 if `--hold` was required but not given (one-shot mode only).
    """
    one_shot = client is None

    if args.speed_percent is not None and one_shot:
        target_percent = abs(args.speed_percent)
        if target_percent > 0 and args.seconds is None:
            print(_SECONDS_REQUIRED_MESSAGE, file=sys.stderr)
            return 2

    try:
        address = await _resolve_address(args.loco)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    throttle_id = cli_throttle_id(address)
    try:
        async with _client_scope(client) as c:
            acquired = await c.acquire_throttle(throttle_id, address)
            if args.speed_percent is None:
                data = acquired
            else:
                target_forward = False if args.speed_percent < 0 else None
                target_fraction = max(
                    MIN_SPEED_PERCENT, min(MAX_SPEED_PERCENT, abs(args.speed_percent))
                ) / 100.0
                data = await _execute_speed_change(
                    c, throttle_id,
                    target_forward=target_forward, target_fraction=target_fraction,
                    rampup=args.rampup, rampdown=args.rampdown, hold_seconds=args.seconds,
                )
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    speed = data.get("speed", acquired.get("speed"))
    forward = data.get("forward")
    _state.update_address(address, speed=speed, **({"forward": forward} if forward is not None else {}))
    direction_suffix = f" direction={_direction_name(forward)}" if forward is not None else ""
    print(f"address={address} speed={(speed or 0) * 100:.0f}%{direction_suffix}")
    return 0


async def throttle_stop(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Controlled stop (speed 0) of one loco, or every touched loco if none is given.

    With no `args.loco` in one-shot mode, this stops every locomotive this
    CLI's local cache (state.py) knows about — the CLI's own "stop
    everything I've driven" primitive, since a fresh CLI process holds
    nothing else to iterate. Locomotives never touched by this CLI (or
    only driven from a JMRI panel/other client) are out of reach here,
    same limitation any cache-driven CLI command has; use `power off` to
    cut power to the whole layout regardless of who's driving. Inside the
    shell, `args.loco` is required (the shell's own held throttles are the
    only meaningful "every loco" set, and `throttle_direction`/
    `throttle_speed` already reuse the shell's connection directly).

    `stop`'s target is always 0, so unlike `speed`/`forward`/`reverse` it
    has no `--hold`/`--rampup` flags at all — only `--rampdown`.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every cached address) and
            `args.rampdown` (seconds, optional).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every targeted loco confirmed stopped, 1 if JMRI is
        unreachable or any command was rejected, 2 if `args.loco` was
        omitted inside the shell (mandatory there).
    """
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriHttpError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif client is not None:
        print(
            "Error: a locomotive is required for `stop` inside the shell "
            "(e.g. `throttle stop 3`) — the CLI-wide cache of every "
            "one-shot-touched address doesn't apply to the shell's own "
            "held throttles.",
            file=sys.stderr,
        )
        return 2
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print("No locomotives touched yet by this CLI, nothing to stop.", file=sys.stderr)
            return 0

    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                throttle_id = cli_throttle_id(address)
                try:
                    await c.acquire_throttle(throttle_id, address)
                    data = await _execute_speed_change(
                        c, throttle_id,
                        target_forward=None, target_fraction=0.0,
                        rampup=None, rampdown=args.rampdown, hold_seconds=None,
                    )
                    speed = data.get("speed", 0.0)
                    _state.update_address(address, speed=speed)
                    print(f"address={address} stopped")
                except JmriWsError as exc:
                    print(f"Error: address={address}: {exc}", file=sys.stderr)
                    ok = False
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0 if ok else 1


async def throttle_estop(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Emergency stop (JMRI decoder e-stop, speed -1.0). No ramp support —
    an emergency stop is a distinct decoder command that must be immediate,
    not gradual (see module docstring: JMRI's real -1.0 sentinel, never to
    be confused with `throttle_speed`'s CLI-only negative-percent shorthand).

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected.
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        async with _client_scope(client) as c:
            await c.acquire_throttle(cli_throttle_id(address), address)
            await c.set_speed(cli_throttle_id(address), -1.0)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _state.update_address(address, speed=-1.0)
    print(f"address={address} emergency-stopped")
    return 0


async def throttle_direction(
    args: argparse.Namespace, *, forward: bool, client: JmriWsClient | None = None
) -> int:
    """Set a loco's direction, ramping speed down/back-up around the flip if moving.

    If the loco is currently moving and this changes its direction, it
    first ramps down to 0 (using `args.rampdown` if given, else instant),
    flips direction, then ramps back up to the speed magnitude it had
    before the flip (using `args.rampup` if given, else instant). If the
    loco is stationary, or already facing the requested direction, this is
    just a plain (possibly no-op) direction set — `args.rampup`/
    `args.rampdown`/`args.seconds` are accepted but have nothing to act on.

    In one-shot mode, this needs one JMRI read (the acquire, to learn the
    current speed) before it can know whether the mandatory-`--hold`
    rule even applies — unlike `throttle_speed`/`throttle_stop`, which
    know the target speed from `args` alone and can reject before
    contacting JMRI at all. This is an accepted, documented exception, not
    an inconsistency to "fix" later.

    Args:
        args: Parsed CLI arguments; uses `args.loco`, `args.rampup`,
            `args.rampdown`, `args.seconds` (all seconds, optional).
        forward: True for `throttle forward`, False for `throttle reverse`
            — bound via functools.partial in parser.py so "forward" and
            "reverse" are each their own leaf subcommand, not a shared one
            with a choice argument.
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection,
            and enforces the mandatory-`--hold` rule above.

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected,
        2 if `--hold` was required (loco already moving) but not given
        (one-shot mode only).
    """
    one_shot = client is None

    try:
        address = await _resolve_address(args.loco)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    throttle_id = cli_throttle_id(address)
    try:
        async with _client_scope(client) as c:
            acquired = await c.acquire_throttle(throttle_id, address)
            current_fraction = acquired.get("speed") or 0.0

            if one_shot and current_fraction > 0.0 and args.seconds is None:
                print(_SECONDS_REQUIRED_MESSAGE, file=sys.stderr)
                return 2

            data = await _execute_speed_change(
                c, throttle_id,
                target_forward=forward, target_fraction=current_fraction,
                rampup=args.rampup, rampdown=args.rampdown, hold_seconds=args.seconds,
            )
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    reported = data.get("forward", forward)
    speed = data.get("speed")
    _state.update_address(address, forward=reported, **({"speed": speed} if speed is not None else {}))
    print(f"address={address} direction={_direction_name(reported)}")
    return 0


async def _resolve_function_numbers(address: int, function: str | None) -> list[int]:
    """Resolve a CLI-typed function reference to one or more function numbers.

    `function` may be a bare number ("1"), a label fragment matched
    against this loco's roster-set function labels ("phares"), or None
    (every labeled function for this loco). Raises JmriHttpError if a
    label/None lookup finds nothing — see throttle_on/throttle_off for why
    this deliberately does NOT fall back to F0 in that case.
    """
    if function is not None and function.strip().lstrip("-").isdigit():
        n = int(function.strip())
        if not (MIN_FUNCTION_NUMBER <= n <= MAX_FUNCTION_NUMBER):
            raise JmriHttpError(f"function must be {MIN_FUNCTION_NUMBER}-{MAX_FUNCTION_NUMBER}, got {n}")
        return [n]

    roster = await get_roster()
    entry = resolve_roster_entry(str(address), roster)
    labels = await get_roster_function_labels(entry["name"])
    if not labels:
        raise JmriHttpError(
            f"{entry['name']} (address={address}) has no labeled functions in JMRI's "
            f"roster — specify a function number, e.g. `throttle on {address} 0`"
        )

    if function is None:
        return sorted(labels)

    q = function.strip().casefold()
    matches = [n for n, label in labels.items() if q in label.casefold()]
    if not matches:
        available = ", ".join(f"F{n}={label}" for n, label in sorted(labels.items()))
        raise JmriHttpError(f"No labeled function matches {function!r}. Available: {available}")
    return sorted(matches)


async def _throttle_set_functions(
    args: argparse.Namespace, *, state: bool, client: JmriWsClient | None = None
) -> int:
    """Shared body for throttle_on/throttle_off."""
    try:
        address = await _resolve_address(args.loco)
        function_numbers = await _resolve_function_numbers(address, args.function)
    except JmriHttpError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    ok = True
    try:
        async with _client_scope(client) as c:
            await c.acquire_throttle(cli_throttle_id(address), address)
            for n in function_numbers:
                try:
                    data = await c.set_function(cli_throttle_id(address), n, state)
                    reported = data.get(f"F{n}", state)
                    _state.update_address(address, functions={n: reported})
                    print(f"address={address} F{n}={'on' if reported else 'off'}")
                except JmriWsError as exc:
                    print(f"Error: F{n}: {exc}", file=sys.stderr)
                    ok = False
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0 if ok else 1


async def throttle_on(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Turn one or more decoder functions on.

    `args.function` may be a number (F0-F28), a fragment of a roster-set
    function label ("phares" matches a label containing it), or omitted
    entirely to turn on every labeled function for this loco. There is no
    F0-is-headlight fallback: F-number meaning is decoder/roster-specific,
    not a protocol guarantee (see jmri_mcp.tools.throttle's set_function
    docstring) — an unlabeled loco with no function number given is a
    clear error asking for one, not a guess.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address) and `args.function` (number, label fragment, or
            None).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every resolved function confirmed on, 1 if JMRI is
        unreachable, nothing resolves, or any command was rejected.
    """
    return await _throttle_set_functions(args, state=True, client=client)


async def throttle_off(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Turn one or more decoder functions off. See throttle_on for `args.function` rules.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address) and `args.function` (number, label fragment, or
            None).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every resolved function confirmed off, 1 if JMRI is
        unreachable, nothing resolves, or any command was rejected.
    """
    return await _throttle_set_functions(args, state=False, client=client)


def _format_sniff_data(msg_type: str, data) -> str:
    """Compact a JMRI message's data for one-line display.

    Throttle messages list every function key (F0-F68) even when only one
    changed, which drowns the field that actually changed — collapse them
    to just the functions currently ON, dropped entirely if none are.

    Args:
        msg_type: JMRI's message "type" field (e.g. "throttle", "pong").
        data: JMRI's message "data" field, of whatever shape `msg_type` implies.

    Returns:
        A JSON string of `data`, with active F<n> fields collapsed into a
        single "functions_on" list when `msg_type` is "throttle".
    """
    if msg_type == "throttle" and isinstance(data, dict):
        data = dict(data)
        active_functions = sorted(
            (k for k, v in data.items() if k[0] == "F" and k[1:].isdigit() and v),
            key=lambda k: int(k[1:]),
        )
        for key in list(data):
            if key[0] == "F" and key[1:].isdigit():
                del data[key]
        if active_functions:
            data["functions_on"] = active_functions
    return json.dumps(data)


async def throttle_sniff(args: argparse.Namespace) -> int:
    """Dump every JMRI WebSocket message on this connection until Ctrl-C.

    With no --address, this only sees hello/pong and whatever this
    connection itself triggers. Pass --address (repeatable) to also acquire
    those locos first — JMRI then pushes every state change on them from
    ANY client (other MCP sessions, JMRI panels, throttle apps) to this
    connection too, which is the point: watching what's actually moving on
    the layout, not just what this tool sends. Keepalive pong messages are
    hidden by default (--show-pong to include them) since they carry no
    information and fire every few seconds regardless of layout activity.

    Args:
        args: Parsed CLI arguments; uses `args.address` (list of DCC
            addresses to acquire first, or None) and `args.show_pong`
            (whether to print keepalive pong messages).

    Returns:
        0 on a clean Ctrl-C exit, 1 if the connection itself errors out.
    """

    async def on_message(msg_type: str, data) -> None:
        if msg_type == "pong" and not args.show_pong:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] {msg_type}: {_format_sniff_data(msg_type, data)}")

    client = JmriWsClient(on_message=on_message)
    try:
        await client.connect()
        for address in args.address or []:
            try:
                await client.acquire_throttle(f"{SNIFF_THROTTLE_ID_PREFIX}{address}", address)
                print(f"(acquired address={address} for observation)")
            except JmriWsError as exc:
                print(f"Warning: could not acquire {address}: {exc}", file=sys.stderr)

        print("Listening for JMRI messages, Ctrl-C to stop...", file=sys.stderr)
        while True:
            await asyncio.sleep(IDLE_POLL_SECONDS)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.close()
    return 0
