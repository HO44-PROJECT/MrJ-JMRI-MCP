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


async def test_compact_power_preserves_parenthetical_description(monkeypatch):
    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

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

    from tests.conftest import MOCK_JMRI_URL

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

    from tests.conftest import MOCK_JMRI_URL

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

    from tests.conftest import MOCK_JMRI_URL

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


async def test_power_off_all_confirms_every_system(monkeypatch):
    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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
