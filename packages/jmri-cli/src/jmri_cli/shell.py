"""Interactive shell launched by bare `jmri-cli` (no arguments at all).

Owns a single long-lived JmriWsClient for the whole session, so a nonzero
speed genuinely keeps a locomotive moving between commands — unlike
one-shot `jmri-cli throttle ...` invocations, which release every throttle
the instant their own connection closes (see throttle.py's module
docstring for the full explanation and the `client=` kwarg pattern every
WS-based throttle_* function supports for exactly this reason).

Reuses build_parser() and the existing command functions rather than
duplicating argparse or dispatch logic: each typed line is split with
shlex, parsed with the same parser as one-shot mode, and its `func` is
called with this shell's shared client if that function accepts a
`client` keyword (checked via inspect.signature, which understands
functools.partial natively — no manual unwrapping needed for the
forward/reverse leaves).

`throttle sniff` is rejected here: it needs its own connection and its own
indefinite Ctrl-C loop, which would otherwise block this shell's own
input() loop. It still works fine as a one-shot command in a second
terminal.

`help`/`-h`/`--help` typed bare at the prompt print the same front page as
`jmri-cli -h` (banner + command list). This has to be handled explicitly
before parsing: the shell has no top-level positional to dispatch a bare
word on the way one-shot mode's argparse tree does, so without this,
argparse would reject "help" as an invalid choice for the {power,status,...}
subparsers instead of treating it as a request for help. A bare "help"
appearing anywhere else in a typed line (e.g. "throttle help", "throttle
speed help") is rewritten to "-h" before parsing for the same reason -
argparse itself only recognizes "-h"/"--help", never the word "help", so
without this rewrite a mid-line "help" hits the exact same "invalid choice"
error one level down instead of showing that subcommand's help text.

Up/down arrow command history is provided by the stdlib `readline` module:
merely importing it patches input() (used by asyncio.to_thread below) to
support line editing and history navigation, no extra wiring needed for the
arrow keys themselves. History is persisted across sessions to
~/.jmri-cli/shell_history (same directory convention as state.py's
throttle-state cache) so a previous session's commands are still reachable
on the next launch. Import is wrapped in a try/except: readline is in the
stdlib on macOS/Linux but not universally available (notably absent by
default on some Windows Python builds) - falling back to plain input()
without history there is preferable to crashing the whole CLI.

TAB completion is wired the same way (_install_completer, guarded by the
same `readline is None` check): the completer walks build_parser()'s own
argparse subparser tree (_leaf_names/_subparsers_action) rather than a
hand-maintained word list, so it can never drift out of sync with the
real command set. It re-parses the in-progress line with shlex on every
keypress to find which node of that tree the cursor is under, then
offers that node's own subcommand names - or, once the word being typed
starts with "-", that node's own --flags (_option_strings), e.g.
--rampup/--rampdown/--hold on `throttle speed`. A positional token
already typed (a loco address, a percentage) doesn't advance the
tree-walk past a leaf the way a subcommand name does, so a node's flags
stay completable no matter how many positional values precede them on
the line. Two readline quirks needed explicit handling, found by testing
against a real pseudo-terminal rather than trusting the docs: readline's
default word-delimiter set includes "-", which splits "--rampup" into a
bare word after the dashes and breaks flag matching, so
_install_completer strips "-" from `completer_delims`; and readline does
not reliably auto-append a trailing space after completing to a sole
unambiguous match, so complete() appends one itself whenever exactly one
candidate remains - otherwise the next character typed lands glued to
the tail of the just-completed word (confirmed live: "throttle spe"+TAB
produced "throttle speed3" instead of "throttle speed 3" without this).
"""

import argparse
import asyncio
import contextlib
import inspect
import shlex
import sys

try:
    import readline
except ImportError:
    readline = None

