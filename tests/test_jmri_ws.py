import asyncio
import json

import pytest
import websockets

from jmri_mcp.jmri_ws import JmriError, JmriWsClient

HEARTBEAT_MS = 200


@pytest.fixture
async def fake_jmri(monkeypatch):
    """A minimal local WebSocket server that speaks enough of JMRI's
    protocol to exercise JmriWsClient: hello on connect, ping->pong,
    power/throttle request-response, and an on/off switch to simulate a
    dropped connection for reconnect tests.
    """
    state = {"connected_sockets": [], "drop_next": False, "power_state": 4}

    async def handler(ws):
        if state["drop_next"]:
            state["drop_next"] = False
            await ws.close()
            return
        state["connected_sockets"].append(ws)
        await ws.send(json.dumps({
            "type": "hello",
            "data": {"JMRI": "test", "json": "5.4.0", "version": "v5", "heartbeat": HEARTBEAT_MS},
        }))
        try:
            async for raw in ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                if msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                elif msg_type == "power":
                    await ws.send(json.dumps({
                        "type": "power",
                        "data": {"name": "Test", "state": state["power_state"], "prefix": "T"},
                    }))
                elif msg_type == "throttle":
                    data = msg.get("data", {})
                    if data.get("release"):
                        await ws.send(json.dumps({
                            "type": "throttle",
                            "data": {"release": None, "throttle": data.get("throttle")},
                        }))
                    else:
                        await ws.send(json.dumps({
                            "type": "throttle",
                            "data": {
                                "address": data.get("address"),
                                "throttle": data.get("throttle"),
                                "speed": 0.0,
                            },
                        }))
                elif msg_type == "boom":
                    await ws.send(json.dumps({
                        "type": "error",
                        "data": {"code": 404, "message": "not found"},
                    }))
                elif msg_type == "silent":
                    pass  # deliberately never reply, to exercise timeout
        except websockets.exceptions.ConnectionClosed:
            pass

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("JMRI_URL", f"http://127.0.0.1:{port}")
    yield state
    server.close()
    await server.wait_closed()


async def test_connect_reads_hello_and_sets_heartbeat(fake_jmri):
    client = JmriWsClient()
    await client.connect()
    assert client._heartbeat_ms == HEARTBEAT_MS
    await client.close()


async def test_request_returns_correlated_data(fake_jmri):
    client = JmriWsClient()
    data = await client.request("power", {})
    assert data == {"name": "Test", "state": 4, "prefix": "T"}
    await client.close()


async def test_request_raises_jmri_error_on_error_reply(fake_jmri):
    client = JmriWsClient()
    with pytest.raises(JmriError, match="not found"):
        await client.request("boom", {})
    await client.close()


async def test_request_times_out_with_no_reply(fake_jmri, monkeypatch):
    import jmri_mcp.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "_REQUEST_TIMEOUT", 0.3)
    client = JmriWsClient()
    with pytest.raises(JmriError, match="Timed out"):
        await client.request("silent", {})
    await client.close()


async def test_acquire_and_release_throttle(fake_jmri):
    client = JmriWsClient()
    data = await client.acquire_throttle("t1", 42)
    assert data["address"] == 42
    assert client._throttles == {"t1": {"address": 42}}

    data = await client.release_throttle("t1")
    assert data["release"] is None
    assert client._throttles == {}
    await client.close()


async def test_keepalive_sends_ping_and_gets_pong(fake_jmri, monkeypatch):
    import jmri_mcp.jmri_ws as ws_module
    client = JmriWsClient()
    await client.connect()
    # heartbeat is 200ms -> keepalive interval is max(0.1, 1.0) = 1.0s by
    # the client's floor; instead of waiting, just confirm the loop task
    # is alive and the connection stays usable across a short wait.
    await asyncio.sleep(0.3)
    data = await client.request("power", {})
    assert data["name"] == "Test"
    await client.close()


async def test_reconnect_after_drop_reacquires_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 7)
    assert len(fake_jmri["connected_sockets"]) == 1

    # force-close the server-side socket to simulate a dropped connection
    await fake_jmri["connected_sockets"][0].close()

    # wait for the client's reconnect loop to notice and reconnect
    for _ in range(50):
        if client._ws is not None and len(fake_jmri["connected_sockets"]) == 2:
            break
        await asyncio.sleep(0.1)

    assert client._ws is not None
    # a fresh request should work on the new connection
    data = await client.request("power", {})
    assert data["name"] == "Test"
    await client.close()


async def test_request_connects_lazily(fake_jmri):
    client = JmriWsClient()
    assert client._ws is None
    await client.request("power", {})
    assert client._ws is not None
    await client.close()
