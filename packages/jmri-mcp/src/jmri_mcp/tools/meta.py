"""Meta MCP tools: layout_status, secure_layout, release_all_locomotives, night_mode, day_mode.

Higher-level tools that combine several low-level operations into one call,
matching how a model railroader would naturally ask an assistant to operate
the layout ("secure the layout", "what's happening?") rather than the
individual JMRI operations that make that up. Each tool here composes
existing jmri_client/jmri_ws calls directly (same low-level functions
power.py/light.py/turnout.py/block.py/sensor.py build their own tools on),
rather than calling another module's @mcp.tool()-decorated function —
FastMCP tools are closures registered on `mcp`, not plain importable
functions, so cross-module reuse happens at the jmri_client/jmri_ws layer,
the same way light.py and turnout.py never import each other.
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import (
    JmriError,
    get_blocks,
    get_lights,
    get_roster_function_labels,
    get_sensors,
    get_systems,
    get_turnouts,
    get_version,
    resolve_roster_entry,
    set_light as _set_light,
)
from jmri_core.jmri_client import get_roster as _get_roster
from jmri_core.constants.lighting import is_light_label
from jmri_core.jmri_ws import JmriError as JmriWsError
from jmri_core.jmri_ws import get_ws_client
from jmri_core.jmri_ws.ramp import execute_speed_change
from jmri_mcp.tools._common import (
    compact_block,
    compact_light,
    compact_power,
    compact_sensor,
    compact_throttle,
    ensure_acquired,
    throttle_id,
)

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def layout_status() -> dict:
        """One-call overview of the whole layout: connectivity, power, active locomotives, blocks, sensors.

        Call for "what's happening on the layout?"/"is everything
        ready?"/"donne-moi l'état du layout" — a broad status question
        with no single named target. Never chain list_systems +
        list_roster + list_blocks + list_sensors yourself, this gathers
        them in one call.

        Different from system_status (reachability + DCC power only):
        this adds every locomotive THIS session holds a throttle for (with
        speed/direction), block occupancy, and sensor states — fuller, at
        the cost of more JMRI calls. Use system_status when only
        reachability/power is in question.

        No side effects. Each section is fetched independently with its
        own "error" key on failure — one section failing doesn't block
        the rest.

        Returns {"reachable", "version", "systems": [...], "locomotives":
        [<compact_throttle per acquired address>], "blocks": [...],
        "sensors": [...]}, with "*_error" keys for any failed section.
        """
        status: dict = {"reachable": False}
        try:
            status["version"] = await get_version()
            status["reachable"] = True
        except JmriError as exc:
            status["error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)
            return status

        try:
            systems = await get_systems()
            status["systems"] = [compact_power(s) for s in systems]
        except JmriError as exc:
            status["systems_error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)

        client = get_ws_client()
        status["locomotives"] = [
            compact_throttle(info) for info in client.all_throttle_states().values()
        ]

        try:
            blocks = await get_blocks()
            status["blocks"] = [compact_block(b) for b in blocks]
        except JmriError as exc:
            status["blocks_error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)

        try:
            sensors = await get_sensors()
            status["sensors"] = [compact_sensor(s) for s in sensors]
        except JmriError as exc:
            status["sensors_error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)

        return status

    @mcp.tool()
    async def release_all_locomotives() -> dict:
        """Release this session's throttle on EVERY currently-acquired locomotive, without changing their state.

        Call for "release all locomotives"/"libère toutes les locos" —
        ending a session or handing off without stopping or altering
        anything. Speed, direction, and lights stay exactly as they are;
        only the throttle (this session's exclusive control) is released,
        freeing each locomotive for other JMRI clients to drive.

        NOT park_all_locomotives (also stops, faces forward, lights off
        before releasing) and NOT emergency_stop_all (stops motion but
        keeps throttles acquired). Use only to let go of control without
        changing current locomotive state — e.g. handing off mid-run.

        Only reaches locomotives THIS session acquired. Nothing acquired
        yet returns {"released": []}, not an error.

        Returns {"released": [{"address", "released": bool}...]} — one
        entry per locomotive, attempted independently so one failure
        doesn't block the rest.
        """
        client = get_ws_client()
        addresses = sorted({
            info["address"]
            for info in client.all_throttle_states().values()
            if info.get("address") is not None
        })
        if not addresses:
            return {"released": []}

        released: list[dict] = []
        for address in addresses:
            try:
                await client.release_throttle(throttle_id(address))
                released.append({"address": address, "released": True})
            except JmriWsError as exc:
                logger.warning("release_all_locomotives address=%r failed: %s", address, exc)
                released.append({
                    "address": address,
                    "released": False,
                    "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                })
        return {"released": released}

    async def _set_loco_lights(address: int, state: bool) -> dict:
        """Same logic and same return shape as throttle.py's set_loco_lights
        (roster-label-driven, not just F0) — reimplemented here rather than
        imported across modules, since it's a closure registered on `mcp`
        in throttle.py, not a plain importable function (see this module's
        docstring). Keep field-for-field identical to throttle.py's version
        (including "label"/"note") so callers see one consistent shape
        regardless of which tool produced it."""
        client = get_ws_client()
        try:
            roster = await _get_roster()
            entry = resolve_roster_entry(str(address), roster)
            labels = await get_roster_function_labels(entry["name"])
        except JmriError as exc:
            return {"address": address, "error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

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
            try:
                await ensure_acquired(client, address)
                await client.set_function(throttle_id(address), n, state)
                applied.append({"function": n, "label": label, "state": state})
            except JmriWsError as exc:
                failed.append({
                    "function": n,
                    "label": label,
                    "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                })
        return {"address": address, "applied": applied, "failed": failed}

    @mcp.tool()
    async def secure_layout(release_throttles: bool = True) -> dict:
        """Put the whole layout into a known safe resting state — the end-of-session "I'm done for today" command.

        Args:
            release_throttles: True (default) to also release every
                locomotive's throttle at the end. False to stop/light-off
                every locomotive but keep throttles acquired.

        Call for "I'm done for today, secure the layout"/"sécurise le
        layout"/"on arrête pour aujourd'hui" — a broad end-of-session
        request naming the layout as a whole, not one locomotive. Never
        chain stop/set_loco_lights/set_layout_lights/release_throttle
        yourself, this runs the full sequence server-side in one call.

        Runs in order: 1) every acquired locomotive smoothly stopped
        (ramped, not abrupt), faced forward, lights off — same as
        park_locomotive, independently per locomotive; 2) every layout
        light (JMRI Light objects) turned off — same as
        set_layout_lights(False); 3) if release_throttles is True
        (default), every throttle released.

        NOT power_off_all (cuts DCC track power itself, unconditionally,
        including locomotives never acquired here — more drastic, never
        touches power) and NOT emergency_stop_all (motion-only, no
        lights/release). Only reaches locomotives THIS session has
        acquired.

        Returns {"locomotives": [<per-locomotive stop/lights/release
        result>...], "layout_lights": <set_layout_lights-shaped result>}.
        """
        client = get_ws_client()
        addresses = sorted({
            info["address"]
            for info in client.all_throttle_states().values()
            if info.get("address") is not None
        })

        locomotives: list[dict] = []
        for address in addresses:
            tid = throttle_id(address)
            info = client.throttle_state(tid) or {}
            current_fraction = info.get("speed") or 0.0
            entry: dict = {"address": address}
            try:
                await execute_speed_change(
                    client,
                    tid,
                    target_forward=True,
                    target_fraction=0.0,
                    rampup=0.0,
                    rampdown=current_fraction * 3.0,
                    hold_seconds=None,
                )
                entry["stopped"] = True
            except JmriWsError as exc:
                logger.warning("secure_layout stop address=%r failed: %s", address, exc)
                entry["stopped"] = False

            entry["lights"] = await _set_loco_lights(address, False)

            if release_throttles:
                try:
                    await client.release_throttle(tid)
                    entry["released"] = True
                except JmriWsError as exc:
                    logger.warning("secure_layout release address=%r failed: %s", address, exc)
                    entry["released"] = False

            locomotives.append(entry)

        try:
            lights = await get_lights()
        except JmriError as exc:
            layout_lights: dict = {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        else:
            succeeded: list[dict] = []
            failed: list[dict] = []
            for lt in lights:
                try:
                    result = await _set_light(lt["name"], False)
                    succeeded.append({**compact_light(result), "confirmed": result["confirmed"]})
                except JmriError as exc:
                    failed.append({
                        "name": lt.get("userName") or lt.get("name"),
                        "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                    })
            layout_lights = {"succeeded": succeeded, "failed": failed}

        return {"locomotives": locomotives, "layout_lights": layout_lights}

    async def _set_mode_lights(loco_state: bool, layout_state: bool) -> dict:
        client = get_ws_client()
        addresses = sorted({
            info["address"]
            for info in client.all_throttle_states().values()
            if info.get("address") is not None
        })
        locomotives = [await _set_loco_lights(a, loco_state) for a in addresses]

        try:
            lights = await get_lights()
        except JmriError as exc:
            layout_lights: dict = {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        else:
            succeeded: list[dict] = []
            failed: list[dict] = []
            for lt in lights:
                try:
                    result = await _set_light(lt["name"], layout_state)
                    succeeded.append({**compact_light(result), "confirmed": result["confirmed"]})
                except JmriError as exc:
                    failed.append({
                        "name": lt.get("userName") or lt.get("name"),
                        "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                    })
            layout_lights = {"succeeded": succeeded, "failed": failed}

        return {"locomotives": locomotives, "layout_lights": layout_lights}

    @mcp.tool()
    async def night_mode() -> dict:
        """Set the layout to night operation mode: turn on every layout light and every locomotive's lights.

        Call for "put the layout in night mode"/"mode nuit"/"il fait
        nuit" — a demonstration-style lighting scene, not a status/power
        command. Turns ON every layout light (JMRI Light objects — same as
        set_layout_lights(True)) and every acquired locomotive's
        light-related functions (same as set_all_locos_lights(True)), in
        one call.

        Does NOT change speed, direction, or throttle acquisition, and
        does NOT affect track power (set_power) or signal aspects
        (set_signal) — lighting only. Inverse is day_mode.

        Visual/demonstration only — does not read or change JMRI's
        internal fast clock.

        Returns {"locomotives": [<per-locomotive set_loco_lights-shaped
        result>...], "layout_lights": <set_layout_lights-shaped result>}.
        """
        return await _set_mode_lights(True, True)

    @mcp.tool()
    async def day_mode() -> dict:
        """Set the layout to daytime operation mode: turn off every layout light and every locomotive's lights.

        Call for "put the layout in day mode"/"mode jour"/"il fait jour"
        — the inverse of night_mode. Turns OFF every layout light (JMRI
        Light objects — same as set_layout_lights(False)) and every
        acquired locomotive's light-related functions (same as
        set_all_locos_lights(False)), in one call.

        Does NOT change speed, direction, or throttle acquisition, and
        does NOT affect track power (set_power) or signal aspects
        (set_signal) — lighting only.

        Returns {"locomotives": [<per-locomotive set_loco_lights-shaped
        result>...], "layout_lights": <set_layout_lights-shaped result>}.
        """
        return await _set_mode_lights(False, False)
