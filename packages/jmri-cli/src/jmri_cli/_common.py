"""Small helpers shared across jmri-cli's command modules."""

import asyncio
import contextlib
import inspect
from pathlib import Path

from jmri_core.constants.cli import CLI_THROTTLE_ID_PREFIX

HISTORY_FILE = Path.home() / ".jmri-cli" / "shell_history"
"""Persisted readline command history for the interactive shell (shell.py).
Lives here rather than in shell.py itself so cache.py's `cache clean` can
reference it without importing shell.py, which would create a cycle
(parser.py -> cache.py -> shell.py -> parser.py)."""

HISTORY_MAX_LINES = 1000


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


def is_ws_func(func) -> bool:
    """Whether `func` (a parser leaf's `args.func`, possibly a
    functools.partial) accepts a `client` keyword — i.e. it holds/mutates
    JMRI throttle state (acquire, release, speed, functions, engine-start/
    stop, session-start/end) rather than being a one-shot HTTP/local-cache
    command (power, roster, status, find, cache).

    A one-shot invocation of one of these can never leave the locomotive
    in the state it just set: JMRI releases a throttle the instant its
    WebSocket connection closes, and jmri-cli's one-shot connection always
    closes right after the command returns (see throttle.py's module
    docstring and `_client_scope`). Releasing while a function like lights
    is still active also leaves the decoder in an unpredictable state
    (issue #59, verified live) — so this is not just "won't persist", it's
    actively unsafe. `main()` uses this to refuse these commands outside
    the shell instead of silently running them and undoing themselves.
    """
    try:
        return "client" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


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


async def wait_for_holds(addresses: list[int] | None) -> None:
    """Block until pending `--hold` background tasks finish.

    With `addresses` given, waits only for those; with None, waits for
    every hold currently pending. Lets a `;`-chained batch place an
    explicit "wait for the hold to finish" step between a `--hold` and a
    following command (e.g. `speed 4 20 --hold 5; wait 4; release 4`)
    instead of the two racing — see throttle.py's `wait` command.
    """
    if addresses is None:
        tasks = list(background_holds.values())
    else:
        tasks = [background_holds[a] for a in addresses if a in background_holds]
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


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
