import json

from mcp.server.fastmcp import FastMCP

from jmri_mcp import tools


def make_server() -> FastMCP:
    mcp = FastMCP("test")
    tools.register(mcp)
    return mcp


async def call(mcp: FastMCP, tool_name: str, **kwargs) -> dict:
    result = await mcp.call_tool(tool_name, kwargs)
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

    from jmri_core.testing.plugin import MOCK_JMRI_URL

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


async def test_compact_power_preserves_parenthetical_description(monkeypatch):
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=[
                {"type": "power", "data": {"name": "zou (test)", "prefix": "Z", "state": 2, "default": True}},
            ])
        )
        out = await call(mcp, "get_power", system="zou")
    assert out["name"] == "zou (test)"


async def test_system_status_reports_version_and_systems(mock_power, version_fixture):
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

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

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/version").mock(side_effect=ConnectError("refused"))
        out = await call(mcp, "system_status")

    assert out["reachable"] is False
    assert "error" in out
    assert "systems" not in out


async def test_list_roster_registered_and_compact(mock_roster):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_roster" in tool_names

    out = await call(mcp, "list_roster")
    assert out == {
        "roster": [
            {
                "name": "141R", "address": 2, "road": "Mikado 141 R",
                "road_number": "141 R 1246, dépôt de Miramas", "manufacturer": "Jouef",
                "model": "8273", "owner": "SNCF", "date_modified": "2024-01-20T13:18:40.774+00:00",
                "groups": ["test"],
            },
            {
                "name": "Autorail", "address": 4, "road": "Railcar",
                "road_number": "", "manufacturer": "", "model": "4185A",
                "owner": "", "date_modified": "2024-01-20T13:18:40.774+00:00",
                "groups": [],
            },
            {
                "name": "Boite à Sel", "address": 8, "road": "",
                "road_number": "", "manufacturer": "", "model": "",
                "owner": "", "date_modified": "2024-01-20T13:18:40.774+00:00",
                "groups": [],
            },
        ]
    }


async def test_list_roster_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_roster")
    assert "error" in out


async def test_find_locomotive_resolves_fuzzy_name(mock_roster):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "find_locomotive" in tool_names

    out = await call(mcp, "find_locomotive", name="autorail")
    assert out == {
        "name": "Autorail", "address": 4, "road": "Railcar",
        "road_number": "", "manufacturer": "", "model": "4185A",
        "owner": "", "date_modified": "2024-01-20T13:18:40.774+00:00",
        "groups": [],
    }


async def test_find_locomotive_accent_insensitive(mock_roster):
    mcp = make_server()
    out = await call(mcp, "find_locomotive", name="boite a sel")
    assert out["name"] == "Boite à Sel"


async def test_find_locomotive_unknown_name_returns_error(mock_roster):
    mcp = make_server()
    out = await call(mcp, "find_locomotive", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_find_locomotive_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "find_locomotive", name="autorail")
    assert "error" in out


async def test_get_locomotive_functions_returns_labels(mock_roster):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "get_locomotive_functions" in tool_names

    out = await call(mcp, "get_locomotive_functions", name="autorail")
    assert out == {
        "name": "Autorail",
        "address": 4,
        "functions": {"F0": "Lumières avant", "F1": "Lumières cabine", "F2": "Lumières arrière"},
    }


async def test_get_locomotive_functions_empty_when_none_labeled(mock_roster):
    mcp = make_server()
    out = await call(mcp, "get_locomotive_functions", name="boite a sel")
    assert out == {"name": "Boite à Sel", "address": 8, "functions": {}}


async def test_get_locomotive_functions_unknown_name_returns_error(mock_roster):
    mcp = make_server()
    out = await call(mcp, "get_locomotive_functions", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_get_locomotive_functions_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "get_locomotive_functions", name="autorail")
    assert "error" in out


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


async def test_emergency_stop_all_stops_every_acquired_address(fake_jmri):
    mcp = make_server()
    await call(mcp, "acquire_throttle", address=3)
    await call(mcp, "acquire_throttle", address=7)
    out = await call(mcp, "emergency_stop_all")
    assert sorted(out["stopped"]) == [3, 7]
    assert out["failed"] == []


async def test_emergency_stop_all_with_nothing_acquired(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "emergency_stop_all")
    assert out == {"stopped": [], "failed": []}


