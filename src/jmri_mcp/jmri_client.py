"""Async client for the JMRI web server JSON API (REST over http).

All layout data (systems, roster, turnouts, ...) is discovered live from
JMRI; nothing is hardcoded here.
"""

import asyncio
import logging
from typing import Any

import httpx

from jmri_mcp.config import get_jmri_url

logger = logging.getLogger("jmri_mcp.client")

_TIMEOUT = 5.0
_POST_RECHECK_DELAY = 1.0
POWER_ON = 2
POWER_OFF = 4


class JmriError(Exception):
    """JMRI is unreachable or returned an unusable response."""


def _unwrap(obj: Any) -> Any:
    """Strip the JMRI message envelope {"type": ..., "data": {...}} if present."""
    if isinstance(obj, dict) and "data" in obj and "type" in obj:
        return obj["data"]
    return obj


async def _get_json(path: str) -> Any:
    url = f"{get_jmri_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise JmriError(f"GET {url} failed: {exc}") from exc


async def _post_json(path: str, body: dict) -> Any:
    url = f"{get_jmri_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise JmriError(f"POST {url} failed: {exc}") from exc


async def get_version() -> str:
    """Return the JMRI version string (e.g. "5.4.0").

    /json/version is unusual: the version is the *key* of the data object
    (e.g. {"5.4.0": "v5"}), not a value under a fixed field name.
    """
    payload = await _get_json("/json/version")
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    data = _unwrap(payload)
    if not isinstance(data, dict) or not data:
        raise JmriError(f"Unexpected /json/version payload: {payload!r}")
    return next(iter(data))


async def get_systems() -> list[dict[str, Any]]:
    """Return every power connection known to JMRI.

    Each entry has at least: name, prefix, state (2=ON, 4=OFF, 0=UNKNOWN,
    8=IDLE) and default (bool).
    """
    payload = await _get_json("/json/power")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError(f"Unexpected /json/power payload: {payload!r}")
    systems = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d power system(s): %s",
                len(systems), [s.get("name") for s in systems])
    return systems


async def set_power(prefix: str, turn_on: bool) -> dict[str, Any]:
    """Set power ON/OFF for one system, then report the observed state.

    The POST response is transient (JMRI/DCC++ re-queries the command
    station and may echo an intermediate state) — this only trusts a
    re-read taken _POST_RECHECK_DELAY seconds after the POST, not the
    POST response itself.
    """
    desired = POWER_ON if turn_on else POWER_OFF
    await _post_json("/json/power", {"state": desired, "prefix": prefix})
    await asyncio.sleep(_POST_RECHECK_DELAY)

    systems = await get_systems()
    matches = [s for s in systems if str(s.get("prefix", "")) == prefix]
    if not matches:
        raise JmriError(f"System with prefix {prefix!r} vanished after POST")
    observed = matches[0]

    confirmed = observed.get("state") == desired
    if not confirmed:
        logger.warning(
            "set_power(%s, %s): requested state=%s but observed state=%s",
            prefix, turn_on, desired, observed.get("state"),
        )
    return {**observed, "confirmed": confirmed}


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
    import unicodedata
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


def resolve_system(
    query: str | None, systems: list[dict[str, Any]]
) -> dict[str, Any]:
    """Match a user-supplied system name against discovered systems.

    Tolerant: case-insensitive, accepts the exact name, the connection
    prefix ("O"), or any unambiguous fragment of the name ("ohara" ->
    "DCC++ Ohara"). None/empty selects the default system.
    """
    if not systems:
        raise JmriError("JMRI reported no power systems")

    if query is None or not query.strip():
        default = next((s for s in systems if s.get("default")), systems[0])
        return default

    q = query.strip().casefold()
    names = [str(s.get("name", "")) for s in systems]

    exact = [s for s in systems if str(s.get("name", "")).casefold() == q]
    if len(exact) == 1:
        return exact[0]

    by_prefix = [s for s in systems if str(s.get("prefix", "")).casefold() == q]
    if len(by_prefix) == 1:
        return by_prefix[0]

    partial = [s for s in systems if q in str(s.get("name", "")).casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(s.get("name")) for s in partial]
        raise JmriError(f"Ambiguous system {query!r}: matches {matches}")

    raise JmriError(f"Unknown system {query!r}. Available: {names}")
