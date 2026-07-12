"""Signal mast commands: `jmri-cli signal [list|find|findr|findg|status|set]`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Covers signalMast only, not signalHead — see
jmri_mcp.jmri_client.signal's module docstring for why.
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.constants.cli import SORT_INDICATOR
from jmri_mcp.jmri_client import JmriError, get_signals, resolve_signal
from jmri_mcp.jmri_client import set_signal as _set_signal


def _headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG. Signal listings are always sorted by name, so the sort indicator is unconditional."""
    return [i18n.t("headers.signal") + SORT_INDICATOR, i18n.t("headers.system_id"), i18n.t("headers.aspect")]


def _row(signal: dict) -> list:
    """Flatten one JMRI signal mast object into a `[label, system_id, aspect]` table row."""
    aspect = signal.get("aspect") or "UNKNOWN"
    label = signal.get("userName") or signal.get("name", "?")
    system_id = signal.get("name", "?")
    return [label, system_id, aspect]


def _label(signal: dict) -> str:
    """The name find_regex/find_glob match against: userName if set, else system name."""
    return str(signal.get("userName") or signal.get("name", ""))


async def signal_list(args: argparse.Namespace) -> int:
    """Print the state of every signal mast, sorted alphabetically.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success (including no signal masts), 1 if JMRI is unreachable.
    """
    try:
        signals = await get_signals()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not signals:
        print("No signal masts found")
        return 0
    rows = [_row(s) for s in sorted(signals, key=lambda s: _row(s)[0].casefold())]
    print(tabulate(rows, headers=_headers()))
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
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    label, system_id, aspect = _row(match)
    print(f"name={label} system_id={system_id} aspect={aspect}")
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
    try:
        signals = await get_signals()
        matcher = find_regex if regex else find_glob
        matches = matcher(args.pattern, signals, _label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(f"No signal masts match {args.pattern!r}")
        return 0
    rows = [_row(s) for s in sorted(matches, key=lambda s: _row(s)[0].casefold())]
    print(tabulate(rows, headers=_headers()))
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
            docstring for why).

    Returns:
        0 on success with the requested aspect confirmed, 1 if JMRI is
        unreachable, `args.name` is ambiguous/unknown, or the re-read
        aspect doesn't confirm the request.
    """
    try:
        signals = await get_signals()
        match = resolve_signal(args.name, signals)
        result = await _set_signal(match["name"], args.aspect)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    label, system_id, aspect = _row(result)
    print(f"name={label} system_id={system_id} aspect={aspect}")
    if not result["confirmed"]:
        print(f"WARNING: requested aspect {args.aspect!r} but observed aspect "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0
