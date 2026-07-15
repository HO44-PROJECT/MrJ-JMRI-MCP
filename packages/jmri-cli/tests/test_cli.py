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


async def test_roster_lists_every_entry(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster")
    assert code == 0
    assert "141R" in out and "Mikado 141 R" in out and "8273" in out
    assert "Autorail" in out and "Railcar" in out
    assert "Boite à Sel" in out and "-" in out  # empty road/model shown as "-"


async def test_roster_bydcc_sorts_by_address(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "bydcc")
    assert code == 0
    lines = [l for l in out.splitlines() if l.split() and l.split()[0].isdigit()]
    assert [l.split()[0] for l in lines] == ["2", "4", "8"]


async def test_roster_findr_byname_sorts_filtered_results(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "byname", ".")
    assert code == 0
    assert "141R" in out and "Autorail" in out and "Boite" in out


async def test_roster_reports_error_on_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("JMRI_URL", "http://127.0.0.1:1")
    code, _, err = await run(capsys, "roster")
    assert code == 1
    assert "Error" in err


async def test_roster_find_resolves_fuzzy_name(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "find", "autorail")
    assert code == 0
    assert "address=4" in out and "name=Autorail" in out


async def test_roster_find_unknown_name(mock_roster, capsys):
    code, _, err = await run(capsys, "roster", "find", "tgv")
    assert code == 1
    assert "Unknown locomotive 'tgv'" in err


async def test_roster_findr_matches_regex(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "^auto")
    assert code == 0
    assert "Autorail" in out
    assert "Boite" not in out


async def test_roster_findr_no_match(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "findr", "zzz")
    assert code == 0
    assert "No roster entries match" in out


async def test_roster_findr_invalid_regex(mock_roster, capsys):
    code, _, err = await run(capsys, "roster", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_roster_findg_matches_glob(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "findg", "auto*")
    assert code == 0
    assert "Autorail" in out
    assert "Boite" not in out


async def test_roster_findg_no_match(mock_roster, capsys):
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


async def test_light_list_all(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    assert "Depot Lighting" in out and "OFF" in out
    assert "Street Lamps" in out and "ON" in out
    header = out.splitlines()[0]
    assert header.index("System ID") < header.index("Light")


async def test_light_bystate_sorts_by_state_column(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "bystate")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    # OFF < ON alphabetically; IL1/IL3 are OFF, IL2 is ON.
    assert [l.split()[0] for l in lines] == ["IL1", "IL3", "IL2"]
    assert "State ▼" in out


async def test_light_findg_byid_sorts_filtered_results(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "findg", "byid", "*")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("IL")]
    assert [l.split()[0] for l in lines] == ["IL1", "IL2", "IL3"]


async def test_light_on_unknown_name(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "on", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_light_find_by_system_id(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "find", "IL1")
    assert code == 0
    assert "system_id=IL1" in out
    assert "name=Depot Lighting" in out
    assert "state=OFF" in out
    assert out.index("system_id=") < out.index("name=")


async def test_light_find_by_username(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "find", "Street Lamps")
    assert code == 0
    assert "system_id=IL2" in out


async def test_light_find_unknown_name(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "find", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_light_findr_matches_regex(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "findr", "^Depot")
    assert code == 0
    assert "Depot Lighting" in out
    assert "Street Lamps" not in out


async def test_light_findr_no_match(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "findr", "zzz")
    assert code == 0
    assert "No lights match" in out


async def test_light_findr_invalid_regex(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_light_findg_matches_glob(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "findg", "Depot*")
    assert code == 0
    assert "Depot Lighting" in out
    assert "Street Lamps" not in out


async def test_light_findg_no_match(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "findg", "zzz*")
    assert code == 0
    assert "No lights match" in out


async def test_light_on_bare_confirms_every_light(capsys):
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


async def test_turnout_list_all(mock_turnouts, capsys):
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


async def test_turnout_list_defaults_to_byname_order(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    lines = [l for l in out.splitlines() if "Layout Turnout" in l or "Mountain" in l]
    # userNames alphabetically: "A / Mountain..." < "Layout Turnout A" < "Layout Turnout BL"
    assert lines[0].startswith("OT23")
    assert "Turnout ▼" in out


async def test_turnout_bystate_sorts_by_state_column(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "bystate")
    assert code == 0
    lines = [l for l in out.splitlines() if "IT100" in l or "IT101" in l or "OT23" in l]
    # CLOSED < THROWN alphabetically; IT100/IT101 are CLOSED, OT23 is THROWN.
    assert lines[0].startswith("IT100") or lines[0].startswith("IT101")
    assert lines[-1].startswith("OT23")
    assert "State ▼" in out


async def test_turnout_byid_sorts_by_system_id(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "byid")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith(("IT", "OT"))]
    assert [l.split()[0] for l in lines] == ["IT100", "IT101", "OT23"]
    assert "System ID ▼" in out


async def test_turnout_findr_byid_sorts_filtered_results(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "byid", "^Layout")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith(("IT", "OT"))]
    assert [l.split()[0] for l in lines] == ["IT100", "IT101"]


async def test_turnout_findr_no_sort_word_still_works(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "^Layout")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_closed_unknown_name(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "close", "tgv")
    assert code == 1
    assert "Unknown turnout 'tgv'" in err


async def test_turnout_throw_bare_confirms_every_turnout(capsys):
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


async def test_turnout_find_by_system_id(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "IT100")
    assert code == 0
    assert "system_id=IT100" in out
    assert "name=Layout Turnout A" in out
    assert "state=CLOSED" in out
    assert "feedback_sensor=yes" in out
    assert out.index("system_id=") < out.index("name=")


async def test_turnout_find_by_username(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "find", "Layout Turnout BL")
    assert code == 0
    assert "system_id=IT101" in out


async def test_turnout_find_unknown_name(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "find", "tgv")
    assert code == 1
    assert "Unknown turnout 'tgv'" in err


async def test_turnout_findr_matches_regex(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "^Layout")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_findr_no_match(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findr", "zzz")
    assert code == 0
    assert "No turnouts match" in out


async def test_turnout_findr_invalid_regex(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_turnout_findg_matches_glob(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findg", "Layout*")
    assert code == 0
    assert "Layout Turnout A" in out
    assert "Mountain" not in out


async def test_turnout_findg_no_match(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "findg", "zzz*")
    assert code == 0
    assert "No turnouts match" in out


async def test_signal_list_all(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "list")
    assert code == 0
    assert "Entry Signal A" in out and "Hp1" in out
    assert "ZF$dsm:DB-HV-1969:block(45)" in out and "Hp0" in out


async def test_signal_byaspect_sorts_by_aspect_column(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "byaspect")
    assert code == 0
    lines = [l for l in out.splitlines() if l.startswith("ZF")]
    # Hp0 < Hp1 alphabetically.
    assert "Hp0" in lines[0]
    assert "Hp1" in lines[1]
    assert "Aspect ▼" in out


async def test_signal_status_one(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "status", "Entry Signal A")
    assert code == 0
    assert out.strip() == "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) aspect=Hp1"


async def test_signal_status_unknown(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "status", "tgv")
    assert code == 1
    assert "Unknown signal mast 'tgv'" in err


async def test_signal_find_by_username(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "find", "Entry Signal A")
    assert code == 0
    assert out.strip() == "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) aspect=Hp1"


async def test_signal_find_by_system_id(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "find", "ZF$dsm:DB-HV-1969:block(45)")
    assert code == 0
    assert "Hp0" in out


async def test_signal_find_unknown_name(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "find", "tgv")
    assert code == 1
    assert "Unknown signal mast 'tgv'" in err


async def test_signal_findr_matches_regex(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "findr", "^Entry")
    assert code == 0
    assert "Entry Signal A" in out
    assert "Hp0" not in out


async def test_signal_findr_no_match(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "findr", "zzz")
    assert code == 0
    assert "No signal masts match" in out


async def test_signal_findr_invalid_regex(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_signal_findg_matches_glob(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "findg", "Entry*")
    assert code == 0
    assert "Entry Signal A" in out
    assert "Hp0" not in out


async def test_signal_findg_no_match(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "findg", "zzz*")
    assert code == 0
    assert "No signal masts match" in out


async def test_signal_set_aspect_and_confirms(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from jmri_core.testing.plugin import MOCK_JMRI_URL

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
        code, out, _ = await run(capsys, "signal", "set", "Entry Signal A", "Hp0")
    assert code == 0
    assert out.strip() == "name=Entry Signal A system_id=ZF$dsm:DB-HV-1969:block(31) aspect=Hp0"
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


async def test_throttle_speed_negative_already_reverse_no_direction_noop(fake_jmri, capsys):
    """Already-reverse + another negative speed shouldn't error or hang -
    the direction no-op path (JMRI sends no reply for it) must not be
    mistaken for a missing response."""
    await run(capsys, "throttle", "reverse", "3")
    code, out, _ = await run(capsys, "throttle", "speed", "3", "-40", "--hold", "1")
    assert code == 0
    assert "address=3 speed=0%" in out


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


async def test_throttle_find_resolves_fuzzy_name(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "find", "autorail")
    assert code == 0
    assert "address=4" in out and "name=Autorail" in out and "speed=-" in out


async def test_throttle_find_unknown_name(mock_roster, capsys):
    code, _, err = await run(capsys, "throttle", "find", "tgv")
    assert code == 1
    assert "Unknown locomotive 'tgv'" in err


async def test_throttle_findr_matches_regex(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "findr", "^auto")
    assert code == 0
    assert "4" in out and "Autorail" in out


async def test_throttle_findr_no_match(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "findr", "zzz")
    assert code == 0
    assert "No roster entries match" in out


async def test_throttle_findr_invalid_regex(mock_roster, capsys):
    code, _, err = await run(capsys, "throttle", "findr", "[")
    assert code == 1
    assert "Invalid regex" in err


async def test_throttle_findg_matches_glob(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "findg", "auto*")
    assert code == 0
    assert "4" in out and "Autorail" in out


async def test_throttle_findg_no_match(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "findg", "zzz*")
    assert code == 0
    assert "No roster entries match" in out


async def test_throttle_list_shows_roster_name_for_matched_address(mock_roster, capsys):
    from jmri_cli import state as _state

    _state.update_address(4, speed=0.4, forward=True)
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    assert "Autorail" in out


async def test_throttle_list_shows_dash_for_address_with_no_roster_entry(mock_roster, capsys):
    from jmri_cli import state as _state

    _state.update_address(99, speed=0.4, forward=True)
    code, out, _ = await run(capsys, "throttle")
    assert code == 0
    lines = [line for line in out.splitlines() if line.strip().startswith("99")]
    assert len(lines) == 1
    assert "-" in lines[0]


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


async def test_throttle_find_shows_dash_name_when_resolved_by_raw_address_with_no_roster_entry(mock_roster, capsys):
    code, out, _ = await run(capsys, "throttle", "find", "99")
    assert code == 0
    assert "address=99" in out and "name=-" in out


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
