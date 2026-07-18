"""Signal mast MCP tools: list_signals, get_signal, set_signal.

Talks to jmri_client.py (one-shot HTTP), same as power.py/turnout.py. This
covers JMRI's signalMast objects only, not signalHead — see
jmri_core.jmri_client.signal's module docstring for why: signalHead is
internal plumbing (individual lamps) that most JMRI users, including this
project's maintainer, never interact with directly once a mast is
configured. A signalMast's "aspect" (e.g. "Hp0", "Hp1", "Hp2" for a German
DB-HV-1969 mast) is the vocabulary PanelPro users actually see and use.
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import JmriError, get_signals, resolve_signal
from jmri_core.jmri_client import set_signal as _set_signal
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

        Use to discover what signal masts exist before calling
        get_signal/set_signal, or to answer "what signals are there?"/
        "what aspect is signal X showing?". No side effects.

        A signal mast is a trackside signal (e.g. German Hauptsignal),
        distinct from a turnout (switch/points) or a layout light
        (scenery) — don't confuse with set_turnout/set_light. Only
        covers signalMast objects, not JMRI's lower-level signalHead
        objects (rarely used directly once a mast is configured).

        "aspect" is a name like "Hp0"/"Hp1"/"Hp2" (German Hauptsignal) or
        a different vocabulary depending on the mast's configured signal
        system — aspect names are never hardcoded/translated, just
        passed through from JMRI.
        """
        try:
            signals = await get_signals()
        except JmriError as exc:
            logger.warning("list_signals failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"signals": [await compact_signal(s) for s in signals]}

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
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return await compact_signal(match)

    @mcp.tool()
    async def set_signal(name: str, aspect: str) -> dict:
        """Set a signal mast's aspect, and report the aspect actually observed.

        Args:
            name: Signal mast name (JMRI system name or user-friendly
                label) or an unambiguous fragment. Case-insensitive.
            aspect: The aspect to request, e.g. "Hp0" (stop), "Hp1"
                (proceed), "Hp2" (proceed reduced speed) for a German
                DB-HV-1969 mast — valid names depend on this mast's
                configured signal system and are NOT validated locally
                (JMRI doesn't expose a valid-aspect list); JMRI validates
                server-side and this tool reports rejection as an error.
                If unsure, call get_signal/list_signals first to see the
                current aspect as a naming-style example, or ask the user
                rather than guessing.

        Writes to JMRI, and on masts driven by external hardware (DCC
        accessory decoder, microcontroller) changes the real physical
        signal. An unknown aspect is reported as an "error". A valid
        aspect is re-read after the command; if the observed aspect still
        doesn't match, "confirmed" is false — report that honestly, not as
        success, since unresponsive hardware can cause this even when
        JMRI itself accepted the change.
        """
        try:
            signals = await get_signals()
            match = resolve_signal(name, signals)
            result = await _set_signal(match["name"], aspect)
        except JmriError as exc:
            logger.warning("set_signal(%r, %r) failed: %s", name, aspect, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {**await compact_signal(result), "confirmed": result["confirmed"]}
