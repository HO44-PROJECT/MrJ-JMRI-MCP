"""Turnout MCP tools: list_turnouts, get_turnout, set_turnout.

Talks to jmri_client.py (one-shot HTTP), same as power.py/light.py. A
turnout is CLOSED or THROWN — this project uses those two words (not
"open"/"closed" track terminology, which is ambiguous) to match JMRI's own
vocabulary exactly, so the LLM's tool calls and any state it reports back
to the user stay consistent with what JMRI/PanelPro shows.

INCONSISTENT state and has_feedback_sensor: every tool below returns a
"has_feedback_sensor" field (see jmri_mcp.tools._common.compact_turnout).
Verified live (2026-07-11) that a turnout with no wired feedback sensor
can report state=INCONSISTENT indefinitely, at rest, with no command in
flight — this is that turnout's normal steady state, not a fault. Never
report INCONSISTENT as an anomaly/problem to the user when
has_feedback_sensor is false; only treat it as noteworthy when
has_feedback_sensor is true (there, it can mean the motor genuinely
hasn't settled or failed to reach the commanded position).
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import JmriError, get_turnouts, resolve_turnout
from jmri_core.jmri_client import set_turnout as _set_turnout
from jmri_mcp.tools._common import compact_turnout

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_turnouts() -> dict:
        """List every turnout known to JMRI, with its current CLOSED/THROWN state.

        Use this to discover what turnouts exist before calling
        get_turnout/set_turnout, or to answer "what turnouts are there?"/
        "which way is turnout X set?". No side effects.

        Each entry includes "has_feedback_sensor" (bool). When false, that
        turnout has no real position sensor wired up, and a state of
        INCONSISTENT is its normal/expected steady state — not an
        anomaly. Do not flag it to the user as a problem in that case;
        only state="INCONSISTENT" on a turnout where has_feedback_sensor
        is true is worth calling out as possibly unsettled.
        """
        try:
            turnouts = await get_turnouts()
        except JmriError as exc:
            logger.warning("list_turnouts failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"turnouts": [await compact_turnout(t) for t in turnouts]}

    @mcp.tool()
    async def get_turnout(name: str) -> dict:
        """Get the current CLOSED/THROWN state of one turnout.

        Args:
            name: Turnout name (JMRI system name like "IT100", or its
                user-friendly label like "Layout Turnout A") or an
                unambiguous fragment of the label. Case-insensitive.

        No side effects — this only reads state, it never changes the
        turnout.

        The result includes "has_feedback_sensor" (bool). When false, that
        turnout has no real position sensor wired up, and a state of
        INCONSISTENT is its normal/expected steady state — not an
        anomaly. Do not flag it to the user as a problem in that case;
        only state="INCONSISTENT" on a turnout where has_feedback_sensor
        is true is worth calling out as possibly unsettled.
        """
        try:
            turnouts = await get_turnouts()
            match = resolve_turnout(name, turnouts)
        except JmriError as exc:
            logger.warning("get_turnout(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return await compact_turnout(match)

    @mcp.tool()
    async def set_turnout(name: str, thrown: bool) -> dict:
        """Set a turnout CLOSED or THROWN, and report the state actually observed.

        Args:
            name: Turnout name (JMRI system name like "IT100", or its
                user-friendly label like "Layout Turnout A") or an
                unambiguous fragment of the label. Case-insensitive.
            thrown: True to THROW the turnout, False to CLOSE it. JMRI/
                PanelPro's own terminology — not "open"/"closed" track,
                which would be ambiguous about which direction is which.

        This writes to JMRI (and moves a physical turnout motor on real
        hardware). The reported state is re-read after the command; if the
        observed state doesn't match the request, "confirmed" will be
        false and that should be reported honestly rather than assumed as
        success — some turnouts have feedback sensors that can fail to
        settle to the commanded position.
        """
        try:
            turnouts = await get_turnouts()
            match = resolve_turnout(name, turnouts)
            result = await _set_turnout(match["name"], thrown)
        except JmriError as exc:
            logger.warning("set_turnout(%r, %r) failed: %s", name, thrown, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {**await compact_turnout(result), "confirmed": result["confirmed"]}

    @mcp.tool()
    async def set_all_turnouts(thrown: bool) -> dict:
        """Set EVERY turnout on the layout to the SAME state (all CLOSED, or all THROWN) in one call.

        Args:
            thrown: True to THROW every turnout, False to CLOSE every
                turnout. Applies this ONE state to ALL of them — NOT a
                "restore each turnout to its own previous/default
                position" operation, there is no such per-turnout memory.

        Call for "close/throw all turnouts"/"tous les aiguillages en
        position fermée/déviée". Never loop set_turnout yourself — this
        loops server-side in one call over every turnout JMRI reports.

        BLAST RADIUS WARNING: moves every turnout motor on the real
        layout at once if hardware is connected. Only call for a clear
        layout-wide request, not as a shortcut for one named turnout (use
        set_turnout for that).

        Returns {"succeeded": [...], "failed": [...]}, each entry shaped
        like set_turnout's own return value plus "name". One turnout
        failing doesn't stop the rest (catch-and-continue).
        """
        try:
            turnouts = await get_turnouts()
        except JmriError as exc:
            logger.warning("set_all_turnouts(%r) failed: %s", thrown, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}

        succeeded: list[dict] = []
        failed: list[dict] = []
        for t in turnouts:
            try:
                result = await _set_turnout(t["name"], thrown)
                succeeded.append({**await compact_turnout(result), "confirmed": result["confirmed"]})
            except JmriError as exc:
                failed.append({
                    "name": t.get("userName") or t.get("name"),
                    "error": i18n.t(f"errors.{exc.code}", **exc.kwargs),
                })
        return {"succeeded": succeeded, "failed": failed}