from jmri_core import i18n
from jmri_cli._common import HISTORY_FILE, HISTORY_MAX_LINES, background_holds, cli_throttle_id
from jmri_cli.banner import banner
from jmri_core.constants.cli import SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS
from jmri_cli.parser import build_parser
from jmri_core.jmri_ws import JmriError
from jmri_core.jmri_ws import JmriWsClient
from jmri_core.jmri_ws.ramp import ramp_speed

_PROMPT = "jmri-cli> "
_EXIT_WORDS = {"exit", "quit"}
_HELP_WORDS = {"help", "-h", "--help"}


def _load_history() -> None:
    """Load persisted command history into readline, if available."""
    if readline is None:
        return
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        readline.read_history_file(HISTORY_FILE)


def _save_history() -> None:
    """Persist command history for the next session, if readline is available."""
    if readline is None:
        return
    readline.set_history_length(HISTORY_MAX_LINES)
    with contextlib.suppress(OSError):
        readline.write_history_file(HISTORY_FILE)


_GROUP_NAMES = ["cache", "light", "power", "roster", "sensor", "session-end", "session-start", "signal", "status", "throttle", "turnout"]
_SHORTCUT_NAMES = ["acquire", "release", "speed", "stop", "estop", "forward", "reverse", "engine-start", "engine-stop"]


def _subparsers_action(parser) -> argparse._SubParsersAction | None:
    """The `_SubParsersAction` directly below `parser`, or None if it's a leaf."""
    for action in parser._subparsers._group_actions if parser._subparsers else []:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _leaf_names(parser) -> list[str]:
    """Every subcommand name one level below `parser`, or [] if it has none.

    Walks argparse's own `_SubParsersAction.choices` rather than a
    hand-maintained list, so completion never drifts from parser.py's
    actual command tree (unlike _GROUP_NAMES/_SHORTCUT_NAMES above, which
    only cover the front page and are fine to hand-maintain since they're
    also just decorative help text).
    """
    action = _subparsers_action(parser)
    return sorted(action.choices.keys()) if action else []


def _option_strings(parser) -> list[str]:
    """Every `--flag`/`-f` string this parser node accepts (e.g. `--rampup`,
    `-h`), read from argparse's own optionals group - same rationale as
    _leaf_names: derived from the real tree, not a hand-maintained list, so
    a leaf's flags (throttle speed's --rampup/--rampdown/--hold, etc.) are
    completable without this file needing to know they exist.
    """
    names = []
    for action in parser._optionals._group_actions:
        names.extend(action.option_strings)
    return sorted(names)


def _make_completer(parser):
    """Build a readline completer function closed over `parser`.

    Re-parses the in-progress line (via shlex, same as the real dispatch
    path) on every TAB press to find which subparser node the cursor is
    currently under, then offers that node's own subcommand names and
    `--flags` (or, at the top level, the group/shortcut names plus
    exit/help words) as completions for the word being typed. Unlike
    run_shell()'s own argv rewrite, an unparseable partial line (unbalanced
    quotes, still being typed) falls back to no completions rather than
    erroring — TAB is pressed mid-edit far more often than a line is
    actually ready.
    """
    top_level = {*_leaf_names(parser), *_EXIT_WORDS, *_HELP_WORDS}

    def complete(text: str, state: int) -> str | None:
        buffer = readline.get_line_buffer()[: readline.get_endidx()]
        try:
            tokens = shlex.split(buffer)
        except ValueError:
            tokens = buffer.split()
        # If the buffer doesn't end in whitespace, the last token is the
        # word being completed, not yet a completed command component.
        typed_tokens = tokens if buffer.endswith((" ", "\t")) or not tokens else tokens[:-1]

        node = parser
        for token in typed_tokens:
            # Only positional subcommand tokens walk the tree - a --flag
            # (or a value consumed by one) mid-line doesn't change which
            # node the cursor is under.
            if token.startswith("-"):
                continue
            action = _subparsers_action(node)
            if action is None or token not in action.choices:
                break
            node = action.choices[token]

        if node is parser:
            candidates = top_level
        elif text.startswith("-"):
            candidates = _option_strings(node)
        else:
            # A leaf's subcommand names (usually none - _leaf_names is []
            # for a true leaf) plus its own flags: an empty/non-dash text
            # at a leaf still needs its --flags offered (e.g. "speed 3 40"
            # then bare TAB), not just once the user has already typed "-".
            candidates = {*_leaf_names(node), *_option_strings(node)}
        matches = sorted(name for name in candidates if name.startswith(text))
        # GNU readline doesn't reliably auto-append a trailing space after
        # an unambiguous single-match completion (observed empirically,
        # not just in theory - readline_delims tweaks alone don't fix it),
        # so this appends one explicitly: with exactly one candidate, the
        # word is done and the cursor should land ready for the next
        # token, not glued to the tail of the one just completed.
        if len(matches) == 1:
            return matches[0] + " " if state == 0 else None
        return matches[state] if state < len(matches) else None

    return complete


