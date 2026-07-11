# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project does not yet follow strict semantic versioning (pre-1.0, `jmri-mcp`
package version stays `0.1.0` during active milestone development).

## [Unreleased]

### Added

- `jmri-cli` command-shape redesign: two consistency rules now apply across
  every subcommand group. **Bare group = smart default** — `jmri-cli power`
  behaves like `power status`, `jmri-cli roster` like `roster list`,
  `jmri-cli throttle` like `throttle list`, `light`/`turnout`/`sensor`/
  `signal` likewise default to their own `list`. **Verb elevation** — a
  state value that used to be a positional argument is now the subcommand
  name itself, with the target becoming an optional fuzzy positional that
  defaults to "everything": `power on [system]` / `power off [system]`
  (replacing `power set` / `stop-all` / `start-all`), `throttle forward
  <loco>` / `throttle reverse <loco>` (replacing `throttle direction`),
  `throttle on <loco> [function]` / `throttle off <loco> [function]`
  (replacing `lights-on` / `lights-off` / `function`), `light on [name]` /
  `light off [name]` and `turnout closed [name]` / `turnout thrown [name]`
  (replacing each group's `status` / `set`). `throttle stop [loco]`
  replaces `stop-all` and, with no loco given, stops every address the
  local cache has touched.
  - Added `power get [system]` (read one/all systems without the table)
    and `power default` (print the configured default system).
  - `roster find` / `roster functions` now accept a DCC address as well as
    a fuzzy name — `resolve_roster_entry()` matches a numeric query against
    `address` first, falling back to name matching otherwise.
  - Every list-style output (`power status`, `roster list`, `throttle
    list`, `light list`, `turnout list`) now renders as a `tabulate` table
    with explicit headers instead of ad hoc printed lines.
  - New `src/jmri_mcp/cli/state.py`: a local JSON cache at
    `~/.jmri-cli/throttle_state.json` recording the last known
    speed/direction/functions per address. `jmri-cli throttle` is
    architecturally one-shot (acquire → act → close per invocation; JMRI
    releases the throttle the moment the connection closes — see the
    known-limitation note on `throttle speed`), so there is no live JMRI
    state left to query between separate CLI invocations once the process
    exits. This cache is what makes bare `throttle` (list touched locos)
    and `throttle speed <loco>` (no value = read current) possible; it is
    a convenience cache only, not a source of truth — another client's
    changes aren't reflected until the next `jmri-cli throttle` command
    touches that address again.
  - `throttle on`/`off` with no function number given resolves every
    labeled function from the roster (`get_roster_function_labels()`) and
    sets them all; if the locomotive has no labeled functions and no
    number was given either, this is an explicit error, not a silent F0
    fallback.
  - Full test suite rewritten/extended alongside the redesign (244 passed);
    `docs/cli.md` and `docs/architecture.md` updated to match.

- **Fixed**: `jmri-cli --help` rendered as an unreadable wall of text —
  argparse's default formatter rewraps a multi-line `description` into one
  prose paragraph, so the ~30 one-per-line usage examples in the CLI
  package docstring collapsed into a run-on block. Also, each of those
  lines repeated `JMRI_URL=http://localhost:12080 python -m jmri_mcp.cli`
  verbatim, which was pure noise once `JMRI_URL` was already exported.
  Fixed by moving the full example list to its own `jmri-cli examples`
  subcommand (prints the real, currently-configured `JMRI_URL` once at the
  top, then bare `jmri-cli <command>` lines — no per-line prefix), shrinking
  `--help`'s own description to a short paragraph, and setting
  `formatter_class=argparse.RawDescriptionHelpFormatter` so that shorter
  description is never auto-rewrapped either. A new test re-parses every
  line `jmri-cli examples` prints against the real argument parser, so a
  renamed/removed subcommand that isn't kept in sync fails the suite
  instead of silently going stale.

- Signal masts (#26): `list_signals` / `get_signal` / `set_signal` +
  `jmri-cli signal list/status/set`, a fifth layout domain alongside light/
  turnout/sensor. Covers JMRI's `signalMast` objects only, not
  `signalHead` — confirmed with the maintainer that their DB-1969 masts
  are driven by a custom ESP32 decoding raw DCC accessory frames off the
  rail (no `signalHead` objects exist in their JMRI at all), and
  `signalMast` (named aspects like `Hp0`/`Hp1`/`Hp2`) is the level
  PanelPro users actually name and interact with anyway. Aspect names are
  passed through verbatim and never validated locally — JMRI's JSON API
  has no endpoint listing a mast's valid aspects, so `set_signal` relies
  on the same re-read-and-confirm honesty contract as `set_power`/
  `set_turnout`/`set_light` instead of guessing.
  - `resolve_signal` shares `resolve_turnout`'s tolerant matching
    (exact name/userName, then an unambiguous `userName` fragment) — note
    fragment matching only ever looks at `userName`, not the system name,
    which is more noticeable here since JMRI auto-generates long system
    names for DCC-driven masts (e.g. `ZF$dsm:DB-HV-1969:block(31)`) that
    are commonly left without a `userName` set in PanelPro.
  - Live-verified against the maintainer's real JMRI: `list_signals`/
    `get_signal` correctly read their one configured mast.
  - **Fixed**: the first live write test of `set_signal` (one user-
    authorized POST requesting `Hp0`) completed with no HTTP error but the
    re-read aspect stayed unchanged — correctly reported as
    `confirmed: false` rather than a false success, but the underlying
    cause was a real bug, not external hardware. Root-caused by reading
    JMRI's own server source (`JsonSignalMastHttpService.doPost()`): the
    POST handler reads the JSON field `"state"`, not `"aspect"` — this
    project's client sent `{"name": ..., "aspect": ...}`, so JMRI's
    `data.path(STATE).isTextual()` check was always false and the entire
    aspect-setting branch was silently skipped, returning 200 with the
    mast's unchanged data. Fixed by sending `"state"` instead. Bonus
    finding from the same source read: JMRI validates the aspect name
    server-side against the mast's signal system and raises a proper 400
    `JsonException` for an unknown one (surfaced here as a `JmriError` /
    tool `"error"`) — so `set_signal` no longer needs to guess whether a
    non-confirming aspect was invalid or just unresponsive hardware; an
    invalid name is now a hard error, not a silent non-confirm. Added a
    regression test asserting the POST body's JSON key, since the
    original tests mocked the endpoint without checking the payload shape
    and would not have caught this.

- **Fixed**: `src/xiaozhi_wrapper` is adapted from the MCP pipe example in
  [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT License) but
  only referenced it in prose, with no copyright notice — MIT requires the
  original copyright/permission notice to be included in copies or
  substantial portions of the software. Added the full MIT notice and a
  direct link to the source repo in `src/xiaozhi_wrapper/__init__.py`'s
  module docstring, plus a "Third-party code" section in the README
  pointing to it.

- **Fixed**: docs, CLI `--help` examples, and `src/xiaozhi_wrapper/mcp_config.json`
  used the maintainer's real network address (`10.0.20.20`) as their example
  JMRI URL. Replaced with a generic `http://localhost:12080` everywhere
  public (docs/, CLI help text, tests). While auditing `mcp_config.json`,
  found its `"env": {"JMRI_URL": ...}` block was redundant — `build_server_command()`
  already merges any per-server `env` onto a **copy** of the bridge's own
  environment, so `JMRI_URL` was already inherited if exported before
  launching `jmri-xiaozhi-bridge`. Removed the block entirely rather than
  just changing its value; `docs/llm-setup.md`'s xiaozhi/Kira section
  updated to say so. `config/live.ini` (gitignored, names the real address)
  and `CLAUDE.md` (gitignored, personal working context) are untouched —
  neither is public.

- **Fixed**: the live test suite (`pytest -m live`) required its own
  `config/live.ini` `url` or `JMRI_URL_LIVE` env var, duplicating the
  `JMRI_URL` most setups already export for the CLI/MCP server. It now
  falls back to plain `JMRI_URL` when neither is set — `config/live.ini`
  is only still required for the write-test safety knobs
  (`write_test_system`, `enable_write_tests`,
  `min_toggle_interval_seconds`), which have no env-var-elsewhere
  equivalent.

- Documentation (#19):
  - `docs/quickstart.md` — a single fast path from a fresh clone to a working
    voice/chat command, linking out to the existing install/CLI/llm-setup
    docs for detail instead of duplicating them. Linked from the README.
  - `docs/llm-setup.md` gained a real Claude Code section (`claude mcp add`
    config example, scope flags, `claude mcp list`/`get` verification) —
    previously just a stub pointing at this issue.
  - Verified live that the server's `initialize` response is pure
    single-line JSON-RPC on stdout with nothing else mixed in (per this
    issue's own text, referencing #1) — no code change needed, `print()`
    only exists in `jmri-cli`, never in the MCP server path.

- Layout-wide STOP features (#23):
  - `emergency_stop_all` — emergency-stop every locomotive throttle this MCP
    session currently holds, in one call, instead of naming addresses one at a
    time. MCP tool + `jmri-cli throttle stop-all [-a ADDR ...]`. Only
    reaches throttles this session has acquired — see `power_off_all` for a
    guarantee that covers every locomotive regardless of who's driving it.
  - **Fixed**: `jmri-cli throttle stop-all` originally required `-a/--address`
    to be typed explicitly, which contradicted its own name — "all" now
    defaults to every address in JMRI's roster (`get_roster()`), matching how
    `power stop-all` needs no argument. `-a` remains available to limit the
    stop to specific addresses. JMRI exposes no scan of what's actually on the
    DCC bus (verified live: no RailCom/reporters configured, `GET
    /json/throttle` list still 400s), so the roster is the only address list
    available short of cutting power outright (`power_off_all`).
  - `power_off_all` — cut power to every DCC system JMRI knows about at once,
    each confirmed by re-read like `set_power`. The real "stop absolutely
    everything on the layout" primitive. MCP tool + `jmri-cli power stop-all`.
  - `power_on_all` — the inverse: restore power to every DCC system at once.
    MCP tool + `jmri-cli power start-all`. Does NOT resume any locomotive's
    previous speed (JMRI's throttle state is untouched by a power cycle) —
    only restores track power, not an "undo" of `power_off_all`.
  - Both `power_off_all`/`power_on_all` and `emergency_stop_all`'s docstrings
    explicitly anchor to natural-language trigger phrases in English and
    French ("cut the power"/"coupe le courant", "turn everything on"/"allume
    tout", "stop everything"/"arrête tout") so voice commands with no named
    system/locomotive reliably map to the right whole-layout tool.
  - Executor mode (`set_executor_mode` / `get_executor_mode`) — a concise,
    no-narration response style the LLM can switch into on request. Works by
    returning a standing instruction string in the tool's own result, re-
    delivered on every call, since this needs to flip on/off mid-session and
    MCP's `instructions` field (below) is static/one-shot. MCP-only, no CLI
    equivalent (no JMRI state involved).
  - MCP `instructions` field: the server now sets `FastMCP(..., instructions=...)`,
    delivered once in the `initialize` response, mapping the four whole-layout
    tools above to their French/English trigger phrases — the one server-level
    channel that reaches the host LLM before any tool has been called. Covered
    by `tests/test_server.py` and live-verified via a real stdio handshake.
  - **Fixed**: a live user test showed "coupe le courant" ("cut the power")
    routed to `emergency_stop_all` instead of `power_off_all`, even though
    both `_SERVER_INSTRUCTIONS` and `power_off_all`'s own docstring already
    listed the phrase. Both tools' docstrings and `_SERVER_INSTRUCTIONS` now
    carry an explicit disambiguation: a phrase naming power/current always
    means `power_off_all`, never `emergency_stop_all`, even though both sound
    like stop commands — `emergency_stop_all` stops motion on throttles this
    session holds, `power_off_all` cuts power to every system regardless of
    who's driving. Covered by a new assertion in `tests/test_server.py`.

- **Fixed** (#24): `get_power`/`list_systems` returned JMRI's connection
  name verbatim (e.g. `"zou (test)"`), but nothing told the LLM this
  parenthetical was a usable answer to "what is system X for?" — JMRI has
  no separate field for a connection's purpose, the parenthetical is the
  only place it's recorded. `compact_power()`, `get_power`, and
  `list_systems` docstrings now explicitly say to read a system's purpose
  from `"name"` instead of saying the information isn't available.
  Docstring-only change, no parsing/new field, per explicit user
  preference. Live-verified against the real JMRI server: `ohara
  (turnouts)`, `zou (test)`, `taya (accessories)`, `raijin (tracks)`.

- **Fixed** (#25): re-POSTing a power state JMRI/DCC++ already reports
  (e.g. `ON` on a system already `ON`) doesn't no-op — it's a real bug on
  the user's installation that knocks the system into state `UNKNOWN`,
  awkward to recover from. `jmri_client.set_power()` now re-reads current
  state before POSTing (not just after) and skips the POST entirely if it
  already matches the request. Applies everywhere uniformly since every
  caller (`set_power` MCP tool, `jmri-cli power set`, and `power_off_all`/
  `power_on_all`'s shared loop) goes through this one function.

## [0.1.0] - milestones M1-M4

Initial implementation, built milestone by milestone against a real JMRI 5.4.0
server. Package restructured into one module per concern
(`jmri_client/`, `jmri_ws/`, `tools/`, `cli/`) partway through, with the
original single-file prototype kept at `legacy/jmri_experimental.py` for
reference only.

### M1 - Foundations & reliable power

- FastMCP stdio server skeleton, stderr-only logging (stdout is the JSON-RPC
  channel and must never be polluted).
- `list_systems` / `get_power` / `set_power` — dynamic power-system discovery
  (no hardcoded layout data), with re-read-and-confirm honesty after every
  POST (JMRI/DCC++'s immediate POST response is transient/unreliable).
- `system_status` one-call diagnostic tool.

### M2 - Throttle & cab control

- `JmriWsClient` — persistent, auto-reconnecting WebSocket client with
  heartbeat-paced keepalive and serialized request/response correlation.
- `acquire_throttle` / `release_throttle`, keyed on DCC address only (JMRI's
  own `throttle` id is never exposed to the LLM).
- `set_speed` / `stop` / `emergency_stop`, `set_direction`, `set_function`
  (F0-F28) + `lights_on` / `lights_off` shortcuts. All built on a live
  per-throttle cache fed by every message JMRI pushes to the connection
  (solicited or not, since JMRI pushes state changes to every connection
  holding an address) — required because JMRI sends no reply at all when a
  requested value already matches current state, and there is no read-only
  way to poll current throttle state.
- `jmri-cli throttle sniff` — live protocol dump for debugging, including
  third-party traffic from other JMRI clients.
- Full CLI parity for every tool in this milestone.

### M3 - Roster

- `list_roster` — compact roster listing (address, name, road, model),
  fixing a legacy envelope-unwrapping bug.
- `find_locomotive` — fuzzy, accent-insensitive name-to-address resolution
  (exact match, then unambiguous fragment).
- `get_locomotive_functions` — user-labeled decoder function names read from
  JMRI's own roster editor, so a spoken function name ("les feux arrière")
  resolves to the right F-number without the user needing to know it.

### M4 - Layout

- `list_lights` / `get_light` / `set_light` — layout/scenery lights, distinct
  from a locomotive's F0 headlight function.
- `list_turnouts` / `get_turnout` / `set_turnout` — CLOSED/THROWN vocabulary
  matching JMRI/PanelPro's own terminology.
- `list_sensors` / `get_sensor` — read-only (sensors report real hardware
  state; this project never writes to one).

### Integrations

- `src/xiaozhi_wrapper/` — generic stdio↔WebSocket bridge exposing `jmri-mcp`
  (or any stdio MCP server) to the xiaozhi/Kira voice assistant, ported
  in-repo from the separate `kira` project.
- Claude Desktop integration via `claude_desktop_config.json`.

### Project

- AGPL-3.0-or-later license.
- Automated test suite (`respx` HTTP mocks, a local `websockets` fixture
  standing in for JMRI's WebSocket server) and `ruff` linting.
