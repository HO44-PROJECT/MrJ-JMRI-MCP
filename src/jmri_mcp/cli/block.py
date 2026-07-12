"""Block commands: `jmri-cli block [list|find|findr|findg|status]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Blocks are read-only — they report real-world occupancy JMRI detects via a
linked sensor (and optionally a reporter/value for RFID-style detection),
so there is no `block set` subcommand.
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.cli._sort import mark_sorted_header, sort_rows, split_find_tokens
from jmri_mcp.constants.cli import BLOCK_STATE_NAMES, SORT_INDICATOR
from jmri_mcp.jmri_client import JmriError, get_blocks, resolve_block


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [
        i18n.t("headers.system_id"),
        i18n.t("headers.block"),
        i18n.t("headers.state"),
        i18n.t("headers.sensor"),
        i18n.t("headers.length"),
        i18n.t("headers.curvature"),
        i18n.t("headers.speed"),
        i18n.t("headers.comment"),
    ]


# `block by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byid": (0, True),
    "byname": (1, True),
    "bystate": (2, True),
    "bysensor": (3, True),
    "bylength": (4, False),
    "bycurvature": (5, False),
    "byspeed": (6, True),
    "bycomment": (7, True),
}


def _row(block: dict) -> list:
    """Flatten one JMRI block object into a `[system_id, label, state, sensor, length, curvature, speed, comment]` table row."""
    state = BLOCK_STATE_NAMES.get(block.get("state"), "UNKNOWN")
    label = block.get("userName") or block.get("name", "?")
    system_id = block.get("name", "?")
    sensor = block.get("sensor") or "?"
    length = block.get("length")
    curvature = block.get("curvature")
    speed = block.get("speed") or ""
    comment = block.get("comment") or ""
    return [system_id, label, state, sensor, length, curvature, speed, comment]


def _label(block: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(block.get("userName") or block.get("name", ""))


async def block_list(args: argparse.Namespace) -> int:
    """Print the state of every block.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS, e.g.
            "byid"/"bystate") picks the sort order - set by parser.py to a
            fixed value per `by*` sibling leaf (defaults to "byname" for
            bare `block`/`block list`).

    Returns:
        0 on success (including no blocks), 1 if JMRI is unreachable.
    """
    try:
        blocks = await get_blocks()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not blocks:
        print(i18n.t("cli.no_entities_found", kind="block"))
        return 0
    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows([_row(b) for b in blocks], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def block_status(args: argparse.Namespace) -> int:
    """Print the state of one block.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one block.
    """
    try:
        blocks = await get_blocks()
        match = resolve_block(args.name, blocks)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, state, sensor, length, curvature, speed, comment = _row(match)
    value = match.get("value")
    print(
        f"name={label} system_id={system_id} state={state} sensor={sensor} value={value} "
        f"length={length} curvature={curvature} speed={speed or '-'} comment={comment or '-'}"
    )
    return 0


async def block_find(args: argparse.Namespace) -> int:
    """Resolve a block name/fragment/system ID to its full state.

    Identical body to `block_status` — `find` is the naming this project
    uses consistently for "resolve one, no side effects" across every
    domain (roster/turnout/light/power/throttle/signal/sensor); `status` is
    kept as an alias for consistency with sensor's own list/find/status set.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one block.
    """
    return await block_status(args)


async def _block_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for block_findr/block_findg: list every block matching a pattern.

    Unlike block_find, a pattern can legitimately match zero, one, or many
    blocks — no ambiguity error, just a filtered `block list`-style table
    (or "no blocks match" if the pattern matches nothing).
    """
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        blocks = await get_blocks()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, blocks, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="block", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(b) for b in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def block_findr(args: argparse.Namespace) -> int:
    """List every block whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each block's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _block_find_pattern(args, regex=True)


async def block_findg(args: argparse.Namespace) -> int:
    """List every block whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each block's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _block_find_pattern(args, regex=False)
