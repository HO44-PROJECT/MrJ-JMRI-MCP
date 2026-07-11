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
"""

import asyncio
import contextlib
import inspect
import shlex
import sys
from pathlib import Path

try:
    import readline
except ImportError:
    readline = None

from jmri_mcp.cli._common import cli_throttle_id
from jmri_mcp.cli._doc import GROUP_HELP
from jmri_mcp.cli.banner import banner
from jmri_mcp.cli.constants import SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS
from jmri_mcp.cli.parser import build_parser
from jmri_mcp.jmri_ws import JmriError as JmriWsError
from jmri_mcp.jmri_ws import JmriWsClient

_PROMPT = "jmri-cli> "
_EXIT_WORDS = {"exit", "quit"}
_HELP_WORDS = {"help", "-h", "--help"}
_HISTORY_FILE = Path.home() / ".jmri-cli" / "shell_history"
_HISTORY_MAX_LINES = 1000


def _load_history() -> None:
    """Load persisted command history into readline, if available."""
    if readline is None:
        return
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        readline.read_history_file(_HISTORY_FILE)


def _save_history() -> None:
    """Persist command history for the next session, if readline is available."""
    if readline is None:
        return
    readline.set_history_length(_HISTORY_MAX_LINES)
    with contextlib.suppress(OSError):
        readline.write_history_file(_HISTORY_FILE)


def _command_list() -> str:
    """Render the top-level command list, shell-flavored (no `jmri-cli` prefix)."""
    width = max(len(name) for name in GROUP_HELP)
    lines = ["commands:"]
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in GROUP_HELP.items()]
    lines.append("")
    lines.append("Run `<command> -h` for its subcommands, or")
    lines.append("`<command> <subcommand> -h` for a runnable example.")
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


async def _confirm_exit(client: JmriWsClient) -> bool:
    """Prompt for confirmation if anything's moving; ramp it down on yes.

    Returns:
        True if the shell should actually exit now, False to keep going
        (only possible if the user is re-prompted and changes their mind —
        currently every path returns True, "no" just skips the ramp-down).
    """
    moving = _moving_addresses(client)
    if not moving:
        return True

    addresses = ", ".join(str(a) for a in moving)
    reply = await asyncio.to_thread(
        input,
        f"{len(moving)} loco(s) in motion (address(es) {addresses}). "
        "Stop them all before exiting? [Y/n] ",
    )
    if reply.strip().lower() in ("", "y", "yes"):
        from jmri_mcp.cli.throttle import _ramp_speed  # local import: avoid a cycle at module load

        for address in moving:
            throttle_id = cli_throttle_id(address)
            state = client.throttle_state(throttle_id) or {}
            current = state.get("speed") or 0.0
            try:
                await _ramp_speed(
                    client, throttle_id, current, 0.0, SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS
                )
            except JmriWsError as exc:
                print(f"Error stopping address={address}: {exc}", file=sys.stderr)
    else:
        print("Exiting without stopping — locomotives left in their current state.", file=sys.stderr)
    return True


async def run_shell() -> None:
    """Run the interactive shell until the user exits.

    Each line is parsed with the same argparse tree as one-shot mode; a
    bad line or `-h`/`--help` triggers argparse's own SystemExit, which is
    caught here so it doesn't kill the session (one-shot mode wants that
    same SystemExit to propagate to the OS exit code — the shell doesn't).
    """
    parser = build_parser()
    client = JmriWsClient()
    _load_history()
    print("jmri-cli interactive shell. Type `exit`, `quit`, or Ctrl-D to leave.")

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
                print(
                    "Error: `throttle sniff` needs its own connection and its own "
                    "indefinite Ctrl-C loop — run it in a separate terminal instead: "
                    "`jmri-cli throttle sniff ...`",
                    file=sys.stderr,
                )
                continue

            try:
                args = parser.parse_args(argv)
            except SystemExit:
                continue

            kwargs = {"client": client} if _is_ws_func(args.func) else {}
            try:
                await args.func(args, **kwargs)
            except JmriWsError as exc:
                print(f"Error: {exc}", file=sys.stderr)
    finally:
        _save_history()
        await client.close()
