"""Signal mast commands: `jmri-cli signal list`, `signal status`, `signal set`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Covers signalMast only, not signalHead — see
jmri_mcp.jmri_client.signal's module docstring for why.
"""

import argparse
import sys

from jmri_mcp.jmri_client import JmriError, get_signals, resolve_signal
from jmri_mcp.jmri_client import set_signal as _set_signal


def _format_signal(signal: dict) -> str:
    """Format one signal mast's state as a single display line.

    Args:
        signal: A signal dict as returned by jmri_client.get_signals(),
            with at least "name" and "aspect", and optionally "userName".

    Returns:
        A line like "Entry Signal A      : Hp1".
    """
    aspect = signal.get("aspect") or "UNKNOWN"
    label = signal.get("userName") or signal.get("name", "?")
    return f"{label:<20}: {aspect}"


async def signal_list(args: argparse.Namespace) -> int:
    """Print the state of every signal mast.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no signal masts), 1 if JMRI is unreachable.
    """
    try:
        signals = await get_signals()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not signals:
        print("No signal masts found")
        return 0
    for signal in signals:
        print(_format_signal(signal))
    return 0


async def signal_status(args: argparse.Namespace) -> int:
    """Print the state of one signal mast.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one signal mast.
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(_format_signal(match))
    return 0


async def signal_set(args: argparse.Namespace) -> int:
    """Set a signal mast's aspect, and confirm by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment) and `args.aspect` (e.g. "Hp0",
            "Hp1" — not validated locally, see jmri_client.signal's module
            docstring for why).

    Returns:
        0 on success with the requested aspect confirmed, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        aspect doesn't confirm the request.
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
        result = await _set_signal(match["name"], args.aspect)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_signal(result))
    if not result["confirmed"]:
        print(f"WARNING: requested aspect {args.aspect!r} but observed aspect "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0
