# CLAUDE.md — project context for Claude sessions

MCP server for JMRI: voice/chat control of a DCC model railroad through any MCP client —
the **Kira** xiaozhi voice assistant (primary consumer, lives in `~/dev/kira`) and Claude
Desktop/Code. The user communicates in French; repo content (code, issues, commits) is in English.

## Hard rules

- **Pure stdio MCP server. Never `print()` anywhere** — stdout is the JSON-RPC channel.
  All logging goes to stderr (`logging`, configured in `src/jmri_mcp/server.py`).
  Proof this matters: kira's `mcp_pipe.py` forwards every stdout line to the xiaozhi
  WebSocket as a protocol message, and Claude Desktop rejects servers that pollute stdout.
- **Fully dynamic — zero hardcoded layout data.** Systems, roster, turnouts, sensors are
  discovered live from JMRI. Only config: `JMRI_URL` env var (issue #2).
- **Honest tool results.** Never report `success: true` without checking the JMRI response
  AND re-reading state (see verified facts below). Compact outputs (voice context is small).
- No xiaozhi-specific code in this repo. xiaozhi connectivity = `mcp_pipe.py` on the kira
  side (bridges stdio ↔ `MCP_ENDPOINT` WebSocket). Claude launches the stdio server directly.
- **LLM-oriented MCP tools.** Every tool needs maximal descriptive context in its
  docstring, in English, so the model actually understands when/how to use it —
  don't skimp on docstrings to save tokens.
- **CLI parity.** Every MCP tool must have a `jmri-cli` equivalent, so functionality
  can be exercised and validated without an MCP client in the loop.
- **State can change outside the MCP session.** JMRI's throttle state (speed,
  direction, functions) can be changed by other clients (JMRI panels, other
  throttle apps) at any time. A purely self-referential cache (updated only
  from this session's own commands) would go stale and is forbidden — but a
  cache kept continuously live by JMRI's own broadcasts (see `jmri_ws.py`'s
  `_dispatch`/`_update_throttle_cache`, which updates it from *every*
  throttle message this connection sees, not just replies to our own
  requests) is exactly "read the current state" and is the required
  implementation, since JMRI has no read-only "get current throttle state"
  call to poll instead (verified live, see below). Apply this to every
  set_speed/stop/set_direction/etc.

## Verified facts about the user's JMRI (tested live, JMRI 5.4.0)

- Server: `http://10.0.20.20:12080` (Web Server; REST `/json/*` + WebSocket `ws://…/json/`).
  Port 12021 (JSON server) is a **raw TCP socket, not HTTP** — the legacy prototype POSTing
  HTTP to it could never work. We use only 12080.
- `GET /json/power` returns all systems dynamically:
  `DCC++ Ohara` (prefix `O`), `DCC++ Zou` (prefix `Z`), `DCC++ Raijin` (prefix `R`, default).
  (Corrected 2026-07-09: earlier notes said "Zou" without the "DCC++ " prefix — verified
  wrong against a captured `/json/power` response, see `tests/fixtures/power_response.json`.)
- Power states: 2=ON, 4=OFF, 0=UNKNOWN, 8=IDLE. Turnouts: 2=closed, 4=thrown.
  Sensors/lights: 2/4. Emergency stop: throttle speed −1.
- **POST /json/power responses are transient**: posting `state:2` to an already-ON system
  returned `state:0` (DCC++ re-queries the station); a re-read ~1 s later showed the real
  state. Tools must confirm by re-reading, not trust the POST response.
- The HTTP servlet accepts both body formats: bare data `{"state":2,"prefix":"O"}` (documented)
  and the WebSocket envelope `{"method":"post","data":{…}}` (tolerated). Prefer the documented one.
- Roster entries are wrapped: `{"type":"rosterEntry","data":{…}}` — read `e["data"]`
  (the legacy prototype searched the envelope level → always empty). Entries are ~2 KB each
  (functionKeys, comments) → summarize for LLM output.
- **Throttles require a persistent connection**: acquire with
  `{"type":"throttle","data":{"throttle":"<id>","address":<n>}}` on the WebSocket, then send
  speed/`F<n>` on the SAME connection; JMRI releases the throttle when the connection closes.
  (Corrected 2026-07-09: the acquire key is `"throttle"`, not `"name"` — verified live; the
  reply echoes both `"throttle"` and `"name"` set to the same id, `"release":true` releases.)
