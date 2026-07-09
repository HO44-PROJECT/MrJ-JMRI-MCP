"""Manual CLI for exercising the JMRI client without an MCP client.

Usage:
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status ohara
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power set ohara on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle acquire 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle release 3

`power`/`status` talk to jmri_client.py directly (one-shot HTTP, no
MCP/JSON-RPC involved). `throttle` talks to jmri_ws.py (a fresh WebSocket
connection for the one command, then closed) — useful for quick manual
checks against a real layout, same role test_manuel.py used to play before
it became tests/test_live.py.
"""

import argparse
import asyncio
import sys

from jmri_mcp.jmri_client import (
    JmriError,
    get_systems,
    get_version,
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
