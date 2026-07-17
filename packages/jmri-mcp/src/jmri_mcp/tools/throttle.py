"""Throttle MCP tools: acquire/release_throttle, set_speed, set_speed_ramped, stop, emergency_stop, set_direction, set_function, lights_on, lights_off, set_loco_lights, set_all_locos_lights, prepare_locomotive, park_locomotive, park_all_locomotives.

All keyed on DCC address — see jmri_mcp.tools._common.throttle_id. Talks to
jmri_ws.py's shared, process-wide WebSocket connection (see
jmri_core.jmri_ws.get_ws_client), unlike power.py/roster.py's one-shot HTTP.
set_speed_ramped reuses jmri_ws.ramp.execute_speed_change, the same
ramping state machine cli/throttle.py's `speed`/`stop`/`forward`/`reverse`
subcommands and cli/shell.py's exit-confirmation use — one implementation,
shared by the CLI and the LLM-facing MCP surface.
"""

import asyncio
import logging

from jmri_core import i18n, jmri_client
from jmri_core.constants.client_tuning import (
    EXHIBITION_SPEED_PERCENT,
    RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS,
    RELEASE_FUNCTION_SETTLE_DELAY_SECONDS,
    STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED,
)
from jmri_core.constants.lighting import is_light_label
from jmri_core.jmri_client import resolve_roster_entry
from jmri_core.jmri_ws import JmriError
from jmri_core.jmri_ws import get_ws_client
from jmri_core.jmri_ws.ramp import execute_speed_change
from jmri_mcp.tools._common import (
    check_exhibition_address_allowed,
    compact_throttle,
    direction_name,
    ensure_acquired,
    resolve_prefix,
    resolve_speed_scale,
    resolve_system_field,
    run_in_background,
    throttle_id,
)
from jmri_mcp.tools.mode import is_exhibition_mode

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
                auto-detect from the roster's DccSystem attribute (see
                list_roster's "dcc_system" field), else JMRI's default
                station. Pass explicitly only to override auto-detection.

        You usually do NOT need to call this explicitly before set_speed/
        stop/emergency_stop — those auto-acquire on first use (same
        DccSystem auto-detection) for a smoother voice UX. Call this
        directly when you want a loco's current speed/direction before
        deciding what to do (the reply reports both), or to override the
        detected station via an explicit `prefix`.

        Safe to call again on an address already acquired this session —
        JMRI just re-confirms it, no error or loco reset. Release with
        release_throttle when done, though not required: JMRI releases
        every throttle this session holds if the MCP server disconnects.

        In exhibition mode with an address allowlist configured, an
        address outside it is refused here (and by every other throttle
        tool, routed through this same check) — see enter_exhibition_mode.

        Returns "system": full name of the command station actually used,
        only when non-default — mention it to the user when present.
        """
        client = get_ws_client()
        try:
            check_exhibition_address_allowed(address)
            resolved_prefix = await resolve_prefix(address, prefix)
            data = await client.acquire_throttle(throttle_id(address), address, resolved_prefix)
            system = await resolve_system_field(resolved_prefix)
        except JmriError as exc:
            logger.warning("acquire_throttle(%r, %r) failed: %s", address, prefix, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        result = {"acquired": True, **compact_throttle(data)}
        if system:
            result["system"] = system
        return result

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

        Turns off any still-active function (e.g. lights) first automatically
        — releasing with one on leaves the decoder in an unpredictable state
        (can flip direction). No action needed from you for this.
        """
        client = get_ws_client()
        tid = throttle_id(address)
        try:
            state = client.throttle_state(tid) or {}
            active = [n for n, on in sorted(state.get("functions", {}).items()) if on]
            for n in active:
                await client.set_function(tid, n, False)
            if active:
                # JMRI's ack only confirms the WS message was received, not
                # that the DCC command has reached the decoder yet —
                # releasing right after the ack raced the real command
                # (issue #59, verified live).
                await asyncio.sleep(RELEASE_FUNCTION_SETTLE_DELAY_SECONDS)
            await client.release_throttle(tid)
        except JmriError as exc:
            logger.warning("release_throttle(%r) failed: %s", address, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"released": True, "address": address}

    @mcp.tool()
    async def set_speed(address: int, speed_percent: float, direction: str | None = None) -> dict:
        """Set a locomotive's speed as a percentage of its maximum (0-100%).

        Args:
            address: DCC address. Auto-acquires the throttle if needed.
            speed_percent: 0-100, clamped not rejected.
            direction: Optional "forward"/"reverse" (case-insensitive) — set
                together with speed_percent atomically ("avance à 40%")
                instead of a separate set_direction call. Omit to leave
                direction untouched. Flips instantly; for a ramped flip use
                set_speed_ramped instead.

        Returns actual speed as % of THIS loco's own configured maximum
        (roster "Throttle Speed Limit"), matching PanelPro's slider, not
        the raw decoder ceiling. Includes "direction" only when passed,
        "system" (command-station name) only when non-default.

        Use stop (0%) or emergency_stop (panic) rather than speed_percent=0.
        For a DURATION use set_speed_ramped(hold_seconds=...) — this tool
        is immediate only.

        No-op (no error, no write) if requested speed already matches
        current — JMRI sends no confirmation for a redundant command.

        Exhibition mode overrides speed_percent/direction with a fixed
        moderate forward speed — see enter_exhibition_mode.
        """
        client = get_ws_client()
        if is_exhibition_mode():
            speed_percent = EXHIBITION_SPEED_PERCENT
            direction = "forward"
        speed = max(0.0, min(100.0, speed_percent)) / 100.0
        normalized = None
        try:
            if direction is not None:
                normalized = direction.strip().lower()
                if normalized not in ("forward", "reverse"):
                    raise JmriError("invalid_direction", direction=direction)
            await ensure_acquired(client, address)
            scale = await resolve_speed_scale(address)
            scaled_speed = speed * scale
            if normalized is not None:
                data = await execute_speed_change(
                    client,
                    throttle_id(address),
                    target_forward=(normalized == "forward"),
                    target_fraction=scaled_speed,
                    rampup=0.0,
                    rampdown=0.0,
                    hold_seconds=None,
                )
            else:
                data = await client.set_speed(throttle_id(address), scaled_speed)
        except JmriError as exc:
            logger.warning(
                "set_speed(%r, %r, %r) failed: %s", address, speed_percent, direction, exc
            )
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        result = {"address": address, "speed_percent": data.get("speed", scaled_speed) / scale * 100}
        if normalized is not None:
            result["direction"] = direction_name(data.get("forward", normalized == "forward"))
        state = client.throttle_state(throttle_id(address)) or {}
        system = await resolve_system_field(state.get("prefix"))
        if system:
            result["system"] = system
        return result

    @mcp.tool()
    async def set_speed_ramped(
        address: int,
        speed_percent: float,
        direction: str | None = None,
        rampup_seconds: float = 0.0,
        rampdown_seconds: float = 0.0,
        hold_seconds: float | None = None,
    ) -> dict:
        """Change a locomotive's speed gradually — a smooth ramp up and/or down.

        Args:
            address: DCC address. Auto-acquires the throttle if needed.
            speed_percent: Target speed, 0-100%. Legacy shorthand: NEGATIVE
                toggles direction relative to current facing, ramps to
                |value|%. Prefer explicit direction for new calls — ignored
                as a sign once direction is given (only its clamped 0-100
                magnitude used then).
            direction: Optional "forward"/"reverse" (case-insensitive), set
                atomically with speed_percent, e.g. "avance progressivement
                à 40%" (loco in reverse) -> speed_percent=40,
                direction="forward", rampup_seconds=3. Wins over the
                negative-sign shorthand if both given.
            rampup_seconds: Seconds to climb to the target if higher (or on
                a direction flip while moving). 0 = instant.
            rampdown_seconds: Seconds to descend when lower, on a
                direction-flip stop-first, and for hold_seconds' auto-stop.
                0 = instant.
            hold_seconds: Hold the target this long, then auto-ramp to a
                stop before returning — "run forward at 30% for 10s" ->
                hold_seconds=10. Omit to reach the target and keep going.

        Use instead of plain set_speed for "en douceur"/"progressivement"
        or a duration before stopping. Use emergency_stop for a panic stop
        — never sent here, even at rampdown_seconds=0.

        A SHORT total duration blocks and returns final speed/direction. A
        LONGER one returns immediately with "status": "started" and keeps
        running server-side — the loco stops itself automatically, no
        follow-up call needed. "started" is success, not "finished".

        A direction flip while moving ramps to 0 first, flips, then ramps
        back up.

        speed_percent is relative to THIS loco's configured maximum
        (roster "Throttle Speed Limit") like set_speed.

        Returns final speed/direction, or for the background path:
        {"address", "status": "started", "speed_percent", "direction",
        "seconds_total"}. Either shape includes "system" (full
        command-station name) only when non-default.

        In exhibition mode, speed_percent/direction are IGNORED and
        replaced with a fixed, moderate, forward-only speed.
        """
        client = get_ws_client()
        if is_exhibition_mode():
            speed_percent = EXHIBITION_SPEED_PERCENT
            direction = "forward"
        normalized = None
        if direction is not None:
            normalized = direction.strip().lower()
        target_fraction = max(0.0, min(100.0, abs(speed_percent))) / 100.0
        if normalized is not None:
            target_forward = normalized == "forward"
            target_fraction = max(0.0, min(100.0, speed_percent)) / 100.0
        total_seconds = rampup_seconds + rampdown_seconds + (hold_seconds or 0.0)
        try:
            if normalized is not None and normalized not in ("forward", "reverse"):
                raise JmriError("invalid_direction", direction=direction)
            await ensure_acquired(client, address)
            scale = await resolve_speed_scale(address)
            state = client.throttle_state(throttle_id(address)) or {}
            system = await resolve_system_field(state.get("prefix"))
        except JmriError as exc:
            logger.warning(
                "set_speed_ramped(%r, %r, direction=%r, rampup=%r, rampdown=%r, hold=%r) failed: %s",
                address, speed_percent, direction, rampup_seconds, rampdown_seconds, hold_seconds, exc,
            )
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        if normalized is None:
            if speed_percent < 0:
                info = client.throttle_state(throttle_id(address)) or {}
                target_forward = not info.get("forward", True)
            else:
                target_forward = None

        scaled_target_fraction = target_fraction * scale

        if total_seconds > RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS:
            async def _run_ramp() -> None:
                try:
                    await execute_speed_change(
                        client,
                        throttle_id(address),
                        target_forward=target_forward,
                        target_fraction=scaled_target_fraction,
                        rampup=rampup_seconds,
                        rampdown=rampdown_seconds,
                        hold_seconds=hold_seconds,
                    )
                except JmriError as exc:
                    logger.warning(
                        "background set_speed_ramped(%r, %r, direction=%r) failed: %s",
                        address, speed_percent, direction, exc,
                    )

            run_in_background(_run_ramp())
            result = {
                "address": address,
                "status": "started",
                "speed_percent": target_fraction * 100,
                "direction": direction_name(target_forward),
                "seconds_total": total_seconds,
            }
            if system:
                result["system"] = system
            return result

        try:
            data = await execute_speed_change(
                client,
                throttle_id(address),
                target_forward=target_forward,
                target_fraction=scaled_target_fraction,
                rampup=rampup_seconds,
                rampdown=rampdown_seconds,
                hold_seconds=hold_seconds,
            )
        except JmriError as exc:
            logger.warning(
                "set_speed_ramped(%r, %r, direction=%r, rampup=%r, rampdown=%r, hold=%r) failed: %s",
                address, speed_percent, direction, rampup_seconds, rampdown_seconds, hold_seconds, exc,
            )
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        result = {
            "address": address,
            "speed_percent": (data.get("speed") or 0.0) / scale * 100,
            "direction": direction_name(data.get("forward")),
        }
        if system:
            result["system"] = system
        return result

    @mcp.tool()
    async def stop(address: int) -> dict:
        """Bring a locomotive to a controlled stop (speed 0%), like releasing the throttle.

        Args:
            address: DCC address. Auto-acquires the throttle if needed.

        For a panic/safety stop (derailment risk, collision course, "stop
        it NOW") use emergency_stop instead — a distinct decoder command
        (immediate motor power cut), not just "speed 0". Use this `stop`
        for a normal, intentional halt (end of run, waiting at a signal).

        Safe to call repeatedly, even when already stopped: JMRI silently
        ignores a redundant request, and a local speed cache (kept fresh
        by JMRI's own broadcasts from ANY client) still returns the
        correct current speed_percent without hanging.
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
            address: DCC address. Auto-acquires the throttle if needed.

        Use ONLY for safety-critical stops: derailment risk, imminent
        collision, or any situation needing an immediate halt rather than
        smooth deceleration. This is JMRI's actual decoder e-stop (speed
        -1.0 on the wire, distinct from a normal speed command) — cuts
        power abruptly, rougher on the mechanism, so don't use as a
        synonym for routine `stop`.

        Returns `stopped: true` once confirmed. Safe to call repeatedly:
        a redundant e-stop is a silent no-op on JMRI's side, and a local
        cache (kept fresh from JMRI's broadcasts from any client) reports
        correct status instead of hanging.
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

        No arguments — panic button for "stop everything NOW" (derailment,
        collision risk, no time to name individual locomotives). Call for
        "stop everything"/"stop all trains"/"arrête tout"/"arrête toutes
        les locos" — stop MOTION generically, no locomotive named. Sends
        the same decoder e-stop as emergency_stop(address) to every
        address this session has acquired.

        NOT "cut the power"/"coupe le courant"/"coupe tout" — that means
        power_off_all (real power cut to every DCC system, reaching
        locomotives regardless of who's driving them). This only sends a
        throttle command, never touches track power.

        LIMITATION: only reaches locomotives THIS session has acquired. A
        locomotive driven only from a JMRI panel or another session is NOT
        stopped, since only the connection holding a throttle can command
        it. For a guarantee covering everything regardless of driver, use
        power_off_all instead.

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
            address: DCC address. Auto-acquires the throttle if needed.
            direction: Exactly "forward" or "reverse" (case-insensitive) —
                the decoder's own front/back, not compass direction. For
                "turn it around"/"go the other way", flip the current
                reported direction rather than guessing.

        Best practice: stop a moving loco first — a direction change at
        speed can jolt or be ignored depending on the decoder; this tool
        doesn't enforce that, just forwards the request.

        Returns direction as "forward"/"reverse" (translated from JMRI's
        true/false) — independent of speed, never changed here.

        Safe to call repeatedly with the same direction: JMRI silently
        no-ops a redundant request, and a local cache (kept fresh by
        JMRI's own broadcasts from ANY client) avoids hanging on a repeat
        or externally-set direction.

        In exhibition mode, "reverse" is REFUSED outright (returns an
        error, does not silently force forward — there's no speed change
        here to narrate as "moving anyway") — "forward" still works
        normally. See enter_exhibition_mode.
        """
        client = get_ws_client()
        normalized = direction.strip().lower()
        try:
            if normalized not in ("forward", "reverse"):
                raise JmriError("invalid_direction", direction=direction)
            if normalized == "reverse" and is_exhibition_mode():
                raise JmriError("exhibition_reverse_restricted")
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
            address: DCC address. Auto-acquires the throttle if needed.
            function: 0-28 inclusive (validated locally; out-of-range
                returns an error without contacting JMRI). What each number
                controls is decoder/roster-specific — F0 is almost always
                headlight(s) (see lights_on/lights_off), F1-F28 vary loco
                to loco (bell, horn, sounds, couplers...). If the user
                names a function by effect ("turn on the bell", "rear
                lights") rather than a number, call
                get_locomotive_functions(name) FIRST to check for a
                user-set label before guessing or asking — only ask for
                the F-number if no label matches.
            state: True to turn the function on, False to turn it off.

        Safe to call repeatedly with the same state: JMRI silently no-ops
        a redundant request, and a local per-function cache (kept fresh by
        JMRI's own broadcasts from ANY client holding this address) avoids
        hanging on a repeat or externally-toggled function.
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
            address: DCC address. Auto-acquires the throttle if needed.
            state: True to turn every light-related function on, False off.

        Different from lights_on/lights_off (F0 only). Reads the roster
        function LABELS (set by the user in JMRI's roster editor — see
        get_locomotive_functions) and switches every function whose label
        names a light: "light"/"lamp"/"headlight" (EN) or "lumière"/"feu"/
        "lampe"/"phare" (FR), case/accent-insensitive. Example: Autorail
        has F0="Lumières avant", F1="Lumières cabine", F2="Lumières
        arrières" — all three light-labeled, so "all lights" must flip all
        three, not just F0. Use for "all"/"every"/"toutes les lumières"
        with a named locomotive — never loop set_function yourself.

        No light-labeled functions is NOT an error: returns an empty
        "applied" list with a "note". Only ask for an explicit F-number as
        a fallback then.

        For "all locos" (no locomotive named), use set_all_locos_lights.
        For layout/scenery lighting (JMRI Light objects), use
        set_layout_lights instead.

        Returns {"address", "applied": [{"function", "label", "state"}...],
        "failed": [...]} — catch-and-continue per function.
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

        Call for "turn on/off all the lights of all the locos"/"allume/
        éteins toutes les lumières de toutes les locos" — locomotives in
        bulk, no single one named. Never loop set_loco_lights/set_function
        yourself — this loops server-side in one call, over every
        locomotive this session has acquired.

        Same scope limitation as emergency_stop_all: only reaches
        locomotives THIS session has acquired a throttle for. A
        locomotive driven only from a JMRI panel or another session is
        untouched. Nothing acquired yet returns {"locomotives": []}, not
        an error.

        For ONE named locomotive use set_loco_lights. For layout/scenery
        lighting (JMRI Light objects, no locomotive involved), use
        set_layout_lights instead — never this tool.

        Returns {"locomotives": [<one set_loco_lights result per
        address>]} — attempted independently, one failure doesn't block
        the others.
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

    @mcp.tool()
    async def prepare_locomotive(address: int, prefix: str | None = None) -> dict:
        """Prepare ONE locomotive for a session: acquire, face forward, lights on.

        Args:
            address: The locomotive's DCC address.
            prefix: Optional command station prefix (e.g. "O", "Z", "R"),
                passed straight through to acquire_throttle — including its
                DccSystem roster auto-detection when omitted.

        Use for "prépare la loco"/"prepare the 3"/"get the autorail ready"
        — counterpart to park_locomotive, beginning a session rather than
        a normal "go" mid-run.

        NOT `stop`/`emergency_stop` (speed only, active session) and NOT
        `set_power` (DCC station power, JMRI-wide). Only touches this
        locomotive's session state (throttle + lights), never power or
        speed/motion.

        Three steps, one call: (1) acquire the throttle (safe if already
        held); (2) set direction forward (session-start convention,
        matching park_locomotive's end-of-session state); (3) turn on
        every light-related function, same as set_loco_lights(address, True).

        Does NOT set a speed. Follow with set_speed/set_speed_ramped if
        the user also asked it to move.

        Never call acquire_throttle, set_direction, and set_loco_lights
        yourself in sequence for a "prepare" request — use this tool.

        Returns {"address", "acquired": bool, "direction": "forward",
        "lights": <set_loco_lights result>}.
        """
        client = get_ws_client()
        try:
            resolved_prefix = await resolve_prefix(address, prefix)
            data = await client.acquire_throttle(throttle_id(address), address, resolved_prefix)
        except JmriError as exc:
            logger.warning("prepare_locomotive(%r, %r) acquire step failed: %s", address, prefix, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        if not data.get("forward", True):
            try:
                await client.set_direction(throttle_id(address), True)
            except JmriError as exc:
                logger.warning("prepare_locomotive(%r) direction step failed: %s", address, exc)

        lights_result = await set_loco_lights(address, True)

        return {
            "address": address,
            "acquired": True,
            "direction": "forward",
            "lights": lights_result,
        }

    @mcp.tool()
    async def park_locomotive(address: int) -> dict:
        """Put ONE locomotive to rest for the session: smooth stop, forward, lights off, throttle released.

        Args:
            address: The locomotive's DCC address.

        Use for "éteins la loco"/"coupe les moteurs"/"put the 3 to bed"/
        "park the autorail"/"shut down the autorail" — end-of-session
        shutdown for one locomotive, not a mid-run pause (use `stop`).

        NOT `stop`/`emergency_stop` (speed only, throttle stays acquired,
        lights untouched) and NOT `set_power` (DCC station's own power,
        JMRI-wide). This tool only touches this one locomotive's session
        state (speed + lights + release), never system power.

        Four steps, one call: (1) ramp down to 0, duration scaled to
        current speed (up to ~3s at full speed, shorter/none if already
        slow); (2) flip to forward if in reverse (safe, since speed is 0
        by now); (3) turn off every light-related function, same as
        set_loco_lights(address, False); (4) release the throttle.

        If never acquired, steps 1-2 are skipped, but step 3 still
        auto-acquires (like set_loco_lights always does) so step 4 always
        has something to release.

        Never call set_speed/stop, set_direction, set_loco_lights, and
        release_throttle yourself in sequence for a shutdown request — use
        this tool.

        Returns {"address", "stopped": bool, "direction": "forward",
        "lights": <set_loco_lights result>, "released": bool}.
        """
        client = get_ws_client()
        tid = throttle_id(address)
        was_acquired = tid in client._throttles

        stopped = True
        if was_acquired:
            info = client.throttle_state(tid) or {}
            current_fraction = info.get("speed") or 0.0
            rampdown = current_fraction * STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED
            try:
                await execute_speed_change(
                    client,
                    tid,
                    target_forward=True,
                    target_fraction=0.0,
                    rampup=0.0,
                    rampdown=rampdown,
                    hold_seconds=None,
                )
            except JmriError as exc:
                logger.warning("park_locomotive(%r) stop step failed: %s", address, exc)
                stopped = False

        lights_result = await set_loco_lights(address, False)

        # Verified live against real JMRI: releasing a throttle while ANY
        # function is still active (not just labeled lights, above) leaves
        # the decoder in an unpredictable state, observed as a flipped
        # direction on the physical loco. Turn off whatever the cache still
        # shows as on, regardless of label, right before release.
        state = client.throttle_state(tid) or {}
        active = [n for n, on in sorted(state.get("functions", {}).items()) if on]
        for n in active:
            try:
                await client.set_function(tid, n, False)
            except JmriError as exc:
                logger.warning("park_locomotive(%r) function F%d cleanup failed: %s", address, n, exc)

        if active:
            # JMRI's ack only confirms the WS message was received, not
            # that the DCC command has reached the decoder yet — releasing
            # right after the ack raced the real command (issue #59,
            # verified live).
            await asyncio.sleep(RELEASE_FUNCTION_SETTLE_DELAY_SECONDS)

        released = True
        release_error = None
        try:
            await client.release_throttle(tid)
        except JmriError as exc:
            logger.warning("park_locomotive(%r) release step failed: %s", address, exc)
            released = False
            release_error = i18n.t(f"errors.{exc.code}", **exc.kwargs)

        out = {
            "address": address,
            "stopped": stopped,
            "direction": "forward",
            "lights": lights_result,
            "released": released,
        }
        if "error" in lights_result and not released:
            out["error"] = release_error or lights_result["error"]
        return out

    @mcp.tool()
    async def park_all_locomotives() -> dict:
        """Put EVERY currently-acquired locomotive to rest at once: smooth stop, forward, lights off, released.

        Call for "éteins toutes les locos"/"coupe tous les moteurs"/"shut
        down every locomotive"/"put everything to bed" — the bulk
        counterpart to park_locomotive. Never loop park_locomotive
        yourself — this loops server-side in one call, running the same
        four-step sequence (proportional rampdown, face forward, lights
        off, release) independently per locomotive.

        NOT `emergency_stop_all` (motion-only, no lights/release) and NOT
        system power off (cuts every locomotive on a DCC system regardless
        of driver — no single "power off everything" tool exists, see
        set_power per system). Only touches locomotives THIS session has a
        throttle for — one driven only from a JMRI panel or another
        session is untouched; nothing acquired yet returns
        {"locomotives": []}, not an error.

        For ONE named locomotive use park_locomotive. For motion-only with
        no lights/release, use emergency_stop_all.

        Returns {"locomotives": [<one park_locomotive result per
        address>]} — each stopped independently, one failure doesn't
        block the others.
        """
        client = get_ws_client()
        addresses = sorted({
            info["address"]
            for info in client.all_throttle_states().values()
            if info.get("address") is not None
        })
        if not addresses:
            return {"locomotives": []}
        return {"locomotives": [await park_locomotive(a) for a in addresses]}
