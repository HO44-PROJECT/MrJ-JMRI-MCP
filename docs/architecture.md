# Architecture

```
src/jmri_mcp/
├── config.py       # env vars: JMRI_URL (e.g. http://10.0.20.20:12080)
├── jmri_client.py  # async HTTP client for JMRI's JSON API (power, version, ...)
├── jmri_ws.py      # persistent WebSocket client (ws://<jmri>/json/) for throttles
├── tools.py        # MCP tools exposed to the LLM (list_systems, get_power, set_power,
│                   #   system_status, list_roster, find_locomotive,
│                   #   get_locomotive_functions, acquire_throttle, release_throttle,
│                   #   set_speed, stop, emergency_stop, set_direction, set_function,
│                   #   lights_on, lights_off)
├── cli.py          # jmri-cli: manual command-line tool, no MCP client needed
└── server.py       # FastMCP entry point (stdio; logging → stderr only)
```

M3 (roster) is now complete. More tools (turnouts, sensors) will land here
as later milestones are implemented — see the
[project board](https://github.com/orgs/HO44-PROJECT/projects/3).

## Two JMRI clients, two different shapes

JMRI exposes the same data over two transports, and this project uses both
for different reasons:

- **`jmri_client.py`** — plain async HTTP (`httpx`) against JMRI's REST-ish
  `/json/*` endpoints. One request, one response, no state kept between
  calls. Used for anything that doesn't need a throttle: power, version,
  roster, system discovery. `get_roster()` compacts JMRI's ~2 KB-per-entry
  `/json/roster` response (functionKeys, comments, icon paths, ...) down to
  name/address/road/model — the legacy prototype's roster bug was reading
  the envelope level instead of `entry["data"]`, which always came up
  empty; `_unwrap()` (shared with `get_systems()`) is what fixes that here.
- **`jmri_ws.py`** — a persistent WebSocket (`ws://<jmri>:12080/json/`).
  This exists for one reason: **a JMRI throttle is bound to the connection
  that acquired it**. HTTP can't hold a throttle open between requests, so
  cab control needs a long-lived connection — see `JmriWsClient` below.
  Wired into the MCP surface as `acquire_throttle`/`release_throttle` in
  `tools.py`.

Port 12021 (the raw "JSON server" TCP socket, not HTTP) is never used —
the original prototype tried to `POST` HTTP to it, which cannot work. Both
clients above talk only to port 12080 (the Web Server), just over two
different protocols on that same port.

## `JmriWsClient` design

- **Lazy connection.** Nothing connects at server startup; the first
  `request()`/`acquire_throttle()` call triggers `connect()`. This keeps
  the stdio server's boot instant even if JMRI is unreachable.
- **Auto-reconnect.** If the read loop sees the connection drop, it
  retries with exponential backoff (`_RECONNECT_DELAY` doubling up to
  `_MAX_RECONNECT_DELAY`) until it succeeds.
- **Keepalive.** JMRI's `hello` message on connect carries a
  `heartbeat` value in milliseconds; the client pings at half that
  interval so JMRI never times the connection out.
- **Throttle re-acquisition.** Acquired throttles are remembered
  (`_throttles`); after a reconnect, `_reacquire_throttles()` re-sends
  the same acquire message for each one before the connection is handed
  back to callers.
- **Serialized request/response.** JMRI's JSON protocol has no
  request-id field, and — verified live against a real JMRI 5.4.0 server —
  concurrent requests of *different* types can come back in an order that
  doesn't match send order, and `{"type":"error",...}` replies don't name
  the request that caused them. There is no reliable way to correlate
  concurrent, mixed-type requests. So `request()` takes a lock: only one
  request is ever in flight on the socket at a time, and the next message
  read off the socket is assumed to be its reply — **except** a `throttle`
  message whose `data["throttle"]` doesn't match the id the pending
  request actually asked about, which is routed as a push instead (see
  below). Messages that arrive with nothing pending, or a mismatched
  push, are handed to an optional `on_event` callback instead of being
  dropped.
- **Live throttle state cache, fed by pushes.** Verified live: JMRI (a)
  sends no reply at all when a requested speed/direction/function already
  equals the current value (a real no-op, not a dropped message — a naive
  "wait for one reply" design hangs until timeout), and (b) pushes every
  throttle state change to *all* connections holding that address, not
  just the one that requested it — so a loco's speed can change from a
  JMRI panel or another session and this client finds out the same way.
  `_dispatch()` updates `_throttles[id]["speed"/"forward"/"functions"]`
  from *every* throttle message it sees, solicited or not, before deciding
  whether that message is the answer to a pending request (`functions` is
  a `{int: bool}` dict keyed by function number, built by parsing any
  `F<n>` field in the message). `set_speed()`/`set_direction()`/
  `set_function()` all check that cache first and skip sending when the
  value's already current — safe specifically because the cache is kept
  live by JMRI's own pushes, not just by this client's own past commands.

See `CLAUDE.md`'s "Verified facts" section for the exact wire format
(hello/ping/pong/power/throttle payloads) captured from the user's JMRI.

## Roster: `list_roster` / `find_locomotive`

`list_roster` (in `tools.py`) returns `jmri_client.get_roster()`'s compact
form directly — for browsing. `find_locomotive` resolves one spoken/typed
name straight to a roster entry (and thus a DCC address) via
`jmri_client.resolve_roster_entry()`, mirroring `resolve_system()`'s
tolerant-match design (exact name, then unambiguous fragment) plus an
accent-insensitive fold (`_fold()`, via `unicodedata` NFKD-strip) so French
names like "Boite à Sel" match "boite a sel". An ambiguous or unknown name
returns an "error" explaining why (with the candidate list) rather than
guessing — the LLM is expected to ask the user to clarify.

`get_locomotive_functions` exposes the per-loco function labels the user
sets in JMRI's own roster editor (`functionKeys[].label`, `null` when
unset — most locos have none) via `jmri_client.get_roster_function_labels()`,
matching by exact roster name (resolved fuzzily first via
`resolve_roster_entry`, same as `find_locomotive`). Its docstring tells the
LLM to call it before `set_function` whenever the user names a function by
effect ("turn on the rear lights") rather than a number, and only fall
back to asking for an explicit F-number if that loco has no matching
label — this closes the gap `set_function`'s own docstring used to flag
("this project has no roster-driven function-name lookup yet").

