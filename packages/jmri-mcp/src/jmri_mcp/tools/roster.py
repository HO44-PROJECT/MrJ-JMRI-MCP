"""Roster MCP tools: list_roster, find_locomotive, get_locomotive_functions.

Talks to jmri_client.py (one-shot HTTP), same as power.py. These are how
the LLM turns a spoken name ("the Autorail") into the DCC address the
throttle.py tools need: list_roster for browsing, find_locomotive for
resolving one specific name (fuzzy, accent/case-insensitive) directly to an
address, get_locomotive_functions for the user's own per-loco function
labels (set in JMRI's roster editor) so "turn on the rear lights" can
resolve to the right F-number without any hardcoded name->function mapping.
"""

import logging

from jmri_core import i18n, jmri_client
from jmri_core.jmri_client import JmriError, resolve_roster_entry

logger = logging.getLogger("jmri_mcp.tools")


def register(mcp) -> None:
    """Register this module's tools on `mcp`.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """

    @mcp.tool()
    async def list_roster() -> dict:
        """List every locomotive in JMRI's roster: name, DCC address, road,
        road number, manufacturer, model, owner, last-modified date, and
        roster groups.

        Use this to discover what locomotives exist and their DCC addresses
        before calling acquire_throttle/set_speed/etc. — those tools take a
        DCC address, not a name, and this is currently the only way to find
        out which address belongs to which named loco (e.g. the user says
        "start the Autorail" but set_speed needs address=4). Any of these
        fields can be empty (string or list) if the user never filled them
        in in JMRI — that's normal, not an error. "groups" lists the JMRI
        Roster Groups (set in PanelPro) this locomotive belongs to — most
        locomotives belong to none. No side effects.

        This does NOT resolve a name to an address for you automatically —
        use find_locomotive for that.
        """
        try:
            roster = await jmri_client.get_roster()
        except JmriError as exc:
            logger.warning("list_roster failed: %s", exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {"roster": roster}

    @mcp.tool()
    async def find_locomotive(name: str) -> dict:
        """Resolve a locomotive's spoken/typed name to its DCC address.

        Use this whenever the user names a locomotive ("the Autorail",
        "141R", "start the Pacific") instead of giving a DCC address
        directly — call this first to get the address, then pass that
        address to acquire_throttle/set_speed/set_direction/set_function/
        lights_on/lights_off/etc.

        Matching is tolerant: case-insensitive, accent-insensitive (useful
        for French names — "boite a sel" matches "Boite à Sel"), and
        accepts an exact name or an unambiguous partial match ("autorail"
        matches "Autorail"). If the name matches more than one roster
        entry, or matches none, this returns an "error" explaining why
        (listing the candidates or the full roster) instead of guessing —
        ask the user to clarify rather than picking one yourself.
        """
        try:
            roster = await jmri_client.get_roster()
            entry = resolve_roster_entry(name, roster)
        except JmriError as exc:
            logger.warning("find_locomotive(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return entry

    @mcp.tool()
    async def get_locomotive_functions(name: str) -> dict:
        """List a locomotive's named decoder functions (e.g. "F2": "Rear lights").

        JMRI lets the user label each loco's functions individually in its
        roster editor — call this BEFORE set_function whenever the user
        refers to a function by what it does ("turn on the rear lights",
        "blow the whistle") instead of an F-number, so you can look up the
        right number instead of guessing or asking. Only labels the user
        actually set are returned; most locos have few or none (an empty
        "functions" dict is normal, not an error — it means this loco has
        no custom labels, so ask the user for an F-number instead).

        Args:
            name: The locomotive's name (fuzzy-resolved the same way as
                find_locomotive — call this directly, you don't need to
                call find_locomotive first just to get the exact name).

        Returns functions as {"F0": "label", ...}. Function numbers with no
        label set are omitted entirely (JMRI has 29 possible slots, F0-F28,
        per loco — only the labeled ones are useful to you).
        """
        try:
            roster = await jmri_client.get_roster()
            entry = resolve_roster_entry(name, roster)
            labels = await jmri_client.get_roster_function_labels(entry["name"])
        except JmriError as exc:
            logger.warning("get_locomotive_functions(%r) failed: %s", name, exc)
            return {"error": i18n.t(f"errors.{exc.code}", **exc.kwargs)}
        return {
            "name": entry["name"],
            "address": entry["address"],
            "functions": {f"F{n}": label for n, label in sorted(labels.items())},
        }
