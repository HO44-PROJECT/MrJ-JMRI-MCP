import asyncio

import pytest

from jmri_cli import build_parser, main


async def run(capsys, *argv):
    args = build_parser().parse_args(argv)
    exit_code = await args.func(args)
    out, err = capsys.readouterr()
    return exit_code, out, err


async def test_power_status_all_systems(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "status")
    assert code == 0
    assert "DCC++ Ohara" in out and "DCC++ Zou" in out
    assert "DCC++ Raijin" in out and "yes" in out


async def test_power_status_shows_system_id_column(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "status")
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip().startswith(("O", "Z", "R"))]
    firsts = {line.split()[0] for line in lines}
    assert firsts == {"O", "Z", "R"}


async def test_power_byid_sorts_by_system_prefix(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "byid")
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip().startswith(("O", "Z", "R"))]
    assert [line.split()[0] for line in lines] == ["O", "R", "Z"]


async def test_power_bystate_sorts_by_state(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "bystate")
    assert code == 0
    assert "OFF" in out


async def test_power_bare_defaults_to_status(mock_power, capsys):
    code, out, _ = await run(capsys, "power")
    assert code == 0
    assert "DCC++ Ohara" in out and "DCC++ Raijin" in out


async def test_power_get_one_system(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "get", "ohara")
    assert code == 0
    assert out.strip() == "OFF"


async def test_power_get_unknown_system(mock_power, capsys):
    code, _, err = await run(capsys, "power", "get", "tgv")
    assert code == 1
    assert "Unknown system 'tgv'" in err


async def test_power_default_prints_default_system(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "default")
    assert code == 0
    assert out.strip() == "DCC++ Raijin"


async def test_power_set_twice_same_state_skips_second_post(monkeypatch, capsys):
    """Real JMRI bug this guards against: re-POSTing the same power state
    (e.g. ON twice in a row) knocks the system into UNKNOWN and is hard to
    recover from. `power set` on a system already in the requested state
    must never issue a second POST."""
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    live_state = {"O": 4}  # starts OFF
    post_calls = []

    def get_power(request):
        return Response(200, json=[
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
        ])

    def post_power(request):
        body = json.loads(request.content)
        post_calls.append(body)
        live_state["O"] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)

        code1, out1, _ = await run(capsys, "power", "on", "ohara")
        code2, out2, _ = await run(capsys, "power", "on", "ohara")

    assert code1 == 0 and code2 == 0
    assert "DCC++ Ohara" in out1 and "ON" in out1
    assert "DCC++ Ohara" in out2 and "ON" in out2
    # Only the first call actually changed anything; the repeat must not
    # have sent a second POST at all.
    assert len(post_calls) == 1


async def test_power_off_cuts_every_system(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    # systems start ON so set_power's pre-check doesn't skip the POST
    live_state = {"O": 2, "R": 2}

    def get_power(request):
        payload = [
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
            {"type": "power", "data": {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True}},
        ]
        return Response(200, json=payload)

    def post_power(request):
        body = json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)
        code, out, _ = await run(capsys, "power", "off")

    assert code == 0
    assert "DCC++ Ohara" in out and "OFF" in out
    assert "DCC++ Raijin" in out


async def test_power_on_restores_every_system(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    # systems start OFF so set_power's pre-check doesn't skip the POST
    live_state = {"O": 4, "R": 4}

    def get_power(request):
        payload = [
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
            {"type": "power", "data": {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True}},
        ]
        return Response(200, json=payload)

    def post_power(request):
        body = json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)
        code, out, _ = await run(capsys, "power", "on")

    assert code == 0
    assert "DCC++ Ohara" in out and "ON" in out
    assert "DCC++ Raijin" in out


async def test_power_on_one_system_only(monkeypatch, capsys):
    """power on <fuzzy target> narrows to just that system."""
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    live_state = {"O": 4, "R": 4}

    def get_power(request):
        payload = [
            {"type": "power", "data": {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False}},
            {"type": "power", "data": {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True}},
        ]
        return Response(200, json=payload)

    def post_power(request):
        body = json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_power)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_power)
        code, out, _ = await run(capsys, "power", "on", "raijin")

    assert code == 0
    assert "DCC++ Raijin" in out and "DCC++ Ohara" not in out
    assert live_state["R"] == 2 and live_state["O"] == 4


async def test_power_find_resolves_fuzzy_name(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "find", "ohara")
    assert code == 0
    assert "name=DCC++ Ohara" in out and "prefix=O" in out


async def test_power_find_unknown_name(mock_power, capsys):
    code, _, err = await run(capsys, "power", "find", "tgv")
    assert code == 1
    assert "Unknown system 'tgv'" in err


async def test_power_findr_matches_regex(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "findr", "^DCC\\+\\+ O")
    assert code == 0
    assert "DCC++ Ohara" in out
    assert "DCC++ Zou" not in out


async def test_power_findr_no_match(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "findr", "zzz")
    assert code == 0
    assert "No power systems match" in out


