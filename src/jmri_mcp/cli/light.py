"""Layout light commands: `jmri-cli light [list|on|off]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
These are JMRI `light` objects wired to the layout/scenery itself (depot
lighting, street lamps, ...), distinct from a locomotive's F0 headlight
function (see `jmri-cli throttle on/off` for that).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.constants.cli import SORT_INDICATOR, LIGHT_STATE_NAMES
from jmri_mcp.jmri_client import JmriError, get_lights, resolve_light
from jmri_mcp.jmri_client import set_light as _set_light
from jmri_mcp.jmri_client.light import LIGHT_ON, LIGHT_OFF


def _headers(*, sorted_by_system_id: bool = False) -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    system_id = i18n.t("headers.system_id")
    if sorted_by_system_id:
        system_id += SORT_INDICATOR
    return [system_id, i18n.t("headers.light"), i18n.t("headers.state")]


def _row(light: dict) -> list:
    """Flatten one JMRI light object into a `[system_id, label, state]` table row."""
    state = LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN")
    label = light.get("userName") or light.get("name", "?")
    system_id = light.get("name", "?")
    return [system_id, label, state]


def _label(light: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(light.get("userName") or light.get("name", ""))


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
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not lights:
        print(i18n.t("cli.no_entities_found", kind="light"))
        return 0
    rows = [_row(lt) for lt in sorted(lights, key=lambda lt: lt.get("name", "?"))]
    print(tabulate(rows, headers=_headers(sorted_by_system_id=True)))
    return 0


async def light_find(args: argparse.Namespace) -> int:
    """Resolve a light name/fragment/system ID to its full state, roster-`find`-style.

    Args:
        args: Parsed CLI arguments; uses `args.name` (userName, a fragment
            of it, or JMRI's own system ID like "IL1").

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` is ambiguous
        or matches no light.
    """
    try:
        lights = await get_lights()
        light = resolve_light(args.name, lights)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, state = _row(light)
    print(f"system_id={system_id} name={label} state={state}")
    return 0


async def _light_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for light_findr/light_findg: list every light matching a pattern.

    Unlike light_find, a pattern can legitimately match zero, one, or many
    lights — no ambiguity error, just a filtered `light list`-style table
    (or "no lights match" if the pattern matches nothing).
    """
    try:
        lights = await get_lights()
        matcher = find_regex if regex else find_glob
        matches = matcher(args.pattern, lights, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="light", pattern=args.pattern))
        return 0
    rows = [_row(lt) for lt in sorted(matches, key=lambda lt: lt.get("name", "?"))]
    print(tabulate(rows, headers=_headers(sorted_by_system_id=True)))
    return 0


async def light_findr(args: argparse.Namespace) -> int:
    """List every light whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each light's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _light_find_pattern(args, regex=True)


async def light_findg(args: argparse.Namespace) -> int:
    """List every light whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each light's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _light_find_pattern(args, regex=False)


async def _light_set(args: argparse.Namespace, *, turn_on: bool) -> int:
    """Shared body for light_on/light_off.

    No `args.name` means every light; a fuzzy `args.name` means just that
    one, matching power/turnout's "verb + optional target, default = all".
    """
    state_name = LIGHT_STATE_NAMES[LIGHT_ON if turn_on else LIGHT_OFF]
    try:
        lights = await get_lights()
        targets = [resolve_light(args.name, lights)] if args.name else lights
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
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
        print(i18n.error(exc), file=sys.stderr)
        return 1

    print(tabulate(rows, headers=_headers()))
    if not all_confirmed:
        print(i18n.t("cli.not_every_entity_confirmed", kind="light", state=state_name), file=sys.stderr)
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