async def test_emergency_stop_all_with_nothing_acquired_and_unreachable_jmri(monkeypatch):
    # Nothing acquired means the stop loop has nothing to iterate, so this
    # succeeds trivially even with JMRI unreachable -- no throttles means
    # no requests are ever sent.
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "emergency_stop_all")
    assert out == {"stopped": [], "failed": []}


async def test_set_speed_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_speed", address=3, speed_percent=50)
    assert "error" in out


class _FastSleepAsyncio:
    """Proxy for jmri_ws.ramp's own `asyncio` reference with `sleep` stubbed
    to instant, so a long hold_seconds doesn't actually slow the test down.
    Mirrors jmri-cli's test_cli.py::_FastSleepAsyncio (patching the real
    asyncio module directly would break fake_jmri's own live websockets
    server, which relies on real sleep timing for handshake/keepalive)."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, _seconds):
        return None


async def test_set_speed_ramped_short_hold_blocks_and_returns_final_state(fake_jmri):
    """Below RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS, the call still
    blocks until the ramp/hold/auto-stop are all done and reports the real
    final speed -- same as before the background path was added."""
    mcp = make_server()
    out = await call(mcp, "set_speed_ramped", address=3, speed_percent=40, hold_seconds=1)
    assert out == {"address": 3, "speed_percent": 0.0, "direction": "forward"}


async def test_set_speed_ramped_long_hold_returns_started_immediately(fake_jmri, monkeypatch):
    """Above the threshold, the tool must return right away with a
    "started" acknowledgement rather than blocking the MCP tool call for
    the full duration -- this is the fix for a voice client (Kira/xiaozhi)
    tripping its own turn timeout while waiting on a long-blocking call."""
    import asyncio

    monkeypatch.setattr("jmri_core.jmri_ws.ramp.asyncio", _FastSleepAsyncio(asyncio))
    mcp = make_server()

    out = await call(mcp, "set_speed_ramped", address=3, speed_percent=40, hold_seconds=10)
    assert out == {
        "address": 3,
        "status": "started",
        "speed_percent": 40,
        "direction": None,
        "seconds_total": 10,
    }

    from jmri_mcp.tools._common import background_tasks

    assert background_tasks
    await asyncio.gather(*background_tasks, return_exceptions=True)


async def test_set_speed_ramped_background_ramp_actually_completes(fake_jmri, monkeypatch):
    """The background task isn't just fired and abandoned -- once it's
    awaited (as server/__init__.py's shutdown path does via
    tools._common.background_tasks), JMRI's real state reflects the
    completed ramp/hold/auto-stop, same end state as the blocking path."""
    import asyncio

    monkeypatch.setattr("jmri_core.jmri_ws.ramp.asyncio", _FastSleepAsyncio(asyncio))
    mcp = make_server()

    await call(mcp, "set_speed_ramped", address=3, speed_percent=40, hold_seconds=10)

    from jmri_core.jmri_ws import get_ws_client
    from jmri_mcp.tools._common import background_tasks

    await asyncio.gather(*background_tasks, return_exceptions=True)
    state = get_ws_client().throttle_state("addr3")
    assert state["speed"] == 0.0  # auto-stopped after the hold, like the blocking path


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


async def test_set_function_auto_acquires_and_sets_state(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_function", address=3, function=5, state=True)
    assert out == {"address": 3, "function": 5, "state": True}


async def test_set_function_rejects_out_of_range(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_function", address=3, function=29, state=True)
    assert "error" in out
    out = await call(mcp, "set_function", address=3, function=-1, state=True)
    assert "error" in out


async def test_set_function_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_function", address=3, function=0, state=True)
    assert "error" in out


async def test_lights_on_sets_function_zero(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "lights_on", address=3)
    assert out == {"address": 3, "function": 0, "state": True}


async def test_lights_off_sets_function_zero(fake_jmri):
    mcp = make_server()
    await call(mcp, "lights_on", address=3)
    out = await call(mcp, "lights_off", address=3)
    assert out == {"address": 3, "function": 0, "state": False}


async def test_list_lights_registered_and_compact(mock_lights):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_lights" in tool_names

    out = await call(mcp, "list_lights")
    assert out == {
        "lights": [
            {"name": "Depot Lighting", "state": "OFF"},
            {"name": "Street Lamps", "state": "ON"},
            {"name": "IL3", "state": "OFF"},
        ]
    }


async def test_list_lights_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_lights")
    assert "error" in out


async def test_get_light_resolves_by_fragment(mock_lights):
    mcp = make_server()
    out = await call(mcp, "get_light", name="depot")
    assert out == {"name": "Depot Lighting", "state": "OFF"}


async def test_get_light_unknown_name_returns_error_not_exception(mock_lights):
    mcp = make_server()
    out = await call(mcp, "get_light", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_set_light_turns_on_and_confirms():
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=[
                {"type": "light", "data": {"name": "IL1", "userName": "Depot Lighting", "state": 2}},
                {"type": "light", "data": {"name": "IL2", "userName": "Street Lamps", "state": 2}},
                {"type": "light", "data": {"name": "IL3", "userName": None, "state": 4}},
            ])
        )
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(return_value=Response(200, json={}))
        out = await call(mcp, "set_light", name="depot", turn_on=True)
    assert out == {"name": "Depot Lighting", "state": "ON", "confirmed": True}


async def test_set_light_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_light", name="depot", turn_on=True)
    assert "error" in out


async def test_list_turnouts_registered_and_compact(mock_turnouts):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_turnouts" in tool_names

    out = await call(mcp, "list_turnouts")
    assert out == {
        "turnouts": [
            {"name": "Layout Turnout A", "state": "CLOSED", "has_feedback_sensor": True},
            {"name": "Layout Turnout BL", "state": "CLOSED", "has_feedback_sensor": True},
            {"name": "A / Mountain A -> Platform A/B", "state": "THROWN", "has_feedback_sensor": False},
        ]
    }


async def test_list_turnouts_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_turnouts")
    assert "error" in out


async def test_get_turnout_resolves_by_fragment(mock_turnouts):
    mcp = make_server()
    out = await call(mcp, "get_turnout", name="Layout Turnout A")
    assert out == {"name": "Layout Turnout A", "state": "CLOSED", "has_feedback_sensor": True}


async def test_get_turnout_unknown_name_returns_error_not_exception(mock_turnouts):
    mcp = make_server()
    out = await call(mcp, "get_turnout", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_set_turnout_throws_and_confirms():
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=[
                {"type": "turnout", "data": {"name": "IT100", "userName": "Layout Turnout A", "state": 4}},
                {"type": "turnout", "data": {"name": "IT101", "userName": "Layout Turnout BL", "state": 2}},
            ])
        )
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(return_value=Response(200, json={}))
        out = await call(mcp, "set_turnout", name="Layout Turnout A", thrown=True)
    assert out == {
        "name": "Layout Turnout A",
        "state": "THROWN",
        "has_feedback_sensor": False,
        "confirmed": True,
    }


async def test_set_turnout_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_turnout", name="Layout Turnout A", thrown=True)
    assert "error" in out


def test_compact_turnout_has_feedback_sensor_true_when_sensor_present():
    from jmri_mcp.tools._common import compact_turnout

    turnout = {"name": "IT100", "state": 2, "sensor": [{"name": "OS37"}, None]}
    assert compact_turnout(turnout)["has_feedback_sensor"] is True


def test_compact_turnout_has_feedback_sensor_false_when_no_sensor():
    from jmri_mcp.tools._common import compact_turnout

    turnout = {"name": "OT23", "state": 8, "sensor": [None, None]}
    assert compact_turnout(turnout)["has_feedback_sensor"] is False


def test_compact_turnout_has_feedback_sensor_false_when_sensor_field_missing():
    from jmri_mcp.tools._common import compact_turnout

    turnout = {"name": "OT23", "state": 8}
    assert compact_turnout(turnout)["has_feedback_sensor"] is False


def test_compact_turnout_has_feedback_sensor_ignores_feedback_mode():
    """feedbackMode alone is not a reliable signal (verified live: a turnout
    can be feedbackMode=2/DIRECT yet still carry a real sensor object) — only
    the sensor array's actual content should matter."""
    from jmri_mcp.tools._common import compact_turnout

    turnout = {"name": "OT27", "state": 2, "feedbackMode": 2, "sensor": [{"name": "OS43"}, None]}
    assert compact_turnout(turnout)["has_feedback_sensor"] is True


