"""Power/status MCP tools: list_systems, get_power, set_power, system_status.

Talks to jmri_client.py (one-shot HTTP), same as roster.py.
"""

import logging

from jmri_mcp import jmri_client
from jmri_mcp.jmri_client import JmriError, get_systems, get_version, resolve_system
from jmri_mcp.tools._common import compact_power

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
        """
        try:
            systems = await get_systems()
        except JmriError as exc:
            logger.warning("list_systems failed: %s", exc)
            return {"error": str(exc)}
        return {"systems": [compact_power(s) for s in systems]}

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
        """
        try:
            systems = await get_systems()
            match = resolve_system(system, systems)
            result = await jmri_client.set_power(match["prefix"], turn_on)
        except JmriError as exc:
            logger.warning("set_power(%r, %r) failed: %s", system, turn_on, exc)
            return {"error": str(exc)}
        return {**compact_power(result), "confirmed": result["confirmed"]}

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
            status["systems"] = [compact_power(s) for s in systems]
        except JmriError as exc:
            status["systems_error"] = str(exc)

        return status
