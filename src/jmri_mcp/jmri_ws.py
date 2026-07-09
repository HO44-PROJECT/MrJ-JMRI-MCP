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
next reply read from the socket is assumed to be its answer. Messages that
arrive with no request in flight are spontaneous pushes (other clients'
throttle moves, etc.) and are handed to an optional callback instead.
"""

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import websockets

from jmri_mcp.config import get_jmri_url

logger = logging.getLogger("jmri_mcp.ws")

_CONNECT_TIMEOUT = 5.0
_REQUEST_TIMEOUT = 5.0
_RECONNECT_DELAY = 2.0
_MAX_RECONNECT_DELAY = 30.0
_DEFAULT_HEARTBEAT_MS = 10_000


class JmriError(Exception):
    """JMRI is unreachable or returned an unusable response."""


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

    def __init__(self, on_event: Callable[[str, Any], Awaitable[None]] | None = None) -> None:
        self._on_event = on_event
        self._ws: websockets.ClientConnection | None = None
        self._reader_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()
        # Only one request is ever in flight on the socket (see module
        # docstring) — this is its pending reply future, or None.
        self._request_lock = asyncio.Lock()
        self._pending: asyncio.Future | None = None
        self._throttles: dict[str, dict[str, Any]] = {}
        self._heartbeat_ms = _DEFAULT_HEARTBEAT_MS
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
        self._fail_all_pending(JmriError("Connection closed"))

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

        payload = {"type": msg_type, "data": data or {}}
        try:
            assert self._ws is not None
            await self._ws.send(json.dumps(payload))
        except websockets.exceptions.WebSocketException as exc:
            self._pending = None
            raise JmriError(f"WebSocket send failed: {exc}") from exc

        try:
            return await asyncio.wait_for(future, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise JmriError(f"Timed out waiting for {msg_type!r} response") from exc
        finally:
            if self._pending is future:
                self._pending = None

    async def acquire_throttle(self, throttle_id: str, address: int) -> dict[str, Any]:
        """Acquire a throttle bound to this connection; remembered for re-acquisition."""
        data = await self.request("throttle", {"throttle": throttle_id, "address": address})
        self._throttles[throttle_id] = {"address": address}
        return data

    async def release_throttle(self, throttle_id: str) -> dict[str, Any]:
        data = await self.request("throttle", {"throttle": throttle_id, "release": True})
        self._throttles.pop(throttle_id, None)
        return data

    # -- internals ---------------------------------------------------

    async def _do_connect(self) -> None:
        url = _ws_url()
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(url), timeout=_CONNECT_TIMEOUT
            )
        except (OSError, websockets.exceptions.WebSocketException, asyncio.TimeoutError) as exc:
            self._ws = None
            raise JmriError(f"WebSocket connect to {url} failed: {exc}") from exc

        try:
            hello_raw = await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT)
            hello = json.loads(hello_raw)
            self._heartbeat_ms = hello.get("data", {}).get("heartbeat", _DEFAULT_HEARTBEAT_MS)
            logger.info(
                "Connected to JMRI WebSocket at %s (heartbeat=%dms)", url, self._heartbeat_ms
            )
        except (asyncio.TimeoutError, json.JSONDecodeError, websockets.exceptions.WebSocketException) as exc:
            await self._ws.close()
            self._ws = None
            raise JmriError(f"WebSocket handshake with {url} failed: {exc}") from exc

        self._reader_task = asyncio.create_task(self._read_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        await self._reacquire_throttles()

    async def _reacquire_throttles(self) -> None:
        for throttle_id, info in list(self._throttles.items()):
            try:
                async with self._request_lock:
                    await self._send_and_wait(
                        "throttle", {"throttle": throttle_id, "address": info["address"]}
                    )
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

        msg_type = msg.get("type")
        data = msg.get("data")
        if msg_type == "pong":
            return

        future, self._pending = self._pending, None
        if future is not None and not future.done():
            if msg_type == "error":
                future.set_exception(JmriError(f"JMRI error: {data}"))
            else:
                future.set_result(data)
            return

        if self._on_event is not None:
            await self._on_event(msg_type, data)

    async def _keepalive_loop(self) -> None:
        interval = max(self._heartbeat_ms / 1000 / 2, 1.0)
        try:
            while True:
                await asyncio.sleep(interval)
                if self._ws is None:
                    return
                try:
                    await self._ws.send(json.dumps({"type": "ping"}))
                except websockets.exceptions.WebSocketException:
                    return
        except asyncio.CancelledError:
            return

    async def _reconnect_loop(self) -> None:
        self._ws = None
        self._fail_all_pending(JmriError("Connection lost"))
        delay = _RECONNECT_DELAY
        while not self._closing:
            try:
                async with self._connect_lock:
                    await self._do_connect()
                logger.info("Reconnected to JMRI WebSocket")
                return
            except JmriError as exc:
                logger.warning("Reconnect failed, retrying in %.0fs: %s", delay, exc)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY)

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