async def test_list_signals_registered_and_compact(mock_signals):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_signals" in tool_names

    out = await call(mcp, "list_signals")
    assert out == {
        "signals": [
            {"name": "Entry Signal A", "aspect": "Hp1", "lit": True, "held": False},
            {"name": "ZF$dsm:DB-HV-1969:block(45)", "aspect": "Hp0", "lit": True, "held": False},
        ]
    }


async def test_list_signals_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_signals")
    assert "error" in out


async def test_get_signal_resolves_by_fragment(mock_signals):
    mcp = make_server()
    out = await call(mcp, "get_signal", name="Entry Signal")
    assert out == {"name": "Entry Signal A", "aspect": "Hp1", "lit": True, "held": False}


async def test_get_signal_unknown_name_returns_error_not_exception(mock_signals):
    mcp = make_server()
    out = await call(mcp, "get_signal", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_set_signal_sets_aspect_and_confirms():
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    post_bodies = []
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=[
                {"type": "signalMast", "data": {
                    "name": "ZF$dsm:DB-HV-1969:block(31)", "userName": "Entry Signal A",
                    "aspect": "Hp0", "lit": True, "held": False,
                }},
            ])
        )

        def post_signal(request):
            post_bodies.append(json.loads(request.content))
            return Response(200, json={})

        router.post(f"{MOCK_JMRI_URL}/json/signalMast/ZF$dsm:DB-HV-1969:block(31)").mock(
            side_effect=post_signal
        )
        out = await call(mcp, "set_signal", name="Entry Signal A", aspect="Hp0")
    assert out == {"name": "Entry Signal A", "aspect": "Hp0", "lit": True, "held": False, "confirmed": True}
    # Regression guard: JMRI's JsonSignalMastHttpService.doPost() reads the
    # "state" field, not "aspect" - sending the wrong key is silently
    # ignored server-side (200 response, no error, aspect never changes).
    assert post_bodies == [{"name": "ZF$dsm:DB-HV-1969:block(31)", "state": "Hp0"}]


