"""Keyword vocabulary for recognizing "light"-related roster function labels.

Used by the bulk lighting tools (jmri_mcp.tools.throttle's set_loco_lights /
set_all_locos_lights, and jmri_cli.throttle's --lights-only filter) to turn
"turn on all the lights of this loco" into every light-labeled F-number, not
just F0. Verified live against the Autorail roster entry: F0="Lumieres
avant", F1="Lumieres cabine", F2="Lumieres arrieres" are ALL labeled as
lights — an F0-only implementation would silently miss F1/F2.

Deliberately a flat keyword list, not the i18n "kinds" table (jmri_core.i18n's
en.json/fr.json "kinds.light" only gives "light"/"lumiere" singular/plural for
generic entity-kind naming) — a user's own roster labels are free text they
typed themselves in JMRI's editor, not a fixed vocabulary this project
controls, so matching needs to be generous/keyword-based, not an exact i18n key.
"""

from jmri_core.text import fold

LIGHT_LABEL_KEYWORDS: tuple[str, ...] = (
    # French (accent-folded via fold(), so "lumiere" also matches
    # "Lumière"/"lumières"/"LUMIÈRE" etc.)
    "lumiere",
    "feu",
    "lampe",
    "phare",
    # English
    "light",
    "lamp",
    "headlight",
)


def is_light_label(label: str) -> bool:
    """True if a roster-set function label (e.g. "Lumieres avant") names a light.

    Case- and accent-insensitive substring match against LIGHT_LABEL_KEYWORDS.
    """
    if not label:
        return False
    folded = fold(label)
    return any(keyword in folded for keyword in LIGHT_LABEL_KEYWORDS)
