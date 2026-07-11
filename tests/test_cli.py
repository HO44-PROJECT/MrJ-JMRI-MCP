import pytest

from jmri_mcp.cli import build_parser, main


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
        code, out, _ = await run(capsys, "power", "off")

    assert code == 0
    assert "DCC++ Ohara" in out and "OFF" in out
    assert "DCC++ Raijin" in out


async def test_power_on_restores_every_system(monkeypatch, capsys):
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
        code, out, _ = await run(capsys, "power", "on")

    assert code == 0
    assert "DCC++ Ohara" in out and "ON" in out
    assert "DCC++ Raijin" in out


async def test_power_on_one_system_only(monkeypatch, capsys):
    """power on <fuzzy target> narrows to just that system."""
    import json

    import respx
    from httpx import Response

    from tests.conftest import MOCK_JMRI_URL

    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
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


async def test_light_on_unknown_name(mock_lights, capsys):
    code, _, err = await run(capsys, "light", "on", "tgv")
    assert code == 1
    assert "Unknown light 'tgv'" in err


async def test_turnout_list_all(mock_turnouts, capsys):
    code, out, _ = await run(capsys, "turnout", "list")
    assert code == 0
    assert "Layout Turnout A" in out and "CLOSED" in out
    assert "A / Mountain A -> Platform A/B" in out and "THROWN" in out


async def test_turnout_closed_unknown_name(mock_turnouts, capsys):
    code, _, err = await run(capsys, "turnout", "closed", "tgv")
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
    from jmri_mcp.cli._common import cli_throttle_id
    from jmri_mcp.cli.throttle import _execute_speed_change
    from jmri_mcp.jmri_ws import JmriWsClient

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


async def test_throttle_speed_negative_is_reverse_shorthand(fake_jmri, capsys, monkeypatch):
    """`speed <loco> -40` must set direction=reverse, speed=40% at the peak
    of the hold, and never send JMRI's real -1.0 emergency-stop sentinel
    over the wire (the printed final speed is 0%, since a bounded one-shot
    hold always auto-stops - see the intermediate-speed assertion below)."""
    sent_speeds = []
    from jmri_mcp.jmri_ws import JmriWsClient

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
    """Proxy for throttle.py's own `asyncio` reference with `sleep` stubbed
    to instant. Patching `jmri_mcp.cli.throttle.asyncio.sleep` directly
    would mutate the REAL asyncio module (import asyncio just binds the
    same module object - see throttle.py's own note on why _ramp_speed's
    `sleep` param is resolved fresh instead of bound as a default), which
    breaks fake_jmri's live websockets server (handshake/keepalive rely on
    real sleep timing). Rebinding just the module-level name in
    throttle.py's namespace to this proxy keeps the patch scoped to only
    the calls throttle.py itself makes."""

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

    monkeypatch.setattr("jmri_mcp.cli.throttle.asyncio", _FastSleepAsyncio(real_asyncio))

    code, out, _ = await run(
        capsys, "throttle", "speed", "3", "40",
        "--rampup", "2", "--rampdown", "2", "--hold", "1",
    )
    assert code == 0
    # The bounded hold auto-stops back to 0 at the end of a one-shot call.
    assert "address=3 speed=0%" in out


async def test_throttle_stop_with_rampdown(fake_jmri, capsys, monkeypatch):
    import asyncio as real_asyncio

    monkeypatch.setattr("jmri_mcp.cli.throttle.asyncio", _FastSleepAsyncio(real_asyncio))

    await run(capsys, "throttle", "speed", "3", "40", "--hold", "1")
    code, out, _ = await run(capsys, "throttle", "stop", "3", "--rampdown", "2")
    assert code == 0
    assert "address=3 stopped" in out


async def test_throttle_stop_inside_shell_requires_loco(fake_jmri, capsys):
    """Per the plan: stop's "every cached address" fallback only makes
    sense one-shot; inside the shell, an omitted loco is a hard error
    rather than silently doing nothing meaningful."""
    from jmri_mcp.cli.throttle import throttle_stop
    from jmri_mcp.jmri_ws import JmriWsClient

    client = JmriWsClient()
    try:
        args = build_parser().parse_args(["throttle", "stop"])
        code = await throttle_stop(args, client=client)
        assert code == 2
        _, err = capsys.readouterr()
        assert "required" in err
    finally:
        await client.close()


async def test_throttle_speed_ctrl_c_during_hold_ramps_to_zero(fake_jmri, capsys):
    """Ctrl-C (task cancellation, the real mechanism asyncio.run() uses to
    deliver a KeyboardInterrupt into a running coroutine) during a bounded
    --hold must ramp the loco back to 0 before the interrupt
    propagates, rather than leaving it coasting."""
    import asyncio

    from jmri_mcp.cli.throttle import _execute_speed_change
    from jmri_mcp.cli._common import cli_throttle_id
    from jmri_mcp.jmri_ws import JmriWsClient

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

    monkeypatch.setattr("jmri_mcp.cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_mcp.cli.throttle.get_roster_function_labels", fake_get_labels)

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

    monkeypatch.setattr("jmri_mcp.cli.throttle.get_roster", fake_get_roster)
    monkeypatch.setattr("jmri_mcp.cli.throttle.get_roster_function_labels", fake_get_labels)

    # Boite à Sel (address=8) has no labeled functions.
    code, _, err = await run(capsys, "throttle", "on", "8")
    assert code == 1
    assert "no labeled functions" in err


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
    monkeypatch.setattr("jmri_mcp.cli.shell.run_shell", fake_run_shell)
    monkeypatch.setattr("jmri_mcp.cli._shell.run_shell", fake_run_shell)

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
    monkeypatch.setattr("jmri_mcp.cli.shell.run_shell", fake_run_shell)
    monkeypatch.setattr("jmri_mcp.cli._shell.run_shell", fake_run_shell)

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert called == []
    out, _ = capsys.readouterr()
    assert "jmri-cli v" in out
    assert "commands:" in out