## Throttle tool surface: DCC address as the only key

`acquire_throttle`/`release_throttle` (in `tools.py`) key everything on the
locomotive's **DCC address** — JMRI's own `throttle` id is never exposed to
the LLM. `_throttle_id(address)` derives a stable internal id
(`f"addr{address}"`) from the address, so the same loco always maps to the
same JMRI throttle across calls without the caller having to track an
opaque handle.

On server shutdown, `server.py` closes the shared `JmriWsClient`; JMRI
releases every throttle bound to that connection automatically, so no
explicit "release all" call is needed on exit.

`set_speed`/`stop`/`emergency_stop`/`set_direction`/`set_function` reuse
the same address-keyed throttle: if the address hasn't been acquired on
this connection yet, `_ensure_acquired` acquires it transparently first
(JMRI rejects speed/direction/function commands on a throttle id it's
never seen an acquire for). `set_speed` takes a 0-100 percentage from the
LLM and converts to JMRI's 0.0-1.0 scale; `stop` is speed 0.0,
`emergency_stop` is speed -1.0 (JMRI's decoder emergency stop, a distinct
command from a controlled stop). `set_speed`/`stop`/`emergency_stop` go
through `JmriWsClient.set_speed()`; `set_direction` goes through the
analogous `JmriWsClient.set_direction()`; `set_function` goes through
`JmriWsClient.set_function()` — all three check the live per-throttle
cache (`speed`/`forward`/`functions[n]` respectively) before sending using
the exact same no-op-skip logic, sharing the cache described in "Live
throttle state cache, fed by pushes" above. `set_direction` translates
JMRI's raw boolean `forward` field to/from the readable strings
`"forward"`/`"reverse"` at the tool boundary (`_direction_name()` in
`tools.py`), which is why `_compact_throttle()`'s output (used by
`acquire_throttle`) reports `direction` rather than JMRI's raw `forward`
too — one readable representation for the whole tool surface. `set_function`
validates `0 <= function <= 28` before sending anything (JMRI's own valid
range); `lights_on`/`lights_off` are thin wrappers calling
`set_function(address, 0, True/False)` directly as a plain Python call
(not through the MCP dispatcher) since F0 is the near-universal DCC
headlight convention.
