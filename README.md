# MrJ-JMRI-MCP

MCP (Model Context Protocol) server for [JMRI](https://www.jmri.org/) — control your DCC model railroad by voice or chat, through any MCP client: [xiaozhi](https://github.com/78/xiaozhi-esp32) voice assistants, Claude Desktop, Claude Code, etc.

> **Status: early development.** The roadmap lives in the [project board](https://github.com/orgs/HO44-PROJECT/projects) and the [issues](../../issues).

## Goals

- **Fully dynamic** — no hardcoded layout data. Systems (power connections), roster, turnouts and sensors are discovered live from the JMRI server (`GET /json/power`, `{"list": ...}`).
- **LLM-friendly** — compact tool outputs (voice assistants have small contexts), honest `success`/`error` reporting, docstrings that tell the model *when* and *how* to use each tool.
- **One server, every client** — pure stdio MCP server: consumed directly by Claude Desktop/Code, and bridged to xiaozhi via `src/xiaozhi_wrapper/` (`jmri-xiaozhi-bridge`), a generic stdio↔WebSocket bridge included in this repo.

## Architecture

Pure stdio MCP server, two JMRI clients under the hood (plain HTTP for
one-shot calls, a persistent WebSocket for throttles) — see
[docs/architecture.md](docs/architecture.md) for the module layout and
design notes.

## Requirements

- Python ≥ 3.10 (developed on 3.12 — see [docs/install.md](docs/install.md#tested-with) for tested versions and `environment.yml`)
- A running JMRI Web Server (tested against JMRI 5.4)

## Documentation

- **[docs/quickstart.md](docs/quickstart.md)** — fastest path from a fresh clone to a working voice/chat command.
- **[docs/architecture.md](docs/architecture.md)** — module layout, the two JMRI clients, WebSocket design notes.
- **[docs/install.md](docs/install.md)** — installing the package, verifying `jmri-mcp`/`jmri-cli`.
- **[docs/cli.md](docs/cli.md)** — `jmri-cli` command reference.
- **[docs/llm-setup.md](docs/llm-setup.md)** — wiring the server into Claude Desktop, Claude Code, xiaozhi/Kira.
- **[docs/testing.md](docs/testing.md)** — the mocked vs. live test suites, hardware-safety config.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `JMRI_URL` | `http://localhost:12080` | Base URL of the JMRI Web Server |

## License

[AGPL-3.0-or-later](LICENSE). Chosen deliberately over a permissive license
(MIT/Apache) so that anyone who modifies this project and offers it as a
network service (not just redistributes the code) must also publish their
modified source — see the [license text](LICENSE) for the exact terms.

### Third-party code

`src/xiaozhi_wrapper/` is adapted from the MCP pipe example in
[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT License,
Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. and Project
Contributors) — see the package docstring
(`src/xiaozhi_wrapper/__init__.py`) for the full notice.
