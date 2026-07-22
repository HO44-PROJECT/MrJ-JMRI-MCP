# MrJ JMRI AI Assistant

*[Version française](README.fr.md)*

[![PyPI - jmri-mcp](https://img.shields.io/pypi/v/jmri-mcp?label=jmri-mcp)](https://pypi.org/project/jmri-mcp/)
[![PyPI - jmri-cli](https://img.shields.io/pypi/v/jmri-cli?label=jmri-cli)](https://pypi.org/project/jmri-cli/)
[![PyPI - jmri-core](https://img.shields.io/pypi/v/jmri-core?label=jmri-core)](https://pypi.org/project/jmri-core/)
[![Downloads](https://img.shields.io/pypi/dm/jmri-mcp)](https://pypi.org/project/jmri-mcp/)
[![GitHub Release](https://img.shields.io/github/v/release/HO44-PROJECT/MrJ-JMRI-MCP)](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/releases/latest)

> **License & attribution — please read before reusing this work.**
> This project is © HO44 PROJECT (MrJ) and licensed under **AGPL-3.0-or-later** (see [LICENSE](LICENSE)).
> If you redistribute, modify, or republish any part of this project — `jmri-core`, `jmri-cli`, `jmri-mcp`,
> the `.mcpb`/`.codex.zip` bundles, or the documentation — **on this repository or anywhere else** (a fork,
> another platform, a package registry, a video, a write-up), you **must**:
> - keep the original author credit (**MrJ / HO44 PROJECT**) and a link back to
>   [this repository](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP), and
> - keep the same AGPL-3.0-or-later license on any redistributed or modified version.
>
> Removing or hiding this attribution is not just bad etiquette — under AGPL-3.0 it is a
> **license violation**, and it will be treated as one. See [NOTICE.md](NOTICE.md) for details.
>
> Questions or general discussion: use [GitHub Discussions](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/discussions).
> Bug reports and feature requests: use [Issues](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/issues).

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
- 50 MCP tools exposing the main JMRI capabilities:
  - Power management
  - Locomotive throttles and functions
  - Roster management
  - Turnouts
  - Sensors
  - Layout lights
  - Signals
  - Blocks
  - Operating modes
  - Layout-wide meta tools (status overview, secure/night/day mode)

See the complete MCP tools reference in [mcp-tools.md](mcp-tools.md).

The goal is simple: make advanced JMRI control accessible to every model railroader, from casual operators to automation enthusiasts.

### Built on real hardware, not just the JMRI docs

This project was developed against a real DCC++ layout with multiple command stations,
and several of its behaviors exist specifically because live hardware doesn't always
behave the way the JMRI API documentation implies:

- **Self-healing UNKNOWN power states.** Re-sending a command station's *current* power
  state (a naive "set power ON" when it's already ON) is a known JMRI/DCC++ trap: it
  knocks the system into an UNKNOWN state instead of being a safe no-op. Every power
  command re-reads current state first and skips redundant POSTs — and if a genuine ON
  request still lands in UNKNOWN, it automatically recovers with an OFF → wait → ON
  retry sequence, rather than leaving the layout stuck.
- **Per-locomotive command station affinity.** On a layout with more than one DCC
  connection, sending a locomotive's throttle commands to the wrong command station
  doesn't raise an error — it's just silently inaudible to the decoder. Roster entries
  can declare which connection they normally run on via a `DccSystem` custom attribute
  (set in JMRI's own Roster Entry → Edit → Attributes tab, e.g. `DccSystem` = `T`), and
  throttle acquisition reads it automatically to target the right station.
- **DCC connection and hardware address surfaced on every turnout, light, and signal.**
  Listing a turnout, light, or signal reports which DCC connection actually drives it
  (resolved from its JMRI system name, e.g. `OT23` → `ohara (turnouts)`) alongside its
  raw hardware address where JMRI exposes one (turnouts and lights; signal masts don't
  expose theirs via any JMRI API today, so that field is honestly reported as unknown
  rather than guessed).
- **Every write is confirmed by re-reading real state, never by trusting the response.**
  Power, turnout, light, and signal commands all re-read JMRI's actual state after
  acting, and report exactly what was observed — including when that doesn't match what
  was asked for — instead of assuming a 200 response means the layout did what was
  requested.
- **Throttle state stays live even when driven from elsewhere.** JMRI broadcasts every
  throttle change (speed, direction, functions) to all clients holding that
  locomotive — including other JMRI panels or a second MCP session — and this project's
  throttle cache is kept continuously in sync with that stream, not just with its own
  commands, so it never reports stale state after someone else drives the train.

## What can I say?

Pick the page that matches what you want to do — each links to the next. Available in
English and French:

- **🚂 Conductor** — just want to drive trains? Start here.
  [English](CONDUCTOR.en.md) · [Français](CONDUCTOR.fr.md)
- **🔧 Tinkerer** — managing power, turnouts, signals, and the whole layout.
  [English](TINKERER.en.md) · [Français](TINKERER.fr.md)
- **🛠️ Engineer** — full tool reference, CLI, scripting, and JMRI internals.
  [English](ENGINEER.en.md) · [Français](ENGINEER.fr.md)

The conductor/tinkerer/engineer split is borrowed from [DCC-EX](https://dcc-ex.com/begin/levels.html), who came up with this framing first.

## Installation

Getting started is designed to be simple.

See the [installation guide](INSTALL.md) for every install combination (CLI, Claude Desktop `.mcpb`, Kira bridge), configuration, and first commands.

Prefer a step-by-step walkthrough with screenshots? See the community
Instructable: [Control Your JMRI Railroad by Chatting With Claude](https://www.instructables.com/Control-Your-JMRI-Railroad-by-Chatting-With-Claude/).

## AI Assistant Setup

- [Claude Desktop and Claude Code](docs/llm-setup-claude.md)
- [xiaozhi / Kira](docs/llm-setup-xiaozhi.md)

## Command Line Interface

`jmri-cli` is a full-featured command-line client for your layout, talking to JMRI
directly with no AI assistant or MCP client required — everything the MCP tools can do,
a human can do too, from a terminal.

Run it bare with no arguments to open an **interactive shell**: a single persistent
connection that keeps locomotives moving, lit, and acquired between commands (unlike a
one-shot invocation, which releases every throttle the instant it exits). The shell
adds real command-line ergonomics on top: up/down arrow **command history** persisted
across sessions (`~/.jmri-cli/shell_history`), **TAB completion** across the entire
command tree, `;`-separated multi-command lines, a `wait` command to sequence a
`--hold` and a following command, and a friendlier natural-language-ish **sentence
syntax** for speed/direction (`speed Autorail at 30 for 30 up 5 down 6 forward`)
alongside the regular flag-based form. Exiting always leaves the layout safe: any
locomotive still in motion gets a ramp-down-and-release prompt, and active functions
(lights) are turned off before the connection closes, rather than being abandoned.

Every command also works one-shot from a plain terminal for scripting, automation, and
quick manual checks or troubleshooting against a real layout.

See the [CLI reference](docs/cli.md).

## MCP Tools

The MCP server currently exposes 50 tools covering the main JMRI capabilities.

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

- **[Installation guide](INSTALL.md)** — every install combination (CLI, Claude Desktop `.mcpb`, Kira bridge), configuration, and first commands
- **[Developing on this repo](docs/install.md)** — editable installs from a cloned copy, for working on the code itself

### AI assistants

- **[Claude Desktop / Claude Code setup](docs/llm-setup-claude.md)** — connect your AI assistant to JMRI
- **[xiaozhi / Kira setup](docs/llm-setup-xiaozhi.md)** — expose JMRI control to voice assistants

### Advanced users

- **[CLI reference](docs/cli.md)** — `jmri-cli` command reference
- **[Exhibition mode](docs/exhibition.md)** — restricted-safety mode for public demos
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
| `EXHIBITION_PASSWORD` | `this is sparta` | Password required to exit exhibition mode. See [Exhibition mode](docs/exhibition.md). |
| `EXHIBITION_ALLOWED_ADDRESSES` | (none) | Comma-separated DCC addresses locomotives are restricted to while exhibition mode is on. |
| `EXHIBITION_START_ON` | (off) | If set to `1`/`true`/`yes`/`on`, the server starts already in exhibition mode. |

## Credits

<img src="https://avatars.githubusercontent.com/u/159026337?v=4" width="80" height="80" alt="MrJ" align="left" style="margin-right: 12px; border-radius: 50%;">

Built and maintained by **[MrJ](https://github.com/HO44-PROJECT)**.

Questions, bugs, and feature requests are welcome via [issues](../../issues).

## License

[AGPL-3.0-or-later](LICENSE)

Chosen deliberately over a permissive license (MIT/Apache) so that anyone who modifies this project and offers it as a network service (not just redistributes the code) must also publish their modified source.

See the [license text](LICENSE) for the exact terms, and [NOTICE.md](NOTICE.md) for what attribution is required when reusing this project.

### Third-party code

`xiaozhi_wrapper` (part of the `jmri-mcp` package) is adapted from the MCP pipe example in [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT License, Copyright (c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. and Project Contributors).

See the package documentation:

`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`
