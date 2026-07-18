"""Shared helpers for tools/power.py, roster.py, throttle.py.

Kept here (not duplicated per-module) because acquire/set_speed/etc. all
need the same address<->throttle-id mapping and the same auto-acquire
behavior, and get_power/set_power/system_status all need the same power
compaction.
"""

import asyncio

from jmri_core.config import get_exhibition_allowed_addresses
from jmri_core.constants.cli import (
    BLOCK_STATE_NAMES,
    LIGHT_STATE_NAMES,
    POWER_STATE_NAMES,
    SENSOR_STATE_NAMES,
    TURNOUT_STATE_NAMES,
)
from jmri_core.constants.protocol import FIELD_ADDRESS, FIELD_FORWARD, FIELD_SPEED
from jmri_core.jmri_client import (
    default_system_prefix,
    resolve_dcc_prefix,
    resolve_dcc_system_name,
    resolve_max_speed_percent,
    resolve_system_name,
)
from jmri_core.jmri_ws import JmriError


def compact_power(system: dict) -> dict:
    """Reduce a raw JMRI power-system dict to the fields worth showing the LLM.

    Args:
        system: A system dict as returned by jmri_client.get_systems(),
            with at least "name" and "state", and optionally "default".

    Returns:
        {"name": ..., "state": "ON"/"OFF"/"UNKNOWN"/"IDLE", "default": bool}.
        "name" is JMRI's full connection name verbatim, e.g. "zou (test)" —
        the user names each of their DCC systems in JMRI's own connection
        setup, often with a short parenthetical describing its purpose
        ("test", "tracks", "turnouts", "accessories"). This is the only
        place that purpose is recorded; if asked what a system is for
        ("à quoi sert le système zou ?"), read it straight out of this
        name rather than saying the information isn't available.
    """
    return {
        "name": system.get("name"),
        "state": POWER_STATE_NAMES.get(system.get("state"), "UNKNOWN"),
        "default": bool(system.get("default")),
    }


async def compact_light(light: dict) -> dict:
    """Reduce a raw JMRI light dict to the fields worth showing the LLM.

    Args:
        light: A light dict as returned by jmri_client.get_lights(), with
            at least "name" and "state", and optionally "userName",
            "comment" (free text set in PanelPro's light editor).

    Returns:
        {"name": ..., "state": "ON"/"OFF"/"UNKNOWN"/"INCONSISTENT",
        "dcc_system_name": str|None, "comment": str|None}. "name" is the
        user-friendly userName if JMRI has one set, else falls back to the
        raw system name (e.g. "IL1") — this is what the LLM should
        show/match against, not JMRI's internal system name.
        "dcc_system_name" is the DCC connection that manages this light,
        derived from its raw system name's prefix (e.g. "TL51" -> Taya) —
        None if the prefix matches no known DCC system (see
        resolve_dcc_system_name). "comment" is static layout metadata, not
        live state — None if never set in PanelPro.
    """
    return {
        "name": light.get("userName") or light.get("name"),
        "state": LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN"),
        "dcc_system_name": await resolve_dcc_system_name(light.get("name")),
        "comment": light.get("comment"),
    }


async def compact_turnout(turnout: dict) -> dict:
    """Reduce a raw JMRI turnout dict to the fields worth showing the LLM.

    Args:
        turnout: A turnout dict as returned by jmri_client.get_turnouts(),
            with at least "name" and "state", and optionally "userName",
            "sensor" (JMRI's 2-element feedback-sensor array), "comment"
            (free text set in PanelPro's turnout editor).

    Returns:
        {"name": ..., "state": "CLOSED"/"THROWN"/"UNKNOWN"/"INCONSISTENT",
        "has_feedback_sensor": bool, "dcc_system_name": str|None,
        "comment": str|None}. "name" is the user-friendly userName if JMRI
        has one set, else falls back to the raw system name (e.g.
        "IT100"). "has_feedback_sensor" is True only if JMRI actually has
        a real feedback sensor wired to this turnout (a non-null entry in
        its "sensor" array) — verified live (2026-07-11) that JMRI's
        "feedbackMode" number alone is NOT a reliable signal for this (a
        turnout in DIRECT mode can still carry a leftover sensor object),
        so presence of an actual sensor entry is what's checked instead.
        When False, INCONSISTENT is normal/expected background noise for
        that turnout — JMRI has no way to confirm the motor's real
        position and reports INCONSISTENT indefinitely, even at rest with
        no command in flight, not just transiently after a set_turnout
        call. See set_turnout's docstring for how this should change what
        gets reported to the user. "dcc_system_name" is the DCC connection
        that manages this turnout, derived from its raw system name's
        prefix (e.g. "OT23" -> Ohara) — None for JMRI-internal turnouts
        with no power connection (e.g. "IT100") or any other unresolvable
        prefix. "comment" is static layout metadata, not live state — None
        if never set in PanelPro (e.g. often used to note what a turnout
        physically connects, like "Yard throat switch").
    """
    sensors = turnout.get("sensor") or []
    has_feedback_sensor = any(s is not None for s in sensors)
    return {
        "name": turnout.get("userName") or turnout.get("name"),
        "state": TURNOUT_STATE_NAMES.get(turnout.get("state"), "UNKNOWN"),
        "has_feedback_sensor": has_feedback_sensor,
        "dcc_system_name": await resolve_dcc_system_name(turnout.get("name")),
        "comment": turnout.get("comment"),
    }


