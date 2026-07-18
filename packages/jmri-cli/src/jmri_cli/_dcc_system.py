"""Shared "which DCC system owns this JMRI object" display helper for the CLI.

Turnout/light/signal system names always start with a real prefix character
(the DCC connection prefix, or "I" for JMRI-internal objects with no power
connection) — unlike a roster entry's `dcc_system`, there is no "unset,
falls back to JMRI's default system" case to handle here, so this is simpler
than roster.py's own `_dcc_system_display`/`_system_names_by_prefix` pair.
"""

from jmri_core.jmri_client import JmriError, get_systems


async def system_names_by_prefix() -> dict[str, str]:
    """{prefix: full system name}, e.g. {"T": "taya (accessories)"}. Empty
    (not raised) if the systems lookup itself fails, so a listing never
    breaks just because this extra context couldn't be fetched."""
    try:
        systems = await get_systems()
    except JmriError:
        return {}
    return {str(s.get("prefix", "")): s.get("name") for s in systems}


def dcc_system_display(system_id: str, names_by_prefix: dict[str, str]) -> str:
    """"OT23" -> "ohara (turnouts)" via its leading prefix character "O"; "-"
    when the prefix matches no known DCC connection (e.g. "I" for
    JMRI-internal objects like IT100, which have no power connection)."""
    if not system_id:
        return "-"
    prefix = system_id[0]
    return names_by_prefix.get(prefix) or "-"