- **Speed/direction on an acquired throttle**: `{"type":"throttle","data":{"throttle":"<id>","speed":<0.0-1.0 or -1.0>}}`
  (verified live) — reply only echoes the changed field(s), e.g.
  `{"speed":0.5,"name":"<id>","throttle":"<id>"}`. `speed:-1.0` is JMRI's emergency stop
  (a distinct decoder command, not just "speed 0"). Direction: `{"forward":true|false}`
  on the same shape. Sending speed/direction/function on a throttle id that was never
  acquired on this connection returns `{"type":"error","data":{"code":400,"message":"Throttles
  must be requested with an address."}}` — verified live.
- **WebSocket protocol has no request-id.** On connect JMRI sends
  `{"type":"hello","data":{...,"heartbeat":<ms>}}` — use that ms value to pace keepalive
  `{"type":"ping"}` → `{"type":"pong"}`. Verified live: concurrent requests of different
  types can come back in an order that doesn't match send order, and `{"type":"error",...}`
  replies carry no reference to the request that caused them. **Correlation is only safe if
  requests are serialized** (one in flight on the socket at a time) — see `jmri_ws.py`.
- **JMRI sends NO reply when a requested throttle speed/direction already equals the
  current value** (verified live, reproducible both fields) — a genuine silent no-op, not
  a dropped message. A "wait for exactly one reply" design hangs until timeout on a repeat
  `stop`/`set_speed` call. There is also **no read-only way to check current throttle
  state**: `GET /json/throttle/<id>` → 405, `GET /json/throttle` (list) → 400, re-acquiring
  an already-held throttle id on the same connection **crashes the connection**
  (`ConnectionClosedError`), and release-then-reacquire resets JMRI's throttle software
  state to its defaults rather than reading the real one. The only source of truth is the
  stream of messages already flowing to a connection holding the throttle.
- **JMRI pushes every throttle state change to ALL connections holding that address**, not
  just the one that requested it (verified live with two concurrent connections holding the
  same address on different throttle ids) — e.g. another JMRI panel or MCP session changing
  a loco's speed arrives here too, unprompted, as `{"type":"throttle","data":{"throttle":"<our
  id>","speed":...}}`. Combined with the no-reply fact above, `jmri_ws.py` keeps a per-throttle
  cache (`_throttles[id]["speed"/"forward"]`) updated from *every* throttle message dispatched,
  solicited or not; `set_speed()` checks it before sending and skips if already current. A
  message only counts as the answer to a pending request if its `throttle` id matches the one
  that request actually asked about (`_pending_throttle_id`) — otherwise it's routed as an
  unsolicited push, so a foreign-throttle push arriving before the real reply can't corrupt
  correlation.
- **Gotcha found via live testing, now fixed**: registering a throttle in the client's cache
  *before* the connection is guaranteed open caused a real bug — if that call was also what
  triggered the initial `connect()`, `_do_connect()`'s end-of-connect `_reacquire_throttles()`
  step would see the not-yet-sent throttle already in the cache and send a duplicate acquire
  for it, stealing the connection's one reply and hanging the real request forever (reproduced
  live: even a bare `acquire_throttle` on a fresh connection timed out). Fix: `acquire_throttle()`
  now calls `connect()` explicitly first, and only registers in the cache after that succeeds.

## Repo / board structure

- Repo: `HO44-PROJECT/MrJ-JMRI-MCP` (public). Legacy prototype kept at
  `legacy/jmri_experimental.py` — reference only, do not extend.
