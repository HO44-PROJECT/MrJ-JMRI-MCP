"""Power/status MCP tools: list_systems, get_power, set_power, power_off_all,
power_on_all, system_status.

Talks to jmri_client.py (one-shot HTTP), same as roster.py.
"""

import logging

from jmri_core import i18n, jmri_client
from jmri_core.jmri_client import JmriError, get_systems, get_version, resolve_system
from jmri_core.jmri_client import power_off_all as _power_off_all
from jmri_core.jmri_client import power_on_all as _power_on_all
from jmri_mcp.tools._common import compact_power
from jmri_mcp.tools.mode import is_exhibition_mode

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_systems() -> dict:
        """List every DCC power system known to JMRI, with its current power state.

        Use this to discover what systems exist before calling get_power, or to
        answer "what systems are there?". No side effects.

        Each system's "name" is JMRI's full connection name, often with a
        parenthetical describing what it's for (e.g. "zou (test)", "raijin
        (tracks)") — the user set these themselves in JMRI. If asked what a
        system is used for, this name is the answer; don't say that
        information isn't available.
        """
        try:
            systems = await get_systems()
        except JmriError as exc:
            logger.warning("list_systems failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"systems": [compact_power(s) for s in systems]}

    @mcp.tool()
    async def get_power(system: str | None = None) -> dict:
        """Get the current power state (ON/OFF/UNKNOWN/IDLE) of one DCC system.

        Args:
            system: System name, prefix, or fragment (e.g. "ohara", "O").
                Case-insensitive. Omit to use JMRI's default system.

        No side effects — this only reads state, it never changes power.

        The returned "name" is JMRI's full connection name, often with a
        parenthetical describing what the system is for (e.g. "zou
        (test)"). If the user asks what a system is used for rather than
        its power state, answer from this name.
        """
        try:
            systems = await get_systems()
            match = resolve_system(system, systems)
        except JmriError as exc:
            logger.warning("get_power(%r) failed: %s", system, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return compact_power(match)

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

        Safe to call repeatedly with the same turn_on value, including
        right after another call already set that state: current state is
        always checked first, and nothing is sent to JMRI if it already
        matches the request. This is not just an optimization — re-POSTing
        a state JMRI already reports is a real JMRI/DCC++ bug that knocks
        the system into UNKNOWN, which is awkward to recover from.

        In exhibition mode, turn_on=True is REFUSED (returns an error,
        power stays off) — turn_on=False (an emergency power cut) always
        still works. See enter_exhibition_mode.
        """
        try:
            if turn_on and is_exhibition_mode():
                raise JmriError("exhibition_power_restricted")
            systems = await get_systems()
            match = resolve_system(system, systems)
            result = await jmri_client.set_power(match["prefix"], turn_on)
        except JmriError as exc:
            logger.warning("set_power(%r, %r) failed: %s", system, turn_on, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {**compact_power(result), "confirmed": result["confirmed"]}

    @mcp.tool()
    async def power_off_all() -> dict:
        """Cut power to EVERY DCC system at once — the real "stop absolutely everything" button.

        No arguments. Call for "cut the power", "cut everything", "kill
        the power", "coupe le courant", "coupe tout", "coupe
        l'alimentation" — any generic power-cut request with no specific
        system named. Use this even when the phrase sounds like a stop
        command — "coupe le courant" means THIS tool, not
        emergency_stop_all, since the user is naming power, not motion.
        For a genuine layout-wide emergency, this reaches every
        locomotive regardless of who's driving it (JMRI panel, PanelPro,
        another session) — unlike emergency_stop_all, which only e-stops
        locomotives THIS session has acquired and never touches power.

        More drastic than emergency_stop_all: also stops anything with no
        throttle acquired, but re-powering afterward requires an explicit
        set_power(system, turn_on=True) per system before any locomotive
        can move again — don't use this for a routine "stop the train",
        only a real emergency.

        Each system's result is re-read and confirmed like set_power —
        check "confirmed" per system rather than assuming the whole
        layout is now unpowered.
        """
        try:
            results = await _power_off_all()
        except JmriError as exc:
            logger.warning("power_off_all failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"systems": [{**compact_power(r), "confirmed": r["confirmed"]} for r in results]}

    @mcp.tool()
    async def power_on_all() -> dict:
        """Restore power to EVERY DCC system at once.

        No arguments. Call this for phrases like "turn everything on",
        "power everything on", "allume tout", "remets le courant" — any
        request to restore/turn on power generically, without a specific
        system named. The inverse of power_off_all — use this after a
        layout-wide power cut (power_off_all, or manually turning systems
        off) to bring every system back to ON in one call, rather than
        naming each system individually with set_power.

        IMPORTANT: restoring power does NOT make locomotives resume their
        previous speed. Every decoder stays stopped until a new speed
        command is sent — this only restores track power, it is not an
        "undo" of power_off_all or emergency_stop_all. Tell the user
        locomotives will need to be started again after calling this.

        Each system's result is re-read and confirmed the same way
        set_power does (see its docstring) — check "confirmed" per system
        rather than assuming the whole layout is now powered.

        In exhibition mode this is REFUSED entirely (returns an error,
        no system is touched) — power_off_all is unaffected. See
        enter_exhibition_mode.
        """
        try:
            if is_exhibition_mode():
                raise JmriError("exhibition_power_restricted")
            results = await _power_on_all()
        except JmriError as exc:
            logger.warning("power_on_all failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"systems": [{**compact_power(r), "confirmed": r["confirmed"]} for r in results]}

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
            status["error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)
            return status

        try:
            systems = await get_systems()
            status["systems"] = [compact_power(s) for s in systems]
        except JmriError as exc:
            status["systems_error"] = i18n.t(f"errors.{exc.code}", **exc.kwargs)

        return status
