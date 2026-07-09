import json
from pathlib import Path

import pytest
import respx
import websockets
from httpx import Response

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_JMRI_URL = "http://mock-jmri:12080"
WS_HEARTBEAT_MS = 200


@pytest.fixture(autouse=True)
def jmri_url(monkeypatch):
    """Point every test at a fake host by default; mocked via respx, never hits the network."""
    monkeypatch.setenv("JMRI_URL", MOCK_JMRI_URL)


@pytest.fixture(autouse=True)
def reset_ws_client():
    """Reset jmri_ws's process-wide singleton so tests don't leak connection state."""
    import jmri_mcp.jmri_ws as ws_module

    ws_module._client = None
    yield
    ws_module._client = None


@pytest.fixture
def power_fixture() -> list[dict]:
    return json.loads((FIXTURES / "power_response.json").read_text())


@pytest.fixture
def mock_power(power_fixture):
    """Mock GET /json/power to return the captured JMRI 5.4 fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=power_fixture)
        )
        yield router


@pytest.fixture
def version_fixture() -> list[dict]:
    return json.loads((FIXTURES / "version_response.json").read_text())


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
            "data": {"JMRI": "test", "json": "5.4.0", "version": "v5", "heartbeat": WS_HEARTBEAT_MS},
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
                        reply_data = {
                            "address": data.get("address"),
                            "throttle": data.get("throttle"),
                            "speed": 0.0,
                            "forward": True,
                        }
                        if data.get("prefix"):
                            reply_data["prefix"] = data["prefix"]
                        await ws.send(json.dumps({"type": "throttle", "data": reply_data}))
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
