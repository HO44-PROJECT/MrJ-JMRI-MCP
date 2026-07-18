"""Turnout commands: `jmri-cli turnout [list|find|findr|findg|close|throw]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
The CLI verbs are `close`/`throw` (natural imperatives); the resulting
*state* is still reported using JMRI/PanelPro's own CLOSED/THROWN
vocabulary (not "open"/"closed" track terminology, which is ambiguous
about which direction is which).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_core import i18n
from jmri_cli._match import find_glob, find_regex
from jmri_cli._sort import mark_sorted_header, sort_rows, split_find_tokens
from jmri_core.constants.cli import SORT_INDICATOR, TURNOUT_STATE_NAMES
from jmri_core.jmri_client import JmriError, get_turnouts, resolve_turnout
from jmri_core.jmri_client import set_turnout as _set_turnout
from jmri_core.jmri_client.turnout import TURNOUT_CLOSED, TURNOUT_THROWN
from jmri_cli._dcc_system import dcc_system_display, system_names_by_prefix


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [
        i18n.t("headers.system_id"),
        i18n.t("headers.turnout"),
        i18n.t("headers.state"),
        i18n.t("headers.feedback"),
        i18n.t("headers.comment"),
        i18n.t("headers.dcc_system"),
    ]


# `turnout by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byid": (0, True),
    "byname": (1, True),
    "bystate": (2, True),
    "byfeedback": (3, True),
    "bycomment": (4, True),
    "bydccsystem": (5, True),
}


def _row(turnout: dict, names_by_prefix: dict[str, str]) -> list:
    """Flatten one JMRI turnout object into a `[system_id, label, state, feedback, comment, dcc_system]` table row."""
    state = TURNOUT_STATE_NAMES.get(turnout.get("state"), "UNKNOWN")
    label = turnout.get("userName") or turnout.get("name", "?")
    system_id = turnout.get("name", "?")
    sensors = turnout.get("sensor") or []
    feedback = "yes" if any(s is not None for s in sensors) else "no"
    comment = turnout.get("comment") or ""
    dcc_system = dcc_system_display(system_id, names_by_prefix)
    return [system_id, label, state, feedback, comment, dcc_system]


def _label(turnout: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(turnout.get("userName") or turnout.get("name", ""))


async def turnout_find(args: argparse.Namespace) -> int:
    """Resolve a turnout name/fragment/system ID to its full state, roster-`find`-style.

    Args:
        args: Parsed CLI arguments; uses `args.name` (userName, a fragment
            of it, or JMRI's own system ID like "IT100").

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` is ambiguous
        or matches no turnout.
    """
    try:
        turnouts = await get_turnouts()
        turnout = resolve_turnout(args.name, turnouts)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, state, feedback, comment, dcc_system = _row(turnout, names_by_prefix)
    print(
        f"system_id={system_id} name={label} state={state} "
        f"feedback_sensor={feedback} comment={comment or '-'} dcc_system={dcc_system}"
    )
    return 0


async def _turnout_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for turnout_findr/turnout_findg: list every turnout matching a pattern.

    Unlike turnout_find, a pattern can legitimately match zero, one, or many
    turnouts — no ambiguity error, just a filtered `turnout list`-style table
    (or "no turnouts match" if the pattern matches nothing).
    """
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        turnouts = await get_turnouts()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, turnouts, _label)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="turnout", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(t, names_by_prefix) for t in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def turnout_findr(args: argparse.Namespace) -> int:
    """List every turnout whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each turnout's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _turnout_find_pattern(args, regex=True)


async def turnout_findg(args: argparse.Namespace) -> int:
    """List every turnout whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each turnout's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _turnout_find_pattern(args, regex=False)


async def turnout_list(args: argparse.Namespace) -> int:
    """Print the state of every turnout.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS, e.g.
            "byid"/"bystate") picks the sort order - set by parser.py to a
            fixed value per `by*` sibling leaf (defaults to "byname" for
            bare `turnout`/`turnout list`).

    Returns:
        0 on success (including no turnouts), 1 if JMRI is unreachable.
    """
    try:
        turnouts = await get_turnouts()
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not turnouts:
        print(i18n.t("cli.no_entities_found", kind="turnout"))
        return 0
    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows([_row(t, names_by_prefix) for t in turnouts], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def _turnout_set(args: argparse.Namespace, *, thrown: bool) -> int:
    """Shared body for turnout_closed/turnout_thrown.

    No `args.name` means every turnout; a fuzzy `args.name` means just
    that one, matching power/light's "verb + optional target, default =
    all". `args.name` accepts either the user-friendly userName ("Layout
    Turnout A"), an unambiguous fragment of it, or JMRI's own system ID
    ("IT100", shown in `turnout list`'s "System ID" column) — useful for
    turnouts that were never given a friendly userName in JMRI.
    """
    state_name = TURNOUT_STATE_NAMES[TURNOUT_THROWN if thrown else TURNOUT_CLOSED]
    try:
        turnouts = await get_turnouts()
        targets = [resolve_turnout(args.name, turnouts)] if args.name else turnouts
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    all_confirmed = True
    unconfirmed_sensorless = False
    rows = []
    try:
        for target in targets:
            result = await _set_turnout(target["name"], thrown)
            rows.append(_row(result, names_by_prefix))
            if not result["confirmed"]:
                all_confirmed = False
                sensors = result.get("sensor") or []
                if not any(s is not None for s in sensors):
                    unconfirmed_sensorless = True
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    print(tabulate(rows, headers=_headers()))
    if not all_confirmed:
        if unconfirmed_sensorless:
            print(i18n.t("cli.turnout_no_feedback_note"), file=sys.stderr)
        print(i18n.t("cli.not_every_entity_confirmed", kind="turnout", state=state_name), file=sys.stderr)
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
