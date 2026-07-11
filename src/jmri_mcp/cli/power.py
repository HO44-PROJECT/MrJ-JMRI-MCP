"""Power-system commands: `jmri-cli power [status|on|off|get|default]`, `status`.

Talks to jmri_client.py directly (one-shot HTTP, no MCP/JSON-RPC involved).
Bare `jmri-cli power` behaves exactly like `jmri-cli power status` — a
group with an obvious "just show me the state" default shouldn't force
typing the leaf name too.
"""

import argparse
import sys

from tabulate import tabulate

from jmri_mcp import i18n
from jmri_mcp.cli._match import find_glob, find_regex
from jmri_mcp.constants.cli import POWER_STATE_NAMES
from jmri_mcp.jmri_client import (
    JmriError,
    get_systems,
    get_version,
    resolve_system,
    set_power,
)
from jmri_mcp.jmri_client.power import POWER_ON, POWER_OFF


def _state_name(system: dict) -> str:
    return POWER_STATE_NAMES.get(system.get("state"), "UNKNOWN")


def _print_systems_table(systems: list[dict]) -> None:
    rows = [
        [s.get("name", "?"), _state_name(s), "yes" if s.get("default") else ""]
        for s in sorted(systems, key=lambda s: str(s.get("name", "")).casefold())
    ]
    print(tabulate(rows, headers=["System", "State", "Default"]))


async def power_status(args: argparse.Namespace) -> int:
    """Print the power state of every system, sorted alphabetically.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success, 1 if JMRI is unreachable.
    """
    try:
        systems = await get_systems()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    _print_systems_table(systems)
    return 0


async def power_get(args: argparse.Namespace) -> int:
    """Print a single system's power state as a bare ON/OFF/UNKNOWN/IDLE.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name/prefix/fragment,
            or None for the default system).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.system` doesn't
        resolve to exactly one system.
    """
    try:
        systems = await get_systems()
        match = resolve_system(args.system, systems)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    print(_state_name(match))
    return 0


async def power_find(args: argparse.Namespace) -> int:
    """Resolve a power system name/prefix/fragment to its full state, roster-`find`-style.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name, prefix, or an
            unambiguous fragment of the name).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.system` is
        ambiguous or matches no system.
    """
    try:
        systems = await get_systems()
        match = resolve_system(args.system, systems)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    print(
        f"name={match.get('name', '?')} prefix={match.get('prefix', '?')} "
        f"state={_state_name(match)} default={'yes' if match.get('default') else 'no'}"
    )
    return 0


def _system_label(system: dict) -> str:
    return str(system.get("name", ""))


async def _power_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for power_findr/power_findg: list every power system matching a pattern.

    Unlike power_find, a pattern can legitimately match zero, one, or many
    systems — no ambiguity error, just a filtered `power status`-style
    table (or "no power systems match" if the pattern matches nothing).
    """
    try:
        systems = await get_systems()
        matcher = find_regex if regex else find_glob
        matches = matcher(args.pattern, systems, _system_label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(f"No power systems match {args.pattern!r}")
        return 0
    _print_systems_table(matches)
    return 0


async def power_findr(args: argparse.Namespace) -> int:
    """List every power system whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each system's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _power_find_pattern(args, regex=True)


async def power_findg(args: argparse.Namespace) -> int:
    """List every power system whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each system's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _power_find_pattern(args, regex=False)


async def power_default(args: argparse.Namespace) -> int:
    """Print which power system JMRI treats as the default.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 on success, 1 if JMRI is unreachable.
    """
    try:
        systems = await get_systems()
        match = resolve_system(None, systems)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    print(match.get("name", "?"))
    return 0


async def _power_set(args: argparse.Namespace, turn_on: bool) -> int:
    """Shared body for power_on/power_off.

    No `args.system` means every system; a fuzzy `args.system` means just
    that one. Sequential like _set_power_all, so results print in a stable
    order and JMRI/DCC++ isn't hit with simultaneous POSTs.
    """
    state_name = POWER_STATE_NAMES[POWER_ON if turn_on else POWER_OFF]
    try:
        systems = await get_systems()
        if args.system:
            targets = [resolve_system(args.system, systems)]
        else:
            targets = systems
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    results = []
    all_confirmed = True
    try:
        for target in targets:
            result = await set_power(target["prefix"], turn_on)
            results.append(result)
            if not result["confirmed"]:
                all_confirmed = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    _print_systems_table(results)
    if not all_confirmed:
        print(f"WARNING: not every system confirmed {state_name} after re-read", file=sys.stderr)
        return 1
    return 0


async def power_on(args: argparse.Namespace) -> int:
    """Turn a system on, or every system if none is given, confirming by re-read.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name/prefix/fragment,
            or None for every system).

    Returns:
        0 on success with every targeted system confirmed ON, 1 if JMRI is
        unreachable, `args.system` is ambiguous/unknown, or any re-read
        didn't confirm ON.
    """
    return await _power_set(args, turn_on=True)


async def power_off(args: argparse.Namespace) -> int:
    """Turn a system off, or every system if none is given, confirming by re-read.

    With no target this is the layout-wide emergency stop: cutting power
    stops every locomotive regardless of who's driving it (a JMRI panel,
    another MCP session), unlike a throttle e-stop which only reaches
    locomotives this session has acquired.

    Args:
        args: Parsed CLI arguments; uses `args.system` (name/prefix/fragment,
            or None for every system).

    Returns:
        0 on success with every targeted system confirmed OFF, 1 if JMRI is
        unreachable, `args.system` is ambiguous/unknown, or any re-read
        didn't confirm OFF.
    """
    return await _power_set(args, turn_on=False)


async def system_status(args: argparse.Namespace) -> int:
    """Run a one-call diagnostic: JMRI reachability, version, power systems.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 if JMRI is reachable (regardless of individual power states),
        1 if JMRI is unreachable or power systems can't be listed.
    """
    try:
        version = await get_version()
    except JmriError as exc:
        print(i18n.t("cli.jmri_unreachable", message=str(exc)), file=sys.stderr)
        return 1

    print(f"JMRI reachable, version {version}")
    try:
        systems = await get_systems()
    except JmriError as exc:
        print(i18n.t("cli.power_systems_unavailable", message=str(exc)), file=sys.stderr)
        return 1
    _print_systems_table(systems)
    return 0
