"""Local last-known-state cache for `jmri-cli throttle`.

Every `jmri-cli throttle` invocation opens a fresh WebSocket connection,
acquires, acts, then closes (see throttle.py's module docstring) — JMRI
releases the throttle the moment that connection closes, so there is no
live per-address state to query back from JMRI itself between CLI
invocations. This file is the CLI's own memory of what it last saw for
each address (speed, direction, functions), so `jmri-cli throttle` (bare)
and `jmri-cli throttle speed <addr>` (no value) have something to show.

This is a convenience cache, not a source of truth: another JMRI client
changing a loco's speed between two `jmri-cli` invocations won't be
reflected here until the next `jmri-cli throttle ...` command touches that
address and resyncs it from JMRI's own acquire/set reply.
"""

import json
from pathlib import Path
from typing import Any

STATE_FILE = Path.home() / ".jmri-cli" / "throttle_state.json"


def load_state() -> dict[str, dict[str, Any]]:
    """Return {address_str: {"speed":..., "forward":..., "functions": {...}}}."""
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict[str, dict[str, Any]]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def update_address(address: int, **fields: Any) -> None:
    """Merge `fields` (e.g. speed=0.4, forward=True) into the cached entry for `address`.

    Function numbers are normalized to string keys before merging — JSON
    only supports string object keys, so a value round-tripped through
    load_state() always comes back with string keys, and merging a fresh
    int-keyed update on top would leave the dict with mixed key types.
    """
    state = load_state()
    entry = state.setdefault(str(address), {})
    if "functions" in fields:
        functions = entry.setdefault("functions", {})
        functions.update({str(n): v for n, v in fields.pop("functions").items()})
    entry.update(fields)
    save_state(state)
