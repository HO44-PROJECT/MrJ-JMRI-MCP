"""Roster domain: locomotive listing, name resolution, and function labels.

One-shot async HTTP against JMRI's /json/roster endpoint (see
jmri_core.jmri_client._http for the shared GET/POST plumbing).
"""

import logging
from typing import Any

from jmri_core.constants import endpoints
from jmri_core.jmri_client._http import JmriError, _get_json, _unwrap
from jmri_core.text import fold as _fold

logger = logging.getLogger("jmri_core.client")


async def get_roster_function_labels(name: str) -> dict[int, str]:
    """Return {function_number: label} for a roster entry's user-set function names.

    JMRI's /json/roster always carries all 29 functionKeys (F0-F28) per
    entry, but `label` is null unless the user typed one in in JMRI (e.g.
    PanelPro's Roster Entry editor) — most locos in a roster have none set.
    This returns only the ones that ARE labeled, keyed by function number;
    an empty dict means the user hasn't labeled anything for this loco (not
    an error). Matches a roster entry by exact `name` (as returned by
    get_roster()/resolve_roster_entry(), not fuzzy here — callers should
    already have resolved the exact name before calling this).
    """
    payload = await _get_json(endpoints.ROSTER)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.ROSTER, payload=payload)
    entries = [_unwrap(entry) for entry in payload]
    match = next((e for e in entries if e.get("name") == name), None)
    if match is None:
        raise JmriError("no_entry_with_name", name=name)

    labels: dict[int, str] = {}
    for fk in match.get("functionKeys", []):
        label = fk.get("label")
        fname = fk.get("name", "")
        if label and fname[:1] == "F" and fname[1:].isdigit():
            labels[int(fname[1:])] = label
    return labels


async def get_roster() -> list[dict[str, Any]]:
    """Return every roster entry, compacted to the fields worth 2 KB of raw JSON.

    Each raw entry is wrapped ({"type": "rosterEntry", "data": {...}}, the
    legacy prototype bug was reading the envelope level instead of ["data"])
    and carries ~2 KB of fields (functionKeys, comment, icon paths, ...) not
    useful for a voice/chat summary. This returns name, address (as int;
    JMRI reports it as a numeric string), road, road number, manufacturer,
    model, owner, last-modified date, and roster groups the entry belongs
    to — any of these can be empty (string or list) if the user never
    filled them in JMRI, not missing. JMRI's own field for the latter is
    "rosterGroups" (a list of group name strings; verified live against
    the user's JMRI 5.4.0 — most entries have an empty list, one had
    ["test"]), not "group" as its PanelPro UI name might suggest.

    Also returns dcc_system: the power system prefix (e.g. "T") this
    locomotive is normally driven through, read from a JMRI RosterEntry
    Attribute named "DccSystem" (PanelPro: Roster Entry -> Edit ->
    Attributes tab) - verified live against the user's JMRI 5.4.0, which
    exposes custom attributes as entry["attributes"], a list of
    {"name", "value"} pairs, distinct from "rosterGroups". None if the user
    hasn't set this attribute for the entry (the normal case for most
    locos, not an error) - issue #60, for users running more than one
    command station where a given loco is only ever acquired through one
    of them.

    Also returns max_speed_percent: JMRI's raw "maxSpeedPct" field (an int,
    e.g. 20), the per-locomotive speed limit set in PanelPro's Roster Entry
    editor ("Throttle Speed Limit"). Defaults to 100 (no restriction) when
    absent. This is a CLIENT-SIDE-only limit in JMRI: PanelPro's own
    throttle applies it by scaling the slider before sending to the
    decoder, but a WebSocket "speed" command sent directly (as this project
    does) is NOT scaled by JMRI itself - verified live, a raw 1.0 sent over
    the wire always means full decoder speed regardless of maxSpeedPct.
    Callers driving a throttle (set_speed and friends) must apply this
    scaling themselves - see resolve_max_speed_percent.
    """
    payload = await _get_json(endpoints.ROSTER)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.ROSTER, payload=payload)
    entries = [_unwrap(entry) for entry in payload]
    compact = []
    for e in entries:
        try:
            address = int(e["address"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Roster entry %r has unusable address %r, skipping",
                           e.get("name"), e.get("address"))
            continue
        dcc_system = None
        for attr in e.get("attributes") or []:
            if attr.get("name") == "DccSystem":
                dcc_system = attr.get("value") or None
                break
        compact.append({
            "name": e.get("name", ""),
            "address": address,
            "road": e.get("road", ""),
            "road_number": e.get("number", ""),
            "manufacturer": e.get("mfg", ""),
            "model": e.get("model", ""),
            "owner": e.get("owner", ""),
            "date_modified": e.get("dateModified", ""),
            "groups": e.get("rosterGroups", []),
            "dcc_system": dcc_system,
            "max_speed_percent": e.get("maxSpeedPct", 100),
        })
    return compact


def resolve_roster_entry(
    query: str, roster: list[dict[str, Any]]
) -> dict[str, Any]:
    """Match a user-supplied locomotive name or DCC address against the roster.

    Tolerant like resolve_system: case/accent-insensitive ("autorail",
    "AUTORAIL", "boite a sel" all match), exact name first, then substring
    fragment if that's unambiguous. A purely numeric query (e.g. "4") is
    matched against `address` instead of `name` — DCC addresses are unique
    in a roster, so this is always a single exact match or not found, never
    ambiguous. Unlike resolve_system there's no "default" to fall back to on
    an empty query — a locomotive must be named. Raises JmriError (not
    found / ambiguous), same as resolve_system, so callers can handle both
    the same way.
    """
    if not roster:
        raise JmriError("none_available", kind="locomotive")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="locomotive")

    stripped = query.strip()
    if stripped.lstrip("-").isdigit():
        address = int(stripped)
        match = next((e for e in roster if e.get("address") == address), None)
        if match is None:
            raise JmriError("no_entry_with_address", address=address)
        return match

    q = _fold(stripped)
    names = [str(e.get("name", "")) for e in roster]

    exact = [e for e in roster if _fold(str(e.get("name", ""))) == q]
    if len(exact) == 1:
        return exact[0]

    partial = [e for e in roster if q in _fold(str(e.get("name", "")))]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(e.get("name")) for e in partial]
        raise JmriError("ambiguous_entity", kind="locomotive", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="locomotive", query=query, available=names)


