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
