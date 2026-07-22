# Claude setup

`jmri-mcp` is a pure stdio MCP server — it doesn't know or care which client
launches it. This page covers Claude Desktop and Claude Code.

## Claude Desktop

Claude Desktop installs `jmri-mcp` as a **desktop extension** (`.mcpb`
bundle) — a double-click install with a graphical Configure screen. Claude
Desktop manages the Python environment itself; there's no `pip install` step
and no JSON file to hand-edit.

Follow **[section 2 of the installation guide](../INSTALL.md#2-mcpb-bundle-in-claude-desktop)**
for the full walkthrough with screenshots: enabling JMRI's web server,
downloading the `.mcpb` from the [latest release](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/releases/latest),
installing it, setting `JMRI Server URL` on the Configure screen, and
enabling the extension.

A community-written, more visual version of the same walkthrough is also
available: the [Instructable](https://www.instructables.com/Control-Your-JMRI-Railroad-by-Chatting-With-Claude/)
"Control Your JMRI Railroad by Chatting With Claude."

### Verifying it's connected

Ask Claude something that needs a tool call, e.g. "what's the status of the
JMRI power systems?". If it says the JMRI tools aren't available, check:

```bash
tail -f ~/Library/Logs/Claude/mcp-server-jmri.log
```

A healthy startup ends with `Server started and connected successfully`
followed by successful `tools/list` request/response pairs, and no
`Shutting down` line afterwards. If the process is simply gone with no error,
restart Claude Desktop (**Cmd+Q**, not just closing the window — closing the
window leaves the app and its subprocess running) — see also the "Claude
will return soon" transient hiccup noted in the install guide.

If the extension is installed but tools still aren't showing up, check
**Settings → Extensions → JMRI MCP** is toggled **Enabled** and that Tool
permissions weren't left denied.

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
