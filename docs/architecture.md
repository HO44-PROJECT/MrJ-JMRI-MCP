# Architecture

```
src/xiaozhi_wrapper/    # generic stdio<->WebSocket bridge for xiaozhi/Kira (no JMRI code)
├── __init__.py         #   main(); build_server_command(), connect_with_retry(), ...
├── __main__.py         #   enables `python -m xiaozhi_wrapper`
├── constants.py         #  env var names, mcp_config.json keys/transport types, backoff/timeout tunables
└── mcp_config.json      #  checked in as-is — nothing secret (same JMRI_URL published elsewhere)

src/jmri_mcp/
├── config/             # env vars: JMRI_URL (e.g. http://10.0.20.20:12080)
│   └── __init__.py
├── jmri_client/       # async HTTP client for JMRI's JSON API
│   ├── __init__.py    #   re-exports every public name (power/roster/light/turnout/sensor)
│   ├── _http.py        #  shared GET/POST plumbing, JmriError, envelope unwrap
│   ├── power.py        #  version, power-system discovery, power on/off, resolve_system
│   ├── roster.py        # roster listing, name resolution, function labels
│   ├── light.py         # layout light discovery, on/off, resolve_light
│   ├── turnout.py       # turnout discovery, closed/thrown, resolve_turnout
│   └── sensor.py        # sensor discovery (read-only), resolve_sensor
├── jmri_ws/            # persistent WebSocket client (ws://<jmri>/json/) for throttles
│   └── __init__.py
├── tools/             # MCP tools exposed to the LLM
│   ├── __init__.py    #   register(mcp): wires every domain module below
│   ├── _common.py      #  shared helpers (throttle_id, compact_*, ensure_acquired)
│   ├── power.py         # list_systems, get_power, set_power, system_status
│   ├── roster.py        # list_roster, find_locomotive, get_locomotive_functions
│   ├── throttle.py      # acquire/release_throttle, set_speed/stop/emergency_stop,
│   │                    #   set_direction, set_function, lights_on/lights_off
│   ├── light.py         # list_lights, get_light, set_light (layout/scenery lights,
│   │                    #   distinct from a locomotive's F0 headlight function)
│   ├── turnout.py       # list_turnouts, get_turnout, set_turnout
│   └── sensor.py        # list_sensors, get_sensor (read-only)
├── server/            # jmri-mcp: the MCP stdio server, no MCP client needed to build it
│   ├── __init__.py    #   main(); FastMCP wiring; logging → stderr only
│   └── __main__.py    #   enables `python -m jmri_mcp.server`
└── cli/               # jmri-cli: manual command-line tool, no MCP client needed
    ├── __init__.py    #   main(); package docstring has full usage examples
    ├── __main__.py    #   enables `python -m jmri_mcp.cli`
    ├── constants.py   #   shared constants (state names, id prefixes, ranges)
    ├── _common.py     #   cross-module helpers (cli_throttle_id)
    ├── _doc.py        #   top-level --help description text
    ├── power.py       #   power status/set, status (jmri_client)
    ├── roster.py      #   roster / roster find / roster functions (jmri_client)
    ├── throttle.py    #   throttle acquire/release/speed/.../sniff (jmri_ws)
    ├── light.py       #   light list/status/set (jmri_client)
    ├── turnout.py     #   turnout list/status/set (jmri_client)
    ├── sensor.py      #   sensor list/status (jmri_client, read-only)
    └── parser.py      #   build_parser(): wires the above into one CLI
```

Six domains — **power**, **roster**, **throttle**, **light**, **turnout**,
**sensor** — recur across the project and are split the same way everywhere
they get big enough to warrant it: `jmri_client/` (HTTP), `tools/` (MCP
surface), and `cli/` (manual CLI) each have their own
`power.py`/`roster.py`/`throttle.py`/`light.py`/`turnout.py`/`sensor.py`.
`jmri_ws/__init__.py` stays a single file within its package — it's one
cohesive unit of tightly-coupled state (a WebSocket connection's
request/reply/cache logic) with no natural seam to split along.

Every directory at the package root is a package (`__init__.py`, no
flat `.py` files at the root) — this project's two executables,
`jmri-mcp` and `jmri-cli`, are each their own package (`server/`,
`cli/`), both following the exact same shape: `main()` lives in
`__init__.py`, and a sibling `__main__.py` re-exports it so
`python -m jmri_mcp.<name>` also works. `config/` and `jmri_ws/` are
single-file packages (all their content lives in `__init__.py`) — they
have no `main()` and no natural seam to split into multiple files, but
still follow the "no bare `.py` at the root" rule. Everything except
`server/` and `cli/` is library code with no top-level side effects —
it can't be run standalone, only imported.