async def test_power_findr_invalid_regex(mock_power, capsys):
    code, _, err = await run(capsys, "power", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_power_findg_matches_glob(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "findg", "*Ohara")
    assert code == 0
    assert "DCC++ Ohara" in out
    assert "DCC++ Zou" not in out


async def test_power_findg_no_match(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "findg", "zzz*")
    assert code == 0
    assert "No power systems match" in out


async def test_roster_lists_every_entry(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster")
    assert code == 0
    assert "141R" in out and "Mikado 141 R" in out and "8273" in out
    assert "Autorail" in out and "Railcar" in out
    assert "Boite à Sel" in out and "-" in out  # empty road/model shown as "-"


async def test_roster_lists_max_speed_percent_column(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster")
    assert code == 0
    assert "100" in out  # every fixture entry defaults to maxSpeedPct=100


async def test_roster_shows_scaled_max_speed_percent_when_set(fake_jmri, roster_fixture, power_fixture, capsys):
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url

    roster_fixture[1]["data"]["maxSpeedPct"] = 20

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "roster")
    finally:
        router.stop()

    assert code == 0
    assert "Autorail" in out
    autorail_line = next(l for l in out.splitlines() if "Autorail" in l)
    assert "20" in autorail_line


async def test_roster_shows_dcc_system_full_name(fake_jmri, roster_fixture, power_fixture, capsys):
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url

    roster_fixture[1]["data"]["attributes"] = [{"name": "DccSystem", "value": "O"}]

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "roster")
    finally:
        router.stop()

    assert code == 0
    autorail_line = next(l for l in out.splitlines() if "Autorail" in l)
    assert "DCC++ Ohara" in autorail_line


async def test_roster_shows_default_system_when_no_dcc_system_set(mock_roster, mock_power, capsys):
    """No DccSystem roster attribute must show JMRI's default system, not
    "-" -- the locomotive is still actually driven through the default
    station, so showing blank/null there would be misleading."""
    code, out, _ = await run(capsys, "roster")
    assert code == 0
    autorail_line = next(l for l in out.splitlines() if "Autorail" in l)
    assert "DCC++ Raijin" in autorail_line


async def test_roster_find_shows_default_system_when_no_dcc_system_set(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "find", "autorail")
    assert code == 0
    assert "DCC++ Raijin" in out


async def test_roster_bydcc_sorts_by_address(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "bydcc")
    assert code == 0
    lines = [l for l in out.splitlines() if l.split() and l.split()[0].isdigit()]
    assert [l.split()[0] for l in lines] == ["2", "4", "8"]


async def test_roster_findr_byname_sorts_filtered_results(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "byname", ".")
    assert code == 0
    assert "141R" in out and "Autorail" in out and "Boite" in out


async def test_roster_reports_error_on_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    code, _, err = await run(capsys, "roster")
    assert code == 1
    assert "Error" in err


async def test_roster_find_resolves_fuzzy_name(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "find", "autorail")
    assert code == 0
    assert "address=4" in out and "name=Autorail" in out


async def test_roster_find_unknown_name(mock_roster, capsys):
    code, _, err = await run(capsys, "roster", "find", "tgv")
    assert code == 1
    assert "Unknown locomotive 'tgv'" in err


async def test_roster_findr_matches_regex(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "^auto")
    assert code == 0
    assert "Autorail" in out
    assert "Boite" not in out


async def test_roster_findr_no_match(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "zzz")
    assert code == 0
    assert "No roster entries match" in out


async def test_roster_findr_invalid_regex(mock_roster, mock_power, capsys):
    code, _, err = await run(capsys, "roster", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_roster_findg_matches_glob(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "findg", "auto*")
    assert code == 0
    assert "Autorail" in out
    assert "Boite" not in out


async def test_roster_findg_no_match(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "roster", "findg", "zzz*")
    assert code == 0
    assert "No roster entries match" in out


async def test_roster_functions_lists_labels(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "functions", "autorail")
    assert code == 0
    assert "Autorail (address=4)" in out
    assert "F0" in out and "Lumières avant" in out
    assert "F2" in out and "Lumières arrière" in out


async def test_roster_functions_reports_none_labeled(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "functions", "boite a sel")
    assert code == 0
    assert "no labeled functions" in out


async def test_light_list_shows_dcc_system_column(mock_lights, mock_power, capsys):
    """All 3 fixture lights are prefix "I" (JMRI-internal) -> no DCC connection match."""
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "DCC system" in header
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    # dcc_system is second-to-last now that Address trails it (IL1/IL2/IL3 -> 1/2/3).
    assert all(l.split()[-2] == "-" for l in lines)


async def test_light_find_shows_dcc_system(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "find", "IL1")
    assert code == 0
    assert "dcc_system=-" in out


async def test_light_list_shows_comment_column(mock_lights, mock_power, capsys):
    """None of the fixture lights have a comment set -> all show as "-"."""
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "Comment" in header


async def test_light_find_shows_comment(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "find", "IL1")
    assert code == 0
    assert "comment=-" in out


async def test_light_list_shows_address_column(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "Address" in header
    il1_line = next(l for l in out.splitlines() if l.startswith("IL1"))
    assert il1_line.split()[-1] == "1"


async def test_light_find_shows_address(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "find", "IL1")
    assert code == 0
    assert "address=1" in out


async def test_light_list_all(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    assert "Depot Lighting" in out and "OFF" in out
    assert "Street Lamps" in out and "ON" in out
    header = out.splitlines()[0]
    assert header.index("System ID") < header.index("Light")


async def test_light_bystate_sorts_by_state_column(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "bystate")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    # OFF < ON alphabetically; IL1/IL3 are OFF, IL2 is ON.
    assert [l.split()[0] for l in lines] == ["IL1", "IL3", "IL2"]
    assert "State ▼" in out


async def test_light_byaddress_sorts_by_address_column(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "byaddress")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    assert [l.split()[0] for l in lines] == ["IL1", "IL2", "IL3"]
    assert "Address ▼" in out


async def test_light_findg_byid_sorts_filtered_results(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "findg", "byid", "*")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    assert [l.split()[0] for l in lines] == ["IL1", "IL2", "IL3"]


async def test_light_on_unknown_name(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "on", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_light_find_by_system_id(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "find", "IL1")
    assert code == 0
    assert "system_id=IL1" in out
    assert "name=Depot Lighting" in out
    assert "state=OFF" in out
    assert out.index("system_id=") < out.index("name=")


async def test_light_find_by_username(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "find", "Street Lamps")
    assert code == 0
    assert "system_id=IL2" in out


async def test_light_find_unknown_name(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "find", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_light_findr_matches_regex(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "findr", "^Depot")
    assert code == 0
    assert "Depot Lighting" in out
    assert "Street Lamps" not in out


async def test_light_findr_no_match(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "findr", "zzz")
    assert code == 0
    assert "No lights match" in out


async def test_light_findr_invalid_regex(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_light_findg_matches_glob(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "findg", "Depot*")
    assert code == 0
    assert "Depot Lighting" in out
    assert "Street Lamps" not in out


async def test_light_findg_no_match(mock_lights, mock_power, capsys):
    code, out, _ = await run(capsys, "light", "findg", "zzz*")
    assert code == 0
    assert "No lights match" in out


async def test_light_on_bare_confirms_every_light(power_fixture, capsys):
    """No name given -> every light, matching set_layout_lights' MCP-tool coverage."""
    import json

    import respx
    from httpx import Response
    from jmri_core.testing.plugin import MOCK_JMRI_URL

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
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json=power_fixture))
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(side_effect=get_lights)
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(side_effect=post_light("IL1"))
        router.post(f"{MOCK_JMRI_URL}/json/light/IL2").mock(side_effect=post_light("IL2"))
        router.post(f"{MOCK_JMRI_URL}/json/light/IL3").mock(side_effect=post_light("IL3"))
        code, out, _ = await run(capsys, "light", "on")

    assert code == 0
    assert "Depot Lighting" in out and "Street Lamps" in out
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    assert all("ON" in l for l in lines)
    assert live_state == {"IL1": 2, "IL2": 2, "IL3": 2}


async def test_turnout_list_shows_dcc_system_column(mock_turnouts, mock_power, capsys):
    """IT100/IT101 (prefix I) have no DCC connection match; OT23 (prefix O) matches "DCC++ Ohara"."""
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "DCC system" in header
    lines = out.splitlines()
    it100_line = next(line for line in lines if "Layout Turnout A" in line)
    ot23_line = next(line for line in lines if "Mountain A" in line)
    # dcc_system is second-to-last now that Address trails it.
    assert it100_line.split()[-2] == "-"
    assert "DCC++ Ohara" in ot23_line


async def test_turnout_find_shows_dcc_system(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "OT23")
    assert code == 0
    assert "dcc_system=DCC++ Ohara" in out


async def test_turnout_find_shows_comment(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "IT100")
    assert code == 0
    assert "comment=Yard throat switch" in out


async def test_turnout_list_shows_address_column(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "Address" in header
    it100_line = next(l for l in out.splitlines() if l.startswith("IT100"))
    assert it100_line.split()[-1] == "100"


async def test_turnout_find_shows_address(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "IT100")
    assert code == 0
    assert "address=100" in out


async def test_turnout_bydccsystem_sorts_by_dcc_system_column(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "bydccsystem")
    assert code == 0
    assert "DCC system ▼" in out


async def test_turnout_byaddress_sorts_by_address_column(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "byaddress")
    assert code == 0
    # Address sorts as a string like every other column here, not numerically:
    # "100" < "101" < "23" lexicographically.
    lines = [l for l in out.splitlines() if l.startswith(("IT", "OT"))]
    assert [l.split()[0] for l in lines] == ["IT100", "IT101", "OT23"]
    assert "Address ▼" in out


async def test_turnout_list_all(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    assert "Feedback" in out
    assert "Comment" in out
    assert "Yard throat switch" in out
    header = out.splitlines()[0]
    assert header.index("System ID") < header.index("Turnout")
    assert "Layout Turnout A" in out and "CLOSED" in out
    assert "A / Mountain A -> Platform A/B" in out and "THROWN" in out
    # IT100 has a real sensor wired (fixture), OT23 doesn't.
    lines = out.splitlines()
    it100_line = next(line for line in lines if "Layout Turnout A" in line)
    ot23_line = next(line for line in lines if "Mountain A" in line)
    assert "yes" in it100_line
    assert "no" in ot23_line


async def test_turnout_list_defaults_to_byname_order(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    lines = [l for l in out.splitlines() if "Layout Turnout" in l or "Mountain" in l]
    # userNames alphabetically: "A / Mountain..." < "Layout Turnout A" < "Layout Turnout BL"
    assert lines[0].startswith("OT23")
    assert "Turnout ▼" in out


async def test_turnout_bystate_sorts_by_state_column(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "bystate")
    assert code == 0
    lines = [l for l in out.splitlines() if "IT100" in l or "IT101" in l or "OT23" in l]
    # CLOSED < THROWN alphabetically; IT100/IT101 are CLOSED, OT23 is THROWN.
    assert lines[0].startswith("IT100") or lines[0].startswith("IT101")
    assert lines[-1].startswith("OT23")
    assert "State ▼" in out


async def test_turnout_byid_sorts_by_system_id(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "byid")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith(("IT", "OT"))]
    assert [l.split()[0] for l in lines] == ["IT100", "IT101", "OT23"]
    assert "System ID ▼" in out


async def test_turnout_findr_byid_sorts_filtered_results(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "byid", "^Layout")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith(("IT", "OT"))]
    assert [l.split()[0] for l in lines] == ["IT100", "IT101"]


async def test_turnout_findr_no_sort_word_still_works(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "^Layout")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_closed_unknown_name(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "close", "tgv")
    assert code == 1
    assert "Unknown turnout 'tgv'" in err


async def test_turnout_throw_bare_confirms_every_turnout(power_fixture, capsys):
    """No name given -> every turnout, matching set_all_turnouts' MCP-tool coverage."""
    import json

    import respx
    from httpx import Response
    from jmri_core.testing.plugin import MOCK_JMRI_URL

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
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json=power_fixture))
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(side_effect=get_turnouts)
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(side_effect=post_turnout("IT100"))
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT101").mock(side_effect=post_turnout("IT101"))
        router.post(f"{MOCK_JMRI_URL}/json/turnout/OT23").mock(side_effect=post_turnout("OT23"))
        code, out, _ = await run(capsys, "turnout", "throw")

    assert code == 0
    assert "Layout Turnout A" in out and "Layout Turnout BL" in out
    assert "A / Mountain A -> Platform A/B" in out
    lines = [l for l in out.splitlines() if "Layout Turnout" in l or "Mountain" in l]
    assert all("THROWN" in l for l in lines)
    assert live_state == {"IT100": 4, "IT101": 4, "OT23": 4}


async def test_turnout_find_by_system_id(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "IT100")
    assert code == 0
    assert "system_id=IT100" in out
    assert "name=Layout Turnout A" in out
    assert "state=CLOSED" in out
    assert "feedback_sensor=yes" in out
    assert out.index("system_id=") < out.index("name=")


async def test_turnout_find_by_username(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "Layout Turnout BL")
    assert code == 0
    assert "system_id=IT101" in out


async def test_turnout_find_unknown_name(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "find", "tgv")
    assert code == 1
    assert "Unknown turnout 'tgv'" in err


async def test_turnout_findr_matches_regex(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "^Layout")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_findr_no_match(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "zzz")
    assert code == 0
    assert "No turnouts match" in out


async def test_turnout_findr_invalid_regex(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_turnout_findg_matches_glob(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findg", "Layout*")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_findg_no_match(mock_turnouts, mock_power, capsys):
    code, out, _ = await run(capsys, "turnout", "findg", "zzz*")
    assert code == 0
    assert "No turnouts match" in out


async def test_signal_list_shows_dcc_system_column(mock_signals, mock_power, capsys):
    """Both fixture signals are prefix "Z" -> match "DCC++ Zou"."""
    code, out, _ = await run(capsys, "signal", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "DCC system" in header
    lines = [l for l in out.splitlines() if l.startswith("ZF")]
    assert all("DCC++ Zou" in l for l in lines)


async def test_signal_find_shows_dcc_system(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "find", "Entry Signal A")
    assert code == 0
    assert "dcc_system=DCC++ Zou" in out


async def test_signal_list_shows_comment_column(mock_signals, mock_power, capsys):
    """Neither fixture signal has a comment set -> shows as "-"."""
    code, out, _ = await run(capsys, "signal", "list")
    assert code == 0
    header = out.splitlines()[0]
    assert "Comment" in header


async def test_signal_find_shows_comment(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "find", "Entry Signal A")
    assert code == 0
    assert "comment=-" in out


async def test_signal_list_all(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "list")
    assert code == 0
    assert "Entry Signal A" in out and "Hp1" in out
    assert "ZF$dsm:DB-HV-1969:block(45)" in out and "Hp0" in out


async def test_signal_byaspect_sorts_by_aspect_column(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "byaspect")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("ZF")]
    # Hp0 < Hp1 alphabetically.
    assert "Hp0" in lines[0]
    assert "Hp1" in lines[1]
    assert "Aspect ▼" in out


async def test_signal_status_one(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "status", "Entry Signal A")
    assert code == 0
    assert out.strip() == (
        "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) "
        "aspect=Hp1 comment=- dcc_system=DCC++ Zou address=31"
    )


async def test_signal_status_unknown(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "status", "tgv")
    assert code == 1
    assert "Unknown signal mast 'tgv'" in err


async def test_signal_find_by_username(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "find", "Entry Signal A")
    assert code == 0
    assert out.strip() == (
        "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) "
        "aspect=Hp1 comment=- dcc_system=DCC++ Zou address=31"
    )


async def test_signal_find_by_system_id(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "find", "ZF$dsm:DB-HV-1969:block(45)")
    assert code == 0
    assert "Hp0" in out


async def test_signal_find_unknown_name(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "find", "tgv")
    assert code == 1
    assert "Unknown signal mast 'tgv'" in err


async def test_signal_findr_matches_regex(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "findr", "^Entry")
    assert code == 0
    assert "Entry Signal A" in out
    assert "Hp0" not in out


async def test_signal_findr_no_match(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "findr", "zzz")
    assert code == 0
    assert "No signal masts match" in out


async def test_signal_findr_invalid_regex(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_signal_findg_matches_glob(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "findg", "Entry*")
    assert code == 0
    assert "Entry Signal A" in out
    assert "Hp0" not in out


async def test_signal_findg_no_match(mock_signals, mock_power, capsys):
    code, out, _ = await run(capsys, "signal", "findg", "zzz*")
    assert code == 0
    assert "No signal masts match" in out


async def test_signal_set_aspect_and_confirms(monkeypatch, power_fixture, capsys):
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

    post_bodies = []
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json=power_fixture))
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
        code, out, _ = await run(capsys, "signal", "set", "Entry Signal A", "Hp0")
    assert code == 0
    assert out.strip() == (
        "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) "
        "aspect=Hp0 comment=- dcc_system=DCC++ Zou address=31"
    )
    # Regression guard: see matching comment in tests/test_tools.py - JMRI's
    # POST handler reads "state", not "aspect".
    assert post_bodies == [{"name": "ZF$dsm:DB-HV-1969:block(31)", "state": "Hp0"}]


async def test_sensor_list_all(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "list")
    assert code == 0
    assert "ISCLOCKRUNNING" in out and "ACTIVE" in out
    assert "Montagne B" in out and "INACTIVE" in out


async def test_sensor_byid_sorts_by_system_id(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "byid")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith(("IS", "RS"))]
    assert [l.split()[0] for l in lines] == ["ISCLOCKRUNNING", "RS22", "RS23"]
    assert "System ID ▼" in out


async def test_sensor_findr_bystate_sorts_filtered_results(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "findr", "bystate", "^Montagne")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("RS")]
    # ACTIVE < INACTIVE alphabetically; RS23 is ACTIVE, RS22 is INACTIVE.
    assert [l.split()[0] for l in lines] == ["RS23", "RS22"]


async def test_sensor_status_one(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "status", "Montagne B")
    assert code == 0
    assert out.strip() == "name=Montagne B system_id=RS22 state=INACTIVE"


async def test_sensor_status_unknown(mock_sensors, capsys):
    code, _, err = await run(capsys, "sensor", "status", "tgv")
    assert code == 1
    assert "Unknown sensor 'tgv'" in err


async def test_sensor_find_by_username(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "find", "Montagne B")
    assert code == 0
    assert out.strip() == "name=Montagne B system_id=RS22 state=INACTIVE"


async def test_sensor_find_by_system_id(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "find", "RS23")
    assert code == 0
    assert "name=Montagne A int" in out


async def test_sensor_find_unknown_name(mock_sensors, capsys):
    code, _, err = await run(capsys, "sensor", "find", "tgv")
    assert code == 1
    assert "Unknown sensor 'tgv'" in err


async def test_sensor_findr_matches_regex(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "findr", "^Montagne B")
    assert code == 0
    assert "Montagne B" in out
    assert "Montagne A int" not in out


async def test_sensor_findr_no_match(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "findr", "zzz")
    assert code == 0
    assert "No sensors match" in out


async def test_sensor_findr_invalid_regex(mock_sensors, capsys):
    code, _, err = await run(capsys, "sensor", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_sensor_findg_matches_glob(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "findg", "Montagne B")
    assert code == 0
    assert "Montagne B" in out
    assert "Montagne A int" not in out


async def test_sensor_findg_no_match(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "findg", "zzz*")
    assert code == 0
    assert "No sensors match" in out


async def test_block_list_all(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "list")
    assert code == 0
    assert "Montagne A" in out and "UNOCCUPIED" in out
    assert "Montagne B" in out and "OCCUPIED" in out


async def test_block_bysensor_sorts_by_sensor_column(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "bysensor")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IB")]
    # RS22 < RS42 alphabetically; IB1 uses RS22, IB2 uses RS42.
    assert [l.split()[0] for l in lines] == ["IB1", "IB2"]
    assert "Sensor ▼" in out


async def test_block_findg_byid_sorts_filtered_results(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "findg", "byid", "Montagne*")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IB")]
    assert [l.split()[0] for l in lines] == ["IB1", "IB2"]


async def test_block_status_one(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "status", "Montagne B")
    assert code == 0
    assert out.strip() == (
        "name=Montagne B system_id=IB2 state=OCCUPIED sensor=RS42 value=None "
        "length=1661.63 curvature=1 speed=Sixty comment=-"
    )


async def test_block_status_unknown(mock_blocks, capsys):
    code, _, err = await run(capsys, "block", "status", "tgv")
    assert code == 1
    assert "Unknown block 'tgv'" in err


async def test_block_find_by_username(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "find", "Montagne B")
    assert code == 0
    assert out.strip() == (
        "name=Montagne B system_id=IB2 state=OCCUPIED sensor=RS42 value=None "
        "length=1661.63 curvature=1 speed=Sixty comment=-"
    )


async def test_block_find_by_system_id(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "find", "IB1")
    assert code == 0
    assert "name=Montagne A" in out


async def test_block_find_unknown_name(mock_blocks, capsys):
    code, _, err = await run(capsys, "block", "find", "tgv")
    assert code == 1
    assert "Unknown block 'tgv'" in err


async def test_block_findr_matches_regex(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "findr", "^Montagne B")
    assert code == 0
    assert "Montagne B" in out
    assert "Montagne A" not in out


async def test_block_findr_no_match(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "findr", "zzz")
    assert code == 0
    assert "No blocks match" in out


async def test_block_findr_invalid_regex(mock_blocks, capsys):
    code, _, err = await run(capsys, "block", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_block_findg_matches_glob(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "findg", "Montagne B")
    assert code == 0
    assert "Montagne B" in out
    assert "Montagne A" not in out


async def test_block_findg_no_match(mock_blocks, capsys):
    code, out, _ = await run(capsys, "block", "findg", "zzz*")
    assert code == 0
    assert "No blocks match" in out


async def test_throttle_stop_one_address(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "stop", "3")
    assert code == 0
    assert "address=3 stopped" in out


async def test_throttle_bare_lists_touched_locomotives(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle")
    assert "No locomotives touched yet" in out

    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    assert "3" in out


async def test_throttle_speed_no_value_reads_current_speed(fake_jmri, capsys):
    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    code, out, _ = await run(capsys, "throttle", "speed", "3")
    assert code == 0
    # The one-shot --hold auto-stops back to 0 before returning, so
    # a subsequent read (a fresh one-shot connection) sees 0, not 40 —
    # correct, the loco really isn't moving anymore.
    assert "address=3 speed=0%" in out


async def test_throttle_speed_without_seconds_is_rejected(fake_jmri, capsys):
    code, out, err = await run(capsys, "throttle", "speed", "3", "40")
    assert code == 2
    assert "--hold is required" in err


async def test_throttle_speed_uses_roster_dcc_system_prefix(fake_jmri, roster_fixture, power_fixture, capsys, monkeypatch):
    """Regression test for issue #60's reported bug: `jmri-cli throttle
    speed <cars> 20` must acquire through the locomotive's own DccSystem
    roster attribute (e.g. Taya, prefix "T"), not JMRI's default command
    station -- otherwise the speed command is accepted by JMRI but
    inaudible to the decoder on the other DCC bus, so it never moves."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url
    from jmri_core.jmri_ws import JmriWsClient

    roster_fixture[0]["data"]["address"] = "5"
    roster_fixture[0]["data"]["attributes"] = [{"name": "DccSystem", "value": "T"}]

    calls = []
    original = JmriWsClient.acquire_throttle

    async def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(JmriWsClient, "acquire_throttle", spy)

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "5", "20", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    prefix = kwargs.get("prefix", args[-1] if len(args) >= 2 else None)
    assert prefix == "T"


async def test_throttle_speed_falls_back_to_default_when_no_dcc_system(fake_jmri, roster_fixture, power_fixture, capsys, monkeypatch):
    """The common case (no DccSystem attribute set) must keep acquiring
    against JMRI's default command station, exactly as before this fix."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url
    from jmri_core.jmri_ws import JmriWsClient

    calls = []
    original = JmriWsClient.acquire_throttle

    async def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(JmriWsClient, "acquire_throttle", spy)

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "4", "20", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert len(calls) == 1
    args, kwargs = calls[0]
    prefix = kwargs.get("prefix", args[-1] if len(args) >= 2 else None)
    assert prefix is None


async def test_throttle_speed_scales_by_roster_max_speed_percent(fake_jmri, roster_fixture, power_fixture, capsys, monkeypatch):
    """PanelPro parity: with the loco's "Throttle Speed Limit" set to 20%,
    `throttle speed 4 100` must send 20% real decoder speed over the wire
    (like PanelPro's own slider does client-side) at the peak of the hold
    -- the printed final line is always 0% since a bounded one-shot hold
    auto-stops before returning (see test_throttle_speed_negative_is_reverse_shorthand)."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url
    from jmri_core.jmri_ws import JmriWsClient

    roster_fixture[1]["data"]["address"] = "4"
    roster_fixture[1]["data"]["maxSpeedPct"] = 20

    sent_speeds = []
    original_set_speed = JmriWsClient.set_speed

    async def spy_set_speed(self, throttle_id, speed):
        sent_speeds.append(speed)
        return await original_set_speed(self, throttle_id, speed)

    monkeypatch.setattr(JmriWsClient, "set_speed", spy_set_speed)

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "4", "100", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert 0.2 in sent_speeds  # held at 20% of the raw decoder ceiling, not 100%


async def test_throttle_speed_no_scaling_when_max_speed_percent_default(fake_jmri, roster_fixture, power_fixture, capsys, monkeypatch):
    """The common case (no PanelPro speed limit set, maxSpeedPct=100) must
    keep sending the raw requested fraction unscaled, exactly as before
    this feature."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url
    from jmri_core.jmri_ws import JmriWsClient

    sent_speeds = []
    original_set_speed = JmriWsClient.set_speed

    async def spy_set_speed(self, throttle_id, speed):
        sent_speeds.append(speed)
        return await original_set_speed(self, throttle_id, speed)

    monkeypatch.setattr(JmriWsClient, "set_speed", spy_set_speed)

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "4", "40", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert 0.4 in sent_speeds


async def test_throttle_speed_shows_system_suffix_for_non_default_prefix(fake_jmri, roster_fixture, power_fixture, capsys):
    """The printed speed line must append " system=<name>" when the loco's
    resolved DccSystem prefix differs from JMRI's default command station
    -- so a multi-station layout can tell which physical bus a command
    actually reached."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url

    roster_fixture[0]["data"]["address"] = "5"
    roster_fixture[0]["data"]["attributes"] = [{"name": "DccSystem", "value": "O"}]

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "5", "40", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert "system=DCC++ Ohara" in out


async def test_throttle_speed_omits_system_suffix_for_default_prefix(fake_jmri, roster_fixture, power_fixture, capsys):
    """The common single-station case must never show a "system=" suffix,
    to avoid cluttering every speed message."""
    import respx
    from httpx import Response
    from jmri_core.config import get_jmri_url

    router = respx.mock(assert_all_called=False)
    router.start()
    router.get(f"{get_jmri_url()}/json/roster").mock(return_value=Response(200, json=roster_fixture))
    router.get(f"{get_jmri_url()}/json/power").mock(return_value=Response(200, json=power_fixture))
    try:
        code, out, _ = await run(capsys, "throttle", "speed", "4", "40", "--hold", "1")
    finally:
        router.stop()

    assert code == 0
    assert "system=" not in out


async def test_throttle_stop_no_loco_stops_every_cached_address(fake_jmri, capsys):
    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    await run(capsys, "throttle", "speed", "7", "40", "--hold", "1")

    code, out, _ = await run(capsys, "throttle", "stop")
    assert code == 0
    assert "address=3 stopped" in out
    assert "address=7 stopped" in out


async def test_throttle_stop_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, err = await run(capsys, "throttle", "stop")
    assert code == 0
    assert "nothing to stop" in err


async def test_throttle_forward_and_reverse(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "forward", "3")
    assert code == 0
    assert "address=3 direction=forward" in out

    code, out, _ = await run(capsys, "throttle", "reverse", "3")
    assert code == 0
    assert "address=3 direction=reverse" in out


async def test_throttle_forward_reverse_stationary_no_seconds_required(fake_jmri, capsys):
    """A stationary loco's direction flip needs no --hold: the mandatory
    check only fires once JMRI is known (post-acquire) to be moving."""
    code, out, _ = await run(capsys, "throttle", "forward", "3")
    assert code == 0
    code, out, _ = await run(capsys, "throttle", "reverse", "3")
    assert code == 0


async def test_throttle_reverse_while_moving_requires_seconds(fake_jmri, capsys):
    """A one-shot `speed --hold` call always auto-stops back to 0 before
    returning, so "already moving" can only be observed via a connection
    still holding a nonzero speed - i.e. the shell's shared client. Drive
    _execute_speed_change directly (mirroring throttle_speed's one-shot
    target computation) to get the loco moving without letting the
    connection close, then hit the same mandatory-check via the CLI."""
    from jmri_cli._common import cli_throttle_id
    from jmri_cli.throttle import _execute_speed_change
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        throttle_id = cli_throttle_id(3)
        await client.acquire_throttle(throttle_id, 3)
        await _execute_speed_change(
            client, throttle_id,
            target_forward=None, target_fraction=0.4,
            rampup=None, rampdown=None, hold_seconds=None,
        )
        assert (client.throttle_state(throttle_id) or {}).get("speed") == 0.4
    finally:
        await client.close()

    code, out, err = await run(capsys, "throttle", "reverse", "3")
    assert code == 2
    assert "--hold is required" in err


async def test_throttle_forward_no_loco_covers_every_touched_locomotive(fake_jmri, capsys):
    await run(capsys, "throttle", "reverse", "3")
    await run(capsys, "throttle", "reverse", "7")

    code, out, _ = await run(capsys, "throttle", "forward")
    assert code == 0
    assert "address=3 direction=forward" in out
    assert "address=7 direction=forward" in out


async def test_throttle_forward_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "forward")
    assert code == 0
    assert out.strip() != ""


async def test_throttle_forward_inside_shell_with_no_loco_uses_touched_cache(fake_jmri, capsys):
    from jmri_cli.throttle import throttle_direction
    from jmri_core.jmri_ws import JmriWsClient

    await run(capsys, "throttle", "reverse", "3")
    await run(capsys, "throttle", "reverse", "7")

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "forward"])
        code = await throttle_direction(args, forward=True, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 direction=forward" in out
        assert "address=7 direction=forward" in out
    finally:
        await client.close()


async def test_throttle_speed_negative_is_reverse_shorthand(fake_jmri, capsys, monkeypatch):
    """`speed <loco> -40` must set direction=reverse, speed=40% at the peak
    of the hold, and never send JMRI's real -1.0 emergency-stop sentinel
    over the wire (the printed final speed is 0%, since a bounded one-shot
    hold always auto-stops - see the intermediate-speed assertion below)."""
    sent_speeds = []
    from jmri_core.jmri_ws import JmriWsClient

    original_set_speed = JmriWsClient.set_speed

    async def spy_set_speed(self, throttle_id, speed):
        sent_speeds.append(speed)
        return await original_set_speed(self, throttle_id, speed)

    monkeypatch.setattr(JmriWsClient, "set_speed", spy_set_speed)

    code, out, _ = await run(capsys, "throttle", "speed", "3", "-40", "--hold", "1")
    assert code == 0
    assert "address=3 speed=0%" in out  # auto-stopped after the hold
    assert 0.4 in sent_speeds  # but it really did hold at 40% first
    assert -1.0 not in sent_speeds


async def test_throttle_speed_negative_toggles_direction_each_time(fake_jmri, capsys):
    """`speed <loco> -N` is a TOGGLE relative to the loco's current
    direction, not an absolute "always reverse" - regression test for a
    real bug reported live: forward -> `-20` correctly went reverse, but a
    second `-20` (already reverse) incorrectly stayed reverse instead of
    flipping back to forward, because the old code unconditionally forced
    target_forward=False on any negative value. Sequence here mirrors the
    exact one that surfaced it: reverse (explicit) -> negative speed
    (must flip back to forward) -> negative speed again (must flip back to
    reverse)."""
    await run(capsys, "throttle", "reverse", "3")
    code, out, _ = await run(capsys, "throttle", "speed", "3", "-40", "--hold", "1")
    assert code == 0
    assert "direction=forward" in out

    code, out, _ = await run(capsys, "throttle", "speed", "3", "-40", "--hold", "1")
    assert code == 0
    assert "direction=reverse" in out


async def test_throttle_speed_positive_never_touches_direction(fake_jmri, capsys):
    """A positive speed must never flip direction, however many times it's
    repeated - this is what keeps `forward`/`reverse` meaningful as
    separate commands from plain `speed`."""
    await run(capsys, "throttle", "reverse", "3")
    code, out, _ = await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    assert code == 0
    assert "direction=reverse" in out

    code, out, _ = await run(capsys, "throttle", "speed", "3", "20", "--hold", "1")
    assert code == 0
    assert "direction=reverse" in out


class _FastSleepAsyncio:
    """Proxy for jmri_ws.ramp's own `asyncio` reference with `sleep` stubbed
    to instant. Patching `jmri_core.jmri_ws.ramp.asyncio.sleep` directly
    would mutate the REAL asyncio module (import asyncio just binds the
    same module object - see ramp.py's own note on why ramp_speed's
    `sleep` param is resolved fresh instead of bound as a default), which
    breaks fake_jmri's live websockets server (handshake/keepalive rely on
    real sleep timing). Rebinding just the module-level name in
    jmri_ws.ramp's namespace to this proxy keeps the patch scoped to only
    the calls ramp.py itself makes."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, _seconds):
        return None


async def test_throttle_speed_with_rampup_rampdown_reaches_target(fake_jmri, capsys, monkeypatch):
    """--rampup/--rampdown should still land exactly on the target speed,
    with the ramp's intermediate sleeps stubbed out so the test is fast."""
    import asyncio as real_asyncio

    monkeypatch.setattr("jmri_core.jmri_ws.ramp.asyncio", _FastSleepAsyncio(real_asyncio))

    code, out, _ = await run(
        capsys, "throttle", "speed", "3", "40",
        "--rampup", "2", "--rampdown", "2", "--hold", "1",
    )
    assert code == 0
    # The bounded hold auto-stops back to 0 at the end of a one-shot call.
    assert "address=3 speed=0%" in out


async def test_throttle_stop_with_rampdown(fake_jmri, capsys, monkeypatch):
    import asyncio as real_asyncio

    monkeypatch.setattr("jmri_core.jmri_ws.ramp.asyncio", _FastSleepAsyncio(real_asyncio))

    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    code, out, _ = await run(capsys, "throttle", "stop", "3", "--rampdown", "2")
    assert code == 0
    assert "address=3 stopped" in out


async def test_throttle_stop_inside_shell_with_no_loco_uses_touched_cache(fake_jmri, capsys):
    """`stop` with no loco falls back to state.py's local touched-address
    cache the same way one-shot or from the shell — not mandatory in the
    shell, same "loco optional" pattern as engine-start/engine-stop/on/off/
    forward/reverse."""
    from jmri_cli.throttle import throttle_stop
    from jmri_core.jmri_ws import JmriWsClient

    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "stop"])
        code = await throttle_stop(args, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 stopped" in out
    finally:
        await client.close()


async def test_throttle_estop_one_address(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "estop", "3")
    assert code == 0
    assert "address=3 emergency-stopped" in out


async def test_throttle_estop_no_loco_covers_every_cached_address(fake_jmri, capsys):
    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    await run(capsys, "throttle", "speed", "7", "40", "--hold", "1")

    code, out, _ = await run(capsys, "throttle", "estop")
    assert code == 0
    assert "address=3 emergency-stopped" in out
    assert "address=7 emergency-stopped" in out


async def test_throttle_estop_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, err = await run(capsys, "throttle", "estop")
    assert code == 0
    assert out.strip() != "" or err.strip() != ""


async def test_throttle_estop_inside_shell_with_no_loco_uses_touched_cache(fake_jmri, capsys):
    """`estop` with no loco falls back to state.py's local touched-address
    cache the same way one-shot or from the shell — not mandatory in the
    shell, same "loco optional" pattern as stop/engine-start/engine-stop/
    on/off/forward/reverse."""
    from jmri_cli.throttle import throttle_estop
    from jmri_core.jmri_ws import JmriWsClient

    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "estop"])
        code = await throttle_estop(args, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 emergency-stopped" in out
    finally:
        await client.close()


async def test_throttle_speed_ctrl_c_during_hold_ramps_to_zero(fake_jmri, capsys):
    """Ctrl-C (task cancellation, the real mechanism asyncio.run() uses to
    deliver a KeyboardInterrupt into a running coroutine) during a bounded
    --hold must ramp the loco back to 0 before the interrupt
    propagates, rather than leaving it coasting."""
    import asyncio

    from jmri_cli.throttle import _execute_speed_change
    from jmri_cli._common import cli_throttle_id
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        throttle_id = cli_throttle_id(3)
        await client.acquire_throttle(throttle_id, 3)

        task = asyncio.ensure_future(_execute_speed_change(
            client, throttle_id,
            target_forward=None, target_fraction=0.4,
            rampup=None, rampdown=None, hold_seconds=30,
        ))
        await asyncio.sleep(0.05)  # let it reach the hold's sleep(30)
        task.cancel()

        raised = False
        try:
            await task
        except asyncio.CancelledError:
            raised = True
        assert raised
        state = client.throttle_state(throttle_id) or {}
        assert state.get("speed") == 0.0
    finally:
        await client.close()


async def test_throttle_speed_hold_in_shell_returns_immediately(fake_jmri, capsys):
    """`speed --hold` inside the shell (client given) must print a
    "started"-style line and return right away, not block for the hold's
    duration - the core regression test for issue #47."""
    import time

    from jmri_cli.throttle import throttle_speed
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "speed", "3", "40", "--hold", "30"])
        started = time.monotonic()
        code = await throttle_speed(args, client=client)
        elapsed = time.monotonic() - started
        assert code == 0
        assert elapsed < 2.0

        out, _ = capsys.readouterr()
        assert "address=3 speed=40%" in out
        assert "holding 30s, then auto-stop" in out

        from jmri_cli._common import background_holds
        assert 3 in background_holds
        task = background_holds[3]
        await asyncio.sleep(0)  # let _run() start before cancelling it
        task.cancel()
        await task  # swallows its own CancelledError, see _background_hold
    finally:
        await client.close()


async def test_throttle_speed_hold_in_shell_auto_stops_in_background(fake_jmri, capsys):
    """The backgrounded hold must still really ramp to the target and
    auto-stop after it elapses, exactly as the blocking one-shot path
    does - only the *waiting* moved off the shell's main loop."""
    import asyncio

    from jmri_cli._common import background_holds
    from jmri_cli.throttle import throttle_speed
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "speed", "3", "40", "--hold", "0.2"])
        code = await throttle_speed(args, client=client)
        assert code == 0
        capsys.readouterr()

        task = background_holds.get(3)
        assert task is not None
        await asyncio.wait_for(task, timeout=2.0)

        throttle_id = "cli3"
        state = client.throttle_state(throttle_id) or {}
        assert state.get("speed") == 0.0
    finally:
        await client.close()


