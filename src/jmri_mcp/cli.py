"""Manual CLI for exercising the JMRI client without an MCP client.

Usage:
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status ohara
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power set ohara on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli roster
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli roster find autorail
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle acquire 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle release 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle speed 3 40
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle stop 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle estop 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle direction 3 reverse
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle function 3 1 on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle lights-on 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle lights-off 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle sniff
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle sniff --address 3 --address 7

`power`/`status` talk to jmri_client.py directly (one-shot HTTP, no
MCP/JSON-RPC involved). `throttle` talks to jmri_ws.py (a fresh WebSocket
connection for the one command, then closed) — useful for quick manual
checks against a real layout, same role test_manuel.py used to play before
it became tests/test_live.py.
"""

import argparse
import asyncio
import json
import sys

from jmri_mcp.jmri_client import (
    JmriError,
    get_roster,
    get_systems,
    get_version,
    resolve_roster_entry,
    resolve_system,
    set_power,
)
from jmri_mcp.jmri_ws import JmriError as JmriWsError
from jmri_mcp.jmri_ws import JmriWsClient

_STATE_NAMES = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}


def _format_system(system: dict) -> str:
    state = _STATE_NAMES.get(system.get("state"), "UNKNOWN")
    marker = " (default)" if system.get("default") else ""
    return f"{system.get('name', '?'):<15}: {state}{marker}"


async def power_status(args: argparse.Namespace) -> int:
    try:
        systems = await get_systems()
        if args.system:
            match = resolve_system(args.system, systems)
            print(_format_system(match))
        else:
            for system in systems:
                print(_format_system(system))
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


async def power_set(args: argparse.Namespace) -> int:
    turn_on = args.state == "on"
    try:
        systems = await get_systems()
        match = resolve_system(args.system, systems)
        result = await set_power(match["prefix"], turn_on)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(_format_system(result))
    if not result["confirmed"]:
        print(f"WARNING: requested {args.state.upper()} but observed state "
              f"did not confirm after re-read", file=sys.stderr)
        return 1
    return 0


async def roster_list(args: argparse.Namespace) -> int:
    try:
        roster = await get_roster()
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not roster:
        print("Roster is empty")
        return 0
    for entry in roster:
        road = entry["road"] or "-"
        model = entry["model"] or "-"
        print(f"{entry['address']:<5} {entry['name']:<20} {road:<30} {model}")
    return 0


async def roster_find(args: argparse.Namespace) -> int:
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.name, roster)
    except JmriError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    road = entry["road"] or "-"
    model = entry["model"] or "-"
    print(f"address={entry['address']} name={entry['name']} road={road} model={model}")
    return 0


async def system_status(args: argparse.Namespace) -> int:
    try:
        version = await get_version()
    except JmriError as exc:
        print(f"JMRI unreachable: {exc}", file=sys.stderr)
        return 1

    print(f"JMRI reachable, version {version}")
    try:
        systems = await get_systems()
        for system in systems:
            print(f"  {_format_system(system)}")
    except JmriError as exc:
        print(f"  Power systems unavailable: {exc}", file=sys.stderr)
        return 1
    return 0


async def throttle_acquire(args: argparse.Namespace) -> int:
    client = JmriWsClient()
    try:
        data = await client.acquire_throttle(f"cli{args.address}", args.address, args.prefix)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={data.get('address')} speed={data.get('speed')} "
          f"forward={data.get('forward')} (acquired)")
    return 0


async def throttle_release(args: argparse.Namespace) -> int:
    # A throttle is only meaningfully released on the connection that holds
    # it — a fresh CLI connection never holds another session's throttle,
    # so this acquires (JMRI just re-confirms if already held elsewhere)
    # then releases on this same connection, mirroring what closing that
    # other connection would do.
    client = JmriWsClient()
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        await client.release_throttle(f"cli{args.address}")
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} released")
    return 0