`src/` has two independent top-level packages: `jmri_mcp/` (this project's
actual purpose — the MCP server and its CLI) and `xiaozhi_wrapper/` (a
generic MCP stdio↔WebSocket bridge, JMRI-agnostic, for exposing `jmri-mcp`
— or any other stdio MCP server — to xiaozhi/Kira). They only meet at
`mcp_config.json`'s `"command": "jmri-mcp"`; `xiaozhi_wrapper` imports
nothing from `jmri_mcp`. It was ported into this repo from the separate
`kira` project on 2026-07-09, since `pyproject.toml`'s `[project.scripts]`
already coupled the two — see `src/xiaozhi_wrapper/__init__.py`'s docstring.

M3 (roster) is complete; M4 (layout) has all three cards implemented —
`light.py` (#17), `turnout.py` (#15), `sensor.py` (#16) — pending user
validation before being marked Done on the
[project board](https://github.com/orgs/HO44-PROJECT/projects/3).

## Two JMRI clients, two different shapes

JMRI exposes the same data over two transports, and this project uses both
for different reasons:

- **`jmri_client/`** — plain async HTTP (`httpx`) against JMRI's REST-ish
  `/json/*` endpoints. One request, one response, no state kept between
  calls. Used for anything that doesn't need a throttle: power, version,
  roster, system discovery. `get_roster()` compacts JMRI's ~2 KB-per-entry
  `/json/roster` response (functionKeys, comments, icon paths, ...) down to
  name/address/road/model — the legacy prototype's roster bug was reading
  the envelope level instead of `entry["data"]`, which always came up
  empty; `_unwrap()` (shared with `get_systems()`) is what fixes that here.
- **`jmri_ws/`** — a persistent WebSocket (`ws://<jmri>:12080/json/`).
  This exists for one reason: **a JMRI throttle is bound to the connection
  that acquired it**. HTTP can't hold a throttle open between requests, so
  cab control needs a long-lived connection — see `JmriWsClient` below.
  Wired into the MCP surface as `acquire_throttle`/`release_throttle` in
  `tools/throttle.py`.

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

`list_roster` (in `tools/roster.py`) returns `jmri_client.get_roster()`'s
compact form directly — for browsing. `find_locomotive` resolves one
spoken/typed name straight to a roster entry (and thus a DCC address) via
`jmri_client.resolve_roster_entry()` (defined in `jmri_client/roster.py`),
mirroring `resolve_system()`'s (`jmri_client/power.py`) tolerant-match
design (exact name, then unambiguous fragment) plus an accent-insensitive
fold (`_fold()`, via `unicodedata` NFKD-strip) so French names like "Boite
à Sel" match "boite a sel". An ambiguous or unknown name returns an
"error" explaining why (with the candidate list) rather than guessing —
the LLM is expected to ask the user to clarify.

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

## Layout lights: `list_lights` / `get_light` / `set_light`

`jmri_client/light.py` mirrors `power.py`'s shape almost exactly: JMRI's
`/json/lights` (list) and `/json/light/<name>` (single get/set) are the
same REST-ish pattern as `/json/power`, with `state` 2=ON/4=OFF (JMRI can
also report 0=UNKNOWN or 8=INCONSISTENT for a feedback-wired light — see
`LIGHT_STATE_NAMES`). `set_light()` re-reads via `get_lights()` after the
POST and reports `confirmed` honestly, same contract as `set_power()`.

These are JMRI `light` *objects* — layout/scenery lighting (depot, street,
signal lamps, ...) wired up as their own devices in JMRI, keyed by JMRI
system name (e.g. `"IL1"`) — **not** a locomotive's F0 headlight function
(`tools/throttle.py`'s `lights_on`/`lights_off`, keyed by DCC address).
`resolve_light()` (in `jmri_client/light.py`) matches a user-supplied name
tolerantly like `resolve_system()`/`resolve_roster_entry()`: case-
insensitive, exact match against either JMRI's system name or its
user-friendly `userName` first, then an unambiguous substring fragment of
`userName`. Unlike `resolve_system()` there's no default fallback — a
light must be named, there's no single "the" light. `compact_light()` (in
`tools/_common.py`) prefers `userName` over the raw system name for
display/matching, falling back to the system name only if the user never
labeled the light in JMRI. Both MCP tool docstrings (`get_light`/
`set_light`) and the light-domain modules explicitly flag this
scenery-vs-headlight distinction so the LLM asks itself "did the user name
a place or a locomotive?" before picking a tool.

## Turnouts: `list_turnouts` / `get_turnout` / `set_turnout`

`jmri_client/turnout.py` is a structural copy of `light.py`: JMRI's
`/json/turnouts` (list) and `/json/turnout/<name>` (single get/set), state
2=CLOSED/4=THROWN (0=UNKNOWN, 8=INCONSISTENT for a feedback-wired turnout
that hasn't settled — see `TURNOUT_STATE_NAMES`). `set_turnout()` re-reads
via `get_turnouts()` after the POST and reports `confirmed` honestly, same
contract as `set_power()`/`set_light()`. `resolve_turnout()` uses the same
tolerant case-insensitive exact-then-fragment match as `resolve_light()`,
with no default fallback (a turnout must be named).

The tool surface deliberately uses JMRI/PanelPro's own **CLOSED/THROWN**
vocabulary rather than track terminology like "open"/"closed", which would
be ambiguous about which of the two routes is which — both the MCP tool
docstrings and `resolve_turnout()`'s design note this explicitly, so the
LLM's own language when talking to the user stays consistent with what
JMRI/PanelPro shows. `set_turnout` writes to JMRI and can move a physical
turnout motor on the real layout, so — like the throttle tools — its
confirmation is never assumed; a turnout with a feedback sensor wired up
can fail to settle to the commanded position, which shows up as
`confirmed: false` rather than being silently reported as success.

## Sensors: `list_sensors` / `get_sensor` (read-only)

`jmri_client/sensor.py` mirrors `light.py`/`turnout.py`'s read side only —
`/json/sensors` (list) and `/json/sensor/<name>` (single get), state
2=ACTIVE/4=INACTIVE (0=UNKNOWN, 8=INCONSISTENT — see `SENSOR_STATE_NAMES`).
There is deliberately **no `set_sensor`**, in either `jmri_client/`,
`tools/`, or `cli/`: a sensor reports real-world state JMRI detects from
its own hardware inputs (block occupancy, turnout motor feedback, a
clock-running flag like `ISCLOCKRUNNING`), not a command this project
should ever issue — writing to one would be lying to JMRI about the
layout's physical state. `resolve_sensor()` uses the same tolerant match as
`resolve_light()`/`resolve_turnout()`.

Confirmed live against the user's real JMRI: turnout motor feedback shows
up as its own sensor entries (e.g. `OS37`-`OS47`), separate from the
`sensor` field nested inside each `get_turnouts()` entry — `list_sensors`
surfaces both a turnout's own feedback sensor and every other block/utility
sensor in one flat list, since JMRI itself treats them as the same kind of
object.

Card #16 originally suggested a WebSocket listener might be needed to catch
spontaneous sensor updates, but live testing showed a one-shot HTTP GET
already returns full current state synchronously (same as power/roster/
light) — no listener needed for a stateless list/get tool, so this domain
follows the simpler `jmri_client/` (one-shot HTTP) pattern rather than
`jmri_ws/`'s persistent-connection one.

## Throttle tool surface: DCC address as the only key

`acquire_throttle`/`release_throttle` (in `tools/throttle.py`) key
everything on the locomotive's **DCC address** — JMRI's own `throttle` id
is never exposed to the LLM. `throttle_id(address)` (in `tools/_common.py`,
shared by every tool in the throttle/power/roster split) derives a stable
internal id (`f"addr{address}"`) from the address, so the same loco always
maps to the same JMRI throttle across calls without the caller having to
track an opaque handle.

On server shutdown, `server.py` closes the shared `JmriWsClient`; JMRI
releases every throttle bound to that connection automatically, so no
explicit "release all" call is needed on exit.

`set_speed`/`stop`/`emergency_stop`/`set_direction`/`set_function` reuse
the same address-keyed throttle: if the address hasn't been acquired on
this connection yet, `tools/_common.py`'s `ensure_acquired` acquires it
transparently first (JMRI rejects speed/direction/function commands on a
throttle id it's never seen an acquire for). `set_speed` takes a 0-100
percentage from the LLM and converts to JMRI's 0.0-1.0 scale; `stop` is
speed 0.0, `emergency_stop` is speed -1.0 (JMRI's decoder emergency stop, a
distinct command from a controlled stop). `set_speed`/`stop`/
`emergency_stop` go through `JmriWsClient.set_speed()`; `set_direction`
goes through the analogous `JmriWsClient.set_direction()`; `set_function`
goes through `JmriWsClient.set_function()` — all three check the live
per-throttle cache (`speed`/`forward`/`functions[n]` respectively) before
sending using the exact same no-op-skip logic, sharing the cache described
in "Live throttle state cache, fed by pushes" above. `set_direction`
translates JMRI's raw boolean `forward` field to/from the readable strings
`"forward"`/`"reverse"` at the tool boundary (`direction_name()` in
`tools/_common.py`), which is why `compact_throttle()`'s output (used by
`acquire_throttle`) reports `direction` rather than JMRI's raw `forward`
too — one readable representation for the whole tool surface. `set_function`
validates `0 <= function <= 28` before sending anything (JMRI's own valid
range); `lights_on`/`lights_off` are thin wrappers calling
`set_function(address, 0, True/False)` directly as a plain Python call
(not through the MCP dispatcher) since F0 is the near-universal DCC
headlight convention.
