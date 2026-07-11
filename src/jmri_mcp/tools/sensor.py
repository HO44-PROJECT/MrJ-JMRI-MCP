"""Sensor MCP tools: list_sensors, get_sensor.

Talks to jmri_client.py (one-shot HTTP), same as power.py/light.py. Sensors
are read-only — they report real-world state JMRI detects (block occupancy,
turnout motor feedback, a clock-running flag, ...), so there is no
set_sensor tool; nothing in this project should write to one directly.
"""

import logging

from jmri_mcp import i18n
from jmri_mcp.jmri_client import JmriError, get_sensors, resolve_sensor
from jmri_mcp.tools._common import compact_sensor

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_sensors() -> dict:
        """List every sensor known to JMRI, with its current ACTIVE/INACTIVE state.

        Sensors report real-world state detected by JMRI's own hardware
        inputs — most commonly block occupancy ("is a train on block X?"),
        but also things like turnout motor feedback or a clock-running
        flag. Read-only, no side effects. Use this to discover what
        sensors exist before calling get_sensor, or to answer "what
        sensors are there?"/"is anything occupied right now?".
        """
        try:
            sensors = await get_sensors()
        except JmriError as exc:
            logger.warning("list_sensors failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"sensors": [compact_sensor(s) for s in sensors]}

    @mcp.tool()
    async def get_sensor(name: str) -> dict:
        """Get the current ACTIVE/INACTIVE state of one sensor.

        Args:
            name: Sensor name (JMRI system name like "RS22", or its
                user-friendly label like "Montagne B") or an unambiguous
                fragment of the label. Case-insensitive.

        Use this to answer "is block X occupied?" or similar real-world
        state questions ("is the clock running?" for the ISCLOCKRUNNING
        sensor JMRI always has). Read-only — there is no set_sensor tool,
        since a sensor reflects hardware JMRI detects, not a command this
        project should issue. No side effects.
        """
        try:
            sensors = await get_sensors()
            match = resolve_sensor(name, sensors)
        except JmriError as exc:
            logger.warning("get_sensor(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return compact_sensor(match)
