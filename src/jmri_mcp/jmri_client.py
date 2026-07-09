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
