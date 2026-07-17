import json

from jmri_mcp.server import _SERVER_INSTRUCTIONS, mcp

# The remote xiaozhi cloud server closes the WebSocket with 1009 (message too
# big) at or above 65536 bytes (64 KiB) of serialized `tools/list` JSON-RPC
# response — empirically bisected live 2026-07-15: 64443 bytes passed, 65572
# failed. This is the remote server's limit, not jmri-xiaozhi-bridge's own
# (its WebSocket max_size is 1 MiB and raising it further has zero effect).
# We assert well under the known-safe 64443 point, not just under 65536, so a
# docstring edit that creeps up to e.g. 65000 still fails loudly here instead
# of shipping right at the edge — see docs/architecture.md and
# .claude/CLAUDE.md's hard rules for the full incident history (2026-07-17
# outage: a real jmri-xiaozhi-bridge/Kira breakage from this limit being
# exceeded without anyone re-checking after several docstring edits).
_XIAOZHI_HARD_CEILING_BYTES = 65536
_SAFE_MARGIN_BYTES = 1000
_MAX_TOOLS_LIST_BYTES = _XIAOZHI_HARD_CEILING_BYTES - _SAFE_MARGIN_BYTES


async def _tools_list_payload_size() -> int:
    """Bytes of the full `tools/list` JSON-RPC response, serialized the same
    way FastMCP actually puts it on the wire (this is what xiaozhi's cloud
    server counts against its 1009 close threshold)."""
    tools = await mcp.list_tools()
    tool_dicts = [t.model_dump(mode="json", exclude_none=True) for t in tools]
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": tool_dicts}}
    return len(json.dumps(payload).encode("utf-8"))


async def test_tools_list_payload_stays_safely_under_xiaozhi_size_ceiling():
    size = await _tools_list_payload_size()
    assert size < _MAX_TOOLS_LIST_BYTES, (
        f"tools/list payload is {size} bytes, over the {_MAX_TOOLS_LIST_BYTES}-byte "
        f"safe budget ({_SAFE_MARGIN_BYTES} bytes under the real 65536-byte xiaozhi "
        "ceiling). The xiaozhi cloud server closes the WebSocket with 1009 (message "
        "too big) at or above 65536 bytes — trim docstring prose (not decision-"
        "relevant content) on the largest tools until this passes again."
    )


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
