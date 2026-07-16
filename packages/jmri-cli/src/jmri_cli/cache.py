"""`jmri-cli cache info` / `cache clean`: inspect and reset the local
files under ~/.jmri-cli/.

Two independent, purely local caches accumulate there over time (see
state.py and shell.py's module docstrings for what each is for and why
it exists): state.py's throttle_state.json (last-known speed/direction/
functions per DCC address) and shell.py's shell_history (readline
command history for the interactive shell). Neither is a source of
truth for anything JMRI-side - both are safe to delete at any time,
they just regenerate empty and refill from normal use.

This module never touches JMRI (no WebSocket/HTTP calls at all), so
unlike every other command in this CLI, neither function here takes a
`client=` kwarg - both behave identically one-shot or from inside the
shell. `cache` (no leaf) defaults to `cache info`, same as every other
bare group in this CLI defaulting to its own "just show me the state"
leaf.
"""

import argparse

from jmri_core import i18n

from jmri_cli import state
from jmri_cli._common import HISTORY_FILE


async def cache_info(args: argparse.Namespace) -> int:
    """Print the path and on-disk status of each local cache file.

    Purely informational and read-only - never creates, touches, or
    deletes either file. Also the default for bare `jmri-cli cache`
    (no obvious single "clean" action to default to, but "show me
    what's there" is the same safe default every other bare group uses).

    Args:
        args: Parsed CLI arguments (unused - `cache info` takes none).

    Returns:
        0 always.
    """
    for path, label in (
        (state.STATE_FILE, i18n.t("cli.cache_target_state")),
        (HISTORY_FILE, i18n.t("cli.cache_target_history")),
    ):
        exists = i18n.t("cli.cache_exists") if path.exists() else i18n.t("cli.cache_missing")
        print(i18n.t("cli.cache_info_line", label=label, path=path, exists=exists))
    return 0


async def cache_clean(args: argparse.Namespace) -> int:
    """Delete the requested local cache file(s) under ~/.jmri-cli/.

    With neither `--state` nor `--history` given, both are cleared - the
    common case (a full reset). Giving one or both flags scopes the clean
    to just those files, leaving the other(s) untouched.

    Args:
        args: Parsed CLI arguments; `args.state`/`args.history` are the
            `--state`/`--history` flags (see parser.py's `cache clean` leaf).

    Returns:
        0 always; a missing file is not an error (nothing to clean).
    """
    only_state = getattr(args, "state", False)
    only_history = getattr(args, "history", False)
    do_state = only_state or not only_history
    do_history = only_history or not only_state
    cleaned_paths = []

    if do_state and state.STATE_FILE.exists():
        state.STATE_FILE.unlink()
        cleaned_paths.append(str(state.STATE_FILE))

    if do_history and HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
        cleaned_paths.append(str(HISTORY_FILE))

    if cleaned_paths:
        print(i18n.t("cli.cache_cleaned", paths="\n  ".join(cleaned_paths)))
    else:
        print(i18n.t("cli.cache_already_clean"))
    return 0
