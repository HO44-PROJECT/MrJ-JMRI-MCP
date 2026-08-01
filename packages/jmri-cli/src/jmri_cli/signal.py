"""Signal mast commands: `jmri-cli signal [list|find|findr|findg|status|set]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Covers signalMast only, not signalHead — see
jmri_core.jmri_client.signal's module docstring for why.
"""

import argparse
import asyncio
import sys

from jmri_core import i18n
from jmri_core.constants.cli import SORT_INDICATOR
from jmri_core.jmri_client import (
    JmriError,
    get_signal_aspects,
    get_signals,
    parse_signal_dcc_address,
    resolve_signal,
)
from jmri_core.jmri_client import set_signal as _set_signal
from tabulate import tabulate

from jmri_cli._dcc_system import dcc_system_display, system_names_by_prefix
from jmri_cli._match import find_glob, find_regex
from jmri_cli._sort import mark_sorted_header, sort_rows, split_find_tokens


def _headers(*, with_aspects: bool = False) -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    headers = [
        i18n.t("headers.system_id"),
        i18n.t("headers.signal"),
        i18n.t("headers.aspect"),
        i18n.t("headers.comment"),
        i18n.t("headers.dcc_system"),
        i18n.t("headers.address"),
    ]
    if with_aspects:
        headers.append(i18n.t("headers.valid_aspects"))
    return headers


# `signal by*` subcommand name -> (index into _row()'s tuple, casefold?).
# Shared with parser.py so every `by*` sibling leaf it builds is guaranteed
# to match a key this module actually knows how to sort on.
SORT_FIELDS: dict[str, tuple[int, bool]] = {
    "byid": (0, True),
    "byname": (1, True),
    "byaspect": (2, True),
    "bycomment": (3, True),
    "bydccsystem": (4, True),
    "byaddress": (5, True),
}


def _row(
    signal: dict, names_by_prefix: dict[str, str], *, valid_aspects: list[str] | None = None
) -> list:
    """Flatten one JMRI signal mast object into a `[system_id, label, aspect, comment, dcc_system, address]` table row.

    aspect is "OFF" when the mast is unlit (dark), regardless of what
    aspect JMRI still has recorded internally — matches set_signal's
    aspect="off"/"unlit" special case, so what's displayed here is always
    exactly what you'd pass back into `signal set`.

    valid_aspects: If given (signal list --with-aspects), appended as one
        extra comma-joined column - the same list get_signal_aspects()
        returns (does NOT include "unlit"/"off" - see that function's
        docstring for why).
    """
    aspect = "OFF" if not signal.get("lit", True) else (signal.get("aspect") or "UNKNOWN")
    label = signal.get("userName") or signal.get("name", "?")
    system_id = signal.get("name", "?")
    comment = signal.get("comment") or ""
    dcc_system = dcc_system_display(system_id, names_by_prefix)
    address = parse_signal_dcc_address(system_id)
    address_display = address if address is not None else ""
    row = [system_id, label, aspect, comment, dcc_system, address_display]
    if valid_aspects is not None:
        row.append(", ".join(valid_aspects))
    return row


