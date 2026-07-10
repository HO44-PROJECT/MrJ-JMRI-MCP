"""Signal mast domain: list/get/set JMRI `signalMast` objects.

One-shot async HTTP against JMRI's /json/signalMasts (list) and
/json/signalMast/<name> (single get/set) endpoints (see
jmri_mcp.jmri_client._http for the shared GET/POST plumbing).

signalHead is deliberately not covered here. JMRI has two signal object
types: signalHead (a single physical lamp/LED head, RED/YELLOW/GREEN/DARK
states) and signalMast (a higher-level mast with named "aspects" like
Hp0/Hp1/Hp2, defined by whatever signaling system - e.g. DB-HV-1969 - the
mast was configured with in PanelPro). A mast is usually built from one or
more heads, but that wiring is internal to JMRI/hardware and isn't
something this project's users manage directly - confirmed against the
maintainer's own layout, where a custom ESP32 decodes the DCC accessory
frame JMRI sends for the mast's aspect and does its own aspect->LED/fading
translation in firmware, so no signalHead objects exist in JMRI at all.
signalMast is the level PanelPro users actually name and interact with, so
it's the only one exposed here.

JMRI does not report a mast's list of *valid* aspects anywhere in
/json/signalMast (that vocabulary lives in the mast's signal system
definition, not the JSON API) - so, like set_function's F-number handling,
this module does not validate aspect names locally. It posts whatever
string is given; JMRI itself validates it server-side against the mast's
signal system and raises a JsonException (surfaced here as JmriError) if
the aspect name isn't one of the mast's valid aspects - confirmed by
reading JMRI's JsonSignalMastHttpService.doPost() source.

The POST body's JSON key is "state", not "aspect" - JMRI's doPost() reads
data.path(STATE) (STATE == "state") to get the requested aspect name, a
naming quirk of the signalMast JSON service worth calling out since it's
easy to guess wrong (verified against JMRI 5.4.0's actual server source
after a POST with an "aspect" key was silently accepted but never applied).
"""

import logging
from typing import Any

from jmri_mcp.jmri_client._http import JmriError, _get_json, _post_json, _unwrap

logger = logging.getLogger("jmri_mcp.client")


async def get_signals() -> list[dict[str, Any]]:
    """Return every signal mast known to JMRI.

    Each entry has at least: name (JMRI system name, e.g.
    "ZF$dsm:DB-HV-1969:block(31)"), userName (may be None if never set in
    JMRI), aspect (current aspect name, e.g. "Hp0"/"Hp1", vocabulary
    depends on the mast's configured signal system), lit (bool, whether the
    mast is currently illuminated), held (bool, whether the mast is held at
    its current aspect regardless of interlocking/logic).
    """
    payload = await _get_json("/json/signalMasts")
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError(f"Unexpected /json/signalMasts payload: {payload!r}")
    signals = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d signal mast(s): %s",
                len(signals), [s.get("userName") or s.get("name") for s in signals])
    return signals


async def set_signal(name: str, aspect: str) -> dict[str, Any]:
    """Set one signal mast's aspect by its JMRI system name, then report the observed state.

    Args:
        name: The mast's JMRI system name (e.g.
            "ZF$dsm:DB-HV-1969:block(31)"), as returned by
            get_signals()/resolve_signal() - not the user-facing label.
        aspect: The aspect name to request (e.g. "Hp0", "Hp1", "Hp2" for a
            DB-HV-1969 mast). Not validated locally - JMRI's signal system
            defines what's valid for this specific mast, and that
            vocabulary isn't available over the JSON API (see module
            docstring). JMRI validates it server-side instead: an unknown
            aspect name raises a JmriError rather than silently failing to
            confirm.

    Re-reads via get_signals() after the POST and reports "confirmed"
    honestly, same contract as set_power()/set_turnout()/set_light() - a
    mast driven by external hardware (e.g. a DCC accessory decoder) can
    still fail to reach a *valid* requested aspect even though the POST
    itself succeeded.
    """
    await _post_json(f"/json/signalMast/{name}", {"name": name, "state": aspect})

    signals = await get_signals()
    matches = [s for s in signals if s.get("name") == name]
    if not matches:
        raise JmriError(f"Signal mast {name!r} vanished after POST")
    observed = matches[0]

    confirmed = observed.get("aspect") == aspect
    if not confirmed:
        logger.warning(
            "set_signal(%s, %s): requested aspect=%s but observed aspect=%s",
            name, aspect, aspect, observed.get("aspect"),
        )
    return {**observed, "confirmed": confirmed}


def resolve_signal(query: str, signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied signal mast name against discovered masts.

    Tolerant like resolve_turnout: case-insensitive, matches either the
    JMRI system name ("ZF$dsm:DB-HV-1969:block(31)") or the user-friendly
    userName exactly first, then an unambiguous substring fragment of
    userName. No default fallback - a mast must be named, there's no
    single "the" signal.
    """
    if not signals:
        raise JmriError("JMRI reports no signal masts")
    if not query or not query.strip():
        raise JmriError("No signal mast name given")

    q = query.strip().casefold()
    labels = [str(s.get("userName") or s.get("name", "")) for s in signals]

    exact = [
        s for s in signals
        if str(s.get("name", "")).casefold() == q
        or str(s.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [s for s in signals if q in str(s.get("userName") or "").casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(s.get("userName") or s.get("name")) for s in partial]
        raise JmriError(f"Ambiguous signal mast {query!r}: matches {matches}")

    raise JmriError(f"Unknown signal mast {query!r}. Available: {labels}")
