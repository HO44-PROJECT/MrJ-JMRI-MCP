# Quick start

Get from a fresh clone to a working voice/chat command against your own JMRI
layout. For background on any step, follow the links — this page only covers
the fastest path.

## 1. Prerequisites

- JMRI's Web Server enabled (*Edit → Preferences → Web Server*, default port
  12080) — note the host/port, you'll need it as `JMRI_URL`.
- Python ≥ 3.10.

## 2. Install

```bash
conda env create -f environment.yml
conda activate jmri-mcp
```

No conda? `pip install -e ./packages/jmri-core -e ./packages/jmri-cli -e ./packages/jmri-mcp`
into any virtualenv works too — see [install.md](install.md) for the full
breakdown (extras, entry points, Python version notes).

## 3. Verify JMRI is reachable

```bash
JMRI_URL=http://<your-jmri-host>:12080 jmri-cli status
```

Expect `JMRI reachable, version X.Y.Z` followed by each power system and its
state. If this fails, fix connectivity/`JMRI_URL` before wiring up any LLM
client — every problem is easier to diagnose from the CLI than from inside a
chat window. See [cli.md](cli.md) for the full command reference.

## 4. Wire it into a client

Pick the one you use:

- **Claude Desktop** — edit `claude_desktop_config.json`, restart the app.
- **Claude Code** — one `claude mcp add` command, no file editing.
- **xiaozhi/Kira** — `jmri-xiaozhi-bridge`, needs the `xiaozhi` extra.

Full config examples for all three: [llm-setup.md](llm-setup.md).

## 5. Try it

Ask your client something that needs a tool call, e.g. "what's the status of
the JMRI power systems?" or "list the locomotives on the roster". If the
client doesn't call any tool, re-check the client-specific "verifying it's
connected" section in [llm-setup.md](llm-setup.md) before assuming the server
itself is broken — `jmri-cli status` already proved that part works.

## Where to go next

- [docs/cli.md](cli.md) — every `jmri-cli` subcommand, useful for testing any
  MCP tool without a chat client in the loop.
- [docs/architecture.md](architecture.md) — module layout and design notes,
  if you're going to read or modify the code.
- [docs/testing.md](testing.md) — running the test suite.
