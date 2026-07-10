"""Layout light commands: `jmri-cli light list`, `light status`, `light set`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
These are JMRI `light` objects wired to the layout/scenery itself (depot
lighting, street lamps, ...), distinct from a locomotive's F0 headlight
function (see `jmri-cli throttle lights-on`/`lights-off` for that).
"""

import argparse
import sys

from jmri_mcp.cli.constants import LIGHT_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_lights, resolve_light
from jmri_mcp.jmri_client import set_light as _set_light


def _format_light(light: dict) -> str:
    """Format one light's state as a single display line.

    Args:
        light: A light dict as returned by jmri_client.get_lights(), with
            at least "name" and "state", and optionally "userName".

    Returns:
        A line like "Depot Lighting  : ON".
    """
    state = LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN")
    label = light.get("userName") or light.get("name", "?")
    return f"{label:<20}: {state}"


async def light_list(args: argparse.Namespace) -> int:
    """Print the state of every layout light.

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
    for light in lights:
        print(_format_light(light))
    return 0


async def light_status(args: argparse.Namespace) -> int:
    """Print the state of one layout light.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one light.
    """
    try:
        lights = await get_lights()
        match = resolve_light(args.name, lights)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(_format_light(match))
    return 0


async def light_set(args: argparse.Namespace) -> int:
    """Turn a layout light on or off, and confirm by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment) and `args.state` ("on" or "off").

    Returns:
        0 on success with the requested state confirmed, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        state doesn't confirm the request.
    """
    turn_on = args.state == "on"
    try:
        lights = await get_lights()
        match = resolve_light(args.name, lights)
        result = await _set_light(match["name"], turn_on)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_light(result))
    if not result["confirmed"]:
        print(f"WARNING: requested {args.state.upper()} but observed state "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0
