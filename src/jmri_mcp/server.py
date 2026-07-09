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

mcp = FastMCP("JMRI")
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


if __name__ == "__main__":
    main()