- Backlog: 22 issues in this repo, 5 milestones:
  M1 Foundations & reliable power (#1–6) → M2 Throttle & cab control (#7–11) →
  M3 Roster (#12–14) → M4 Layout (#15–17) → M5 Integrations & quality (#18–22).
- Project board: https://github.com/users/HO44-PROJECT/projects/3 (`MrJ-JMRI-MCP Backlog`,
  Board view copied from the user's RailwayFX project). GraphQL IDs for automation:
  - project: `PVT_kwHOCXqMoc4Bc2bI` (number 3, owner `HO44-PROJECT`)
  - Status field: `PVTSSF_lAHOCXqMoc4Bc2bIzhXcOCI`
  - options: Todo `f75ad846` · In Progress `47fc9ee4` · Done `98236657` · Ideation `8e934159`
  - example: `gh project item-edit --id <item-id> --project-id PVT_kwHOCXqMoc4Bc2bI
    --field-id PVTSSF_lAHOCXqMoc4Bc2bIzhXcOCI --single-select-option-id 47fc9ee4`

## Working agreement (per card)

1. Move the card to **In Progress** on the board.
2. Implement + smoke-test for real (e.g. MCP `initialize`/`tools/list` over stdio, checking
   stdout stays pure JSON-RPC; JMRI reads against the live server are OK, writes only as
   no-ops or with the user's go-ahead).
3. Update the relevant doc chapter(s) under `docs/` (architecture/install/cli/llm-setup/testing)
   and the README if the card adds a new tool, CLI subcommand, config key, module, or changes
   setup steps — docs land in the same commit as the card, not as a separate later pass.
4. Present the result to the user; **wait for their validation**.
5. On validation: commit with `Closes #N` in the message, push, move the card to **Done**.

## Current state (end of session 2026-07-09, continued)

- Issues #1–#7 implemented, validated, committed, closed. M1 done; M2 underway.
  - #7 (persistent WebSocket client): `src/jmri_mcp/jmri_ws.py` — `JmriWsClient` with lazy
    connect, auto-reconnect (exponential backoff), heartbeat-paced keepalive ping/pong,
    serialized request/response (see verified facts above for why), and a throttle registry
    that re-acquires after reconnect. `get_ws_client()` gives a process-wide shared instance.
    `tests/test_jmri_ws.py` added: a local `websockets` server fixture (`fake_jmri`, now
    shared via `tests/conftest.py`) stands in for JMRI since `respx` only mocks HTTP, not
    WebSockets.
  - Fixed a pre-existing, unrelated test-collection bug while running the full suite for #7:
    `tests/__init__.py` was missing, so `from tests.conftest import MOCK_JMRI_URL` (used by
    3 older test files) broke depending on how pytest was invoked. Added the empty
    `__init__.py` to make `tests/` a real package; fixed in the same commit since it blocked
    running the suite at all.
- Issue #8 (throttle acquisition / release) implemented, validated, committed, closed.
  `acquire_throttle`/`release_throttle` MCP tools in `src/jmri_mcp/tools.py`, wiring
  `jmri_ws.py` into the LLM-facing surface for the first time. Design: **DCC address is
  the only key the LLM ever uses** — JMRI's own `throttle` id is never exposed;
  `_throttle_id(address)` derives a stable internal id (`f"addr{address}"`).
  `jmri_ws.py`'s `acquire_throttle()`/`_reacquire_throttles()` extended to accept an
  optional `prefix` (targets a specific command station). `server.py` now runs
  `mcp.run_stdio_async()` inside an explicit `async def _run()` with a `try/finally` that
  closes the shared `JmriWsClient` on shutdown — since FastMCP has no lifecycle hooks of its
  own — so any held throttles are released JMRI-side. Also added `jmri-cli throttle
  acquire/release` for manual testing without an MCP client.
- Issue #9 (set_speed / stop / emergency_stop) implemented, live-verified, validated,
  committed (`1925f24`), pushed, closed. M2 continues with #10. Three new MCP tools in
  `tools.py`, all reusing the address-keyed throttle from #8. `_ensure_acquired()` acquires
  the throttle transparently
  if this connection doesn't hold it yet (JMRI otherwise rejects speed commands with
  "Throttles must be requested with an address.", verified live) — chosen over requiring an
  explicit prior `acquire_throttle` call, for voice UX ("speed up the 3" should work
  standalone). `set_speed` takes 0-100 and converts to JMRI's 0.0-1.0 scale (clamped);
  `stop` is speed 0.0; `emergency_stop` is speed -1.0 (JMRI's decoder emergency stop,
  verified live to be a distinct command from a controlled stop). `jmri_ws.py` gained
  `JmriWsClient.set_speed()`.
  - **Redesigned mid-implementation** after the user rejected a first fix that cached only
    this session's own commands (see verified facts above for the full no-op/push/cache
    design, and the "State can change outside the MCP session" hard rule this enshrined).
    `jmri_ws.py`'s `_dispatch()` now distinguishes a real reply from an unsolicited push via
    `_pending_throttle_id`, and updates the per-throttle cache from every throttle message
    seen. Fixed one bug surfaced only by live testing along the way (throttle registered in
    cache before `connect()` guaranteed the socket open → duplicate acquire on first
    connect → hung requests) — see verified facts above.
  - `fake_jmri` fixture in `tests/conftest.py` extended to track acquired throttle ids
    (rejecting speed commands on unacquired ones, matching real JMRI), simulate the silent
    no-op (no reply when requested speed/forward already matches), and push state changes to
    every connection holding an address, not just the one that sent the change — needed to
    unit-test the redesign instead of relying solely on live probing.
  - 9 new tests covering set_speed/stop/emergency_stop plus the no-op-skip, cross-connection
    push, and pending-request-not-corrupted-by-foreign-push cases. Full suite: 61 passed.
  - Live-verified against real JMRI (after the user power-cycled the DCC++ Raijin command
    station, which had gone to state UNKNOWN mid-session — unrelated to this code): bare
    acquire, speed, repeated stop, repeated emergency_stop, and release all complete in
    under ~1.5s each including on repeat/no-op calls (previously repeat `stop` hung ~5s to
    timeout). Also live-verified with two concurrent connections that a speed change on one
    is reflected in the other's cache via JMRI's push.
  - `docs/architecture.md` and `docs/cli.md` updated for the finalized design (new `throttle
    speed/stop/estop` CLI subcommands, live cache/push behavior). Re-presented to the user
    after the redesign (not treating the earlier #8 mix-up as a shortcut this time); user
    validated explicitly ("okay je valide") before commit.
  - **Also added `jmri-cli throttle sniff [-a ADDR...] [--show-pong]`** in the same commit:
    dumps every JMRI WebSocket message live (timestamped) until Ctrl-C, via a new
    `on_message` callback on `JmriWsClient` (fires for every message received, including
    replies to our own requests — unlike the pre-existing `on_event`, which only fires for
    unsolicited pushes/messages with nothing pending). `-a` acquires addresses first so
    their cross-connection pushes show up too. Polished after user feedback: `pong`
    messages hidden by default (`--show-pong` to reveal), and a throttle message's 69
    `F0`-`F68` fields collapsed to a single `functions_on` list (omitted if none are on).
    **Live-validated against real third-party traffic**: sniffing while the user drove a
    loco from JMRI's own PanelPro app (not `jmri-cli`) correctly showed PanelPro's pushes,
    including the discovery that PanelPro's "Stop" button sends `speed:-1.0` (JMRI's
    decoder e-stop) rather than a controlled `speed:0.0` — a PanelPro/JMRI convention
    unrelated to this project's own `stop` vs `emergency_stop` distinction, not a bug.
- Issue #10 (set_direction forward/reverse) implemented, live-verified, validated,
  committed (`f5c5119`), pushed, closed. M2 continues with #11. New `JmriWsClient.set_direction()` in `jmri_ws.py`,
  mirroring `set_speed()`'s cache-check-then-request/no-op-skip pattern exactly (same
  live-synced `_throttles[id]["forward"]` cache, same silent-no-op handling). New
  `set_direction` MCP tool in `tools.py` accepts case-insensitive `"forward"`/`"reverse"`
  strings and validates them honestly (`{"error": ...}` on anything else); reuses
  `_ensure_acquired()` from #9 so it auto-acquires like the other throttle tools.
  **Readable-value cleanup across the whole tool surface**: added `_direction_name()`
  helper and changed `_compact_throttle()` (used by `acquire_throttle`'s return value) to
  report `"direction": "forward"|"reverse"` instead of JMRI's raw `"forward": bool` — a
  deliberate breaking change to `acquire_throttle`'s MCP return shape, done so the LLM
  never has to interpret a raw boolean anywhere in this tool surface. Updated the one
  stale test assertion this broke (`test_acquire_throttle_returns_state`).
  - CLI parity: added `jmri-cli throttle direction <address> <forward|reverse>`, mirroring
    `throttle_speed`/`throttle_stop`/`throttle_estop`'s acquire-then-act/fresh-connection
    pattern. Live-verified: set reverse, repeat reverse (no-op, completed in ~0.3s not a
    ~5s timeout), set forward — all against the real DCC++ Raijin station.
  - 6 new tests: 3 client-level (`set_direction` basic/no-op-skip/cross-connection-push,
    mirroring #9's `set_speed` test trio) and 4 tool-level (auto-acquire, case-
    insensitivity, invalid-value rejection, error honesty). Full suite: 68 passed.
  - `docs/architecture.md` and `docs/cli.md` updated in the same pass: architecture notes
    `set_direction`'s reuse of the same cache/push design and the readable-value
    translation now shared by `acquire_throttle`'s output; cli.md gained the `direction`
    subcommand section and a note on why `acquire`'s own raw `forward=True/False` print
    differs from `direction`'s readable output.
  - Built applying [[feedback-llm-cli-checklist]] from the start (not reactively): the MCP
    tool's docstring explains decoder-relative forward/reverse semantics, the
    stop-before-reversing best practice, that direction is independent of speed, and the
    same no-op/external-change caveats as `set_speed`; the CLI subcommand and its live
    verification were done as part of this same implementation pass, not deferred.
- **Issue #11 (set_function F0-F28 + lights_on/lights_off) implemented, live-verified,
  AWAITING USER VALIDATION** (not committed yet): M2 (#7-#11) now fully implemented pending
  this last validation. New `JmriWsClient.set_function()` in `jmri_ws.py`, mirroring
  `set_speed()`/`set_direction()`'s cache-check-then-request/no-op-skip pattern, but keyed
  per function number rather than a single field: `_throttles[id]["functions"]` is a
  `{int: bool}` dict, populated by `_update_throttle_cache()` parsing any `F<n>` field off
  *any* throttle message seen (solicited or pushed), same as speed/forward. New
  `set_function` MCP tool in `tools.py` validates `0 <= function <= 28` locally before
  contacting JMRI (JMRI's own valid range); reuses `_ensure_acquired()` so it auto-acquires
  like the other throttle tools. `lights_on`/`lights_off` MCP tools are thin wrappers
  calling `set_function(address, 0, True/False)` directly as a plain Python call (verified
  the `@mcp.tool()` decorator returns the original undecorated function, so this works) —
  this project's answer to the legacy prototype's non-functional `lights_on`/`lights_off`
  (which never worked because the prototype had no persistent connection/acquire step at
  all; see `legacy/jmri_experimental.py`).
  - CLI parity: added `jmri-cli throttle function <address> <function> <on|off>` (local
    0-28 range validation before touching JMRI) and `lights-on`/`lights-off` shortcut
    subcommands, mirroring the acquire-then-act/fresh-connection pattern of the other
    throttle subcommands.
  - `tests/conftest.py`'s `fake_jmri` fixture extended: `loco_state` entries now carry a
    `functions` dict alongside `speed`/`forward`, and the no-op-diff logic generically
    handles any `F<n>` key in a request the same way it already handled `speed`/`forward`
    (silent no-op if unchanged, pushed to all holders of the address if changed).
  - 7 new tests: 3 client-level (`set_function` basic/no-op-skip/cross-connection-push) and
    4 tool-level (`set_function` auto-acquire, range rejection, error honesty, plus
    `lights_on`/`lights_off`). Full suite: 76 passed.
  - Live-verified against real JMRI (DCC++ Raijin, address 3): F1 on, repeated F1 on
    (no-op, ~0.27s not a hang), F1 off, F30 rejected locally without contacting JMRI,
    `lights-on`/`lights-off` (both CLI and MCP tool paths), and cross-connection push of an
    F3 toggle observed live via `jmri-cli throttle sniff -a 3` (showed up as
    `functions_on: ["F3"]` on toggle-on, and correctly omitted `functions_on` entirely on
    toggle-off — confirming sniff's existing compaction logic from #9 needed no changes for
    functions).
  - `docs/architecture.md` and `docs/cli.md` updated in the same pass: architecture notes
    the per-function cache shape and that `lights_on`/`lights_off` call `set_function`
    directly rather than through the MCP dispatcher; cli.md gained `function` and
    `lights-on`/`lights-off` subcommand sections.
  - Applied [[feedback-llm-cli-checklist]] from the start: `set_function`'s docstring
    explicitly tells the LLM F0's near-universal headlight convention isn't a protocol
    guarantee, that F1-F28 meanings are decoder/roster-specific and unknown to this tool
    (project has no roster-driven function-name lookup yet, that's M3), and to ask the user
    for an F-number rather than guess when they name a function by effect (e.g. "turn on
    the bell"); CLI subcommands were built and live-tested in the same pass, not deferred.
- `environment.yml` added (prior session): dedicated `jmri-mcp` conda env on Python 3.12,
  independent of `kira` (which stays on 3.11 — xiaozhi/Kira and Claude Desktop currently
  still run the `kira`-env copy of `jmri-mcp`/`jmri-cli`). Switching them to the 3.12 env
  means updating the hardcoded path in `claude_desktop_config.json` and Kira's
  `mcp_config.json` — not yet done, pending user decision.
- Kira integration (issue #18) already working end-to-end: `mcp_config.json` +
  `launch.sh` (`python mcp_pipe.py`, config mode) verified live against xiaozhi.
- Claude Desktop integration already working: `jmri` entry added to
  `claude_desktop_config.json` with an absolute path into the `kira` env. Note: its
  `jmri-mcp` subprocess has been observed to die silently with no error in the logs;
  fix is Cmd+Q + relaunch Claude Desktop (see `docs/llm-setup.md`).
- Project board is private (copied projects are private by default) — user hasn't asked
  to make it public, not a blocker.
