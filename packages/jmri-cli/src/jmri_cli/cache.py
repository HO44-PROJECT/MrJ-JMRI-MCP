"""`jmri-cli cache info` / `cache clean`: inspect and reset the local
files under ~/.jmri-cli/.

Three independent, purely local caches accumulate there over time (see
state.py, shell.py's, and completion.py's module docstrings for what each
is for and why it exists): state.py's throttle_state.json (last-known
speed/direction/functions per DCC address), shell.py's shell_history
(readline command history for the interactive shell), and completion.py's
completion_cache/ directory (short-TTL name lists for shell tab-completion).
None is a source of truth for anything JMRI-side - all are safe to delete
at any time, they just regenerate empty and refill from normal use.

This module never touches JMRI (no WebSocket/HTTP calls at all), so
unlike every other command in this CLI, neither function here takes a
`client=` kwarg - both behave identically one-shot or from inside the
shell. `cache` (no leaf) defaults to `cache info`, same as every other
bare group in this CLI defaulting to its own "just show me the state"
leaf.
"""

import argparse

from jmri_core import i18n

from jmri_cli import completion, state
from jmri_cli._common import HISTORY_FILE


def _completion_cache_status() -> str:
    """Whether any per-kind completion cache file currently exists on disk."""
    any_exists = completion.CACHE_DIR.is_dir() and any(completion.CACHE_DIR.iterdir())
    return i18n.t("cli.cache_exists") if any_exists else i18n.t("cli.cache_missing")


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
    print(i18n.t(
        "cli.cache_info_line",
        label=i18n.t("cli.cache_target_completion"),
        path=completion.CACHE_DIR,
        exists=_completion_cache_status(),
    ))
    return 0


async def cache_clean(args: argparse.Namespace) -> int:
    """Delete the requested local cache file(s) under ~/.jmri-cli/.

    With none of `--state`/`--history`/`--completions` given, all three are
    cleared - the common case (a full reset). Giving one or more flags
    scopes the clean to just those, leaving the rest untouched.

    Args:
        args: Parsed CLI arguments; `args.state`/`args.history`/
            `args.completions` are the `--state`/`--history`/`--completions`
            flags (see parser.py's `cache clean` leaf).

    Returns:
        0 always; a missing file is not an error (nothing to clean).
    """
    only_state = getattr(args, "state", False)
    only_history = getattr(args, "history", False)
    only_completions = getattr(args, "completions", False)
    any_scoped = only_state or only_history or only_completions
    do_state = only_state or not any_scoped
    do_history = only_history or not any_scoped
    do_completions = only_completions or not any_scoped
    cleaned_paths = []

    if do_state and state.STATE_FILE.exists():
        state.STATE_FILE.unlink()
        cleaned_paths.append(str(state.STATE_FILE))

    if do_history and HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
        cleaned_paths.append(str(HISTORY_FILE))

    if do_completions and completion.CACHE_DIR.is_dir():
        for cache_file in completion.CACHE_DIR.iterdir():
            cache_file.unlink()
            cleaned_paths.append(str(cache_file))

    if cleaned_paths:
        print(i18n.t("cli.cache_cleaned", paths="\n  ".join(cleaned_paths)))
    else:
        print(i18n.t("cli.cache_already_clean"))
    return 0
