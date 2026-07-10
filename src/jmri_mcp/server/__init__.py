"""FastMCP stdio entry point.

stdout is reserved for the MCP JSON-RPC channel: all logging goes to stderr.
Never use print() anywhere in this package.
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from jmri_mcp import __version__
from jmri_mcp.config import get_jmri_url
from jmri_mcp import tools
from jmri_mcp.jmri_ws import get_ws_client

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jmri_mcp")

# MCP's `instructions` field (delivered once, in the `initialize` response —
# distinct from `@mcp.prompt()`, which a user must invoke manually) is the
# one server-level channel that reaches the host LLM before any tool is
# called. Used here only for the whole-layout STOP/START tools' voice
# trigger phrases: without this, the LLM has no signal connecting a French
# command with no named target ("arrête tout") to the right tool until it
# has already read that tool's own docstring, which only happens if it
# guesses to look. Respecting `instructions` is still up to the MCP client
# (Claude Desktop, Kira's bridge) — this is not a guaranteed override, just
# the best-effort mechanism the protocol actually provides.
_SERVER_INSTRUCTIONS = (
    "This server controls a DCC model railroad via JMRI. Four tools act on "
    "the WHOLE layout at once, with no address/system argument — route any "
    "command with no specific locomotive/system named to one of these "
    "instead of asking the user to name one: "
    "emergency_stop_all (\"stop everything\", \"arrête tout\" — stops MOTION "
    "only, on throttles this session already holds), "
    "power_off_all (\"cut the power\", \"coupe le courant\", \"coupe tout\" — "
    "cuts POWER to every system, reaching every locomotive regardless of "
    "who's driving it), "
    "power_on_all (\"turn everything on\", \"allume tout\"), "
    "set_executor_mode (\"be concise\", \"mode exécutant\"). "
    "power_off_all and emergency_stop_all are NOT interchangeable: a phrase "
    "naming power/current (\"courant\", \"power\") always means "
    "power_off_all, never emergency_stop_all, even though both sound like "
    "stop commands."
)

mcp = FastMCP("JMRI", instructions=_SERVER_INSTRUCTIONS)
tools.register(mcp)


async def _run() -> None:
    try:
        await mcp.run_stdio_async()
    finally:
        # Release any acquired throttles by closing the WebSocket cleanly —
        # JMRI drops throttles bound to a connection when it closes.
        await get_ws_client().close()


def main() -> None:
    """Run the MCP server on stdio (entry point for the `jmri-mcp` script)."""
    try:
        jmri_url = get_jmri_url()
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    logger.info(
        "JMRI MCP server %s starting (stdio transport, JMRI at %s)",
        __version__,
        jmri_url,
    )
    asyncio.run(_run())
