"""Power, roster, and throttle tools exposed to the LLM.

Throttle tools (acquire_throttle, release_throttle, set_speed, stop,
emergency_stop, set_direction, set_function, lights_on, lights_off) key
everything on DCC address — see _throttle_id. list_roster is the current
way to discover which address belongs to which named locomotive; it does
not (yet) resolve a name to an address on the tool's behalf.
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

    The LLM identifies a loco by its DCC address (list_roster maps a name
    to one; see #13/#14 for automatic name/function-label resolution) —
    this hides JMRI's separate "throttle" id from callers so tools only
    ever deal in addresses.
    """
    return f"addr{address}"


def _direction_name(forward: bool | None) -> str | None:
    if forward is None:
        return None
    return "forward" if forward else "reverse"


def _compact_throttle(data: dict) -> dict:
    return {
        "address": data.get("address"),
        "speed": data.get("speed"),
        "direction": _direction_name(data.get("forward")),
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
    async def list_roster() -> dict:
        """List every locomotive in JMRI's roster: name, DCC address, road, model.

        Use this to discover what locomotives exist and their DCC addresses
        before calling acquire_throttle/set_speed/etc. — those tools take a
        DCC address, not a name, and this is currently the only way to find
        out which address belongs to which named loco (e.g. the user says
        "start the Autorail" but set_speed needs address=4). road/model can
        be empty strings if the user never filled them in in JMRI — that's
        normal, not an error. No side effects.

        This does NOT yet resolve a name to an address for you automatically
        (that's a future tool) — read the returned list and match the name
        yourself, tolerating case and partial matches the way a human would
        ("autorail" / "Autorail" should both find the "Autorail" entry).
        """
        try:
            roster = await jmri_client.get_roster()
        except JmriError as exc:
            logger.warning("list_roster failed: %s", exc)
            return {"error": str(exc)}
        return {"roster": roster}

    @mcp.tool()
    async def acquire_throttle(address: int, prefix: str | None = None) -> dict:
        """Acquire control of a locomotive by its DCC address, and report its current state.

        Args:
            address: The locomotive's DCC address.
            prefix: Optional command station prefix (e.g. "O", "Z", "R") to
                target when more than one DCC system is connected. Omit to
                use JMRI's default command station.

        You usually do NOT need to call this explicitly before set_speed/
        stop/emergency_stop — those acquire the throttle automatically on
        first use for a smoother voice UX ("speed up the 3" just works).
        Call acquire_throttle directly when you specifically want to know a
        loco's current speed/direction before deciding what to do (the
        acquire reply reports both), or to target a non-default command
        station via `prefix`.

        Safe to call again on an address already acquired by this session —
        JMRI just re-confirms it, it does not error or reset the loco.
        Release with release_throttle when done, though it's not required:
        JMRI releases every throttle this session holds automatically if
        the MCP server disconnects.
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
        """Release this session's control of a locomotive acquired with acquire_throttle.

        Args:
            address: The locomotive's DCC address.

        Good practice once you're done controlling a loco (frees it up for
        other JMRI clients/throttles to acquire without contention), but not
        required for correctness — JMRI releases it automatically when the
        MCP server's connection to JMRI closes, so a missed release_throttle
        does not leave the loco "stuck" for other clients across restarts.
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
        """Set a locomotive's speed as a percentage of its maximum (0-100%).

        Args:
            address: The locomotive's DCC address.
            speed_percent: 0-100. Values outside this range are clamped, not
                rejected. Acquires the throttle automatically if this session
                doesn't already hold it — no need to call acquire_throttle
                first for a simple "speed up the 3" style voice command.

        Returns the actual speed JMRI reports back, as a percentage — this
        may differ slightly from what was requested (DCC uses a small number
        of discrete speed steps, so exact percentages get rounded).

        Use stop for a controlled halt (speed 0%) or emergency_stop for a
        panic stop — don't call set_speed(speed_percent=0) for an emergency,
        it's a different command to JMRI, not just "speed 0".

        A locomotive's speed can be changed by something other than this
        tool at any time — another JMRI panel, PanelPro, another MCP/voice
        session controlling the same loco. If the requested speed already
        matches the current one (whoever set it), JMRI does not send a
        confirmation and this call returns immediately without writing
        anything new to the layout — this is expected, not a failure; the
        reported speed_percent in the response is still accurate because
        it's read from a cache kept continuously up to date by JMRI's own
        state broadcasts, not from what this tool last sent.
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
        """Bring a locomotive to a controlled stop (speed 0%), like releasing the throttle.

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.

        For a panic/safety stop (derailment risk, collision course, or any
        "stop it NOW") use emergency_stop instead — JMRI treats it as a
        distinct decoder command (an immediate power cut to the motor), not
        just "speed 0". Use this `stop` tool for a normal, intentional halt
        (end of a run, waiting at a signal, user just says "stop the 3").

        Safe to call repeatedly, including when the loco is already
        stopped: JMRI silently ignores a redundant "already at this speed"
        request instead of replying, and this tool's client keeps a local
        speed cache continuously refreshed by JMRI's own state broadcasts
        (which fire for ANY client's changes, not just this tool's), so a
        repeat call still returns the correct current speed_percent (very
        likely 0) without hanging or erroring.
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
        """Emergency-stop a locomotive immediately (JMRI's decoder e-stop command).

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.

        Use this ONLY for safety-critical stops: derailment risk, imminent
        collision, or any situation calling for an immediate halt rather than
        a smooth deceleration. This is JMRI's actual decoder emergency-stop
        command (speed -1.0 on the wire, distinct from a normal speed
        command) — it cuts power abruptly rather than ramping down, which is
        rougher on the mechanism/cargo, so don't use it as a synonym for a
        routine `stop`.

        Returns `stopped: true` once JMRI confirms the e-stop speed. Safe to
        call repeatedly: like `stop`, a redundant emergency_stop on an
        already-e-stopped loco is a silent no-op on JMRI's side, and this
        tool's local throttle-state cache (kept fresh from JMRI's broadcasts,
        including e-stops triggered by any OTHER client) reports the correct
        current status instead of hanging.
        """
        client = get_ws_client()
        try:
            await _ensure_acquired(client, address)
            data = await client.set_speed(_throttle_id(address), -1.0)
        except JmriWsError as exc:
            logger.warning("emergency_stop(%r) failed: %s", address, exc)
            return {"error": str(exc)}
        return {"address": address, "stopped": data.get("speed") == -1.0}

    @mcp.tool()
    async def set_direction(address: int, direction: str) -> dict:
        """Set a locomotive's direction of travel: "forward" or "reverse".

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.
            direction: Must be exactly "forward" or "reverse" (case-
                insensitive). "forward"/"reverse" here mean the loco's own
                notion of front/back as wired in its decoder — not compass
                direction or "toward/away from the operator" — so if a user
                says "turn it around" or "go the other way", flip whatever
                the current reported direction is rather than guessing.

        Best practice: for a moving loco, bring it to a stop first — DCC
        decoders generally accept a direction change at speed, but it can
        cause a rough jolt or be ignored/delayed by the decoder depending
        on its configuration; this tool does not enforce that, it just
        forwards the request.

        Returns the direction JMRI actually reports back as "forward" or
        "reverse" (translated from JMRI's own true/false), not "stopped" —
        direction and speed are independent fields on the same throttle, so
        set_direction never changes speed and doesn't report one.

        Like set_speed/stop/emergency_stop, this is safe to call repeatedly
        with the same direction: JMRI silently no-ops a redundant "already
        going this way" request instead of replying, and this tool checks a
        local direction cache — kept fresh by JMRI's own broadcasts of
        state changes from ANY client, not just this one — before deciding
        whether to send anything, so a repeat call (or a direction that was
        actually last changed by a JMRI panel/PanelPro, not this session)
        still reports the correct current direction instead of hanging.
        """
        client = get_ws_client()
        normalized = direction.strip().lower()
        if normalized not in ("forward", "reverse"):
            return {"error": f"direction must be 'forward' or 'reverse', got {direction!r}"}
        forward = normalized == "forward"
        try:
            await _ensure_acquired(client, address)
            data = await client.set_direction(_throttle_id(address), forward)
        except JmriWsError as exc:
            logger.warning("set_direction(%r, %r) failed: %s", address, direction, exc)
            return {"error": str(exc)}
        return {"address": address, "direction": _direction_name(data.get("forward", forward))}

    @mcp.tool()
    async def set_function(address: int, function: int, state: bool) -> dict:
        """Turn one of a locomotive's decoder functions (F0-F28) on or off.

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.
            function: Function number, 0-28 inclusive (validated; anything
                outside that range returns an error rather than being sent
                to JMRI). What each number actually controls is decoder/
                roster-specific and NOT known by this tool — F0 is almost
                universally the headlight(s) (see lights_on/lights_off
                below for that common case), but F1-F28 vary loco to loco
                (bell, horn, sound effects, couplers, etc.) and this project
                has no roster-driven function-name lookup yet. If a user
                names a function by effect ("turn on the bell") rather than
                number and you don't already know the mapping for this
                loco, ask which F-number it is rather than guessing.
            state: True to turn the function on, False to turn it off.

        Safe to call repeatedly with the same state: like set_speed/
        set_direction, JMRI silently no-ops a redundant "already in this
        state" request instead of replying, and this tool checks a local
        per-function cache — kept fresh by JMRI's own broadcasts from ANY
        client holding this address, not just this one — before deciding
        whether to send anything, so a repeat call (or a function last
        toggled by a JMRI panel/PanelPro) still reports the correct current
        state instead of hanging.
        """
        if not (0 <= function <= 28):
            return {"error": f"function must be 0-28, got {function}"}
        client = get_ws_client()
        try:
            await _ensure_acquired(client, address)
            data = await client.set_function(_throttle_id(address), function, state)
        except JmriWsError as exc:
            logger.warning("set_function(%r, %r, %r) failed: %s", address, function, state, exc)
            return {"error": str(exc)}
        return {"address": address, "function": function, "state": data.get(f"F{function}", state)}

    @mcp.tool()
    async def lights_on(address: int) -> dict:
        """Turn on a locomotive's headlight(s): shortcut for set_function(address, 0, True).

        F0 is almost universally the headlight function across DCC decoders
        (this is a very strong convention, not a JMRI/protocol guarantee),
        so this is the tool to reach for on a plain "turn the lights on"
        voice request without asking the user for a function number. Same
        auto-acquire and no-op-safe behavior as set_function.
        """
        return await set_function(address, 0, True)

    @mcp.tool()
    async def lights_off(address: int) -> dict:
        """Turn off a locomotive's headlight(s): shortcut for set_function(address, 0, False).

        See lights_on for why F0. Same auto-acquire and no-op-safe behavior
        as set_function.
        """
        return await set_function(address, 0, False)
