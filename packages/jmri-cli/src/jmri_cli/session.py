"""Top-level `session-start`/`session-end` composite commands (issue #49).

Pure orchestration over already-working, unmodified commands - no new
low-level throttle/power logic here. Each step is the exact same function
`jmri-cli power on`/`power off`/`throttle stop`/`throttle engine-start`/
`throttle engine-stop` already runs on its own, called here in sequence
with no explicit target so each falls back to its own existing "every
system"/"every touched locomotive" default (state.py's local cache for
the throttle steps).
"""

import argparse
import sys

from jmri_core import i18n
from jmri_core.jmri_ws import JmriWsClient

from jmri_cli import power, throttle


async def session_start(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Power on every system, then wake up every touched locomotive.

    Runs `power on` (no target -> every system) followed by `engine-start`
    (no loco -> every locomotive in state.py's touched-address cache,
    forward + lights on). Sequential: power is confirmed on before any
    locomotive is woken up. A failure in either step is surfaced (non-zero
    exit) but engine-start still runs even if a specific system's power-on
    wasn't confirmed, matching the "one failure doesn't abort the rest"
    convention used throughout this CLI's cache-fallback commands.

    Args:
        args: Parsed CLI arguments; takes no fields of its own.
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if power-on and engine-start both fully succeeded, 1 otherwise.
    """
    power_ok = await power.power_on(argparse.Namespace(system=None)) == 0
    engine_ok = await throttle.throttle_engine_start(
        argparse.Namespace(loco=None, prefix=None), client=client,
    ) == 0
    return 0 if power_ok and engine_ok else 1


async def session_end(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Stop every touched locomotive, put each to rest, then power off every system.

    Runs `stop` (no loco -> every locomotive in state.py's touched-address
    cache, controlled stop) then `engine-stop` (same cache, ramp down if
    still moving, forward, lights off, release) then `power off` (no
    target -> every system, doubling as the layout-wide emergency cutoff).
    Strictly sequential and each step is awaited to completion before the
    next starts, so power is never cut while a locomotive might still be
    moving. A failure in one locomotive's stop/engine-stop doesn't skip
    the rest of the cache, and doesn't skip the final power-off - but is
    still surfaced via a non-zero exit code. With an empty touched-address
    cache, stop/engine-stop are no-ops (as they already are standalone)
    and this reduces to just `power off`.

    Args:
        args: Parsed CLI arguments; takes no fields of its own.
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if stop, engine-stop and power-off all fully succeeded, 1 otherwise.
    """
    stop_ok = await throttle.throttle_stop(
        argparse.Namespace(loco=None, rampdown=None), client=client,
    ) == 0
    engine_ok = await throttle.throttle_engine_stop(
        argparse.Namespace(loco=None), client=client,
    ) == 0
    power_ok = await power.power_off(argparse.Namespace(system=None)) == 0
    if not (stop_ok and engine_ok and power_ok):
        print(i18n.t("cli.session_end_partial_failure"), file=sys.stderr)
        return 1
    return 0
