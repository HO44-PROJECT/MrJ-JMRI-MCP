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
