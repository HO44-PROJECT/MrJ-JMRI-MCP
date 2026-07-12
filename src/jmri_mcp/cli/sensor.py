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
from jmri_mcp.cli._sort import mark_sorted_header, sort_rows, split_find_tokens
from jmri_mcp.constants.cli import SORT_INDICATOR, SENSOR_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_sensors, resolve_sensor


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [i18n.t("headers.system_id"), i18n.t("headers.sensor"), i18n.t("headers.state")]


# `sensor by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byid": (0, True),
    "byname": (1, True),
    "bystate": (2, True),
}


def _row(sensor: dict) -> list:
    """Flatten one JMRI sensor object into a `[system_id, label, state]` table row."""
    state = SENSOR_STATE_NAMES.get(sensor.get("state"), "UNKNOWN")
    label = sensor.get("userName") or sensor.get("name", "?")
    system_id = sensor.get("name", "?")
    return [system_id, label, state]


def _label(sensor: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(sensor.get("userName") or sensor.get("name", ""))


async def sensor_list(args: argparse.Namespace) -> int:
    """Print the state of every sensor.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS, e.g.
            "byid"/"bystate") picks the sort order - set by parser.py to a
            fixed value per `by*` sibling leaf (defaults to "byname" for
            bare `sensor`/`sensor list`).

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
    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows([_row(s) for s in sensors], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
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

    system_id, label, state = _row(match)
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
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        sensors = await get_sensors()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, sensors, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="sensor", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(s) for s in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
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
