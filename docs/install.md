# Installation

## Requirements

- Python ≥ 3.10
- A running JMRI Web Server (developed and tested against JMRI 5.4.0), with the
  Web Server enabled (JMRI menu: *Edit → Preferences → Web Server*, default port 12080).

## Tested with

- JMRI **5.4.0**
- DCC++ **5.4.16** (the command station firmware behind the `O`/`Z`/`R` power systems)
- Python **3.11** (the `kira` conda env currently used to run `jmri-mcp` for both
  Claude Desktop and xiaozhi/Kira) — 3.12 is preferred going forward, see below
- [xiaozhi](https://github.com/78/xiaozhi-esp32) (via `src/xiaozhi_wrapper/`, this repo)
- Claude Desktop **1.19367.0** (1a5be1), 2026-07-07

### Python 3.11 vs 3.12

The `kira` conda env historically used to run `jmri-mcp` was created with
Python 3.11 — there's no code reason to stay on 3.11, so this project now has
its **own** dedicated env (`jmri-mcp`, see below) on Python 3.12, independent
of `kira`. `kira` is left untouched, since xiaozhi/Kira depends on it for
other things and upgrading it in place isn't possible with conda (Python
minor versions can't be upgraded in an existing env — only recreated).

This means `kira`'s own copy of `jmri-mcp`/`jmri-cli` (3.11) still exists
side by side with the new `jmri-mcp` env's copy (3.12). If you switch which
env you run from, **update every client config that hardcodes a path**
(Claude Desktop's `claude_desktop_config.json`, Kira's `mcp_config.json` if
it doesn't rely on shell `PATH`) — see [llm-setup.md](llm-setup.md).

## Install into a conda env

The fastest path is `environment.yml`, which creates a dedicated `jmri-mcp`
env on Python 3.12 and installs this package (with the `dev` extra) into it:

```bash
conda env create -f environment.yml
conda activate jmri-mcp
```

Re-run `conda env update -f environment.yml --prune` after pulling changes
that touch dependencies.

### Manual install (any virtualenv or conda env)

From the repo root, with your environment already active:

```bash
pip install -e .
```

This registers the packages (`jmri_mcp`, `xiaozhi_wrapper`) in editable mode and
creates console scripts in the environment's `bin/`:

| Command | Entry point | Purpose |
|---|---|---|
| `jmri-mcp` | `jmri_mcp.server:main` | The MCP stdio server (used by Claude Desktop/Code, or by `jmri-xiaozhi-bridge` for xiaozhi/Kira) |
| `jmri-cli` | `jmri_mcp.cli:main` | Manual command-line tool for testing against JMRI directly, no MCP client needed |
| `jmri-xiaozhi-bridge` | `xiaozhi_wrapper:main` | Generic stdio↔WebSocket bridge exposing `jmri-mcp` to xiaozhi/Kira (needs the `xiaozhi` extra, below) |

For development (running the test suite), install the `dev` extra instead:

```bash
pip install -e ".[dev]"
```

For the xiaozhi/Kira bridge, install the `xiaozhi` extra (see [llm-setup.md](llm-setup.md)):

```bash
pip install -e ".[xiaozhi]"
```

## Verifying the install

```bash
which jmri-mcp jmri-cli
JMRI_URL=http://<your-jmri-host>:12080 jmri-cli status
```

`jmri-cli status` should print `JMRI reachable, version X.Y.Z` followed by each
power system and its state. See [cli.md](cli.md) for the full command reference.

## Conda environments

If you use conda with multiple environments, `pip install -e .` only registers the
entry points in the **currently active** environment. If `jmri-mcp`/`jmri-cli` are
"command not found" after activating an env, it usually means that specific env
never had `pip install -e .` run in it — re-run the install with that env active:

```bash
conda activate <env-name>
pip install -e .
```

Re-run `pip install -e .` again any time `pyproject.toml`'s `[project.scripts]`
section changes (e.g. a new CLI subcommand was added) — pip only regenerates the
entry-point scripts at install time, not automatically.

## Configuration

The only required configuration is the `JMRI_URL` environment variable — see the
[README](../README.md#configuration) for details. Nothing else is hardcoded: systems,
roster, turnouts and sensors are all discovered live from JMRI.

For the opt-in live test suite (which talks to a real JMRI server), see
[testing.md](testing.md) for `config/live.ini`.