def _label(signal: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(signal.get("userName") or signal.get("name", ""))


async def _valid_aspects_or_placeholder(system_id: str) -> list[str]:
    """get_signal_aspects(), but never raises - used for `signal list --with-aspects`,
    where one mast with a non-standard name (see get_signal_aspects's
    JmriError("aspects_not_derivable")) shouldn't blank out the whole table.
    """
    try:
        return await get_signal_aspects(system_id)
    except JmriError:
        return ["?"]


async def signal_list(args: argparse.Namespace) -> int:
    """Print the state of every signal mast.

    Args:
        args: Parsed CLI arguments; `args.sort_by` (one of SORT_FIELDS, e.g.
            "byid"/"byaspect") picks the sort order - set by parser.py to a
            fixed value per `by*` sibling leaf (defaults to "byname" for
            bare `signal`/`signal list`). `args.with_aspects` (bool, default
            False) adds a column with each mast's valid aspects - one extra
            live request per mast (concurrent, via get_signal_aspects), so
            slower than the default; a mast whose aspects can't be derived
            shows "?" in that column rather than failing the whole command.

    Returns:
        0 on success (including no signal masts), 1 if JMRI is unreachable.
    """
    try:
        signals = await get_signals()
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not signals:
        print(i18n.t("cli.no_entities_found", kind="signal mast"))
        return 0

    with_aspects = getattr(args, "with_aspects", False)
    if with_aspects:
        aspects_by_signal = await asyncio.gather(
            *(_valid_aspects_or_placeholder(s.get("name", "")) for s in signals)
        )
        rows = [
            _row(s, names_by_prefix, valid_aspects=aspects)
            for s, aspects in zip(signals, aspects_by_signal, strict=True)
        ]
    else:
        rows = [_row(s, names_by_prefix) for s in signals]

    sort_by = getattr(args, "sort_by", None) or "byname"
    rows = sort_rows(rows, SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(with_aspects=with_aspects), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def signal_status(args: argparse.Namespace) -> int:
    """Print the state of one signal mast.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one signal mast.
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, aspect, comment, dcc_system, address = _row(match, names_by_prefix)
    print(
        f"name={label} system_id={system_id} aspect={aspect} "
        f"comment={comment or '-'} dcc_system={dcc_system} "
        f"address={address if address != '' else '-'}"
    )
    return 0


async def signal_find(args: argparse.Namespace) -> int:
    """Resolve a signal mast name/fragment/system ID to its full state.

    Identical body to `signal_status` — `find` is the naming this project
    uses consistently for "resolve one, no side effects" across every
    domain (roster/turnout/light/power/throttle/sensor); `status` is kept as
    an alias since it predates that convention and existing scripts may use it.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.name` doesn't
        resolve to exactly one signal mast.
    """
    return await signal_status(args)


async def _signal_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for signal_findr/signal_findg: list every signal mast matching a pattern.

    Unlike signal_find, a pattern can legitimately match zero, one, or many
    masts — no ambiguity error, just a filtered `signal list`-style table
    (or "no signal masts match" if the pattern matches nothing).
    """
    sort_by, pattern = split_find_tokens(args.pattern_tokens, SORT_FIELDS)
    try:
        signals = await get_signals()
        matcher = find_regex if regex else find_glob
        matches = matcher(pattern, signals, _label)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_entities_match", kind="signal mast", pattern=pattern))
        return 0
    sort_by = sort_by or "byname"
    rows = sort_rows([_row(s, names_by_prefix) for s in matches], SORT_FIELDS, sort_by)
    headers = mark_sorted_header(_headers(), SORT_FIELDS, sort_by, SORT_INDICATOR)
    print(tabulate(rows, headers=headers))
    return 0


async def signal_findr(args: argparse.Namespace) -> int:
    """List every signal mast whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each mast's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _signal_find_pattern(args, regex=True)


async def signal_findg(args: argparse.Namespace) -> int:
    """List every signal mast whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each mast's userName/name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _signal_find_pattern(args, regex=False)


async def signal_set(args: argparse.Namespace) -> int:
    """Set a signal mast's aspect, and confirm by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment) and `args.aspect` (e.g. "Hp0",
            "Hp1" — not validated locally, see jmri_client.signal's module
            docstring for why. "unlit"/"off", case-insensitive, make the
            mast dark instead of requesting a real aspect).

    Returns:
        0 on success with the requested aspect confirmed, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        aspect doesn't confirm the request.
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
        result = await _set_signal(match["name"], args.aspect)
        names_by_prefix = await system_names_by_prefix()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    system_id, label, aspect, comment, dcc_system, address = _row(result, names_by_prefix)
    print(
        f"name={label} system_id={system_id} aspect={aspect} "
        f"comment={comment or '-'} dcc_system={dcc_system} "
        f"address={address if address != '' else '-'}"
    )
    if not result["confirmed"]:
        print(i18n.t("cli.signal_aspect_not_confirmed", aspect=args.aspect), file=sys.stderr)
        return 1
    return 0


async def signal_off(args: argparse.Namespace) -> int:
    """Darken a signal mast (JMRI's "lit" flag), confirming by re-reading its state.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Shortcut for `signal set <name> off` - same underlying set_signal()
    call, just without needing to type/remember the "off"/"unlit" aspect
    special case. Whether this actually does anything meaningful depends
    on that specific mast's own "This Mast can be unlit" checkbox in
    PanelPro - JMRI accepts the "lit" flag on any mast regardless, so a
    successful "confirmed: true" here does not by itself mean the mast
    was configured to be unlit-capable (see jmri_client.signal's
    get_signal_aspects docstring for why that can't be checked from here).

    Returns:
        0 on success with the mast confirmed unlit, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        state doesn't confirm unlit.
    """
    args.aspect = "off"
    return await signal_set(args)


async def signal_aspects(args: argparse.Namespace) -> int:
    """Print the valid aspect names for one signal mast, one per line.

    Args:
        args: Parsed CLI arguments; uses `args.name` (system name, userName,
            or an unambiguous fragment).

    Aspects are case-sensitive and not otherwise discoverable from JMRI
    (see jmri_client.signal's module docstring) - this is what feeds
    `signal set`'s own aspect Tab-completion in the interactive shell, and
    is also the plain way to check exact spelling from a one-shot command.

    Returns:
        0 on success, 1 if JMRI is unreachable, `args.name` is
        ambiguous/unknown, or this mast's aspects can't be derived (see
        get_signal_aspects).
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
        aspects = await get_signal_aspects(match["name"])
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    for aspect in aspects:
        print(aspect)
    return 0
