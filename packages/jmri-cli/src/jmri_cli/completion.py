"""Name-list fetching for shell.py's interactive TAB completion.

shell.py's `_make_completer` walks build_parser()'s own argparse tree to
complete command/flag names; this module supplies the other half — real
values pulled from JMRI (power system names, roster/locomotive names,
light/turnout/sensor/signal/block names) — so e.g. `power on a<TAB>` at
the `jmri-cli>` prompt can complete to `power on Autorail`. `_names_for(kind)`
is the entry point shell.py calls; it's a synchronous function (readline
completers must be plain callables, but jmri_core's client is async) backed
by a small on-disk JSON cache under `~/.jmri-cli/completion_cache/<kind>.json`.

Why a cache at all: a completer runs synchronously the instant the user
presses Tab, in the middle of typing a command — a live HTTP round trip to
JMRI every keystroke would make completion feel laggy or hang outright if
JMRI is slow/unreachable, and readline doesn't tolerate a completer that's
slow or throws. `_names_for` always returns *something* usable within
COMPLETION_TIMEOUT_SECONDS: a fresh live read when the cache is missing/stale
and JMRI answers in time, the last successfully cached list when JMRI
doesn't, or an empty list (never an exception, never a hang) if there's
nothing cached either. This mirrors state.py's existing "local convenience
cache, not a source of truth" pattern — a stale suggestion is a minor
inconvenience (you'd just get a "no such locomotive" from the real
command), unlike a stale throttle-state read, which is never trusted as an
actual JMRI state.
"""

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

from jmri_core import jmri_client
from jmri_core.constants.client_tuning import (
    COMPLETION_CACHE_TTL_SECONDS,
    COMPLETION_TIMEOUT_SECONDS,
)

CACHE_DIR = Path.home() / ".jmri-cli" / "completion_cache"

_FETCHERS: dict[str, Callable] = {
    "system": jmri_client.get_systems,
    "roster": jmri_client.get_roster,
    "light": jmri_client.get_lights,
    "turnout": jmri_client.get_turnouts,
    "sensor": jmri_client.get_sensors,
    "signal": jmri_client.get_signals,
    "block": jmri_client.get_blocks,
}


def _cache_path(kind: str) -> Path:
    return CACHE_DIR / f"{kind}.json"


def _read_cache(kind: str) -> list[str] | None:
    """Return the cached name list for `kind` if the file exists and parses,
    regardless of age — staleness is decided by the caller, not here, so a
    live-fetch failure can still fall back to an old-but-present cache."""
    try:
        payload = json.loads(_cache_path(kind).read_text())
        return list(payload["names"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return None


def _cache_age_seconds(kind: str) -> float | None:
    try:
        return time.time() - _cache_path(kind).stat().st_mtime
    except FileNotFoundError:
        return None


def _write_cache(kind: str, names: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(kind).write_text(json.dumps({"names": names}))


async def _fetch_names(kind: str) -> list[str]:
    """Names to offer as Tab candidates for `kind`.

    Prefers each entry's `userName` (the human label set in JMRI, e.g.
    "Parc") over its raw system name ("IL1") when both exist - lights,
    turnouts, sensors, signals, and blocks all carry both fields, and
    resolve_light/resolve_turnout/resolve_sensor/etc. already accept a
    userName fragment, so completion must offer the same names those
    resolvers actually match on. Roster entries and power systems have no
    userName field at all; `name` there already is the human-facing one
    (e.g. "Autorail", "DCC++ Zou"), so the `or` falls through to it.
    """
    entries = await _FETCHERS[kind]()
    names = (e.get("userName") or e.get("name") for e in entries)
    return [str(name) for name in names if name]


def _names_for(kind: str) -> list[str]:
    """Sync entry point a completer callable can call directly.

    Never raises and never blocks longer than COMPLETION_TIMEOUT_SECONDS —
    an argcomplete completer that hangs or throws breaks Tab entirely, not
    just this one suggestion.
    """
    age = _cache_age_seconds(kind)
    if age is not None and age < COMPLETION_CACHE_TTL_SECONDS:
        cached = _read_cache(kind)
        if cached is not None:
            return cached

    async def _with_timeout():
        return await asyncio.wait_for(_fetch_names(kind), timeout=COMPLETION_TIMEOUT_SECONDS)

    try:
        names = asyncio.run(_with_timeout())
    except Exception:
        return _read_cache(kind) or []

    _write_cache(kind, names)
    return names
