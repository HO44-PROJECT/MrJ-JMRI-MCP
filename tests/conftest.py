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
def jmri_mcp_lang(monkeypatch):
    """Pin JMRI_MCP_LANG=en so the suite doesn't silently assert French output
    if a developer's shell profile happens to export a different language."""
    monkeypatch.setenv("JMRI_MCP_LANG", "en")


def expect_error(code: str, **kwargs) -> str:
    """Render an errors.<code> template from en.json, for asserting against
    JmriError output without re-typing production English as a second,
    silently-divergent literal in the test."""
    from jmri_mcp.i18n import lookup

    return lookup("en", f"errors.{code}", **kwargs)


@pytest.fixture(autouse=True)
def reset_ws_client():
    """Reset jmri_ws's process-wide singleton so tests don't leak connection state."""
    import jmri_mcp.jmri_ws as ws_module

    ws_module._client = None
    yield
    ws_module._client = None


@pytest.fixture(autouse=True)
def isolated_cli_state(monkeypatch, tmp_path):
    """Point jmri-cli's local throttle-state cache at a tmp file, never the
    real user's ~/.jmri-cli/throttle_state.json."""
    import jmri_mcp.cli.state as state_module

    monkeypatch.setattr(state_module, "STATE_FILE", tmp_path / "throttle_state.json")


@pytest.fixture(autouse=True)
def reset_executor_mode():
    """Reset tools.mode's process-wide flag so tests don't leak state across each other."""
    import jmri_mcp.tools.mode as mode_module

    mode_module._executor_mode = False
    yield
    mode_module._executor_mode = False


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
def lights_fixture() -> list[dict]:
    return json.loads((FIXTURES / "lights_response.json").read_text())


@pytest.fixture
def mock_lights(lights_fixture):
    """Mock GET /json/lights to return the captured JMRI 5.4-shaped fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=lights_fixture)
        )
        yield router


@pytest.fixture
def turnouts_fixture() -> list[dict]:
    return json.loads((FIXTURES / "turnouts_response.json").read_text())


@pytest.fixture
def mock_turnouts(turnouts_fixture):
    """Mock GET /json/turnouts to return the captured JMRI 5.4-shaped fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=turnouts_fixture)
        )
        yield router


@pytest.fixture
def sensors_fixture() -> list[dict]:
    return json.loads((FIXTURES / "sensors_response.json").read_text())


@pytest.fixture
def mock_sensors(sensors_fixture):
    """Mock GET /json/sensors to return the captured JMRI 5.4-shaped fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/sensors").mock(
            return_value=Response(200, json=sensors_fixture)
        )
        yield router


@pytest.fixture
def signals_fixture() -> list[dict]:
    return json.loads((FIXTURES / "signal_masts_response.json").read_text())


@pytest.fixture
def mock_signals(signals_fixture):
    """Mock GET /json/signalMasts to return the captured JMRI 5.4-shaped fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=signals_fixture)
        )
        yield router


@pytest.fixture
def roster_fixture() -> list[dict]:
    return json.loads((FIXTURES / "roster_response.json").read_text())


@pytest.fixture
def mock_roster(roster_fixture):
    """Mock GET /json/roster to return the captured JMRI 5.4 fixture (3 entries)."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(
            return_value=Response(200, json=roster_fixture)
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

    Also mirrors two real-JMRI behaviors verified live (see jmri_ws.py's
    module docstring), since they're what motivated the cache/correlation
    redesign and need real coverage, not just live-server spot checks:
      - silent no-op: no reply is sent when a requested speed/forward/F<n>
        already equals the address's current state.
      - cross-connection push: a state change on one connection is pushed,
        unprompted, to every OTHER connection that also holds the same
        address (keyed by "throttle" id on each connection).
    """
    state = {
        "connected_sockets": [],
        "drop_next": False,
        "power_state": 4,
        "acquired": set(),  # throttle ids acquired on *some* connection
        # address -> {"speed": float, "forward": bool, "functions": {int: bool}}
        "loco_state": {},
        # address -> list of (ws, throttle_id) holding it, across connections
        "holders": {},
    }

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
                    throttle_id = data.get("throttle")
                    if data.get("release"):
                        state["acquired"].discard(throttle_id)
                        for holders in state["holders"].values():
                            holders[:] = [h for h in holders if h[1] != throttle_id]
                        await ws.send(json.dumps({
                            "type": "throttle",
                            "data": {"release": None, "throttle": throttle_id},
                        }))
                    elif "address" not in data:
                        # a speed/direction/function command with no prior acquire
                        # on this connection — mirrors JMRI's real rejection.
                        if throttle_id not in state["acquired"]:
                            await ws.send(json.dumps({
                                "type": "error",
                                "data": {"code": 400, "message": "Throttles must be requested with an address."},
                            }))
                            continue
                        address = next(
                            (addr for addr, holders in state["holders"].items()
                             if any(h[1] == throttle_id for h in holders)),
                            None,
                        )
                        current = state["loco_state"].setdefault(
                            address, {"speed": 0.0, "forward": True, "functions": {}}
                        )
                        changed = {}
                        if "speed" in data and data["speed"] != current.get("speed"):
                            changed["speed"] = data["speed"]
                        if "forward" in data and data["forward"] != current.get("forward"):
                            changed["forward"] = data["forward"]
                        for key, value in data.items():
                            if key[0] == "F" and key[1:].isdigit():
                                if value != current["functions"].get(key):
                                    changed[key] = value
                        if not changed:
                            # real JMRI: silently drops a no-op request, no reply at all.
                            continue
                        for key, value in changed.items():
                            if key[0] == "F" and key[1:].isdigit():
                                current["functions"][key] = value
                            else:
                                current[key] = value
                        for holder_ws, holder_id in state["holders"].get(address, []):
                            reply_data = {"throttle": holder_id, **changed}
                            await holder_ws.send(json.dumps({"type": "throttle", "data": reply_data}))
                    else:
                        address = data["address"]
                        state["acquired"].add(throttle_id)
                        state["holders"].setdefault(address, [])
                        state["holders"][address] = [
                            h for h in state["holders"][address] if h[1] != throttle_id
                        ] + [(ws, throttle_id)]
                        loco = state["loco_state"].setdefault(
                            address, {"speed": 0.0, "forward": True, "functions": {}}
                        )
                        reply_data = {
                            "address": address,
                            "throttle": throttle_id,
                            "speed": loco["speed"],
                            "forward": loco["forward"],
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
        finally:
            for holders in state["holders"].values():
                holders[:] = [h for h in holders if h[0] is not ws]

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("JMRI_URL", f"http://127.0.0.1:{port}")
    yield state
    server.close()
    await server.wait_closed()