async def test_throttle_speed_hold_supersedes_pending_hold_same_address(fake_jmri, capsys):
    """A second `speed --hold` on the same address while one is still
    pending must cancel/replace it rather than let both race - the
    issue's own explicit requirement."""
    import asyncio

    from jmri_cli._common import background_holds
    from jmri_cli.throttle import throttle_speed
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        args1 = build_parser().parse_args(["throttle", "speed", "3", "40", "--hold", "30"])
        await throttle_speed(args1, client=client)
        capsys.readouterr()
        first_task = background_holds[3]
        assert not first_task.done()

        args2 = build_parser().parse_args(["throttle", "speed", "3", "80", "--hold", "0.2"])
        code = await throttle_speed(args2, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 speed=80%" in out

        second_task = background_holds[3]
        assert second_task is not first_task

        await first_task  # swallows its own CancelledError, see _background_hold

        await asyncio.wait_for(second_task, timeout=2.0)
        state = client.throttle_state("cli3") or {}
        assert state.get("speed") == 0.0
    finally:
        await client.close()


async def test_throttle_direction_hold_in_shell_returns_immediately(fake_jmri, capsys):
    """`forward`/`reverse --hold` gets the identical shell-mode
    backgrounding treatment as `speed --hold`, for consistency (the
    issue's own suggestion)."""
    import time

    from jmri_cli.throttle import throttle_direction
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        await client.acquire_throttle("cli3", 3)
        await client.set_speed("cli3", 0.5)

        args = build_parser().parse_args(["throttle", "reverse", "3", "--hold", "30"])
        started = time.monotonic()
        code = await throttle_direction(args, forward=False, client=client)
        elapsed = time.monotonic() - started
        assert code == 0
        assert elapsed < 2.0

        out, _ = capsys.readouterr()
        assert "address=3 direction=reverse" in out
        assert "holding 30s, then auto-stop" in out

        from jmri_cli._common import background_holds
        task = background_holds[3]
        await asyncio.sleep(0)  # let _run() start before cancelling it
        task.cancel()
        await task  # swallows its own CancelledError, see _background_hold
    finally:
        await client.close()


async def test_shell_exit_awaits_pending_hold_before_closing(fake_jmri, capsys, monkeypatch):
    """A pending background hold must be cancelled and awaited (ramping
    the loco back to 0) as part of shell exit, not abandoned when the
    connection closes - mirrors the MCP server's own shutdown guarantee
    for its background ramps."""
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(EOFError))

    from jmri_cli.shell import run_shell
    from jmri_cli._common import background_holds
    from jmri_cli.throttle import throttle_speed
    from jmri_core.jmri_ws import JmriWsClient

    holder = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "speed", "3", "40", "--hold", "30"])
        await throttle_speed(args, client=holder)
        capsys.readouterr()
        assert 3 in background_holds
        task = background_holds[3]
        assert not task.done()

        await run_shell()

        assert task.done()
        state = holder.throttle_state("cli3") or {}
        assert state.get("speed") == 0.0
    finally:
        await holder.close()


