"""Top-level usage text shown by `jmri-cli --help`, shared by __init__.py and parser.py."""

CLI_DESCRIPTION = """Manual CLI for exercising the JMRI client without an MCP client.

Usage:
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli power status
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli power status ohara
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli power set ohara on
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli power stop-all
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli status
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli roster
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli roster find autorail
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli roster functions autorail
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle acquire 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle release 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle speed 3 40
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle stop 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle estop 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle stop-all -a 3 -a 7
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle direction 3 reverse
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle function 3 1 on
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle lights-on 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle lights-off 3
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle sniff
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli throttle sniff --address 3 --address 7
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli light list
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli light status "Depot Lighting"
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli light set "Depot Lighting" on
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli turnout list
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli turnout status "Layout Turnout A"
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli turnout set "Layout Turnout A" thrown
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli sensor list
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli sensor status "Montagne B"
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli signal list
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli signal status "Entry Signal A"
    JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli signal set "Entry Signal A" Hp1

`power`/`status`/`light`/`turnout`/`sensor`/`signal` talk to jmri_client.py
directly (one-shot HTTP, no MCP/JSON-RPC involved). `throttle` talks to
jmri_ws.py (a fresh WebSocket connection for the one command, then closed) —
useful for quick manual checks against a real layout, same role
test_manuel.py used to play before it became tests/test_live.py.
"""
