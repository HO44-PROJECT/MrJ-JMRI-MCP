"""Shared regex/glob matching for the `findr`/`findg` CLI leaves.

`find` itself stays on each domain's own resolve_*() (jmri_client) — exact
match, ambiguous substring = error, exactly one result. `findr`/`findg`
are a different shape entirely: a pattern can legitimately match zero, one,
or many entries, so they return a list instead of raising on ambiguity.
Only used by the CLI layer (roster.py/turnout.py); resolve_*() and the
close/throw/on/off commands that rely on its single-match contract are
untouched.
"""

import fnmatch
import re
from collections.abc import Callable
from typing import Any

from jmri_mcp.jmri_client import JmriError


def find_regex(
    pattern: str, entries: list[dict[str, Any]], label: Callable[[dict], str]
) -> list[dict[str, Any]]:
    """Return every entry whose label matches `pattern` as a case-insensitive regex (re.search)."""
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise JmriError(f"Invalid regex {pattern!r}: {exc}") from None
    return [e for e in entries if compiled.search(label(e))]


def find_glob(
    pattern: str, entries: list[dict[str, Any]], label: Callable[[dict], str]
) -> list[dict[str, Any]]:
    """Return every entry whose label matches `pattern` as a case-insensitive shell glob (*, ?, [...])."""
    return [e for e in entries if fnmatch.fnmatch(label(e).casefold(), pattern.casefold())]
