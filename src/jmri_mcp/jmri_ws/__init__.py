"""Persistent WebSocket client for JMRI's JSON API (ws://<jmri>/json/).

Unlike jmri_client.py (one-shot HTTP requests), a JMRI throttle is bound to
the WebSocket connection that acquired it — JMRI releases it when the
connection closes. This module keeps a single shared connection alive for
the whole server process: auto-reconnecting, keeping it alive with the
server-requested heartbeat, and re-acquiring throttles after a reconnect.

JMRI's JSON protocol has no request-id field, and error replies don't even
name the request type that caused them — verified live against JMRI 5.4.0
that concurrent requests of different types can come back in an order that
doesn't match the send order, making correlation ambiguous. So requests
are serialized: only one is ever in flight on the socket at a time, and the
next reply read from the socket is assumed to be its answer — UNLESS it's a
throttle message for a different throttle id than the one we're waiting on,
in which case it's a spontaneous push (see below) and dispatch keeps
waiting for the real reply.

Throttle state (speed, direction, functions) is not exclusively owned by
whichever connection last set it: verified live that JMRI pushes every
throttle state change to *all* connections that hold that address, not just
the one that requested it — e.g. a JMRI panel or another MCP session
changing a loco's speed shows up here too, as an unsolicited
`{"type":"throttle","data":{"throttle":"<our id>","speed":...}}` message.
Also verified live: JMRI sends no reply at all when a requested speed
already equals the current speed (a real no-op, not a dropped message) —
so requests can't rely on "no reply" meaning "something's wrong". Both
facts are handled by dispatch updating a per-throttle state cache
(`_throttles[id]["speed"/"forward"/"functions"]`) from every throttle
message seen, solicited or not; `set_speed()`/`set_direction()`/
`set_function()` read that cache immediately before acting and skip
sending if it already matches, rather than guessing from a stale value set
once at acquire time.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import websockets

from jmri_mcp.config import get_jmri_url
from jmri_mcp.constants.client_tuning import (
    WS_CONNECT_TIMEOUT_SECONDS,
    WS_DEFAULT_HEARTBEAT_MS,
    WS_MAX_RECONNECT_DELAY_SECONDS,
    WS_RECONNECT_DELAY_SECONDS,
    WS_REQUEST_TIMEOUT_SECONDS,
)
from jmri_mcp.constants.protocol import (
    FIELD_ADDRESS,
    FIELD_DATA,
    FIELD_FORWARD,
    FIELD_HEARTBEAT,
    FIELD_PREFIX,
    FIELD_RELEASE,
    FIELD_SPEED,
    FIELD_THROTTLE,
    FIELD_TYPE,
    MSG_TYPE_ERROR,
    MSG_TYPE_HELLO,
    MSG_TYPE_PING,
    MSG_TYPE_PONG,
    MSG_TYPE_THROTTLE,
)
from jmri_mcp.jmri_errors import JmriError

logger = logging.getLogger("jmri_mcp.ws")


def _ws_url() -> str:
    base = get_jmri_url()
    scheme = "wss" if base.startswith("https://") else "ws"
    host = base.split("://", 1)[1]
    return f"{scheme}://{host}/json/"


class JmriWsClient:
    """One shared, auto-reconnecting WebSocket connection to JMRI.

    Call `request(type, data)` to send a message and await its correlated
    response. Throttles acquired via `request("throttle", {...})` with an
    "address" are tracked and automatically re-acquired after a reconnect.
    """

    def __init__(
        self,
        on_event: Callable[[str, Any], Awaitable[None]] | None = None,
        on_message: Callable[[str, Any], Awaitable[None]] | None = None,
    ) -> None:
        self._on_event = on_event
        # Unlike on_event (only unsolicited pushes / messages with nothing
        # pending), on_message fires for every message this connection
        # receives, including replies to our own requests — for a passive
        # "sniff everything" observer (jmri-cli throttle sniff), not for
        # request/response logic.
        self._on_message = on_message
        self._ws: websockets.ClientConnection | None = None
        self._reader_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()
        # Only one request is ever in flight on the socket (see module
        # docstring) — this is its pending reply future, or None.
        self._request_lock = asyncio.Lock()
        self._pending: asyncio.Future | None = None
        # Throttle id the pending future is waiting on, if the in-flight
        # request is a throttle message — lets dispatch tell a real reply
        # apart from an unsolicited push about a *different* throttle.
        self._pending_throttle_id: str | None = None
        self._throttles: dict[str, dict[str, Any]] = {}
        self._heartbeat_ms = WS_DEFAULT_HEARTBEAT_MS
        self._closing = False

    async def connect(self) -> None:
        """Ensure a live connection, connecting (or reconnecting) if needed."""
        async with self._connect_lock:
            if self._ws is not None:
                return
            self._closing = False
            await self._do_connect()

    async def close(self) -> None:
        """Close the connection and stop background tasks."""
        self._closing = True
        for task in (self._reader_task, self._keepalive_task):
            if task is not None:
                task.cancel()
        if self._ws is not None:
            await self._ws.close()
        self._ws = None
        self._fail_all_pending(JmriError("connection_closed"))

    async def request(self, msg_type: str, data: dict | None = None) -> Any:
        """Send a JSON message and await its response's data.

        Serialized: only one request is in flight on the socket at a time
        (see module docstring), so this blocks if another request is
        already pending.
        """
        await self.connect()
        async with self._request_lock:
            return await self._send_and_wait(msg_type, data)

    async def _send_and_wait(self, msg_type: str, data: dict | None) -> Any:
        """Send + await a reply on the current connection, holding no locks.

        Callers must already hold _request_lock. Split out from `request()`
        so `_reacquire_throttles()` (called from inside `_do_connect()`,
        which holds `_connect_lock`) can send without re-entering
        `connect()` and deadlocking on that lock.
        """
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending = future
        # For throttle messages, remember which throttle id we're expecting
        # a reply for, so dispatch can tell a real reply apart from an
        # unsolicited push about a different throttle on the same socket.
        self._pending_throttle_id = (
            (data or {}).get(FIELD_THROTTLE) if msg_type == MSG_TYPE_THROTTLE else None
        )

        payload = {FIELD_TYPE: msg_type, FIELD_DATA: data or {}}
        try:
            assert self._ws is not None
            await self._ws.send(json.dumps(payload))
        except websockets.exceptions.WebSocketException as exc:
            self._pending = None
            self._pending_throttle_id = None
            raise JmriError("ws_send_failed", exc=exc) from exc

        try:
            return await asyncio.wait_for(future, timeout=WS_REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as exc:
            raise JmriError("ws_response_timeout", msg_type=msg_type) from exc
        finally:
            if self._pending is future:
                self._pending = None
                self._pending_throttle_id = None

    async def acquire_throttle(
        self, throttle_id: str, address: int, prefix: str | None = None
    ) -> dict[str, Any]:
        """Acquire a throttle bound to this connection; remembered for re-acquisition.

        prefix optionally targets a specific command station (e.g. "R" for
        DCC++ Raijin) when more than one is connected to JMRI.

        Idempotent per connection: re-acquiring a throttle_id this same
        connection already holds is a no-op that returns the live cache
        instead of re-sending the wire request — verified live that JMRI
        crashes the connection (ConnectionClosedError) on a genuine
        duplicate acquire (see CLAUDE.md). Every WS-based throttle_*
        command in cli/throttle.py calls acquire_throttle() unconditionally
        before acting, which is harmless in one-shot mode (fresh connection
        every time) but, without this check, corrupted the interactive
        shell's shared connection on a second command touching an address
        already acquired earlier in the same session (reproduced live:
        `throttle speed 4 5` then `throttle stop 4` in the same shell
        session timed out on the second command).
        """
        await self.connect()
        cached = self._throttles.get(throttle_id)
        if (
            cached is not None
            and cached.get(FIELD_ADDRESS) == address
            and cached.get(FIELD_PREFIX) == prefix
        ):
            return dict(cached)
        self._throttles[throttle_id] = {FIELD_ADDRESS: address, FIELD_PREFIX: prefix, FIELD_SPEED: None}
        data_out: dict[str, Any] = {FIELD_THROTTLE: throttle_id, FIELD_ADDRESS: address}
        if prefix:
            data_out[FIELD_PREFIX] = prefix
        try:
            async with self._request_lock:
                data = await self._send_and_wait(MSG_TYPE_THROTTLE, data_out)
        except JmriError:
            self._throttles.pop(throttle_id, None)
            raise
        return data

    async def release_throttle(self, throttle_id: str) -> dict[str, Any]:
        data = await self.request(
            MSG_TYPE_THROTTLE, {FIELD_THROTTLE: throttle_id, FIELD_RELEASE: True}
        )
        self._throttles.pop(throttle_id, None)
        return data

    async def set_speed(self, throttle_id: str, speed: float) -> dict[str, Any]:
        """Set speed on an already-acquired throttle. -1.0 is JMRI's emergency stop.

        Verified live: JMRI sends no reply at all when the requested speed
        already matches the throttle's current speed (a real no-op, not a
        dropped message) — so we check the current cached speed first and
        skip sending if it's already there. That cache isn't just "what we
        last set": JMRI pushes throttle state changes made by *other*
        clients (a JMRI panel, another session) to every connection holding
        that address too, and dispatch keeps it updated from those pushes
        as well as from our own replies — see module docstring.
        """
        info = self._throttles.get(throttle_id)
        if info is not None and info.get(FIELD_SPEED) == speed:
            return {FIELD_THROTTLE: throttle_id, FIELD_SPEED: speed}
        return await self.request(MSG_TYPE_THROTTLE, {FIELD_THROTTLE: throttle_id, FIELD_SPEED: speed})

    async def set_direction(self, throttle_id: str, forward: bool) -> dict[str, Any]:
        """Set direction on an already-acquired throttle. Same no-op/cache logic as set_speed.

        Verified live: JMRI sends no reply at all when the requested
        direction already matches the current one, for the same reason as
        speed (see set_speed and the module docstring) — checked against
        the same live-synced per-throttle cache before sending.
        """
        info = self._throttles.get(throttle_id)
        if info is not None and info.get(FIELD_FORWARD) == forward:
            return {FIELD_THROTTLE: throttle_id, FIELD_FORWARD: forward}
        return await self.request(
            MSG_TYPE_THROTTLE, {FIELD_THROTTLE: throttle_id, FIELD_FORWARD: forward}
        )

    async def emergency_stop_all(self) -> dict[str, list[str]]:
        """Emergency-stop every locomotive this connection currently holds a throttle for.

        Iterates `_throttles` (every address acquired on this connection,
        not just ones this call touches) and sends the same speed=-1.0
        decoder e-stop as `set_speed(throttle_id, -1.0)` to each, reusing
        its existing no-op-skip/cache logic — a loco already at -1.0 (e.g.
        already e-stopped by another client) is silently skipped, not
        resent. Does NOT reach locomotives held only by some other JMRI
        client/connection (there is no "stop every throttle in JMRI"
        server-side call — see module docstring on why cross-connection
        control doesn't exist for throttles the way it does for pushes).

        Returns:
            {"stopped": [...ids successfully e-stopped...],
             "failed": [...ids that raised an error...]}. A `throttle_id`
            with no error is not necessarily freshly-sent (see no-op above)
            but IS confirmed at -1.0 either way, since the no-op path only
            triggers when the cache already reads -1.0.
        """
        stopped: list[str] = []
        failed: list[str] = []
        for tid in list(self._throttles):
            try:
                await self.set_speed(tid, -1.0)
                stopped.append(tid)
            except JmriError as exc:
                logger.warning("emergency_stop_all: failed to stop %r: %s", tid, exc)
                failed.append(tid)
        return {"stopped": stopped, "failed": failed}

    async def set_function(self, throttle_id: str, function: int, state: bool) -> dict[str, Any]:
        """Set a decoder function (F0-F28) on an already-acquired throttle.

        Same no-op/cache logic as set_speed/set_direction, applied per
        function key: the per-throttle cache keeps a "functions" dict
        (`{0: False, 1: True, ...}`) fed from every throttle message seen
        for this id, solicited or not, so a repeat call — or a function
        last toggled by another client — resolves from live state instead
        of blindly resending.
        """
        info = self._throttles.get(throttle_id)
        if info is not None and info.get("functions", {}).get(function) == state:
            return {FIELD_THROTTLE: throttle_id, f"F{function}": state}
        return await self.request(
            MSG_TYPE_THROTTLE, {FIELD_THROTTLE: throttle_id, f"F{function}": state}
        )

    def throttle_state(self, throttle_id: str) -> dict[str, Any] | None:
        """Read-only snapshot of the live-synced cache for one throttle id.

        Callers (cli/throttle.py, cli/shell.py) use this instead of reaching
        into the private `_throttles` dict directly.
        """
        state = self._throttles.get(throttle_id)
        return dict(state) if state is not None else None

    def all_throttle_states(self) -> dict[str, dict[str, Any]]:
        """Read-only snapshot of every throttle id's cache, keyed by throttle id."""
        return {tid: dict(state) for tid, state in self._throttles.items()}

    # -- internals ---------------------------------------------------

    async def _do_connect(self) -> None:
        url = _ws_url()
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(url), timeout=WS_CONNECT_TIMEOUT_SECONDS
            )
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as exc:
            self._ws = None
            raise JmriError("ws_connect_failed", url=url, exc=exc) from exc

        try:
            hello_raw = await asyncio.wait_for(self._ws.recv(), timeout=WS_CONNECT_TIMEOUT_SECONDS)
            hello = json.loads(hello_raw)
            self._heartbeat_ms = hello.get(FIELD_DATA, {}).get(FIELD_HEARTBEAT, WS_DEFAULT_HEARTBEAT_MS)
            logger.info(
                "Connected to JMRI WebSocket at %s (heartbeat=%dms)", url, self._heartbeat_ms
            )
        except (asyncio.TimeoutError, json.JSONDecodeError, websockets.exceptions.WebSocketException) as exc:
            await self._ws.close()
            self._ws = None
            raise JmriError("ws_handshake_failed", url=url, exc=exc) from exc

        self._reader_task = asyncio.create_task(self._read_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        await self._reacquire_throttles()

    async def _reacquire_throttles(self) -> None:
        for throttle_id, info in list(self._throttles.items()):
            try:
                data_out = {FIELD_THROTTLE: throttle_id, FIELD_ADDRESS: info[FIELD_ADDRESS]}
                if info.get(FIELD_PREFIX):
                    data_out[FIELD_PREFIX] = info[FIELD_PREFIX]
                async with self._request_lock:
                    # _dispatch updates _throttles[throttle_id] from the
                    # reply itself (a fresh acquire resets JMRI's speed to
                    # 0, so this also resyncs our cache to match).
                    await self._send_and_wait(MSG_TYPE_THROTTLE, data_out)
            except JmriError as exc:
                logger.warning("Failed to re-acquire throttle %r after reconnect: %s", throttle_id, exc)

    async def _read_loop(self) -> None:
        assert self._ws is not None
        ws = self._ws
        try:
            async for raw in ws:
                await self._dispatch(raw)
        except websockets.exceptions.WebSocketException as exc:
            logger.warning("WebSocket read loop ended: %s", exc)
        if not self._closing:
            asyncio.create_task(self._reconnect_loop())

    async def _dispatch(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ignoring non-JSON WebSocket message: %r", raw)
            return

        msg_type = msg.get(FIELD_TYPE)
        data = msg.get(FIELD_DATA)
        if self._on_message is not None:
            await self._on_message(msg_type, data)
        if msg_type == MSG_TYPE_PONG:
            return

        if msg_type == MSG_TYPE_THROTTLE and isinstance(data, dict):
            self._update_throttle_cache(data)

        # A throttle message is only "our" reply if it names the throttle id
        # we're waiting on — otherwise it's an unsolicited push about a
        # different throttle (e.g. another client's loco) sharing this
        # socket, and the real reply is still to come.
        is_throttle_push = (
            msg_type == MSG_TYPE_THROTTLE
            and self._pending_throttle_id is not None
            and isinstance(data, dict)
            and data.get(FIELD_THROTTLE) != self._pending_throttle_id
        )
        if is_throttle_push:
            if self._on_event is not None:
                await self._on_event(msg_type, data)
            return

        future, self._pending = self._pending, None
        self._pending_throttle_id = None
        if future is not None and not future.done():
            if msg_type == MSG_TYPE_ERROR:
                future.set_exception(JmriError("ws_jmri_error", data=data))
            else:
                future.set_result(data)
            return

        if self._on_event is not None:
            await self._on_event(msg_type, data)

    def _update_throttle_cache(self, data: dict[str, Any]) -> None:
        throttle_id = data.get(FIELD_THROTTLE)
        info = self._throttles.get(throttle_id) if throttle_id else None
        if info is None:
            return
        if FIELD_SPEED in data:
            info[FIELD_SPEED] = data[FIELD_SPEED]
        if FIELD_FORWARD in data:
            info[FIELD_FORWARD] = data[FIELD_FORWARD]
        functions = info.setdefault("functions", {})
        for key, value in data.items():
            if key and key[0] == "F" and key[1:].isdigit():
                functions[int(key[1:])] = value

    async def _keepalive_loop(self) -> None:
        interval = max(self._heartbeat_ms / 1000 / 2, 1.0)
        try:
            while True:
                await asyncio.sleep(interval)
                if self._ws is None:
                    return
                try:
                    await self._ws.send(json.dumps({FIELD_TYPE: MSG_TYPE_PING}))
                except websockets.exceptions.WebSocketException:
                    return
        except asyncio.CancelledError:
            return

    async def _reconnect_loop(self) -> None:
        self._ws = None
        self._fail_all_pending(JmriError("connection_lost"))
        delay = WS_RECONNECT_DELAY_SECONDS
        while not self._closing:
            try:
                async with self._connect_lock:
                    await self._do_connect()
                logger.info("Reconnected to JMRI WebSocket")
                return
            except JmriError as exc:
                logger.warning("Reconnect failed, retrying in %.0fs: %s", delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, WS_MAX_RECONNECT_DELAY_SECONDS)

    def _fail_all_pending(self, exc: Exception) -> None:
        future, self._pending = self._pending, None
        if future is not None and not future.done():
            future.set_exception(exc)


_client: JmriWsClient | None = None


def get_ws_client() -> JmriWsClient:
    """Return the process-wide shared JmriWsClient, creating it lazily."""
    global _client
    if _client is None:
        _client = JmriWsClient()
    return _client
