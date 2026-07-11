"""Power-system domain: version, power state discovery, and power on/off.

One-shot async HTTP against JMRI's /json/power and /json/version endpoints
(see jmri_mcp.jmri_client._http for the shared GET/POST plumbing).
"""

import asyncio
import logging
from typing import Any

from jmri_mcp.constants import endpoints
from jmri_mcp.constants.client_tuning import POWER_POST_RECHECK_DELAY_SECONDS
from jmri_mcp.jmri_client._http import JmriError, _get_json, _post_json, _unwrap

logger = logging.getLogger("jmri_mcp.client")

POWER_ON = 2
POWER_OFF = 4


async def get_version() -> str:
    """Return the JMRI version string (e.g. "5.4.0").

    /json/version is unusual: the version is the *key* of the data object
    (e.g. {"5.4.0": "v5"}), not a value under a fixed field name.
    """
    payload = await _get_json(endpoints.VERSION)
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    data = _unwrap(payload)
    if not isinstance(data, dict) or not data:
        raise JmriError(f"Unexpected {endpoints.VERSION} payload: {payload!r}")
    return next(iter(data))


async def get_systems() -> list[dict[str, Any]]:
    """Return every power connection known to JMRI.

    Each entry has at least: name, prefix, state (2=ON, 4=OFF, 0=UNKNOWN,
    8=IDLE) and default (bool).
    """
    payload = await _get_json(endpoints.POWER)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError(f"Unexpected {endpoints.POWER} payload: {payload!r}")
    systems = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d power system(s): %s",
                len(systems), [s.get("name") for s in systems])
    return systems


async def set_power(prefix: str, turn_on: bool) -> dict[str, Any]:
    """Set power ON/OFF for one system, then report the observed state.

    The POST response is transient (JMRI/DCC++ re-queries the command
    station and may echo an intermediate state) — this only trusts a
    re-read taken POWER_POST_RECHECK_DELAY_SECONDS seconds after the POST,
    not the POST response itself.

    Re-POSTing the SAME state JMRI/DCC++ already reports is a known JMRI
    bug, not a safe no-op: it knocks the system into state UNKNOWN, which
    is awkward to recover from (verified by the user against their real
    installation). To avoid ever triggering it, this always re-reads
    current state first and skips the POST entirely if it already matches
    the request — "already ON" and "turn ON" must be indistinguishable
    from the caller's point of view, not just an optimization.
    """
    desired = POWER_ON if turn_on else POWER_OFF

    systems = await get_systems()
    matches = [s for s in systems if str(s.get("prefix", "")) == prefix]
    if not matches:
        raise JmriError(f"Unknown system with prefix {prefix!r}")
    current = matches[0]

    if current.get("state") == desired:
        return {**current, "confirmed": True}

    await _post_json(endpoints.POWER, {"state": desired, "prefix": prefix})
    await asyncio.sleep(POWER_POST_RECHECK_DELAY_SECONDS)

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


async def _set_power_all(turn_on: bool) -> list[dict[str, Any]]:
    """Shared implementation for power_off_all/power_on_all — see their docstrings.

    Discovers every system via get_systems() and calls
    set_power(prefix, turn_on) on each in turn, sequentially not
    concurrently: set_power's own POWER_POST_RECHECK_DELAY_SECONDS re-read already
    serializes each system's own round-trip, and sequential calls avoid
    hammering JMRI/DCC++ with simultaneous POSTs to different command
    stations.

    Returns:
        One compact result per system, in get_systems() order:
        {**observed_system_fields, "confirmed": bool}, same shape as a
        single set_power() call. A system whose prefix vanishes mid-call
        raises JmriError for THAT system only after the ones before it in
        the list have already been posted — callers should treat a raised
        JmriError here as "some systems may already be in the new state,
        check get_systems() to see which."
    """
    systems = await get_systems()
    results = []
    for system in systems:
        results.append(await set_power(system["prefix"], turn_on=turn_on))
    return results


async def power_off_all() -> list[dict[str, Any]]:
    """Cut power to EVERY DCC system JMRI knows about, confirming each by re-read.

    Unlike set_power (one system by prefix), this discovers every system
    and turns each off in turn — the real "stop absolutely everything on
    the layout" primitive, since cutting power stops every locomotive
    regardless of who's driving it (a JMRI panel, PanelPro, another MCP
    session), unlike a throttle e-stop which only reaches locomotives the
    caller's own connection has acquired.
    """
    return await _set_power_all(turn_on=False)


async def power_on_all() -> list[dict[str, Any]]:
    """Restore power to EVERY DCC system JMRI knows about, confirming each by re-read.

    The inverse of power_off_all — discovers every system and turns each
    on in turn. Locomotives do NOT resume their previous speed just
    because power is restored: JMRI's throttle software state (this
    session's own _throttles cache, and any other client's) is untouched
    by a power cycle, so re-powering leaves every decoder stopped until a
    new speed command is sent. This only restores track power, it is not
    an "undo" of power_off_all/emergency_stop_all.
    """
    return await _set_power_all(turn_on=True)


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
