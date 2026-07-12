"""Turnout domain: list/get/set JMRI `turnout` objects.

One-shot async HTTP against JMRI's /json/turnouts (list) and
/json/turnout/<name> (single get/set) endpoints (see
jmri_core.jmri_client._http for the shared GET/POST plumbing).
"""

import logging
from typing import Any

from jmri_core.constants import endpoints
from jmri_core.jmri_client._http import JmriError, _get_json, _post_json, _unwrap

logger = logging.getLogger("jmri_core.client")

TURNOUT_CLOSED = 2
TURNOUT_THROWN = 4


async def get_turnouts() -> list[dict[str, Any]]:
    """Return every turnout known to JMRI.

    Each entry has at least: name (JMRI system name, e.g. "IT100"),
    userName (may be None if never set in JMRI), state (2=CLOSED,
    4=THROWN, 0=UNKNOWN, 8=INCONSISTENT), and "sensor" (JMRI's 2-element
    feedback-sensor array, entries null if no real sensor is wired there).

    INCONSISTENT is NOT always a transient settling condition. Verified
    live (2026-07-11) against a turnout with no wired feedback sensor
    (sensor: [null, null]): it reported state=8 persistently, at rest,
    with no command in flight — JMRI simply has no way to confirm that
    kind of turnout's real position, so it reports INCONSISTENT
    indefinitely as its steady state. Only a turnout with an actual
    sensor object in its "sensor" array can meaningfully "settle" out of
    INCONSISTENT. See the jmri-mcp package's jmri_mcp.tools._common.compact_turnout's
    has_feedback_sensor field, derived from this same "sensor" array, for
    how downstream callers should interpret this.
    """
    payload = await _get_json(endpoints.TURNOUTS)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.TURNOUTS, payload=payload)
    turnouts = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d turnout(s): %s",
                len(turnouts), [t.get("userName") or t.get("name") for t in turnouts])
    return turnouts


async def set_turnout(name: str, thrown: bool) -> dict[str, Any]:
    """Set one turnout CLOSED/THROWN by its JMRI system name, then report the observed state.

    Args:
        name: The turnout's JMRI system name (e.g. "IT100"), as returned by
            get_turnouts()/resolve_turnout() — not the user-facing label.
        thrown: True to throw the turnout, False to close it.

    Re-reads via get_turnouts() after the POST and reports "confirmed"
    honestly, same contract as set_power()/set_light() — a feedback-wired
    turnout's motor can take a moment to settle, or fail to reach the
    requested position.
    """
    desired = TURNOUT_THROWN if thrown else TURNOUT_CLOSED
    await _post_json(endpoints.TURNOUT.format(name=name), {"name": name, "state": desired})

    turnouts = await get_turnouts()
    matches = [t for t in turnouts if t.get("name") == name]
    if not matches:
        raise JmriError("vanished_after_post", kind="turnout", name=name)
    observed = matches[0]

    confirmed = observed.get("state") == desired
    if not confirmed:
        logger.warning(
            "set_turnout(%s, %s): requested state=%s but observed state=%s",
            name, thrown, desired, observed.get("state"),
        )
    return {**observed, "confirmed": confirmed}


def resolve_turnout(query: str, turnouts: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied turnout name against discovered turnouts.

    Tolerant like resolve_light: case-insensitive, matches either the JMRI
    system name ("IT100") or the user-friendly userName ("Layout Turnout A")
    exactly first, then an unambiguous substring fragment of userName. No
    default fallback — a turnout must be named, there's no single "the"
    turnout.
    """
    if not turnouts:
        raise JmriError("none_available", kind="turnout")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="turnout")

    q = query.strip().casefold()
    labels = [str(t.get("userName") or t.get("name", "")) for t in turnouts]

    exact = [
        t for t in turnouts
        if str(t.get("name", "")).casefold() == q
        or str(t.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [t for t in turnouts if q in str(t.get("userName") or "").casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(t.get("userName") or t.get("name")) for t in partial]
        raise JmriError("ambiguous_entity", kind="turnout", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="turnout", query=query, available=labels)
