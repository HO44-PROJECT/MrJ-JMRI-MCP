"""Read-only power tools exposed to the LLM."""

import logging

from jmri_mcp.jmri_client import JmriError, get_systems, resolve_system

logger = logging.getLogger("jmri_mcp.tools")

_STATE_NAMES = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}


def _compact(system: dict) -> dict:
    return {
        "name": system.get("name"),
        "state": _STATE_NAMES.get(system.get("state"), "UNKNOWN"),
        "default": bool(system.get("default")),
    }


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
