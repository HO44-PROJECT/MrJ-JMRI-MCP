"""Tests for cli/shell.py, the interactive shell launched by bare `jmri-cli`.

Drives run_shell() end-to-end against fake_jmri (the local WebSocket
server fixture also used by test_cli.py), scripting the sequence of typed
lines by monkeypatching shell._read_line directly rather than stdin - the
shell's own dispatch, parsing, and exit-confirmation logic all run for
real.

TAB-completion tests (bottom of file) are the exception: _make_completer/
_leaf_names/_subparsers_action are pure argparse-tree introspection with
no JMRI contact at all, so they're exercised directly rather than through
run_shell()'s scripted-input flow - there's no connection or dispatch
involved for readline to hook into.
"""

import pytest

from jmri_cli import shell
from jmri_cli.parser import build_parser


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


async def test_shell_semicolon_splits_into_separate_commands(fake_jmri, capsys, monkeypatch):
    """`;` on one typed line must run each segment through the exact same
    one-command-at-a-time dispatch as if each had been typed on its own
    line - not a separate inner loop. Verified here via two independent,
    unrelated commands on one line (a throttle acquire and a purely local,
    no-JMRI-contact cache read)."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle acquire 3; cache info"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "acquired" in out
    assert "throttle state" in out


async def test_shell_semicolon_exit_word_drops_remaining_segments(fake_jmri, capsys, monkeypatch):
    """An exit word among `;`-separated segments exits immediately, same as
    typing it alone - anything queued after it must never run."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["throttle acquire 3; exit; throttle acquire 7"])

    await shell.run_shell()
    out, _ = capsys.readouterr()
    assert "address=3" in out
    assert "address=7" not in out


async def test_shell_wait_blocks_until_hold_finishes_before_release(fake_jmri, capsys, monkeypatch):
    """Regression test for the real bug the user hit live: `--hold` runs in
    the background, so a `release` right after it on the same `;`-joined
    line used to race the hold and fail with JMRI's "Throttles must be
    requested with an address" once the hold's own speed command landed on
    an already-released throttle. `wait` must block until the hold
    actually completes, so `release` only ever runs after."""
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["speed 3 40 --hold 0.05; wait 3; release 3"])

    await shell.run_shell()
    out, err = capsys.readouterr()
    assert "must be requested with an address" not in err
    assert "address=3 released" in out

    from jmri_cli import state as _state
    assert _state.load_state().get("3", {}).get("speed") == 0.0


async def test_shell_wait_with_no_address_waits_for_every_pending_hold(fake_jmri, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["speed 3 40 --hold 0.05; wait; release 3"])

    await shell.run_shell()
    out, err = capsys.readouterr()
    assert "must be requested with an address" not in err
    assert "address=3 released" in out


async def test_shell_wait_with_no_pending_hold_is_a_noop(fake_jmri, capsys, monkeypatch):
    _no_prompt_needed(monkeypatch)
    _scripted_lines(monkeypatch, ["wait"])

    await shell.run_shell()
    out, err = capsys.readouterr()
    assert err == ""


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


# -- TAB completion -----------------------------------------------------
#
# _make_completer's closure reads the in-progress line via
# readline.get_line_buffer()/get_endidx(); these tests fake both with a
# tiny stand-in object rather than requiring a real readline session; the
# completer only ever calls those two functions on the `readline` module,
# so monkeypatching them is enough to drive complete(text, state) exactly
# as a real TAB press would.


def _completions(monkeypatch, buffer, text):
    """All candidates complete() would offer for `text` at end of `buffer`."""
    if shell.readline is None:
        pytest.skip("readline not available on this platform")
    monkeypatch.setattr(shell.readline, "get_line_buffer", lambda: buffer)
    monkeypatch.setattr(shell.readline, "get_endidx", lambda: len(buffer))
    complete = shell._make_completer(build_parser())
    results = []
    state = 0
    while (match := complete(text, state)) is not None:
        results.append(match)
        state += 1
    return results


def test_completion_top_level_prefix_match(monkeypatch):
    # A sole match gets a trailing space appended (see _make_completer's
    # docstring) so the next character typed doesn't glue onto its tail.
    assert _completions(monkeypatch, "thr", "thr") == ["throttle "]


