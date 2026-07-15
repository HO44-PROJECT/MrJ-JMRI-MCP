"""Throttle commands: `jmri-cli throttle [acquire|release|speed|stop|estop|direction|on|off|function|sniff]`.

Talks to jmri_ws.py. Two connection modes now coexist:
  - One-shot (the default: `client=None`): a fresh WebSocket connection is
    opened for the one command, then closed — see module docstring in
    jmri_cli for why this differs from the MCP server's single
    long-lived connection. Because that connection closes right after
    acting, JMRI itself has nothing left to query between two `jmri-cli
    throttle` invocations — state.py's local cache is what `throttle`
    (bare) and `speed <loco>` (no value) read back.
  - Shared (`client=<JmriWsClient>`, passed by cli/shell.py): the caller
    owns a long-lived connection across many commands, so a nonzero speed
    genuinely keeps the locomotive moving instead of being released the
    instant one command's connection closes — see `_client_scope()`.

Every WS-based command function below accepts an optional `client` keyword
for this reason. `speed`/`stop`/`forward`/`reverse` additionally support
ramping (`--rampup`/`--rampdown`) and, in one-shot mode only, a mandatory
`--hold` whenever the resulting speed is nonzero — seeing this
project's history of a "hold the connection open a fixed number of
seconds" hack not being a real fix (a throttle held open for exactly N
seconds just stops the locomotive at second N, not on command), one-shot
mode never holds a nonzero speed indefinitely; only the shell does.

Naming convention used throughout this module: `speed_percent` is the
CLI-facing value (a float that MAY be negative, as shorthand for
"reverse at this magnitude" — see throttle_speed), and is NEVER passed
directly to JmriWsClient. Only a resolved `*_fraction` value (always
0.0-1.0, or literally -1.0 inside throttle_estop only) ever reaches
`client.set_speed()`. This keeps the CLI-only negative-percent shorthand
strictly separate from JMRI's real wire-level emergency-stop sentinel.
"""

import argparse
import asyncio
import contextlib
import datetime
import json
import sys

from tabulate import tabulate

from jmri_core import i18n
from jmri_cli import state as _state
from jmri_cli._common import cli_throttle_id
from jmri_cli._match import find_glob, find_regex
from jmri_core.constants.cli import (
    IDLE_POLL_SECONDS,
    MAX_FUNCTION_NUMBER,
    MAX_SPEED_PERCENT,
    MIN_FUNCTION_NUMBER,
    MIN_SPEED_PERCENT,
    SNIFF_THROTTLE_ID_PREFIX,
)
from jmri_core.constants.client_tuning import STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED
from jmri_core.constants.lighting import is_light_label
from jmri_core.constants.protocol import FIELD_FORWARD
from jmri_core.jmri_client import JmriError, get_roster, get_roster_function_labels, resolve_roster_entry
from jmri_core.jmri_ws import JmriWsClient
from jmri_core.jmri_ws.ramp import execute_speed_change as _execute_speed_change

async def _resolve_address(loco: str) -> int:
    """Resolve a CLI-typed locomotive reference to a DCC address.

    Accepts a bare DCC address ("3"), a roster name, or an unambiguous
    fragment of one ("autorail"). A numeric value not found in the roster
    is still accepted as a raw address — this project has no server-side
    scan of what's actually on the DCC bus (verified live, see
    CLAUDE.md), so hardware never added to JMRI's roster must stay
    reachable by address alone.
    """
    stripped = loco.strip()
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(stripped, roster)
        return entry["address"]
    except JmriError:
        if stripped.lstrip("-").isdigit():
            return int(stripped)
        raise


def _direction_name(forward: bool) -> str:
    """Readable "forward"/"reverse" for JMRI's raw boolean direction field."""
    return "forward" if forward else "reverse"


def _throttle_headers() -> list[str]:
    """Build translated table headers for `tabulate()`, resolved at call time (not import time) so they reflect the active JMRI_MCP_LANG."""
    return [
        i18n.t("headers.address"),
        i18n.t("headers.name"),
        i18n.t("headers.speed"),
        i18n.t("headers.direction"),
        i18n.t("headers.functions_on"),
    ]


