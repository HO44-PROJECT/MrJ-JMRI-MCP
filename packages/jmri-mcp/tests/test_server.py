from jmri_mcp.server import _SERVER_INSTRUCTIONS, mcp


def test_server_exposes_instructions_field():
    assert mcp.instructions == _SERVER_INSTRUCTIONS


def test_server_instructions_cover_whole_layout_tools():
    for phrase in ("arrête tout", "coupe le courant", "allume tout", "mode exécutant"):
        assert phrase in _SERVER_INSTRUCTIONS
    for tool_name in ("emergency_stop_all", "power_off_all", "power_on_all", "set_executor_mode"):
        assert tool_name in _SERVER_INSTRUCTIONS


def test_server_instructions_disambiguate_power_from_motion_stop():
    assert "NOT interchangeable" in _SERVER_INSTRUCTIONS


def test_server_instructions_cover_bulk_lighting_and_turnout_tools():
    for tool_name in (
        "set_all_turnouts", "set_layout_lights", "set_loco_lights", "set_all_locos_lights",
    ):
        assert tool_name in _SERVER_INSTRUCTIONS


def test_server_instructions_cover_act_dont_recite_guidance():
    assert "Act, don't recite" in _SERVER_INSTRUCTIONS
    assert "unknown_entity" in _SERVER_INSTRUCTIONS


def test_server_instructions_disambiguate_loco_lights_from_layout_lights():
    assert "Loco-lights disambiguation" in _SERVER_INSTRUCTIONS


def test_server_instructions_route_duration_requests_to_ramped_tool():
    assert "Duration routing" in _SERVER_INSTRUCTIONS
    assert "set_speed_ramped" in _SERVER_INSTRUCTIONS
    assert "hold_seconds" in _SERVER_INSTRUCTIONS


def test_server_instructions_explain_started_status_is_not_a_failure():
    assert '"status": "started"' in _SERVER_INSTRUCTIONS
    assert "NOT an error" in _SERVER_INSTRUCTIONS


def test_server_instructions_cover_meta_tools():
    for tool_name in (
        "layout_status", "secure_layout", "release_all_locomotives", "night_mode", "day_mode",
    ):
        assert tool_name in _SERVER_INSTRUCTIONS
