"""Signal mast domain: list/get/set JMRI `signalMast` objects.

One-shot async HTTP against JMRI's /json/signalMasts (list) and
/json/signalMast/<name> (single get/set) endpoints (see
jmri_core.jmri_client._http for the shared GET/POST plumbing).

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

The "lit" field has an even sharper quirk: JsonSignalMastHttpService.doPost()
guards it with `data.path(LIT).isTextual()` - it only acts on "lit" if the
JSON value is a STRING ("true"/"false"), not a JSON boolean. A POST with a
real boolean (`{"lit": false}`) passes `isTextual() == false`, so the whole
branch is skipped and JMRI silently keeps the mast lit - no error, no
indication anything was ignored, confirmed live against a real DCC Signal
Mast Decoder mast (curl with `"lit": false` did nothing; `"lit": "false"`
worked). This module always posts "lit" as a JSON string for that reason.

get_signal_aspects() fills the one remaining gap: JMRI's JSON API never
exposes a mast's *valid* aspect vocabulary anywhere (confirmed by reading
JsonSignalMastHttpService's doGet()/doPost() source - the response schema
is closed over name/userName/comment/properties/aspect/lit/held/state, and
a rejected POST's error message only echoes back what was sent, never what
would have been accepted). That vocabulary exists server-side only as XML
under JMRI's own xml/signals/<SignalSystem>/appearance-<mastType>.xml -
and JMRI's web server happens to serve its whole xml/ install directory
statically at the same host:port as the JSON API (confirmed live: GET
.../xml/signals/DB-HV-1969/appearance-block.xml -> 200, no extra config).
The signal system and mast type needed to build that URL are themselves
parsed from the mast's own JMRI system name (e.g.
"TF$dsm:DB-HV-1969:block(103)" -> system "DB-HV-1969", type "block") -
verified live against the maintainer's full roster of masts, the pattern
held for all of them. Still zero hardcoded aspect/system data: everything
here is derived from a mast name JMRI already gave us, plus a live XML
fetch.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from jmri_core.constants import endpoints
from jmri_core.jmri_client._http import JmriError, _get_json, _get_text, _post_json, _unwrap

logger = logging.getLogger("jmri_core.client")

_MAST_NAME_RE = re.compile(r"\$dsm:([^:]+):(\w+)\(")


async def get_signals() -> list[dict[str, Any]]:
    """Return every signal mast known to JMRI.

    Each entry has at least: name (JMRI system name, e.g.
    "ZF$dsm:DB-HV-1969:block(31)"), userName (may be None if never set in
    JMRI), aspect (current aspect name, e.g. "Hp0"/"Hp1", vocabulary
    depends on the mast's configured signal system), lit (bool, whether the
    mast is currently illuminated), held (bool, whether the mast is held at
    its current aspect regardless of interlocking/logic).
    """
    payload = await _get_json(endpoints.SIGNAL_MASTS)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.SIGNAL_MASTS, payload=payload)
    signals = [_unwrap(entry) for entry in payload]
    logger.info(
        "Discovered %d signal mast(s): %s",
        len(signals),
        [s.get("userName") or s.get("name") for s in signals],
    )
    return signals


_UNLIT_ASPECTS = {"unlit", "off"}


async def get_signal_aspects(name: str) -> list[str]:
    """Return the valid aspect names for one signal mast, parsed live from JMRI's own XML.

    Args:
        name: The mast's JMRI system name (e.g.
            "TF$dsm:DB-HV-1969:block(103)"), as returned by
            get_signals()/resolve_signal() - not the user-facing label.

    JMRI's JSON API has no field anywhere for a mast's valid aspects (see
    module docstring), so this parses the signal system and mast type out
    of the mast's own system name (the "DB-HV-1969" and "block" in the
    example above) and fetches JMRI's web server's static copy of
    xml/signals/<system>/appearance-<type>.xml, which lists exactly the
    aspects usable by that mast type (a real subset of the signal system's
    full vocabulary - e.g. a "block" mast may support only Hp0/Hp1 while
    the full DB-HV-1969 system defines many more).

    Does NOT include "unlit"/"off": whether a mast can be unlit is a
    separate per-mast PanelPro checkbox ("This Mast can be unlit"), not
    part of the signal system's aspect vocabulary, and not derivable from
    JMRI's JSON API or its xml/signals/ system definitions (confirmed
    live: a mast with the checkbox unset still accepts set_signal's
    "unlit" - JMRI's own "lit" field has no such restriction - so this
    can't be inferred from behavior either). Use "signal off <name>" /
    set_signal(name, "off") directly if you want to darken a mast; JMRI
    itself is the only honest source for whether that's meaningful for a
    given mast.

    Raises JmriError("aspects_not_derivable") if the mast's name doesn't
    match JMRI's usual "$dsm:<system>:<type>(<address>)" pattern (e.g. a
    manually renamed mast) - callers should fall back to JMRI's own
    server-side validation on set_signal() rather than guess.
    """
    match = _MAST_NAME_RE.search(name)
    if not match:
        raise JmriError("aspects_not_derivable", name=name)
    signal_system, mast_type = match.group(1), match.group(2)

    xml_text = await _get_text(
        endpoints.SIGNAL_MAST_APPEARANCE.format(signal_system=signal_system, mast_type=mast_type)
    )
    root = ET.fromstring(xml_text)
    aspects = [el.text.strip() for el in root.iter("aspectname") if el.text and el.text.strip()]
    logger.info("Discovered %d valid aspect(s) for %s: %s", len(aspects), name, aspects)
    return aspects


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
            confirm. Special-cased (case-insensitive): "unlit"/"off" mean
            "make this mast dark" rather than a real aspect name - JMRI
            models that as a separate "lit" field, not an aspect, so this
            posts {"lit": "false"} instead of {"state": aspect} and
            confirms against the mast's observed "lit" state instead of
            "aspect". A normal aspect request always re-asserts
            {"lit": "true"} alongside {"state": aspect}, so setting any
            real aspect also relights a mast previously left unlit -
            JMRI does not do this on its own (confirmed live: a "state"-only
            POST with no "lit" key leaves a previously-unlit mast dark even
            though the aspect itself did change server-side).

    Re-reads via get_signals() after the POST and reports "confirmed"
    honestly, same contract as set_power()/set_turnout()/set_light() - a
    mast driven by external hardware (e.g. a DCC accessory decoder) can
    still fail to reach a *valid* requested aspect even though the POST
    itself succeeded.
    """
    unlit = aspect.strip().casefold() in _UNLIT_ASPECTS
    if unlit:
        # "lit" must be a JSON string, not a boolean - see module docstring.
        await _post_json(endpoints.SIGNAL_MAST.format(name=name), {"name": name, "lit": "false"})
    else:
        # Always re-assert lit:"true" alongside the aspect: JMRI does not
        # auto-relight a mast just because a new aspect was requested (a
        # mast left unlit by a prior "unlit"/"off" call stays unlit even
        # after a normal aspect POST with no "lit" key) - confirmed live.
        await _post_json(
            endpoints.SIGNAL_MAST.format(name=name),
            {"name": name, "state": aspect, "lit": "true"},
        )

    signals = await get_signals()
    matches = [s for s in signals if s.get("name") == name]
    if not matches:
        raise JmriError("vanished_after_post", kind="signal mast", name=name)
    observed = matches[0]

    if unlit:
        confirmed = not bool(observed.get("lit"))
    else:
        confirmed = observed.get("aspect") == aspect
    if not confirmed:
        logger.warning(
            "set_signal(%s, %s): requested aspect=%s but observed aspect=%s lit=%s",
            name,
            aspect,
            aspect,
            observed.get("aspect"),
            observed.get("lit"),
        )
    return {**observed, "confirmed": confirmed}


def resolve_signal(query: str, signals: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied signal mast name against discovered masts.

    Tolerant like resolve_turnout: case-insensitive, matches either the
    JMRI system name ("ZF$dsm:DB-HV-1969:block(31)") or the user-friendly
    userName exactly first, then an unambiguous substring fragment of
    userName or the system name. No default fallback - a mast must be
    named, there's no single "the" signal.
    """
    if not signals:
        raise JmriError("none_available", kind="signal mast")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="signal mast")

    q = query.strip().casefold()
    labels = [str(s.get("userName") or s.get("name", "")) for s in signals]

    exact = [
        s
        for s in signals
        if str(s.get("name", "")).casefold() == q or str(s.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [
        s
        for s in signals
        if q in str(s.get("userName") or "").casefold() or q in str(s.get("name", "")).casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(s.get("userName") or s.get("name")) for s in partial]
        raise JmriError("ambiguous_entity", kind="signal mast", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="signal mast", query=query, available=labels)
