"""Throttle MCP tools: acquire/release_throttle, set_speed, set_speed_ramped, stop, emergency_stop, set_direction, set_function, lights_on, lights_off.

All keyed on DCC address — see jmri_mcp.tools._common.throttle_id. Talks to
jmri_ws.py's shared, process-wide WebSocket connection (see
jmri_core.jmri_ws.get_ws_client), unlike power.py/roster.py's one-shot HTTP.
set_speed_ramped reuses jmri_ws.ramp.execute_speed_change, the same
ramping state machine cli/throttle.py's `speed`/`stop`/`forward`/`reverse`
subcommands and cli/shell.py's exit-confirmation use — one implementation,
shared by the CLI and the LLM-facing MCP surface.
"""

import logging

from jmri_core import i18n, jmri_client
from jmri_core.constants.client_tuning import RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS
from jmri_core.constants.lighting import is_light_label
from jmri_core.jmri_client import resolve_roster_entry
from jmri_core.jmri_ws import JmriError
from jmri_core.jmri_ws import get_ws_client
from jmri_core.jmri_ws.ramp import execute_speed_change
from jmri_mcp.tools._common import (
    compact_throttle,
    direction_name,
    ensure_acquired,
    run_in_background,
    throttle_id,
)

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

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
            data = await client.acquire_throttle(throttle_id(address), address, prefix)
        except JmriError as exc:
            logger.warning("acquire_throttle(%r, %r) failed: %s", address, prefix, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"acquired": True, **compact_throttle(data)}

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
            await client.release_throttle(throttle_id(address))
        except JmriError as exc:
            logger.warning("release_throttle(%r) failed: %s", address, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
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

        If the request names a DURATION ("for 10 seconds", "pendant 10
        secondes"), do NOT use this tool followed by a separately-timed
        stop call — use set_speed_ramped(hold_seconds=...) instead, which
        waits and auto-stops server-side in one call. This tool is only
        for an immediate, duration-less speed change.

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
            await ensure_acquired(client, address)
            data = await client.set_speed(throttle_id(address), speed)
        except JmriError as exc:
            logger.warning("set_speed(%r, %r) failed: %s", address, speed_percent, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"address": address, "speed_percent": data.get("speed", speed) * 100}

    @mcp.tool()
    async def set_speed_ramped(
        address: int,
        speed_percent: float,
        rampup_seconds: float = 0.0,
        rampdown_seconds: float = 0.0,
        hold_seconds: float | None = None,
    ) -> dict:
        """Change a locomotive's speed gradually instead of instantly — a smooth ramp up and/or down.

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.
            speed_percent: Target speed, 0-100% of maximum. As CLI-only
                shorthand, a NEGATIVE value means "reverse at |value|%" and
                flips direction as part of the same ramp (e.g. -30 means
                direction=reverse, speed=30%) — this is resolved entirely
                here and is unrelated to emergency_stop's real decoder
                e-stop command, which this tool never sends.
            rampup_seconds: How long to spend climbing from the current
                speed up to the target, if the target is higher (or a
                direction flip is needed while moving — see below). 0 (the
                default) means jump straight to the target instantly, same
                as plain set_speed.
            rampdown_seconds: How long to spend descending, whenever the
                target is lower than the current speed, when a direction
                flip requires slowing to 0 first, and (if hold_seconds is
                given) for the automatic stop at the end of the hold. 0 (the
                default) means an instant drop/stop.
            hold_seconds: If given, hold the target speed for this many
                seconds and then AUTOMATICALLY RAMP BACK TO A STOP (using
                rampdown_seconds) before this tool returns — use this for
                requests like "run forward at 30% for 10 seconds". Omit
                (the default, None) to just reach the target and keep going
                indefinitely, like plain set_speed but ramped.

                YOU DO NOT NEED TO TRACK OR MEASURE THIS DURATION YOURSELF.
                Just pass through the number of seconds the user asked for
                (e.g. "pendant 10 secondes" -> hold_seconds=10) — this MCP
                server does the actual waiting internally on the JMRI
                connection, not you. Never refuse or say you "can't track
                time" for this parameter; it's a plain number, not
                something you have to count yourself.

        Use this instead of plain set_speed whenever the user asks for
        smoothness/gentleness ("en douceur", "progressivement", "ramp up/
        down") or gives a explicit duration to run at a speed before
        stopping ("pendant 10 secondes", "for 10 seconds"). Use plain
        set_speed for an immediate, unqualified speed change, and
        emergency_stop for any panic/safety stop — this tool never sends
        JMRI's real -1.0 e-stop sentinel, even at rampdown_seconds=0.

        NOTE on response timing: for a SHORT total duration (rampup +
        hold_seconds + rampdown), this call blocks until it's all finished
        and returns the real final speed/direction, same as set_speed. For
        a LONGER total duration, this tool instead returns right away with
        "status": "started" once the ramp has been kicked off, and the
        ramp/hold/auto-stop keep running server-side on JMRI's already-open
        connection after your response — the loco WILL still stop itself
        automatically at the end, you do not need (and should not attempt)
        a follow-up call to check on or stop it. This split exists because
        a voice/chat turn that just sits silent for many seconds waiting on
        one tool call can trip the CLIENT's own turn timeout even though
        the ramp is working correctly — do not interpret "status": "started"
        as a failure or as needing a retry. Tell the user the action has
        begun (and for how long/what target), not that it already finished.

        If a direction flip is needed while the locomotive is already
        moving, this ramps down to 0 first (over rampdown_seconds), flips
        direction, then ramps back up to the requested speed (over
        rampup_seconds) — never flips direction while still rolling.

        Returns the actual speed/direction JMRI reports back after the
        ramp (and the auto-stop, if hold_seconds was given) completes, the
        same shape as set_speed/set_direction's combined fields — or, for
        the long-duration background path, {"address", "status": "started",
        "speed_percent" (the target), "direction", "seconds_total"}.
        """
        client = get_ws_client()
        target_forward = False if speed_percent < 0 else None
        target_fraction = max(0.0, min(100.0, abs(speed_percent))) / 100.0
        total_seconds = rampup_seconds + rampdown_seconds + (hold_seconds or 0.0)
        try:
            await ensure_acquired(client, address)
        except JmriError as exc:
            logger.warning(
                "set_speed_ramped(%r, %r, rampup=%r, rampdown=%r, hold=%r) failed: %s",
                address, speed_percent, rampup_seconds, rampdown_seconds, hold_seconds, exc,
            )
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        if total_seconds > RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS:
            async def _run_ramp() -> None:
                try:
                    await execute_speed_change(
                        client,
                        throttle_id(address),
                        target_forward=target_forward,
                        target_fraction=target_fraction,
                        rampup=rampup_seconds,
                        rampdown=rampdown_seconds,
                        hold_seconds=hold_seconds,
                    )
                except JmriError as exc:
                    logger.warning(
                        "background set_speed_ramped(%r, %r) failed: %s",
                        address, speed_percent, exc,
                    )

            run_in_background(_run_ramp())
            return {
                "address": address,
                "status": "started",
                "speed_percent": abs(speed_percent),
                "direction": "reverse" if target_forward is False else None,
                "seconds_total": total_seconds,
            }

        try:
            data = await execute_speed_change(
                client,
                throttle_id(address),
                target_forward=target_forward,
                target_fraction=target_fraction,
                rampup=rampup_seconds,
                rampdown=rampdown_seconds,
                hold_seconds=hold_seconds,
            )
        except JmriError as exc:
            logger.warning(
                "set_speed_ramped(%r, %r, rampup=%r, rampdown=%r, hold=%r) failed: %s",
                address, speed_percent, rampup_seconds, rampdown_seconds, hold_seconds, exc,
            )
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {
            "address": address,
            "speed_percent": (data.get("speed") or 0.0) * 100,
            "direction": direction_name(data.get("forward")),
        }

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
            await ensure_acquired(client, address)
            data = await client.set_speed(throttle_id(address), 0.0)
        except JmriError as exc:
            logger.warning("stop(%r) failed: %s", address, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
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
            await ensure_acquired(client, address)
            data = await client.set_speed(throttle_id(address), -1.0)
        except JmriError as exc:
            logger.warning("emergency_stop(%r) failed: %s", address, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"address": address, "stopped": data.get("speed") == -1.0}

    @mcp.tool()
    async def emergency_stop_all() -> dict:
        """Emergency-stop EVERY locomotive currently under this session's control at once.

        No arguments — this is the panic button for "stop everything NOW"
        (derailment, collision risk, or any situation where you can't take
        the time to name individual locomotives). Call this for phrases
        like "stop everything", "stop all trains", "arrête tout",
        "arrête toutes les locos" — any request to stop MOTION generically,
        without a specific locomotive named. Sends the same decoder e-stop
        as emergency_stop(address) to every address this session has
        acquired (via acquire_throttle or any prior set_speed/stop/
        emergency_stop/set_direction/set_function call), not just one.

        Do NOT use this for "cut the power"/"coupe le courant"/"kill the
        power"/"coupe tout" — those mean power_off_all instead (a real
        power cut to every DCC system, reaching locomotives regardless of
        who's driving them). This tool only sends a throttle command, never
        touches track power, and only reaches locomotives already acquired
        by this session — see the limitation below.

        IMPORTANT LIMITATION: this only reaches locomotives THIS MCP
        session has acquired a throttle for. A locomotive being driven only
        from a JMRI panel, PanelPro, or another MCP/voice session — never
        acquired here — is NOT stopped by this call, because JMRI has no
        "stop every throttle in the whole system" command; only the
        connection holding a throttle can command it. If you need to
        guarantee everything on the layout stops regardless of who's
        driving it, use power_off_all to cut power to every DCC system
        instead — that's the only real "stop absolutely everything" tool.

        Returns {"stopped": [...addresses e-stopped...], "failed": [...]}.
        An address with no error is confirmed at emergency-stop speed
        either way (already-stopped locos are a safe no-op, not skipped
        silently without being reported).
        """
        client = get_ws_client()
        result = await client.emergency_stop_all()
        to_address = {tid: info.get("address") for tid, info in client._throttles.items()}
        return {
            "stopped": [to_address.get(tid, tid) for tid in result["stopped"]],
            "failed": [to_address.get(tid, tid) for tid in result["failed"]],
        }

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
        try:
            if normalized not in ("forward", "reverse"):
                raise JmriError("invalid_direction", direction=direction)
            forward = normalized == "forward"
            await ensure_acquired(client, address)
            data = await client.set_direction(throttle_id(address), forward)
        except JmriError as exc:
            logger.warning("set_direction(%r, %r) failed: %s", address, direction, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"address": address, "direction": direction_name(data.get("forward", forward))}

    @mcp.tool()
    async def set_function(address: int, function: int, state: bool) -> dict:
        """Turn one of a locomotive's decoder functions (F0-F28) on or off.

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.
            function: Function number, 0-28 inclusive (validated; anything
                outside that range returns an error rather than being sent
                to JMRI). What each number actually controls is decoder/
                roster-specific — F0 is almost universally the headlight(s)
                (see lights_on/lights_off below for that common case), but
                F1-F28 vary loco to loco (bell, horn, sound effects,
                couplers, etc.). If a user names a function by effect
                ("turn on the bell", "rear lights") rather than a number,
                call get_locomotive_functions(name) FIRST to check for a
                user-set label before guessing or asking — only fall back
                to asking the user for the F-number if that loco has no
                label matching what they described.
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
        client = get_ws_client()
        try:
            if not (0 <= function <= 28):
                raise JmriError("invalid_function_number", function=function)
            await ensure_acquired(client, address)
            data = await client.set_function(throttle_id(address), function, state)
        except JmriError as exc:
            logger.warning("set_function(%r, %r, %r) failed: %s", address, function, state, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"address": address, "function": function, "state": data.get(f"F{function}", state)}

    @mcp.tool()
    async def lights_on(address: int) -> dict:
        """Turn on a locomotive's headlight(s): shortcut for set_function(address, 0, True).

        F0 is almost universally the headlight function across DCC decoders
        (this is a very strong convention, not a JMRI/protocol guarantee),
        so this is the tool to reach for on a plain "turn the lights on"
        voice request without asking the user for a function number. Same
        auto-acquire and no-op-safe behavior as set_function.

        This is the locomotive's own headlight, NOT layout/scenery lighting
        (depot, street lamps, signals) — for those, use set_light instead.
        """
        return await set_function(address, 0, True)

    @mcp.tool()
    async def lights_off(address: int) -> dict:
        """Turn off a locomotive's headlight(s): shortcut for set_function(address, 0, False).

        See lights_on for why F0. Same auto-acquire and no-op-safe behavior
        as set_function.

        This is the locomotive's own headlight, NOT layout/scenery lighting
        (depot, street lamps, signals) — for those, use set_light instead.
        """
        return await set_function(address, 0, False)

    @mcp.tool()
    async def set_loco_lights(address: int, state: bool) -> dict:
        """Turn ON/OFF EVERY light-related function of ONE locomotive in a single call.

        Args:
            address: The locomotive's DCC address. Acquires the throttle
                automatically if this session doesn't already hold it.
            state: True to turn every light-related function on, False to
                turn them all off.

        Different from lights_on/lights_off, which only ever touch F0. This
        tool reads the locomotive's roster function LABELS (as set by the
        user in JMRI's roster editor — see get_locomotive_functions) and
        switches every function whose label names a light: keywords like
        "light"/"lamp"/"headlight" (English) or "lumière"/"feu"/"lampe"/
        "phare" (French), case- and accent-insensitive. Real example from
        this layout: the Autorail has F0="Lumières avant", F1="Lumières
        cabine", F2="Lumières arrières" — all three are light-labeled, so
        "turn on all the Autorail's lights" must flip all three, not just
        F0. Use THIS tool (not lights_on/lights_off) whenever the request
        says "all"/"every"/"toutes les lumières" together with a named
        locomotive — never loop set_function yourself, this tool already
        does that server-side in one call.

        If the locomotive has no light-labeled functions at all, this is
        NOT an error: it returns an empty "applied" list with a "note"
        explaining why (most locos have no labels set — see
        get_locomotive_functions). Only ask the user for an explicit
        F-number as a fallback in that case.

        For "all locos"/"toutes les locos" (no single locomotive named),
        use set_all_locos_lights instead. For layout/scenery lighting
        (depot, street lamps — JMRI Light objects, not a locomotive's own
        functions), use set_layout_lights instead — never this tool.

        Returns {"address": ..., "applied": [{"function", "label", "state"}...],
        "failed": [...]} — each individual function switch is attempted even
        if another one fails (catch-and-continue), so a single bad function
        doesn't block the rest of the loco's lights.
        """
        try:
            roster = await jmri_client.get_roster()
            entry = resolve_roster_entry(str(address), roster)
            labels = await jmri_client.get_roster_function_labels(entry["name"])
        except JmriError as exc:
            logger.warning("set_loco_lights(%r, %r) failed: %s", address, state, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        light_functions = {n: label for n, label in labels.items() if is_light_label(label)}
        if not light_functions:
            return {
                "address": address,
                "applied": [],
                "failed": [],
                "note": i18n.t("cli.no_light_labeled_functions", name=entry["name"]),
            }

        applied: list[dict] = []
        failed: list[dict] = []
        for n, label in sorted(light_functions.items()):
            result = await set_function(address, n, state)
            if "error" in result:
                failed.append({"function": n, "label": label, "error": result["error"]})
            else:
                applied.append({"function": n, "label": label, "state": state})
        return {"address": address, "applied": applied, "failed": failed}

    @mcp.tool()
    async def set_all_locos_lights(state: bool) -> dict:
        """Turn ON/OFF EVERY light-related function of EVERY currently-acquired locomotive at once.

        Args:
            state: True to turn every light-related function on for every
                locomotive, False to turn them all off.

        Call this for "turn on/off all the lights of all the locos"/"allume/
        éteins toutes les lumières de toutes les locos" — any lighting
        request that mentions locomotives in bulk, with no single one
        named. Never loop set_loco_lights or set_function yourself for a
        request like this — this tool already loops server-side, in one
        call, over every locomotive this session has acquired.

        IMPORTANT LIMITATION: same scope as emergency_stop_all — this only
        reaches locomotives THIS MCP session has acquired a throttle for
        (via acquire_throttle or any prior set_speed/stop/set_function/
        etc. call). A locomotive being driven only from a JMRI panel or
        another session is not touched. If nothing has been acquired yet,
        returns {"locomotives": []}, not an error.

        For a lighting request that names ONE specific locomotive, use
        set_loco_lights instead. For layout/scenery lighting (JMRI Light
        objects — depot, street lamps, no locomotive involved), use
        set_layout_lights instead — never this tool.

        Returns {"locomotives": [<one set_loco_lights result per address>]}
        — each locomotive's lights are attempted independently, so one
        loco's failure doesn't block the others.
        """
        client = get_ws_client()
        addresses = sorted({
            info["address"]
            for info in client.all_throttle_states().values()
            if info.get("address") is not None
        })
        if not addresses:
            return {"locomotives": []}
        return {"locomotives": [await set_loco_lights(a, state) for a in addresses]}
