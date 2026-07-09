"""Power, roster, and throttle tools exposed to the LLM.

Throttle tools (acquire_throttle, release_throttle, set_speed, stop,
emergency_stop, set_direction, set_function, lights_on, lights_off) key
everything on DCC address — see tools._common.throttle_id. list_roster/
find_locomotive are how the LLM turns a spoken name ("the Autorail") into
the address those tools need: list_roster for browsing, find_locomotive for
resolving one specific name (fuzzy, accent/case-insensitive) directly to an
address. get_locomotive_functions exposes the user's own per-loco function
labels (set in JMRI's roster editor) so "turn on the rear lights" can
resolve to the right F-number without any hardcoded name->function mapping.

Package layout:
    _common.py  Shared helpers (throttle_id, compact_power/throttle, ensure_acquired).
    power.py    list_systems, get_power, set_power, system_status.
    roster.py   list_roster, find_locomotive, get_locomotive_functions.
    throttle.py acquire/release_throttle, set_speed/stop/emergency_stop,
                set_direction, set_function, lights_on/lights_off.
"""

from jmri_mcp.tools import power, roster, throttle

__all__ = ["register"]


def register(mcp) -> None:
    """Register every tool from power.py/roster.py/throttle.py on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """
    power.register(mcp)
    roster.register(mcp)
    throttle.register(mcp)