def compact_sensor(sensor: dict) -> dict:
    """Reduce a raw JMRI sensor dict to the fields worth showing the LLM.

    Args:
        sensor: A sensor dict as returned by jmri_client.get_sensors(),
            with at least "name" and "state", and optionally "userName".

    Returns:
        {"name": ..., "state": "ACTIVE"/"INACTIVE"/"UNKNOWN"/"INCONSISTENT"}.
        "name" is the user-friendly userName if JMRI has one set, else
        falls back to the raw system name (e.g. "RS22").
    """
    return {
        "name": sensor.get("userName") or sensor.get("name"),
        "state": SENSOR_STATE_NAMES.get(sensor.get("state"), "UNKNOWN"),
    }


def compact_block(block: dict) -> dict:
    """Reduce a raw JMRI block dict to the fields worth showing the LLM.

    Args:
        block: A block dict as returned by jmri_client.get_blocks(), with
            at least "name" and "state", and optionally "userName",
            "sensor" (linked occupancy sensor's system name), "value"
            (whatever JMRI's reporting hardware detected occupying the
            block, e.g. a roster entry or RFID tag id), "length" (block
            length in JMRI's configured layout units, e.g. cm), "curvature"
            (JMRI's small curvature enum, e.g. 0=NONE/1=GRADUAL/2=TIGHT/
            3=SEVERE), "speed" (a named speed step, e.g. "Normal"/"Fifty",
            or a numeric string — vocabulary is layout-defined, not a fixed
            enum), "comment" (free text set in PanelPro's block editor).

    Returns:
        {"name": ..., "state": "OCCUPIED"/"UNOCCUPIED"/"UNKNOWN"/"INCONSISTENT",
        "sensor": str|None, "value": ...|None, "length": float|None,
        "curvature": int|None, "speed": str|None, "comment": str|None}.
        "name" is the user-friendly userName if JMRI has one set, else
        falls back to the raw system name (e.g. "IB1"). "value" is included
        verbatim (not just a bool) because on layouts with train-detection
        hardware beyond simple occupancy (RFID/reporter based), it
        identifies *what* is occupying the block, not just *whether* — but
        is None on layouts (like this project's own, verified live) with
        plain occupancy sensors only. "length"/"curvature"/"speed" are
        static layout metadata (PanelPro's block editor), not live state —
        useful context for the LLM (e.g. explaining a speed restriction),
        not something this project ever writes.
    """
    return {
        "name": block.get("userName") or block.get("name"),
        "state": BLOCK_STATE_NAMES.get(block.get("state"), "UNKNOWN"),
        "sensor": block.get("sensor"),
        "value": block.get("value"),
        "length": block.get("length"),
        "curvature": block.get("curvature"),
        "speed": block.get("speed"),
        "comment": block.get("comment"),
    }


