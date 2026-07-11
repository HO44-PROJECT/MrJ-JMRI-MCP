"""Turnout commands: `jmri-cli turnout [list|closed|thrown]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Uses JMRI/PanelPro's own CLOSED/THROWN vocabulary (not "open"/"closed"
track terminology, which is ambiguous about which direction is which).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp.cli.constants import TURNOUT_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_turnouts, resolve_turnout
from jmri_mcp.jmri_client import set_turnout as _set_turnout


def _row(turnout: dict) -> list:
    state = TURNOUT_STATE_NAMES.get(turnout.get("state"), "UNKNOWN")
    label = turnout.get("userName") or turnout.get("name", "?")
    return [label, state]


async def turnout_list(args: argparse.Namespace) -> int:
    """Print the state of every turnout, sorted alphabetically.

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
    rows = [_row(t) for t in sorted(turnouts, key=lambda t: _row(t)[0].casefold())]
    print(tabulate(rows, headers=["Turnout", "State"]))
    return 0


async def _turnout_set(args: argparse.Namespace, *, thrown: bool) -> int:
    """Shared body for turnout_closed/turnout_thrown.

    No `args.name` means every turnout; a fuzzy `args.name` means just
    that one, matching power/light's "verb + optional target, default =
    all".
    """
    state_name = "THROWN" if thrown else "CLOSED"
    try:
        turnouts = await get_turnouts()
        targets = [resolve_turnout(args.name, turnouts)] if args.name else turnouts
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    all_confirmed = True
    rows = []
    try:
        for target in targets:
            result = await _set_turnout(target["name"], thrown)
            rows.append(_row(result))
            if not result["confirmed"]:
                all_confirmed = False
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(tabulate(rows, headers=["Turnout", "State"]))
    if not all_confirmed:
        print(f"WARNING: not every turnout confirmed {state_name} after re-read", file=sys.stderr)
        return 1
    return 0


async def turnout_closed(args: argparse.Namespace) -> int:
    """Set a turnout closed, or every turnout if none is given, confirming by re-read.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            fragment, or None for every turnout).

    Returns:
        0 on success with every targeted turnout confirmed CLOSED, 1 if
        JMRI is unreachable, `args.name` is ambiguous/unknown, or any
        re-read didn't confirm CLOSED.
    """
    return await _turnout_set(args, thrown=False)


async def turnout_thrown(args: argparse.Namespace) -> int:
    """Set a turnout thrown, or every turnout if none is given, confirming by re-read.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            fragment, or None for every turnout).

    Returns:
        0 on success with every targeted turnout confirmed THROWN, 1 if
        JMRI is unreachable, `args.name` is ambiguous/unknown, or any
        re-read didn't confirm THROWN.
    """
    return await _turnout_set(args, thrown=True)
