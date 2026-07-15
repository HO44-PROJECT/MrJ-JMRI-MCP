# MrJ JMRI AI Assistant

**Talk to your model railroad.**

Bring AI to your [JMRI](https://www.jmri.org/) powered layout. Connect your favorite AI assistant and control your [DCC](https://www.nmra.com/digital-command-control-dcc) model railroad using natural language through voice or chat.

Drive locomotives, control turnouts, operate signals, manage layout accessories, and more — just by asking.

Compatible with MCP clients such as [Claude Desktop](https://claude.ai/download), [Claude Code](https://claude.com/claude-code), [xiaozhi](https://github.com/78/xiaozhi-esp32), and other MCP-compatible AI assistants.

## Features

**MrJ JMRI AI Assistant provides:**

- Ready-to-use package for easy installation
- Full documentation with setup guides and usage examples
- A complete MCP (Model Context Protocol) server for JMRI integration
- A command-line interface (`jmri-cli`) for direct control, scripting, and automation
- 42 MCP tools exposing the main JMRI capabilities:
  - Power management
  - Locomotive throttles and functions
  - Roster management
  - Turnouts
  - Sensors
  - Layout lights
  - Signals
  - Blocks
  - Operating modes

See the complete MCP tools reference in [mcp-tools.md](mcp-tools.md).

The goal is simple: make advanced JMRI control accessible to every model railroader, from casual operators to automation enthusiasts.

## Installation

Getting started is designed to be simple.

See the [installation guide](docs/install.md) and [quick start guide](docs/quickstart.md) for setup instructions, configuration, and first commands.

## AI Assistant Setup

- [Claude Desktop and Claude Code](docs/llm-setup-claude.md)
- [xiaozhi / Kira](docs/llm-setup-xiaozhi.md)

## Command Line Interface

The included CLI provides direct access to your JMRI layout without requiring an AI assistant.

It can be used for:
- Manual control
- Scripting
- Automation
- Testing and troubleshooting

See the [CLI reference](docs/cli.md).

## MCP Tools

The MCP server currently exposes 42 tools covering the main JMRI capabilities.

See the complete reference:

- [MCP Tools Reference](mcp-tools.md)

## Status

**v1.0**

The project is fully functional and actively maintained.

Future improvements, feature requests, and roadmap items are tracked in the [project board](https://github.com/orgs/HO44-PROJECT/projects) and the [issues](../../issues).

## Requirements

- Python ≥ 3.10 (developed on 3.12)
- A running JMRI Web Server (tested with JMRI 5.4)

See [docs/install.md](docs/install.md) for installation details.

## Documentation

### Getting started

- **[Quick start](docs/quickstart.md)** — fastest path from a fresh installation to a working voice/chat command
- **[Installation](docs/install.md)** — package installation, configuration, and verification

### AI assistants

- **[Claude Desktop / Claude Code setup](docs/llm-setup-claude.md)** — connect your AI assistant to JMRI
- **[xiaozhi / Kira setup](docs/llm-setup-xiaozhi.md)** — expose JMRI control to voice assistants

### Advanced users

- **[CLI reference](docs/cli.md)** — `jmri-cli` command reference
- **[Architecture](docs/architecture.md)** — module design, JMRI clients, WebSocket implementation
- **[Testing](docs/testing.md)** — mocked and live test suites, hardware safety configuration
- **[Resources](docs/resources.md)** — references for JMRI, MCP, and xiaozhi/Kira

### Project

- **[ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md)** — thanks to the open-source projects this depends on
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — contribution guidelines and project conventions

## Configuration

| Variable | Default | Description |
|---|---|---|
| `JMRI_URL` | `http://localhost:12080` | Base URL of the JMRI Web Server |

## License

[AGPL-3.0-or-later](LICENSE)

Chosen deliberately over a permissive license (MIT/Apache) so that anyone who modifies this project and offers it as a network service (not just redistributes the code) must also publish their modified source.

See the [license text](LICENSE) for the exact terms.

### Third-party code

`xiaozhi_wrapper` (part of the `jmri-mcp` package) is adapted from the MCP pipe example in [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT License, Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. and Project Contributors).

See the package documentation:

`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`
