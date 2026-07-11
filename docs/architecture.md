# Architecture

```
src/xiaozhi_wrapper/    # generic stdio<->WebSocket bridge for xiaozhi/Kira (no JMRI code)
├── __init__.py         #   main(); build_server_command(), connect_with_retry(), ...
├── __main__.py         #   enables `python -m xiaozhi_wrapper`
├── constants.py         #  env var names, mcp_config.json keys/transport types, backoff/timeout tunables
└── mcp_config.json      #  checked in as-is — no env block, JMRI_URL comes from the launching shell

src/jmri_mcp/
├── config/             # env vars: JMRI_URL (e.g. http://localhost:12080)
│   └── __init__.py
├── constants/          # dedicated modules for every literal used more than once
│   ├── __init__.py    #   re-exports protocol/endpoints/client_tuning/cli
│   ├── protocol.py     #  JMRI JSON field names + WS message-type strings
│   ├── endpoints.py    #  JMRI REST path templates (e.g. TURNOUT = "/json/turnout/{name}")
│   ├── client_tuning.py #  HTTP/WS timeouts, reconnect delays, ramp step rate
│   └── cli.py          #  *_STATE_NAMES dicts, CLI id prefixes/ranges, SORT_INDICATOR
├── jmri_errors.py      # shared JmriError(code, **kwargs), raised by jmri_client AND jmri_ws
├── i18n/               # hand-rolled i18n: dotted-key lookup against per-language JSON
│   ├── __init__.py    #   lookup(lang, key, **kwargs), t(key, **kwargs), active_lang()
│   ├── en.json          # errors.*/kinds.* message templates (English, default)
│   └── fr.json          # same keys, French
├── jmri_client/       # async HTTP client for JMRI's JSON API
│   ├── __init__.py    #   re-exports every public name (power/roster/light/turnout/sensor/signal)
│   ├── _http.py        #  shared GET/POST plumbing, JmriError re-export, envelope unwrap
│   ├── power.py        #  version, power-system discovery, power on/off,
│   │                   #  power_off_all/power_on_all, resolve_system
│   ├── roster.py        # roster listing, name resolution, function labels
│   ├── light.py         # layout light discovery, on/off, resolve_light
│   ├── turnout.py       # turnout discovery, closed/thrown, resolve_turnout
│   ├── sensor.py        # sensor discovery (read-only), resolve_sensor
│   └── signal.py        # signal mast discovery, aspect set, resolve_signal
│   │                    #   (signalMast only, not signalHead — see file docstring)
├── jmri_ws/            # persistent WebSocket client (ws://<jmri>/json/) for throttles
│   ├── __init__.py     #   incl. emergency_stop_all() (every acquired throttle at once)
│   └── ramp.py          #  ramp_speed/execute_speed_change: shared ramp state
│                        #   machine, used by cli/throttle.py, cli/shell.py, and
│                        #   tools/throttle.py's set_speed_ramped
├── tools/             # MCP tools exposed to the LLM
│   ├── __init__.py    #   register(mcp): wires every domain module below
│   ├── _common.py      #  shared helpers (throttle_id, compact_*, ensure_acquired)
│   ├── power.py         # list_systems, get_power, set_power, power_off_all,
│   │                    #   power_on_all, system_status
│   ├── roster.py        # list_roster, find_locomotive, get_locomotive_functions
│   ├── throttle.py      # acquire/release_throttle, set_speed/set_speed_ramped/
│   │                    #   stop/emergency_stop, emergency_stop_all, set_direction,
│   │                    #   set_function, lights_on/lights_off
│   ├── light.py         # list_lights, get_light, set_light (layout/scenery lights,
│   │                    #   distinct from a locomotive's F0 headlight function)
│   ├── turnout.py       # list_turnouts, get_turnout, set_turnout
│   ├── sensor.py        # list_sensors, get_sensor (read-only)
│   ├── signal.py        # list_signals, get_signal, set_signal (signalMast only)
│   └── mode.py           # set_executor_mode, get_executor_mode (concise/
│   │                    #   no-narration response style, no JMRI I/O)
├── server/            # jmri-mcp: the MCP stdio server, no MCP client needed to build it
│   ├── __init__.py    #   main(); FastMCP wiring; logging → stderr only
│   └── __main__.py    #   enables `python -m jmri_mcp.server`
└── cli/               # jmri-cli: manual command-line tool, no MCP client needed
    ├── __init__.py    #   main(); bare launches shell.py, help/-h/--help show
    │                  #     banner.py's welcome banner, everything else runs clean
    ├── __main__.py    #   enables `python -m jmri_mcp.cli`
    ├── banner.py      #   the welcome banner (name, version, repo link, command list)
    ├── _common.py     #   cross-module helpers (cli_throttle_id)
    ├── _doc.py        #   GROUP_HELP: short one-liner per top-level command group
    ├── _match.py      #   find_regex/find_glob: shared matching for findr/findg leaves
    ├── state.py       #   local throttle-state cache (~/.jmri-cli/throttle_state.json)
    ├── power.py       #   power [status|on|off|get|find|findr|findg|default] (jmri_client)
    ├── roster.py      #   roster [list|find|findr|findg|functions] (jmri_client)
    ├── throttle.py    #   throttle [list|find|findr|findg|acquire|release|speed|
    │                  #     stop|estop|forward|reverse|on|off|sniff] (jmri_ws +
    │                  #     state.py; find/findr/findg are read-only, roster+cache only)
    ├── light.py       #   light [list|find|findr|findg|on|off] (jmri_client)
    ├── turnout.py     #   turnout [list|find|findr|findg|close|throw] (jmri_client)
    ├── sensor.py      #   sensor [list|find|findr|findg|status] (jmri_client, read-only)
    ├── signal.py      #   signal [list|status|find|findr|findg|set] (jmri_client, signalMast only)
    └── parser.py      #   build_parser(): wires the above into one CLI, incl. the
                        #     bare-group-default and verb-elevation patterns (see docs/cli.md)
```

