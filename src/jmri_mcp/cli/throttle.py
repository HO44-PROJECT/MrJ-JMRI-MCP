"""Throttle commands: `jmri-cli throttle acquire/release/speed/stop/estop/direction/function/lights-on/lights-off/sniff`.

Talks to jmri_ws.py — a fresh WebSocket connection for the one command,
then closed (see module docstring in jmri_mcp.cli for why this differs
from the MCP server's single long-lived connection).
"""

import argparse
import asyncio
import datetime
import json
import sys

from jmri_mcp.cli._common import cli_throttle_id
from jmri_mcp.cli.constants import (
    IDLE_POLL_SECONDS,
    MAX_FUNCTION_NUMBER,
    MAX_SPEED_PERCENT,
    MIN_FUNCTION_NUMBER,
    MIN_SPEED_PERCENT,
    SNIFF_THROTTLE_ID_PREFIX,
)
from jmri_mcp.jmri_client import JmriError as JmriHttpError
from jmri_mcp.jmri_client import get_roster
from jmri_mcp.jmri_ws import JmriError as JmriWsError
from jmri_mcp.jmri_ws import JmriWsClient


async def throttle_acquire(args: argparse.Namespace) -> int:
    """Acquire a loco by DCC address on a fresh connection, then release it.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address) and
            `args.prefix` (optional command station prefix).

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire is rejected.
    """
    client = JmriWsClient()
    try:
        data = await client.acquire_throttle(cli_throttle_id(args.address), args.address, args.prefix)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={data.get('address')} speed={data.get('speed')} "
          f"forward={data.get('forward')} (acquired)")
    return 0


async def throttle_release(args: argparse.Namespace) -> int:
    """Acquire then immediately release a loco by DCC address.

    A throttle is only meaningfully released on the connection that holds
    it — a fresh CLI connection never holds another session's throttle, so
    this acquires (JMRI just re-confirms if already held elsewhere) then
    releases on this same connection, mirroring what closing that other
    connection would do.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address).

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire/release is
        rejected.
    """
    client = JmriWsClient()
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        await client.release_throttle(cli_throttle_id(args.address))
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} released")
    return 0


async def throttle_speed(args: argparse.Namespace) -> int:
    """Set a loco's speed as a 0-100% of maximum, on a fresh connection.

    NOTE (2026-07-09): a throttle only means anything on the connection
    holding it - JMRI releases it the moment this connection closes, and
    verified live, a plain acquire/set/close one-shot does not reliably
    keep the real locomotive moving at the requested speed. A "hold the
    connection open until Ctrl-C" version (like `sniff`) was tried, but
    disabled per user request: on Ctrl-C the loco kept coasting at the
    last speed instead of stopping, because closing the socket releases
    the throttle without sending a stop first - a worse surprise than the
    one-shot's unreliability. Left commented out below rather than
    deleted; needs a real fix (e.g. send speed 0 before closing on
    Ctrl-C) before re-enabling, not reverted from history if needed:

        print(f"address={args.address} speed={data.get('speed', speed) * 100:.0f}%")
        if speed == 0.0:
            await client.close()
            return 0
        print("Holding throttle open, Ctrl-C to release...", file=sys.stderr)
        try:
            while True:
                await asyncio.sleep(IDLE_POLL_SECONDS)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await client.close()
        print(f"address={args.address} throttle released")
        return 0

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address) and
            `args.speed_percent` (0-100, clamped).

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected.
    """
    client = JmriWsClient()
    speed = max(MIN_SPEED_PERCENT, min(MAX_SPEED_PERCENT, args.speed_percent)) / 100.0
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        data = await client.set_speed(cli_throttle_id(args.address), speed)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} speed={data.get('speed', speed) * 100:.0f}%")
    return 0


async def throttle_stop(args: argparse.Namespace) -> int:
    """Controlled stop (speed 0) on a fresh connection.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address).

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected.
    """
    client = JmriWsClient()
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        await client.set_speed(cli_throttle_id(args.address), 0.0)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} stopped")
    return 0


async def throttle_estop(args: argparse.Namespace) -> int:
    """Emergency stop (JMRI decoder e-stop, speed -1.0) on a fresh connection.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address).

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected.
    """
    client = JmriWsClient()
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        await client.set_speed(cli_throttle_id(args.address), -1.0)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    print(f"address={args.address} emergency-stopped")
    return 0


async def throttle_stop_all(args: argparse.Namespace) -> int:
    """Emergency-stop EVERY roster locomotive at once, on one fresh connection.

    Unlike the MCP tool's emergency_stop_all() (which iterates whatever
    this long-lived session already has acquired), a CLI invocation starts
    with nothing acquired — so "all" is resolved from JMRI's own roster
    (get_roster()) rather than requiring the caller to type every address
    by hand, the same way `power stop-all` needs no arguments. This only
    reaches roster-known addresses: JMRI has no server-side scan of what's
    actually on the DCC bus (no RailCom/reporters, no "list active
    throttles" call — verified live), so hardware never added to the
    roster is out of reach here, the same limitation any roster-driven
    tool in this project has.

    Pass -a/--address (repeatable) to limit the stop to specific addresses
    instead of the whole roster.

    Args:
        args: Parsed CLI arguments; uses `args.address` (list of DCC
            addresses, or None to use every roster entry).

    Returns:
        0 if every resolved address was acquired and stopped, 1 if JMRI is
        unreachable or any address failed to resolve/acquire/stop.
    """
    if args.address:
        addresses = args.address
    else:
        try:
            addresses = [entry["address"] for entry in await get_roster()]
        except JmriHttpError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if not addresses:
            print("Roster is empty, nothing to stop.", file=sys.stderr)
            return 0

    client = JmriWsClient()
    failed_acquire: list[int] = []
    try:
        for address in addresses:
            try:
                await client.acquire_throttle(cli_throttle_id(address), address)
            except JmriWsError as exc:
                print(f"Warning: could not acquire {address}: {exc}", file=sys.stderr)
                failed_acquire.append(address)
        result = await client.emergency_stop_all()
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    to_address = {cli_throttle_id(a): a for a in addresses}
    for tid in result["stopped"]:
        print(f"address={to_address.get(tid, tid)} emergency-stopped")
    for tid in result["failed"]:
        print(f"address={to_address.get(tid, tid)} FAILED to stop", file=sys.stderr)
    return 1 if (result["failed"] or failed_acquire) else 0