async def throttle_speed(args: argparse.Namespace) -> int:
    # NOTE (2026-07-09): a throttle only means anything on the connection
    # holding it - JMRI releases it the moment this connection closes, and
    # verified live, a plain acquire/set/close one-shot does not reliably
    # keep the real locomotive moving at the requested speed. A "hold the
    # connection open until Ctrl-C" version (like `sniff`) was tried, but
    # disabled per user request: on Ctrl-C the loco kept coasting at the
    # last speed instead of stopping, because closing the socket releases
    # the throttle without sending a stop first - a worse surprise than the
    # one-shot's unreliability. Left commented out below rather than
    # deleted; needs a real fix (e.g. send speed 0 before closing on
    # Ctrl-C) before re-enabling, not reverted from history if needed:
    #
    #     print(f"address={args.address} speed={data.get('speed', speed) * 100:.0f}%")
    #     if speed == 0.0:
    #         await client.close()
    #         return 0
    #     print("Holding throttle open, Ctrl-C to release...", file=sys.stderr)
    #     try:
    #         while True:
    #             await asyncio.sleep(3600)
    #     except (KeyboardInterrupt, asyncio.CancelledError):
    #         pass
    #     finally:
    #         await client.close()
    #     print(f"address={args.address} throttle released")
    #     return 0
    client = JmriWsClient()
    speed = max(0.0, min(100.0, args.speed_percent)) / 100.0
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        data = await client.set_speed(f"cli{args.address}", speed)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} speed={data.get('speed', speed) * 100:.0f}%")
    return 0


async def throttle_stop(args: argparse.Namespace) -> int:
    client = JmriWsClient()
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        await client.set_speed(f"cli{args.address}", 0.0)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} stopped")
    return 0


async def throttle_estop(args: argparse.Namespace) -> int:
    client = JmriWsClient()
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        await client.set_speed(f"cli{args.address}", -1.0)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} emergency-stopped")
    return 0


async def throttle_direction(args: argparse.Namespace) -> int:
    client = JmriWsClient()
    forward = args.direction == "forward"
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        data = await client.set_direction(f"cli{args.address}", forward)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    reported = "forward" if data.get("forward", forward) else "reverse"
    print(f"address={args.address} direction={reported}")
    return 0


async def throttle_function(args: argparse.Namespace) -> int:
    if not (0 <= args.function <= 28):
        print(f"Error: function must be 0-28, got {args.function}", file=sys.stderr)
        return 1
    client = JmriWsClient()
    state = args.state == "on"
    try:
        await client.acquire_throttle(f"cli{args.address}", args.address)
        data = await client.set_function(f"cli{args.address}", args.function, state)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    reported = "on" if data.get(f"F{args.function}", state) else "off"
    print(f"address={args.address} F{args.function}={reported}")
    return 0


async def throttle_lights_on(args: argparse.Namespace) -> int:
    args.function, args.state = 0, "on"
    return await throttle_function(args)


async def throttle_lights_off(args: argparse.Namespace) -> int:
    args.function, args.state = 0, "off"
    return await throttle_function(args)


def _format_sniff_data(msg_type: str, data) -> str:
    """Compact a JMRI message's data for one-line display.

    Throttle messages list every function key (F0-F68) even when only one
    changed, which drowns the field that actually changed — collapse them
    to just the functions currently ON, dropped entirely if none are.
    """
    if msg_type == "throttle" and isinstance(data, dict):
        data = dict(data)
        active_functions = sorted(
            (k for k, v in data.items() if k[0] == "F" and k[1:].isdigit() and v),
            key=lambda k: int(k[1:]),
        )
        for key in list(data):
            if key[0] == "F" and key[1:].isdigit():
                del data[key]
        if active_functions:
            data["functions_on"] = active_functions
    return json.dumps(data)