def test_completion_top_level_empty_includes_groups_shortcuts_and_exit_help(monkeypatch):
    results = _completions(monkeypatch, "", "")
    assert "throttle" in results
    assert "cache" in results
    assert "speed" in results  # shortcut
    assert "acquire" in results  # shortcut
    assert "release" in results  # shortcut
    assert "exit" in results
    assert "quit" in results
    assert "help" in results


def test_completion_subcommand_prefix_match(monkeypatch):
    assert _completions(monkeypatch, "throttle sp", "sp") == ["speed "]


def test_completion_subcommand_full_listing_on_trailing_space(monkeypatch):
    results = _completions(monkeypatch, "throttle ", "")
    assert "speed" in results
    assert "acquire" in results
    assert "release" in results
    assert "sniff" in results


def test_completion_flag_prefix_match_on_a_leaf(monkeypatch):
    results = _completions(monkeypatch, "throttle speed 3 --ram", "--ram")
    assert set(results) == {"--rampup", "--rampdown"}


def test_completion_flag_full_listing_on_a_leaf(monkeypatch):
    results = _completions(monkeypatch, "throttle speed 3 --", "--")
    assert {"--rampup", "--rampdown", "--hold", "--help"} == set(results)


def test_completion_flag_after_a_positional_value_still_resolves_leaf(monkeypatch):
    """A positional (the address `3`) mid-line must not be mistaken for an
    unknown subcommand token and abort the tree-walk - the cursor is still
    under `throttle speed`, so its flags must be offered."""
    results = _completions(monkeypatch, "throttle speed 3 --rampup 5 --h", "--h")
    assert results == ["--help", "--hold"]


def test_completion_flag_on_a_group_offers_only_help(monkeypatch):
    results = _completions(monkeypatch, "throttle --", "--")
    assert results == ["--help "]


def test_completion_bare_tab_after_positionals_offers_flags(monkeypatch):
    """After all of a leaf's positionals are already typed (loco + percent
    for `throttle speed`), a bare TAB (empty text, no leading "-" typed
    yet) must still offer that leaf's own flags - not just once the user
    has already typed a literal "-" themselves."""
    results = _completions(monkeypatch, "throttle speed 3 40", "")
    assert {"--rampup", "--rampdown", "--hold"} <= {r.strip() for r in results}


def test_completion_unambiguous_match_gets_trailing_space(monkeypatch):
    """GNU readline doesn't reliably auto-append a space after a sole
    match in this project's target environments, so complete() appends
    one itself - otherwise the next character typed lands glued to the
    tail of the just-completed word (e.g. "throttlespeed")."""
    assert _completions(monkeypatch, "thr", "thr") == ["throttle "]


def test_completion_ambiguous_match_gets_no_trailing_space(monkeypatch):
    """Multiple candidates (a real ambiguity) must not get a trailing
    space on any of them - the user still needs to keep typing/TAB again
    to disambiguate, same as a normal shell."""
    results = _completions(monkeypatch, "throttle speed 3 --ram", "--ram")
    assert results == ["--rampdown", "--rampup"]
    assert all(not r.endswith(" ") for r in results)


def test_completion_nested_group(monkeypatch):
    assert _completions(monkeypatch, "cache cl", "cl") == ["clean "]


def test_completion_unknown_top_level_token_yields_nothing(monkeypatch):
    assert _completions(monkeypatch, "foo bar", "bar") == []


def test_completion_exit_word_offered(monkeypatch):
    assert _completions(monkeypatch, "ex", "ex") == ["exit "]


def test_leaf_names_matches_parser_choices():
    parser = build_parser()
    action = shell._subparsers_action(parser)
    assert shell._leaf_names(parser) == sorted(action.choices.keys())


def test_leaf_names_empty_for_a_leaf_command():
    parser = build_parser()
    throttle_parser = shell._subparsers_action(parser).choices["throttle"]
    speed_parser = shell._subparsers_action(throttle_parser).choices["speed"]
    assert shell._leaf_names(speed_parser) == []


def test_install_completer_noop_without_readline(monkeypatch):
    monkeypatch.setattr(shell, "readline", None)
    shell._install_completer(build_parser())  # must not raise
