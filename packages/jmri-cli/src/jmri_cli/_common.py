"""Small helpers shared across jmri-cli's command modules."""

import asyncio

from jmri_core.constants.cli import CLI_THROTTLE_ID_PREFIX


def cli_throttle_id(address: int) -> str:
    """Derive this CLI's own JMRI throttle id for a DCC address.

    Each jmri-cli invocation opens a fresh WebSocket connection (see
    module docstring in jmri_cli), so there is no cross-invocation
    state to key off of — the address itself, prefixed, is enough to
    identify the throttle to JMRI for the lifetime of one command.

    Args:
        address: The locomotive's DCC address.

    Returns:
        A throttle id string unique to this address, e.g. "cli3".
    """
    return f"{CLI_THROTTLE_ID_PREFIX}{address}"


background_holds: dict[int, asyncio.Task] = {}
"""Live asyncio.Task handles for shell-mode `--hold` sequences running in the
background, keyed by DCC address (not a flat set — see run_hold_in_background,
which needs to find and cancel the ONE task for an address a new command is
about to supersede). Scoped to one shell session's lifetime, same as
JmriWsClient itself; run_shell()'s shutdown awaits whatever's left so a hold
is never abandoned on a clean exit, mirroring jmri-mcp's own
tools/_common.py:background_tasks/run_in_background for the analogous
set_speed_ramped case.
"""


def run_hold_in_background(address: int, coro) -> None:
    """Schedule `coro` (a hold-and-auto-stop sequence for `address`) to run
    after the current shell command returns, cancelling any hold already
    pending for that same address first.

    Superseding rather than letting both race matters here: a second
    `throttle speed`/`forward`/`reverse --hold` on the same address means
    the user wants to replace what that loco is currently doing, not queue
    a second auto-stop behind the first one.

    Args:
        address: DCC address the hold applies to — the supersede key.
        coro: An awaitable (a call to execute_speed_change(...)) to run
            without the caller waiting for it.
    """
    pending = background_holds.get(address)
    if pending is not None and not pending.done():
        pending.cancel()
    task = asyncio.create_task(coro)
    background_holds[address] = task
    task.add_done_callback(
        lambda t, address=address: (
            background_holds.pop(address, None) if background_holds.get(address) is t else None
        )
    )
