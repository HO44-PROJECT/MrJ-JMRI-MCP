"""Async client for the JMRI web server JSON API (REST over http).

All layout data (systems, roster, turnouts, ...) is discovered live from
JMRI; nothing is hardcoded here.

Unlike jmri_ws.py (a persistent WebSocket, needed only because a JMRI
throttle is bound to its connection), everything here is a one-shot HTTP
request with no state kept between calls.

Package layout:
    _http.py   Shared GET/POST plumbing, JmriError, envelope unwrapping.
    power.py   Version, power-system discovery, power on/off, resolve_system.
    roster.py  Roster listing, name resolution, function labels.

Every public name below is re-exported here so existing callers can keep
doing `from jmri_mcp.jmri_client import get_roster` etc. without knowing
which domain module actually defines it.
"""

from jmri_mcp.jmri_client._http import JmriError
from jmri_mcp.jmri_client.power import (
    POWER_OFF,
    POWER_ON,
    get_systems,
    get_version,
    resolve_system,
    set_power,
)
from jmri_mcp.jmri_client.roster import (
    get_roster,
    get_roster_function_labels,
    resolve_roster_entry,
)

__all__ = [
    "JmriError",
    "POWER_ON",
    "POWER_OFF",
    "get_version",
    "get_systems",
    "set_power",
    "resolve_system",
    "get_roster",
    "get_roster_function_labels",
    "resolve_roster_entry",
]