async def test_set_signal_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_signal", name="Entry Signal A", aspect="Hp0")
    assert "error" in out


async def test_list_sensors_registered_and_compact(mock_sensors):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_sensors" in tool_names

    out = await call(mcp, "list_sensors")
    assert out == {
        "sensors": [
            {"name": "ISCLOCKRUNNING", "state": "ACTIVE"},
            {"name": "Montagne B", "state": "INACTIVE"},
            {"name": "Montagne A int", "state": "ACTIVE"},
        ]
    }


async def test_list_sensors_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_sensors")
    assert "error" in out


async def test_get_sensor_resolves_by_fragment(mock_sensors):
    mcp = make_server()
    out = await call(mcp, "get_sensor", name="montagne b")
    assert out == {"name": "Montagne B", "state": "INACTIVE"}


async def test_get_sensor_unknown_name_returns_error_not_exception(mock_sensors):
    mcp = make_server()
    out = await call(mcp, "get_sensor", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_list_blocks_registered_and_compact(mock_blocks):
    mcp = make_server()
    tool_names = {t.name for t in await mcp.list_tools()}
    assert "list_blocks" in tool_names

    out = await call(mcp, "list_blocks")
    assert out == {
        "blocks": [
            {
                "name": "Montagne A", "state": "UNOCCUPIED", "sensor": "RS24", "value": None,
                "length": 934.24, "curvature": 2, "speed": "Fifty", "comment": None,
            },
            {
                "name": "Montagne B", "state": "OCCUPIED", "sensor": "RS42", "value": None,
                "length": 1661.63, "curvature": 1, "speed": "Sixty", "comment": None,
            },
        ]
    }


async def test_list_blocks_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "list_blocks")
    assert "error" in out


async def test_get_block_resolves_by_fragment(mock_blocks):
    mcp = make_server()
    out = await call(mcp, "get_block", name="montagne b")
    assert out == {
        "name": "Montagne B", "state": "OCCUPIED", "sensor": "RS42", "value": None,
        "length": 1661.63, "curvature": 1, "speed": "Sixty", "comment": None,
    }


async def test_get_block_unknown_name_returns_error_not_exception(mock_blocks):
    mcp = make_server()
    out = await call(mcp, "get_block", name="tgv")
    assert "error" in out and "tgv" in out["error"]