async def throttle_direction(args: argparse.Namespace) -> int:
    """Set a loco's direction (forward/reverse) on a fresh connection.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address) and
            `args.direction` ("forward" or "reverse").

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected.
    """
    client = JmriWsClient()
    forward = args.direction == "forward"
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        data = await client.set_direction(cli_throttle_id(args.address), forward)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    reported = "forward" if data.get("forward", forward) else "reverse"
    print(f"address={args.address} direction={reported}")
    return 0


async def throttle_function(args: argparse.Namespace) -> int:
    """Set a decoder function (F0-F28) on or off, on a fresh connection.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address),
            `args.function` (function number, validated 0-28 locally
            before contacting JMRI), and `args.state` ("on" or "off").

    Returns:
        0 on success, 1 if the function number is out of range, JMRI is
        unreachable, or the command is rejected.
    """
    if not (MIN_FUNCTION_NUMBER <= args.function <= MAX_FUNCTION_NUMBER):
        print(f"Error: function must be {MIN_FUNCTION_NUMBER}-{MAX_FUNCTION_NUMBER}, "
              f"got {args.function}", file=sys.stderr)
        return 1
    client = JmriWsClient()
    state = args.state == "on"
    try:
        await client.acquire_throttle(cli_throttle_id(args.address), args.address)
        data = await client.set_function(cli_throttle_id(args.address), args.function, state)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.close()

    reported = "on" if data.get(f"F{args.function}", state) else "off"
    print(f"address={args.address} F{args.function}={reported}")
    return 0


async def throttle_lights_on(args: argparse.Namespace) -> int:
    """Shortcut for `throttle_function` with F0 on (near-universal DCC headlight).

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address).
            `args.function`/`args.state` are set here before delegating.

    Returns:
        Same as `throttle_function`.
    """
    args.function, args.state = 0, "on"
    return await throttle_function(args)


async def throttle_lights_off(args: argparse.Namespace) -> int:
    """Shortcut for `throttle_function` with F0 off.

    Args:
        args: Parsed CLI arguments; uses `args.address` (DCC address).
            `args.function`/`args.state` are set here before delegating.

    Returns:
        Same as `throttle_function`.
    """
    args.function, args.state = 0, "off"
    return await throttle_function(args)


def _format_sniff_data(msg_type: str, data) -> str:
    """Compact a JMRI message's data for one-line display.

    Throttle messages list every function key (F0-F68) even when only one
    changed, which drowns the field that actually changed — collapse them
    to just the functions currently ON, dropped entirely if none are.

    Args:
        msg_type: JMRI's message "type" field (e.g. "throttle", "pong").
        data: JMRI's message "data" field, of whatever shape `msg_type` implies.

    Returns:
        A JSON string of `data`, with active F<n> fields collapsed into a
        single "functions_on" list when `msg_type` is "throttle".
    """
    if msg_type == "throttle" and isinstance(data, dict):
        data = dict(data)
        active_functions = sorted(
            (k for k, v in data.items() if k[0] == "F" and k[1:].isdigit() and v),
            key=lambda k: int(k[1:]),
        )
        for key in list(data):
            if key[0] == "F" and key[1:].isdigit():
                del data[key]
        if active_functions:
            data["functions_on"] = active_functions
    return json.dumps(data)


async def throttle_sniff(args: argparse.Namespace) -> int:
    """Dump every JMRI WebSocket message on this connection until Ctrl-C.

    With no --address, this only sees hello/pong and whatever this
    connection itself triggers. Pass --address (repeatable) to also acquire
    those locos first — JMRI then pushes every state change on them from
    ANY client (other MCP sessions, JMRI panels, throttle apps) to this
    connection too, which is the point: watching what's actually moving on
    the layout, not just what this tool sends. Keepalive pong messages are
    hidden by default (--show-pong to include them) since they carry no
    information and fire every few seconds regardless of layout activity.

    Args:
        args: Parsed CLI arguments; uses `args.address` (list of DCC
            addresses to acquire first, or None) and `args.show_pong`
            (whether to print keepalive pong messages).

    Returns:
        0 on a clean Ctrl-C exit, 1 if the connection itself errors out.
    """

    async def on_message(msg_type: str, data) -> None:
        if msg_type == "pong" and not args.show_pong:
            return
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] {msg_type}: {_format_sniff_data(msg_type, data)}")

    client = JmriWsClient(on_message=on_message)
    try:
        await client.connect()
        for address in args.address or []:
            try:
                await client.acquire_throttle(f"{SNIFF_THROTTLE_ID_PREFIX}{address}", address)
                print(f"(acquired address={address} for observation)")
            except JmriWsError as exc:
                print(f"Warning: could not acquire {address}: {exc}", file=sys.stderr)

        print("Listening for JMRI messages, Ctrl-C to stop...", file=sys.stderr)
        while True:
            await asyncio.sleep(IDLE_POLL_SECONDS)
    except JmriWsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.close()
    return 0
