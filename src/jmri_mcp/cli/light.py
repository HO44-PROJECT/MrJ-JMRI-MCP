"""Layout light commands: `jmri-cli light [list|on|off]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
These are JMRI `light` objects wired to the layout/scenery itself (depot
lighting, street lamps, ...), distinct from a locomotive's F0 headlight
function (see `jmri-cli throttle on/off` for that).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp.cli.constants import LIGHT_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_lights, resolve_light
from jmri_mcp.jmri_client import set_light as _set_light


def _row(light: dict) -> list:
    state = LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN")
    label = light.get("userName") or light.get("name", "?")
    return [label, state]


async def light_list(args: argparse.Namespace) -> int:
    """Print the state of every layout light, sorted alphabetically.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no lights), 1 if JMRI is unreachable.
    """
    try:
        lights = await get_lights()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not lights:
        print("No lights found")
        return 0
    rows = [_row(lt) for lt in sorted(lights, key=lambda lt: _row(lt)[0].casefold())]
    print(tabulate(rows, headers=["Light", "State"]))
    return 0


async def _light_set(args: argparse.Namespace, *, turn_on: bool) -> int:
    """Shared body for light_on/light_off.

    No `args.name` means every light; a fuzzy `args.name` means just that
    one, matching power/turnout's "verb + optional target, default = all".
    """
    state_name = "ON" if turn_on else "OFF"
    try:
        lights = await get_lights()
        targets = [resolve_light(args.name, lights)] if args.name else lights
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    all_confirmed = True
    rows = []
    try:
        for target in targets:
            result = await _set_light(target["name"], turn_on)
            rows.append(_row(result))
            if not result["confirmed"]:
                all_confirmed = False
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(tabulate(rows, headers=["Light", "State"]))
    if not all_confirmed:
        print(f"WARNING: not every light confirmed {state_name} after re-read", file=sys.stderr)
        return 1
    return 0


async def light_on(args: argparse.Namespace) -> int:
    """Turn a light on, or every light if none is given, confirming by re-read.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            fragment, or None for every light).

    Returns:
        0 on success with every targeted light confirmed ON, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or any re-read
        didn't confirm ON.
    """
    return await _light_set(args, turn_on=True)


async def light_off(args: argparse.Namespace) -> int:
    """Turn a light off, or every light if none is given, confirming by re-read.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            fragment, or None for every light).

    Returns:
        0 on success with every targeted light confirmed OFF, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or any re-read
        didn't confirm OFF.
    """
    return await _light_set(args, turn_on=False)
