"""Async client for the JMRI web server JSON API (REST over http).

All layout data (systems, roster, turnouts, ...) is discovered live from
JMRI; nothing is hardcoded here.

Unlike jmri_ws.py (a persistent WebSocket, needed only because a JMRI
throttle is bound to its connection), everything here is a one-shot HTTP
request with no state kept between calls.

Package layout:
    _http.py    Shared GET/POST plumbing, JmriError, envelope unwrapping.
    power.py    Version, power-system discovery, power on/off, resolve_system.
    roster.py   Roster listing, name resolution, function labels.
    light.py    Layout light discovery, on/off, resolve_light.
    turnout.py  Turnout discovery, closed/thrown, resolve_turnout.
    sensor.py   Sensor discovery (read-only), resolve_sensor.
    signal.py   Signal mast discovery, aspect set, resolve_signal.
    block.py    Layout block discovery (read-only), resolve_block.

Every public name below is re-exported here so existing callers can keep
doing `from jmri_core.jmri_client import get_roster` etc. without knowing
which domain module actually defines it.
"""

from jmri_core.jmri_client._http import JmriError
from jmri_core.jmri_client.block import (
    BLOCK_OCCUPIED,
    BLOCK_UNOCCUPIED,
    get_blocks,
    resolve_block,
)
from jmri_core.jmri_client.light import (
    LIGHT_OFF,
    LIGHT_ON,
    get_lights,
    resolve_light,
    set_light,
)
from jmri_core.jmri_client.power import (
    POWER_OFF,
    POWER_ON,
    POWER_UNKNOWN,
    default_system_prefix,
    get_systems,
    get_version,
    parse_dcc_address,
    parse_signal_dcc_address,
    power_off_all,
    power_on_all,
    resolve_dcc_system_name,
    resolve_system,
    resolve_system_name,
    set_power,
)
from jmri_core.jmri_client.roster import (
    get_roster,
    get_roster_function_labels,
    resolve_dcc_prefix,
    resolve_max_speed_percent,
    resolve_roster_entry,
)
from jmri_core.jmri_client.sensor import (
    SENSOR_ACTIVE,
    SENSOR_INACTIVE,
    get_sensors,
    resolve_sensor,
)
from jmri_core.jmri_client.signal import (
    get_signals,
    resolve_signal,
    set_signal,
)
from jmri_core.jmri_client.turnout import (
    TURNOUT_CLOSED,
    TURNOUT_THROWN,
    get_turnouts,
    resolve_turnout,
    set_turnout,
)

__all__ = [
    "JmriError",
    "POWER_ON",
    "POWER_OFF",
    "POWER_UNKNOWN",
    "get_version",
    "get_systems",
    "set_power",
    "power_off_all",
    "power_on_all",
    "resolve_system",
    "resolve_system_name",
    "resolve_dcc_system_name",
    "parse_dcc_address",
    "parse_signal_dcc_address",
    "default_system_prefix",
    "get_roster",
    "get_roster_function_labels",
    "resolve_dcc_prefix",
    "resolve_max_speed_percent",
    "resolve_roster_entry",
    "LIGHT_ON",
    "LIGHT_OFF",
    "get_lights",
    "set_light",
    "resolve_light",
    "TURNOUT_CLOSED",
    "TURNOUT_THROWN",
    "get_turnouts",
    "set_turnout",
    "resolve_turnout",
    "SENSOR_ACTIVE",
    "SENSOR_INACTIVE",
    "get_sensors",
    "resolve_sensor",
    "get_signals",
    "set_signal",
    "resolve_signal",
    "BLOCK_OCCUPIED",
    "BLOCK_UNOCCUPIED",
    "get_blocks",
    "resolve_block",
]
