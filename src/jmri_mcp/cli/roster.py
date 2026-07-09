"""Roster commands: `jmri-cli roster`, `roster find`, `roster functions`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
"""

import argparse
import sys

from jmri_mcp.jmri_client import (
    JmriError,
    get_roster,
    get_roster_function_labels,
    resolve_roster_entry,
)


async def roster_list(args: argparse.Namespace) -> int:
    """Print every locomotive in JMRI's roster: address, name, road, model.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including an empty roster), 1 if JMRI is unreachable.
    """
    try:
        roster = await get_roster()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not roster:
        print("Roster is empty")
        return 0
    for entry in roster:
        road = entry["road"] or "-"
        model = entry["model"] or "-"
        print(f"{entry['address']:<5} {entry['name']:<20} {road:<30} {model}")
    return 0


async def roster_find(args: argparse.Namespace) -> int:
    """Resolve a locomotive name (fuzzy, accent-insensitive) to its roster entry.

    Args:
        args: Parsed CLI arguments; uses `args.name` (a full name or fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` is ambiguous
        or matches no roster entry.
    """
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.name, roster)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    road = entry["road"] or "-"
    model = entry["model"] or "-"
    print(f"address={entry['address']} name={entry['name']} road={road} model={model}")
    return 0


async def roster_functions(args: argparse.Namespace) -> int:
    """Print a locomotive's user-labeled decoder functions (F0-F28).

    Resolves `args.name` the same fuzzy way as `roster_find`, then looks up
    the function labels the user set in JMRI's own roster editor. Most
    locos have none set at all — that's reported plainly, not as an error.

    Args:
        args: Parsed CLI arguments; uses `args.name` (a full name or fragment).

    Returns:
        0 on success (including no labeled functions), 1 if JMRI is
        unreachable or `args.name` is ambiguous or matches no roster entry.
    """
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.name, roster)
        labels = await get_roster_function_labels(entry["name"])
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{entry['name']} (address={entry['address']})")
    if not labels:
        print("  no labeled functions")
        return 0
    for n in sorted(labels):
        print(f"  F{n}: {labels[n]}")
    return 0
