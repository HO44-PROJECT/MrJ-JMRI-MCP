"""FastMCP stdio entry point.

stdout is reserved for the MCP JSON-RPC channel: all logging goes to stderr.
Never use print() anywhere in this package.
"""

import logging
import sys

from mcp.server.fastmcp import FastMCP

from jmri_mcp import __version__
from jmri_mcp.config import get_jmri_url
from jmri_mcp import tools

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("jmri_mcp")

mcp = FastMCP("JMRI")
tools.register(mcp)


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
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
