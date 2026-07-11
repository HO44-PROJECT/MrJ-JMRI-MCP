"""The banner shown by `jmri-cli -h`/`--help`.

Kept as one static string (not folded into argparse's own description
formatting) so it renders identically everywhere it's shown - one
canonical "front page" for the tool instead of several different first
impressions. Note: bare `jmri-cli` (no arguments) does NOT show this -
it launches the interactive shell instead (see shell.py).
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
