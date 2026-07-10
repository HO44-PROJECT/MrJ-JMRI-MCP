"""Power-system commands: `jmri-cli power status`, `power set`, `status`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
"""

import argparse
import sys

from jmri_mcp.cli.constants import POWER_STATE_NAMES
from jmri_mcp.jmri_client import (
    JmriError,
    get_systems,
    get_version,
    power_off_all,
    power_on_all,
    resolve_system,
    set_power,
)


def _format_system(system: dict) -> str:
    """Format one power system's state as a single display line.

    Args:
        system: A system dict as returned by jmri_client.get_systems(),
            with at least "name" and "state", and optionally "default".

    Returns:
        A line like "DCC++ Ohara    : ON (default)".
    """
    state = POWER_STATE_NAMES.get(system.get("state"), "UNKNOWN")
    marker = " (default)" if system.get("default") else ""
    return f"{system.get('name', '?'):<15}: {state}{marker}"


async def power_status(args: argparse.Namespace) -> int:
    """Print the power state of every system, or one if `args.system` is set.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name/prefix/fragment,
            or None for all systems).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.system` doesn't
        resolve to exactly one system.
    """
    try:
        systems = await get_systems()
        if args.system:
            match = resolve_system(args.system, systems)
            print(_format_system(match))
        else:
            for system in systems:
                print(_format_system(system))
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


async def power_set(args: argparse.Namespace) -> int:
    """Turn a system's power on or off, and confirm by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name/prefix/fragment)
            and `args.state` ("on" or "off").

    Returns:
        0 on success with the requested state confirmed, 1 if JMRI is
        unreachable, `args.system` is ambiguous/unknown, or the re-read
        state doesn't confirm the request.
    """
    turn_on = args.state == "on"
    try:
        systems = await get_systems()
        match = resolve_system(args.system, systems)
        result = await set_power(match["prefix"], turn_on)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_system(result))
    if not result["confirmed"]:
        print(f"WARNING: requested {args.state.upper()} but observed state "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0


async def _power_set_all(turn_on: bool) -> int:
    """Shared body for power_stop_all/power_start_all — see their docstrings."""
    try:
        results = await (power_on_all() if turn_on else power_off_all())
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    state_name = "ON" if turn_on else "OFF"
    all_confirmed = True
    for result in results:
        print(_format_system(result))
        if not result["confirmed"]:
            all_confirmed = False
    if not all_confirmed:
        print(f"WARNING: not every system confirmed {state_name} after re-read", file=sys.stderr)
        return 1
    return 0


async def power_stop_all(args: argparse.Namespace) -> int:
    """Cut power to every DCC system at once, confirming each by re-read.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 if every system confirmed OFF, 1 if JMRI is unreachable or any
        system's re-read didn't confirm OFF.
    """
    return await _power_set_all(turn_on=False)


async def power_start_all(args: argparse.Namespace) -> int:
    """Restore power to every DCC system at once, confirming each by re-read.

    The inverse of power_stop_all. Does NOT resume any locomotive's
    previous speed — decoders stay stopped until a new speed command is
    sent, this only restores track power.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 if every system confirmed ON, 1 if JMRI is unreachable or any
        system's re-read didn't confirm ON.
    """
    return await _power_set_all(turn_on=True)


async def system_status(args: argparse.Namespace) -> int:
    """Run a one-call diagnostic: JMRI reachability, version, power systems.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 if JMRI is reachable (regardless of individual power states),
        1 if JMRI is unreachable or power systems can't be listed.
    """
    try:
        version = await get_version()
    except JmriError as exc:
        print(f"JMRI unreachable: {exc}", file=sys.stderr)
        return 1

    print(f"JMRI reachable, version {version}")
    try:
        systems = await get_systems()
        for system in systems:
            print(f"  {_format_system(system)}")
    except JmriError as exc:
        print(f"  Power systems unavailable: {exc}", file=sys.stderr)
        return 1
    return 0
