"""Sensor domain: list/get JMRI `sensor` objects (block occupancy, etc).

One-shot async HTTP against JMRI's /json/sensors (list) and
/json/sensor/<name> (single get) endpoints (see jmri_core.jmri_client._http
for the shared GET/POST plumbing). Read-only: sensors report real-world
state (block occupancy, turnout motor feedback, ...) detected by JMRI's own
hardware inputs — this project has no business setting one directly, only
reading it (contrast with turnout.py/light.py, which do write).
"""

import logging
from typing import Any

from jmri_core.constants import endpoints
from jmri_core.jmri_client._http import JmriError, _get_json, _unwrap

logger = logging.getLogger("jmri_core.client")

SENSOR_ACTIVE = 2
SENSOR_INACTIVE = 4


async def get_sensors() -> list[dict[str, Any]]:
    """Return every sensor known to JMRI.

    Each entry has at least: name (JMRI system name, e.g. "RS22"),
    userName (may be None if never set in JMRI), state (2=ACTIVE,
    4=INACTIVE; JMRI can also report 0=UNKNOWN or 8=INCONSISTENT). Sensors
    are used for block occupancy detection and other real-world inputs
    (e.g. turnout motor feedback, which shows up here too — see the
    "sensor" field nested in get_turnouts() entries).
    """
    payload = await _get_json(endpoints.SENSORS)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.SENSORS, payload=payload)
    sensors = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d sensor(s): %s",
                len(sensors), [s.get("userName") or s.get("name") for s in sensors])
    return sensors


def resolve_sensor(query: str, sensors: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied sensor name against discovered sensors.

    Tolerant like resolve_light/resolve_turnout: case-insensitive, matches
    either the JMRI system name ("RS22") or the user-friendly userName
    ("Montagne B") exactly first, then an unambiguous substring fragment of
    userName or the system name. No default fallback — a sensor must be named.
    """
    if not sensors:
        raise JmriError("none_available", kind="sensor")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="sensor")

    q = query.strip().casefold()
    labels = [str(s.get("userName") or s.get("name", "")) for s in sensors]

    exact = [
        s for s in sensors
        if str(s.get("name", "")).casefold() == q
        or str(s.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [
        s for s in sensors
        if q in str(s.get("userName") or "").casefold()
        or q in str(s.get("name", "")).casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(s.get("userName") or s.get("name")) for s in partial]
        raise JmriError("ambiguous_entity", kind="sensor", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="sensor", query=query, available=labels)