Seven domains — **power**, **roster**, **throttle**, **light**, **turnout**,
**sensor**, **signal** — recur across the project and are split the same way
everywhere they get big enough to warrant it: `jmri_client/` (HTTP),
`tools/` (MCP surface), and `cli/` (manual CLI) each have their own
`power.py`/`roster.py`/`throttle.py`/`light.py`/`turnout.py`/`sensor.py`/`signal.py`.
`jmri_ws/__init__.py` stays a single file within its package — it's one
cohesive unit of tightly-coupled state (a WebSocket connection's
request/reply/cache logic) with no natural seam to split along.
`tools/mode.py` is the one module with no `jmri_client`/`jmri_ws`
counterpart and no `cli/` equivalent — it holds no JMRI state at all (see
"Executor mode" below), so there's nothing for a one-shot CLI process to
usefully exercise (its whole point is a flag that persists across tool
calls within one long-lived MCP session).

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

M3 (roster) and M4 (layout — `light.py` #17, `turnout.py` #15, `sensor.py`
#16) are both complete and closed on the
[project board](https://github.com/orgs/HO44-PROJECT/projects/3). Four
"whole-layout" features tracked together under issue #23
(`emergency_stop_all`, `power_off_all`, `power_on_all`, executor mode — see
their own sections below) have been implemented on top of that. Signal
masts (`signal.py` #26) were added afterward as a standalone card, once the
maintainer had a real signalMast configured on their layout to design
against.

## `constants/`: every repeated literal in one place, organized by layer

Any magic string or number used more than once lives in `src/jmri_mcp/constants/`,
never re-typed at each call site. Four dedicated **modules** (not `class X:` bodies —
module-qualified access like `endpoints.TURNOUT` gives the same namespacing with less
boilerplate), split along the same layer boundary as the rest of the tree:

- **`protocol.py`** — JMRI JSON field-name keys (`FIELD_STATE`, `FIELD_THROTTLE`,
  `FIELD_SPEED`, `FIELD_FORWARD`, ...) and WebSocket message-type strings
  (`MSG_TYPE_THROTTLE`, `MSG_TYPE_PING`, `MSG_TYPE_PONG`, `MSG_TYPE_ERROR`). Shared by
  `jmri_client` (HTTP) and `jmri_ws` (WebSocket), which speak the same JMRI JSON object
  shapes over two different transports.
- **`endpoints.py`** — JMRI REST path templates, e.g. `TURNOUT = "/json/turnout/{name}"`;
  call sites do `endpoints.TURNOUT.format(name=name)` instead of an inline f-string.
- **`client_tuning.py`** — HTTP/WS timeouts, the POST-recheck delay, WS reconnect
  backoff bounds, the default heartbeat, and `RAMP_STEPS_PER_SECOND` (imported by
  `jmri_ws/ramp.py`, not defined there).
- **`cli.py`** — the `POWER_STATE_NAMES`/`LIGHT_STATE_NAMES`/`TURNOUT_STATE_NAMES`/
  `SENSOR_STATE_NAMES` dicts (the single source both `tools/_common.py` and every
  `cli/*.py` module import, rather than each redefining them), CLI throttle-id prefixes,
  function/speed ranges, and `SORT_INDICATOR` (` ▼`, appended to a sorted column's header
  at the print call site — never baked into the header string itself).

`cli/light.py`, `cli/power.py`, and `cli/turnout.py`'s `_*_set()` helpers reconstruct
the reported state name via `STATE_NAMES[ON_VALUE if flag else OFF_VALUE]` — reading the
same dict `_row()` uses to render table rows — rather than a second, independent
`"ON" if flag else "OFF"`-style string literal that could drift out of sync with it.

## `jmri_errors.py` + `i18n/`: structured errors, hand-rolled translation

No user-facing message is written as a hardcoded string in `jmri_client`/`jmri_ws`
anymore. Both raise a single shared `JmriError(code, **kwargs)` (`src/jmri_mcp/jmri_errors.py`)
instead of each defining its own exception class with a baked-in English f-string —
`jmri_client/_http.py` and `jmri_ws/__init__.py` used to each define an identical local
`JmriError`, which meant `cli/throttle.py`/`cli/shell.py`/`tools/throttle.py` had to
import one of them aliased as `JmriWsError` just to catch both; a single shared class
collapses that back to one `except JmriError`.

`code` is a short machine-readable key (`"unknown_entity"`, `"vanished_after_post"`,
`"ws_connect_failed"`, ...) resolved at message-render time against
`src/jmri_mcp/i18n/en.json` / `fr.json` — not gettext or an external i18n library, a
small dotted-key JSON lookup (`i18n.lookup(lang, "errors.<code>", **kwargs)`) using
`str.format()` interpolation (chosen over `%`-style because several templates need
`{query!r}`-style conversion flags). `JmriError.__str__` always renders English
(`lookup("en", ...)`) regardless of the active language — logging/`str(exc)` call sites
stay English/developer-facing, per this project's existing English-for-code convention;
only `cli`/`tools` translate at the catch site via `i18n.t()` (against
`active_lang()`, driven by the `JMRI_MCP_LANG` env var, default `"en"`).

Domain errors that repeat the same shape across turnout/light/sensor/signal/roster/system
(`"Unknown X 'query'. Available: ..."`, `"Ambiguous X 'query': matches ..."`, `"JMRI
reports no Xs"`, ...) share one code each (`unknown_entity`, `ambiguous_entity`,
`none_available`, `no_query_given`, `vanished_after_post`) parameterized by a `kind=`
kwarg (e.g. `kind="turnout"`) instead of being restated per domain. Each language's JSON
carries a `kinds` table mapping a kind to its singular/plural/capitalized forms
(`{kind}`/`{kind_plural}`/`{Kind}`), resolved by `i18n.lookup()` before the final
`str.format(**kwargs)` — this is what lets French render "aiguillage"/"aiguillages" for
`kind="turnout"` instead of a raw English word leaking into a translated sentence.

`i18n.lookup()` never raises: a missing translation falls back language → `"en"` → the
raw key itself, so a gap in `fr.json` degrades to readable English rather than crashing,
and a genuinely missing key is visible/greppable in output instead of silently swallowed.

LLM-facing instruction strings (`server/__init__.py`'s server instructions,
`tools/mode.py`'s executor-mode strings) and every docstring are **deliberately out of
scope** for i18n — they're consumed by the LLM host, not read directly by a human, and
`tools/mode.py` specifically depends on intentional bilingual FR/EN trigger vocabulary
that a translation table would collapse.

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
2=CLOSED/4=THROWN/0=UNKNOWN/8=INCONSISTENT (see `TURNOUT_STATE_NAMES`).
`set_turnout()` re-reads via `get_turnouts()` after the POST and reports
`confirmed` honestly, same contract as `set_power()`/`set_light()`.
`resolve_turnout()` uses the same tolerant case-insensitive exact-then-
fragment match as `resolve_light()`, with no default fallback (a turnout
must be named).

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

**INCONSISTENT is not always transient.** Verified live against the user's
own layout (2026-07-11): a turnout with no wired feedback sensor reported
`state: 8` (INCONSISTENT) persistently, at rest, with no command in
flight — JMRI has no way to confirm that turnout's real position, so it
reports INCONSISTENT as a permanent steady state, not a settling delay.
JMRI's own `feedbackMode` field is **not** a reliable way to detect this on
its own — a counter-example was found live where a turnout configured
`feedbackMode: 2` (DIRECT/no-feedback) still carried a genuine `sensor`
object. `tools/_common.py`'s `compact_turnout()` instead derives a
`has_feedback_sensor` boolean directly from whether JMRI's `sensor` array
(2 elements, `null` if unwired) has any non-null entry, and exposes it
alongside `state` on `list_turnouts`/`get_turnout`/`set_turnout`. Every
turnout tool's docstring tells the LLM explicitly: when
`has_feedback_sensor` is false, INCONSISTENT is expected/normal and must
not be reported to the user as an anomaly; it's only worth flagging when
`has_feedback_sensor` is true. `cli/turnout.py` mirrors this with a
"Feedback" (yes/no) column on `list`/`find`/`findr`/`findg`, and
`turnout close`/`throw`'s unconfirmed-state warning adds an extra note
when the unconfirmed turnout(s) are sensorless, for the same reason.

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

## Signal masts: `list_signals` / `get_signal` / `set_signal` (#26)

`jmri_client/signal.py` is a structural copy of `turnout.py`: JMRI's
`/json/signalMasts` (list) and `/json/signalMast/<name>` (single get/set).
Unlike turnout/light/sensor, a mast's state is not a small numeric enum —
it's an **aspect name** (a free-form string like `"Hp0"`/`"Hp1"`/`"Hp2"`),
whose valid vocabulary is defined by whichever signal system (e.g.
`DB-HV-1969`) the mast was configured with in PanelPro. JMRI does not
expose that vocabulary anywhere in its JSON API (verified live: no
`/json/signalSystem`, `/json/signalMastAspects`, or per-mast aspect list
exists), so `set_signal()` does not validate aspect names locally — same
"accept it, then let re-read confirm or refute" honesty contract as
`set_power()`/`set_turnout()`/`set_light()`, since a bad guess would be
worse than an honest "not confirmed." JMRI *does* validate server-side,
though: reading JMRI's own `JsonSignalMastHttpService.doPost()` source
confirmed `SignalMast.getValidAspects()` exists internally and an unknown
aspect name raises a proper 400 `JsonException` — surfaced here as a
`JmriError`/tool `"error"` rather than a silent non-confirm. It's only the
*list* of valid aspects that's unreachable over JSON, not validation
itself.

The POST body's JSON key is `"state"`, not `"aspect"` — an easy trap,
since `"aspect"` is what every GET response and this project's own field
names call it. `doPost()` specifically reads `data.path(STATE)`
(`STATE == "state"`). Sending `"aspect"` is not rejected — JMRI just never
looks at it, so the whole aspect-setting branch is skipped and a 200 with
unchanged data comes back. See the `set_signal` fix note below; this was
caught live, not in review.

**signalHead is deliberately not covered.** JMRI has two signal object
types: `signalHead` (a single physical lamp, states like RED/YELLOW/GREEN)
and `signalMast` (the higher-level object built from one or more heads,
speaking named aspects). Confirmed with the maintainer (2026-07-10): their
layout has no `signalHead` objects in JMRI at all — their DB-1969 masts are
physically driven by a custom ESP32 that decodes the raw DCC accessory
frame JMRI sends for the mast's aspect and does its own aspect→LED/fading
translation entirely in firmware, so there's no JMRI-side head object to
expose. `signalMast` is also the level PanelPro users actually name and
interact with directly, so it's the only one this project's tool surface
covers; revisit only if a setup with real `signalHead` objects comes up.

`resolve_signal()` uses the same tolerant case-insensitive exact-then-
fragment match as `resolve_turnout()`/`resolve_light()`, matching either
the system name or `userName` exactly, then falling back to an unambiguous
*fragment of `userName` only* (not the system name) — same limitation
`resolve_turnout()` already has. This is more noticeable for signal masts
in practice: JMRI auto-generates long system names like
`ZF$dsm:DB-HV-1969:block(31)` for DCC-driven masts, and unlike turnouts
these are commonly left without a `userName` set in PanelPro (verified live
against the maintainer's own mast, which has `userName: null`) — so a
fragment like `"block 31"` won't resolve; only the exact full system name
or an explicit `userName` set in PanelPro will. Worth setting a `userName`
per mast in PanelPro if fragment matching is wanted.

Live-verified against the user's real JMRI: `list_signals`/`get_signal`
correctly read the one configured mast (`ZF$dsm:DB-HV-1969:block(31)`,
aspect `Hp1`). The first live write test of `set_signal` (user-authorized,
one write) requesting `Hp0` completed with no HTTP error, but the re-read
showed the aspect unchanged at `Hp1` — reported honestly as
`confirmed: false` rather than a false success, but the underlying cause
turned out to be a real bug in this project, not the mast/ESP32: the POST
body sent `{"name": ..., "aspect": ...}`, and JMRI's server-side handler
only ever reads `"state"` (see above), so the request was silently a
no-op from JMRI's point of view every time. Fixed by sending `"state"`
instead; a regression test now asserts the POST body's JSON key so this
exact bug can't reappear silently. Re-verified live against the real
"bloc31" mast (the maintainer's own `userName`, set after this bug was
first reported) — requesting `Hp0` now confirms correctly.

## CLI UX: banner, per-leaf examples, and the bare-group/verb-elevation pattern

`jmri-cli`'s command surface went through two redesigns driven directly by
maintainer feedback on the real terminal output, not speculative design:

**Welcome banner + per-leaf epilogs** (`cli/banner.py`, `cli/__init__.py`,
`cli/_doc.py`'s `GROUP_HELP`). Bare `jmri-cli`, `jmri-cli -h`, and
`jmri-cli --help` all print a byte-identical, non-technical welcome banner
(name, version via `importlib.metadata`, repo link, one-line purpose,
command list) instead of argparse's default technical help — no
implementation detail (`JMRI_URL`, "no MCP client" framing) belongs there.
Each top-level group gets a short, inviting one-liner in `GROUP_HELP`
instead of a dry description. There used to be a separate `jmri-cli
examples` subcommand collecting every runnable example in one place; it was
removed in favor of putting each leaf subcommand's own example directly in
its `-h` epilog (`parser.py`'s `_leaf()` helper sets `epilog=f"example:\n
{example}"` with `RawDescriptionHelpFormatter` so it's never auto-rewrapped)
— `jmri-cli <group> <leaf> -h` is now self-sufficient, and
`tests/test_cli.py::test_every_leaf_subcommand_epilog_example_is_parseable`
re-parses every printed example against the real parser, so a
renamed/removed subcommand that isn't updated here fails the test suite
instead of silently going stale.

**Bare-group-default + verb-elevation** (`parser.py`'s `_group()` helper).
A `jmri-cli roster` terminal transcript the maintainer pasted (missing
header, unaligned columns) triggered a broader pass: every list-style
command now renders through `tabulate` with explicit headers, and every
command group was audited for two consistency rules stated explicitly by
the maintainer ("qu'en déduis-tu en terme de bonne pratique et de
cohérence?"):

- **Bare group = smart default**, not an argparse "required" error.
  `subparsers.add_subparsers(dest=..., required=False)` plus
  `group_cmd.set_defaults(func=default_func)` lets `jmri-cli power` run
  `power_status` directly. Applied to every group: `power`→`status`,
  `roster`→`list`, `throttle`→`list`, `light`/`turnout`/`sensor`/`signal`→
  their own `list`.
- **Verb elevation**: a leaf whose own argument was really a fixed choice
  of state values (`power set <system> <on|off>`, `throttle direction
  <addr> <forward|reverse>`, `throttle lights-on`/`lights-off`) is
  rewritten so the state value becomes the subcommand name itself, and the
  target becomes an *optional* fuzzy positional defaulting to "every
  member of the group" — `power on [system]`, `power off [system]`
  (replacing `power set`/`stop-all`/`start-all` entirely, not aliasing
  them), `throttle forward <loco>`/`throttle reverse <loco>` (no more
  shared `direction` leaf), `throttle on <loco> [function]`/`throttle off
  <loco> [function]` (replacing the F0-assuming `lights-on`/`lights-off`
  — no function number is ever a protocol guarantee for "lights", see
  `throttle.py`'s `_resolve_function_numbers`), `light on
  [name]`/`light off [name]`, `turnout closed [name]`/`turnout thrown
  [name]` (both replacing their old `status`/`set <name> <state>` shape).
  `throttle forward`/`reverse` are wired via `functools.partial(
  throttle.throttle_direction, forward=True/False)` in `parser.py` so both
  leaves share one implementation while still being independent
  subcommands, not a shared one with a choice argument.

`throttle`'s bare-default and `speed <loco>` (value omitted = read) needed
one more piece to actually work: a CLI invocation is a fresh
acquire-act-close WebSocket connection every time (see below), so there is
no live JMRI state left to query back between two separate `jmri-cli
throttle` calls. `cli/state.py` is a small local JSON cache
(`~/.jmri-cli/throttle_state.json`, keyed by DCC address) that every
throttle-touching command writes to and that `throttle list`/`speed`
(no value)/`stop` (no address) read from — a convenience cache the CLI
keeps for itself, not a live source of truth (see `docs/cli.md` for the
staleness caveat). `throttle on`/`off` with no function number resolves
against the loco's roster-set function labels
(`get_roster_function_labels`, from M3) and raises an explicit error
rather than falling back to F0 if the loco has none labeled — a
deliberate maintainer decision (over a silent F0 default), consistent with
the project's existing stance that F-number meaning is decoder/roster-
specific, never a protocol guarantee.

## CLI UX: interactive shell, ramping, and the `client=` kwarg pattern

**Persistence model, summarized.** The CLI has exactly two ways to run a
throttle command, and they hold a connection open in different ways —
there is no thread and no subprocess involved in either; both are plain
single-threaded `asyncio`, one event loop doing cooperative multitasking:

- **One-shot** (`jmri-cli throttle speed 3 60 --hold 60`): the process
  itself blocks. `_execute_speed_change`'s hold step does
  `await asyncio.sleep(hold_seconds)` on the *same* connection that just
  set the speed, so the connection — and therefore the throttle JMRI
  granted on it — stays alive for the full 60 seconds. Only after the hold
  ends (and the auto-stop below runs) does the function return, `_client_scope`
  close the connection, and the process exit. Control is **not** returned to
  the shell/terminal until all of that has happened — this is required, not
  a limitation: JMRI releases a throttle the instant its owning connection
  closes (see below), so a one-shot command that returned early would leave
  nothing holding the throttle and the locomotive would stop mid-command.
- **Shell** (`jmri-cli` bare, then `speed 3 60` typed at the prompt): the
  shell's `JmriWsClient` was already opened once when the shell started and
  outlives every individual command — so sending a speed command doesn't
  need to block on anything to keep the locomotive moving. `throttle_speed`
  returns as soon as JMRI confirms the speed change, and control comes back
  to the `jmri-cli>` prompt immediately, while the locomotive keeps moving
  in the background (the connection's reader/keepalive tasks and the
  prompt's `input()` all run concurrently on the one event loop — see
  `asyncio.to_thread(input, ...)` below). The locomotive only stops when a
  later command says so, or the shell exits (see exit-confirmation below).
  **Caveat**: if `--hold` *is* given inside the shell too (e.g.
  `speed 3 60 --hold 10`), the shell prompt blocks for those 10 seconds
  and then auto-stops, exactly like one-shot — `--hold N` always means
  "hold for N seconds then stop, blocking the caller for that long"
  regardless of mode. Omit `--hold` in the shell to get the immediate-return,
  indefinite-hold behavior described above.

**Why one-shot mode can never reliably hold a nonzero speed.** Every
`jmri-cli throttle` invocation opened a fresh `JmriWsClient`, acted, then
closed it in a `finally` block — and JMRI releases a throttle the instant
its owning connection closes (verified live via Proxyman capture). A
temporary `HOLD_SECONDS_AFTER_SPEED` sleep constant only delayed the release,
it never fixed it (raising it from 1.0 to 10.0 just made the loco stop 9
seconds later instead of 1). The actual fix needed a genuine second
connection *mode* — a persistent one — rather than another tweak to the
one-shot lifecycle, since a fresh-connection-per-command design fundamentally
cannot hold state between commands, only within one.

**Two connection modes, one implementation.** Every WS-based
`throttle_*` function in `throttle.py` (`throttle_acquire`, `_release`,
`_speed`, `_stop`, `_estop`, `_direction`, `_on`, `_off`) takes an optional
`*, client: JmriWsClient | None = None` and routes its JMRI calls through
`_client_scope(client)`:

```python
@contextlib.asynccontextmanager
async def _client_scope(client: JmriWsClient | None):
    if client is not None:
        yield client          # shell mode - caller owns the lifecycle
        return
    owned = JmriWsClient()    # one-shot mode - this call owns it
    try:
        yield owned
    finally:
        await owned.close()
```

`client=None` (the default, used by one-shot CLI invocations) opens a fresh
connection, acts, and closes it exactly as before. `client=<JmriWsClient>`
(passed by `shell.py`) reuses a connection that outlives any single command
— the *only* code difference between "acquire and release a throttle
immediately" and "keep a locomotive moving indefinitely" is which of these
two branches runs, not a separate code path. `throttle_list` (reads
`state.py`'s local cache only) and `throttle_sniff` (explicitly one-shot-only,
see below) don't take a `client` kwarg — neither has a reason to share a
connection.

**`shell.py`: bare `jmri-cli` launches it, not a subcommand.** `cli/__init__.py`'s
`main()` special-cases `len(sys.argv) == 1` to call `shell.run_shell()`
directly, before `build_parser()` is even invoked — deliberately *not* a
`jmri-cli shell` subcommand, so the shell is the natural "just run it" path
rather than something to discover. `jmri-cli -h`/`--help` is checked
immediately after and still prints today's banner, unchanged. `run_shell()`
owns one long-lived `JmriWsClient` for the session; each typed line is
`shlex.split()`, parsed with the *same* `build_parser()` tree as one-shot
mode (zero duplication of the argparse tree or dispatch logic), and
dispatched via `args.func(args, **kwargs)` where
`kwargs = {"client": client} if _is_ws_func(args.func) else {}`.
`_is_ws_func` checks `"client" in inspect.signature(func).parameters` —
this works unmodified against the `functools.partial(throttle_direction,
forward=...)` objects used for `forward`/`reverse`, since `inspect.signature`
already understands partials natively. A per-line `parser.parse_args()`
is wrapped in `try/except SystemExit: continue`, since argparse calls
`sys.exit()` on a bad line or `-h` — one-shot mode wants that same
`SystemExit` to reach the OS exit code, the shell must swallow it and keep
the session alive instead. `throttle sniff` is special-cased and rejected
before parsing (needs its own connection and its own indefinite Ctrl-C loop,
which would otherwise block the shell's own `input()` loop) with a message
redirecting to a second terminal.

Reading the prompt uses `asyncio.to_thread(input, "jmri-cli> ")` rather than
a blocking call directly on the event loop — the client's background
reader/keepalive tasks (see `JmriWsClient` design above) need the loop free
while waiting on stdin.

**Exit-confirmation** (`_confirm_exit`) is built on two new read-only
`JmriWsClient` accessors added specifically for this:

```python
def throttle_state(self, throttle_id: str) -> dict[str, Any] | None: ...
def all_throttle_states(self) -> dict[str, dict[str, Any]]: ...
```

Both return copies of the live-synced per-throttle cache described in
`JmriWsClient` design above (never the private dict itself), so `shell.py`
never reaches into `_throttles` directly. `_moving_addresses()` filters
`all_throttle_states()` to nonzero speed; if any are moving, Ctrl-D, typed
`exit`/`quit`, and Ctrl-C at the prompt all funnel into the same prompt-then-
ramp-down flow, using a fixed `SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS = 3.0`
constant for every address (deliberately no per-address memory of past
`--rampdown` values — kept simple). Declining leaves every locomotive in its
current state with an explicit stderr warning; JMRI does not stop a loco
just because its throttle's owning connection closes.

**Ramping** (`ramp_speed`, `execute_speed_change`, both in the shared module
`jmri_ws/ramp.py` — moved out of `cli/throttle.py` when `tools/throttle.py`
gained its own ramped MCP tool, see "Ramped speed changes over MCP" below;
`jmri_ws/` has no dependency on `cli/`, so this is the correct lowest-common
home for logic both surfaces need, keeping `tools/` from ever importing
`cli/`-private code). `ramp_speed` is the shared linear-ramp primitive:
`seconds <= 0` or `from_fraction == to_fraction` degenerates to a single
final `set_speed()` call, so every caller can unconditionally call it rather
than branching on "was a ramp actually requested." Steps are `max(1,
int(seconds * RAMP_STEPS_PER_SECOND))` (4 steps/second, module constant),
always finishing with one exact final `set_speed(to_fraction)` so float
accumulation never leaves the throttle short of target. Its `sleep`
parameter is resolved *inside* the function body (`sleep = sleep or
asyncio.sleep`), not as a bound default — a bound default captures the
function object at import time, which would make
`monkeypatch.setattr("jmri_mcp.jmri_ws.ramp.asyncio", fake_asyncio)` silently
ineffective; resolving fresh inside the body is what makes that monkeypatch
actually take effect.

`execute_speed_change` is the shared orchestrator behind CLI `speed`,
`forward`/`reverse` (via the `target_forward`/`target_fraction` split, see
below) and the MCP `set_speed_ramped` tool: ramp-down (if direction is
flipping, or `--rampdown` is given) → optional direction flip via
`client.set_direction()` → ramp-up to target (if `--rampup` given) → hold
for `hold_seconds` → a final ramp-to-0 once a bounded hold ends,
unconditionally for any caller (a caller that bounds a speed with a hold
means "hold for N seconds, then stop" either way — see the persistence-model
summary above). It re-reads `client.throttle_state()` once at the end for
its return value rather than threading state through every internal step.
The hold is the one place in the whole design with explicit interrupt
handling:

```python
if hold_seconds:
    try:
        await asyncio.sleep(hold_seconds)
    except (KeyboardInterrupt, asyncio.CancelledError):
        await ramp_speed(client, throttle_id, target_fraction, 0.0, rampdown or 0.0)
        raise
```

Ctrl-C during a bounded one-shot hold ramps back to 0 (or jumps, with no
`--rampdown`) before the interrupt propagates, rather than leaving the loco
coasting at whatever speed it had at the moment of interruption. This is
deliberately the *only* interrupt-handling code in the design — the shell has
its own separate Ctrl-C handling at the prompt (above), and every other
`asyncio.sleep` call is allowed to raise and propagate normally.

**`speed_percent` vs. `*_fraction` naming split.** `speed_percent` (CLI-
facing, `args.speed_percent`, may be negative) is never passed directly to
`JmriWsClient`; only a resolved `*_fraction` value (always `0.0`-`1.0`, or
literally `-1.0` inside `throttle_estop` only) reaches `client.set_speed()`.
This is what keeps `throttle speed 3 -40` (CLI-only shorthand for "reverse at
40%", resolved entirely client-side into `target_forward=False,
target_fraction=0.4`) from ever colliding with JMRI's real emergency-stop
wire sentinel `speed=-1.0` — the two never share a code path, and the naming
convention makes an accidental mix-up visible at every call site rather than
relying on a comment. `throttle_direction` (the shared body behind `forward`/
`reverse`) reads `current_fraction` from the acquire reply and re-targets it
as-is (`target_fraction=current_fraction`) with only `target_forward`
changed — a pure direction flip ramps back to the speed the loco was already
at, never to a fixed value.

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

## Ramped speed changes over MCP: `set_speed_ramped`

`tools/throttle.py`'s `set_speed_ramped` is the LLM-facing equivalent of the
CLI's `--rampup`/`--rampdown`/`--hold` flags — added because the CLI's
ramping (from the interactive-shell work above) was never actually exposed
to the LLM, so a voice/chat request like "run the autorail forward at 30%
for 10 seconds, ramp up and down" had no tool that could do it. It reuses
`jmri_ws.ramp.execute_speed_change` directly rather than duplicating the
ramp state machine — the same function CLI `speed`/`stop`/`forward`/
`reverse` and `shell.py`'s exit-confirmation ramp-down call. `speed_percent`
accepts the same CLI-only negative-value shorthand as `throttle speed`
("reverse at |value|%", resolved client-side, never sent as JMRI's real
`speed=-1.0` e-stop sentinel). `hold_seconds`, if given, blocks the tool
call server-side for the full ramp-up + hold + ramp-down duration before
returning — the LLM never has to measure or track time itself, it just
passes the number of seconds through; the tool's docstring says this
explicitly (added after a live report that an LLM verbally refused a
`hold_seconds` request, saying it couldn't "measure time" — the fix was
reassuring language in the docstring, not a code change, since the call was
never actually attempted). Uses the same `ensure_acquired`/`throttle_id`
plumbing as `set_speed`/`stop`/etc., so it auto-acquires the throttle like
every other throttle tool.

## `set_power`: never re-POST a state JMRI already reports

Real JMRI/DCC++ bug, found by the user on their own installation:
POSTing a power state to a system that's already in that state (e.g. ON
twice in a row) doesn't no-op — it knocks the system into state UNKNOWN,
which is awkward to recover from. This isn't a transient-response quirk
like the one `_POST_RECHECK_DELAY` already works around (see the
`set_power` docstring) — it's a distinct failure mode triggered by the
POST itself being redundant, not by trusting its immediate response.

`jmri_client/power.py`'s `set_power(prefix, turn_on)` now re-reads
current state via `get_systems()` **before** POSTing, not just after, and
returns immediately with `confirmed: True` if the current state already
matches the request — no POST is sent at all in that case. This makes
"already ON" and "turn ON" indistinguishable from the caller's point of
view, by design: every caller (the `set_power` MCP tool, `jmri-cli power
on`/`off`, and `_set_power_all` — the shared loop behind `power_off_all`/
`power_on_all`) goes through this one function, so the guard applies
everywhere uniformly rather than needing to be duplicated per call site.

The pre-check costs one extra `get_systems()` call per `set_power`
invocation in the case where a POST does end up being sent (current state
differs from requested) — accepted deliberately, since avoiding the
UNKNOWN failure mode matters more than saving one HTTP round-trip.

## `get_power` / `list_systems`: connection name doubles as system description

JMRI has no dedicated field for "what is this power system for" — the
user names each DCC connection directly in JMRI's own connection setup,
and any purpose description they add lives as a plain parenthetical
inside that same name string, e.g. `"zou (test)"`, `"raijin (tracks)"`,
`"ohara (turnouts)"`, `"taya (accessories)"` (the user's real systems,
verified live). `get_systems()`/`compact_power()` do no parsing or
splitting of this — the full name string, parenthetical included, passes
through untouched as the `"name"` field both `get_power` and
`list_systems` return.

The fix here (issue #24) is docstring-only: `compact_power()`,
`get_power`, and `list_systems` all now explicitly tell the LLM that this
`"name"` field is the answer to "what is system X for?" — without this,
the LLM had the description in front of it (verified: `get_power("zou")`
already returned `{"name": "zou (test)", ...}` before this fix) but no
instruction that it was safe/expected to read purpose out of it, so a
"à quoi sert le système zou ?" question risked an "I don't have that
information" answer despite the answer being present in the payload.

## `emergency_stop_all`: stop every acquired throttle at once

`JmriWsClient.emergency_stop_all()` (in `jmri_ws/__init__.py`) iterates
`_throttles` — every address this connection currently holds, not just
ones a single call names — and calls the existing `set_speed(tid, -1.0)`
per throttle, inheriting its no-op-skip/cache logic for free: an
already-e-stopped loco is silently skipped rather than resent, but still
reported as stopped in the result. This is a thin iteration wrapper
reusing already-verified low-level logic rather than new protocol code.

The MCP tool (`tools/throttle.py`) takes no arguments and translates the
returned throttle ids back to DCC addresses via `client._throttles`
before returning `{"stopped": [...], "failed": [...]}` to the LLM. Its
docstring is deliberately explicit about a real limitation: this only
reaches locomotives *this* MCP session has acquired a throttle for — a
loco being driven from a JMRI panel, PanelPro, or another MCP/voice
session that never went through this connection is untouched, because
JMRI has no server-side "stop every throttle" call; only the connection
holding a throttle can command it. The docstring points at `power_off_all`
for the case where the caller needs a guarantee that covers every
locomotive regardless of who's driving it.

The CLI has no equivalent long-lived session to iterate, so `jmri-cli
throttle stop [loco]` resolves its population of throttles differently:
with no `loco` given, it reads every address key out of `cli/state.py`'s
local cache (`~/.jmri-cli/throttle_state.json`) instead of the roster —
"every locomotive this CLI has already touched", not "every locomotive
JMRI knows about" — then acquires each on a fresh connection and issues a
controlled stop (`set_speed(tid, 0.0)`), not the decoder e-stop
`emergency_stop_all()` uses (`throttle estop <loco>` remains the CLI's
single-target e-stop). This has its own honestly-documented limitation,
distinct from the MCP tool's: a locomotive only ever driven from a JMRI
panel or another client, never touched by this CLI, is out of reach here.
`power off` remains the CLI's actual "stop absolutely everything
regardless of who's driving" primitive (see below), since cutting power
stops every decoder unconditionally.

## `power_off_all` / `power_on_all`: cut or restore power to every DCC system at once

`jmri_client/power.py`'s private `_set_power_all(turn_on)` discovers every
system via `get_systems()` and calls the existing
`set_power(prefix, turn_on)` on each in turn, inheriting the same
re-read-and-confirm honesty contract as a single `set_power()` call.
`power_off_all()` and `power_on_all()` are both thin wrappers over this one
shared loop — same reasoning as `_power_set(args, turn_on)` in `cli/power.py`
(the shared body behind `power on`/`power off`) and the `turn_on: bool`
shared `power_off_all`/`power_on_all` MCP tool pair, so the
sequential/re-read logic exists exactly once instead of being copied per
direction. Systems are processed **sequentially, not concurrently** —
`set_power`'s own `_POST_RECHECK_DELAY` already serializes one system's
round-trip, and going one at a time avoids hammering JMRI/DCC++ with
simultaneous POSTs to different command stations.

`power_off_all` is the real "stop absolutely everything on the layout"
primitive, distinct from `emergency_stop_all` above: cutting power stops
every decoder on every system unconditionally, including locomotives with
no throttle acquired anywhere, because they lose track power entirely.
It's also more drastic — re-powering afterward requires an explicit
`power_on_all` (or per-system `set_power(system, turn_on=True)`) before
anything can move again, so both MCP tools' docstrings and `jmri-cli power
off`/`on` (with no target — see the CLI redesign section above) frame
`power_off_all` as a genuine-emergency tool, not a routine "stop the
train" command. `power_on_all`'s own docstring is
explicit that restoring power does **not** resume any locomotive's
previous speed — every decoder stays stopped until a new speed command is
sent, since JMRI's throttle software state is untouched by a power cycle;
it is not an "undo" of `power_off_all`/`emergency_stop_all`. Both MCP
tools return one compact, individually-`confirmed` result per system (same
shape as `get_power`/`set_power`), so a caller checks per-system
confirmation rather than assuming the whole layout changed state.

Both tools' docstrings explicitly anchor to the natural-language phrasings
that should trigger them (English and French: "cut the power"/"coupe le
courant"/"coupe tout" for `power_off_all`, "turn everything on"/"allume
tout" for `power_on_all`, "stop everything"/"arrête tout" for
`emergency_stop_all`) — the LLM has no other signal to map a generic,
no-target-named voice command to the right whole-layout tool instead of
asking the user to name a system/locomotive.

## Executor mode: `set_executor_mode` / `get_executor_mode`

`tools/mode.py` answers a different kind of request — not "stop the
layout" but "stop narrating." MCP does have one server-level channel that
reaches the host LLM without a tool call (`instructions`, see the section
below), but it's static and one-shot — set once at server construction,
delivered once at `initialize`, no way to update mid-conversation — so it
cannot carry a flag that flips on/off as the user asks for it mid-session.
`@mcp.prompt()` is dynamic but opt-in and client-controlled (e.g. a user
must manually invoke it as a slash command in Claude Desktop), not
something a tool call can force either. The only mechanism actually
available to a tool at any point in the conversation is its own **return
value**, since the LLM reads every tool result before deciding what to say
next.

So "executor mode" is a module-level flag, `_executor_mode` — process-wide
is correct here, not a bug, because this MCP server runs one process per
stdio client session, so there's no cross-session leakage to worry about.
`set_executor_mode(enabled)` flips it and returns an explicit natural-
language instruction string (terse, no narration, no restating the
request, report outcomes only); `get_executor_mode()` re-delivers the same
instruction if it's on, for a caller unsure whether it's still active after
a long gap. The instruction is re-delivered on every call rather than sent
once and assumed to "stick," since there's no system-prompt-level way for
this server to keep reminding the LLM otherwise — this is a behavioral
nudge via tool output, not an enforced constraint.

`mode.py` deliberately has **no `jmri_client`/`jmri_ws` counterpart and no
`cli/` equivalent** — it holds no JMRI state and makes no JMRI calls at
all, so there's nothing for a one-shot `jmri-cli` process to usefully
exercise; the whole point of the flag is that it persists across tool
calls within one long-lived MCP session, which a fresh CLI invocation
never has.

## `server/__init__.py`: MCP `instructions` — standing guidance delivered at `initialize`

`FastMCP`'s `instructions` constructor argument flows through the
underlying SDK (`Server.create_initialization_options()`) into
`InitializationOptions`, which becomes a top-level field of the MCP
protocol's `initialize` response — delivered once, before the LLM has
necessarily read any tool's docstring. Verified live: a bare
`FastMCP("JMRI")` with no `instructions=` produces an `initialize`
response with only `protocolVersion`, `capabilities`, `serverInfo` — no
`instructions` key at all until one is passed in.

`server/__init__.py` sets `_SERVER_INSTRUCTIONS` and passes it as
`FastMCP("JMRI", instructions=_SERVER_INSTRUCTIONS)`. Content is scoped to
exactly one thing: mapping the four whole-layout, no-argument tools to the
French/English phrases that should trigger them (`emergency_stop_all`,
`power_off_all`, `power_on_all`, `set_executor_mode`) — without this, the
LLM has no signal connecting a generic, no-target-named command like
"arrête tout" to the right tool until it has already read that tool's own
docstring, which only happens if it guesses to look there first. This is
deliberately narrow: a general safety reminder (e.g. about unauthorized
motion commands) and general project context were both considered and
left out, kept instead in `CLAUDE.md`/this repo's docs, not the MCP
protocol payload.

Two real limits on this mechanism, both by design of the protocol, not
bugs here:
- **Static and one-shot** — set at server construction, delivered once at
  `initialize`, no way to update mid-conversation. This is exactly why it
  cannot carry `mode.py`'s executor-mode flag (which needs to flip on/off
  as the user asks) — that still has to work by returning an instruction
  in a tool's own result on every call, since that is the only channel
  that can change mid-session.
- **Best-effort, not guaranteed** — respecting `instructions` is up to the
  MCP client (Claude Desktop, Kira's bridge via `xiaozhi_wrapper`). The
  protocol defines the field; nothing forces a client to surface it into
  the underlying LLM's context.

**Listing the right phrase is not sufficient by itself.** A live user test
found "coupe le courant" ("cut the power") routing to `emergency_stop_all`
instead of `power_off_all`, even though `_SERVER_INSTRUCTIONS` and
`power_off_all`'s own docstring both already listed that exact phrase —
the LLM can still pattern-match "this sounds like a stop request" ahead of
actually comparing which specific tool the phrase is mapped to, especially
when two tools' purposes are this close (both are "stop the whole layout"
in spirit, but one only touches throttles, the other cuts power). The fix
was an explicit negative clause added to both docstrings and
`_SERVER_INSTRUCTIONS`: a phrase naming power/current always means
`power_off_all`, never `emergency_stop_all`, stated as a direct
"NOT interchangeable" rule rather than relying on the trigger-phrase lists
alone to disambiguate by omission.
