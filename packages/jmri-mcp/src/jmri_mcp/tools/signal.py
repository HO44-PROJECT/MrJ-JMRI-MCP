"""Signal mast MCP tools: list_signals, get_signal, set_signal, signal_off, list_signal_aspects.

Talks to jmri_client.py (one-shot HTTP), same as power.py/turnout.py. Covers
JMRI's signalMast only, not signalHead (internal plumbing, unused by this
project's users) — see jmri_core.jmri_client.signal's module docstring.
"""

import logging

from jmri_core import i18n
from jmri_core.jmri_client import JmriError, get_signal_aspects, get_signals, resolve_signal
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

        Use to discover what signal masts exist, or answer "what signals
        are there?"/"what aspect is signal X showing?". No side effects.
        Also reports "lit" — use signal_off(name) to darken a mast. Call
        list_signal_aspects(name) for a mast's valid aspects before
        set_signal with one you're unsure of.
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
            name: Mast name (system name or userName) or unambiguous
                fragment. Case-insensitive.

        Also reports "lit" (bool, illuminated or dark — independent of
        aspect). No side effects.
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
            name: Mast name (system name or userName) or unambiguous
                fragment. Case-insensitive.
            aspect: e.g. "Hp0"/"Hp1"/"Hp2" — signal-system-dependent, IS
                case-sensitive, NOT validated locally (rejection: "error").
                Call list_signal_aspects(name) FIRST if unsure of
                spelling/case, e.g. when named by effect ("turn it red") —
                don't guess. "unlit"/"off" darkens the mast — prefer
                signal_off(name).

        Writes to JMRI. "confirmed" false means re-read still doesn't
        match — report honestly.
        """
        try:
            signals = await get_signals()
            match = resolve_signal(name, signals)
            result = await _set_signal(match["name"], aspect)
        except JmriError as exc:
            logger.warning("set_signal(%r, %r) failed: %s", name, aspect, exc)
            message = i18n.t(f"errors.{exc.code}", **exc.kwargs)
            if "unknown state" in message.casefold():
                message = i18n.t("errors.set_signal_rejected_hint", message=message)
            return {"error": message}
        return {**await compact_signal(result), "confirmed": result["confirmed"]}

    @mcp.tool()
    async def signal_off(name: str) -> dict:
        """Darken a signal mast: shortcut for set_signal(name, "off").

        Args:
            name: Mast name (system name or userName) or unambiguous
                fragment. Case-insensitive.

        Depends on this mast's "can be unlit" setting in PanelPro — JMRI
        accepts "lit" regardless, so "confirmed": true doesn't guarantee
        unlit-capability.
        """
        return await set_signal(name, "off")

    @mcp.tool()
    async def list_signal_aspects(name: str) -> dict:
        """List valid aspect names for one mast, to pick an exact spelling before set_signal.

        Args:
            name: Mast name (system name or userName) or unambiguous
                fragment. Case-insensitive.

        Aspects ARE case-sensitive ("Hp0", not "hp0"). Returns
        {"aspects": [...]}, this mast's real subset. Excludes "unlit"/"off"
        (use signal_off). No side effects; "error" for non-standard names.
        """
        try:
            signals = await get_signals()
            match = resolve_signal(name, signals)
            aspects = await get_signal_aspects(match["name"])
        except JmriError as exc:
            logger.warning("list_signal_aspects(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"aspects": aspects}
