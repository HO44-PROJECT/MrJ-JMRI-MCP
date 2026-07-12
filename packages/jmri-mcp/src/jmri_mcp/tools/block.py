"""Block MCP tools: list_blocks, get_block.

Talks to jmri_client.py (one-shot HTTP), same as sensor.py. Blocks are
read-only — they report real-world occupancy JMRI detects via a linked
sensor (and optionally a reporter/value for RFID-style detection), so
there is no set_block tool; nothing in this project should write to one
directly.
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import JmriError, get_blocks, resolve_block
from jmri_mcp.tools._common import compact_block

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_blocks() -> dict:
        """List every layout block known to JMRI, with its current OCCUPIED/UNOCCUPIED state.

        A block is a named section of track JMRI uses for occupancy
        detection and signaling logic — richer than a plain sensor: each
        block also reports which sensor drives its occupancy, and (on
        layouts with RFID/reporter-based detection, not just simple
        occupancy) a "value" identifying what's occupying it. Also includes
        static layout metadata set in PanelPro's block editor: "length"
        (track length), "curvature", "speed" (a named speed restriction,
        e.g. "Normal"/"Fifty" — vocabulary is layout-defined), and
        "comment" (free text). Read-only, no side effects. Use this to
        discover what blocks exist before calling get_block, or to answer
        "what blocks are there?"/"is anything occupied right now?" at the
        layout-section level (as opposed to a single sensor's raw state).
        """
        try:
            blocks = await get_blocks()
        except JmriError as exc:
            logger.warning("list_blocks failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"blocks": [compact_block(b) for b in blocks]}

    @mcp.tool()
    async def get_block(name: str) -> dict:
        """Get the current OCCUPIED/UNOCCUPIED state of one layout block.

        Args:
            name: Block name (JMRI system name like "IB1", or its
                user-friendly label) or an unambiguous fragment of the
                label. Case-insensitive.

        Use this to answer "is block X occupied?" when the user names a
        layout block/section specifically (as opposed to a raw sensor id —
        if they instead name a sensor directly, use get_sensor). Read-only
        — there is no set_block tool, since a block reflects hardware JMRI
        detects via its linked sensor, not a command this project should
        issue. No side effects.
        """
        try:
            blocks = await get_blocks()
            match = resolve_block(name, blocks)
        except JmriError as exc:
            logger.warning("get_block(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return compact_block(match)