async def throttle_sniff(args: argparse.Namespace) -> int:
    """Dump every JMRI WebSocket message on this connection until Ctrl-C.

    With no --address, this only sees hello/pong and whatever this
    connection itself triggers. Pass --address (repeatable) to also acquire
    those locos first — JMRI then pushes every state change on them from
    ANY client (other MCP sessions, JMRI panels, throttle apps) to this
    connection too, which is the point: watching what's actually moving on
    the layout, not just what this tool sends. Keepalive pong messages are
    hidden by default (--show-pong to include them) since they carry no
    information and fire every few seconds regardless of layout activity.
    """
    import datetime

    async def on_message(msg_type: str, data) -> None:
        if msg_type == "pong" and not args.show_pong:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] {msg_type}: {_format_sniff_data(msg_type, data)}")

    client = JmriWsClient(on_message=on_message)
    try:
        await client.connect()
        for address in args.address or []:
            try:
                await client.acquire_throttle(f"sniff{address}", address)
                print(f"(acquired address={address} for observation)")
            except JmriWsError as exc:
                print(f"Warning: could not acquire {address}: {exc}", file=sys.stderr)

        print("Listening for JMRI messages, Ctrl-C to stop...", file=sys.stderr)
        while True:
            await asyncio.sleep(3600)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jmri-cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    power = subparsers.add_parser("power", help="Power system commands")
    power_sub = power.add_subparsers(dest="power_command", required=True)

    status = power_sub.add_parser("status", help="Show power state (all systems, or one)")
    status.add_argument("system", nargs="?", default=None,
                         help="System name/prefix/fragment (omit for all systems)")
    status.set_defaults(func=power_status)

    set_ = power_sub.add_parser("set", help="Turn a system's power on/off (writes to JMRI)")
    set_.add_argument("system", help="System name/prefix/fragment")
    set_.add_argument("state", choices=["on", "off"])
    set_.set_defaults(func=power_set)

    status_cmd = subparsers.add_parser(
        "status", help="One-call diagnostic: JMRI reachability, version, power systems"
    )
    status_cmd.set_defaults(func=system_status)

    roster_cmd = subparsers.add_parser(
        "roster", help="List every locomotive in JMRI's roster (name, address, road, model)"
    )
    roster_sub = roster_cmd.add_subparsers(dest="roster_command")
    roster_cmd.set_defaults(func=roster_list)

    roster_find_cmd = roster_sub.add_parser(
        "find", help="Resolve a locomotive name to its DCC address (fuzzy match)"
    )
    roster_find_cmd.add_argument("name", help="Locomotive name, or a fragment of it")
    roster_find_cmd.set_defaults(func=roster_find)

    throttle = subparsers.add_parser("throttle", help="Throttle commands (persistent WebSocket)")
    throttle_sub = throttle.add_subparsers(dest="throttle_command", required=True)

    acquire = throttle_sub.add_parser("acquire", help="Acquire a loco by DCC address")
    acquire.add_argument("address", type=int, help="DCC address")
    acquire.add_argument("--prefix", default=None,
                          help="Command station prefix (e.g. O, Z, R) to target")
    acquire.set_defaults(func=throttle_acquire)

    release = throttle_sub.add_parser("release", help="Release a loco by DCC address")
    release.add_argument("address", type=int, help="DCC address")
    release.set_defaults(func=throttle_release)

    speed = throttle_sub.add_parser("speed", help="Set a loco's speed (0-100%)")
    speed.add_argument("address", type=int, help="DCC address")
    speed.add_argument("speed_percent", type=float, help="Speed, 0-100")
    speed.set_defaults(func=throttle_speed)

    stop_cmd = throttle_sub.add_parser("stop", help="Controlled stop (speed 0)")
    stop_cmd.add_argument("address", type=int, help="DCC address")
    stop_cmd.set_defaults(func=throttle_stop)

    estop = throttle_sub.add_parser("estop", help="Emergency stop (JMRI decoder e-stop)")
    estop.add_argument("address", type=int, help="DCC address")
    estop.set_defaults(func=throttle_estop)

    direction = throttle_sub.add_parser("direction", help="Set direction (forward/reverse)")
    direction.add_argument("address", type=int, help="DCC address")
    direction.add_argument("direction", choices=["forward", "reverse"])
    direction.set_defaults(func=throttle_direction)

    function = throttle_sub.add_parser("function", help="Set a decoder function F0-F28 on/off")
    function.add_argument("address", type=int, help="DCC address")
    function.add_argument("function", type=int, help="Function number, 0-28")
    function.add_argument("state", choices=["on", "off"])
    function.set_defaults(func=throttle_function)

    lights_on = throttle_sub.add_parser("lights-on", help="Shortcut for function <address> 0 on")
    lights_on.add_argument("address", type=int, help="DCC address")
    lights_on.set_defaults(func=throttle_lights_on)

    lights_off = throttle_sub.add_parser("lights-off", help="Shortcut for function <address> 0 off")
    lights_off.add_argument("address", type=int, help="DCC address")
    lights_off.set_defaults(func=throttle_lights_off)

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
    sniff.set_defaults(func=throttle_sniff)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