async def test_power_off_all_confirms_every_system(monkeypatch):
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    mcp = make_server()
    # Stateful fake: systems start ON, flip to OFF once their POST arrives —
    # so set_power's pre-check sees ON (POST is not skipped) and the
    # post-POST re-read correctly observes OFF.
    live_state = {"O": 2, "R": 2}

    def get_power(request):
        payload = [
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
            {"type": "power", "data": {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True}},
        ]
        return Response(200, json=payload)

    def post_power(request):
        import json as _json
        body = _json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)
        out = await call(mcp, "power_off_all")

    assert out == {
        "systems": [
            {"name": "DCC++ Ohara", "state": "OFF", "default": False, "confirmed": True},
            {"name": "DCC++ Raijin", "state": "OFF", "default": True, "confirmed": True},
        ]
    }


async def test_power_off_all_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "power_off_all")
    assert "error" in out


async def test_power_on_all_confirms_every_system(monkeypatch):
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    mcp = make_server()
    # Stateful fake: systems start OFF, flip to ON once their POST arrives —
    # so set_power's pre-check sees OFF (POST is not skipped) and the
    # post-POST re-read correctly observes ON.
    live_state = {"O": 4, "R": 4}

    def get_power(request):
        payload = [
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
            {"type": "power", "data": {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True}},
        ]
        return Response(200, json=payload)

    def post_power(request):
        import json as _json
        body = _json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)
        out = await call(mcp, "power_on_all")

    assert out == {
        "systems": [
            {"name": "DCC++ Ohara", "state": "ON", "default": False, "confirmed": True},
            {"name": "DCC++ Raijin", "state": "ON", "default": True, "confirmed": True},
        ]
    }


async def test_power_on_all_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "power_on_all")
    assert "error" in out


async def test_set_executor_mode_on_returns_instruction():
    mcp = make_server()
    out = await call(mcp, "set_executor_mode", enabled=True)
    assert out["executor_mode"] is True
    assert "instruction" in out and len(out["instruction"]) > 0


async def test_set_executor_mode_off_returns_instruction():
    mcp = make_server()
    await call(mcp, "set_executor_mode", enabled=True)
    out = await call(mcp, "set_executor_mode", enabled=False)
    assert out["executor_mode"] is False
    assert "instruction" in out


async def test_get_executor_mode_reflects_current_state():
    mcp = make_server()
    out = await call(mcp, "get_executor_mode")
    assert out == {"executor_mode": False}

    await call(mcp, "set_executor_mode", enabled=True)
    out = await call(mcp, "get_executor_mode")
    assert out["executor_mode"] is True
    assert "instruction" in out


def _mock_roster_for(monkeypatch, roster_fixture):
    """respx can't target fake_jmri's fixture port statically like MOCK_JMRI_URL,
    since fake_jmri assigns a random local WS port and repoints JMRI_URL at it;
    build the router against whatever JMRI_URL is current at call time instead."""
    import respx
    from httpx import Response

    from jmri_core.config import get_jmri_url

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    return router


