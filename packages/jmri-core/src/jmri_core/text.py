"""Shared text-matching helpers used across resolver and keyword-matching code."""

import unicodedata


def fold(text: str) -> str:
    """Casefold and strip accents, for tolerant French-name matching ("autorail" == "Autorail")."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).casefold()
