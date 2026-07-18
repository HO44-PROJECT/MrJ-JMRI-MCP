# Installation guide

This project ships three things you can install independently, in any
combination:

- **`jmri-cli`** — a manual command-line tool for driving JMRI directly from
  a terminal. No AI client involved.
- **A `.mcpb` bundle for Claude Desktop** — lets Claude Desktop control JMRI
  through natural-language chat, installed with a double-click.
- **`jmri-xiaozhi-bridge`** — connects JMRI control to **Kira**, a
  voice-assistant device, so you can drive the layout by talking to it.

All three sit on top of the same `jmri-mcp` MCP server; they're just
different front doors to it. Pick the section(s) below that match what you
actually want to install — you don't need all three.

## What is Kira, and why is there a "bridge"?

[Kira](https://makerworld.com/en/models/2836210-kira-ai-assistant#profileId-3161104) is a
physical voice-assistant device built on the open-source
[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) firmware/cloud project.

<img src="https://makerworld.bblmw.com/makerworld/model/DSM00000002836210/design/3eb9b54c97b26f38.png?x-oss-process=image/format,webp" width="360" alt="Kira AI Assistant device">

You talk to it out loud; it talks back. Out of the box it doesn't know
anything about JMRI or model trains — the xiaozhi cloud service dispatches
its tool calls over a WebSocket connection, and this project's `jmri-mcp`
server only speaks stdio (the standard MCP transport used by Claude Desktop,
Claude Code, etc.), not WebSocket.

`jmri-xiaozhi-bridge` closes that gap: it's a small always-on process that
opens a WebSocket connection to xiaozhi's cloud on one side, launches
`jmri-mcp` as a subprocess and talks stdio to it on the other, and shuttles
MCP messages between the two. It has no JMRI-specific code of its own — it
would bridge any stdio MCP server to xiaozhi. The bridge is the piece you
need to run *somewhere* (your own machine, or a small always-on server like
a Portainer host) for Kira to be able to control your trains; Claude
Desktop/Code don't need it at all, since they speak stdio natively.

See [docs/llm-setup-xiaozhi.md](docs/llm-setup-xiaozhi.md) for the full
technical detail and [docs/resources.md](docs/resources.md) for links.
`~/dev/kira` (if you have it locally) is a separate, unrelated proof-of-concept
project — not part of this repo, not required for any of the installs below.

## Requirements (all modes)

- A running JMRI Web Server (tested against JMRI 5.4.0), with the Web Server
  enabled (JMRI menu: *Edit → Preferences → Web Server*, default port
  12080), reachable from wherever you install the pieces below.
- Python ≥ 3.10 for anything installed via `pip`/`conda` (the CLI, the
  bridge run locally). Not needed for the `.mcpb` install — Claude Desktop
  manages its own Python.

---

## 1. `jmri-cli` (manual command-line tool)

Use this if you want to drive JMRI from a terminal, or test your JMRI
connection without involving any AI client.

### 1a. In a conda environment

```bash
conda create -n jmri-cli python=3.12
conda activate jmri-cli
pip install jmri-cli
```

### 1b. In a venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install jmri-cli
```

### Verify (either mode)

```bash
export JMRI_URL=http://<your-jmri-host>:12080
jmri-cli status
```

Should print `JMRI reachable, version X.Y.Z` followed by each power system
and its state. See [docs/cli.md](docs/cli.md) for the full command
reference, and [docs/install.md](docs/install.md) if you're installing from
a cloned copy of this repo instead of from PyPI (e.g. to work on the code).

---

## 2. `.mcpb` bundle in Claude Desktop

Use this if you want to talk to Claude Desktop in natural language ("what's
the status of the layout?", "move loco 3 forward at 40%") and have it
control JMRI directly. No terminal needed after the install step.

1. Download the latest `jmri-mcp-<version>.mcpb` file from this repo's
   [Releases](../../releases) page.
2. Double-click it (or drag it into Claude Desktop). Claude Desktop opens an
   install prompt showing what the bundle requests.
3. Fill in the requested value — `JMRI_URL` (e.g.
   `http://<your-jmri-host>:12080`) — when prompted.
4. Confirm the install. Claude Desktop manages the Python environment and
   `jmri-mcp` install for you; there's no separate `pip install` step.

### Verify

Restart Claude Desktop if it was already running (**Cmd+Q**, not just
closing the window), then ask it something that needs a tool call, e.g.
"what's the status of the JMRI power systems?". See
[docs/llm-setup-claude.md](docs/llm-setup-claude.md) for troubleshooting
(log locations, subprocess checks) and for wiring Claude Code instead, which
doesn't use `.mcpb` and is configured via `claude mcp add`.

---

## 3. `jmri-xiaozhi-bridge` (Kira / xiaozhi voice control)

Use this if you want to control JMRI by talking to a Kira device. You need
an `MCP_ENDPOINT` (the xiaozhi WebSocket URL your Kira device/account uses)
in addition to `JMRI_URL`.

The bridge is one always-on process. Run it wherever is convenient for
you — your own machine while you're actively using Kira, or a small
always-on host via Docker/Portainer so it's up whenever Kira is.

### 3a. Locally, in a conda environment

```bash
conda create -n jmri-bridge python=3.12
conda activate jmri-bridge
pip install "jmri-mcp[xiaozhi]"

export MCP_ENDPOINT=<your xiaozhi ws endpoint>
export JMRI_URL=http://<your-jmri-host>:12080
jmri-xiaozhi-bridge
```

### 3b. Locally, in a venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "jmri-mcp[xiaozhi]"

export MCP_ENDPOINT=<your xiaozhi ws endpoint>
export JMRI_URL=http://<your-jmri-host>:12080
jmri-xiaozhi-bridge
```

Either way, the bridge keeps running in that terminal (or under whatever
process supervisor you use, e.g. `systemd`, `tmux`, `pm2`) — closing the
terminal stops it, and Kira loses JMRI control until it's started again.
See [docs/llm-setup-xiaozhi.md](docs/llm-setup-xiaozhi.md) for how
`MCP_ENDPOINT`/`JMRI_URL` and JMRI's own config get picked up.

### 3c. In Portainer (Docker, always-on)

This is the easiest way to keep the bridge running continuously without
babysitting a terminal. It uses the stock `python:3.12-slim` image and
installs `jmri-mcp` at container start — no custom image to build or
maintain.

1. In Portainer, go to **Stacks → Add stack**.
2. Paste this into the Web editor:

   ```yaml
   services:
     jmri-xiaozhi-bridge:
       image: python:3.12-slim
       restart: unless-stopped
       command: sh -c "pip install --no-cache-dir jmri-mcp[xiaozhi] && jmri-xiaozhi-bridge"
       environment:
         MCP_ENDPOINT: ${MCP_ENDPOINT}
         JMRI_URL: ${JMRI_URL:-http://localhost:12080}
   ```

3. In the **Environment variables** section of the Stack editor, add:
   - `MCP_ENDPOINT` — your xiaozhi WebSocket endpoint
   - `JMRI_URL` — your JMRI Web Server URL, reachable from the Portainer
     host (`localhost` will usually be wrong here unless JMRI runs on the
     same host as Portainer — use the JMRI machine's actual LAN address)
4. Deploy the stack. Portainer pulls `python:3.12-slim`, installs
   `jmri-mcp[xiaozhi]`, and starts the bridge; `restart: unless-stopped`
   keeps it running across container/host restarts.

Check the container's logs in Portainer to verify: a successful start logs
a WebSocket connection to xiaozhi, `jmri-mcp` starting up, and an incoming
tool-list request.

---

## Combining installs

Nothing above conflicts with anything else — e.g. you can have `jmri-cli`
in a local conda env for manual testing, the `.mcpb` in Claude Desktop for
chat control, and the bridge running in Portainer for Kira, all pointed at
the same JMRI server, at the same time. Each talks to JMRI independently;
JMRI itself has no concept of "which client" beyond the usual multi-client
behavior described in [docs/architecture.md](docs/architecture.md).

## Try it

Once you've installed at least one front door above, confirm it actually
talks to your layout:

- **`jmri-cli`**: `jmri-cli status` should print `JMRI reachable, version
  X.Y.Z` followed by each power system and its state. If this fails, fix
  connectivity/`JMRI_URL` before wiring up any LLM client — every problem
  is easier to diagnose from the CLI than from inside a chat window.
- **Claude Desktop/Code**: ask something that needs a tool call, e.g.
  "what's the status of the JMRI power systems?" or "list the locomotives
  on the roster." If it doesn't call any tool, see the "verifying it's
  connected" section in [docs/llm-setup-claude.md](docs/llm-setup-claude.md).
- **Kira**: ask it the same kind of question out loud. If nothing happens,
  check the bridge's logs (terminal output locally, or the container logs
  in Portainer) — see [docs/llm-setup-xiaozhi.md](docs/llm-setup-xiaozhi.md).

## Developing on this repo instead

Everything above installs from PyPI. If you're cloning this repo to modify
the code itself, see [docs/install.md](docs/install.md) instead — it covers
editable installs of all three packages (`jmri-core`, `jmri-cli`,
`jmri-mcp`) from the working tree.

## Where to go next

- [docs/cli.md](docs/cli.md) — every `jmri-cli` subcommand.
- [docs/architecture.md](docs/architecture.md) — module layout and design
  notes, if you're going to read or modify the code.
- [docs/testing.md](docs/testing.md) — running the test suite.
