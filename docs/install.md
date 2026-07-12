# Installation

## Requirements

- Python ≥ 3.10
- A running JMRI Web Server (tested against JMRI 5.4.0), with the Web Server
  enabled (JMRI menu: *Edit → Preferences → Web Server*, default port 12080).

## Install into a conda env

The fastest path is `environment.yml`, which creates a dedicated `jmri-mcp-cli`
env and installs all three packages into it:

```bash
conda env create -f environment.yml
conda activate jmri-mcp-cli
```

Re-run `conda env update -f environment.yml --prune` after pulling changes
that touch dependencies.

### Manual install (any virtualenv or conda env)

This repo is a monorepo of three packages under `packages/`:

```
jmri-core   (shared HTTP/WebSocket client, config, i18n)
    ^               ^
    |               |
jmri-cli        jmri-mcp
(manual CLI)    (MCP stdio server + xiaozhi_wrapper bridge)
```

Install all three in one command:

```bash
pip install -e ./packages/jmri-core -e ./packages/jmri-cli -e ./packages/jmri-mcp
```

This creates console scripts in the environment's `bin/`:

| Command | Package | Purpose |
|---|---|---|
| `jmri-mcp` | `jmri-mcp` | The MCP stdio server (used by Claude Desktop/Code, or by `jmri-xiaozhi-bridge` for xiaozhi/Kira) |
| `jmri-cli` | `jmri-cli` | Manual command-line tool for testing against JMRI directly, no MCP client needed |
| `jmri-xiaozhi-bridge` | `jmri-mcp` | Generic stdio↔WebSocket bridge exposing `jmri-mcp` to xiaozhi/Kira (needs the `xiaozhi` extra, below) |

For the xiaozhi/Kira bridge, install the `xiaozhi` extra of `jmri-mcp` (see [llm-setup-xiaozhi.md](llm-setup-xiaozhi.md)):

```bash
pip install -e ./packages/jmri-core -e "./packages/jmri-mcp[xiaozhi]"
```

## Verifying the install

```bash
which jmri-mcp jmri-cli
JMRI_URL=http://<your-jmri-host>:12080 jmri-cli status
```

`jmri-cli status` should print `JMRI reachable, version X.Y.Z` followed by each
power system and its state. See [cli.md](cli.md) for the full command reference.

## Conda environments

If you use conda with multiple environments, `pip install -e ./packages/<pkg>` only
registers the entry points in the **currently active** environment. If `jmri-mcp`/
`jmri-cli` are "command not found" after activating an env, it usually means that
specific env never had the install run in it — re-run with that env active:

```bash
conda activate <env-name>
pip install -e ./packages/jmri-core -e ./packages/jmri-cli -e ./packages/jmri-mcp
```

Re-run the install again any time a package's `pyproject.toml` changes (e.g. a new
CLI subcommand or a new dependency) — otherwise you'll see `ModuleNotFoundError`
for the new dependency after `git pull`.

If you use `environment.yml` instead, `conda env update -f environment.yml --prune`
covers this the same way.

## Configuration

The only required configuration is the `JMRI_URL` environment variable — see the
[README](../README.md#configuration) for details. Nothing else is hardcoded: systems,
roster, turnouts and sensors are all discovered live from JMRI.
