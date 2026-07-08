"""Manual CLI for exercising the JMRI client without an MCP client.

Usage:
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status ohara

Talks to jmri_client.py directly (no MCP/JSON-RPC involved) — useful for
quick manual checks against a real layout, same role test_manuel.py used
to play before it became tests/test_live.py.
"""

import argparse
import asyncio
import sys

from jmri_mcp.jmri_client import JmriError, get_systems, resolve_system

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jmri-cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    power = subparsers.add_parser("power", help="Power system commands")
    power_sub = power.add_subparsers(dest="power_command", required=True)

    status = power_sub.add_parser("status", help="Show power state (all systems, or one)")
    status.add_argument("system", nargs="?", default=None,
                         help="System name/prefix/fragment (omit for all systems)")
    status.set_defaults(func=power_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
