"""Layout light MCP tools: list_lights, get_light, set_light.

Talks to jmri_client.py (one-shot HTTP), same as power.py/roster.py. These
are JMRI `light` objects wired to the layout itself (depot lighting, street
lamps, signal lamps, ...) — NOT a locomotive's F0 headlight function. If the
user names a locomotive ("turn on the Autorail's lights"), use
find_locomotive + set_function/lights_on instead; use these tools only for
lights that are part of the layout/scenery, not a specific loco.
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import JmriError, get_lights, resolve_light
from jmri_core.jmri_client import set_light as _set_light
from jmri_mcp.tools._common import compact_light

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_lights() -> dict:
        """List every layout light known to JMRI, with its current ON/OFF state.

        These are JMRI `light` objects wired to the layout/scenery itself
        (depot lighting, street lamps, signal lamps, ...) — NOT a
        locomotive's headlight (that's F0, via set_function/lights_on on a
        DCC address). Use this to discover what lights exist before calling
        get_light/set_light, or to answer "what lights are there?". No
        side effects.
        """
        try:
            lights = await get_lights()
        except JmriError as exc:
            logger.warning("list_lights failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"lights": [compact_light(lt) for lt in lights]}

    @mcp.tool()
    async def get_light(name: str) -> dict:
        """Get the current ON/OFF state of one layout light.

        Args:
            name: Light name (JMRI system name like "IL1", or its
                user-friendly label like "Depot Lighting") or an
                unambiguous fragment of the label. Case-insensitive.

        This is a layout light (scenery), not a locomotive headlight — for
        "is the Autorail's headlight on", use get_locomotive_functions
        instead. No side effects.
        """
        try:
            lights = await get_lights()
            match = resolve_light(name, lights)
        except JmriError as exc:
            logger.warning("get_light(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return compact_light(match)

    @mcp.tool()
    async def set_light(name: str, turn_on: bool) -> dict:
        """Turn a layout light ON or OFF, and report the state actually observed.

        Args:
            name: Light name (JMRI system name like "IL1", or its
                user-friendly label like "Depot Lighting") or an
                unambiguous fragment of the label. Case-insensitive.
            turn_on: True to turn the light ON, False to turn it OFF.

        This is a layout light (scenery: depot, street, signal lamps, ...),
        distinct from a locomotive's F0 headlight function — if the user
        names a locomotive rather than a place/scene, use set_function or
        lights_on/lights_off on its DCC address instead. This writes to
        JMRI; the reported state is re-read after the command, and
        "confirmed" is honestly reported false if the observed state
        doesn't match what was requested (e.g. a feedback-wired light that
        didn't actually switch).
        """
        try:
            lights = await get_lights()
            match = resolve_light(name, lights)
            result = await _set_light(match["name"], turn_on)
        except JmriError as exc:
            logger.warning("set_light(%r, %r) failed: %s", name, turn_on, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {**compact_light(result), "confirmed": result["confirmed"]}

    @mcp.tool()
    async def set_layout_lights(turn_on: bool) -> dict:
        """Turn EVERY layout light ON or OFF at once (depot, street, signal lamps — JMRI Light objects).

        Args:
            turn_on: True to turn every layout light ON, False to turn
                every layout light OFF.

        These are JMRI `light` objects wired to the layout/scenery itself
        — NOT a locomotive's own headlight/cabin/rear-light functions. Call
        this tool for a lighting request that does NOT name a locomotive
        ("turn on all the lights", "éteins toutes les lumières" with no
        loco mentioned). If the request DOES name a locomotive ("all of
        the Autorail's lights", "toutes les lumières de la loco"), use
        set_loco_lights or set_all_locos_lights instead — never this tool
        for that case, and never this tool's name to guess what a bare
        "lights" request meant if a locomotive was mentioned anywhere in
        it.

        Never loop set_light yourself for a "every light"/"toutes les
        lumières" request — this tool already loops server-side, in one
        call, over every light JMRI reports.

        Returns {"succeeded": [...], "failed": [...]}, each entry shaped
        like set_light's own return value plus a "name". One light failing
        does not stop the rest — every light is attempted independently
        (catch-and-continue).
        """
        try:
            lights = await get_lights()
        except JmriError as exc:
            logger.warning("set_layout_lights(%r) failed: %s", turn_on, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        succeeded: list[dict] = []
        failed: list[dict] = []
        for lt in lights:
            try:
                result = await _set_light(lt["name"], turn_on)
                succeeded.append({**compact_light(result), "confirmed": result["confirmed"]})
            except JmriError as exc:
                failed.append({
                    "name": lt.get("userName") or lt.get("name"),
                    "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                })
        return {"succeeded": succeeded, "failed": failed}
