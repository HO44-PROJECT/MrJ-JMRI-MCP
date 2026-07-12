"""Sensor commands: `jmri-cli sensor [list|find|findr|findg|status]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Sensors are read-only — they report real-world state JMRI detects (block
occupancy, turnout motor feedback, a clock-running flag, ...), so there is
no `sensor set` subcommand.
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.constants.cli import SORT_INDICATOR, SENSOR_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_sensors, resolve_sensor


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG. Sensor listings are always sorted by name, so the sort indicator is unconditional."""
    return [i18n.t("headers.sensor") + SORT_INDICATOR, i18n.t("headers.system_id"), i18n.t("headers.state")]


def _row(sensor: dict) -> list:
    """Flatten one JMRI sensor object into a `[label, system_id, state]` table row."""
    state = SENSOR_STATE_NAMES.get(sensor.get("state"), "UNKNOWN")
    label = sensor.get("userName") or sensor.get("name", "?")
    system_id = sensor.get("name", "?")
    return [label, system_id, state]


def _label(sensor: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(sensor.get("userName") or sensor.get("name", ""))


async def sensor_list(args: argparse.Namespace) -> int:
    """Print the state of every sensor, sorted alphabetically.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no sensors), 1 if JMRI is unreachable.
    """
    try:
        sensors = await get_sensors()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not sensors:
        print(i18n.t("cli.no_entities_found", kind="sensor"))
        return 0
    rows = [_row(s) for s in sorted(sensors, key=lambda s: _row(s)[0].casefold())]
    print(tabulate(rows, headers=_headers()))
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
        print(i18n.error(exc), file=sys.stderr)
        return 1

    label, system_id, state = _row(match)
    print(f"name={label} system_id={system_id} state={state}")
    return 0


async def sensor_find(args: argparse.Namespace) -> int:
    """Resolve a sensor name/fragment/system ID to its full state.

    Identical body to `sensor_status` — `find` is the naming this project
    uses consistently for "resolve one, no side effects" across every
    domain (roster/turnout/light/power/throttle/signal); `status` is kept
    as an alias since it predates that convention.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one sensor.
    """
    return await sensor_status(args)


async def _sensor_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for sensor_findr/sensor_findg: list every sensor matching a pattern.

    Unlike sensor_find, a pattern can legitimately match zero, one, or many
    sensors — no ambiguity error, just a filtered `sensor list`-style table
    (or "no sensors match" if the pattern matches nothing).
    """
    try:
        sensors = await get_sensors()
        matcher = find_regex if regex else find_glob
        matches = matcher(args.pattern, sensors, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="sensor", pattern=args.pattern))
        return 0
    rows = [_row(s) for s in sorted(matches, key=lambda s: _row(s)[0].casefold())]
    print(tabulate(rows, headers=_headers()))
    return 0


async def sensor_findr(args: argparse.Namespace) -> int:
    """List every sensor whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each sensor's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _sensor_find_pattern(args, regex=True)


async def sensor_findg(args: argparse.Namespace) -> int:
    """List every sensor whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each sensor's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _sensor_find_pattern(args, regex=False)