async def compact_signal(signal: dict) -> dict:
    """Reduce a raw JMRI signal mast dict to the fields worth showing the LLM.

    Args:
        signal: A signal mast dict as returned by jmri_client.get_signals(),
            with at least "name" and "aspect", and optionally "userName",
            "lit", "held", "comment" (free text set in PanelPro's signal
            mast editor).

    Returns:
        {"name": ..., "aspect": ..., "lit": bool, "held": bool,
        "dcc_system_name": str|None, "comment": str|None}. "name" is the
        user-friendly userName if JMRI has one set, else falls back to the
        raw system name. "aspect" is passed through verbatim (e.g.
        "Hp0"/"Hp1") - the valid vocabulary is defined by the mast's own
        signal system and isn't available over JMRI's JSON API, so this
        project never hardcodes or translates aspect names.
        "dcc_system_name" is the DCC connection that manages this signal
        mast, derived from its raw system name's prefix (e.g. a "Z..."
        system name -> Zou) — None if the prefix matches no known DCC
        system. "comment" is static layout metadata, not live state — None
        if never set in PanelPro.
    """
    return {
        "name": signal.get("userName") or signal.get("name"),
        "aspect": signal.get("aspect"),
        "lit": bool(signal.get("lit")),
        "held": bool(signal.get("held")),
        "dcc_system_name": await resolve_dcc_system_name(signal.get("name")),
        "comment": signal.get("comment"),
    }


def throttle_id(address: int) -> str:
    """Derive a stable JMRI throttle id from a DCC address.

    The LLM identifies a loco by its DCC address (list_roster/find_locomotive
    map a name to one) — this hides JMRI's separate "throttle" id from
    callers so tools only ever deal in addresses.

    Args:
        address: The locomotive's DCC address.

    Returns:
        A throttle id string unique to this address, e.g. "addr3".
    """
    return f"addr{address}"


def direction_name(forward: bool | None) -> str | None:
    """Translate JMRI's raw boolean "forward" field to a readable direction string.

    Args:
        forward: JMRI's raw forward field (True/False), or None if unknown.

    Returns:
        "forward", "reverse", or None if `forward` is None.
    """
    if forward is None:
        return None
    return "forward" if forward else "reverse"


def compact_throttle(data: dict) -> dict:
    """Reduce a raw JMRI throttle dict to the fields worth showing the LLM.

    Args:
        data: A throttle dict as returned by JmriWsClient.acquire_throttle(),
            with JMRI's raw "address"/"speed"/"forward" fields.

    Returns:
        {"address": ..., "speed": ..., "direction": "forward"/"reverse"/None}.
    """
    return {
        "address": data.get(FIELD_ADDRESS),
        "speed": data.get(FIELD_SPEED),
        "direction": direction_name(data.get(FIELD_FORWARD)),
    }


background_tasks: set = set()
"""Live asyncio.Task handles for fire-and-forget tool work (set_speed_ramped's
long-duration path). A plain module-level set, not per-request state, since
a task must outlive the tool call that started it. Each task removes itself
on completion (see run_in_background); server/__init__.py's shutdown awaits
whatever's left so a locomotive is never abandoned mid-ramp on a clean exit.
"""


def run_in_background(coro) -> None:
    """Schedule `coro` to run after the current tool call returns, and track it.

    Args:
        coro: An awaitable (e.g. a call to execute_speed_change(...)) to run
            without the caller waiting for it.

    The task is kept alive by a strong reference in `background_tasks`
    (asyncio only weakly references tasks created with create_task, so an
    untracked task can be silently garbage-collected mid-run) and removes
    itself from that set once done, successfully or not.
    """
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)


def check_exhibition_address_allowed(address: int) -> None:
    """Raise JmriError if exhibition mode is on and `address` isn't allow-listed.

    Args:
        address: The DCC address about to be acquired/driven.

    No-op (including when exhibition mode is off, or on with no allowlist
    configured — get_exhibition_allowed_addresses() returns None then).
    Called from acquire_throttle before ever opening a throttle for an
    address, so every other throttle tool (set_speed, set_direction,
    prepare_locomotive, ...) inherits the restriction for free via
    ensure_acquired — no need to repeat this check in each of them.
    """
    from jmri_mcp.tools.mode import is_exhibition_mode

    if not is_exhibition_mode():
        return
    allowed = get_exhibition_allowed_addresses()
    if allowed is not None and address not in allowed:
        raise JmriError(
            "exhibition_address_not_allowed",
            address=address,
            allowed=", ".join(str(a) for a in sorted(allowed)),
        )


async def resolve_prefix(address: int, prefix: str | None) -> str | None:
    """Return `prefix` unchanged if given, else auto-detect from the roster's DccSystem.

    Shared by acquire_throttle, prepare_locomotive, and ensure_acquired so
    all three agree on the same auto-detection (issue #60): an explicit
    caller-given prefix always wins; otherwise resolve_dcc_prefix(address)
    is consulted, falling back to None (JMRI's default command station) if
    the address has no roster entry, no DccSystem attribute set, or the
    roster lookup itself fails (JMRI unreachable, etc.) — never raises,
    since a failed auto-detection must not block the acquire itself.
    """
    if prefix is not None:
        return prefix
    try:
        return await resolve_dcc_prefix(address)
    except JmriError:
        return None


