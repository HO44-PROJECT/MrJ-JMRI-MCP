"""jmri-cli: command line tool to exercise the JMRI client and throttle.

Bare `jmri-cli` (no arguments at all) launches the interactive shell (see
shell.py) — a single long-lived connection for indefinite locomotive
control, since a one-shot connection can never hold a nonzero speed (JMRI
releases a throttle the instant its connection closes; see throttle.py's
module docstring). `jmri-cli -h`/`--help` instead prints the welcome banner
(see banner.py) plus the command list below and exits, same as before —
it does NOT launch the shell. Every leaf subcommand has its own `-h` with
a runnable example in its epilog, e.g. `jmri-cli turnout closed -h`.
Setup (JMRI_URL, etc) is documented in docs/ — not repeated here.

Every command group follows two rules: a bare group defaults to its own
`list`/`status` leaf, and a state value (on/off, forward/reverse, closed/
thrown, ...) is elevated to the subcommand name itself rather than being a
positional argument — see docs/architecture.md's CLI UX section for the
full rationale.

Package layout:
    constants.py  Shared constants (state names, id prefixes, ranges).
    _common.py    Small cross-module helpers (cli_throttle_id).
    _doc.py       Short per-group help text (GROUP_HELP), shared with parser.py.
    banner.py     Welcome banner shown by -h / --help.
    power.py      power [status|on|off|get|default] (jmri_client.py, one-shot HTTP).
    roster.py     roster [list|find|functions] (jmri_client.py).
    state.py      Local ~/.jmri-cli/throttle_state.json cache (last known
                  speed/direction/functions per address).
    throttle.py   throttle [list|acquire|release|speed|stop|estop|forward|
                  reverse|on|off|sniff] (jmri_ws.py + state.py). Every
                  WS-based command accepts an optional `client=` kwarg so
                  it can run one-shot or on the shell's shared connection.
    shell.py      Interactive shell launched by bare `jmri-cli`: one
                  long-lived JmriWsClient, reusing build_parser() and the
                  same throttle.py command functions via their `client=`
                  kwarg instead of duplicating dispatch logic.
    light.py      light [list|on|off] (jmri_client.py, one-shot HTTP;
                  layout/scenery lights, not loco headlights).
    turnout.py    turnout [list|closed|thrown] (jmri_client.py, one-shot HTTP).
    sensor.py     sensor list/status (jmri_client.py, one-shot HTTP; read-only).
    signal.py     signal list/status/set (jmri_client.py, one-shot HTTP;
                  signalMast only, not signalHead).
    parser.py     build_parser(): wires all of the above into one CLI, incl.
                  the bare-group-default and verb-elevation patterns.
"""

import asyncio
import sys

from jmri_mcp.cli import shell as _shell
from jmri_mcp.cli._doc import GROUP_HELP
from jmri_mcp.cli.banner import banner
from jmri_mcp.cli.parser import build_parser

__all__ = ["build_parser", "main"]


def _command_list() -> str:
    """Render the "front page" list of top-level commands and their one-liners."""
    width = max(len(name) for name in GROUP_HELP)
    lines = ["commands:"]
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in GROUP_HELP.items()]
    lines.append("")
    lines.append("Run `jmri-cli <command> -h` for its subcommands, or")
    lines.append("`jmri-cli <command> <subcommand> -h` for a runnable example.")
    return "\n".join(lines)


def _print_front_page() -> None:
    print(banner())
    print(_command_list())


def main() -> None:
    """Entry point for the `jmri-cli` console script and `python -m jmri_mcp.cli`."""
    if len(sys.argv) == 1:
        asyncio.run(_shell.run_shell())
        sys.exit(0)

    if sys.argv[1] in ("-h", "--help"):
        _print_front_page()
        sys.exit(0)

    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)
