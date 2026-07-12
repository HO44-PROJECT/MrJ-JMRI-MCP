"""Roster commands: `jmri-cli roster [list|find|findr|findg|functions]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.cli._sort import mark_sorted_header, sort_rows, split_find_tokens
from jmri_mcp.constants.cli import SORT_INDICATOR
from jmri_mcp.jmri_client import (
    JmriError,
    get_roster,
    get_roster_function_labels,
    resolve_roster_entry,
)


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [
        i18n.t("headers.address"),
        i18n.t("headers.name"),
        i18n.t("headers.road"),
        i18n.t("headers.road_number"),
        i18n.t("headers.manufacturer"),
        i18n.t("headers.model"),
        i18n.t("headers.owner"),
        i18n.t("headers.modified"),
        i18n.t("headers.groups"),
    ]


# `roster by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byname": (1, True),
    "bydcc": (0, False),
    "byroad": (2, True),
    "byroadnumber": (3, True),
    "bymanufacturer": (4, True),
    "bymodel": (5, True),
    "byowner": (6, True),
    "bydate": (7, True),
    "bygroup": (8, True),
}


def _row(e: dict) -> list:
    """Flatten one roster entry (get_roster()'s compact shape) into a table row matching _headers()'s column order."""
    return [
        e["address"],
        e["name"],
        e["road"] or "-",
        e["road_number"] or "-",
        e["manufacturer"] or "-",
        e["model"] or "-",
        e["owner"] or "-",
        e["date_modified"] or "-",
        ", ".join(e["groups"]) or "-",
    ]


def _label(e: dict) -> str:
    """The name find_regex/find_glob match against: the roster entry's name."""
    return str(e.get("name", ""))


async def roster_list(args: argparse.Namespace) -> int:
    """Print every locomotive in JMRI's roster: all known roster fields.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS,
            e.g. "bydcc"/"bygroup") picks the sort order - set by parser.py
            to a fixed value per `by*` sibling leaf (defaults to "byname"
            for bare `roster`/`roster list`, see build_parser()'s
            `_sort_family()` call for this group).

    Returns:
        0 on success (including an empty roster), 1 if JMRI is unreachable.
    """
    try:
        roster = await get_roster()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not roster:
        print(i18n.t("cli.roster_empty"))
        return 0
    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows([_row(e) for e in roster], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def _roster_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for roster_findr/roster_findg: list every roster entry matching a pattern.

    Unlike roster_find, a pattern can legitimately match zero, one, or many
    locomotives — no ambiguity error, just a filtered `roster list`-style
    table (or "no roster entries match" if the pattern matches nothing).
    """
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        roster = await get_roster()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, roster, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_roster_entries_match", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(e) for e in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def roster_findr(args: argparse.Namespace) -> int:
    """List every roster entry whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each entry's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _roster_find_pattern(args, regex=True)


async def roster_findg(args: argparse.Namespace) -> int:
    """List every roster entry whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each entry's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _roster_find_pattern(args, regex=False)


async def roster_find(args: argparse.Namespace) -> int:
    """Resolve a locomotive name or DCC address to its roster entry.

    Args:
        args: Parsed CLI arguments; uses `args.name` (a full name, a
            fragment of one, or a numeric DCC address as a string).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` is ambiguous
        or matches no roster entry.
    """
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.name, roster)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    road = entry["road"] or "-"
    road_number = entry["road_number"] or "-"
    manufacturer = entry["manufacturer"] or "-"
    model = entry["model"] or "-"
    owner = entry["owner"] or "-"
    modified = entry["date_modified"] or "-"
    groups = ", ".join(entry["groups"]) or "-"
    print(
        f"address={entry['address']} name={entry['name']} road={road} "
        f"road_number={road_number} manufacturer={manufacturer} model={model} "
        f"owner={owner} modified={modified} groups={groups}"
    )
    return 0


async def roster_functions(args: argparse.Namespace) -> int:
    """Print a locomotive's user-labeled decoder functions (F0-F28).

    Resolves `args.name` the same way as `roster_find` (name, fragment, or
    DCC address), then looks up the function labels the user set in JMRI's
    own roster editor. Most locos have none set at all — that's reported
    plainly, not as an error.

    Args:
        args: Parsed CLI arguments; uses `args.name` (a full name, a
            fragment of one, or a numeric DCC address as a string).

    Returns:
        0 on success (including no labeled functions), 1 if JMRI is
        unreachable or `args.name` is ambiguous or matches no roster entry.
    """
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.name, roster)
        labels = await get_roster_function_labels(entry["name"])
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    print(f"{entry['name']} (address={entry['address']})")
    if not labels:
        print(i18n.t("cli.no_labeled_functions"))
        return 0
    rows = [[f"F{n}", labels[n]] for n in sorted(labels)]
    print(tabulate(rows, headers=[i18n.t("headers.function"), i18n.t("headers.label")]))
    return 0