def _install_completer(parser) -> None:
    """Enable TAB completion at the shell prompt, if readline is available."""
    if readline is None:
        return
    readline.set_completer(_make_completer(parser))
    # readline's default completer_delims treats "-" as a word boundary,
    # which splits "--rampup" into a bare word after the dashes - this is
    # what silently broke both flag matching and the trailing space
    # readline normally appends after an unambiguous completion. Dropping
    # "-" (leaving the rest of the defaults untouched) makes "--rampup" one
    # complete word, matching how it's actually typed and how the rest of
    # this completer already reasons about it via shlex tokens.
    readline.set_completer_delims(readline.get_completer_delims().replace("-", ""))
    readline.parse_and_bind("tab: complete")


def _command_list() -> str:
    """Render the top-level command list, shell-flavored (no `jmri-cli` prefix)."""
    group_help = {name: i18n.t(f"help.group.{name}") for name in _GROUP_NAMES}
    shortcut_help = {name: i18n.t(f"help.shortcut.{name}") for name in _SHORTCUT_NAMES}
    width = max(len(name) for name in {**group_help, **shortcut_help})
    lines = [i18n.t("cli.commands_header")]
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in group_help.items()]
    lines.append("")
    lines.append(i18n.t("cli.shortcuts_header"))
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in shortcut_help.items()]
    lines.append("")
    lines.append(i18n.t("cli.help_hint_shell_group"))
    lines.append(i18n.t("cli.help_hint_shell_example"))
    return "\n".join(lines)


def _is_ws_func(func) -> bool:
    """Whether `func` (possibly a functools.partial) accepts a `client` keyword."""
    try:
        return "client" in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


async def _read_line() -> str | None:
    """Read one line from the prompt, or None on EOF (Ctrl-D)."""
    try:
        return await asyncio.to_thread(input, _PROMPT)
    except EOFError:
        return None


def _moving_addresses(client: JmriWsClient) -> list[int]:
    """DCC addresses this shell's connection holds with a nonzero speed."""
    addresses = []
    for throttle_id, state in client.all_throttle_states().items():
        speed = state.get("speed") or 0.0
        if speed != 0.0:
            addresses.append(state.get("address", throttle_id))
    return sorted(addresses)


async def _cancel_pending_holds() -> None:
    """Cancel every background `--hold` task still pending and wait for
    each to unwind, so nothing keeps driving a throttle after the shell
    has decided to stop it (or is about to close the connection outright).

    Cancelling before `_confirm_exit`'s own ramp-down avoids racing two
    separate speed-changing sequences against the same throttle; awaiting
    with return_exceptions=True absorbs the CancelledError each task
    raises on its way out (see _background_hold in throttle.py, which
    ramps back to 0 on cancellation same as a Ctrl-C mid-hold) without
    letting one task's cancellation stop the others from being awaited.
    """
    pending = [t for t in background_holds.values() if not t.done()]
    if not pending:
        return
    # Give every task at least one scheduler tick before cancelling: a task
    # cancelled before its coroutine ever starts raises CancelledError at
    # the task boundary without running any of its own code, so a hold
    # cancelled the instant it's created would skip execute_speed_change's
    # ramp-to-0-on-cancel step entirely and leave the locomotive at speed.
    await asyncio.sleep(0)
    await asyncio.gather(*pending, return_exceptions=True)