async def test_set_loco_lights_applies_every_light_labeled_function(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        out = await call(mcp, "set_loco_lights", address=4, state=True)
    finally:
        router.stop()
    assert out["address"] == 4
    assert out["failed"] == []
    assert sorted(out["applied"], key=lambda a: a["function"]) == [
        {"function": 0, "label": "Lumières avant", "state": True},
        {"function": 1, "label": "Lumières cabine", "state": True},
        {"function": 2, "label": "Lumières arrière", "state": True},
    ]


async def test_set_loco_lights_no_labeled_functions_returns_empty_not_error(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        out = await call(mcp, "set_loco_lights", address=8, state=True)
    finally:
        router.stop()
    assert out["address"] == 8
    assert out["applied"] == []
    assert out["failed"] == []
    assert "note" in out
    assert "error" not in out


async def test_set_loco_lights_unknown_address_returns_error(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        out = await call(mcp, "set_loco_lights", address=999, state=True)
    finally:
        router.stop()
    assert "error" in out


async def test_set_loco_lights_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_loco_lights", address=4, state=True)
    assert "error" in out


async def test_set_all_locos_lights_covers_every_acquired_address(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        await call(mcp, "acquire_throttle", address=4)
        await call(mcp, "acquire_throttle", address=8)
        out = await call(mcp, "set_all_locos_lights", state=True)
    finally:
        router.stop()
    by_address = {loco["address"]: loco for loco in out["locomotives"]}
    assert sorted(by_address) == [4, 8]
    assert len(by_address[4]["applied"]) == 3
    assert by_address[8]["applied"] == []
    assert "note" in by_address[8]


async def test_set_all_locos_lights_with_nothing_acquired(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "set_all_locos_lights", state=True)
    assert out == {"locomotives": []}


async def test_prepare_locomotive_acquires_faces_forward_and_lights_on(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        out = await call(mcp, "prepare_locomotive", address=4)
    finally:
        router.stop()
    assert out["address"] == 4
    assert out["acquired"] is True
    assert out["direction"] == "forward"
    assert len(out["lights"]["applied"]) == 3
    assert all(a["state"] is True for a in out["lights"]["applied"])


async def test_prepare_locomotive_flips_reverse_to_forward(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        await call(mcp, "set_direction", address=4, direction="reverse")
        out = await call(mcp, "prepare_locomotive", address=4)
    finally:
        router.stop()
    assert out["direction"] == "forward"

    from jmri_core.jmri_ws import get_ws_client

    assert get_ws_client().throttle_state("addr4")["forward"] is True


async def test_prepare_locomotive_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "prepare_locomotive", address=4)
    assert "error" in out


async def test_park_locomotive_ramps_down_faces_forward_lights_off_and_releases(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        await call(mcp, "prepare_locomotive", address=4)
        await call(mcp, "set_speed", address=4, speed_percent=40)
        out = await call(mcp, "park_locomotive", address=4)
    finally:
        router.stop()
    assert out["address"] == 4
    assert out["stopped"] is True
    assert out["direction"] == "forward"
    assert out["released"] is True
    assert len(out["lights"]["applied"]) == 3
    assert all(a["state"] is False for a in out["lights"]["applied"])

    from jmri_core.jmri_ws import get_ws_client

    assert "addr4" not in get_ws_client().all_throttle_states()


async def test_park_locomotive_flips_reverse_to_forward_at_rest(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        await call(mcp, "set_direction", address=4, direction="reverse")
        out = await call(mcp, "park_locomotive", address=4)
    finally:
        router.stop()
    assert out["direction"] == "forward"


async def test_park_locomotive_never_acquired_still_turns_off_lights_and_releases(fake_jmri, roster_fixture):
    """No prior acquire_throttle/set_speed for this address -- steps 1-2
    (ramp/direction) are skipped, but lights (which auto-acquire, like
    set_loco_lights always does) still run, and the resulting throttle is
    still released rather than left dangling."""
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        out = await call(mcp, "park_locomotive", address=4)
    finally:
        router.stop()
    assert out["stopped"] is True
    assert out["released"] is True
    assert len(out["lights"]["applied"]) == 3

    from jmri_core.jmri_ws import get_ws_client

    assert "addr4" not in get_ws_client().all_throttle_states()


async def test_park_locomotive_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "park_locomotive", address=4)
    assert "error" in out


async def test_park_all_locomotives_covers_every_acquired_address(fake_jmri, roster_fixture):
    router = _mock_roster_for(None, roster_fixture)
    try:
        mcp = make_server()
        await call(mcp, "prepare_locomotive", address=4)
        await call(mcp, "acquire_throttle", address=8)
        out = await call(mcp, "park_all_locomotives")
    finally:
        router.stop()
    by_address = {loco["address"]: loco for loco in out["locomotives"]}
    assert sorted(by_address) == [4, 8]
    assert by_address[4]["stopped"] is True
    assert by_address[4]["released"] is True
    assert len(by_address[4]["lights"]["applied"]) == 3
    assert by_address[8]["released"] is True

    from jmri_core.jmri_ws import get_ws_client

    assert get_ws_client().all_throttle_states() == {}


async def test_park_all_locomotives_with_nothing_acquired(fake_jmri):
    mcp = make_server()
    out = await call(mcp, "park_all_locomotives")
    assert out == {"locomotives": []}


async def test_set_all_turnouts_confirms_every_turnout():
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    live_state = {"IT100": 2, "IT101": 2, "OT23": 4}

    def get_turnouts(request):
        payload = [
            {"type": "turnout", "data": {"name": "IT100", "userName": "Layout Turnout A", "state": live_state["IT100"]}},
            {"type": "turnout", "data": {"name": "IT101", "userName": "Layout Turnout BL", "state": live_state["IT101"]}},
            {"type": "turnout", "data": {"name": "OT23", "userName": "A / Mountain A -> Platform A/B", "state": live_state["OT23"]}},
        ]
        return Response(200, json=payload)

    def post_turnout(name):
        def handler(request):
            live_state[name] = json.loads(request.content)["state"]
            return Response(200, json={})
        return handler

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(side_effect=get_turnouts)
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(side_effect=post_turnout("IT100"))
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT101").mock(side_effect=post_turnout("IT101"))
        router.post(f"{MOCK_JMRI_URL}/json/turnout/OT23").mock(side_effect=post_turnout("OT23"))
        out = await call(mcp, "set_all_turnouts", thrown=True)

    assert out["failed"] == []
    assert {s["name"] for s in out["succeeded"]} == {
        "Layout Turnout A", "Layout Turnout BL", "A / Mountain A -> Platform A/B",
    }
    assert all(s["state"] == "THROWN" and s["confirmed"] for s in out["succeeded"])


async def test_set_all_turnouts_continues_after_one_failure():
    import respx
    from httpx import ConnectError, Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=[
                {"type": "turnout", "data": {"name": "IT100", "userName": "Layout Turnout A", "state": 2}},
                {"type": "turnout", "data": {"name": "IT101", "userName": "Layout Turnout BL", "state": 2}},
            ])
        )
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(side_effect=ConnectError("refused"))
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT101").mock(return_value=Response(200, json={}))
        out = await call(mcp, "set_all_turnouts", thrown=True)

    assert len(out["failed"]) == 1
    assert out["failed"][0]["name"] == "Layout Turnout A"
    assert len(out["succeeded"]) == 1
    assert out["succeeded"][0]["name"] == "Layout Turnout BL"


async def test_set_all_turnouts_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_all_turnouts", thrown=True)
    assert "error" in out


async def test_set_layout_lights_confirms_every_light():
    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    live_state = {"IL1": 4, "IL2": 2, "IL3": 4}

    def get_lights(request):
        payload = [
            {"type": "light", "data": {"name": "IL1", "userName": "Depot Lighting", "state": live_state["IL1"]}},
            {"type": "light", "data": {"name": "IL2", "userName": "Street Lamps", "state": live_state["IL2"]}},
            {"type": "light", "data": {"name": "IL3", "userName": None, "state": live_state["IL3"]}},
        ]
        return Response(200, json=payload)

    def post_light(name):
        def handler(request):
            live_state[name] = json.loads(request.content)["state"]
            return Response(200, json={})
        return handler

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(side_effect=get_lights)
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(side_effect=post_light("IL1"))
        router.post(f"{MOCK_JMRI_URL}/json/light/IL2").mock(side_effect=post_light("IL2"))
        router.post(f"{MOCK_JMRI_URL}/json/light/IL3").mock(side_effect=post_light("IL3"))
        out = await call(mcp, "set_layout_lights", turn_on=True)

    assert out["failed"] == []
    assert {s["name"] for s in out["succeeded"]} == {"Depot Lighting", "Street Lamps", "IL3"}
    assert all(s["state"] == "ON" and s["confirmed"] for s in out["succeeded"])


async def test_set_layout_lights_continues_after_one_failure():
    import respx
    from httpx import ConnectError, Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    mcp = make_server()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=[
                {"type": "light", "data": {"name": "IL1", "userName": "Depot Lighting", "state": 4}},
                {"type": "light", "data": {"name": "IL2", "userName": "Street Lamps", "state": 4}},
            ])
        )
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(side_effect=ConnectError("refused"))
        router.post(f"{MOCK_JMRI_URL}/json/light/IL2").mock(return_value=Response(200, json={}))
        out = await call(mcp, "set_layout_lights", turn_on=True)

    assert len(out["failed"]) == 1
    assert out["failed"][0]["name"] == "Depot Lighting"
    assert len(out["succeeded"]) == 1
    assert out["succeeded"][0]["name"] == "Street Lamps"


async def test_set_layout_lights_reports_error_honestly(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    mcp = make_server()
    out = await call(mcp, "set_layout_lights", turn_on=True)
    assert "error" in out
