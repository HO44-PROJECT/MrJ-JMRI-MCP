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
  `{"type":"throttle","data":{"name":"<id>","address":<n>}}` on the WebSocket, then send
  speed/`F<n>` on the SAME connection; JMRI releases the throttle when the connection closes.

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
3. Present the result to the user; **wait for their validation**.
4. On validation: commit with `Closes #N` in the message, push, move the card to **Done**.

## Current state (end of session 2026-07-08)

- Scaffold pushed (README, pyproject with `jmri-mcp` entry point, deps mcp/httpx/websockets).
- **Issue #1 implemented, smoke-tested, AWAITING USER VALIDATION** (not committed yet):
  `src/jmri_mcp/server.py` (FastMCP stdio, stderr-only logging) + `__init__.py` (version).
  Smoke test passed: initialize + tools/list over stdio, stdout pure, logs on stderr.
- Next: on validation, commit/close #1, then #2 (`JMRI_URL` env config), then #3–6.
- Kira integration target (issue #18): kira's `mcp_config.json` gets
  `{"mcpServers": {"jmri": {"command": "jmri-mcp", "env": {"JMRI_URL": "http://10.0.20.20:12080"}}}}`
  and `launch.sh` becomes `python mcp_pipe.py` (config mode).
- Manual step still pending on the user side: make project board public if desired
  (copied projects are private by default).