@contextlib.asynccontextmanager
async def _client_scope(client: JmriWsClient | None):
    """Yield `client` if given (shell mode — caller owns its lifecycle,
    never closed here), else construct and close a fresh one-shot client.

    Every WS-based throttle_* function routes its JMRI calls through this,
    so the same function body works identically whether called one-shot
    (client=None, from a plain `jmri-cli throttle ...` invocation) or from
    the interactive shell (client=<shared JmriWsClient>, see shell.py).
    """
    if client is not None:
        yield client
        return
    owned = JmriWsClient()
    try:
        yield owned
    finally:
        await owned.close()


async def _roster_names_by_address() -> dict[int, str]:
    """Build an {address: name} lookup from the live roster, for display only.

    Returns an empty dict (never raises) if JMRI is unreachable — callers
    fall back to "-" for the Name column rather than failing outright,
    since throttle_list/find read a local, offline-safe cache and a
    display-only roster lookup shouldn't take away that guarantee.
    """
    try:
        roster = await get_roster()
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        print(i18n.t("cli.throttle_roster_names_unavailable"), file=sys.stderr)
        return {}
    return {entry["address"]: entry["name"] for entry in roster}


async def throttle_list(args: argparse.Namespace) -> int:
    """Print last-known speed/direction/functions for every locomotive this CLI has touched.

    Reads state.py's local cache, not a live JMRI query — see this
    module's docstring for why a fresh CLI connection has nothing live to
    ask between invocations. Empty until at least one `throttle speed`/
    `direction`/`on`/`off`/etc has been run. The Name column is the one
    exception: it's resolved from a live roster lookup so it stays
    accurate even for a loco this CLI hasn't touched — falls back to "-"
    per address (not a command failure) if JMRI is unreachable or the
    address has no roster entry.

    Args:
        args: Parsed CLI arguments; no fields used.

    Returns:
        0 always (an empty cache, or JMRI being unreachable for the Name
        lookup, is not an error).
    """
    cache = _state.load_state()
    if not cache:
        print(i18n.t("cli.throttle_no_locos_touched"))
        return 0

    names = await _roster_names_by_address()
    rows = []
    for address, info in sorted(cache.items(), key=lambda kv: int(kv[0])):
        rows.append(_cache_row(int(address), name=names.get(int(address), "-"), info=info))
    print(tabulate(rows, headers=_throttle_headers()))
    return 0


def _cache_row(address: int, *, name: str = "-", info: dict | None = None) -> list:
    """Build one throttle_list-style row for `address` from state.py's local cache.

    Args:
        address: DCC address to read cached throttle state for.
        name: Roster display name, or "-" if unknown/not looked up. Callers
            that already have a roster entry in scope (throttle_find,
            _throttle_find_pattern) pass it directly instead of triggering
            a second roster fetch here.
        info: Pre-fetched cache entry for `address`, or None to look it up
            (throttle_list already has the full cache loaded and passes
            each entry in directly rather than reloading it per address).
    """
    if info is None:
        info = _state.load_state().get(str(address), {})
    speed = info.get("speed")
    speed_display = "-" if speed is None else f"{speed * 100:.0f}%"
    direction = info.get("forward")
    direction_display = "-" if direction is None else _direction_name(direction)
    functions = info.get("functions", {})
    on_functions = sorted(int(n) for n, v in functions.items() if v)
    functions_display = ", ".join(f"F{n}" for n in on_functions) or "-"
    return [address, name, speed_display, direction_display, functions_display]


async def throttle_find(args: argparse.Namespace) -> int:
    """Resolve a locomotive name/fragment/address to its roster identity and last-known throttle state.

    Read-only — resolves via the roster (same tolerant matching as `roster
    find`/`_resolve_address`) but never opens a JMRI connection; the
    speed/direction/functions shown come from state.py's local cache (see
    `throttle_list`'s docstring for why a fresh connection has nothing live
    to ask between CLI invocations), so they read "-" for a locomotive this
    CLI hasn't touched yet even if it's actually moving under JMRI/another
    client's control.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, a fragment of
            it, or a DCC address).

    Returns:
        0 on success, 1 if JMRI is unreachable or `args.loco` is ambiguous
        or matches no roster entry (a bare numeric address always resolves,
        even if absent from the roster).
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    names = await _roster_names_by_address()
    _, name, speed, direction, functions = _cache_row(address, name=names.get(address, "-"))
    print(f"address={address} name={name} speed={speed} direction={direction} functions_on={functions}")
    return 0


def _roster_label(entry: dict) -> str:
    """The name find_regex/find_glob match against: the roster entry's name."""
    return str(entry.get("name", ""))


