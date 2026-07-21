# Codex (ChatGPT) setup

`jmri-mcp` is a pure stdio MCP server — it doesn't know or care which client
launches it. This page covers [OpenAI Codex](https://openai.com/codex/), the
CLI/IDE agent bundled with a ChatGPT **Plus** subscription (or higher).

`jmri_mcpctl.py` (in this package's `codex/` directory) automates registering,
starting, stopping, and uninstalling the server in Codex's own MCP config —
so you don't hand-edit Codex's config file the way [Claude
setup](llm-setup-claude.md) hand-edits `claude_desktop_config.json`.

Two ways to get it:

- **From a clone of this repo**: use `packages/jmri-mcp/codex/jmri_mcpctl.py`
  directly, as below — it defaults to registering this checkout.
- **Standalone, no clone needed**: download `jmri-mcp-<version>.codex.zip`
  from a [GitHub Release](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/releases)
  and unzip it anywhere. It bundles `jmri_mcpctl.py`, the `jmri_mcp` source,
  and a self-contained `pyproject.toml` (`jmri-core`/`mcp` resolved from
  PyPI) — `install` works immediately from inside the unzipped folder, same
  commands as below.

## Requirements

- A ChatGPT **Plus** (or higher) subscription — Codex's MCP support isn't
  available on the free tier.
- The Codex CLI, installed via either the ChatGPT desktop app or the
  standalone `Codex.app` (`jmri-mcpctl` looks for `codex` on `PATH` first,
  then falls back to each app's bundled binary).
- [`uv`](https://docs.astral.sh/uv/) (`brew install uv`), used to create the
  server's virtual environment and run `jmri-mcp`.

## Configure the current terminal

```bash
export JMRI_URL="http://10.0.20.20:12080"
export EXHIBITION_PASSWORD="your-password"
export EXHIBITION_ALLOWED_ADDRESSES=""
export EXHIBITION_START_ON="false"
```

Only `JMRI_URL` is required — the rest default to exhibition mode being off
(see [Exhibition mode](exhibition.md)).

## Commands

```bash
python3 packages/jmri-mcp/codex/jmri_mcpctl.py install
python3 packages/jmri-mcp/codex/jmri_mcpctl.py start
python3 packages/jmri-mcp/codex/jmri_mcpctl.py stop
python3 packages/jmri-mcp/codex/jmri_mcpctl.py restart
python3 packages/jmri-mcp/codex/jmri_mcpctl.py status
python3 packages/jmri-mcp/codex/jmri_mcpctl.py uninstall
python3 packages/jmri-mcp/codex/jmri_mcpctl.py uninstall --purge
```

- `install` — `uv sync`s the project's dependencies, then registers the
  server with Codex using the current environment variables.
- `start` — (re-)registers the server with Codex using the current
  environment variables, without reinstalling dependencies.
- `stop` — removes the MCP entry from Codex.
- `restart` — `stop` then `start`.
- `status` — shows whether the entry is registered, and probes `JMRI_URL`
  for reachability.
- `uninstall` — removes the Codex registration and reports each step.
- `uninstall --purge` — also removes the dedicated `.venv-jmri-mcp-codex`
  virtual environment, while preserving the source code and JMRI itself.

Open a new Codex task after `start`, `stop`, `restart`, or `uninstall` — Codex
only picks up MCP registration changes for tasks started afterward.

## How it finds the project

`jmri_mcpctl.py` defaults `SOURCE_DIR` to the nearest ancestor directory
containing a `pyproject.toml`, starting from the script's own location — the
unzip directory itself for the standalone `.codex.zip`, or this repo's root
for a clone. It then runs `uv run --project "$SOURCE_DIR" jmri-mcp` under a
**dedicated virtual environment named `.venv-jmri-mcp-codex`** (not `uv`'s
default `.venv`), created inside `SOURCE_DIR`. Override the source directory
with `JMRI_MCP_SOURCE_DIR` if that auto-detection picks the wrong directory:

```bash
export JMRI_MCP_SOURCE_DIR="/absolute/path/to/MrJ-JMRI-MCP"
```

The dedicated venv name matters if you're working from a repo clone: this
repo's own dev `.venv` (used by `uv sync --all-packages`, Claude Desktop,
Kira/xiaozhi) is a different, shared environment — `.venv-jmri-mcp-codex`
keeps Codex's environment isolated from it, so `uninstall --purge` can never
remove the shared one by accident.

Other optional variables: `JMRI_MCP_NAME` (the Codex MCP entry name,
default `jmri`).

## Notes

Codex stores the values passed by `start`/`install` in its own local MCP
configuration — `EXHIBITION_PASSWORD` is no longer kept in a separate `.env`
file, but it is still stored locally in Codex's config.
