"""Signal mast MCP tools: list_signals, get_signal, set_signal.

Talks to jmri_client.py (one-shot HTTP), same as power.py/turnout.py. This
covers JMRI's signalMast objects only, not signalHead — see
jmri_mcp.jmri_client.signal's module docstring for why: signalHead is
internal plumbing (individual lamps) that most JMRI users, including this
project's maintainer, never interact with directly once a mast is
configured. A signalMast's "aspect" (e.g. "Hp0", "Hp1", "Hp2" for a German
DB-HV-1969 mast) is the vocabulary PanelPro users actually see and use.
"""

import logging

from jmri_mcp.jmri_client import JmriError, get_signals, resolve_signal
from jmri_mcp.jmri_client import set_signal as _set_signal
from jmri_mcp.tools._common import compact_signal

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_signals() -> dict:
        """List every signal mast known to JMRI, with its current aspect.

        Use this to discover what signal masts exist before calling
        get_signal/set_signal, or to answer "what signals are there?"/
        "what aspect is signal X showing?". No side effects.

        A signal mast is a trackside signal (e.g. a German Hauptsignal),
        distinct from a turnout (a switch/points) or a layout light
        (scenery lighting) — don't confuse "set the signal" with
        set_turnout or set_light. This tool only covers signalMast
        objects; JMRI's lower-level signalHead objects (individual lamps
        that a mast is built from) are not exposed, since most layouts —
        including this one — never interact with them directly once a
        mast is configured in PanelPro.

        Each mast's "aspect" is a name like "Hp0"/"Hp1"/"Hp2" (German
        Hauptsignal aspects) or a different vocabulary entirely, depending
        on which signal system the mast was configured with in PanelPro —
        this project never hardcodes or translates aspect names, it passes
        through whatever JMRI reports for that specific mast.
        """
        try:
            signals = await get_signals()
        except JmriError as exc:
            logger.warning("list_signals failed: %s", exc)
            return {"error": str(exc)}
        return {"signals": [compact_signal(s) for s in signals]}

    @mcp.tool()
    async def get_signal(name: str) -> dict:
        """Get the current aspect of one signal mast.

        Args:
            name: Signal mast name (JMRI system name, or its user-friendly
                label if one is set) or an unambiguous fragment of the
                label. Case-insensitive.

        No side effects — this only reads state, it never changes the
        signal.
        """
        try:
            signals = await get_signals()
            match = resolve_signal(name, signals)
        except JmriError as exc:
            logger.warning("get_signal(%r) failed: %s", name, exc)
            return {"error": str(exc)}
        return compact_signal(match)

    @mcp.tool()
    async def set_signal(name: str, aspect: str) -> dict:
        """Set a signal mast's aspect, and report the aspect actually observed.

        Args:
            name: Signal mast name (JMRI system name, or its user-friendly
                label if one is set) or an unambiguous fragment of the
                label. Case-insensitive.
            aspect: The aspect to request, e.g. "Hp0" (stop), "Hp1"
                (proceed), "Hp2" (proceed with reduced speed) for a German
                DB-HV-1969 mast — the exact valid names depend on this
                specific mast's configured signal system and are NOT
                validated locally by this tool (JMRI doesn't expose the
                valid-aspect list over its JSON API) — JMRI validates it
                server-side instead and this tool reports that as an error
                if the name is unknown. If unsure what aspects a mast
                supports, call get_signal/list_signals first to see its
                current aspect as an example of the naming style in use,
                or ask the user rather than guessing an aspect name.

        This writes to JMRI (and, on masts driven by external hardware —
        e.g. a DCC accessory decoder or a custom microcontroller — changes
        what the physical signal displays on the real layout). An unknown
        aspect name is reported as an "error" (JMRI rejects it outright).
        A *valid* aspect is re-read after the command; if the observed
        aspect still doesn't match the request, "confirmed" will be false
        and that should be reported honestly rather than assumed as
        success — unresponsive external hardware can cause this even when
        JMRI itself accepted the change.
        """
        try:
            signals = await get_signals()
            match = resolve_signal(name, signals)
            result = await _set_signal(match["name"], aspect)
        except JmriError as exc:
            logger.warning("set_signal(%r, %r) failed: %s", name, aspect, exc)
            return {"error": str(exc)}
        return {**compact_signal(result), "confirmed": result["confirmed"]}
