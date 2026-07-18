# Resources

Reference links used while building this project, grouped by topic.

## JMRI

- [JMRI project site](https://www.jmri.org/) — the server this entire tool talks to.
- [JMRI JSON Web Service docs](https://www.jmri.org/help/en/html/web/JsonServlet.shtml) —
  the `/json/*` REST + WebSocket API this project's `jmri_client`/`jmri_ws` modules
  implement (`/json/power`, `/json/roster`, `/json/turnout`, `/json/throttle`, etc.).
- [PanelPro](https://www.jmri.org/help/en/html/apps/PanelPro/index.shtml) — JMRI's own
  desktop control app, useful as a second client when testing/comparing behavior (see
  `docs/architecture.md`'s `throttle sniff` notes).

## Claude / MCP

- [Model Context Protocol](https://modelcontextprotocol.io/) — the protocol spec this
  server implements (`jmri-mcp` is a pure stdio MCP server).
- [Claude Desktop](https://claude.ai/download) and
  [Claude Code](https://docs.claude.com/en/docs/claude-code) — the two Anthropic MCP
  clients this project targets; see [llm-setup-claude.md](llm-setup-claude.md) for wiring
  instructions.

## xiaozhi / Kira

- [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) — the open-source voice assistant
  firmware/project `xiaozhi_wrapper` bridges to; its MCP pipe example is the basis for
  this project's bridge (see `packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`'s module
  docstring and the README's "Third-party code" section for the MIT license notice).
- [Kira AI Assistant (MakerWorld)](https://makerworld.com/en/models/2836210-kira-ai-assistant#profileId-3161104) —
  the physical voice-assistant device this project was built to control JMRI from.

## MrJ hardware

- MrJ ESP32 board — TODO: add link.
- MrJ signals — TODO: add link.
