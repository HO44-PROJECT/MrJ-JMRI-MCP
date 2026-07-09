"""Power and throttle tools exposed to the LLM.

Throttle tools (acquire_throttle, release_throttle, set_speed, stop,
emergency_stop) key everything on DCC address — see _throttle_id.
"""

import logging

from jmri_mcp import jmri_client
from jmri_mcp.jmri_client import JmriError, get_systems, get_version, resolve_system
from jmri_mcp.jmri_ws import JmriError as JmriWsError
from jmri_mcp.jmri_ws import get_ws_client

logger = logging.getLogger("jmri_mcp.tools")

_STATE_NAMES = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}


def _compact(system: dict) -> dict:
    return {
        "name": system.get("name"),
        "state": _STATE_NAMES.get(system.get("state"), "UNKNOWN"),
        "default": bool(system.get("default")),
    }


def _throttle_id(address: int) -> str:
    """Derive a stable throttle id from a DCC address.

    The LLM identifies a loco by its DCC address alone (no roster yet, see
    M3) — this hides JMRI's separate "throttle" id from callers so tools
    only ever deal in addresses.
    """
    return f"addr{address}"


def _compact_throttle(data: dict) -> dict:
    return {
        "address": data.get("address"),
        "speed": data.get("speed"),
        "forward": data.get("forward"),
    }


async def _ensure_acquired(client, address: int) -> None:
    """Acquire the throttle for `address` if this connection doesn't hold it yet.

    JMRI rejects speed/direction/function commands on a throttle id it has
    never seen an acquire for ("Throttles must be requested with an
    address."). Tracking acquired ids client-side lets set_speed/stop/etc.
    work standalone (voice UX: "speed up the 3" without a separate acquire
    step) while still reusing the same throttle id acquire_throttle uses.
    """
    if _throttle_id(address) not in client._throttles:
        await client.acquire_throttle(_throttle_id(address), address)


