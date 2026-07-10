"""Turnout commands: `jmri-cli turnout list`, `turnout status`, `turnout set`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Uses JMRI/PanelPro's own CLOSED/THROWN vocabulary (not "open"/"closed"
track terminology, which is ambiguous about which direction is which).
"""

import argparse
import sys

from jmri_mcp.cli.constants import TURNOUT_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_turnouts, resolve_turnout
from jmri_mcp.jmri_client import set_turnout as _set_turnout


def _format_turnout(turnout: dict) -> str:
    """Format one turnout's state as a single display line.

    Args:
        turnout: A turnout dict as returned by jmri_client.get_turnouts(),
            with at least "name" and "state", and optionally "userName".

    Returns:
        A line like "Layout Turnout A   : CLOSED".
    """
    state = TURNOUT_STATE_NAMES.get(turnout.get("state"), "UNKNOWN")
    label = turnout.get("userName") or turnout.get("name", "?")
    return f"{label:<20}: {state}"


async def turnout_list(args: argparse.Namespace) -> int:
    """Print the state of every turnout.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no turnouts), 1 if JMRI is unreachable.
    """
    try:
        turnouts = await get_turnouts()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not turnouts:
        print("No turnouts found")
        return 0
    for turnout in turnouts:
        print(_format_turnout(turnout))
    return 0


async def turnout_status(args: argparse.Namespace) -> int:
    """Print the state of one turnout.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one turnout.
    """
    try:
        turnouts = await get_turnouts()
        match = resolve_turnout(args.name, turnouts)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(_format_turnout(match))
    return 0


async def turnout_set(args: argparse.Namespace) -> int:
    """Set a turnout closed or thrown, and confirm by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment) and `args.state` ("closed" or
            "thrown").

    Returns:
        0 on success with the requested state confirmed, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        state doesn't confirm the request.
    """
    thrown = args.state == "thrown"
    try:
        turnouts = await get_turnouts()
        match = resolve_turnout(args.name, turnouts)
        result = await _set_turnout(match["name"], thrown)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_turnout(result))
    if not result["confirmed"]:
        print(f"WARNING: requested {args.state.upper()} but observed state "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0
