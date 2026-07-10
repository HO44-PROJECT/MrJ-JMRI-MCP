"""Argument parser assembly for jmri-cli.

Wires the command functions from power.py/roster.py/throttle.py into a
single argparse.ArgumentParser, matching jmri-cli's documented command
tree (see the package docstring in jmri_mcp/cli/__init__.py).
"""

import argparse

from jmri_mcp.cli import light, power, roster, sensor, throttle, turnout
from jmri_mcp.cli._doc import CLI_DESCRIPTION


def build_parser() -> argparse.ArgumentParser:
    """Build jmri-cli's full argument parser.

    Returns:
        An argparse.ArgumentParser with all subcommands registered, each
        with its `func` default set to the command function that handles it.
    """
    parser = argparse.ArgumentParser(prog="jmri-cli", description=CLI_DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    power_cmd = subparsers.add_parser("power", help="Power system commands")
    power_sub = power_cmd.add_subparsers(dest="power_command", required=True)

    status = power_sub.add_parser("status", help="Show power state (all systems, or one)")
    status.add_argument("system", nargs="?", default=None,
                         help="System name/prefix/fragment (omit for all systems)")
    status.set_defaults(func=power.power_status)

    set_ = power_sub.add_parser("set", help="Turn a system's power on/off (writes to JMRI)")
    set_.add_argument("system", help="System name/prefix/fragment")
    set_.add_argument("state", choices=["on", "off"])
    set_.set_defaults(func=power.power_set)

    stop_all = power_sub.add_parser(
        "stop-all", help="Cut power to EVERY system at once (layout-wide emergency stop)"
    )
    stop_all.set_defaults(func=power.power_stop_all)

    start_all = power_sub.add_parser(
        "start-all", help="Restore power to EVERY system at once (inverse of stop-all)"
    )
    start_all.set_defaults(func=power.power_start_all)

    status_cmd = subparsers.add_parser(
        "status", help="One-call diagnostic: JMRI reachability, version, power systems"
    )
    status_cmd.set_defaults(func=power.system_status)

    roster_cmd = subparsers.add_parser(
        "roster", help="List every locomotive in JMRI's roster (name, address, road, model)"
    )
    roster_sub = roster_cmd.add_subparsers(dest="roster_command")
    roster_cmd.set_defaults(func=roster.roster_list)

    roster_find_cmd = roster_sub.add_parser(
        "find", help="Resolve a locomotive name to its DCC address (fuzzy match)"
    )
    roster_find_cmd.add_argument("name", help="Locomotive name, or a fragment of it")
    roster_find_cmd.set_defaults(func=roster.roster_find)

    roster_functions_cmd = roster_sub.add_parser(
        "functions", help="List a locomotive's user-labeled decoder functions"
    )
    roster_functions_cmd.add_argument("name", help="Locomotive name, or a fragment of it")
    roster_functions_cmd.set_defaults(func=roster.roster_functions)

    throttle_cmd = subparsers.add_parser("throttle", help="Throttle commands (persistent WebSocket)")
    throttle_sub = throttle_cmd.add_subparsers(dest="throttle_command", required=True)

    acquire = throttle_sub.add_parser("acquire", help="Acquire a loco by DCC address")
    acquire.add_argument("address", type=int, help="DCC address")
    acquire.add_argument("--prefix", default=None,
                          help="Command station prefix (e.g. O, Z, R) to target")
    acquire.set_defaults(func=throttle.throttle_acquire)

    release = throttle_sub.add_parser("release", help="Release a loco by DCC address")
    release.add_argument("address", type=int, help="DCC address")
    release.set_defaults(func=throttle.throttle_release)

    speed = throttle_sub.add_parser("speed", help="Set a loco's speed (0-100%%)")
    speed.add_argument("address", type=int, help="DCC address")
    speed.add_argument("speed_percent", type=float, help="Speed, 0-100")
    speed.set_defaults(func=throttle.throttle_speed)

    stop_cmd = throttle_sub.add_parser("stop", help="Controlled stop (speed 0)")
    stop_cmd.add_argument("address", type=int, help="DCC address")
    stop_cmd.set_defaults(func=throttle.throttle_stop)

    estop = throttle_sub.add_parser("estop", help="Emergency stop (JMRI decoder e-stop)")
    estop.add_argument("address", type=int, help="DCC address")
    estop.set_defaults(func=throttle.throttle_estop)

    stop_all = throttle_sub.add_parser(
        "stop-all", help="Emergency-stop EVERY roster locomotive at once (panic button)"
    )
    stop_all.add_argument(
        "-a", "--address", type=int, action="append", default=None,
        help="Limit to this DCC address instead of the whole roster (repeatable)",
    )
    stop_all.set_defaults(func=throttle.throttle_stop_all)

    direction = throttle_sub.add_parser("direction", help="Set direction (forward/reverse)")
    direction.add_argument("address", type=int, help="DCC address")
    direction.add_argument("direction", choices=["forward", "reverse"])
    direction.set_defaults(func=throttle.throttle_direction)

    function = throttle_sub.add_parser("function", help="Set a decoder function F0-F28 on/off")
    function.add_argument("address", type=int, help="DCC address")
    function.add_argument("function", type=int, help="Function number, 0-28")
    function.add_argument("state", choices=["on", "off"])
    function.set_defaults(func=throttle.throttle_function)

    lights_on = throttle_sub.add_parser("lights-on", help="Shortcut for function <address> 0 on")
    lights_on.add_argument("address", type=int, help="DCC address")
    lights_on.set_defaults(func=throttle.throttle_lights_on)

    lights_off = throttle_sub.add_parser("lights-off", help="Shortcut for function <address> 0 off")
    lights_off.add_argument("address", type=int, help="DCC address")
    lights_off.set_defaults(func=throttle.throttle_lights_off)

    sniff = throttle_sub.add_parser(
        "sniff", help="Dump every JMRI WebSocket message live, until Ctrl-C"
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
    sniff.set_defaults(func=throttle.throttle_sniff)

    light_cmd = subparsers.add_parser(
        "light", help="Layout light commands (depot/street/signal lamps, not loco headlights)"
    )
    light_sub = light_cmd.add_subparsers(dest="light_command", required=True)

    light_list_cmd = light_sub.add_parser("list", help="Show every light's state")
    light_list_cmd.set_defaults(func=light.light_list)

    light_status_cmd = light_sub.add_parser("status", help="Show one light's state")
    light_status_cmd.add_argument("name", help="Light system name, userName, or fragment")
    light_status_cmd.set_defaults(func=light.light_status)

    light_set_cmd = light_sub.add_parser("set", help="Turn a light on/off (writes to JMRI)")
    light_set_cmd.add_argument("name", help="Light system name, userName, or fragment")
    light_set_cmd.add_argument("state", choices=["on", "off"])
    light_set_cmd.set_defaults(func=light.light_set)

    turnout_cmd = subparsers.add_parser("turnout", help="Turnout commands")
    turnout_sub = turnout_cmd.add_subparsers(dest="turnout_command", required=True)

    turnout_list_cmd = turnout_sub.add_parser("list", help="Show every turnout's state")
    turnout_list_cmd.set_defaults(func=turnout.turnout_list)

    turnout_status_cmd = turnout_sub.add_parser("status", help="Show one turnout's state")
    turnout_status_cmd.add_argument("name", help="Turnout system name, userName, or fragment")
    turnout_status_cmd.set_defaults(func=turnout.turnout_status)

    turnout_set_cmd = turnout_sub.add_parser("set", help="Set a turnout closed/thrown (writes to JMRI)")
    turnout_set_cmd.add_argument("name", help="Turnout system name, userName, or fragment")
    turnout_set_cmd.add_argument("state", choices=["closed", "thrown"])
    turnout_set_cmd.set_defaults(func=turnout.turnout_set)

    sensor_cmd = subparsers.add_parser("sensor", help="Sensor commands (read-only)")
    sensor_sub = sensor_cmd.add_subparsers(dest="sensor_command", required=True)

    sensor_list_cmd = sensor_sub.add_parser("list", help="Show every sensor's state")
    sensor_list_cmd.set_defaults(func=sensor.sensor_list)

    sensor_status_cmd = sensor_sub.add_parser("status", help="Show one sensor's state")
    sensor_status_cmd.add_argument("name", help="Sensor system name, userName, or fragment")
    sensor_status_cmd.set_defaults(func=sensor.sensor_status)

    return parser
