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
