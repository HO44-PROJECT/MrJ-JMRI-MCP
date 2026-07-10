"""Sensor commands: `jmri-cli sensor list`, `sensor status`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Sensors are read-only — they report real-world state JMRI detects (block
occupancy, turnout motor feedback, a clock-running flag, ...), so there is
no `sensor set` subcommand.
"""

import argparse
import sys

from jmri_mcp.cli.constants import SENSOR_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_sensors, resolve_sensor


def _format_sensor(sensor: dict) -> str:
    """Format one sensor's state as a single display line.

    Args:
        sensor: A sensor dict as returned by jmri_client.get_sensors(),
            with at least "name" and "state", and optionally "userName".

    Returns:
        A line like "Montagne B          : ACTIVE".
    """
    state = SENSOR_STATE_NAMES.get(sensor.get("state"), "UNKNOWN")
    label = sensor.get("userName") or sensor.get("name", "?")
    return f"{label:<20}: {state}"


async def sensor_list(args: argparse.Namespace) -> int:
    """Print the state of every sensor.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no sensors), 1 if JMRI is unreachable.
    """
    try:
        sensors = await get_sensors()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not sensors:
        print("No sensors found")
        return 0
    for sensor in sensors:
        print(_format_sensor(sensor))
    return 0


async def sensor_status(args: argparse.Namespace) -> int:
    """Print the state of one sensor.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one sensor.
    """
    try:
        sensors = await get_sensors()
        match = resolve_sensor(args.name, sensors)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(_format_sensor(match))
    return 0
