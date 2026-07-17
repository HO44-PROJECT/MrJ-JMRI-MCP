"""Argument parser assembly for jmri-cli.

Wires the command functions from power.py/roster.py/throttle.py into a
single argparse.ArgumentParser, matching jmri-cli's documented command
tree (see the package docstring in jmri_cli/__init__.py). Every
top-level group gets a short, inviting one-liner (see the
`help.group.*` keys in jmri_core/i18n/en.json) instead of a technical
description, and every leaf subcommand (the ones
that actually run against JMRI) gets an `epilog` with a copy-pasteable
example - `jmri-cli <group> <leaf> -h` is meant to be self-sufficient,
no separate "examples" command needed.

Consistency rule applied throughout (per user feedback on the first pass
of this redesign): a group whose members share an obvious "just show me
the state" default doesn't force typing a leaf name for it — bare `power`
behaves like `power status`, bare `roster` like `roster list`, bare
`throttle` like `throttle list`. And where a leaf's own value is really a
verb (on/off, forward/reverse, close/throw), that value is elevated to
be the subcommand name itself instead of a positional choice argument —
`power on`/`power off`, `throttle forward`/`throttle reverse`, `light
on`/`light off`, `turnout close`/`turnout throw`, `throttle on`/`off`.
"""

import argparse
import functools

from jmri_core import i18n
from jmri_cli import block, cache, light, power, roster, sensor, session, signal, throttle, turnout


