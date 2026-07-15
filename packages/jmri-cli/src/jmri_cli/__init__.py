"""jmri-cli: command line tool to exercise the JMRI client and throttle.

Bare `jmri-cli` (no arguments at all) launches the interactive shell (see
shell.py) — a single long-lived connection for indefinite locomotive
control, since a one-shot connection can never hold a nonzero speed (JMRI
releases a throttle the instant its connection closes; see throttle.py's
module docstring). `jmri-cli help`/`-h`/`--help` prints the welcome banner (see banner.py)
plus the command list below and exits — it does NOT launch the shell. Every
leaf subcommand has its own `-h` with a runnable example in its epilog, e.g.
`jmri-cli turnout close -h`; argparse shows the banner-free help text for
those on its own, no code here is involved.

The banner is shown **only** for help output (`jmri-cli`/`-h`/`--help` at
any level) — never for a real command's result, and never merely because a
subcommand was invalid or unrecognized. A one-shot invocation that runs a
real command (e.g. `jmri-cli turnout find OT23`) prints nothing but that
command's own output, so its stdout stays clean for scripting/piping.
Setup (JMRI_URL, etc) is documented in docs/ — not repeated here.

Every command group follows two rules: a bare group defaults to its own
`list`/`status` leaf, and a state value (on/off, forward/reverse, closed/
thrown, ...) is elevated to the subcommand name itself rather than being a
positional argument — see docs/architecture.md's CLI UX section for the
full rationale.

Package layout:
    constants.py  Shared constants (state names, id prefixes, ranges).
    _common.py    Small cross-module helpers (cli_throttle_id).
    _match.py     find_regex/find_glob: shared matching for findr/findg leaves.
    banner.py     Welcome banner shown by -h / --help.
    power.py      power [status|on|off|get|find|findr|findg|default]
                  (jmri_client.py, one-shot HTTP).
    roster.py     roster [list|find|findr|findg|functions] (jmri_client.py).
    state.py      Local ~/.jmri-cli/throttle_state.json cache (last known
                  speed/direction/functions per address).
    throttle.py   throttle [list|find|findr|findg|acquire|release|speed|
                  stop|estop|forward|reverse|on|off|sniff] (jmri_ws.py +
                  state.py). find/findr/findg are read-only and never open
                  a JMRI connection (roster HTTP + local cache only); every
                  other WS-based command accepts an optional `client=`
                  kwarg so it can run one-shot or on the shell's shared
                  connection.
    shell.py      Interactive shell launched by bare `jmri-cli`: one
                  long-lived JmriWsClient, reusing build_parser() and the
                  same throttle.py command functions via their `client=`
                  kwarg instead of duplicating dispatch logic.
    light.py      light [list|find|findr|findg|on|off] (jmri_client.py,
                  one-shot HTTP; layout/scenery lights, not loco headlights).
    turnout.py    turnout [list|find|findr|findg|close|throw] (jmri_client.py,
                  one-shot HTTP).
    sensor.py     sensor [list|find|findr|findg|status] (jmri_client.py,
                  one-shot HTTP; read-only).
    signal.py     signal [list|status|find|findr|findg|set] (jmri_client.py,
                  one-shot HTTP; signalMast only, not signalHead).
    block.py      block [list|find|findr|findg|status] (jmri_client.py,
                  one-shot HTTP; read-only; a named track section with
                  occupancy + linked sensor/value, richer than a plain
                  sensor).
    parser.py     build_parser(): wires all of the above into one CLI, incl.
                  the bare-group-default and verb-elevation patterns.
"""

import asyncio
import sys

from jmri_core import i18n
from jmri_cli import shell as _shell
from jmri_cli.banner import banner
from jmri_cli.parser import build_parser

__all__ = ["build_parser", "main"]

_GROUP_NAMES = ["block", "light", "power", "roster", "sensor", "signal", "status", "throttle", "turnout"]
_SHORTCUT_NAMES = ["speed", "stop", "estop", "forward", "reverse", "engine-start", "engine-stop"]


def _command_list() -> str:
    """Render the "front page" list of top-level commands and their one-liners."""
    group_help = {name: i18n.t(f"help.group.{name}") for name in _GROUP_NAMES}
    shortcut_help = {name: i18n.t(f"help.shortcut.{name}") for name in _SHORTCUT_NAMES}
    width = max(len(name) for name in {**group_help, **shortcut_help})
    lines = [i18n.t("cli.commands_header")]
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in group_help.items()]
    lines.append("")
    lines.append(i18n.t("cli.shortcuts_header"))
    lines += [f"  {name:<{width}}  {help_text}" for name, help_text in shortcut_help.items()]
    lines.append("")
    lines.append(i18n.t("cli.help_hint_group"))
    lines.append(i18n.t("cli.help_hint_example"))
    return "\n".join(lines)


def _print_front_page() -> None:
    print(banner())
    print(_command_list())


def main() -> None:
    """Entry point for the `jmri-cli` console script and `python -m jmri_cli`."""
    if len(sys.argv) == 1:
        asyncio.run(_shell.run_shell())
        sys.exit(0)

    if sys.argv[1] in ("help", "-h", "--help"):
        _print_front_page()
        sys.exit(0)

    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(args.func(args))
    sys.exit(exit_code)