def register(mcp) -> None:
    @mcp.tool()
    async def list_systems() -> dict:
        """List every DCC power system known to JMRI, with its current power state.

        Use this to discover what systems exist before calling get_power, or to
        answer "what systems are there?". No side effects.
        """
        try:
            systems = await get_systems()
        except JmriError as exc:
            logger.warning("list_systems failed: %s", exc)
            return {"error": str(exc)}
        return {"systems": [_compact(s) for s in systems]}

    @mcp.tool()
    async def get_power(system: str | None = None) -> dict:
        """Get the current power state (ON/OFF/UNKNOWN/IDLE) of one DCC system.

        Args:
            system: System name, prefix, or fragment (e.g. "ohara", "O").
                Case-insensitive. Omit to use JMRI's default system.

        No side effects — this only reads state, it never changes power.
        """
        try:
            systems = await get_systems()
            match = resolve_system(system, systems)
        except JmriError as exc:
            logger.warning("get_power(%r) failed: %s", system, exc)
            return {"error": str(exc)}
        return _compact(match)

    @mcp.tool()
    async def set_power(system: str | None, turn_on: bool) -> dict:
        """Turn a DCC system's power ON or OFF, and report the state actually observed.

        Args:
            system: System name, prefix, or fragment (e.g. "ohara", "O").
                Case-insensitive. Omit to use JMRI's default system.
            turn_on: True to turn power ON, False to turn it OFF.

        This writes to JMRI. The reported state is re-read ~1s after the
        command (JMRI's immediate POST response is transient/unreliable) —
        if the observed state doesn't match the request, "confirmed" will
        be false and the caller should say so honestly rather than assume
        success.
        """
        try:
            systems = await get_systems()
            match = resolve_system(system, systems)
            result = await jmri_client.set_power(match["prefix"], turn_on)
        except JmriError as exc:
            logger.warning("set_power(%r, %r) failed: %s", system, turn_on, exc)
            return {"error": str(exc)}
        return {**_compact(result), "confirmed": result["confirmed"]}

    @mcp.tool()
    async def system_status() -> dict:
        """One-call diagnostic: is JMRI reachable, and what state is it in?

        Reports JMRI reachability/version and every power system's state.
        Call this first when something isn't responding, instead of
        guessing which tool to retry. No side effects.
        """
        status: dict = {"reachable": False}
        try:
            status["version"] = await get_version()
            status["reachable"] = True
        except JmriError as exc:
            status["error"] = str(exc)
            return status

        try:
            systems = await get_systems()
            status["systems"] = [_compact(s) for s in systems]
        except JmriError as exc:
            status["systems_error"] = str(exc)

        return status

    @mcp.tool()
    async def acquire_throttle(address: int, prefix: str | None = None) -> dict:
        """Acquire control of a locomotive by its DCC address.

        Args:
            address: The locomotive's DCC address.
            prefix: Optional command station prefix (e.g. "O", "Z", "R") to
                target when more than one is connected. Omit to use JMRI's
                default command station.

        Call this before set_speed/set_direction/set_function on a loco you
        haven't controlled yet in this session — safe to call again on an
        address that's already acquired (JMRI just re-confirms it). Release
        with release_throttle when done; JMRI also releases automatically
        if the server disconnects.
        """
        client = get_ws_client()
        try:
            data = await client.acquire_throttle(_throttle_id(address), address, prefix)
        except JmriWsError as exc:
            logger.warning("acquire_throttle(%r, %r) failed: %s", address, prefix, exc)
            return {"error": str(exc)}
        return {"acquired": True, **_compact_throttle(data)}

    @mcp.tool()
    async def release_throttle(address: int) -> dict:
        """Release control of a locomotive acquired with acquire_throttle.

        Args:
            address: The locomotive's DCC address.

        Good practice once done controlling a loco, but not required —
        JMRI releases it automatically when the server disconnects.
        """
        client = get_ws_client()
        try:
            await client.release_throttle(_throttle_id(address))
        except JmriWsError as exc:
            logger.warning("release_throttle(%r) failed: %s", address, exc)
            return {"error": str(exc)}
        return {"released": True, "address": address}

    @mcp.tool()
    async def set_speed(address: int, speed_percent: float) -> dict:
        """Set a locomotive's speed as a percentage of its maximum.

        Args:
            address: The locomotive's DCC address.
            speed_percent: 0-100. Acquires the throttle automatically if not
                already held.

        Use stop for a controlled halt (speed 0) or emergency_stop for a
        panic stop — don't call set_speed(speed_percent=0) for an emergency,
        it's not the same command to JMRI.
        """
        client = get_ws_client()
        speed = max(0.0, min(100.0, speed_percent)) / 100.0
        try:
            await _ensure_acquired(client, address)
            data = await client.set_speed(_throttle_id(address), speed)
        except JmriWsError as exc:
            logger.warning("set_speed(%r, %r) failed: %s", address, speed_percent, exc)
            return {"error": str(exc)}
        return {"address": address, "speed_percent": data.get("speed", speed) * 100}

    @mcp.tool()
    async def stop(address: int) -> dict:
        """Bring a locomotive to a controlled stop (speed 0).

        Args:
            address: The locomotive's DCC address.

        For a panic/safety stop use emergency_stop instead — it's a
        different command to JMRI (decoder emergency stop), not just speed 0.
        """
        client = get_ws_client()
        try:
            await _ensure_acquired(client, address)
            data = await client.set_speed(_throttle_id(address), 0.0)
        except JmriWsError as exc:
            logger.warning("stop(%r) failed: %s", address, exc)
            return {"error": str(exc)}
        return {"address": address, "speed_percent": data.get("speed", 0.0) * 100}

    @mcp.tool()
    async def emergency_stop(address: int) -> dict:
        """Emergency-stop a locomotive immediately (JMRI decoder e-stop).

        Args:
            address: The locomotive's DCC address.

        Use this for safety-critical stops (derailment risk, collision
        course). For a normal controlled stop use stop instead.
        """
        client = get_ws_client()
        try:
            await _ensure_acquired(client, address)
            data = await client.set_speed(_throttle_id(address), -1.0)
        except JmriWsError as exc:
            logger.warning("emergency_stop(%r) failed: %s", address, exc)
            return {"error": str(exc)}
        return {"address": address, "stopped": data.get("speed") == -1.0}