def _leaf(subparsers, name: str, *, help: str, example: str, func) -> argparse.ArgumentParser:
    """Add a leaf subcommand with a one-line help and a runnable-example epilog.

    Args:
        subparsers: The parent subparsers action (from add_subparsers()).
        name: The subcommand name (e.g. "status", "on").
        help: Short help shown in the parent's command list.
        example: A full `jmri-cli ...` command string shown in `-h`'s epilog.
        func: The async command function to run for this subcommand.

    Returns:
        The new subparser, so callers can add positional/optional arguments.
    """
    sub = subparsers.add_parser(
        name,
        help=help,
        description=help,
        epilog=f"example:\n  {example}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub.set_defaults(func=func)
    return sub


def _shortcut(subparsers, name: str, source: argparse.ArgumentParser, *, example: str) -> None:
    """Register a top-level shortcut that mirrors an existing `throttle <leaf>` parser.

    Copies `source`'s positional/optional arguments (and its `func`
    default, including any functools.partial like forward/reverse's)
    onto a brand-new top-level parser — so `jmri-cli speed 3 40` behaves
    identically to `jmri-cli throttle speed 3 40`, no dispatch logic
    duplicated. Purely additive: `source` itself is untouched, so
    `jmri-cli throttle <leaf>` keeps working exactly as before.

    Only covers the small set of everyday verbs named in issue #45
    (speed/stop/estop/forward/reverse/engine-start/engine-stop) — `on`/
    `off` were deliberately left out of that set, since bare `jmri-cli
    on`/`off` at the top level would read ambiguously against the
    already-existing `power on`/`power off` group.

    Args:
        subparsers: The root parser's subparsers action.
        name: The shortcut's top-level name (matches `source`'s leaf name).
        source: The already-built `throttle <name>` subparser to mirror.
        example: A full `jmri-cli <name> ...` command string for the epilog.
    """
    shortcut = subparsers.add_parser(
        name,
        help=f"{source.description} (shortcut for `throttle {name}`)",
        description=f"{source.description} (shortcut for `throttle {name}`)",
        epilog=f"example:\n  {example}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    for action in source._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        shortcut._add_action(action)
    shortcut.set_defaults(**source._defaults)


def _add_ramp_args(leaf: argparse.ArgumentParser, *, rampup: bool, seconds: bool) -> None:
    """Add --rampup/--rampdown/--hold flags to a throttle leaf subparser.

    Args:
        leaf: The subparser to add flags to (e.g. `speed`, `stop`).
        rampup: Whether to add `--rampup` (stop's target is always 0, so it
            has no use for one).
        seconds: Whether to add `--hold` (stop's target is always 0, so
            "how long to hold a nonzero speed" doesn't apply to it either).
    """
    if rampup:
        leaf.add_argument(
            "--rampup", type=float, default=None, metavar="SECONDS",
            help=i18n.t("help.arg.ramp_up"),
        )
    leaf.add_argument(
        "--rampdown", type=float, default=None, metavar="SECONDS",
        help=i18n.t("help.arg.ramp_down"),
    )
    if seconds:
        leaf.add_argument(
            "--hold", type=float, default=None, metavar="SECONDS", dest="seconds",
            help=i18n.t("help.arg.hold_seconds"),
        )


def _group(subparsers, name: str, *, default_func=None):
    """Add a top-level command group, optionally with a "bare invocation" default.

    Args:
        subparsers: The root parser's subparsers action.
        name: The group name (e.g. "power", "throttle").
        default_func: If set, running `jmri-cli <name>` with no leaf
            subcommand runs this instead of argparse erroring out.

    Returns:
        (group_parser, its own subparsers action).
    """
    group_cmd = subparsers.add_parser(name, help=i18n.t(f"help.group.{name}"))
    if default_func is not None:
        group_cmd.set_defaults(func=default_func)
    group_sub = group_cmd.add_subparsers(dest=f"{name}_command", required=default_func is None)
    return group_cmd, group_sub


def _sort_siblings(subparsers, sort_fields, *, func, example_prefix: str, pattern_help: str | None = None) -> None:
    """Add one `by*` sibling leaf per key in a domain module's `SORT_FIELDS`.

    `jmri-cli <group> by<column>` runs the exact same command function as
    the group's `list` leaf, just with `sort_by` pre-bound to that column
    instead of defaulting to "byname". This is what lets a user type
    `jmri-cli block bystate` directly, matching the existing pattern for
    verb-shaped leaves elsewhere (`turnout close`/`throw`, `light on`/`off`)
    instead of a `--sort`-style option.

    Also used one level down, under `findr`/`findg`, to sort filtered
    results the same way - pass `pattern_help` in that case so each `by*`
    leaf also gets the `pattern` positional `findr`/`findg` need
    (`jmri-cli block findr byid '^B_1'`); omit it for the top-level
    `list`/bare-group case, which takes no positional at all.

    Args:
        subparsers: The parent subparsers action (e.g. block_sub, or
            block_findr_cmd's own add_subparsers() for the nested case).
        sort_fields: The domain module's `SORT_FIELDS` dict (e.g. block.SORT_FIELDS).
        func: The command function to reuse (e.g. block.block_list).
        example_prefix: What precedes the `by*` word in the epilog example
            (e.g. "jmri-cli block" or "jmri-cli block findr").
        pattern_help: If set, each `by*` leaf also gets a `pattern`
            positional with this help text (the findr/findg case).
    """
    for sort_by in sort_fields:
        leaf = subparsers.add_parser(
            sort_by,
            help=i18n.t(f"help.sort.{sort_by}"),
            description=i18n.t(f"help.sort.{sort_by}"),
            epilog=f"example:\n  {example_prefix} {sort_by}" + (" '^B_1'" if pattern_help else ""),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        leaf.set_defaults(func=func, sort_by=sort_by)
        if pattern_help is not None:
            leaf.add_argument("pattern", help=pattern_help)


def _find_pattern_leaf(subparsers, name: str, *, help: str, example: str, func, sort_fields) -> None:
    """Add a findr/findg-style leaf that also accepts an optional `by*` sort word.

    `jmri-cli <group> findr '^B_1'` still works with no sort word (defaults
    to name order, same as bare `list`). `jmri-cli <group> findr byid
    '^B_1'` additionally sorts the filtered results by a specific column -
    the `by*` word comes right after `findr`/`findg` and before the
    pattern, mirroring how `by*` sits right after the group name for `list`.

    Implemented as a single positional `nargs="+"` (1 or 2 tokens) rather
    than nested subparsers: argparse can't cleanly make an optional
    positional and an optional subparser coexist in the same parser (the
    first free token gets tried against the subparser's `choices` first,
    so a pattern like `^B_1` that isn't a `by*` word hard-errors instead of
    falling through). `args.pattern_tokens` is split back into
    `(sort_by, pattern)` by the command function itself at call time - see
    each domain's `_split_find_tokens()`-style handling in `_find_pattern`.

    Args:
        subparsers: The parent group's subparsers action (e.g. block_sub).
        name: "findr" or "findg".
        help: Short help shown in the parent's command list.
        example: A full `jmri-cli ...` command string shown in `-h`'s epilog.
        func: The command function (e.g. block.block_findr).
        sort_fields: The domain module's `SORT_FIELDS` dict, used only to
            list valid `by*` words in the help text.
    """
    find_cmd = subparsers.add_parser(
        name, help=help, description=help,
        epilog=f"example:\n  {example}\n  {example.rsplit(' ', 1)[0]} byid {example.rsplit(' ', 1)[1]}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    find_cmd.set_defaults(func=func)
    pattern_help = i18n.t("help.arg.regex_pattern" if name == "findr" else "help.arg.glob_pattern")
    sort_words = "/".join(sort_fields)
    find_cmd.add_argument(
        "pattern_tokens", nargs="+", metavar="[SORT] PATTERN",
        help=f"{pattern_help}; optionally preceded by a sort word ({sort_words})",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build jmri-cli's full argument parser.

    Returns:
        An argparse.ArgumentParser with all subcommands registered, each
        with its `func` default set to the command function that handles it.
    """
    parser = argparse.ArgumentParser(prog="jmri-cli", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- power: bare = status; on/off take an optional fuzzy target ------
    power_cmd, power_sub = _group(subparsers, "power", default_func=power.power_status)
    power_cmd.epilog = "example:\n  jmri-cli power"
    power_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        power_sub, "status", help=i18n.t("help.power.status"),
        example="jmri-cli power status", func=power.power_status,
    )
    _sort_siblings(
        power_sub, power.SORT_FIELDS, func=power.power_status,
        example_prefix="jmri-cli power",
    )

    on_ = _leaf(
        power_sub, "on", help=i18n.t("help.power.on"),
        example="jmri-cli power on ohara", func=power.power_on,
    )
    on_.add_argument("system", nargs="?", default=None,
                      help=i18n.t("help.arg.system_ref_or_every"))

    off_ = _leaf(
        power_sub, "off",
        help=i18n.t("help.power.off"),
        example="jmri-cli power off", func=power.power_off,
    )
    off_.add_argument("system", nargs="?", default=None,
                       help=i18n.t("help.arg.system_ref_or_every"))

    get_ = _leaf(
        power_sub, "get", help=i18n.t("help.power.get"),
        example="jmri-cli power get ohara", func=power.power_get,
    )
    get_.add_argument("system", nargs="?", default=None,
                       help=i18n.t("help.arg.system_ref_or_default"))

    power_find_cmd = _leaf(
        power_sub, "find", help=i18n.t("help.power.find"),
        example="jmri-cli power find ohara", func=power.power_find,
    )
    power_find_cmd.add_argument("system", nargs="?", default=None,
                                 help=i18n.t("help.arg.system_ref_or_default"))

    power_findr_cmd = _leaf(
        power_sub, "findr", help=i18n.t("help.power.findr"),
        example="jmri-cli power findr '^DCC'", func=power.power_findr,
    )
    power_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    power_findg_cmd = _leaf(
        power_sub, "findg", help=i18n.t("help.power.findg"),
        example="jmri-cli power findg 'DCC*'", func=power.power_findg,
    )
    power_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

    _leaf(
        power_sub, "default", help=i18n.t("help.power.default"),
        example="jmri-cli power default", func=power.power_default,
    )

    status_help = i18n.t("help.group.status")
    status_cmd = subparsers.add_parser(
        "status", help=status_help,
        description=status_help,
        epilog="example:\n  jmri-cli status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_cmd.set_defaults(func=power.system_status)

    # -- session-start / session-end: composite commands (issue #49) -----
    session_start_help = i18n.t("help.group.session-start")
    session_start_cmd = subparsers.add_parser(
        "session-start", help=session_start_help,
        description=session_start_help,
        epilog="example:\n  jmri-cli session-start",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    session_start_cmd.set_defaults(func=session.session_start)

    session_end_help = i18n.t("help.group.session-end")
    session_end_cmd = subparsers.add_parser(
        "session-end", help=session_end_help,
        description=session_end_help,
        epilog="example:\n  jmri-cli session-end",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    session_end_cmd.set_defaults(func=session.session_end)

    # -- cache: local ~/.jmri-cli/ files, no JMRI contact -----------------
    cache_cmd, cache_sub = _group(subparsers, "cache", default_func=cache.cache_info)
    cache_cmd.epilog = "example:\n  jmri-cli cache"
    cache_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        cache_sub, "info", help=i18n.t("help.cache.info"),
        example="jmri-cli cache info", func=cache.cache_info,
    )

    cache_clean_cmd = _leaf(
        cache_sub, "clean", help=i18n.t("help.cache.clean"),
        example="jmri-cli cache clean", func=cache.cache_clean,
    )
    cache_clean_cmd.add_argument(
        "--state", action="store_true",
        help=i18n.t("help.cache.clean_state_only"),
    )
    cache_clean_cmd.add_argument(
        "--history", action="store_true",
        help=i18n.t("help.cache.clean_history_only"),
    )

    # -- roster: bare = list -----------------------------------------
    roster_cmd, roster_sub = _group(subparsers, "roster", default_func=roster.roster_list)
    roster_cmd.epilog = "example:\n  jmri-cli roster"
    roster_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        roster_sub, "list", help=i18n.t("help.roster.list"),
        example="jmri-cli roster list", func=roster.roster_list,
    )
    _sort_siblings(
        roster_sub, roster.SORT_FIELDS, func=roster.roster_list,
        example_prefix="jmri-cli roster",
    )

    roster_find_cmd = _leaf(
        roster_sub, "find", help=i18n.t("help.roster.find"),
        example="jmri-cli roster find autorail", func=roster.roster_find,
    )
    roster_find_cmd.add_argument("name", help=i18n.t("help.arg.loco_ref"))

    _find_pattern_leaf(
        roster_sub, "findr", help=i18n.t("help.roster.findr"),
        example="jmri-cli roster findr '^auto'", func=roster.roster_findr,
        sort_fields=roster.SORT_FIELDS,
    )

    _find_pattern_leaf(
        roster_sub, "findg", help=i18n.t("help.roster.findg"),
        example="jmri-cli roster findg 'boite*'", func=roster.roster_findg,
        sort_fields=roster.SORT_FIELDS,
    )

    roster_functions_cmd = _leaf(
        roster_sub, "functions", help=i18n.t("help.arg.function_labels"),
        example="jmri-cli roster functions autorail", func=roster.roster_functions,
    )
    roster_functions_cmd.add_argument("name", help=i18n.t("help.arg.loco_ref"))

    # -- throttle: bare = list acquired (from local cache) ------------
    throttle_cmd, throttle_sub = _group(subparsers, "throttle", default_func=throttle.throttle_list)
    throttle_cmd.epilog = "example:\n  jmri-cli throttle"
    throttle_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        throttle_sub, "list", help=i18n.t("help.throttle.list"),
        example="jmri-cli throttle list", func=throttle.throttle_list,
    )

    throttle_find_cmd = _leaf(
        throttle_sub, "find", help=i18n.t("help.throttle.find"),
        example="jmri-cli throttle find autorail", func=throttle.throttle_find,
    )
    throttle_find_cmd.add_argument("loco", help=i18n.t("help.arg.loco_ref"))

    throttle_findr_cmd = _leaf(
        throttle_sub, "findr", help=i18n.t("help.throttle.findr"),
        example="jmri-cli throttle findr '^auto'", func=throttle.throttle_findr,
    )
    throttle_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    throttle_findg_cmd = _leaf(
        throttle_sub, "findg", help=i18n.t("help.throttle.findg"),
        example="jmri-cli throttle findg 'Auto*'", func=throttle.throttle_findg,
    )
    throttle_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

    acquire = _leaf(
        throttle_sub, "acquire", help=i18n.t("help.throttle.acquire"),
        example="jmri-cli throttle acquire 3", func=throttle.throttle_acquire,
    )
    acquire.add_argument("loco", nargs="?", default=None,
                          help=i18n.t("help.throttle.acquire_loco"))
    acquire.add_argument("--prefix", default=None,
                          help=i18n.t("help.throttle.acquire_prefix"))

    release = _leaf(
        throttle_sub, "release", help=i18n.t("help.throttle.release"),
        example="jmri-cli throttle release 3", func=throttle.throttle_release,
    )
    release.add_argument("loco", nargs="?", default=None,
                          help=i18n.t("help.throttle.release_loco"))

    speed = _leaf(
        throttle_sub, "speed", help=i18n.t("help.throttle.speed"),
        example="jmri-cli throttle speed 3 40", func=throttle.throttle_speed,
    )
    speed.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    speed.add_argument("speed_percent", type=float, nargs="?", default=None,
                        help=i18n.t("help.throttle.speed_percent"))
    _add_ramp_args(speed, rampup=True, seconds=True)
    speed.epilog = (
        "example:\n"
        "  jmri-cli throttle speed 3 40\n"
        "  jmri-cli throttle speed 3 40 --rampup 5 --hold 30 --rampdown 5"
    )

    stop_cmd = _leaf(
        throttle_sub, "stop",
        help=i18n.t("help.throttle.stop"),
        example="jmri-cli throttle stop", func=throttle.throttle_stop,
    )
    stop_cmd.add_argument("loco", nargs="?", default=None,
                           help=i18n.t("help.throttle.stop_loco"))
    _add_ramp_args(stop_cmd, rampup=False, seconds=False)
    stop_cmd.epilog = (
        "example:\n"
        "  jmri-cli throttle stop\n"
        "  jmri-cli throttle stop 3 --rampdown 5"
    )

    estop = _leaf(
        throttle_sub, "estop", help=i18n.t("help.throttle.estop"),
        example="jmri-cli throttle estop 3", func=throttle.throttle_estop,
    )
    estop.add_argument("loco", nargs="?", default=None,
                        help=i18n.t("help.throttle.estop_loco"))
    estop.epilog = (
        "example:\n"
        "  jmri-cli throttle estop\n"
        "  jmri-cli throttle estop 3"
    )

    forward = _leaf(
        throttle_sub, "forward", help=i18n.t("help.throttle.forward"),
        example="jmri-cli throttle forward 3", func=functools.partial(throttle.throttle_direction, forward=True),
    )
    forward.add_argument("loco", nargs="?", default=None,
                          help=i18n.t("help.throttle.direction_loco"))
    _add_ramp_args(forward, rampup=True, seconds=True)
    forward.epilog = (
        "example:\n"
        "  jmri-cli throttle forward 3\n"
        "  jmri-cli throttle forward\n"
        "  jmri-cli throttle forward 3 --rampdown 3 --rampup 3 --hold 30"
    )

    reverse = _leaf(
        throttle_sub, "reverse", help=i18n.t("help.throttle.reverse"),
        example="jmri-cli throttle reverse 3", func=functools.partial(throttle.throttle_direction, forward=False),
    )
    reverse.add_argument("loco", nargs="?", default=None,
                          help=i18n.t("help.throttle.direction_loco"))
    _add_ramp_args(reverse, rampup=True, seconds=True)
    reverse.epilog = (
        "example:\n"
        "  jmri-cli throttle reverse 3\n"
        "  jmri-cli throttle reverse\n"
        "  jmri-cli throttle reverse 3 --rampdown 3 --rampup 3 --hold 30"
    )

    on_fn = _leaf(
        throttle_sub, "on",
        help=i18n.t("help.throttle.on"),
        example="jmri-cli throttle on 3 1", func=throttle.throttle_on,
    )
    on_fn.add_argument("loco", nargs="?", default=None,
                        help=i18n.t("help.throttle.function_loco"))
    on_fn.add_argument("function", nargs="?", default=None,
                        help=i18n.t("help.arg.function_ref_or_every"))
    on_fn.add_argument("--lights-only", action="store_true",
                        help=i18n.t("help.throttle.lights_only"))
    on_fn.epilog = (
        "example:\n"
        "  jmri-cli throttle on 3 1\n"
        "  jmri-cli throttle on 3\n"
        "  jmri-cli throttle on"
    )

    off_fn = _leaf(
        throttle_sub, "off",
        help=i18n.t("help.throttle.off"),
        example="jmri-cli throttle off 3 1", func=throttle.throttle_off,
    )
    off_fn.add_argument("loco", nargs="?", default=None,
                         help=i18n.t("help.throttle.function_loco"))
    off_fn.add_argument("function", nargs="?", default=None,
                         help=i18n.t("help.arg.function_ref_or_every"))
    off_fn.add_argument("--lights-only", action="store_true",
                         help=i18n.t("help.throttle.lights_only"))
    off_fn.epilog = (
        "example:\n"
        "  jmri-cli throttle off 3 1\n"
        "  jmri-cli throttle off 3\n"
        "  jmri-cli throttle off"
    )

    engine_start_cmd = _leaf(
        throttle_sub, "engine-start", help=i18n.t("help.throttle.engine_start"),
        example="jmri-cli throttle engine-start 3", func=throttle.throttle_engine_start,
    )
    engine_start_cmd.add_argument("loco", nargs="?", default=None,
                                   help=i18n.t("help.throttle.engine_start_loco"))
    engine_start_cmd.add_argument("--prefix", default=None,
                                   help=i18n.t("help.throttle.acquire_prefix"))

    engine_stop_cmd = _leaf(
        throttle_sub, "engine-stop", help=i18n.t("help.throttle.engine_stop"),
        example="jmri-cli throttle engine-stop", func=throttle.throttle_engine_stop,
    )
    engine_stop_cmd.add_argument("loco", nargs="?", default=None,
                                  help=i18n.t("help.throttle.engine_stop_loco"))

    function_cmd = _leaf(
        throttle_sub, "function",
        help=i18n.t("help.throttle.function"),
        example="jmri-cli throttle function 3", func=throttle.throttle_function,
    )
    function_cmd.add_argument("loco", help=i18n.t("help.arg.loco_ref"))

    sniff = _leaf(
        throttle_sub, "sniff", help=i18n.t("help.throttle.sniff"),
        example="jmri-cli throttle sniff -a 3 -a 7", func=throttle.throttle_sniff,
    )
    sniff.add_argument(
        "-a", "--address", type=int, action="append", default=None,
        help=i18n.t("help.throttle.sniff_address"),
    )
    sniff.add_argument(
        "--show-pong", action="store_true",
        help=i18n.t("help.throttle.sniff_show_pong"),
    )

    # -- top-level shortcuts for the everyday throttle verbs (issue #45) --
    # Additive only: each mirrors an already-built `throttle <leaf>` parser
    # above, so `jmri-cli speed 3 40` and `jmri-cli throttle speed 3 40`
    # are the exact same command. on/off deliberately excluded — see
    # _shortcut()'s docstring for why.
    _shortcut(subparsers, "acquire", acquire, example="jmri-cli acquire 3")
    _shortcut(subparsers, "release", release, example="jmri-cli release 3")
    _shortcut(subparsers, "speed", speed, example="jmri-cli speed 3 40")
    _shortcut(subparsers, "stop", stop_cmd, example="jmri-cli stop")
    _shortcut(subparsers, "estop", estop, example="jmri-cli estop 3")
    _shortcut(subparsers, "forward", forward, example="jmri-cli forward 3")
    _shortcut(subparsers, "reverse", reverse, example="jmri-cli reverse 3")
    _shortcut(subparsers, "engine-start", engine_start_cmd, example="jmri-cli engine-start 3")
    _shortcut(subparsers, "engine-stop", engine_stop_cmd, example="jmri-cli engine-stop")

    # -- light: bare = list; on/off take an optional fuzzy target -----
    light_cmd, light_sub = _group(subparsers, "light", default_func=light.light_list)
    light_cmd.epilog = "example:\n  jmri-cli light"
    light_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        light_sub, "list", help=i18n.t("help.light.list"),
        example="jmri-cli light list", func=light.light_list,
    )
    _sort_siblings(
        light_sub, light.SORT_FIELDS, func=light.light_list,
        example_prefix="jmri-cli light",
    )

    light_find_cmd = _leaf(
        light_sub, "find", help=i18n.t("help.light.find"),
        example='jmri-cli light find "Depot Lighting"', func=light.light_find,
    )
    light_find_cmd.add_argument("name", help=i18n.t("help.light.find_name"))

    _find_pattern_leaf(
        light_sub, "findr", help=i18n.t("help.light.findr"),
        example="jmri-cli light findr '^Depot'", func=light.light_findr,
        sort_fields=light.SORT_FIELDS,
    )

    _find_pattern_leaf(
        light_sub, "findg", help=i18n.t("help.light.findg"),
        example="jmri-cli light findg 'Depot*'", func=light.light_findg,
        sort_fields=light.SORT_FIELDS,
    )

    light_on_cmd = _leaf(
        light_sub, "on", help=i18n.t("help.light.on"),
        example='jmri-cli light on "Depot Lighting"', func=light.light_on,
    )
    light_on_cmd.add_argument("name", nargs="?", default=None,
                               help=i18n.t("help.arg.light_ref_or_every"))

    light_off_cmd = _leaf(
        light_sub, "off", help=i18n.t("help.light.off"),
        example='jmri-cli light off "Depot Lighting"', func=light.light_off,
    )
    light_off_cmd.add_argument("name", nargs="?", default=None,
                                help=i18n.t("help.arg.light_ref_or_every"))

    # -- turnout: bare = list; close/throw take an optional fuzzy target
    turnout_cmd, turnout_sub = _group(subparsers, "turnout", default_func=turnout.turnout_list)
    turnout_cmd.epilog = "example:\n  jmri-cli turnout"
    turnout_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        turnout_sub, "list", help=i18n.t("help.turnout.list"),
        example="jmri-cli turnout list", func=turnout.turnout_list,
    )
    _sort_siblings(
        turnout_sub, turnout.SORT_FIELDS, func=turnout.turnout_list,
        example_prefix="jmri-cli turnout",
    )

    turnout_find_cmd = _leaf(
        turnout_sub, "find", help=i18n.t("help.turnout.find"),
        example="jmri-cli turnout find IT100", func=turnout.turnout_find,
    )
    turnout_find_cmd.add_argument("name", help=i18n.t("help.turnout.find_name"))

    _find_pattern_leaf(
        turnout_sub, "findr", help=i18n.t("help.turnout.findr"),
        example="jmri-cli turnout findr '^Mountain'", func=turnout.turnout_findr,
        sort_fields=turnout.SORT_FIELDS,
    )

    _find_pattern_leaf(
        turnout_sub, "findg", help=i18n.t("help.turnout.findg"),
        example="jmri-cli turnout findg 'Layout*'", func=turnout.turnout_findg,
        sort_fields=turnout.SORT_FIELDS,
    )

    turnout_close_cmd = _leaf(
        turnout_sub, "close", help=i18n.t("help.turnout.close"),
        example='jmri-cli turnout close "Layout Turnout A"', func=turnout.turnout_closed,
    )
    turnout_close_cmd.add_argument("name", nargs="?", default=None,
                                    help=i18n.t("help.arg.turnout_ref_or_every"))

    turnout_throw_cmd = _leaf(
        turnout_sub, "throw", help=i18n.t("help.turnout.throw"),
        example='jmri-cli turnout throw "Layout Turnout A"', func=turnout.turnout_thrown,
    )
    turnout_throw_cmd.add_argument("name", nargs="?", default=None,
                                    help=i18n.t("help.arg.turnout_ref_or_every"))

    # -- sensor: bare = list; read-only ---------------------------------
    sensor_cmd, sensor_sub = _group(subparsers, "sensor", default_func=sensor.sensor_list)
    sensor_cmd.epilog = "example:\n  jmri-cli sensor"
    sensor_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        sensor_sub, "list", help=i18n.t("help.sensor.list"),
        example="jmri-cli sensor list", func=sensor.sensor_list,
    )
    _sort_siblings(
        sensor_sub, sensor.SORT_FIELDS, func=sensor.sensor_list,
        example_prefix="jmri-cli sensor",
    )

    sensor_status_cmd = _leaf(
        sensor_sub, "status", help=i18n.t("help.sensor.status"),
        example='jmri-cli sensor status "Montagne B"', func=sensor.sensor_status,
    )
    sensor_status_cmd.add_argument("name", help=i18n.t("help.arg.sensor_ref"))

    sensor_find_cmd = _leaf(
        sensor_sub, "find", help=i18n.t("help.sensor.find"),
        example='jmri-cli sensor find "Montagne B"', func=sensor.sensor_find,
    )
    sensor_find_cmd.add_argument("name", help=i18n.t("help.arg.sensor_ref"))

    _find_pattern_leaf(
        sensor_sub, "findr", help=i18n.t("help.sensor.findr"),
        example="jmri-cli sensor findr '^Montagne'", func=sensor.sensor_findr,
        sort_fields=sensor.SORT_FIELDS,
    )

    _find_pattern_leaf(
        sensor_sub, "findg", help=i18n.t("help.sensor.findg"),
        example="jmri-cli sensor findg 'Montagne*'", func=sensor.sensor_findg,
        sort_fields=sensor.SORT_FIELDS,
    )

    # -- block: bare = list; read-only ------------------------------------
    block_cmd, block_sub = _group(subparsers, "block", default_func=block.block_list)
    block_cmd.epilog = "example:\n  jmri-cli block"
    block_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        block_sub, "list", help=i18n.t("help.block.list"),
        example="jmri-cli block list", func=block.block_list,
    )
    _sort_siblings(
        block_sub, block.SORT_FIELDS, func=block.block_list,
        example_prefix="jmri-cli block",
    )

    block_status_cmd = _leaf(
        block_sub, "status", help=i18n.t("help.block.status"),
        example='jmri-cli block status "B_1_Montagne A"', func=block.block_status,
    )
    block_status_cmd.add_argument("name", help=i18n.t("help.arg.block_ref"))

    block_find_cmd = _leaf(
        block_sub, "find", help=i18n.t("help.block.find"),
        example='jmri-cli block find "B_1_Montagne A"', func=block.block_find,
    )
    block_find_cmd.add_argument("name", help=i18n.t("help.arg.block_ref"))

    _find_pattern_leaf(
        block_sub, "findr", help=i18n.t("help.block.findr"),
        example="jmri-cli block findr '^B_1'", func=block.block_findr,
        sort_fields=block.SORT_FIELDS,
    )

    _find_pattern_leaf(
        block_sub, "findg", help=i18n.t("help.block.findg"),
        example="jmri-cli block findg 'B_1*'", func=block.block_findg,
        sort_fields=block.SORT_FIELDS,
    )

    # -- signal: bare = list ---------------------------------------------
    signal_cmd, signal_sub = _group(subparsers, "signal", default_func=signal.signal_list)
    signal_cmd.epilog = "example:\n  jmri-cli signal"
    signal_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        signal_sub, "list", help=i18n.t("help.signal.list"),
        example="jmri-cli signal list", func=signal.signal_list,
    )
    _sort_siblings(
        signal_sub, signal.SORT_FIELDS, func=signal.signal_list,
        example_prefix="jmri-cli signal",
    )

    signal_status_cmd = _leaf(
        signal_sub, "status", help=i18n.t("help.signal.status"),
        example='jmri-cli signal status "Entry Signal A"', func=signal.signal_status,
    )
    signal_status_cmd.add_argument("name", help=i18n.t("help.arg.signal_ref"))

    signal_find_cmd = _leaf(
        signal_sub, "find", help=i18n.t("help.signal.find"),
        example='jmri-cli signal find "Entry Signal A"', func=signal.signal_find,
    )
    signal_find_cmd.add_argument("name", help=i18n.t("help.arg.signal_ref"))

    _find_pattern_leaf(
        signal_sub, "findr", help=i18n.t("help.signal.findr"),
        example="jmri-cli signal findr '^Entry'", func=signal.signal_findr,
        sort_fields=signal.SORT_FIELDS,
    )

    _find_pattern_leaf(
        signal_sub, "findg", help=i18n.t("help.signal.findg"),
        example="jmri-cli signal findg 'Entry*'", func=signal.signal_findg,
        sort_fields=signal.SORT_FIELDS,
    )

    signal_set_cmd = _leaf(
        signal_sub, "set", help=i18n.t("help.signal.set"),
        example='jmri-cli signal set "Entry Signal A" Hp1', func=signal.signal_set,
    )
    signal_set_cmd.add_argument("name", help=i18n.t("help.arg.signal_ref"))
    signal_set_cmd.add_argument("aspect", help=i18n.t("help.signal.set_aspect"))

    return parser
