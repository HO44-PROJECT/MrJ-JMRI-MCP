# xiaozhi / Kira setup

`jmri-mcp` is a pure stdio MCP server — it doesn't know or care which client
launches it. This page covers exposing it to a xiaozhi-based voice assistant
(such as Kira) via the bundled bridge. See [resources.md](resources.md) for
links to the xiaozhi-esp32 project and Kira itself.

`xiaozhi_wrapper` (part of the `jmri-mcp` package) is a generic stdio↔WebSocket
bridge — it speaks stdio to `jmri-mcp` (or any configured MCP server) on one
side and `MCP_ENDPOINT` (a WebSocket) on the other. It knows nothing about
JMRI; the only link between the two packages is `mcp_config.json`'s
`"command": "jmri-mcp"`. See the package docstring
(`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`) for the full design.

## Install

Install the extra dependency this package needs beyond the core install
(`python-dotenv`, for optionally loading `MCP_ENDPOINT`/`JMRI_URL` from a
`.env` file):

```bash
pip install -e ./packages/jmri-core -e "./packages/jmri-mcp[xiaozhi]"
```

## Configure

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
everywhere else in this project). This applies to every `jmri-mcp` env var,
not just `JMRI_URL` — for example [exhibition mode](exhibition.md)'s
`EXHIBITION_PASSWORD`/`EXHIBITION_ALLOWED_ADDRESSES`/`EXHIBITION_START_ON`
need to be set the same way (either exported in the launching shell, or added
to this file's `env` block) to take effect for Kira specifically. A `.mcpb`
installer's inputs only configure the client it was run for (e.g. Claude
Desktop) — they don't propagate here automatically.

## Run

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

## Verifying it's connected

A successful run logs a WebSocket connection to xiaozhi, `jmri-mcp` starting
up, and an incoming `ListToolsRequest`.
