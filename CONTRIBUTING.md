# Contributing

Thanks for looking at this project. It's a small, early-stage MCP server with a
few hard constraints that aren't obvious from the code alone — read this before
sending a PR.

## Project layout

See [docs/architecture.md](docs/architecture.md) for the module layout and
design notes, and [docs/cli.md](docs/cli.md)'s "Development conventions for
`cli/*.py`" section for the day-to-day checklist when touching CLI code
specifically. This document covers the rules that apply across the whole repo.

## Hard rules

- **Pure stdio MCP server. Never `print()` in server/tool code.** stdout is the
  JSON-RPC channel; any stray stdout write breaks every MCP client connected to
  this server (Claude Desktop rejects a server that pollutes stdout; the
  xiaozhi bridge forwards every stdout line as a protocol message). All
  logging goes to stderr via the stdlib `logging` module. `jmri-cli` (the
  standalone CLI, not the MCP server) is the one place `print()` to stdout is
  correct and expected.
- **Fully dynamic — no hardcoded layout data.** Systems, roster entries,
  turnouts, sensors, and signal masts are discovered live from JMRI. The only
  configuration is the `JMRI_URL` env var (and, for the CLI's i18n,
  `JMRI_MCP_LANG`). Don't hardcode a user's roster/turnout/system names
  anywhere.
- **Honest tool results.** Never report `success: true` without checking
  JMRI's actual response *and* re-reading state to confirm it took effect (see
  "State can change outside your session" below). JMRI's own POST responses
  can be transient/stale — confirm by re-read, not by trusting the write
  response.
- **LLM-oriented MCP tool docstrings.** Every `@mcp.tool()` function needs a
  docstring with enough context (in English) that an LLM can tell *when* and
  *how* to call it without guessing — decoder-relative semantics, caveats
  about state that can change externally, what to do when a name is ambiguous,
  etc. Don't skimp on docstrings to save tokens; they're the tool's only
  interface contract with the model.
- **CLI parity.** Every MCP tool needs a corresponding `jmri-cli` subcommand,
  so functionality can be exercised and validated without an MCP client in the
  loop. Build and manually test the CLI side in the same PR as the MCP tool,
  not as a follow-up.
- **State can change outside your session.** JMRI throttle state (speed,
  direction, functions) can be changed at any time by other clients — JMRI
  panels, other throttle apps, another MCP session. A cache that's updated
  only from this session's own commands goes stale and is not acceptable. The
  required pattern is a cache kept live by JMRI's own broadcasts (see
  `jmri_ws.py`'s `_dispatch`/`_update_throttle_cache`, which updates from
  *every* throttle message this connection sees, not just replies to its own
  requests) — JMRI has no read-only "get current throttle state" call to poll
  instead. Apply this to any new set_speed/stop/set_direction/set_function-style
  tool.

## No hardcoded literals: constants and i18n

This codebase went through a deliberate refactor to remove magic
strings/numbers and inline user-facing text from the code. New code must
follow the same pattern:

- **Constants.** Magic strings/numbers (state codes, id prefixes, ranges,
  timeouts, JMRI field names, REST path templates, ...) belong in a
  `src/jmri_mcp/constants/*.py` module, never inline. Check the existing
  modules (`constants/protocol.py`, `constants/endpoints.py`,
  `constants/client_tuning.py`, `constants/cli.py`) before adding a new
  constant — it may already exist.
- **i18n.** Every user-facing message goes through the hand-rolled i18n system
  in `src/jmri_mcp/i18n/` (`i18n.t(key, **kwargs)` / `i18n.error(exc)`), never
  a raw f-string printed to the user. This is a deliberate project-specific
  choice — explicitly not gettext or an external i18n library — don't
  introduce one. Add any new key to **both** `i18n/en.json` and
  `i18n/fr.json` in the same change; a key present in only one language
  silently falls back to English at runtime, which hides missing
  translations instead of surfacing them at review time.
  - The one exception: `key=value` diagnostic CLI output (e.g.
    `f"address={address} speed={speed}"`) keeps its English label
    unconditionally — treated as machine/script-parseable logging output, not
    translated prose.
  - LLM-facing instruction strings (the MCP server's system instructions,
    executor-mode trigger text) are out of scope for i18n — they're consumed
    by the LLM host, not read directly by a human, and some intentionally mix
    French/English trigger vocabulary that a translation table would break.
- **Structured errors.** `jmri_client`/`jmri_ws` never bake English into an
  exception. They raise the shared `JmriError(code, **kwargs)`
  (`src/jmri_mcp/jmri_errors.py`) with no English baked in; `cli/*.py` and
  `tools/*.py` translate at the point they catch it. Don't reintroduce a
  second `JmriError` class or an aliased import — there is exactly one, and
  `except JmriError` must catch both HTTP- and WS-origin errors uniformly.

See [docs/cli.md](docs/cli.md#development-conventions-for-clipy) for the full
checklist (table headers, argparse help, docstrings on small helpers, test
conventions) once you're editing `cli/*.py` specifically.

## Working with real hardware

If you have a real JMRI server / DCC layout reachable, be deliberate about it:

- Never run a command that could set a locomotive in motion (`throttle
  speed`/`acquire`/`forward`/`reverse`/etc., or the equivalent MCP tools)
  against a real, non-test JMRI server without a human directly confirming
  that specific command first — "just to debug" is not a substitute for
  confirmation, and a prior confirmation does not carry over to the next
  command.
- Prefer testing and debugging against the mocked suite / `fake_jmri` fixture
  (see [docs/testing.md](docs/testing.md)) over a real server. The opt-in live
  suite (`pytest -m live`) exists for exactly this and has its own safety
  knobs (`packages/jmri-core/tests/config/live.ini`: `enable_write_tests`,
  `min_toggle_interval_seconds`)
  for the rare cases that do need real hardware.
- `DCC++` command stations drive real relays — rapid on/off cycling causes
  real wear. Don't write a test or debugging loop that toggles power/turnouts
  repeatedly against real hardware.

## Testing

- `uv sync --all-packages --extra test` then `uv run pytest` runs the full
  mocked suite across all three packages (no network calls, no hardware side
  effects) — this is what CI runs and what you should run after any change.
  See [docs/testing.md](docs/testing.md) for the full breakdown.
- Don't hardcode an English literal in a test that duplicates production text
  sourced from `i18n/en.json`. Assert against
  `jmri_mcp.i18n.lookup("en", key, **kwargs)` (or the `expect_error()` helper
  in `tests/conftest.py` for `JmriError` codes) instead of a re-typed string,
  so a wording change in `en.json` doesn't silently desync the test suite.
  `tests/conftest.py`'s autouse `JMRI_MCP_LANG=en` fixture keeps the suite
  deterministic regardless of your shell's environment — don't remove it.
- See [docs/testing.md](docs/testing.md) for the full mocked-vs-live split and
  how to configure the live suite if you need it.

## Docs

If a change adds or changes a tool, CLI subcommand, config key, module, or
setup step, update the relevant `docs/` chapter (and the README, if relevant)
in the **same PR** — don't defer docs to a later pass.

## Commit style

- Commit messages: a short imperative summary line, English, describing the
  *why* as much as the *what*. Look at `git log` for the established tone.
- Reference the issue being closed with `Closes #N` in the commit message when
  applicable.
- Keep commits scoped to one logical change; a large refactor is usually
  better split into several commits (see the constants/i18n refactor's history
  for an example of a multi-phase, one-commit-per-phase migration).

## Legacy code

`legacy/jmri_experimental.py` is a kept-for-reference prototype — don't extend
it; new work goes in `src/jmri_mcp/`.