async def _throttle_find_pattern(args: argparse.Namespace, *, regex: bool) -> int:
    """Shared body for throttle_findr/throttle_findg: list every roster entry matching a pattern.

    Filters the roster by name (same as roster_findr/findg) but shows each
    match's last-known throttle state (from state.py's local cache,
    `throttle_list`-style) instead of roster fields — the throttle-relevant
    view of a name search. Zero matches is not an error.
    """
    try:
        roster = await get_roster()
        matcher = find_regex if regex else find_glob
        matches = matcher(args.pattern, roster, _roster_label)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    if not matches:
        print(i18n.t("cli.no_roster_entries_match", pattern=args.pattern))
        return 0
    rows = [
        _cache_row(e["address"], name=_roster_label(e) or "-")
        for e in sorted(matches, key=lambda e: _roster_label(e).casefold())
    ]
    print(tabulate(rows, headers=_throttle_headers()))
    return 0


async def throttle_findr(args: argparse.Namespace) -> int:
    """List every roster entry whose name matches a regular expression (case-insensitive, re.search).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a Python regex,
            matched against each roster entry's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable or
        `args.pattern` is not a valid regex.
    """
    return await _throttle_find_pattern(args, regex=True)


async def throttle_findg(args: argparse.Namespace) -> int:
    """List every roster entry whose name matches a shell-style glob (case-insensitive, *, ?, [...]).

    Args:
        args: Parsed CLI arguments; uses `args.pattern` (a glob, matched
            against each roster entry's name).

    Returns:
        0 on success (including zero matches), 1 if JMRI is unreachable.
    """
    return await _throttle_find_pattern(args, regex=False)


async def throttle_acquire(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Acquire a loco by name/fragment/address.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address) and `args.prefix` (optional command station prefix).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire is rejected.
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    try:
        async with _client_scope(client) as c:
            data = await c.acquire_throttle(cli_throttle_id(address), address, args.prefix)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    _state.update_address(address, speed=data.get("speed"), forward=data.get("forward"))
    print(f"address={address} speed={data.get('speed')} "
          f"forward={data.get('forward')} (acquired)")
    return 0


