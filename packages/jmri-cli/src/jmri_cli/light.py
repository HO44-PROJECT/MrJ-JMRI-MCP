"""Layout light commands: `jmri-cli light [list|on|off]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
These are JMRI `light` objects wired to the layout/scenery itself (depot
lighting, street lamps, ...), distinct from a locomotive's F0 headlight
function (see `jmri-cli throttle on/off` for that).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_core import i18n
from jmri_cli._match import find_glob, find_regex
from jmri_cli._sort import mark_sorted_header, sort_rows, split_find_tokens
from jmri_core.constants.cli import SORT_INDICATOR, LIGHT_STATE_NAMES
from jmri_core.jmri_client import JmriError, get_lights, resolve_light
from jmri_core.jmri_client import set_light as _set_light
from jmri_core.jmri_client.light import LIGHT_ON, LIGHT_OFF
from jmri_cli._dcc_system import dcc_system_display, system_names_by_prefix


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [
        i18n.t("headers.system_id"),
        i18n.t("headers.light"),
        i18n.t("headers.state"),
        i18n.t("headers.comment"),
        i18n.t("headers.dcc_system"),
    ]


# `light by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byid": (0, True),
    "byname": (1, True),
    "bystate": (2, True),
    "bycomment": (3, True),
    "bydccsystem": (4, True),
}


def _row(light: dict, names_by_prefix: dict[str, str]) -> list:
    """Flatten one JMRI light object into a `[system_id, label, state, comment, dcc_system]` table row."""
    state = LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN")
    label = light.get("userName") or light.get("name", "?")
    system_id = light.get("name", "?")
    comment = light.get("comment") or ""
    dcc_system = dcc_system_display(system_id, names_by_prefix)
    return [system_id, label, state, comment, dcc_system]


def _label(light: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(light.get("userName") or light.get("name", ""))


async def light_list(args: argparse.Namespace) -> int:
    """Print the state of every layout light.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS, e.g.
            "byid"/"bystate") picks the sort order - set by parser.py to a
            fixed value per `by*` sibling leaf (defaults to "byname" for
            bare `light`/`light list`).

    Returns:
        0 on success (including no lights), 1 if JMRI is unreachable.
    """
    try:
        lights = await get_lights()
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not lights:
        print(i18n.t("cli.no_entities_found", kind="light"))
        return 0
    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows([_row(lt, names_by_prefix) for lt in lights], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
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
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, state, comment, dcc_system = _row(light, names_by_prefix)
    print(
        f"system_id={system_id} name={label} state={state} "
        f"comment={comment or '-'} dcc_system={dcc_system}"
    )
    return 0


async def _light_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for light_findr/light_findg: list every light matching a pattern.

    Unlike light_find, a pattern can legitimately match zero, one, or many
    lights — no ambiguity error, just a filtered `light list`-style table
    (or "no lights match" if the pattern matches nothing).
    """
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        lights = await get_lights()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, lights, _label)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="light", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(lt, names_by_prefix) for lt in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
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
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    all_confirmed = True
    rows = []
    try:
        for target in targets:
            result = await _set_light(target["name"], turn_on)
            rows.append(_row(result, names_by_prefix))
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
