import json

from mcp.server.fastmcp import FastMCP

from jmri_mcp import tools


def make_server() -> FastMCP:
    mcp = FastMCP("test")
    tools.register(mcp)
    return mcp


async def call(mcp: FastMCP, name: str, **kwargs) -> dict:
    result = await mcp.call_tool(name, kwargs)
    return json.loads(result[0].text)


async def test_list_systems_registered_and_compact(mock_power):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert {"list_systems", "get_power"} <= tool_names

    out = await call(mcp, "list_systems")
    assert out == {
        "systems": [
            {"name": "DCC++ Ohara", "state": "OFF", "default": False},
            {"name": "DCC++ Zou", "state": "OFF", "default": False},
            {"name": "DCC++ Raijin", "state": "OFF", "default": True},
        ]
    }


async def test_list_systems_reports_jmri_error_without_raising(monkeypatch):
    import respx
    from httpx import ConnectError

    from tests.conftest import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=ConnectError("refused"))
        out = await call(mcp, "list_systems")
    assert "error" in out


async def test_get_power_resolves_by_fragment(mock_power):
    mcp = make_server()
    out = await call(mcp, "get_power", system="ohara")
    assert out == {"name": "DCC++ Ohara", "state": "OFF", "default": False}


async def test_get_power_defaults_to_default_system(mock_power):
    mcp = make_server()
    out = await call(mcp, "get_power")
    assert out["name"] == "DCC++ Raijin"
    assert out["default"] is True


async def test_get_power_unknown_system_returns_error_not_exception(mock_power):
    mcp = make_server()
    out = await call(mcp, "get_power", system="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_system_status_reports_version_and_systems(mock_power, version_fixture):
    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/version").mock(
            return_value=Response(200, json=version_fixture)
        )
        out = await call(mcp, "system_status")

    assert out["reachable"] is True
    assert out["version"] == "5.4.0"
    assert len(out["systems"]) == 3


async def test_system_status_unreachable_reports_honestly():
    import respx
    from httpx import ConnectError

    from tests.conftest import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/version").mock(side_effect=ConnectError("refused"))
        out = await call(mcp, "system_status")

    assert out["reachable"] is False
    assert "error" in out
    assert "systems" not in out


async def test_acquire_throttle_returns_state(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "acquire_throttle", address=3)
    assert out == {"acquired": True, "address": 3, "speed": 0.0, "direction": "forward"}


async def test_acquire_throttle_passes_prefix(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "acquire_throttle", address=3, prefix="R")
    assert out["acquired"] is True
    assert out["address"] == 3


async def test_release_throttle_reports_success(fake_jmri):
    mcp = make_server()
    await call(mcp, "acquire_throttle", address=7)
    out = await call(mcp, "release_throttle", address=7)
    assert out == {"released": True, "address": 7}


async def test_acquire_throttle_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "acquire_throttle", address=3)
    assert "error" in out


async def test_set_speed_auto_acquires_and_converts_percent(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_speed", address=3, speed_percent=40)
    assert out == {"address": 3, "speed_percent": 40.0}


async def test_set_speed_clamps_out_of_range_percent(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_speed", address=3, speed_percent=150)
    assert out == {"address": 3, "speed_percent": 100.0}


async def test_stop_sets_speed_zero(fake_jmri):
    mcp = make_server()
    await call(mcp, "set_speed", address=3, speed_percent=60)
    out = await call(mcp, "stop", address=3)
    assert out == {"address": 3, "speed_percent": 0.0}


async def test_emergency_stop_reports_stopped(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "emergency_stop", address=3)
    assert out == {"address": 3, "stopped": True}


async def test_set_speed_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_speed", address=3, speed_percent=50)
    assert "error" in out


async def test_set_direction_auto_acquires_and_sets_reverse(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_direction", address=3, direction="reverse")
    assert out == {"address": 3, "direction": "reverse"}


async def test_set_direction_is_case_insensitive(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_direction", address=3, direction="Forward")
    assert out == {"address": 3, "direction": "forward"}


async def test_set_direction_rejects_invalid_value(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_direction", address=3, direction="sideways")
    assert "error" in out


async def test_set_direction_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_direction", address=3, direction="forward")
    assert "error" in out