async def test_throttle_on_with_function_number(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "on", "3", "1")
    assert code == 0
    assert "address=3 F1=on" in out


async def test_throttle_off_with_function_number(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "off", "3", "1")
    assert code == 0
    assert "address=3 F1=off" in out


async def test_throttle_on_no_function_uses_roster_labels(fake_jmri, monkeypatch, roster_fixture, capsys):
    # fake_jmri (WebSocket fixture) repoints JMRI_URL at its own local port
    # for the throttle half of this command, so get_roster()'s plain HTTP
    # call can't be mocked via respx against MOCK_JMRI_URL at the same
    # time — stub it directly instead, same approach the old stop-all test
    # used for this exact collision.
    async def fake_get_roster():
        return [{"address": 2, "name": "141R"}, {"address": 4, "name": "Autorail"},
                 {"address": 8, "name": "Boite à Sel"}]

    async def fake_get_labels(name):
        return {
            "Autorail": {0: "Lumières avant", 1: "Lumières cabine", 2: "Lumières arrière"},
            "Boite à Sel": {},
        }.get(name, {})

    monkeypatch.setattr("jmri_cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_cli.throttle.get_roster_function_labels", fake_get_labels)

    # Autorail (address=4) has F0/F1/F2 labeled.
    code, out, _ = await run(capsys, "throttle", "on", "4")
    assert code == 0
    assert "address=4 F0=on" in out
    assert "address=4 F1=on" in out
    assert "address=4 F2=on" in out


