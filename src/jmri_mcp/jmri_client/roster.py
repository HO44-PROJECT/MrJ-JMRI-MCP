"""Roster domain: locomotive listing, name resolution, and function labels.

One-shot async HTTP against JMRI's /json/roster endpoint (see
jmri_mcp.jmri_client._http for the shared GET/POST plumbing).
"""

import logging
import unicodedata
from typing import Any

from jmri_mcp.jmri_client._http import JmriError, _get_json, _unwrap

logger = logging.getLogger("jmri_mcp.client")


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
    payload = await _get_json("/json/roster")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError(f"Unexpected /json/roster payload: {payload!r}")
    entries = [_unwrap(entry) for entry in payload]
    match = next((e for e in entries if e.get("name") == name), None)
    if match is None:
        raise JmriError(f"No roster entry named {name!r}")

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
    useful for a voice/chat summary. This returns only name, address (as
    int; JMRI reports it as a numeric string), road, and model — road/model
    can be empty strings if the user never filled them in JMRI, not missing.
    """
    payload = await _get_json("/json/roster")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError(f"Unexpected /json/roster payload: {payload!r}")
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
            "model": e.get("model", ""),
        })
    return compact


def _fold(text: str) -> str:
    """Casefold and strip accents, for tolerant French-name matching ("autorail" == "Autorail")."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).casefold()


def resolve_roster_entry(
    query: str, roster: list[dict[str, Any]]
) -> dict[str, Any]:
    """Match a user-supplied locomotive name against the roster (see get_roster).

    Tolerant like resolve_system: case/accent-insensitive ("autorail",
    "AUTORAIL", "boite a sel" all match), exact name first, then substring
    fragment if that's unambiguous. Unlike resolve_system there's no
    "default" to fall back to on an empty query — a locomotive must be
    named. Raises JmriError (not found / ambiguous), same as resolve_system,
    so callers can handle both the same way.
    """
    if not roster:
        raise JmriError("JMRI roster is empty")
    if not query or not query.strip():
        raise JmriError("No locomotive name given")

    q = _fold(query.strip())
    names = [str(e.get("name", "")) for e in roster]

    exact = [e for e in roster if _fold(str(e.get("name", ""))) == q]
    if len(exact) == 1:
        return exact[0]

    partial = [e for e in roster if q in _fold(str(e.get("name", "")))]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(e.get("name")) for e in partial]
        raise JmriError(f"Ambiguous locomotive {query!r}: matches {matches}")

    raise JmriError(f"Unknown locomotive {query!r}. Available: {names}")