async def _confirm_exit(client: JmriWsClient) -> bool:
    """Prompt for confirmation if anything's moving; ramp it down on yes.

    Returns:
        True if the shell should actually exit now, False to keep going
        (only possible if the user is re-prompted and changes their mind —
        currently every path returns True, "no" just skips the ramp-down).
    """
    await _cancel_pending_holds()

    moving = _moving_addresses(client)
    if not moving:
        return True

    addresses = ", ".join(str(a) for a in moving)
    reply = await asyncio.to_thread(
        input,
        i18n.t("cli.shell_stop_prompt", n=len(moving), addrs=addresses),
    )
    if reply.strip().lower() in ("", "y", "yes"):
        for address in moving:
            throttle_id = cli_throttle_id(address)
            state = client.throttle_state(throttle_id) or {}
            current = state.get("speed") or 0.0
            try:
                await ramp_speed(
                    client, throttle_id, current, 0.0, SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS
                )
            except JmriError as exc:
                print(i18n.t("cli.throttle_error_stopping_address", address=address, message=str(exc)), file=sys.stderr)
    else:
        print(i18n.t("cli.shell_exit_no_stop"), file=sys.stderr)
    return True


async def run_shell() -> None:
    """Run the interactive shell until the user exits.

    Each line is parsed with the same argparse tree as one-shot mode; a
    bad line or `-h`/`--help` triggers argparse's own SystemExit, which is
    caught here so it doesn't kill the session (one-shot mode wants that
    same SystemExit to propagate to the OS exit code — the shell doesn't).

    A `throttle speed`/`forward`/`reverse --hold` runs its ramp/hold/
    auto-stop in the background (see throttle.py's _background_hold) so
    it doesn't block this loop — any such task still pending is cancelled
    and awaited before the connection closes, on every exit path
    (_confirm_exit and this function's own `finally`), so a hold is never
    silently abandoned mid-flight.
    """
    parser = build_parser()
    client = JmriWsClient()
    _load_history()
    _install_completer(parser)
    print(banner())
    print(i18n.t("cli.shell_welcome"))

    try:
        while True:
            try:
                line = await _read_line()
            except KeyboardInterrupt:
                print()
                if await _confirm_exit(client):
                    return
                continue

            if line is None:
                print()
                if await _confirm_exit(client):
                    return
                continue

            stripped = line.strip()
            if not stripped:
                continue
            if stripped in _EXIT_WORDS:
                if await _confirm_exit(client):
                    return
                continue
            if stripped in _HELP_WORDS:
                print(banner())
                print(_command_list())
                continue

            try:
                argv = shlex.split(stripped)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                continue

            # A bare "help" anywhere (e.g. "throttle help", "throttle speed
            # help") means the same thing a user typing "-h" there would get
            # - argparse itself only recognizes "-h"/"--help", so "help" as
            # a subcommand name is otherwise an "invalid choice" error one
            # level down instead of the help text the user actually wants.
            argv = ["-h" if token == "help" else token for token in argv]

            if argv[:2] == ["throttle", "sniff"]:
                print(i18n.t("cli.shell_sniff_needs_own_terminal"), file=sys.stderr)
                continue

            try:
                args = parser.parse_args(argv)
            except SystemExit:
                continue

            kwargs = {"client": client} if _is_ws_func(args.func) else {}
            try:
                await args.func(args, **kwargs)
            except JmriError as exc:
                print(i18n.error(exc), file=sys.stderr)
    finally:
        _save_history()
        await _cancel_pending_holds()
        await client.close()
