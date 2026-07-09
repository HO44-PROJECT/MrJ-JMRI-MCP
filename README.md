# MrJ-JMRI-MCP

MCP (Model Context Protocol) server for [JMRI](https://www.jmri.org/) — control your DCC model railroad by voice or chat, through any MCP client: [xiaozhi](https://github.com/78/xiaozhi-esp32) voice assistants, Claude Desktop, Claude Code, etc.

> **Status: early development.** The roadmap lives in the [project board](https://github.com/orgs/HO44-PROJECT/projects) and the [issues](../../issues).

## Goals

- **Fully dynamic** — no hardcoded layout data. Systems (power connections), roster, turnouts and sensors are discovered live from the JMRI server (`GET /json/power`, `{"list": ...}`).
- **LLM-friendly** — compact tool outputs (voice assistants have small contexts), honest `success`/`error` reporting, docstrings that tell the model *when* and *how* to use each tool.
- **One server, every client** — pure stdio MCP server: consumed directly by Claude Desktop/Code, and bridged to xiaozhi via [`mcp_pipe.py`](https://github.com/78/mcp-calculator).

## Architecture

```
src/jmri_mcp/
├── config.py       # env vars: JMRI_URL (e.g. http://10.0.20.20:12080)
├── jmri_client.py  # async HTTP client for JMRI's JSON API (power, version, ...)
├── tools.py        # MCP tools exposed to the LLM (list_systems, get_power, set_power, system_status)
├── cli.py          # jmri-cli: manual command-line tool, no MCP client needed
└── server.py       # FastMCP entry point (stdio; logging → stderr only)
```

More tools (throttle, roster, turnouts, sensors, lights) will land here as
their milestones are implemented — see the [project board](https://github.com/orgs/HO44-PROJECT/projects/3).

## Requirements

- Python ≥ 3.10 (developed on 3.12 — see [docs/install.md](docs/install.md#tested-with) for tested versions and `environment.yml`)
- A running JMRI Web Server (tested against JMRI 5.4)

## Documentation

- **[docs/install.md](docs/install.md)** — installing the package, verifying `jmri-mcp`/`jmri-cli`.
- **[docs/cli.md](docs/cli.md)** — `jmri-cli` command reference.
- **[docs/llm-setup.md](docs/llm-setup.md)** — wiring the server into Claude Desktop, Claude Code, xiaozhi/Kira.
- **[docs/testing.md](docs/testing.md)** — the mocked vs. live test suites, hardware-safety config.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `JMRI_URL` | `http://localhost:12080` | Base URL of the JMRI Web Server |

## Legacy

`legacy/jmri_experimental.py` is the original proof-of-concept (power on/off only). Kept for reference; do not extend it.
