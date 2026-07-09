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
