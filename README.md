# MrJ-JMRI-MCP

MCP (Model Context Protocol) server for [JMRI](https://www.jmri.org/) — control your DCC model railroad by voice or chat, through any MCP client: [xiaozhi](https://github.com/78/xiaozhi-esp32) voice assistants, Claude Desktop, Claude Code, etc.

> **Status: early development.** The roadmap lives in the [project board](https://github.com/orgs/HO44-PROJECT/projects) and the [issues](../../issues).

## Goals

- **Fully dynamic** — no hardcoded layout data. Systems (power connections), roster, turnouts and sensors are discovered live from the JMRI server (`GET /json/power`, `{"list": ...}`).
- **LLM-friendly** — compact tool outputs (voice assistants have small contexts), honest `success`/`error` reporting, docstrings that tell the model *when* and *how* to use each tool.
- **One server, every client** — pure stdio MCP server: consumed directly by Claude Desktop/Code, and bridged to xiaozhi via [`mcp_pipe.py`](https://github.com/78/mcp-calculator).

## Architecture (target)

```
src/jmri_mcp/
├── config.py      # env vars: JMRI_URL (e.g. http://10.0.20.20:12080)
├── client.py      # persistent WebSocket client to ws://<jmri>/json/
│                  #   auto-reconnect, ping/pong, throttle registry
├── tools/
│   ├── power.py   # discover systems, get/set power (state 2=ON, 4=OFF)
│   ├── throttle.py# acquire, speed, direction, stop, e-stop, F0–F28
│   ├── roster.py  # compact list/search, name → DCC address resolution
│   └── layout.py  # turnouts, sensors, lights
└── server.py      # FastMCP entry point (stdio; logging → stderr only)
```

## Requirements

- Python ≥ 3.10
- A running JMRI Web Server (tested against JMRI 5.4)

## Configuration

| Variable | Default | Description |
|---|---|---|
| `JMRI_URL` | `http://localhost:12080` | Base URL of the JMRI Web Server |

## Legacy

`legacy/jmri_experimental.py` is the original proof-of-concept (power on/off only). Kept for reference; do not extend it.
