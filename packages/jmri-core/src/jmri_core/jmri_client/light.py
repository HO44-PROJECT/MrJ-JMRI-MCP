"""Layout light domain: list/get/set JMRI `light` objects.

One-shot async HTTP against JMRI's /json/lights (list) and /json/light/<name>
(single get/set) endpoints (see jmri_core.jmri_client._http for the shared
GET/POST plumbing). Distinct from a locomotive's F0 headlight function
(tools/throttle.py) — these are layout-side lights (depot, street, signal
lamps, ...) wired to JMRI as their own `light` objects, independent of any
DCC address.
"""

import logging
from typing import Any

from jmri_core.constants import endpoints
from jmri_core.jmri_client._http import JmriError, _get_json, _post_json, _unwrap

logger = logging.getLogger("jmri_core.client")

LIGHT_ON = 2
LIGHT_OFF = 4


async def get_lights() -> list[dict[str, Any]]:
    """Return every layout light known to JMRI.

    Each entry has at least: name (JMRI system name, e.g. "IL1"), userName
    (may be None if never set in JMRI), state (2=ON, 4=OFF; JMRI can also
    report 0=UNKNOWN or 8=INCONSISTENT for a light with feedback wired up).
    """
    payload = await _get_json(endpoints.LIGHTS)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.LIGHTS, payload=payload)
    lights = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d light(s): %s",
                len(lights), [lt.get("userName") or lt.get("name") for lt in lights])
    return lights


async def set_light(name: str, turn_on: bool) -> dict[str, Any]:
    """Set one light ON/OFF by its JMRI system name, then report the observed state.

    Args:
        name: The light's JMRI system name (e.g. "IL1"), as returned by
            get_lights()/resolve_light() — not the user-facing label.
        turn_on: True to turn the light ON, False to turn it OFF.

    Unlike set_power, JMRI's /json/light POST response for a simple
    (non-feedback) light is authoritative immediately — but this still
    re-reads via get_lights() to report the same "confirmed" honesty
    contract as set_power, since some light hardware (feedback-wired)
    can settle to a different state than requested.
    """
    desired = LIGHT_ON if turn_on else LIGHT_OFF
    await _post_json(endpoints.LIGHT.format(name=name), {"name": name, "state": desired})

    lights = await get_lights()
    matches = [lt for lt in lights if lt.get("name") == name]
    if not matches:
        raise JmriError("vanished_after_post", kind="light", name=name)
    observed = matches[0]

    confirmed = observed.get("state") == desired
    if not confirmed:
        logger.warning(
            "set_light(%s, %s): requested state=%s but observed state=%s",
            name, turn_on, desired, observed.get("state"),
        )
    return {**observed, "confirmed": confirmed}


def resolve_light(query: str, lights: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied light name against discovered lights.

    Tolerant like resolve_system/resolve_roster_entry: case-insensitive,
    matches either the JMRI system name ("IL1") or the user-friendly
    userName ("Depot Lighting") exactly first, then an unambiguous
    substring fragment of userName or the system name. No default fallback
    — a light must be named, there's no single "the" light the way there's
    a default power system.
    """
    if not lights:
        raise JmriError("none_available", kind="light")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="light")

    q = query.strip().casefold()
    labels = [str(lt.get("userName") or lt.get("name", "")) for lt in lights]

    exact = [
        lt for lt in lights
        if str(lt.get("name", "")).casefold() == q
        or str(lt.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [
        lt for lt in lights
        if q in str(lt.get("userName") or "").casefold()
        or q in str(lt.get("name", "")).casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(lt.get("userName") or lt.get("name")) for lt in partial]
        raise JmriError("ambiguous_entity", kind="light", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="light", query=query, available=labels)
