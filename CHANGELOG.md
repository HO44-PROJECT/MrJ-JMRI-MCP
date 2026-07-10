# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project does not yet follow strict semantic versioning (pre-1.0, `jmri-mcp`
package version stays `0.1.0` during active milestone development).

## [Unreleased]

### Added

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
