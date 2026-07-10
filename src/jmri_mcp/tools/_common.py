"""Shared helpers for tools/power.py, roster.py, throttle.py.

Kept here (not duplicated per-module) because acquire/set_speed/etc. all
need the same address<->throttle-id mapping and the same auto-acquire
behavior, and get_power/set_power/system_status all need the same power
compaction.
"""

POWER_STATE_NAMES = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}
LIGHT_STATE_NAMES = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "INCONSISTENT"}
TURNOUT_STATE_NAMES = {2: "CLOSED", 4: "THROWN", 0: "UNKNOWN", 8: "INCONSISTENT"}
SENSOR_STATE_NAMES = {2: "ACTIVE", 4: "INACTIVE", 0: "UNKNOWN", 8: "INCONSISTENT"}


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


def compact_light(light: dict) -> dict:
    """Reduce a raw JMRI light dict to the fields worth showing the LLM.

    Args:
        light: A light dict as returned by jmri_client.get_lights(), with
            at least "name" and "state", and optionally "userName".

    Returns:
        {"name": ..., "state": "ON"/"OFF"/"UNKNOWN"/"INCONSISTENT"}. "name"
        is the user-friendly userName if JMRI has one set, else falls back
        to the raw system name (e.g. "IL1") — this is what the LLM should
        show/match against, not JMRI's internal system name.
    """
    return {
        "name": light.get("userName") or light.get("name"),
        "state": LIGHT_STATE_NAMES.get(light.get("state"), "UNKNOWN"),
    }


def compact_turnout(turnout: dict) -> dict:
    """Reduce a raw JMRI turnout dict to the fields worth showing the LLM.

    Args:
        turnout: A turnout dict as returned by jmri_client.get_turnouts(),
            with at least "name" and "state", and optionally "userName".

    Returns:
        {"name": ..., "state": "CLOSED"/"THROWN"/"UNKNOWN"/"INCONSISTENT"}.
        "name" is the user-friendly userName if JMRI has one set, else
        falls back to the raw system name (e.g. "IT100").
    """
    return {
        "name": turnout.get("userName") or turnout.get("name"),
        "state": TURNOUT_STATE_NAMES.get(turnout.get("state"), "UNKNOWN"),
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


def compact_signal(signal: dict) -> dict:
    """Reduce a raw JMRI signal mast dict to the fields worth showing the LLM.

    Args:
        signal: A signal mast dict as returned by jmri_client.get_signals(),
            with at least "name" and "aspect", and optionally "userName",
            "lit", "held".

    Returns:
        {"name": ..., "aspect": ..., "lit": bool, "held": bool}. "name" is
        the user-friendly userName if JMRI has one set, else falls back to
        the raw system name. "aspect" is passed through verbatim (e.g.
        "Hp0"/"Hp1") - the valid vocabulary is defined by the mast's own
        signal system and isn't available over JMRI's JSON API, so this
        project never hardcodes or translates aspect names.
    """
    return {
        "name": signal.get("userName") or signal.get("name"),
        "aspect": signal.get("aspect"),
        "lit": bool(signal.get("lit")),
        "held": bool(signal.get("held")),
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
        "address": data.get("address"),
        "speed": data.get("speed"),
        "direction": direction_name(data.get("forward")),
    }


async def ensure_acquired(client, address: int) -> None:
    """Acquire the throttle for `address` if this connection doesn't hold it yet.

    JMRI rejects speed/direction/function commands on a throttle id it has
    never seen an acquire for ("Throttles must be requested with an
    address."). Tracking acquired ids client-side lets set_speed/stop/etc.
    work standalone (voice UX: "speed up the 3" without a separate acquire
    step) while still reusing the same throttle id acquire_throttle uses.

    Args:
        client: The shared JmriWsClient (see jmri_mcp.jmri_ws.get_ws_client).
        address: The locomotive's DCC address.
    """
    if throttle_id(address) not in client._throttles:
        await client.acquire_throttle(throttle_id(address), address)
