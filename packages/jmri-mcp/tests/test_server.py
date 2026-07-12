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
