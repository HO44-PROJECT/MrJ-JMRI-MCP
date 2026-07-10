"""Manual CLI for exercising the JMRI client without an MCP client.

Usage:
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power status ohara
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power set ohara on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli power stop-all
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli status
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli roster
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli roster find autorail
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli roster functions autorail
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle acquire 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle release 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle speed 3 40
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle stop 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle estop 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle stop-all -a 3 -a 7
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle direction 3 reverse
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle function 3 1 on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle lights-on 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle lights-off 3
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle sniff
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli throttle sniff --address 3 --address 7
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli light list
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli light status "Depot Lighting"
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli light set "Depot Lighting" on
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli turnout list
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli turnout status "Layout Turnout A"
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli turnout set "Layout Turnout A" thrown
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli sensor list
    JMRI_URL=http://10.0.20.20:12080 python -m jmri_mcp.cli sensor status "Montagne B"

`power`/`status`/`light`/`turnout`/`sensor` talk to jmri_client.py directly
(one-shot HTTP, no MCP/JSON-RPC involved). `throttle` talks to jmri_ws.py (a
fresh WebSocket connection for the one command, then closed) — useful for
quick manual checks against a real layout, same role test_manuel.py used to
play before it became tests/test_live.py.

Package layout:
    constants.py  Shared constants (state names, id prefixes, ranges).
    _common.py    Small cross-module helpers (cli_throttle_id).
    _doc.py       This module's usage text, shared with parser.py.
    power.py      power status/set, status (jmri_client.py, one-shot HTTP).
    roster.py     roster / roster find / roster functions (jmri_client.py).
    throttle.py   throttle acquire/release/speed/stop/estop/direction/
                  function/lights-on/lights-off/sniff (jmri_ws.py).
    light.py      light list/status/set (jmri_client.py, one-shot HTTP;
                  layout/scenery lights, not loco headlights).
    turnout.py    turnout list/status/set (jmri_client.py, one-shot HTTP).
    sensor.py     sensor list/status (jmri_client.py, one-shot HTTP; read-only).
    parser.py     build_parser(): wires all of the above into one CLI.
"""

import asyncio
import sys

from jmri_mcp.cli.parser import build_parser

__all__ = ["build_parser", "main"]


def main() -> None:
    """Entry point for the `jmri-cli` console script and `python -m jmri_mcp.cli`."""
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)