async def test_throttle_on_no_function_no_labels_is_explicit_error(fake_jmri, monkeypatch, capsys):
    async def fake_get_roster():
        return [{"address": 8, "name": "Boite à Sel"}]

    async def fake_get_labels(name):
        return {}

    monkeypatch.setattr("jmri_cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_cli.throttle.get_roster_function_labels", fake_get_labels)

    # Boite à Sel (address=8) has no labeled functions.
    code, _, err = await run(capsys, "throttle", "on", "8")
    assert code == 1
    assert "no labeled functions" in err


def _patch_autorail_roster(monkeypatch):
    async def fake_get_roster():
        return [{"address": 2, "name": "141R"}, {"address": 4, "name": "Autorail"},
                 {"address": 8, "name": "Boite à Sel"}]

    async def fake_get_labels(name):
        return {
            "Autorail": {0: "Lumières avant", 1: "Lumières cabine", 2: "Lumières arrière", 3: "Klaxon"},
            "141R": {0: "Phares"},
            "Boite à Sel": {},
        }.get(name, {})

    monkeypatch.setattr("jmri_cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_cli.throttle.get_roster_function_labels", fake_get_labels)


async def test_throttle_on_lights_only_filters_out_non_light_labels(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    code, out, _ = await run(capsys, "throttle", "on", "4", "--lights-only")
    assert code == 0
    assert "address=4 F0=on" in out
    assert "address=4 F1=on" in out
    assert "address=4 F2=on" in out
    assert "F3" not in out


async def test_throttle_off_lights_only_filters_out_non_light_labels(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    code, out, _ = await run(capsys, "throttle", "off", "4", "--lights-only")
    assert code == 0
    assert "address=4 F0=off" in out
    assert "address=4 F1=off" in out
    assert "address=4 F2=off" in out
    assert "F3" not in out


async def test_throttle_on_lights_only_no_light_labels_is_explicit_error(fake_jmri, monkeypatch, capsys):
    async def fake_get_roster():
        return [{"address": 3, "name": "141R"}]

    async def fake_get_labels(name):
        return {"141R": {3: "Klaxon"}}.get(name, {})

    monkeypatch.setattr("jmri_cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_cli.throttle.get_roster_function_labels", fake_get_labels)

    code, _, err = await run(capsys, "throttle", "on", "3", "--lights-only")
    assert code == 1
    assert "no light-labeled functions" in err


async def test_throttle_on_no_loco_covers_every_touched_locomotive(fake_jmri, monkeypatch, capsys):
    # Touch addresses 4/2 via `speed` (not `on`) to populate state.py's
    # cache without pre-setting any function state — the follow-up bare
    # `on` (no loco) then genuinely turns each labeled function on for the
    # first time. Pre-touching via `on`/`off` itself would risk hitting
    # JMRI's real silent-no-op-drop behavior on a same-value repeat across
    # two separate one-shot connections (see CLAUDE.md) — not what this
    # test is exercising.
    _patch_autorail_roster(monkeypatch)
    from jmri_cli.throttle import throttle_on

    await run(capsys, "throttle", "speed", "4", "0", "--hold", "1")
    await run(capsys, "throttle", "speed", "2", "0", "--hold", "1")

    code = await throttle_on(build_parser().parse_args(["throttle", "on"]))
    out, err = capsys.readouterr()
    assert code == 0, f"out={out!r} err={err!r}"
    assert "address=4" in out
    assert "address=2" in out


async def test_throttle_off_no_loco_and_empty_cache(fake_jmri, capsys):
    from jmri_cli.throttle import throttle_off

    code = await throttle_off(build_parser().parse_args(["throttle", "off"]))
    out, _ = capsys.readouterr()
    assert code == 0
    assert out.strip() != ""


async def test_throttle_on_inside_shell_with_no_loco_uses_touched_cache(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)
    from jmri_cli.throttle import throttle_on
    from jmri_core.jmri_ws import JmriWsClient

    await run(capsys, "throttle", "speed", "4", "0", "--hold", "1")
    await run(capsys, "throttle", "speed", "2", "0", "--hold", "1")

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "on"])
        code = await throttle_on(args, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=4" in out
        assert "address=2" in out
    finally:
        await client.close()


async def test_throttle_on_lights_only_no_loco_covers_every_touched_locomotive(fake_jmri, monkeypatch, capsys):
    # `on --lights-only` with no loco replaces the old dedicated `lights-all`
    # verb now that `on`/`off` themselves fall back to the touched-address
    # cache when no loco is given.
    _patch_autorail_roster(monkeypatch)

    await run(capsys, "throttle", "speed", "4", "0")
    await run(capsys, "throttle", "speed", "8", "0")

    code, out, err = await run(capsys, "throttle", "on", "--lights-only")
    assert code == 0, f"out={out!r} err={err!r}"
    assert "address=4 F0=on" in out
    assert "address=4 F1=on" in out
    assert "address=4 F2=on" in out


async def test_throttle_on_lights_only_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "on", "--lights-only")
    assert code == 0
    assert "no locomotives" in out.lower() or out.strip() != ""