async def resolve_dcc_prefix(address: int) -> str | None:
    """Look up the command station prefix a DCC address should be acquired through.

    Reads the roster entry with this `address` and returns its `dcc_system`
    (see get_roster()) — the connection prefix (e.g. "T") set via a
    "DccSystem" Roster Entry Attribute in PanelPro. Returns None when the
    address has no matching roster entry, or the entry has no DccSystem
    attribute set — both are normal (a raw address with no roster entry,
    or a single-command-station layout that doesn't need this), not an
    error; callers should fall back to JMRI's default command station.

    This is issue #60's fix: without it, acquiring a throttle always goes
    to JMRI's default command station regardless of which one a given
    locomotive is actually wired to, so a loco on a secondary station
    (e.g. Taya) silently never moves even though the acquire/speed calls
    "succeed" — JMRI has no way to reject a speed command sent to the
    wrong station, it's just inaudible to that decoder.
    """
    roster = await get_roster()
    entry = next((e for e in roster if e.get("address") == address), None)
    if entry is None:
        return None
    return entry.get("dcc_system")


async def resolve_max_speed_percent(address: int) -> int:
    """Look up the per-locomotive speed limit ("Throttle Speed Limit" in PanelPro).

    Reads the roster entry with this `address` and returns its
    max_speed_percent (see get_roster()) — an int 1-100, JMRI's raw
    "maxSpeedPct" field. Returns 100 (no restriction) when the address has
    no matching roster entry — a raw address with no roster entry has no
    limit to apply, not an error.

    Verified live against the user's JMRI 5.4.0: a locomotive with its
    PanelPro Roster Entry "Throttle Speed Limit" set to 20% moves at 20%
    real decoder speed when PanelPro's own throttle slider is at 100%,
    because PanelPro scales the value it sends. JMRI's WebSocket "speed"
    command does NOT apply this scaling itself — sending speed:1.0 directly
    always means full decoder speed. Callers driving a throttle (set_speed
    and friends) must multiply their own 0.0-1.0 fraction by
    max_speed_percent/100 before sending, to match PanelPro's behavior.
    """
    roster = await get_roster()
    entry = next((e for e in roster if e.get("address") == address), None)
    if entry is None:
        return 100
    return entry.get("max_speed_percent", 100)
