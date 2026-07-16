"""Tests for cli/shell.py, the interactive shell launched by bare `jmri-cli`.

Drives run_shell() end-to-end against fake_jmri (the local WebSocket
server fixture also used by test_cli.py), scripting the sequence of typed
lines by monkeypatching shell._read_line directly rather than stdin - the
shell's own dispatch, parsing, and exit-confirmation logic all run for
real.
"""

from jmri_cli import shell


def _scripted_lines(monkeypatch, lines):
    """Feed `lines` one at a time from shell._read_line, then EOF (None)."""
    queue = list(lines)

    async def fake_read_line():
        if queue:
            return queue.pop(0)
        return None

    monkeypatch.setattr(shell, "_read_line", fake_read_line)


def _no_prompt_needed(monkeypatch):
    """Fail loudly if the shell ever calls input() directly (e.g. the exit
    confirmation prompt) when a test didn't expect to be asked anything -
    catches tests that forgot a moving loco needs a scripted answer."""
    def boom(*args, **kwargs):
        raise AssertionError(f"unexpected input() call: {args!r}")

    monkeypatch.setattr("builtins.input", boom)


async def test_shell_single_shared_connection_across_commands(fake_jmri, capsys, monkeypatch):
    """The core proof this feature works: two throttle commands in the
    same shell session share one connection, so a nonzero speed set by the
    first command is still visible to the second (no re-acquire needed)."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle acquire 3", "throttle speed 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "acquired" in out
    assert "address=3 speed=0%" in out


async def test_shell_top_level_shortcut_shares_connection_like_throttle_verb(fake_jmri, capsys, monkeypatch):
    """`speed`/`stop`/etc (issue #45's top-level shortcuts) must dispatch
    through the shell exactly like their `throttle <verb>` equivalent,
    including sharing this session's one connection - not just work in
    one-shot mode."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["speed 3 40 --hold 0.05", "stop 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "address=3 speed=40%" in out
    assert "address=3 stopped" in out


async def test_shell_second_command_on_same_address_does_not_reacquire(fake_jmri, capsys, monkeypatch):
    """Regression test: every throttle_* command in cli/throttle.py calls
    acquire_throttle() unconditionally, and a second command touching an
    address already acquired earlier in the same shell session used to
    send a genuine duplicate acquire on the wire — harmless against
    fake_jmri (which just re-registers), but verified live to crash a real
    JMRI connection (ConnectionClosedError), which surfaced as the second
    command timing out. Guarded now by JmriWsClient.acquire_throttle()'s
    no-op check; this test asserts the shell-level symptom (second command
    succeeds) rather than the wire-level mechanism (covered directly in
    test_jmri_ws.py)."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle speed 3 5 --hold 0.05", "throttle stop 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "Timed out" not in out
    assert "address=3 stopped" in out


async def test_shell_seconds_bounded_speed_auto_stops_inside_shell(fake_jmri, capsys, monkeypatch):
    """Regression test: `throttle speed <loco> <pct> --hold N` inside the
    shell must auto-stop back to 0 once the hold ends, exactly like
    one-shot mode — verified live: `throttle speed 4 10 --hold 2` in the
    shell held the speed correctly for 2s but then left the locomotive
    moving forever, because _execute_speed_change's final auto-stop step
    used to be gated on one_shot (True only outside the shell). The shell
    holding its own connection open is not a reason to skip the user's
    explicit `--hold` bound."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle speed 3 40 --hold 0.05"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "address=3 speed=40%" in out
    assert "holding 0.05s, then auto-stop" in out

    from jmri_cli import state as _state
    assert _state.load_state().get("3", {}).get("speed") == 0.0


async def test_shell_non_throttle_command_runs_unchanged(mock_power, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["power status"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "DCC++ Ohara" in out


async def test_shell_rejects_sniff_with_redirect_message(fake_jmri, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle sniff"])

    await shell.run_shell()
    _, err = capsys.readouterr()
    assert "separate terminal" in err


async def test_shell_bad_line_does_not_crash_session(fake_jmri, capsys, monkeypatch):
    """A bad/unparseable line triggers argparse's SystemExit, which must be
    swallowed so a subsequent good line still runs."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle bogus-subcommand", "throttle acquire 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "acquired" in out


async def test_shell_dash_h_does_not_crash_session(fake_jmri, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle -h", "throttle acquire 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "acquired" in out


async def test_shell_bare_help_prints_front_page(fake_jmri, capsys, monkeypatch):
    """`help`/`-h`/`--help` typed bare at the prompt must print the front
    page like `jmri-cli -h` does, not hit argparse's "invalid choice" error
    (there's no top-level positional to dispatch on inside the shell)."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["help", "-h", "--help", "throttle acquire 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert out.count("commands:") == 3
    assert "invalid choice" not in out
    assert "acquired" in out


async def test_shell_mid_line_help_shows_subcommand_help(fake_jmri, capsys, monkeypatch):
    """`throttle help` (and deeper, `throttle speed help`) must show that
    subcommand's argparse help, not argparse's "invalid choice" error -
    argparse itself only ever recognizes "-h"/"--help", never the bare word
    "help", as a subcommand name."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle help", "throttle speed help", "throttle acquire 3"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "invalid choice" not in out
    assert "acquired" in out
    assert out.count("show this help message and exit") == 2


async def test_shell_exit_confirmation_not_prompted_when_nothing_moving(fake_jmri, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle acquire 3", "exit"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "in motion" not in out


async def test_shell_exit_confirmation_yes_ramps_down(fake_jmri, capsys, monkeypatch):
    """A loco left moving (no --hold given, so the shell holds it
    indefinitely — unlike a bounded --hold, which now always auto-stops
    itself even inside the shell) triggers the exit prompt; 'y' ramps it
    to 0 before the shell returns."""
    monkeypatch.setattr(shell, "SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS", 0.0)
    _scripted_lines(monkeypatch, [
        "throttle acquire 3",
        "throttle speed 3 40",
        "exit",
    ])

    prompted = []

    def fake_input(prompt=""):
        prompted.append(prompt)
        return "y"

    monkeypatch.setattr("builtins.input", fake_input)

    await shell.run_shell()
    assert len(prompted) == 1
    assert "in motion" in prompted[0] and "address(es) 3" in prompted[0]


async def test_shell_exit_confirmation_no_leaves_state_and_warns(fake_jmri, capsys, monkeypatch):
    monkeypatch.setattr(shell, "SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS", 0.0)
    _scripted_lines(monkeypatch, [
        "throttle acquire 3",
        "throttle speed 3 40",
        "exit",
    ])

    def fake_input(prompt=""):
        return "n"

    monkeypatch.setattr("builtins.input", fake_input)

    await shell.run_shell()
    _, err = capsys.readouterr()
    assert "left in their current state" in err


async def test_shell_eof_triggers_same_confirmation_as_exit(fake_jmri, capsys, monkeypatch):
    """Ctrl-D (EOFError from input(), surfaced by _read_line as None) uses
    the identical exit-confirmation path as typed `exit`/`quit`."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle acquire 3"])  # then EOF, nothing moving

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "in motion" not in out


def test_shell_history_persists_across_load_save_cycles(monkeypatch, tmp_path):
    """_save_history()/_load_history() round-trip readline's in-memory
    history through ~/.jmri-cli/shell_history (redirected to tmp_path here).

    Doesn't drive run_shell() directly: GNU readline's own history hook only
    fires for lines it reads itself via a real terminal, not for input()
    calls made through asyncio.to_thread with stdin monkeypatched (as every
    other test in this file does) - so the meaningful thing to test is the
    persistence wiring itself, with readline.add_history() standing in for
    "the user pressed Enter on a real line"."""
    if shell.readline is None:
        import pytest

        pytest.skip("readline not available on this platform")

    history_file = tmp_path / "shell_history"
    monkeypatch.setattr(shell, "HISTORY_FILE", history_file)
    shell.readline.clear_history()
    shell.readline.add_history("throttle acquire 3")
    shell.readline.add_history("throttle speed 3 40 --hold 5")

    shell._save_history()
    assert history_file.exists()

    shell.readline.clear_history()
    assert shell.readline.get_current_history_length() == 0

    shell._load_history()
    assert shell.readline.get_current_history_length() == 2
    assert shell.readline.get_history_item(1) == "throttle acquire 3"