async def test_throttle_engine_start_acquires_faces_forward_and_lights_on(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    code, out, _ = await run(capsys, "throttle", "engine-start", "4")
    assert code == 0
    assert "address=4 started" in out
    assert "forward" in out
    assert "3 light function(s) on" in out


async def test_throttle_engine_start_reports_error_honestly(monkeypatch, capsys):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    code, _, err = await run(capsys, "throttle", "engine-start", "3")
    assert code == 1
    assert err.strip() != ""


async def test_throttle_engine_start_with_no_loco_covers_every_touched_locomotive(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    await run(capsys, "throttle", "engine-stop", "4")
    await run(capsys, "throttle", "engine-stop", "8")

    code, out, _ = await run(capsys, "throttle", "engine-start")
    assert code == 0
    assert "address=4 started" in out
    assert "address=8 started" in out


async def test_throttle_engine_start_with_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "engine-start")
    assert code == 0
    assert out.strip() != ""


async def test_throttle_engine_start_inside_shell_with_no_loco_uses_touched_cache(
    fake_jmri, monkeypatch, capsys
):
    """Unlike `throttle stop`, `engine-start` with no loco is NOT an error
    inside the shell: it falls back to state.py's local touched-address
    cache, same as engine-stop, not the shell's own in-memory throttles."""
    _patch_autorail_roster(monkeypatch)
    from jmri_cli.throttle import throttle_engine_start
    from jmri_core.jmri_ws import JmriWsClient

    await run(capsys, "throttle", "engine-stop", "4")
    await run(capsys, "throttle", "engine-stop", "8")

    client = JmriWsClient()
    try:
        code = await throttle_engine_start(build_parser().parse_args(["throttle", "engine-start"]), client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=4 started" in out
        assert "address=8 started" in out
    finally:
        await client.close()


async def test_throttle_engine_start_forces_forward_when_loco_was_reversed(fake_jmri, monkeypatch, capsys):
    """Regression test for issue #59: a loco already driven into reverse by
    another connection (e.g. JMRI PanelPro) before engine-start ever touches
    it must still end up facing forward - engine-start must not trust the
    acquire reply's own "forward" field (which real JMRI doesn't guarantee to
    reflect true state on a first acquire) and silently skip the fix."""
    _patch_autorail_roster(monkeypatch)
    from jmri_core.jmri_ws import JmriWsClient

    driver = JmriWsClient()
    try:
        await driver.acquire_throttle("driver4", 4)
        await driver.set_direction("driver4", False)  # reversed, like PanelPro would do

        code, out, _ = await run(capsys, "throttle", "engine-start", "4")
        assert code == 0
        assert "address=4 started (forward" in out

        state = driver.throttle_state("driver4") or {}
        assert state.get("forward") is True
    finally:
        await driver.close()


async def test_throttle_engine_start_forces_forward_when_acquire_ack_omits_forward(
    fake_jmri, monkeypatch, capsys
):
    """Tighter regression test for issue #59's actual root cause: real JMRI's
    documented acquire-ack shape does not guarantee a "forward" field at all
    (see CLAUDE.md) - the buggy code (`if not data.get("forward", True)`)
    only failed in exactly this case, not when the field was present and
    False. Patches JmriWsClient.acquire_throttle to strip "forward" from the
    reply, so this test actually discriminates old buggy code from the fix
    (unlike the sibling test above, which passes either way since the fixture
    always echoes a real forward value)."""
    _patch_autorail_roster(monkeypatch)
    from jmri_core.jmri_ws import JmriWsClient

    driver = JmriWsClient()
    try:
        await driver.acquire_throttle("driver4", 4)
        await driver.set_direction("driver4", False)  # reversed, like PanelPro would do

        original_acquire = JmriWsClient.acquire_throttle

        async def acquire_without_forward(self, throttle_id, address, prefix=None):
            data = await original_acquire(self, throttle_id, address, prefix)
            data.pop("forward", None)
            self._throttles[throttle_id].pop("forward", None)
            return data

        monkeypatch.setattr(JmriWsClient, "acquire_throttle", acquire_without_forward)

        code, out, _ = await run(capsys, "throttle", "engine-start", "4")
        assert code == 0
        assert "address=4 started (forward" in out

        state = driver.throttle_state("driver4") or {}
        assert state.get("forward") is True
    finally:
        await driver.close()


async def test_throttle_engine_stop_ramps_faces_forward_lights_off_and_releases(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    await run(capsys, "throttle", "engine-start", "4")
    await run(capsys, "throttle", "speed", "4", "40", "--hold", "0")

    code, out, _ = await run(capsys, "throttle", "engine-stop", "4")
    assert code == 0
    assert "address=4 stopped" in out
    assert "forward" in out
    assert "lights off" in out
    assert "released" in out


async def test_throttle_engine_stop_forces_forward_when_direction_unconfirmed(fake_jmri, monkeypatch, capsys):
    """Regression test for issue #59: engine-stop must force forward even when
    this connection's own cached "forward" value was never confirmed at the
    moment execute_speed_change runs (e.g. acquired earlier in the shell
    session, but no push/reply has told this connection's cache the real
    direction yet). The bug was ramp.py's execute_speed_change defaulting an
    unset cache value to True ("assume already forward"), which made
    needs_flip silently False and skipped set_direction entirely, leaving the
    Autorail/Diesel DB reversed after a real engine-stop (live-reproduced by
    the user). The loco is actually reversed server-side (via a second,
    independent connection, mirroring JMRI PanelPro) - only THIS connection's
    cache is missing the confirmation."""
    _patch_autorail_roster(monkeypatch)
    from jmri_cli._common import cli_throttle_id
    from jmri_cli.throttle import throttle_engine_stop
    from jmri_core.jmri_ws import JmriWsClient

    driver = JmriWsClient()
    client = JmriWsClient()
    try:
        await driver.acquire_throttle("driver4", 4)
        await driver.set_direction("driver4", False)  # physically reversed

        throttle_id = cli_throttle_id(4)
        await client.acquire_throttle(throttle_id, 4)
        # Simulate "acquired earlier, direction never confirmed by this
        # connection's cache" - the real race window acquire_throttle()
        # leaves open between its own FIELD_SPEED-only cache seed and the
        # eventual reply/push that would populate FIELD_FORWARD. The
        # acquire above genuinely registers the throttle server-side (so
        # engine-stop's speed/direction/function commands aren't rejected);
        # we then strip the confirmed value from this connection's own
        # cache only, leaving the server-side state (reversed, set by
        # `driver` above) untouched.
        client._throttles[throttle_id].pop("forward", None)

        code = await throttle_engine_stop(build_parser().parse_args(["throttle", "engine-stop", "4"]), client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=4 stopped" in out
        assert "forward" in out

        state = driver.throttle_state("driver4") or {}
        assert state.get("forward") is True
    finally:
        await client.close()
        await driver.close()


async def test_throttle_engine_stop_never_acquired_still_turns_off_lights_and_releases(
    fake_jmri, monkeypatch, capsys
):
    _patch_autorail_roster(monkeypatch)

    code, out, _ = await run(capsys, "throttle", "engine-stop", "4")
    assert code == 0
    assert "address=4 stopped" in out


async def test_throttle_engine_stop_reports_error_honestly(monkeypatch, capsys):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    code, _, err = await run(capsys, "throttle", "engine-stop", "3")
    assert code == 1
    assert err.strip() != ""


async def test_throttle_engine_stop_with_no_loco_covers_every_touched_locomotive(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    await run(capsys, "throttle", "engine-start", "4")
    await run(capsys, "throttle", "engine-start", "8")

    code, out, _ = await run(capsys, "throttle", "engine-stop")
    assert code == 0
    assert "address=4 stopped" in out
    assert "address=8 stopped" in out


async def test_throttle_engine_stop_with_no_loco_and_empty_cache(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "engine-stop")
    assert code == 0
    assert out.strip() != ""


async def test_throttle_engine_stop_inside_shell_with_no_loco_uses_touched_cache(
    fake_jmri, monkeypatch, capsys
):
    """Unlike `throttle stop`, `engine-stop` with no loco is NOT an error
    inside the shell: it falls back to state.py's local touched-address
    cache (the same list `throttle` bare prints), not the shell's own
    in-memory acquired throttles — the cache is what "every known
    locomotive" means to the user, disk-persisted and shell-restart-safe."""
    _patch_autorail_roster(monkeypatch)
    from jmri_cli.throttle import throttle_engine_start, throttle_engine_stop
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        await throttle_engine_start(build_parser().parse_args(["throttle", "engine-start", "4"]), client=client)
        await throttle_engine_start(build_parser().parse_args(["throttle", "engine-start", "8"]), client=client)

        code = await throttle_engine_stop(build_parser().parse_args(["throttle", "engine-stop"]), client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=4 stopped" in out
        assert "address=8 stopped" in out
    finally:
        await client.close()


async def test_throttle_engine_stop_inside_shell_with_no_loco_and_empty_cache(fake_jmri, capsys):
    from jmri_cli.throttle import throttle_engine_stop
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        code = await throttle_engine_stop(build_parser().parse_args(["throttle", "engine-stop"]), client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert out.strip() != ""
    finally:
        await client.close()


async def test_throttle_find_resolves_fuzzy_name(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "find", "autorail")
    assert code == 0
    assert "address=4" in out and "name=Autorail" in out and "speed=-" in out


async def test_throttle_find_unknown_name(mock_roster, capsys):
    code, _, err = await run(capsys, "throttle", "find", "tgv")
    assert code == 1
    assert "Unknown locomotive 'tgv'" in err


async def test_throttle_findr_matches_regex(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "findr", "^auto")
    assert code == 0
    assert "4" in out and "Autorail" in out


async def test_throttle_findr_no_match(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "findr", "zzz")
    assert code == 0
    assert "No roster entries match" in out


async def test_throttle_findr_invalid_regex(mock_roster, mock_power, capsys):
    code, _, err = await run(capsys, "throttle", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_throttle_findg_matches_glob(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "findg", "auto*")
    assert code == 0
    assert "4" in out and "Autorail" in out


async def test_throttle_findg_no_match(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "findg", "zzz*")
    assert code == 0
    assert "No roster entries match" in out


async def test_throttle_list_shows_roster_name_for_matched_address(mock_roster, mock_power, capsys):
    from jmri_cli import state as _state

    _state.update_address(4, speed=0.4, forward=True)
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    assert "Autorail" in out


async def test_throttle_list_shows_dash_for_address_with_no_roster_entry(mock_roster, mock_power, capsys):
    from jmri_cli import state as _state

    _state.update_address(99, speed=0.4, forward=True)
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip().startswith("99")]
    assert len(lines) == 1
    assert "-" in lines[0]


async def test_throttle_list_shows_default_system_when_no_dcc_system_set(mock_roster, mock_power, capsys):
    """A roster entry with no DccSystem attribute is still actually driven
    through JMRI's default command station -- must show its name, not "-"."""
    from jmri_cli import state as _state

    _state.update_address(4, speed=0.4, forward=True)
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    autorail_line = next(l for l in out.splitlines() if l.strip().startswith("4"))
    assert "DCC++ Raijin" in autorail_line


async def test_throttle_list_falls_back_to_dash_when_jmri_unreachable(fake_jmri, capsys):
    from jmri_cli import state as _state

    fake_jmri["connected_sockets"]  # sanity: fixture is active, no HTTP roster server exists
    _state.update_address(4, speed=0.4, forward=True)
    code, out, err = await run(capsys, "throttle")
    assert code == 0
    assert "4" in out
    lines = [line for line in out.splitlines() if line.strip().startswith("4")]
    assert len(lines) == 1
    assert "-" in lines[0]
    assert "Warning" in err


async def test_throttle_find_shows_dash_name_when_resolved_by_raw_address_with_no_roster_entry(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "find", "99")
    assert code == 0
    assert "address=99" in out and "name=-" in out


async def test_throttle_find_shows_default_system_when_no_dcc_system_set(mock_roster, mock_power, capsys):
    code, out, _ = await run(capsys, "throttle", "find", "autorail")
    assert code == 0
    assert "DCC++ Raijin" in out


async def test_acquire_shortcut_matches_throttle_acquire(fake_jmri, capsys):
    """`jmri-cli acquire` (issue #61) must behave identically to `jmri-cli
    throttle acquire` - same func, same args, same output."""
    code, out, _ = await run(capsys, "acquire", "3")
    assert code == 0
    assert "address=3" in out and "(acquired)" in out


async def test_release_shortcut_matches_throttle_release(fake_jmri, capsys):
    """`jmri-cli release` (one-shot, client=None) never holds anything on
    its own connection - see issue #59: a one-shot invocation must not
    acquire-then-release, since that resets JMRI's throttle state to
    software defaults (flipping direction) instead of doing nothing."""
    code, out, _ = await run(capsys, "acquire", "3")
    assert code == 0
    code, out, _ = await run(capsys, "release", "3")
    assert code == 0
    assert "address=3 not held by this connection, nothing to release" in out


async def test_throttle_release_in_shell_actually_releases_when_held(fake_jmri, capsys):
    """Inside the shell (shared connection), releasing an address this
    connection genuinely acquired must still work for real - issue #59's
    fix only skips the acquire+release round-trip for one-shot calls that
    never held anything, not for a connection that actually does."""
    from jmri_cli._common import cli_throttle_id
    from jmri_cli.throttle import throttle_release
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        throttle_id = cli_throttle_id(3)
        await client.acquire_throttle(throttle_id, 3)
        args = build_parser().parse_args(["throttle", "release", "3"])
        code = await throttle_release(args, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 released" in out
        assert client.throttle_state(throttle_id) is None
    finally:
        await client.close()


async def test_throttle_release_turns_off_active_functions_first(fake_jmri, capsys):
    """Core regression test for the real issue #59 root cause, verified
    directly against real JMRI by the user: releasing a throttle while ANY
    function (typically lights) is still on leaves the decoder in an
    unpredictable state, observed live as a flipped direction on the
    physical locomotive. throttle_release must turn off every function this
    connection's cache knows is active before ever sending release."""
    from jmri_cli._common import cli_throttle_id
    from jmri_cli.throttle import throttle_release
    from jmri_core.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        throttle_id = cli_throttle_id(3)
        await client.acquire_throttle(throttle_id, 3)
        await client.set_function(throttle_id, 0, True)
        await client.set_function(throttle_id, 2, True)

        args = build_parser().parse_args(["throttle", "release", "3"])
        code = await throttle_release(args, client=client)
        assert code == 0
        out, _ = capsys.readouterr()
        assert "address=3 released" in out
        assert client.throttle_state(throttle_id) is None
    finally:
        await client.close()

    # Verify from a fresh connection that the functions were genuinely
    # turned off server-side before release, not just dropped from cache.
    checker = JmriWsClient()
    try:
        data = await checker.acquire_throttle("checker3", 3)
        assert data.get("speed") in (0.0, None)
        state = checker.throttle_state("checker3") or {}
        assert not any(state.get("functions", {}).values())
    finally:
        await checker.close()


async def test_throttle_release_one_shot_does_not_touch_loco_state(fake_jmri, capsys):
    """Core regression test for issue #59: a one-shot `throttle release`
    on an address already moving (acquired+driven by ANOTHER connection,
    e.g. JMRI PanelPro) must not flip its direction or otherwise touch its
    state - the bug was `throttle_release` unconditionally acquiring
    (resetting JMRI's throttle to software defaults) before releasing."""
    from jmri_core.jmri_ws import JmriWsClient

    driver = JmriWsClient()
    try:
        await driver.acquire_throttle("driver3", 3)
        await driver.set_direction("driver3", False)  # reverse
        await driver.set_speed("driver3", 0.4)

        code, out, _ = await run(capsys, "release", "3")
        assert code == 0
        assert "not held by this connection, nothing to release" in out

        state = driver.throttle_state("driver3") or {}
        assert state.get("forward") is False
        assert state.get("speed") == 0.4
    finally:
        await driver.close()


async def test_speed_shortcut_matches_throttle_speed(fake_jmri, capsys):
    """`jmri-cli speed` (issue #45) must behave identically to `jmri-cli
    throttle speed` - same func, same args, same output."""
    code, out, _ = await run(capsys, "speed", "3", "40", "--hold", "1")
    assert code == 0
    assert "address=3" in out


async def test_stop_shortcut_matches_throttle_stop(fake_jmri, capsys):
    await run(capsys, "speed", "3", "40", "--hold", "1")
    code, out, _ = await run(capsys, "stop", "3")
    assert code == 0
    assert "address=3 stopped" in out


async def test_estop_shortcut_matches_throttle_estop(fake_jmri, capsys):
    code, out, _ = await run(capsys, "estop", "3")
    assert code == 0
    assert "address=3" in out


async def test_forward_and_reverse_shortcuts_match_throttle_direction(fake_jmri, capsys):
    code, out, _ = await run(capsys, "forward", "3")
    assert code == 0
    assert "address=3 direction=forward" in out

    code, out, _ = await run(capsys, "reverse", "3")
    assert code == 0
    assert "address=3 direction=reverse" in out


async def test_engine_start_shortcut_matches_throttle_engine_start(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    code, out, _ = await run(capsys, "engine-start", "4")
    assert code == 0
    assert "address=4 started" in out


async def test_engine_stop_shortcut_matches_throttle_engine_stop(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)

    await run(capsys, "engine-start", "4")
    code, out, _ = await run(capsys, "engine-stop", "4")
    assert code == 0
    assert "address=4" in out


async def test_shortcuts_do_not_add_on_off_at_top_level():
    """on/off were deliberately excluded (issue #45) - bare `jmri-cli on`/
    `off` would read ambiguously against the existing `power on`/`off`
    group. Only `throttle on`/`off` should exist."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["on", "3", "1"])
    with pytest.raises(SystemExit):
        parser.parse_args(["off", "3", "1"])


async def test_shortcut_help_notes_it_is_a_shortcut():
    parser = build_parser()
    speed_shortcut = None
    for action in parser._subparsers._group_actions:
        speed_shortcut = action.choices.get("speed")
        if speed_shortcut:
            break
    assert speed_shortcut is not None
    assert "shortcut for `throttle speed`" in speed_shortcut.description


def _patch_fake_power(monkeypatch, live_state):
    """Monkeypatch jmri_cli.power's get_systems/set_power directly against a
    mutable {prefix: state} dict - avoids routing through real HTTP, whose
    host fake_jmri already points at its own local WS-only server for."""

    async def fake_get_systems():
        return [
            {"name": "DCC++ Ohara", "prefix": "O", "state": live_state["O"], "default": False},
            {"name": "DCC++ Raijin", "prefix": "R", "state": live_state["R"], "default": True},
        ]

    names = {"O": "DCC++ Ohara", "R": "DCC++ Raijin"}

    async def fake_set_power(prefix, turn_on):
        live_state[prefix] = 2 if turn_on else 4
        return {
            "name": names[prefix], "prefix": prefix, "state": live_state[prefix],
            "default": prefix == "R", "confirmed": True,
        }

    monkeypatch.setattr("jmri_cli.power.get_systems", fake_get_systems)
    monkeypatch.setattr("jmri_cli.power.set_power", fake_set_power)


async def test_session_start_powers_on_and_wakes_every_touched_locomotive(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)
    _patch_fake_power(monkeypatch, {"O": 4, "R": 4})
    await run(capsys, "throttle", "engine-stop", "4")
    await run(capsys, "throttle", "engine-stop", "8")

    code, out, _ = await run(capsys, "session-start")

    assert code == 0
    assert "DCC++ Ohara" in out and "ON" in out
    assert "address=4 started" in out
    assert "address=8 started" in out


async def test_session_start_with_empty_cache_just_powers_on(fake_jmri, monkeypatch, capsys):
    _patch_fake_power(monkeypatch, {"O": 4, "R": 4})

    code, out, _ = await run(capsys, "session-start")

    assert code == 0
    assert "DCC++ Ohara" in out and "ON" in out


async def test_session_end_stops_engine_stops_then_powers_off(fake_jmri, monkeypatch, capsys):
    _patch_autorail_roster(monkeypatch)
    _patch_fake_power(monkeypatch, {"O": 2, "R": 2})
    await run(capsys, "throttle", "speed", "4", "40", "--hold", "1")
    await run(capsys, "throttle", "speed", "8", "40", "--hold", "1")

    code, out, _ = await run(capsys, "session-end")

    assert code == 0
    assert "address=4 stopped" in out
    assert "address=8 stopped" in out
    assert "DCC++ Ohara" in out and "OFF" in out


async def test_session_end_with_empty_cache_just_powers_off(fake_jmri, monkeypatch, capsys):
    _patch_fake_power(monkeypatch, {"O": 2, "R": 2})

    code, out, _ = await run(capsys, "session-end")

    assert code == 0
    assert "DCC++ Ohara" in out and "OFF" in out


async def test_session_end_surfaces_partial_failure_but_still_powers_off(fake_jmri, monkeypatch, capsys):
    """A failing engine-stop step must not prevent power-off from still
    running, but the overall exit code must surface the failure (issue #49's
    "one address failing doesn't abort the rest, but still surface it")."""
    _patch_autorail_roster(monkeypatch)
    _patch_fake_power(monkeypatch, {"O": 2, "R": 2})
    await run(capsys, "throttle", "speed", "4", "40", "--hold", "1")

    async def failing_engine_stop(args, *, client=None):
        return 1

    monkeypatch.setattr("jmri_cli.session.throttle.throttle_engine_stop", failing_engine_stop)

    code, out, err = await run(capsys, "session-end")

    assert code == 1
    assert "DCC++ Ohara" in out and "OFF" in out
    assert err.strip() != ""


def test_every_leaf_subcommand_epilog_example_is_parseable():
    """Every leaf subcommand's `-h` epilog shows a runnable example - make
    sure each one actually parses, so the docs in --help can't drift from
    what the parser accepts."""
    import shlex

    parser = build_parser()

    def leaf_subparsers(p):
        for action in getattr(p, "_subparsers", None)._group_actions if p._subparsers else []:
            for name, sub in action.choices.items():
                if sub._subparsers:
                    yield from leaf_subparsers(sub)
                else:
                    yield sub

    for sub in leaf_subparsers(parser):
        if not sub.epilog:
            continue
        example_line = sub.epilog.splitlines()[-1].strip()
        assert example_line.startswith("jmri-cli "), sub.epilog
        argv = shlex.split(example_line.removeprefix("jmri-cli "))
        build_parser().parse_args(argv)


def test_main_bare_invocation_launches_shell(monkeypatch):
    """`jmri-cli` with zero arguments launches the interactive shell instead
    of going through the normal argparse dispatch path."""
    called = []

    async def fake_run_shell():
        called.append(True)

    monkeypatch.setattr("sys.argv", ["jmri-cli"])
    monkeypatch.setattr("jmri_cli.shell.run_shell", fake_run_shell)
    monkeypatch.setattr("jmri_cli._shell.run_shell", fake_run_shell)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert called == [True]


def test_main_dash_h_shows_banner_not_shell(monkeypatch, capsys):
    """`jmri-cli -h` prints the banner/command list and exits - it must NOT
    launch the shell."""
    called = []

    async def fake_run_shell():
        called.append(True)

    monkeypatch.setattr("sys.argv", ["jmri-cli", "-h"])
    monkeypatch.setattr("jmri_cli.shell.run_shell", fake_run_shell)
    monkeypatch.setattr("jmri_cli._shell.run_shell", fake_run_shell)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert called == []
    out, _ = capsys.readouterr()
    assert "jmri-cli v" in out
    assert "commands:" in out
