import pytest

from jmri_cli import build_parser
from jmri_cli import cache as cache_module
from jmri_cli import completion as completion_module
from jmri_cli import state as state_module


async def run(capsys, *argv):
    args = build_parser().parse_args(argv)
    exit_code = await args.func(args)
    out, err = capsys.readouterr()
    return exit_code, out, err


@pytest.fixture(autouse=True)
def isolated_history(monkeypatch, tmp_path):
    """Point cache.py's HISTORY_FILE at a tmp file, never the real
    ~/.jmri-cli/shell_history (isolated_cli_state in conftest.py already
    does the same for STATE_FILE via jmri_cli.state)."""
    monkeypatch.setattr(cache_module, "HISTORY_FILE", tmp_path / "shell_history")


@pytest.fixture(autouse=True)
def isolated_completion_cache(monkeypatch, tmp_path):
    """Point completion.py's CACHE_DIR at a tmp dir, never the real
    ~/.jmri-cli/completion_cache/ -- cache_clean's default (no flags) path
    deletes every file under it, which must never touch the real one."""
    monkeypatch.setattr(completion_module, "CACHE_DIR", tmp_path / "completion_cache")


def _write_state():
    state_module.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state_module.STATE_FILE.write_text('{"3": {"speed": 0.4}}')


def _write_history():
    cache_module.HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache_module.HISTORY_FILE.write_text("throttle speed 3 40\n")


def _write_completion_cache():
    completion_module.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    completion_module._write_cache("system", ["DCC++ Ohara"])


async def test_cache_clean_default_clears_both(capsys):
    _write_state()
    _write_history()
    _write_completion_cache()

    code, out, _ = await run(capsys, "cache", "clean")

    assert code == 0
    assert not state_module.STATE_FILE.exists()
    assert not cache_module.HISTORY_FILE.exists()
    assert not completion_module.CACHE_DIR.is_dir() or not any(completion_module.CACHE_DIR.iterdir())
    assert str(state_module.STATE_FILE) in out
    assert str(cache_module.HISTORY_FILE) in out


async def test_cache_clean_state_only(capsys):
    _write_state()
    _write_history()
    _write_completion_cache()

    code, out, _ = await run(capsys, "cache", "clean", "--state")

    assert code == 0
    assert not state_module.STATE_FILE.exists()
    assert cache_module.HISTORY_FILE.exists()
    assert any(completion_module.CACHE_DIR.iterdir())
    assert str(state_module.STATE_FILE) in out
    assert str(cache_module.HISTORY_FILE) not in out


async def test_cache_clean_history_only(capsys):
    _write_state()
    _write_history()
    _write_completion_cache()

    code, out, _ = await run(capsys, "cache", "clean", "--history")

    assert code == 0
    assert state_module.STATE_FILE.exists()
    assert not cache_module.HISTORY_FILE.exists()
    assert any(completion_module.CACHE_DIR.iterdir())
    assert str(cache_module.HISTORY_FILE) in out
    assert str(state_module.STATE_FILE) not in out


async def test_cache_clean_completions_only(capsys):
    _write_state()
    _write_history()
    _write_completion_cache()

    code, out, _ = await run(capsys, "cache", "clean", "--completions")

    assert code == 0
    assert state_module.STATE_FILE.exists()
    assert cache_module.HISTORY_FILE.exists()
    assert not any(completion_module.CACHE_DIR.iterdir())
    assert str(completion_module.CACHE_DIR) in out
    assert str(state_module.STATE_FILE) not in out
    assert str(cache_module.HISTORY_FILE) not in out


async def test_cache_clean_already_clean_is_a_no_op(capsys):
    assert not state_module.STATE_FILE.exists()
    assert not cache_module.HISTORY_FILE.exists()

    code, out, _ = await run(capsys, "cache", "clean")

    assert code == 0
    assert "Nothing to clean" in out


async def test_cache_info_shows_paths_and_status(capsys):
    _write_state()

    code, out, _ = await run(capsys, "cache", "info")

    assert code == 0
    assert str(state_module.STATE_FILE) in out
    assert str(cache_module.HISTORY_FILE) in out
    assert str(completion_module.CACHE_DIR) in out
    # state exists, history and completion cache don't -- all three facts visible
    state_line = next(line for line in out.splitlines() if str(state_module.STATE_FILE) in line)
    history_line = next(line for line in out.splitlines() if str(cache_module.HISTORY_FILE) in line)
    completion_line = next(line for line in out.splitlines() if str(completion_module.CACHE_DIR) in line)
    assert "not present" in history_line
    assert "not present" in completion_line
    assert "not present" not in state_line


async def test_cache_bare_defaults_to_info(capsys):
    code, out, _ = await run(capsys, "cache")

    assert code == 0
    assert str(state_module.STATE_FILE) in out
    assert str(cache_module.HISTORY_FILE) in out
