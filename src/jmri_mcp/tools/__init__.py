"""Power, roster, and throttle tools exposed to the LLM.

Throttle tools (acquire_throttle, release_throttle, set_speed, stop,
emergency_stop, emergency_stop_all, set_direction, set_function, lights_on,
lights_off) key everything on DCC address — see tools._common.throttle_id.
list_roster/find_locomotive are how the LLM turns a spoken name ("the
Autorail") into the address those tools need: list_roster for browsing,
find_locomotive for resolving one specific name (fuzzy, accent/case-
insensitive) directly to an address. get_locomotive_functions exposes the
user's own per-loco function labels (set in JMRI's roster editor) so "turn
on the rear lights" can resolve to the right F-number without any
hardcoded name->function mapping.

Package layout:
    _common.py  Shared helpers (throttle_id, compact_power/throttle/light/
                turnout/sensor, ensure_acquired).
    power.py    list_systems, get_power, set_power, power_off_all,
                system_status.
    roster.py   list_roster, find_locomotive, get_locomotive_functions.
    throttle.py acquire/release_throttle, set_speed/stop/emergency_stop,
                emergency_stop_all, set_direction, set_function,
                lights_on/lights_off.
    light.py    list_lights, get_light, set_light (layout/scenery lights,
                distinct from a locomotive's F0 headlight function).
    turnout.py  list_turnouts, get_turnout, set_turnout.
    sensor.py   list_sensors, get_sensor (read-only).
    signal.py   list_signals, get_signal, set_signal (signalMast only,
                see jmri_client.signal's module docstring for why not
                signalHead).
    block.py    list_blocks, get_block (read-only; a block is a named
                track section with occupancy + linked sensor/value,
                richer than a plain sensor).
    mode.py     set_executor_mode, get_executor_mode (concise/no-narration
                response style — a behavioral nudge, not a JMRI command).
"""

from jmri_mcp.tools import block, light, mode, power, roster, sensor, signal, throttle, turnout

__all__ = ["register"]


def register(mcp) -> None:
    """Register every tool from every domain module on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """
    power.register(mcp)
    roster.register(mcp)
    throttle.register(mcp)
    light.register(mcp)
    turnout.register(mcp)
    sensor.register(mcp)
    signal.register(mcp)
    block.register(mcp)
    mode.register(mcp)
