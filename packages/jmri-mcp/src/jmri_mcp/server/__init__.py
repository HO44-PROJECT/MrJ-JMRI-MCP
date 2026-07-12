"""FastMCP stdio entry point.

stdout is reserved for the MCP JSON-RPC channel: all logging goes to stderr.
Never use print() anywhere in this package.
"""

import asyncio
import logging
import sys

from mcp.server.fastmcp import FastMCP

from jmri_mcp import __version__
from jmri_core.config import get_jmri_url
from jmri_mcp import tools
from jmri_core.jmri_ws import get_ws_client
from jmri_mcp.tools._common import background_tasks

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
    "stop commands. "
    "\n\n"
    "Act, don't recite: if a tool call fails because a name wasn't "
    "recognized (unknown_entity/ambiguous_entity), do not read the tool's "
    "full available-entity list back to the user as your answer — that is "
    "unusable noise in a voice/chat context. Instead ask one short, "
    "specific clarifying question (or state briefly that the name wasn't "
    "recognized), the same way you'd handle any other ambiguous request. "
    "\n\n"
    "Bulk routing: any request naming \"all\"/\"every\"/\"tout(e)(s)\" must "
    "go to the matching whole-layout tool in ONE call — never call a "
    "single-entity tool (set_turnout, set_light, set_function, ...) "
    "repeatedly in a loop yourself, that is far too slow from the user's "
    "perspective and these tools exist specifically so you don't have to. "
    "The whole-layout tools are: power_off_all, power_on_all, "
    "emergency_stop_all, set_all_turnouts (every turnout to the same "
    "CLOSED/THROWN state), set_layout_lights (every JMRI Light — depot/"
    "street/signal lamps — ON/OFF), set_loco_lights (every light-related "
    "function of ONE named locomotive), and set_all_locos_lights (every "
    "light-related function of EVERY currently-acquired locomotive). "
    "\n\n"
    "Loco-lights disambiguation: a lighting request that names a "
    "locomotive (\"toutes les lumières de l'Autorail\", \"all of the 3's "
    "lights\") routes to set_loco_lights (one loco named) or "
    "set_all_locos_lights (\"all locos\"/\"toutes les locos\"). A lighting "
    "request that does NOT mention a locomotive (\"turn on all the "
    "lights\", \"allume toutes les lumières\") routes to set_layout_lights "
    "instead — never guess which one a bare \"lights\" request meant "
    "without checking whether a locomotive was named."
    "\n\n"
    "Duration routing: a speed request that names a DURATION (\"avance "
    "pendant 10 secondes\", \"run forward for 10 seconds\", \"pendant 5s\") "
    "always routes to set_speed_ramped with hold_seconds set to that "
    "number — never plain set_speed, and never a separate stop call timed "
    "yourself. You do not measure or track the duration, just pass the "
    "number through — the server handles the wait AND auto-stop on its own, "
    "including for durations too long to sit through in one voice/chat "
    "turn, where set_speed_ramped returns \"status\": \"started\" right "
    "away instead of waiting for the ramp to finish. That is a normal, "
    "successful acknowledgement, NOT an error or a dropped request — tell "
    "the user the action has begun, don't retry the call, and don't say it "
    "failed or timed out. Plain set_speed is only for a duration-less "
    "speed change (\"speed up the 3\", \"mets la 3 à 40%\")."
)

mcp = FastMCP("JMRI", instructions=_SERVER_INSTRUCTIONS)
tools.register(mcp)


async def _run() -> None:
    try:
        await mcp.run_stdio_async()
    finally:
        # Let any in-flight set_speed_ramped background task (long-duration
        # holds started via tools/_common.run_in_background) finish its
        # ramp/hold/auto-stop before the connection closes underneath it,
        # so a clean shutdown never abandons a locomotive mid-ramp.
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
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
