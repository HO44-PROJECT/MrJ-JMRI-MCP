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