async def throttle_release(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Acquire then immediately release a loco by name/fragment/address.

    A throttle is only meaningfully released on the connection that holds
    it — a fresh CLI connection never holds another session's throttle, so
    this acquires (JMRI just re-confirms if already held elsewhere) then
    releases on this same connection, mirroring what closing that other
    connection would do. Inside the shell, this releases it on the shell's
    own shared connection instead, which is the one actually holding it.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 on success, 1 if JMRI is unreachable or the acquire/release is
        rejected.
    """
    try:
        address = await _resolve_address(args.loco)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    try:
        async with _client_scope(client) as c:
            await c.acquire_throttle(cli_throttle_id(address), address)
            await c.release_throttle(cli_throttle_id(address))
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    print(f"address={address} released")
    return 0


async def throttle_speed(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Get or set a loco's speed.

    With no `args.speed_percent`, this acquires the loco (which resyncs on
    JMRI's real current speed) and prints it without sending any speed
    command — a read, not a write. With a value, it sets speed as 0-100%
    of maximum; a NEGATIVE value is CLI-only shorthand for "flip direction
    and go at |value|%" (e.g. `-40` means: if currently forward, switch to
    reverse at 40%; if already reverse, switch to forward at 40% — a
    TOGGLE relative to the loco's current direction, not an absolute
    "always reverse"). A POSITIVE value never touches direction, whatever
    it currently is — this is what keeps `forward`/`reverse` meaningful as
    separate commands: a plain `speed 3 40` must never silently flip a
    loco that's currently in reverse. This sign handling is resolved
    entirely client-side (reading the acquired throttle's own current
    direction) and is unrelated to JMRI's own -1.0 emergency-stop
    sentinel, which only `throttle_estop` ever sends.

    In one-shot mode (client=None), setting a nonzero speed WITHOUT
    `args.seconds` is a hard, upfront error — see module docstring for why
    a one-shot connection can never reliably hold a nonzero speed, no
    matter how long it delays before closing. Inside the shell,
    `args.seconds` is optional — omitting it holds the speed indefinitely
    (until another command or shell exit), same as today.

    Whenever `args.seconds` IS given (one-shot or shell), the loco holds
    that speed for that long, then always auto-stops before this function
    returns (ramped via `args.rampdown` if given, else instantly) — this
    applies in both modes: a one-shot invocation must never exit leaving
    the layout moving with no connection left to control it, and inside
    the shell `--hold N` means "hold for N seconds, then stop", not
    "hold forever after N seconds" (bug found live: it used to only
    auto-stop in one-shot mode, silently leaving the loco moving forever
    after the hold when run inside the shell).

    Args:
        args: Parsed CLI arguments; uses `args.loco`, `args.speed_percent`
            (0-100, may be negative, or None to just read), `args.rampup`,
            `args.rampdown`, `args.seconds` (all seconds, optional).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection,
            and enforces the mandatory-`--hold` rule above.

    Returns:
        0 on success, 1 if JMRI is unreachable or the command is rejected,
        2 if `--hold` was required but not given (one-shot mode only).
    """
    one_shot = client is None

    if args.speed_percent is not None and one_shot:
        target_percent = abs(args.speed_percent)
        if target_percent > 0 and args.seconds is None:
            print(i18n.t("cli.throttle_hold_required"), file=sys.stderr)
            return 2

    try:
        address = await _resolve_address(args.loco)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    throttle_id = cli_throttle_id(address)
    try:
        async with _client_scope(client) as c:
            acquired = await c.acquire_throttle(throttle_id, address)
            if args.speed_percent is None:
                data = acquired
            else:
                if args.speed_percent < 0:
                    info = c.throttle_state(throttle_id) or {}
                    target_forward = not info.get(FIELD_FORWARD, True)
                else:
                    target_forward = None
                target_fraction = max(
                    MIN_SPEED_PERCENT, min(MAX_SPEED_PERCENT, abs(args.speed_percent))
                ) / 100.0
                data = await _execute_speed_change(
                    c, throttle_id,
                    target_forward=target_forward, target_fraction=target_fraction,
                    rampup=args.rampup, rampdown=args.rampdown, hold_seconds=args.seconds,
                )
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    speed = data.get("speed", acquired.get("speed"))
    forward = data.get("forward")
    _state.update_address(address, speed=speed, **({"forward": forward} if forward is not None else {}))
    direction_suffix = f" direction={_direction_name(forward)}" if forward is not None else ""
    print(f"address={address} speed={(speed or 0) * 100:.0f}%{direction_suffix}")
    return 0


async def throttle_stop(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Controlled stop (speed 0) of one loco, or every touched loco if none is given.

    With no `args.loco`, this stops every locomotive state.py's local
    cache knows about — the same touched-address population bare
    `throttle` prints and `engine-start`/`engine-stop`/`on`/`off`/
    `forward`/`reverse` fall back to — regardless of whether called
    one-shot or from the shell. Locomotives never touched by this CLI (or only driven from
    a JMRI panel/other client) are out of reach here, same limitation any
    cache-driven CLI command has; use `power off` to cut power to the
    whole layout regardless of who's driving.

    `stop`'s target is always 0, so unlike `speed`/`forward`/`reverse` it
    has no `--hold`/`--rampup` flags at all — only `--rampdown`.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every cached address) and
            `args.rampdown` (seconds, optional).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every targeted loco confirmed stopped, 1 if JMRI is
        unreachable or any command was rejected.
    """
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_to_stop"), file=sys.stderr)
            return 0

    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                throttle_id = cli_throttle_id(address)
                try:
                    await c.acquire_throttle(throttle_id, address)
                    data = await _execute_speed_change(
                        c, throttle_id,
                        target_forward=None, target_fraction=0.0,
                        rampup=None, rampdown=args.rampdown, hold_seconds=None,
                    )
                    speed = data.get("speed", 0.0)
                    _state.update_address(address, speed=speed)
                    print(f"address={address} stopped")
                except JmriError as exc:
                    print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
                    ok = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return 0 if ok else 1


async def throttle_estop(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Emergency stop (JMRI decoder e-stop, speed -1.0) of one loco, or
    every touched loco if none is given. No ramp support — an emergency
    stop is a distinct decoder command that must be immediate, not gradual
    (see module docstring: JMRI's real -1.0 sentinel, never to be confused
    with `throttle_speed`'s CLI-only negative-percent shorthand).

    With no `args.loco`, this e-stops every locomotive state.py's local
    cache knows about — same "loco optional, defaults to state.py's
    touched-address cache" pattern as `on`/`off`/`stop`/`forward`/
    `reverse`/`engine-start`/`engine-stop`, not mandatory in the shell
    either. One address failing doesn't abort the rest.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every cached address).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every targeted loco confirmed emergency-stopped, 1 if JMRI is
        unreachable or any command was rejected.
    """
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_to_stop"), file=sys.stderr)
            return 0

    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                try:
                    await c.acquire_throttle(cli_throttle_id(address), address)
                    await c.set_speed(cli_throttle_id(address), -1.0)
                    _state.update_address(address, speed=-1.0)
                    print(f"address={address} emergency-stopped")
                except JmriError as exc:
                    print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
                    ok = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return 0 if ok else 1


async def _direction_one(
    address: int, args: argparse.Namespace, *, forward: bool, one_shot: bool, client: JmriWsClient
) -> int:
    """Set direction for one address. Returns 0 on success, 1 on JMRI error, 2 if --hold was required but missing."""
    throttle_id = cli_throttle_id(address)
    try:
        acquired = await client.acquire_throttle(throttle_id, address)
        current_fraction = acquired.get("speed") or 0.0

        if one_shot and current_fraction > 0.0 and args.seconds is None:
            print(i18n.t("cli.throttle_hold_required_address", address=address), file=sys.stderr)
            return 2

        data = await _execute_speed_change(
            client, throttle_id,
            target_forward=forward, target_fraction=current_fraction,
            rampup=args.rampup, rampdown=args.rampdown, hold_seconds=args.seconds,
        )
    except JmriError as exc:
        print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
        return 1

    reported = data.get("forward", forward)
    speed = data.get("speed")
    _state.update_address(address, forward=reported, **({"speed": speed} if speed is not None else {}))
    print(f"address={address} direction={_direction_name(reported)}")
    return 0


async def throttle_direction(
    args: argparse.Namespace, *, forward: bool, client: JmriWsClient | None = None
) -> int:
    """Set direction for one loco, or every touched loco if none is given, ramping speed down/back-up around the flip if moving.

    If a loco is currently moving and this changes its direction, it
    first ramps down to 0 (using `args.rampdown` if given, else instant),
    flips direction, then ramps back up to the speed magnitude it had
    before the flip (using `args.rampup` if given, else instant). If a
    loco is stationary, or already facing the requested direction, this is
    just a plain (possibly no-op) direction set — `args.rampup`/
    `args.rampdown`/`args.seconds` are accepted but have nothing to act on.

    In one-shot mode, this needs one JMRI read per address (the acquire,
    to learn the current speed) before it can know whether the
    mandatory-`--hold` rule even applies — unlike `throttle_speed`/
    `throttle_stop`, which know the target speed from `args` alone and
    can reject before contacting JMRI at all. This is an accepted,
    documented exception, not an inconsistency to "fix" later.

    With no `args.loco`, this falls back to state.py's local
    touched-address cache and applies the direction change to every one
    of them — same "loco optional, defaults to every known locomotive"
    pattern as `engine-start`/`engine-stop`/`stop`/`on`/`off`, not
    mandatory in the shell either. A per-address `--hold`-required
    rejection (one-shot mode, that address moving) does not abort the
    rest of the loop.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every locomotive in state.py's local
            touched-address cache), `args.rampup`, `args.rampdown`,
            `args.seconds` (all seconds, optional).
        forward: True for `throttle forward`, False for `throttle reverse`
            — bound via functools.partial in parser.py so "forward" and
            "reverse" are each their own leaf subcommand, not a shared one
            with a choice argument.
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection,
            and enforces the mandatory-`--hold` rule above.

    Returns:
        0 if every targeted loco's direction was set (or none were
        touched, with no `args.loco` given), 1 if JMRI is unreachable or
        any command was rejected, 2 if `--hold` was required for any
        moving loco but not given (one-shot mode only) and nothing else failed worse.
    """
    one_shot = client is None

    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_touched"))
            return 0

    worst = 0
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                code = await _direction_one(address, args, forward=forward, one_shot=one_shot, client=c)
                worst = max(worst, code)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return worst


async def _resolve_function_numbers(
    address: int, function: str | None, *, lights_only: bool = False
) -> list[int]:
    """Resolve a CLI-typed function reference to one or more function numbers.

    `function` may be a bare number ("1"), a label fragment matched
    against this loco's roster-set function labels ("phares"), or None
    (every labeled function for this loco). Raises JmriError if a
    label/None lookup finds nothing — see throttle_on/throttle_off for why
    this deliberately does NOT fall back to F0 in that case.

    `lights_only`, when True, restricts a None/label-fragment lookup to
    functions whose label matches a light keyword (see
    jmri_core.constants.lighting.is_light_label) — the CLI equivalent of
    the MCP server's set_loco_lights tool. Ignored for a bare function
    number, which is always explicit regardless of its label.
    """
    if function is not None and function.strip().lstrip("-").isdigit():
        n = int(function.strip())
        if not (MIN_FUNCTION_NUMBER <= n <= MAX_FUNCTION_NUMBER):
            raise JmriError(
                "invalid_function_number_range", min=MIN_FUNCTION_NUMBER, max=MAX_FUNCTION_NUMBER, n=n
            )
        return [n]

    roster = await get_roster()
    entry = resolve_roster_entry(str(address), roster)
    labels = await get_roster_function_labels(entry["name"])
    if lights_only:
        labels = {n: label for n, label in labels.items() if is_light_label(label)}
    if not labels:
        if lights_only:
            raise JmriError("no_light_labeled_functions", name=entry["name"])
        raise JmriError("no_labeled_functions", name=entry["name"], address=address)

    if function is None:
        return sorted(labels)

    q = function.strip().casefold()
    matches = [n for n, label in labels.items() if q in label.casefold()]
    if not matches:
        available = ", ".join(f"F{n}={label}" for n, label in sorted(labels.items()))
        raise JmriError("no_labeled_function_match", query=function, available=available)
    return sorted(matches)


async def _set_functions_one(
    address: int, function: str | None, *, state: bool, lights_only: bool, client: JmriWsClient, bulk: bool = False
) -> bool:
    """Resolve and set one or more functions for one address. Returns True on full success.

    `bulk`, when True (looping every address in state.py's touched-address
    cache because no loco was given), downgrades a `lights_only` lookup
    finding no light-labeled functions from a hard failure to a skipped
    note — a locomotive without any light-labeled function isn't a error
    in that context, unlike naming that same locomotive explicitly.
    """
    try:
        function_numbers = await _resolve_function_numbers(address, function, lights_only=lights_only)
    except JmriError as exc:
        if bulk and exc.code == "no_light_labeled_functions":
            print(i18n.t("cli.no_light_labeled_functions", name=exc.kwargs.get("name", address)))
            return True
        print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
        return False

    ok = True
    try:
        await client.acquire_throttle(cli_throttle_id(address), address)
    except JmriError as exc:
        print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
        return False
    for n in function_numbers:
        try:
            data = await client.set_function(cli_throttle_id(address), n, state)
            reported = data.get(f"F{n}", state)
            _state.update_address(address, functions={n: reported})
            print(f"address={address} F{n}={'on' if reported else 'off'}")
        except JmriError as exc:
            print(i18n.t("cli.throttle_error_function", function=n, message=str(exc)), file=sys.stderr)
            ok = False
    return ok


async def _throttle_set_functions(
    args: argparse.Namespace, *, state: bool, client: JmriWsClient | None = None
) -> int:
    """Shared body for throttle_on/throttle_off.

    With no `args.loco`, falls back to state.py's local touched-address
    cache — same "loco optional, defaults to every known locomotive"
    pattern as `engine-start`/`engine-stop`/`stop`, not mandatory in the
    shell either. `args.function` (number/label fragment/None) is applied
    identically to every targeted address.
    """
    bulk = not args.loco
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_touched"))
            return 0

    lights_only = getattr(args, "lights_only", False)
    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                if not await _set_functions_one(
                    address, args.function, state=state, lights_only=lights_only, client=c, bulk=bulk
                ):
                    ok = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return 0 if ok else 1


async def throttle_on(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Turn one or more decoder functions on, for one loco or every touched loco.

    `args.function` may be a number (F0-F28), a fragment of a roster-set
    function label ("phares" matches a label containing it), or omitted
    entirely to turn on every labeled function for this loco. There is no
    F0-is-headlight fallback: F-number meaning is decoder/roster-specific,
    not a protocol guarantee (see the jmri-mcp package's jmri_mcp.tools.throttle
    module, set_function docstring) — an unlabeled loco with no function number given is a
    clear error asking for one, not a guess.

    With no `args.loco`, this falls back to state.py's local
    touched-address cache and applies `args.function` to every one of
    them — same "loco optional, defaults to every known locomotive"
    pattern as `engine-start`/`engine-stop`/`stop`, not mandatory in the
    shell either.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every locomotive in state.py's local
            touched-address cache) and `args.function` (number, label
            fragment, or None).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every resolved function confirmed on for every targeted loco
        (or none were touched, with no `args.loco` given), 1 if JMRI is
        unreachable, nothing resolves, or any command was rejected.
    """
    return await _throttle_set_functions(args, state=True, client=client)


async def throttle_off(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Turn one or more decoder functions off, for one loco or every touched loco.

    See throttle_on for `args.function` rules and the no-`args.loco`
    cache-fallback behavior.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every locomotive in state.py's local
            touched-address cache) and `args.function` (number, label
            fragment, or None).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every resolved function confirmed off for every targeted
        loco (or none were touched, with no `args.loco` given), 1 if JMRI
        is unreachable, nothing resolves, or any command was rejected.
    """
    return await _throttle_set_functions(args, state=False, client=client)


async def _engine_start_one(address: int, prefix: str | None, *, client: JmriWsClient) -> bool:
    """Acquire, face forward, lights on for one address. Returns True on full success."""
    throttle_id = cli_throttle_id(address)
    try:
        data = await client.acquire_throttle(throttle_id, address, prefix)
        if not data.get("forward", True):
            await client.set_direction(throttle_id, True)
        function_numbers = await _resolve_function_numbers(address, None, lights_only=True)
        for n in function_numbers:
            await client.set_function(throttle_id, n, True)
    except JmriError as exc:
        if exc.code == "no_light_labeled_functions":
            function_numbers = []
        else:
            print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
            return False

    _state.update_address(address, speed=data.get("speed"), forward=True)
    print(f"address={address} started (forward, {len(function_numbers)} light function(s) on)")
    return True


async def throttle_engine_start(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Wake up one loco, or every touched loco if none is given: acquire, face forward, lights on.

    The CLI equivalent of the MCP server's prepare_locomotive tool. Does NOT
    start the locomotive moving — follow with `throttle speed` if the user
    also wants it to move. Deliberately named "engine start", not "power
    on"/"start" alone — this project already has `power on/off` for DCC
    system power, a completely different concept (cutting power reaches
    every locomotive regardless of who's driving it; this only ever
    touches one loco's own throttle/lights). Never conflate the two.

    Same "loco optional, defaults to every known locomotive" pattern as
    `engine-stop`: with no `loco`, this always falls back to state.py's
    local touched-address cache (the same list bare `throttle` prints),
    whether called one-shot or from the shell — not mandatory in the
    shell, unlike plain `throttle stop`.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every locomotive in state.py's local
            touched-address cache) and `args.prefix` (optional command
            station prefix, only meaningful with an explicit `loco`).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every targeted loco started cleanly (or none were touched,
        with no `args.loco` given), 1 if JMRI is unreachable or any
        locomotive's startup had a failing step.
    """
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_touched"))
            return 0

    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                if not await _engine_start_one(address, args.prefix, client=c):
                    ok = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return 0 if ok else 1


async def _engine_stop_one(address: int, *, client: JmriWsClient) -> bool:
    """Ramp down, face forward, lights off, release for one address. Returns True on full success."""
    throttle_id = cli_throttle_id(address)
    ok = True
    c = client
    was_acquired = throttle_id in c._throttles
    if was_acquired:
        info = c.throttle_state(throttle_id) or {}
        current_fraction = info.get("speed") or 0.0
        rampdown = current_fraction * STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED
        try:
            await _execute_speed_change(
                c, throttle_id,
                target_forward=True, target_fraction=0.0,
                rampup=0.0, rampdown=rampdown, hold_seconds=None,
            )
        except JmriError as exc:
            print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
            ok = False

    try:
        function_numbers = await _resolve_function_numbers(address, None, lights_only=True)
    except JmriError as exc:
        function_numbers = []
        if exc.code != "no_light_labeled_functions":
            print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
            ok = False

    lights_ok = True
    if function_numbers:
        try:
            await c.acquire_throttle(throttle_id, address)
        except JmriError as exc:
            print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
            ok = False
            lights_ok = False
            function_numbers = []
    for n in function_numbers:
        try:
            await c.set_function(throttle_id, n, False)
        except JmriError as exc:
            print(i18n.t("cli.throttle_error_function", function=n, message=str(exc)), file=sys.stderr)
            ok = False
            lights_ok = False

    try:
        await c.release_throttle(throttle_id)
    except JmriError as exc:
        if not lights_ok:
            print(i18n.t("cli.throttle_error_address", address=address, message=str(exc)), file=sys.stderr)
            ok = False

    _state.update_address(address, speed=0.0, forward=True)
    print(f"address={address} stopped (forward, lights off, released)")
    return ok


async def throttle_engine_stop(args: argparse.Namespace, *, client: JmriWsClient | None = None) -> int:
    """Put one loco to rest, or every touched loco if none is given: ramp down, forward, lights off, release.

    The CLI equivalent of the MCP server's park_locomotive/
    park_all_locomotives tools — same "loco optional, defaults to every
    known locomotive" philosophy as plain `throttle stop`. Unlike
    `throttle_stop`, `loco` is never mandatory, not even inside the shell:
    with no `loco`, this always targets state.py's local touched-address
    cache (the same list `jmri-cli throttle` bare prints), whether called
    one-shot or from the shell — that cache, not the shell's own
    in-memory acquired throttles, is what a user means by "every known
    locomotive" (it's disk-persisted, survives across shell restarts, and
    is exactly what the shell's own bare `throttle` status table reads).
    Rampdown duration scales with each loco's current speed (proportionally
    shorter for a loco already slow/stopped, up to
    STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED at full speed) — not a
    fixed wait. Unlike plain `throttle stop`, this also faces each loco
    forward, turns off its light-related functions, and releases its
    throttle; use plain `throttle stop` for a mid-run pause instead.
    Deliberately named "engine stop", not "power off" — see
    throttle_engine_start's docstring for why that name is reserved for
    DCC system power, a different concept entirely.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, fragment, or
            DCC address, or None for every locomotive in state.py's local
            touched-address cache).
        client: Shared connection when called from the interactive shell;
            None (default) opens and closes a fresh one-shot connection.

    Returns:
        0 if every targeted loco stopped cleanly (or none were touched,
        with no `args.loco` given), 1 if JMRI is unreachable or any
        locomotive's shutdown had a failing step.
    """
    if args.loco:
        try:
            addresses = [await _resolve_address(args.loco)]
        except JmriError as exc:
            print(i18n.error(exc), file=sys.stderr)
            return 1
    else:
        addresses = [int(a) for a in _state.load_state()]
        if not addresses:
            print(i18n.t("cli.throttle_no_locos_touched"))
            return 0

    ok = True
    try:
        async with _client_scope(client) as c:
            for address in addresses:
                if not await _engine_stop_one(address, client=c):
                    ok = False
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    return 0 if ok else 1


async def throttle_function(args: argparse.Namespace) -> int:
    """Print a locomotive's user-labeled decoder functions (F0-F28).

    Identical to `roster functions <name>`, reachable from the `throttle`
    group too since that's where a user looking to run `throttle on`/`off`
    is most likely to look first for "what functions does this loco have?".
    Read-only — no JMRI WebSocket/throttle connection involved, just the
    roster HTTP read.

    Args:
        args: Parsed CLI arguments; uses `args.loco` (name, a fragment of
            it, or a DCC address).

    Returns:
        0 on success (including no labeled functions), 1 if JMRI is
        unreachable or `args.loco` is ambiguous or matches no roster entry.
    """
    try:
        roster = await get_roster()
        entry = resolve_roster_entry(args.loco, roster)
        labels = await get_roster_function_labels(entry["name"])
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1

    print(f"{entry['name']} (address={entry['address']})")
    if not labels:
        print(i18n.t("cli.no_labeled_functions"))
        return 0
    rows = [[f"F{n}", labels[n]] for n in sorted(labels)]
    print(tabulate(rows, headers=[i18n.t("headers.function"), i18n.t("headers.label")]))
    return 0


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
                print(i18n.t("cli.sniff_acquired_for_observation", address=address))
            except JmriError as exc:
                print(i18n.t("cli.throttle_warning_could_not_acquire", address=address, message=str(exc)), file=sys.stderr)

        print(i18n.t("cli.sniff_listening"), file=sys.stderr)
        while True:
            await asyncio.sleep(IDLE_POLL_SECONDS)
    except JmriError as exc:
        print(i18n.error(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.close()
    return 0
