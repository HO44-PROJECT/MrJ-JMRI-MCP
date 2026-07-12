# LLM client setup

`jmri-mcp` is a pure stdio MCP server — it doesn't know or care which client
launches it. This page covers the two clients this project targets.

## Claude Desktop

Tested with Claude Desktop **1.19367.0** (1a5be1), 2026-07-07.

Claude Desktop spawns each configured MCP server as a subprocess itself, using
its own launcher (not your shell), so it does **not** inherit your shell `PATH`.
The `command` must be an absolute path to the `jmri-mcp` script inside the
environment where you installed the `jmri-mcp` package (see [install.md](install.md)).

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add
an entry under `mcpServers`:

```json
{
  "mcpServers": {
    "jmri": {
      "command": "/absolute/path/to/your/env/bin/jmri-mcp",
      "env": {
        "JMRI_URL": "http://localhost:12080"
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
provider — same `jmri-mcp` command and `JMRI_URL` env var as Claude Desktop,
wired through Claude Code's own MCP configuration instead of a JSON file you
edit by hand.

Unlike Claude Desktop, `claude mcp add` runs `jmri-mcp` through your shell, so
it **does** inherit your shell `PATH` — a bare `jmri-mcp` works as long as the
right environment is active when you run the command (and, for `user`/
`project` scope, when Claude Code itself later launches the server).

```bash
claude mcp add jmri -e JMRI_URL=http://localhost:12080 -- jmri-mcp
```

- `-e JMRI_URL=...` sets the same env var as Claude Desktop's config.
- The bare `--` separates `claude mcp add`'s own flags from the command to
  run; everything after it (`jmri-mcp`) is passed through untouched.
- `-s/--scope` picks where the config is stored: `local` (default, this
  machine only), `user` (all your projects), or `project` (checked into a
  `.mcp.json` next to this repo, shared with anyone who clones it — don't use
  `project` scope if `JMRI_URL` shouldn't be committed).

Verify it's registered and reachable:

```bash
claude mcp list
claude mcp get jmri
```

Then ask Claude Code something that needs a tool call (e.g. "what's the
status of the JMRI power systems?") to confirm the tools are actually being
called, not just registered.

## xiaozhi / Kira

`xiaozhi_wrapper` (part of the `jmri-mcp` package) is a generic stdio↔WebSocket
bridge — it speaks stdio to `jmri-mcp` (or any configured MCP server) on one
side and `MCP_ENDPOINT` (a WebSocket) on the other. It knows nothing about
JMRI; the only link between the two packages is `mcp_config.json`'s
`"command": "jmri-mcp"`. See the package docstring
(`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`) for the full design.

`packages/jmri-mcp/src/xiaozhi_wrapper/mcp_config.json` is checked into the
repo as-is (not a template to copy) — it has no `env` block at all:

```json
{
  "mcpServers": {
    "jmri": {
      "command": "jmri-mcp"
    }
  }
}
```

`build_server_command()` merges any per-server `env` from this file onto a
**copy of the bridge's own environment**, not a replacement of it — so
`JMRI_URL` doesn't need to be duplicated here, it just needs to already be
exported wherever `jmri-xiaozhi-bridge` is launched from (same variable used
everywhere else in this project).

Install the extra dependency this package needs beyond the core install
(`python-dotenv`, for optionally loading `MCP_ENDPOINT`/`JMRI_URL` from a
`.env` file):

```bash
pip install -e ./packages/jmri-core -e "./packages/jmri-mcp[xiaozhi]"
```

The bridge is launched from your own shell, so it **does** inherit your
shell `PATH` — a bare `"jmri-mcp"` in the config works as long as the right
conda env is active when you launch it. Set `MCP_ENDPOINT` (your xiaozhi
WebSocket URL) and `JMRI_URL` and run it from anywhere — it finds its own
`mcp_config.json` next to the installed package, not the current directory:

```bash
export MCP_ENDPOINT=<your xiaozhi ws endpoint>
export JMRI_URL=http://localhost:12080
jmri-xiaozhi-bridge
```

A successful run logs a WebSocket connection to xiaozhi, `jmri-mcp` starting
up, and an incoming `ListToolsRequest`. Tested end-to-end against xiaozhi
this way (previously as a standalone script in the separate `kira` project,
ported into this repo 2026-07-09).
