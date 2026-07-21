# Documentation

- [Architecture](architecture.md) — module layout, the two JMRI clients, WebSocket design notes.
- [Installation](install.md) — requirements, `pip install`, verifying the entry points.
- [MCP tool inventory](mcp-tools.md) — every tool the LLM can call, grouped by domain, with signatures.
- [Exhibition mode](exhibition.md) — the restricted-safety mode for public demos: what's restricted, and how to configure it.
- [CLI reference](cli.md) — `jmri-cli`, every subcommand, examples.
- [Claude setup](llm-setup-claude.md) — wiring the MCP server into Claude Desktop and Claude Code.
- [Codex (ChatGPT) setup](llm-setup-codex.md) — registering the MCP server with OpenAI Codex via `jmri-mcpctl` (requires ChatGPT Plus).
- [xiaozhi/Kira setup](llm-setup-xiaozhi.md) — exposing the MCP server to a xiaozhi-based voice assistant.
- [Testing](testing.md) — the mocked test suite vs. the opt-in live suite, and the hardware-safety config.
- [Release procedure](release.md) — building and publishing `jmri-core`/`jmri-cli`/`jmri-mcp` to PyPI.
- [Resources](resources.md) — reference links for JMRI, MCP, and xiaozhi/Kira.
- [Known JMRI issues reported upstream](jmri-upstream-issues.md) — JMRI bugs found while building this project, reported to the JMRI tracker, and what this project does to work around them.
- [Acknowledgments](../ACKNOWLEDGMENTS.md) — thanks to the open-source projects this depends on.

See the top-level [README](../README.md) for the project overview, and [CLAUDE.md](../CLAUDE.md) for
verified facts about the JMRI JSON API and the project's working agreement.
