from jmri_mcp.cli import build_parser


async def run(capsys, *argv):
    args = build_parser().parse_args(argv)
    exit_code = await args.func(args)
    out, err = capsys.readouterr()
    return exit_code, out, err


async def test_power_status_all_systems(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "status")
    assert code == 0
    assert "DCC++ Ohara" in out and "DCC++ Zou" in out
    assert "DCC++ Raijin" in out and "(default)" in out


async def test_power_status_one_system(mock_power, capsys):
    code, out, _ = await run(capsys, "power", "status", "ohara")
    assert code == 0
    assert out.strip() == "DCC++ Ohara    : OFF"


async def test_power_status_unknown_system(mock_power, capsys):
    code, _, err = await run(capsys, "power", "status", "tgv")
    assert code == 1
    assert "Unknown system 'tgv'" in err


async def test_power_set_twice_same_state_skips_second_post(monkeypatch, capsys):
    """Real JMRI bug this guards against: re-POSTing the same power state
    (e.g. ON twice in a row) knocks the system into UNKNOWN and is hard to
    recover from. `power set` on a system already in the requested state
    must never issue a second POST."""
    import json

    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
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

        code1, out1, _ = await run(capsys, "power", "set", "ohara", "on")
        code2, out2, _ = await run(capsys, "power", "set", "ohara", "on")

    assert code1 == 0 and code2 == 0
    assert "DCC++ Ohara" in out1 and "ON" in out1
    assert "DCC++ Ohara" in out2 and "ON" in out2
    # Only the first call actually changed anything; the repeat must not
    # have sent a second POST at all.
    assert len(post_calls) == 1


async def test_power_stop_all_cuts_every_system(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
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
        code, out, _ = await run(capsys, "power", "stop-all")

    assert code == 0
    assert "DCC++ Ohara" in out and "OFF" in out
    assert "DCC++ Raijin" in out


async def test_power_start_all_restores_every_system(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
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
        code, out, _ = await run(capsys, "power", "start-all")

    assert code == 0
    assert "DCC++ Ohara" in out and "ON" in out
    assert "DCC++ Raijin" in out


async def test_roster_lists_every_entry(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster")
    assert code == 0
    assert "141R" in out and "Mikado 141 R" in out and "8273" in out
    assert "Autorail" in out and "Railcar" in out
    assert "Boite à Sel" in out and "-" in out  # empty road/model shown as "-"


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


async def test_roster_functions_lists_labels(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "functions", "autorail")
    assert code == 0
    assert "Autorail (address=4)" in out
    assert "F0: Lumières avant" in out
    assert "F2: Lumières arrière" in out


async def test_roster_functions_reports_none_labeled(mock_roster, capsys):
    code, out, _ = await run(capsys, "roster", "functions", "boite a sel")
    assert code == 0
    assert "no labeled functions" in out


async def test_light_list_all(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "list")
    assert code == 0
    assert "Depot Lighting" in out and "OFF" in out
    assert "Street Lamps" in out and "ON" in out


async def test_light_status_one(mock_lights, capsys):
    code, out, _ = await run(capsys, "light", "status", "depot")
    assert code == 0
    assert out.strip() == "Depot Lighting      : OFF"


async def test_light_status_unknown(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "status", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_turnout_list_all(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    assert "Layout Turnout A" in out and "CLOSED" in out
    assert "A / Mountain A -> Platform A/B" in out and "THROWN" in out


async def test_turnout_status_one(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "status", "Layout Turnout A")
    assert code == 0
    assert out.strip() == "Layout Turnout A    : CLOSED"


async def test_turnout_status_unknown(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "status", "tgv")
    assert code == 1
    assert "Unknown turnout 'tgv'" in err


async def test_signal_list_all(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "list")
    assert code == 0
    assert "Entry Signal A" in out and "Hp1" in out
    assert "ZF$dsm:DB-HV-1969:block(45)" in out and "Hp0" in out


async def test_signal_status_one(mock_signals, capsys):
    code, out, _ = await run(capsys, "signal", "status", "Entry Signal A")
    assert code == 0
    assert out.strip() == "Entry Signal A      : Hp1"


async def test_signal_status_unknown(mock_signals, capsys):
    code, _, err = await run(capsys, "signal", "status", "tgv")
    assert code == 1
    assert "Unknown signal mast 'tgv'" in err


async def test_signal_set_aspect_and_confirms(monkeypatch, capsys):
    import json

    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

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
    assert out.strip() == "Entry Signal A      : Hp0"
    # Regression guard: see matching comment in tests/test_tools.py - JMRI's
    # POST handler reads "state", not "aspect".
    assert post_bodies == [{"name": "ZF$dsm:DB-HV-1969:block(31)", "state": "Hp0"}]


async def test_sensor_list_all(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "list")
    assert code == 0
    assert "ISCLOCKRUNNING" in out and "ACTIVE" in out
    assert "Montagne B" in out and "INACTIVE" in out


async def test_sensor_status_one(mock_sensors, capsys):
    code, out, _ = await run(capsys, "sensor", "status", "Montagne B")
    assert code == 0
    assert out.strip() == "Montagne B          : INACTIVE"


async def test_sensor_status_unknown(mock_sensors, capsys):
    code, _, err = await run(capsys, "sensor", "status", "tgv")
    assert code == 1
    assert "Unknown sensor 'tgv'" in err


async def test_throttle_stop_all_acquires_and_stops_every_address(fake_jmri, capsys):
    code, out, _ = await run(capsys, "throttle", "stop-all", "-a", "3", "-a", "7")
    assert code == 0
    assert "address=3 emergency-stopped" in out
    assert "address=7 emergency-stopped" in out


async def test_throttle_stop_all_defaults_to_whole_roster(fake_jmri, monkeypatch, capsys):
    # fake_jmri (WebSocket fixture) already repoints JMRI_URL at its own local
    # port for the throttle acquire/stop half of this command; get_roster()
    # is a plain HTTP call jmri-cli makes first, so it's stubbed directly
    # rather than juggling JMRI_URL between two different fake servers.
    async def fake_get_roster():
        return [{"address": 2}, {"address": 4}, {"address": 8}]

    monkeypatch.setattr("jmri_mcp.cli.throttle.get_roster", fake_get_roster)

    code, out, _ = await run(capsys, "throttle", "stop-all")
    assert code == 0
    assert "address=2 emergency-stopped" in out
    assert "address=4 emergency-stopped" in out
    assert "address=8 emergency-stopped" in out
