"""Argument parser assembly for jmri-cli.

Wires the command functions from power.py/roster.py/throttle.py into a
single argparse.ArgumentParser, matching jmri-cli's documented command
tree (see the package docstring in jmri_mcp/cli/__init__.py). Every
top-level group gets a short, inviting one-liner (see _doc.GROUP_HELP)
instead of a technical description, and every leaf subcommand (the ones
that actually run against JMRI) gets an `epilog` with a copy-pasteable
example - `jmri-cli <group> <leaf> -h` is meant to be self-sufficient,
no separate "examples" command needed.

Consistency rule applied throughout (per user feedback on the first pass
of this redesign): a group whose members share an obvious "just show me
the state" default doesn't force typing a leaf name for it — bare `power`
behaves like `power status`, bare `roster` like `roster list`, bare
`throttle` like `throttle list`. And where a leaf's own value is really a
verb (on/off, forward/reverse, closed/thrown), that value is elevated to
be the subcommand name itself instead of a positional choice argument —
`power on`/`power off`, `throttle forward`/`throttle reverse`, `light
on`/`light off`, `turnout closed`/`turnout thrown`, `throttle on`/`off`.
"""

import argparse
import functools

from jmri_mcp.cli import light, power, roster, sensor, signal, throttle, turnout
from jmri_mcp.cli._doc import GROUP_HELP


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
            help="Ramp up to the target speed over this many seconds, instead of jumping instantly",
        )
    leaf.add_argument(
        "--rampdown", type=float, default=None, metavar="SECONDS",
        help="Ramp down to the target speed over this many seconds, instead of jumping instantly",
    )
    if seconds:
        leaf.add_argument(
            "--hold", type=float, default=None, metavar="SECONDS", dest="seconds",
            help="Hold the resulting nonzero speed this long, then auto-stop "
                 "(mandatory outside the shell whenever the target speed is nonzero)",
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
    group_cmd = subparsers.add_parser(name, help=GROUP_HELP[name])
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
        power_sub, "status", help="Show power state of every system",
        example="jmri-cli power status", func=power.power_status,
    )

    on_ = _leaf(
        power_sub, "on", help="Turn a system on, or every system if none is given",
        example="jmri-cli power on ohara", func=power.power_on,
    )
    on_.add_argument("system", nargs="?", default=None,
                      help="System name/prefix/fragment (omit for every system)")

    off_ = _leaf(
        power_sub, "off",
        help="Turn a system off, or every system if none is given (layout-wide stop)",
        example="jmri-cli power off", func=power.power_off,
    )
    off_.add_argument("system", nargs="?", default=None,
                       help="System name/prefix/fragment (omit for every system)")

    get_ = _leaf(
        power_sub, "get", help="Print one system's power state as a bare ON/OFF",
        example="jmri-cli power get ohara", func=power.power_get,
    )
    get_.add_argument("system", nargs="?", default=None,
                       help="System name/prefix/fragment (omit for the default system)")

    _leaf(
        power_sub, "default", help="Print which power system JMRI treats as the default",
        example="jmri-cli power default", func=power.power_default,
    )

    status_cmd = subparsers.add_parser(
        "status", help=GROUP_HELP["status"],
        description=GROUP_HELP["status"],
        epilog="example:\n  jmri-cli status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status_cmd.set_defaults(func=power.system_status)

    # -- roster: bare = list -----------------------------------------
    roster_cmd, roster_sub = _group(subparsers, "roster", default_func=roster.roster_list)
    roster_cmd.epilog = "example:\n  jmri-cli roster"
    roster_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        roster_sub, "list", help="Show every locomotive in the roster",
        example="jmri-cli roster list", func=roster.roster_list,
    )

    roster_find_cmd = _leaf(
        roster_sub, "find", help="Resolve a locomotive name or DCC address to its roster entry",
        example="jmri-cli roster find autorail", func=roster.roster_find,
    )
    roster_find_cmd.add_argument("name", help="Locomotive name, a fragment of it, or a DCC address")

    roster_functions_cmd = _leaf(
        roster_sub, "functions", help="List a locomotive's user-labeled decoder functions",
        example="jmri-cli roster functions autorail", func=roster.roster_functions,
    )
    roster_functions_cmd.add_argument("name", help="Locomotive name, a fragment of it, or a DCC address")

    # -- throttle: bare = list acquired (from local cache) ------------
    throttle_cmd, throttle_sub = _group(subparsers, "throttle", default_func=throttle.throttle_list)
    throttle_cmd.epilog = "example:\n  jmri-cli throttle"
    throttle_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        throttle_sub, "list", help="Show last-known speed/direction/functions per locomotive",
        example="jmri-cli throttle list", func=throttle.throttle_list,
    )

    acquire = _leaf(
        throttle_sub, "acquire", help="Acquire a locomotive by name/fragment/address",
        example="jmri-cli throttle acquire 3", func=throttle.throttle_acquire,
    )
    acquire.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    acquire.add_argument("--prefix", default=None,
                          help="Command station prefix (e.g. O, Z, R) to target")

    release = _leaf(
        throttle_sub, "release", help="Release a locomotive by name/fragment/address",
        example="jmri-cli throttle release 3", func=throttle.throttle_release,
    )
    release.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")

    speed = _leaf(
        throttle_sub, "speed", help="Get or set a locomotive's speed (0-100%%)",
        example="jmri-cli throttle speed 3 40", func=throttle.throttle_speed,
    )
    speed.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    speed.add_argument("speed_percent", type=float, nargs="?", default=None,
                        help="Speed, 0-100 (omit to just read the current speed); a NEGATIVE "
                             "value is shorthand for reverse at that magnitude, e.g. -40")
    _add_ramp_args(speed, rampup=True, seconds=True)
    speed.epilog = (
        "example:\n"
        "  jmri-cli throttle speed 3 40\n"
        "  jmri-cli throttle speed 3 40 --rampup 5 --hold 30 --rampdown 5"
    )

    stop_cmd = _leaf(
        throttle_sub, "stop",
        help="Controlled stop of one locomotive, or every touched one if none is given",
        example="jmri-cli throttle stop", func=throttle.throttle_stop,
    )
    stop_cmd.add_argument("loco", nargs="?", default=None,
                           help="Locomotive name, fragment, or DCC address (omit to stop every "
                                "locomotive this CLI has touched; required inside the shell)")
    _add_ramp_args(stop_cmd, rampup=False, seconds=False)
    stop_cmd.epilog = (
        "example:\n"
        "  jmri-cli throttle stop\n"
        "  jmri-cli throttle stop 3 --rampdown 5"
    )

    estop = _leaf(
        throttle_sub, "estop", help="Emergency stop (JMRI decoder e-stop)",
        example="jmri-cli throttle estop 3", func=throttle.throttle_estop,
    )
    estop.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")

    forward = _leaf(
        throttle_sub, "forward", help="Set direction forward",
        example="jmri-cli throttle forward 3", func=functools.partial(throttle.throttle_direction, forward=True),
    )
    forward.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    _add_ramp_args(forward, rampup=True, seconds=True)
    forward.epilog = (
        "example:\n"
        "  jmri-cli throttle forward 3\n"
        "  jmri-cli throttle forward 3 --rampdown 3 --rampup 3 --hold 30"
    )

    reverse = _leaf(
        throttle_sub, "reverse", help="Set direction reverse",
        example="jmri-cli throttle reverse 3", func=functools.partial(throttle.throttle_direction, forward=False),
    )
    reverse.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    _add_ramp_args(reverse, rampup=True, seconds=True)
    reverse.epilog = (
        "example:\n"
        "  jmri-cli throttle reverse 3\n"
        "  jmri-cli throttle reverse 3 --rampdown 3 --rampup 3 --hold 30"
    )

    on_fn = _leaf(
        throttle_sub, "on",
        help="Turn a decoder function on (by number or label), or every labeled one",
        example="jmri-cli throttle on 3 1", func=throttle.throttle_on,
    )
    on_fn.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    on_fn.add_argument("function", nargs="?", default=None,
                        help="Function number (0-28) or a fragment of its roster label "
                             "(omit for every labeled function)")

    off_fn = _leaf(
        throttle_sub, "off",
        help="Turn a decoder function off (by number or label), or every labeled one",
        example="jmri-cli throttle off 3 1", func=throttle.throttle_off,
    )
    off_fn.add_argument("loco", help="Locomotive name, a fragment of it, or a DCC address")
    off_fn.add_argument("function", nargs="?", default=None,
                         help="Function number (0-28) or a fragment of its roster label "
                              "(omit for every labeled function)")

    sniff = _leaf(
        throttle_sub, "sniff", help="Dump every JMRI WebSocket message live, until Ctrl-C",
        example="jmri-cli throttle sniff -a 3 -a 7", func=throttle.throttle_sniff,
    )
    sniff.add_argument(
        "-a", "--address", type=int, action="append", default=None,
        help="DCC address to acquire first (repeatable) so its pushes from "
             "OTHER clients show up too; omit to just watch this connection",
    )
    sniff.add_argument(
        "--show-pong", action="store_true",
        help="Include keepalive pong messages (hidden by default, no info)",
    )

    # -- light: bare = list; on/off take an optional fuzzy target -----
    light_cmd, light_sub = _group(subparsers, "light", default_func=light.light_list)
    light_cmd.epilog = "example:\n  jmri-cli light"
    light_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        light_sub, "list", help="Show every light's state",
        example="jmri-cli light list", func=light.light_list,
    )

    light_on_cmd = _leaf(
        light_sub, "on", help="Turn a light on, or every light if none is given",
        example='jmri-cli light on "Depot Lighting"', func=light.light_on,
    )
    light_on_cmd.add_argument("name", nargs="?", default=None,
                               help="Light name/userName/fragment (omit for every light)")

    light_off_cmd = _leaf(
        light_sub, "off", help="Turn a light off, or every light if none is given",
        example='jmri-cli light off "Depot Lighting"', func=light.light_off,
    )
    light_off_cmd.add_argument("name", nargs="?", default=None,
                                help="Light name/userName/fragment (omit for every light)")

    # -- turnout: bare = list; closed/thrown take an optional fuzzy target
    turnout_cmd, turnout_sub = _group(subparsers, "turnout", default_func=turnout.turnout_list)
    turnout_cmd.epilog = "example:\n  jmri-cli turnout"
    turnout_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        turnout_sub, "list", help="Show every turnout's state",
        example="jmri-cli turnout list", func=turnout.turnout_list,
    )

    turnout_closed_cmd = _leaf(
        turnout_sub, "closed", help="Set a turnout closed, or every turnout if none is given",
        example='jmri-cli turnout closed "Layout Turnout A"', func=turnout.turnout_closed,
    )
    turnout_closed_cmd.add_argument("name", nargs="?", default=None,
                                     help="Turnout name/userName/fragment (omit for every turnout)")

    turnout_thrown_cmd = _leaf(
        turnout_sub, "thrown", help="Set a turnout thrown, or every turnout if none is given",
        example='jmri-cli turnout thrown "Layout Turnout A"', func=turnout.turnout_thrown,
    )
    turnout_thrown_cmd.add_argument("name", nargs="?", default=None,
                                     help="Turnout name/userName/fragment (omit for every turnout)")

    # -- sensor: bare = list; read-only ---------------------------------
    sensor_cmd, sensor_sub = _group(subparsers, "sensor", default_func=sensor.sensor_list)
    sensor_cmd.epilog = "example:\n  jmri-cli sensor"
    sensor_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        sensor_sub, "list", help="Show every sensor's state",
        example="jmri-cli sensor list", func=sensor.sensor_list,
    )

    sensor_status_cmd = _leaf(
        sensor_sub, "status", help="Show one sensor's state",
        example='jmri-cli sensor status "Montagne B"', func=sensor.sensor_status,
    )
    sensor_status_cmd.add_argument("name", help="Sensor system name, userName, or fragment")

    # -- signal: bare = list ---------------------------------------------
    signal_cmd, signal_sub = _group(subparsers, "signal", default_func=signal.signal_list)
    signal_cmd.epilog = "example:\n  jmri-cli signal"
    signal_cmd.formatter_class = argparse.RawDescriptionHelpFormatter

    _leaf(
        signal_sub, "list", help="Show every signal mast's aspect",
        example="jmri-cli signal list", func=signal.signal_list,
    )

    signal_status_cmd = _leaf(
        signal_sub, "status", help="Show one signal mast's aspect",
        example='jmri-cli signal status "Entry Signal A"', func=signal.signal_status,
    )
    signal_status_cmd.add_argument("name", help="Signal mast system name, userName, or fragment")

    signal_set_cmd = _leaf(
        signal_sub, "set", help="Set a signal mast's aspect (writes to JMRI)",
        example='jmri-cli signal set "Entry Signal A" Hp1', func=signal.signal_set,
    )
    signal_set_cmd.add_argument("name", help="Signal mast system name, userName, or fragment")
    signal_set_cmd.add_argument("aspect", help="Aspect name, e.g. Hp0/Hp1/Hp2 (not validated locally)")

    return parser
