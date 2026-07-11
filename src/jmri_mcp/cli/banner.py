"""The banner shown by `jmri-cli help`/`-h`/`--help` (at any command level) —
and nowhere else. A real command's output (or an argparse error for an
invalid/unrecognized command) is never preceded by it, so one-shot
invocations stay script/pipe-friendly.

Kept as one static string (not folded into argparse's own description
formatting) so it renders identically everywhere it's shown - one
canonical "front page" for the tool instead of several different first
impressions.
"""

from importlib.metadata import PackageNotFoundError, version

REPO_URL = "https://github.com/HO44-PROJECT/MrJ-JMRI-MCP"


def _version() -> str:
    try:
        return version("jmri-mcp")
    except PackageNotFoundError:
        return "dev"


def banner() -> str:
    """Build the CLI's welcome banner, with the installed package version."""
    return (
        f"jmri-cli v{_version()} ({REPO_URL})\n"
        "Control power, locomotives, lights, turnouts and signals on your JMRI layout.\n"
        "Also reports roster and sensor info.\n"
    )
