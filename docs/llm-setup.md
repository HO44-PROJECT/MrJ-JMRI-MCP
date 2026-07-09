# LLM client setup

`jmri-mcp` is a pure stdio MCP server — it doesn't know or care which client
launches it. This page covers the two clients this project targets.

## Claude Desktop

Tested with Claude Desktop **1.19367.0** (1a5be1), 2026-07-07.

Claude Desktop spawns each configured MCP server as a subprocess itself, using
its own launcher (not your shell), so it does **not** inherit your shell `PATH`.
The `command` must be an absolute path to the `jmri-mcp` script inside the
environment where you ran `pip install -e .` (see [install.md](install.md)).

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add
an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "jmri": {
      "command": "/absolute/path/to/your/env/bin/jmri-mcp",
      "env": {
        "JMRI_URL": "http://10.0.20.20:12080"
      }
    }
  }
}
```

Find the absolute path with `which jmri-mcp` after activating the right
environment. Restart Claude Desktop (**Cmd+Q**, not just closing the window —
closing the window leaves the app and its subprocess running) for config
changes to take effect.

### Verifying it's connected

Ask Claude something that needs a tool call, e.g. "what's the status of the
JMRI power systems?". If it says the JMRI tools aren't available, the
subprocess likely isn't running — check:

```bash
ps aux | grep jmri-mcp
tail -f ~/Library/Logs/Claude/mcp-server-jmri.log
```

A healthy startup ends with `Server started and connected successfully`
followed by successful `tools/list` request/response pairs, and no
`Shutting down` line afterwards. If the process is simply gone with no error,
restart Claude Desktop (Cmd+Q, relaunch) — this has been observed to happen
without warning even when the server code itself is fine.

## Claude Code

Claude Code (this CLI) can also be configured to use the server as an MCP tool
provider — same `jmri-mcp` command and `JMRI_URL` env var, wired through
Claude Code's own MCP configuration (see `claude mcp add` / project-level
`.mcp.json`). Not yet formally documented here — see issue #19.

## xiaozhi / Kira

This repo has **no xiaozhi-specific code** — xiaozhi/Kira connectivity is a
bridge that lives entirely in the separate `kira` project (`~/dev/kira`),
via its `mcp_pipe.py`, which speaks stdio to `jmri-mcp` on one side and
`MCP_ENDPOINT` (a WebSocket) on the other.

On the kira side:

`mcp/mcp_config.json`:

```json
{
  "mcpServers": {
    "jmri": {
      "command": "jmri-mcp",
      "env": { "JMRI_URL": "http://10.0.20.20:12080" }
    }
  }
}
```

Unlike Claude Desktop, `mcp_pipe.py` is launched from your own shell, so it
**does** inherit your shell `PATH` — a bare `"jmri-mcp"` works as long as the
right conda env is active when you launch it.

`mcp/launch.sh` should launch `mcp_pipe.py` in config mode (no server name
argument), which reads `mcp_config.json` and starts every enabled server:

```bash
python mcp_pipe.py
```

A successful run logs a WebSocket connection to xiaozhi, `jmri-mcp` starting
up, and an incoming `ListToolsRequest`. Tested end-to-end against xiaozhi this way.
