"""Argument parser assembly for jmri-cli.

Wires the command functions from power.py/roster.py/throttle.py into a
single argparse.ArgumentParser, matching jmri-cli's documented command
tree (see the package docstring in jmri_mcp/cli/__init__.py). Every
top-level group gets a short, inviting one-liner (see the
`help.group.*` keys in jmri_mcp/i18n/en.json) instead of a technical
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

from jmri_mcp import i18n
from jmri_mcp.cli import light, power, roster, sensor, signal, throttle, turnout


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

    # -- roster: bare = list -----------------------------------------
    roster_cmd, roster_sub = _group(subparsers, "roster", default_func=roster.roster_list)
    roster_cmd.epilog = "example:\n  jmri-cli roster"
    roster_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    list_cmd = _leaf(
        roster_sub, "list", help=i18n.t("help.roster.list"),
        example="jmri-cli roster list bydcc", func=roster.roster_list,
    )
    list_cmd.add_argument(
        "sort_by", nargs="?", default="byname",
        choices=roster.SORT_CHOICES,
        help=i18n.t("help.roster.sort_by"),
    )

    roster_find_cmd = _leaf(
        roster_sub, "find", help=i18n.t("help.roster.find"),
        example="jmri-cli roster find autorail", func=roster.roster_find,
    )
    roster_find_cmd.add_argument("name", help=i18n.t("help.arg.loco_ref"))

    roster_findr_cmd = _leaf(
        roster_sub, "findr", help=i18n.t("help.roster.findr"),
        example="jmri-cli roster findr '^auto'", func=roster.roster_findr,
    )
    roster_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    roster_findg_cmd = _leaf(
        roster_sub, "findg", help=i18n.t("help.roster.findg"),
        example="jmri-cli roster findg 'boite*'", func=roster.roster_findg,
    )
    roster_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

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
    acquire.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    acquire.add_argument("--prefix", default=None,
                          help=i18n.t("help.throttle.acquire_prefix"))

    release = _leaf(
        throttle_sub, "release", help=i18n.t("help.throttle.release"),
        example="jmri-cli throttle release 3", func=throttle.throttle_release,
    )
    release.add_argument("loco", help=i18n.t("help.arg.loco_ref"))

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
    estop.add_argument("loco", help=i18n.t("help.arg.loco_ref"))

    forward = _leaf(
        throttle_sub, "forward", help=i18n.t("help.throttle.forward"),
        example="jmri-cli throttle forward 3", func=functools.partial(throttle.throttle_direction, forward=True),
    )
    forward.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    _add_ramp_args(forward, rampup=True, seconds=True)
    forward.epilog = (
        "example:\n"
        "  jmri-cli throttle forward 3\n"
        "  jmri-cli throttle forward 3 --rampdown 3 --rampup 3 --hold 30"
    )

    reverse = _leaf(
        throttle_sub, "reverse", help=i18n.t("help.throttle.reverse"),
        example="jmri-cli throttle reverse 3", func=functools.partial(throttle.throttle_direction, forward=False),
    )
    reverse.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    _add_ramp_args(reverse, rampup=True, seconds=True)
    reverse.epilog = (
        "example:\n"
        "  jmri-cli throttle reverse 3\n"
        "  jmri-cli throttle reverse 3 --rampdown 3 --rampup 3 --hold 30"
    )

    on_fn = _leaf(
        throttle_sub, "on",
        help=i18n.t("help.throttle.on"),
        example="jmri-cli throttle on 3 1", func=throttle.throttle_on,
    )
    on_fn.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    on_fn.add_argument("function", nargs="?", default=None,
                        help=i18n.t("help.arg.function_ref_or_every"))

    off_fn = _leaf(
        throttle_sub, "off",
        help=i18n.t("help.throttle.off"),
        example="jmri-cli throttle off 3 1", func=throttle.throttle_off,
    )
    off_fn.add_argument("loco", help=i18n.t("help.arg.loco_ref"))
    off_fn.add_argument("function", nargs="?", default=None,
                         help=i18n.t("help.arg.function_ref_or_every"))

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

    # -- light: bare = list; on/off take an optional fuzzy target -----
    light_cmd, light_sub = _group(subparsers, "light", default_func=light.light_list)
    light_cmd.epilog = "example:\n  jmri-cli light"
    light_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        light_sub, "list", help=i18n.t("help.light.list"),
        example="jmri-cli light list", func=light.light_list,
    )

    light_find_cmd = _leaf(
        light_sub, "find", help=i18n.t("help.light.find"),
        example='jmri-cli light find "Depot Lighting"', func=light.light_find,
    )
    light_find_cmd.add_argument("name", help=i18n.t("help.light.find_name"))

    light_findr_cmd = _leaf(
        light_sub, "findr", help=i18n.t("help.light.findr"),
        example="jmri-cli light findr '^Depot'", func=light.light_findr,
    )
    light_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    light_findg_cmd = _leaf(
        light_sub, "findg", help=i18n.t("help.light.findg"),
        example="jmri-cli light findg 'Depot*'", func=light.light_findg,
    )
    light_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

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

    turnout_find_cmd = _leaf(
        turnout_sub, "find", help=i18n.t("help.turnout.find"),
        example="jmri-cli turnout find IT100", func=turnout.turnout_find,
    )
    turnout_find_cmd.add_argument("name", help=i18n.t("help.turnout.find_name"))

    turnout_findr_cmd = _leaf(
        turnout_sub, "findr", help=i18n.t("help.turnout.findr"),
        example="jmri-cli turnout findr '^Mountain'", func=turnout.turnout_findr,
    )
    turnout_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    turnout_findg_cmd = _leaf(
        turnout_sub, "findg", help=i18n.t("help.turnout.findg"),
        example="jmri-cli turnout findg 'Layout*'", func=turnout.turnout_findg,
    )
    turnout_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

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

    sensor_findr_cmd = _leaf(
        sensor_sub, "findr", help=i18n.t("help.sensor.findr"),
        example="jmri-cli sensor findr '^Montagne'", func=sensor.sensor_findr,
    )
    sensor_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    sensor_findg_cmd = _leaf(
        sensor_sub, "findg", help=i18n.t("help.sensor.findg"),
        example="jmri-cli sensor findg 'Montagne*'", func=sensor.sensor_findg,
    )
    sensor_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

    # -- signal: bare = list ---------------------------------------------
    signal_cmd, signal_sub = _group(subparsers, "signal", default_func=signal.signal_list)
    signal_cmd.epilog = "example:\n  jmri-cli signal"
    signal_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        signal_sub, "list", help=i18n.t("help.signal.list"),
        example="jmri-cli signal list", func=signal.signal_list,
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

    signal_findr_cmd = _leaf(
        signal_sub, "findr", help=i18n.t("help.signal.findr"),
        example="jmri-cli signal findr '^Entry'", func=signal.signal_findr,
    )
    signal_findr_cmd.add_argument("pattern", help=i18n.t("help.arg.regex_pattern"))

    signal_findg_cmd = _leaf(
        signal_sub, "findg", help=i18n.t("help.signal.findg"),
        example="jmri-cli signal findg 'Entry*'", func=signal.signal_findg,
    )
    signal_findg_cmd.add_argument("pattern", help=i18n.t("help.arg.glob_pattern"))

    signal_set_cmd = _leaf(
        signal_sub, "set", help=i18n.t("help.signal.set"),
        example='jmri-cli signal set "Entry Signal A" Hp1', func=signal.signal_set,
    )
    signal_set_cmd.add_argument("name", help=i18n.t("help.arg.signal_ref"))
    signal_set_cmd.add_argument("aspect", help=i18n.t("help.signal.set_aspect"))

    return parser