async def resolve_speed_scale(address: int) -> float:
    """Return the fraction (0.0-1.0) to multiply a requested speed by before sending to JMRI.

    Reads `address`'s roster max_speed_percent (PanelPro's "Throttle Speed
    Limit", see jmri_client.roster.resolve_max_speed_percent) and converts
    it to a 0.0-1.0 scale factor, defaulting to 1.0 (no scaling) if the
    roster lookup fails (JMRI unreachable, no entry) — never raises, same
    fail-open policy as resolve_prefix, since a failed lookup must not
    block a speed command.

    Why this exists: JMRI's WebSocket "speed" field is always a RAW decoder
    fraction (verified live) — unlike PanelPro's own throttle window, which
    silently scales its slider by this same per-loco limit before sending.
    Without this, a locomotive limited to 20% in its roster entry would get
    the full unscaled speed from set_speed/set_speed_ramped, moving 5x
    faster than PanelPro's throttle would for the same requested percent.
    Callers multiply their own 0.0-1.0 target fraction by this scale before
    calling client.set_speed()/execute_speed_change(), and divide a
    JMRI-reported real fraction by it before reporting speed_percent back
    to the caller, so 100% requested always means "the loco's own configured
    max", matching PanelPro's convention, not the raw decoder ceiling.
    """
    try:
        max_speed_percent = await resolve_max_speed_percent(address)
    except JmriError:
        return 1.0
    return max(1, min(100, max_speed_percent)) / 100.0


async def resolve_system_field(prefix: str | None) -> str | None:
    """Return the full system name for `prefix` if it differs from JMRI's
    default command station, else None — the shared "only report the
    system when it's non-default" rule for throttle tool return dicts
    (acquire_throttle, set_speed, set_speed_ramped, set_direction, ...).

    Never raises: a failed default-system lookup returns None (silently
    omitting the field) rather than failing the throttle command it's
    decorating. A caller adds this to its return dict conditionally:
    `if system: result["system"] = system`.
    """
    try:
        default_prefix = await default_system_prefix()
    except JmriError:
        return None
    if prefix is None or prefix == default_prefix:
        return None
    name = await resolve_system_name(prefix)
    return name or prefix


async def ensure_acquired(client, address: int) -> None:
    """Acquire the throttle for `address` if this connection doesn't hold it yet.

    JMRI rejects speed/direction/function commands on a throttle id it has
    never seen an acquire for ("Throttles must be requested with an
    address."). Tracking acquired ids client-side lets set_speed/stop/etc.
    work standalone (voice UX: "speed up the 3" without a separate acquire
    step) while still reusing the same throttle id acquire_throttle uses.

    Args:
        client: The shared JmriWsClient (see jmri_core.jmri_ws.get_ws_client).
        address: The locomotive's DCC address.

    Also enforces the exhibition-mode address allowlist (see
    check_exhibition_address_allowed) on this first acquire, so every tool
    that auto-acquires (set_speed, set_direction, set_function, ...)
    inherits the restriction without checking it individually — an
    already-acquired address is never re-checked, matching how a real
    acquire_throttle call behaves too (see that tool's own docstring).

    Issue #60: before acquiring, looks up this address's roster entry for
    a `dcc_system` (a "DccSystem" Roster Entry Attribute set in PanelPro)
    and, if set, passes it as the acquire's `prefix` so the throttle binds
    to the RIGHT command station. Without this, every auto-acquired
    throttle silently goes to JMRI's default station — harmless on a
    single-station layout, but on a multi-station one a locomotive wired
    to a secondary station (e.g. Taya) would accept speed commands
    ("succeed") that are inaudible to its actual decoder, since JMRI has
    no way to reject a command sent to the wrong station. A roster lookup
    failure here (JMRI unreachable, etc.) must not block the acquire
    itself — falls back to no prefix (JMRI's default station) rather than
    raising, same as an address with no roster entry at all.
    """
    if throttle_id(address) not in client._throttles:
        check_exhibition_address_allowed(address)
        prefix = await resolve_prefix(address, None)
        await client.acquire_throttle(throttle_id(address), address, prefix)
