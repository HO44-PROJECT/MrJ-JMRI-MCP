# Architecture

## Package layout

This is a monorepo of **three independently-installable PyPI packages**, lockstep-versioned,
under `packages/`:

```
packages/
├── jmri-core/                 # PyPI: jmri-core — shared foundation, no UI of its own
│   ├── pyproject.toml
│   ├── src/jmri_core/
│   │   ├── config/             # env vars: JMRI_URL (e.g. http://localhost:12080)
│   │   │   └── __init__.py
│   │   ├── constants/          # dedicated modules for every literal used more than once
│   │   │   ├── __init__.py    #   re-exports protocol/endpoints/client_tuning/cli
│   │   │   ├── protocol.py     #  JMRI JSON field names + WS message-type strings
│   │   │   ├── endpoints.py    #  JMRI REST path templates (e.g. TURNOUT = "/json/turnout/{name}")
│   │   │   ├── client_tuning.py #  HTTP/WS timeouts, reconnect delays, ramp step rate
│   │   │   └── cli.py          #  *_STATE_NAMES dicts, CLI id prefixes/ranges, SORT_INDICATOR
│   │   │                       #  (lives here, not in jmri-cli — also imported by jmri_client/jmri_ws)
│   │   ├── jmri_errors.py      # shared JmriError(code, **kwargs), raised by jmri_client AND jmri_ws
│   │   ├── i18n/               # hand-rolled i18n: dotted-key lookup against per-language JSON
│   │   │   ├── __init__.py    #   lookup(lang, key, **kwargs), t(key, **kwargs), active_lang()
│   │   │   ├── en.json          # errors.*/kinds.* message templates (English, default)
│   │   │   └── fr.json          # same keys, French
│   │   ├── jmri_client/       # async HTTP client for JMRI's JSON API
│   │   │   ├── __init__.py    #   re-exports every public name (power/roster/light/turnout/sensor/block/signal)
│   │   │   ├── _http.py        #  shared GET/POST plumbing, JmriError re-export, envelope unwrap
│   │   │   ├── power.py        #  version, power-system discovery, power on/off,
│   │   │   │                   #  power_off_all/power_on_all, resolve_system
│   │   │   ├── roster.py        # roster listing, name resolution, function labels
│   │   │   ├── light.py         # layout light discovery, on/off, resolve_light
│   │   │   ├── turnout.py       # turnout discovery, closed/thrown, resolve_turnout
│   │   │   ├── sensor.py        # sensor discovery (read-only), resolve_sensor
│   │   │   ├── block.py          # layout block discovery (read-only), resolve_block
│   │   │   └── signal.py        # signal mast discovery, aspect set, resolve_signal
│   │   │   │                    #   (signalMast only, not signalHead — see file docstring)
│   │   ├── jmri_ws/            # persistent WebSocket client (ws://<jmri>/json/) for throttles
│   │   │   ├── __init__.py     #   incl. emergency_stop_all() (every acquired throttle at once)
│   │   │   └── ramp.py          #  ramp_speed/execute_speed_change: shared ramp state
│   │   │                        #   machine, used by jmri-cli's throttle.py/shell.py, and
│   │   │                        #   jmri-mcp's tools/throttle.py's set_speed_ramped
│   │   └── testing/            # pytest plugin: fake_jmri + mock_*/*_fixture fixtures,
│   │       ├── __init__.py     #   shared by all 3 packages' test suites — installed
│   │       ├── plugin.py       #   automatically via the pytest11 entry point once
│   │       └── fixtures/*.json #   jmri-core[test] is installed, no per-package conftest wiring needed
│   └── tests/                  # tests for jmri_client/jmri_ws/i18n/constants/config/jmri_errors
│
├── jmri-cli/                  # PyPI: jmri-cli — manual command-line tool, depends on jmri-core
│   ├── pyproject.toml
│   ├── src/jmri_cli/
│   │   ├── __init__.py    #   main(); bare launches shell.py, help/-h/--help show
│   │   │                  #     banner.py's welcome banner, everything else runs clean
│   │   ├── __main__.py    #   enables `python -m jmri_cli`
│   │   ├── banner.py      #   the welcome banner (name, version, repo link, command list)
│   │   ├── _common.py     #   cross-module helpers (cli_throttle_id)
│   │   ├── _match.py      #   find_regex/find_glob: shared matching for findr/findg leaves
│   │   ├── _sort.py       #   sortable "by*" sibling subcommands shared across list/find
│   │   ├── state.py       #   local throttle-state cache (~/.jmri-cli/throttle_state.json)
│   │   ├── cache.py       #   cache [info|clean]: inspect/reset the local ~/.jmri-cli/ files
│   │   │                  #     (throttle_state.json, shell_history) — no JMRI contact
│   │   ├── power.py       #   power [status|on|off|get|find|findr|findg|default] (jmri_client)
│   │   ├── roster.py      #   roster [list|find|findr|findg|functions] (jmri_client)
│   │   ├── throttle.py    #   throttle [list|find|findr|findg|acquire|release|speed|
│   │   │                  #     stop|estop|forward|reverse|on|off|sniff] (jmri_ws +
│   │   │                  #     state.py; find/findr/findg are read-only, roster+cache only)
│   │   ├── light.py       #   light [list|find|findr|findg|on|off] (jmri_client)
│   │   ├── turnout.py     #   turnout [list|find|findr|findg|close|throw] (jmri_client)
│   │   ├── sensor.py      #   sensor [list|find|findr|findg|status] (jmri_client, read-only)
│   │   ├── block.py       #   block [list|find|findr|findg|status] (jmri_client, read-only)
│   │   ├── signal.py      #   signal [list|status|find|findr|findg|set] (jmri_client, signalMast only)
│   │   ├── session.py     #   session-start / session-end: composite commands sequencing
│   │   │                  #     power.py/throttle.py's own commands (see docs/cli.md)
│   │   └── parser.py      #   build_parser(): wires the above into one CLI, incl. the
│   │                      #     bare-group-default and verb-elevation patterns (see docs/cli.md)
│   └── tests/              # tests for the jmri-cli argument parser and command execution
│
└── jmri-mcp/                  # PyPI: jmri-mcp — the MCP stdio server, depends on jmri-core
    ├── pyproject.toml
    ├── src/jmri_mcp/
    │   ├── __init__.py    # __version__
    │   ├── tools/             # MCP tools exposed to the LLM
    │   │   ├── __init__.py    #   register(mcp): wires every domain module below
    │   │   ├── _common.py      #  shared helpers (throttle_id, compact_*, ensure_acquired)
    │   │   ├── power.py         # list_systems, get_power, set_power, power_off_all,
    │   │   │                    #   power_on_all, system_status
    │   │   ├── roster.py        # list_roster, find_locomotive, get_locomotive_functions
    │   │   ├── throttle.py      # acquire/release_throttle, set_speed/set_speed_ramped/
    │   │   │                    #   stop/emergency_stop, emergency_stop_all, set_direction,
    │   │   │                    #   set_function, lights_on/lights_off
    │   │   ├── light.py         # list_lights, get_light, set_light (layout/scenery lights,
    │   │   │                    #   distinct from a locomotive's F0 headlight function)
    │   │   ├── turnout.py       # list_turnouts, get_turnout, set_turnout
    │   │   ├── sensor.py        # list_sensors, get_sensor (read-only)
    │   │   ├── block.py          # list_blocks, get_block (read-only)
    │   │   ├── signal.py        # list_signals, get_signal, set_signal (signalMast only)
    │   │   └── mode.py           # set_executor_mode, get_executor_mode (concise/
    │   │   │                    #   no-narration response style, no JMRI I/O)
    │   └── server/            # jmri-mcp: the MCP stdio server, no MCP client needed to build it
    │       ├── __init__.py    #   main(); FastMCP wiring; logging → stderr only
    │       └── __main__.py    #   enables `python -m jmri_mcp.server`
    ├── src/xiaozhi_wrapper/    # generic stdio<->WebSocket bridge for xiaozhi/Kira (no JMRI code)
    │   ├── __init__.py         #   main(); build_server_command(), connect_with_retry(), ...
    │   ├── __main__.py         #   enables `python -m xiaozhi_wrapper`
    │   ├── constants.py         #  env var names, mcp_config.json keys/transport types, backoff/timeout tunables
    │   └── mcp_config.json      #  checked in as-is — no env block, JMRI_URL comes from the launching shell
    └── tests/                  # tests for tools/ and server/
```

`jmri-core` has **zero UI of its own** — it's a library consumed by both `jmri-cli` and
`jmri-mcp`, never installed standalone by an end user. `constants/cli.py`'s name is a
historical misnomer from before the package split: despite the filename, it's imported by
`jmri_client`/`jmri_ws` too (the state-name dicts and CLI id-prefix constants are genuinely
shared), so it lives in `jmri-core`, not `jmri-cli` — moving it would create a
`jmri-cli`→`jmri-core` circular dependency in reverse.

A root-level `pyproject.toml` (no `[project]` of its own) wires the three as a
[`uv` workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
(`[tool.uv.workspace] members = ["packages/*"]`) so `uv sync --all-packages` installs all
three editable in one `.venv` for local development — each package also installs and
publishes independently via its own `pyproject.toml`. Shared dev tooling config
(`pytest`, `ruff`) lives in this root file too, since `pytest`/`ruff` read config relative
to their invocation directory and this project runs both from the repo root across all
three packages at once.

Eight domains — **power**, **roster**, **throttle**, **light**, **turnout**,
**sensor**, **block**, **signal** — recur across the project and are split the same way
everywhere they get big enough to warrant it: `jmri_client/` (HTTP, in `jmri-core`),
`tools/` (MCP surface, in `jmri-mcp`), and the CLI leaves (manual CLI, in `jmri-cli`) each
have their own
`power.py`/`roster.py`/`throttle.py`/`light.py`/`turnout.py`/`sensor.py`/`block.py`/`signal.py`.
`jmri_ws/__init__.py` stays a single file within its package — it's one
cohesive unit of tightly-coupled state (a WebSocket connection's
request/reply/cache logic) with no natural seam to split along.
`tools/mode.py` is the one module with no `jmri_client`/`jmri_ws`
counterpart and no CLI equivalent — it holds no JMRI state at all (see
"Executor mode" below), so there's nothing for a one-shot CLI process to
usefully exercise (its whole point is a flag that persists across tool
calls within one long-lived MCP session).

Every directory at a package's `src/` root is a package (`__init__.py`, no
flat `.py` files at the root) — this project's two executables,
`jmri-mcp` and `jmri-cli`, are each their own package (`jmri_mcp/server/` in the
`jmri-mcp` distribution, `jmri_cli/` itself in the `jmri-cli` distribution), both
following the same shape: `main()` lives in `__init__.py`, and a sibling
`__main__.py` re-exports it so `python -m jmri_cli` / `python -m jmri_mcp.server`
also work. `jmri_core.config` and `jmri_core.jmri_ws` are single-file packages (all
their content lives in `__init__.py`) — they have no `main()` and no natural seam to
split into multiple files, but still follow the "no bare `.py` at the root" rule.
Everything except `jmri_mcp/server/` and `jmri_cli/` itself is library code with no
top-level side effects — it can't be run standalone, only imported.

`jmri-mcp`'s `src/` has two independent top-level packages: `jmri_mcp/` (this
project's actual purpose — the MCP server) and `xiaozhi_wrapper/` (a generic MCP
stdio↔WebSocket bridge, JMRI-agnostic, for exposing `jmri-mcp` — or any other stdio
MCP server — to xiaozhi/Kira). They only meet at `mcp_config.json`'s `"command":
"jmri-mcp"`; `xiaozhi_wrapper` imports nothing from `jmri_mcp` or `jmri_core`. It was
ported into this repo from the separate `kira` project on 2026-07-09, since
`pyproject.toml`'s `[project.scripts]` already coupled the two — see
`packages/jmri-mcp/src/xiaozhi_wrapper/__init__.py`'s docstring. It ships inside the `jmri-mcp`
PyPI package (not split into a fourth package) since it has no independent use
outside exposing an MCP server to xiaozhi/Kira.

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

Any magic string or number used more than once lives in `packages/jmri-core/src/jmri_core/constants/`,
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
  `jmri_cli/*.py` module import, rather than each redefining them), CLI throttle-id prefixes,
  function/speed ranges, and `SORT_INDICATOR` (` ▼`, appended to a sorted column's header
  at the print call site — never baked into the header string itself).
- **`lighting.py`** — `LIGHT_LABEL_KEYWORDS` and `is_light_label(label)`, the keyword
  vocabulary `set_loco_lights`/`set_all_locos_lights` (and the CLI's `--lights-only`
  flag) use to recognize a roster function label as naming a light (English
  light/lamp/headlight; French lumière/feu/lampe/phare, accent-folded). Deliberately a
  flat keyword list, not the i18n `kinds` table above — a user's roster labels are free
  text they typed themselves in JMRI's own editor, not a fixed vocabulary this project
  controls, so matching is generous/substring-based rather than an exact i18n key.
  Depends on `jmri_core/text.py`'s `fold()` (NFKD accent-strip + casefold), promoted there
  from what used to be `jmri_client/roster.py`'s private `_fold()` so both `roster.py` and
  `lighting.py` share one implementation without `constants` importing from `jmri_client`
  (the wrong layering direction — `constants` is meant to be a leaf).

`jmri_cli/light.py`, `jmri_cli/power.py`, and `jmri_cli/turnout.py`'s `_*_set()` helpers reconstruct
the reported state name via `STATE_NAMES[ON_VALUE if flag else OFF_VALUE]` — reading the
same dict `_row()` uses to render table rows — rather than a second, independent
`"ON" if flag else "OFF"`-style string literal that could drift out of sync with it.

## `jmri_errors.py` + `i18n/`: structured errors, hand-rolled translation

No user-facing message is written as a hardcoded string in `jmri_client`/`jmri_ws`
anymore. Both raise a single shared `JmriError(code, **kwargs)` (`packages/jmri-core/src/jmri_core/jmri_errors.py`)
instead of each defining its own exception class with a baked-in English f-string —
`jmri_client/_http.py` and `jmri_ws/__init__.py` used to each define an identical local
`JmriError`, which meant `jmri_cli/throttle.py`/`jmri_cli/shell.py`/`tools/throttle.py` had to
import one of them aliased as `JmriWsError` just to catch both; a single shared class
collapses that back to one `except JmriError`.

`code` is a short machine-readable key (`"unknown_entity"`, `"vanished_after_post"`,
`"ws_connect_failed"`, ...) resolved at message-render time against
`packages/jmri-core/src/jmri_core/i18n/en.json` / `fr.json` — not gettext or an external i18n library, a
small dotted-key JSON lookup (`i18n.lookup(lang, "errors.<code>", **kwargs)`) using
`str.format()` interpolation (chosen over `%`-style because several templates need
`{query!r}`-style conversion flags). `JmriError.__str__` always renders English
(`lookup("en", ...)`) regardless of the active language — logging/`str(exc)` call sites
stay English/developer-facing, per this project's existing English-for-code convention;
only `cli`/`tools` translate at the catch site via `i18n.t()` (against
`active_lang()`, driven by the `JMRI_MCP_LANG` env var, default `"en"`).

Domain errors that repeat the same shape across turnout/light/sensor/block/signal/roster/system
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

`lookup()` also caps how much of a resolver's `available`/`matches` kwarg it renders:
`_cap_list_kwarg()` joins the list and, past `_MAX_LISTED = 15` entries, truncates to
`"A, B, C, ... (+N more)"` before the final `str.format()`. A layout with dozens of
turnouts/lights/sensors previously rendered its *entire* inventory into a single
`unknown_entity`/`ambiguous_entity` message — a wall of text for voice/chat output that
an LLM tends to recite back to the user verbatim rather than summarizing. This is fixed
centrally in `lookup()`, not at each of the 6 resolver call sites, to avoid drift across
turnout/light/sensor/signal/block/roster. Only the *rendered string* is capped —
`exc.kwargs["available"]`/`exc.kwargs["matches"]` themselves keep the full uncapped list,
so a caller that inspects the exception programmatically (rather than just printing it)
still sees everything. Capping the payload doesn't by itself stop an LLM from reading a
15-item list back as prose; that behavioral half is addressed by `_SERVER_INSTRUCTIONS`
below ("act, don't recite").

LLM-facing instruction strings (`server/__init__.py`'s server instructions,
`tools/mode.py`'s executor-mode strings) and every docstring are **deliberately out of
scope** for i18n — they're consumed by the LLM host, not read directly by a human, and
`tools/mode.py` specifically depends on intentional bilingual FR/EN trigger vocabulary
that a translation table would collapse.

Every `jmri_cli/*.py` catch site now goes through `i18n.error(exc)` (`packages/jmri-core/src/jmri_core/i18n/__init__.py`)
instead of `print(f"Error: {exc}", file=sys.stderr)`: it renders the translated
`errors.<code>` body via `exc.code`/`exc.kwargs` and wraps it in the translated
`cli.error_prefix` template ("Error: {message}" / "Erreur : {message}"), so the "Error:"
label itself is translated too, not just the message body. `i18n.error()` only works on
`JmriError` — catch sites for other exceptions (e.g. `jmri_cli/shell.py`'s `except ValueError`
around `shlex.split()` for malformed shell input) are untouched and keep their plain
f-string, since a plain exception has no `.code`/`.kwargs` to look up. A handful of catch
sites don't fit the generic "Error: {message}" shape because they prepend domain-specific
context (an address, an F-number) before the JMRI error text — these use dedicated
`cli.*` keys taking a `message=` kwarg instead (`cli.jmri_unreachable`,
`cli.power_systems_unavailable`, `cli.throttle_error_stopping_address`,
`cli.throttle_error_address`, `cli.throttle_error_function`,
`cli.throttle_warning_could_not_acquire`), called directly via `i18n.t(key, message=str(exc), ...)`.
`tools/*.py` catch sites follow the same split at the MCP-return level: `return {"error":
i18n.t(f"errors.{exc.code}", **exc.kwargs)}` instead of `return {"error": str(exc)}` —
tools have no prefix template since the "error" key in the returned dict already carries
that meaning to the LLM host.

The two independent `JmriError` classes noted above are now fully unified: `jmri_cli/throttle.py`,
`jmri_cli/shell.py`, and `tools/throttle.py` no longer alias `jmri_ws`'s class as `JmriWsError`
(or `jmri_client`'s as `JmriHttpError`) — every catch site imports and matches on the one
shared `JmriError`.

`tabulate()` table headers and argparse `help=` strings are translated the same way.
Each `jmri_cli/*.py` file with a table gets a small `_headers()` (or, for `throttle.py`,
`_throttle_headers()`) helper building `[i18n.t("headers.x"), ...]` at *call* time, not
import time — `i18n.active_lang()` reads `JMRI_MCP_LANG` dynamically, so headers must
reflect whatever language is active when the command actually runs. The `▼` sort-indicator
is never baked into a translated string: it's the shared `SORT_INDICATOR` constant
(`constants/cli.py`) appended to the plain translated header at the sorted-view call site
only (`headers[column] += SORT_INDICATOR`), replacing the old mix of hardcoded `"System ID
▼"` literals and ad hoc `f"{header} ▼"` concatenation. `jmri_cli/parser.py`'s `build_parser()`
runs fresh per invocation, after `JMRI_MCP_LANG` is already in the environment, so every
`help=i18n.t("help.<group>.<leaf>")` / `help=i18n.t("help.arg.<name>")` call resolves
correctly with no special-casing — there's no long-lived parser instance that could outlive
an env var change. `jmri_cli/_doc.py` (the old `GROUP_HELP` dict) is deleted; `jmri_cli/__init__.py`'s
and `jmri_cli/shell.py`'s front-page command lists now build `{name: i18n.t(f"help.group.{name}")
for name in _GROUP_NAMES}` instead of importing that dict.

The remaining hardcoded `print()` calls across `jmri_cli/*.py` — success/status prose, empty-
result messages, unconfirmed-state warnings, the welcome banner (`jmri_cli/banner.py`), and the
shell's own welcome/exit/help text (`jmri_cli/shell.py`) — are now wired to `i18n.t("cli.*", ...)`
the same way. The `no_entities_found`/`no_entities_match`/`not_every_entity_confirmed`
templates are shared across `light.py`/`turnout.py`/`sensor.py`/`block.py`/`signal.py` via a `kind=`
kwarg (e.g. `kind="signal mast"`, matching the `kinds` table's key exactly) — callers pass
`kind=` directly and let `i18n.lookup()`'s `_expand_kind()` step derive `{kind}`/
`{kind_plural}`/`{Kind}` from the `kinds.*` table; a call site must never pre-resolve
`kind_plural` itself via a second `i18n.t("kinds.X.plural")` lookup, since that bypasses the
same expansion `{kind}` still needs and produces an inconsistent pattern. One exception
stays firmly out of scope, as decided from the start of this refactor: every `key=value`
diagnostic line (e.g. `f"address={address} speed={speed} direction={direction}"`,
throttle.py's `sniff` message dump) keeps its English label unconditionally — these are
treated as machine/script-parseable logging output, not translated prose, so only the
values interpolate, never the labels.

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
  It also surfaces `dcc_system`: the connection prefix (e.g. `"T"`) a
  locomotive is normally driven through, read from a `DccSystem` JMRI
  RosterEntry Attribute (`entry["attributes"]`, a list of `{"name",
  "value"}` pairs set via PanelPro's Roster Entry → Edit → Attributes tab,
  distinct from `rosterGroups`) — `None` when unset, the normal case on a
  single-command-station layout. `get_roster()` also surfaces
  `max_speed_percent`: the roster's `maxSpeedPct` field (PanelPro's Roster
  Entry editor calls this "Throttle Speed Limit"), defaulting to 100 (no
  restriction) when unset. `resolve_dcc_prefix()`/`resolve_max_speed_percent()`
  look these two fields up for a single address without fetching/compacting
  the whole roster. `resolve_system_name(prefix)` and `default_system_prefix()`
  round out the display side: given a prefix, look up the matching system's
  full name from `get_systems()` (falling back to the prefix itself if it's
  unknown or JMRI is unreachable — never raises), and report which prefix is
  JMRI's own default system.
- **Speed scaling (PanelPro parity).** JMRI's WebSocket `speed` field is a
  raw 0.0-1.0 decoder fraction; it does not apply a roster's `maxSpeedPct`
  limit on its own. PanelPro's own throttle window scales its slider by that
  limit client-side before sending to JMRI, so this project replicates that
  scaling itself: a requested `speed_percent` is always relative to a loco's
  *own* configured maximum (100% means 100% of `max_speed_percent`, not the
  raw decoder ceiling), converted to a decoder fraction via
  `resolve_speed_scale(address)` (jmri-mcp `tools/_common.py`, 0.0-1.0
  multiplier from `resolve_max_speed_percent`, defaults to 1.0 — fail-open —
  on lookup failure) immediately before the value reaches
  `client.set_speed()`/`execute_speed_change()`, and unscaled back the same
  way when reporting the actual speed. `jmri-cli`'s `throttle speed` applies
  the identical scale computed inline from `resolve_max_speed_percent()`.
  Most locos have no limit set, in which case this is a no-op.
- **System-name display: two different conventions for two different
  audiences.** Every place a command station matters to the user shows the
  resolved system's full name (e.g. `"DCC++ Ohara"`), never the bare prefix
  alone — but *when* it's shown differs by context:
  - **Roster listings** (`list_roster`/`find_locomotive`, `roster
    list`/`find`/`findr`/`findg`, `throttle list`/`find`/`findr`/`findg`)
    always show a system, because a locomotive is always actually driven
    through *some* system. `dcc_system_name` (MCP) and the `DCC system`
    column/`dcc_system=` field (CLI) fall back to JMRI's own default
    system's prefix/name when the entry has no explicit `DccSystem`
    attribute set, rather than showing `null`/`-` — that would misleadingly
    read as "no system" instead of "the default one". Only a failed
    default-system lookup itself falls back to `-`/`null`.
    `find_locomotive` gets this for free from `resolve_system_name(prefix)`
    (its `prefix=None` case already resolves to the default system's name);
    `list_roster` and the `jmri-cli` roster/throttle listing code derive
    `default_prefix` from `get_systems()`'s `default: True` entry and apply
    `dcc_system or default_prefix` before the name lookup.
  - **Throttle action messages** (`acquire_throttle`, `set_speed`,
    `set_speed_ramped`, and `jmri-cli`'s equivalents) stay silent about the
    system on the common case, to avoid clutter — they only mention it when
    the prefix in use differs from JMRI's default system
    (`resolve_system_field(prefix)` in `tools/_common.py`, returning `None`
    when the prefix equals the default); `jmri-cli` mirrors this with
    `_system_suffix(prefix)` in `throttle.py`, appending `" system=<name>"`
    to printed lines only in the non-default case.
- **Turnout/light/signal system attribution: `dcc_system_name`.** Unlike a
  roster entry (which needs an explicit `DccSystem` attribute or a
  default-system fallback, see above), a turnout/light/signal's JMRI system
  name always starts with a real prefix character — the DCC connection
  prefix (`O`/`R`/`T`/`Z` on this layout) or `I` for a JMRI-internal object
  with no power connection at all (e.g. `IT100`, `IL1`). `power.py`'s
  `resolve_dcc_system_name(system_name)` takes a full system name like
  `"OT23"`, resolves its leading character against `get_systems()`, and
  returns the owning system's full name (e.g. `"DCC++ Ohara"`) — or `None`
  (never raises) when the prefix matches nothing (the common case for
  `I`-prefixed internal objects) or the input is empty/JMRI is unreachable.
  `tools/_common.py`'s `compact_turnout()`/`compact_light()`/
  `compact_signal()` are `async def` for this reason (they weren't before)
  and each add a `"dcc_system_name"` field via this resolver — `None`, not a
  fallback name, is the correct/expected value for internal objects, so
  callers must not treat it as an error. `jmri-cli` has its own independent
  display/formatting code for these three domains (`_row()`/`_headers()` in
  `turnout.py`/`light.py`/`signal.py` — it does not call the MCP `compact_*`
  functions), so parity needed a matching CLI-side implementation:
  `jmri_cli/_dcc_system.py`'s `system_names_by_prefix()` (fetches
  `get_systems()` once per command, returns `{prefix: name}`) and
  `dcc_system_display(system_id, names_by_prefix)` (prefix lookup, `"-"` on
  no match) — a simplified version of `roster.py`'s own
  `_system_names_by_prefix`/`_dcc_system_display` pair, simpler because
  there's no "unset, fall back to the default system" case to handle here.
  Every `turnout`/`light`/`signal` `list`/`find`/`findr`/`findg`/`status`
  subcommand shows a "DCC system" table column (or `dcc_system=` field for
  the single-entity `find`/`status`/`set` commands), and each domain gained
  a `bydccsystem` sort sibling.
- **Turnout/light/signal free-text comments.** JMRI returns a `comment`
  field (set in PanelPro's own object editor, e.g. "Yard throat switch" on
  a turnout) for turnouts, lights, and signal masts alike — static layout
  metadata, not live state, same treatment as `compact_block()`'s existing
  `comment` field. `compact_turnout()`/`compact_light()`/`compact_signal()`
  in `tools/_common.py` all pass it through verbatim (`None` if never set
  in PanelPro — not an empty string, not an error). `jmri-cli`'s
  `turnout.py`/`light.py`/`signal.py` show a "Comment" table column (empty
  cell when unset) and a `comment=` field on the single-entity
  `find`/`status`/`set` commands (`-` when unset, matching the "DCC
  system" column's own no-match convention) — each domain also gained a
  `bycomment` sort sibling. `turnout.py` already had this from an earlier
  pass; `light.py`/`signal.py` gained it to match.
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
either `userName` **or** the system name. Unlike `resolve_system()` there's
no default fallback — a light must be named, there's no single "the" light. `compact_light()` (in
`tools/_common.py`) prefers `userName` over the raw system name for
display/matching, falling back to the system name only if the user never
labeled the light in JMRI. Both MCP tool docstrings (`get_light`/
`set_light`) and the light-domain modules explicitly flag this
scenery-vs-headlight distinction so the LLM asks itself "did the user name
a place or a locomotive?" before picking a tool.

## `set_layout_lights`: every JMRI Light at once

`tools/light.py`'s `set_layout_lights(turn_on: bool)` loops `get_lights()`
and calls the existing `_set_light(name, turn_on)` per entry inside a
`try/except JmriError` — one light failing doesn't stop the rest
(catch-and-continue, the same shape as `set_all_turnouts` below). Returns
`{"succeeded": [...], "failed": [...]}`, each `succeeded` entry shaped like
`set_light`'s own return value (including `confirmed`) plus a `name`.

This is the native, server-side bulk tool required by the standing rule
that the LLM must never loop single-entity tool calls itself for a
whole-layout request — see the `_SERVER_INSTRUCTIONS` section below.
Routing is disambiguated by whether a locomotive is named in the request:
"turn on all the lights" (no loco mentioned) → this tool; "all of the
Autorail's lights" (a loco named) → `set_loco_lights`/`set_all_locos_lights`
(see the throttle tool surface section), never this one. Both docstrings
state the rule from both directions so the LLM doesn't have to infer it.

No new CLI code was needed for parity: `jmri-cli light on`/`light off`
already loop every light when `[name]` is omitted (see `docs/cli.md`) —
that pre-existing bare-verb behavior is exactly this tool's CLI
equivalent, confirmed by a regression test
(`test_light_on_bare_confirms_every_light` in `packages/jmri-cli/tests/test_cli.py`)
that both agree against the same fixture data.

## Turnouts: `list_turnouts` / `get_turnout` / `set_turnout`

`jmri_client/turnout.py` is a structural copy of `light.py`: JMRI's
`/json/turnouts` (list) and `/json/turnout/<name>` (single get/set), state
2=CLOSED/4=THROWN/0=UNKNOWN/8=INCONSISTENT (see `TURNOUT_STATE_NAMES`).
`set_turnout()` re-reads via `get_turnouts()` after the POST and reports
`confirmed` honestly, same contract as `set_power()`/`set_light()`.
`resolve_turnout()` uses the same tolerant case-insensitive exact-then-
fragment match as `resolve_light()` (fragment matching checks both
`userName` and the system name — see the note below), with no default
fallback (a turnout must be named).

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
`has_feedback_sensor` is true. `jmri_cli/turnout.py` mirrors this with a
"Feedback" (yes/no) column on `list`/`find`/`findr`/`findg`, and
`turnout close`/`throw`'s unconfirmed-state warning adds an extra note
when the unconfirmed turnout(s) are sensorless, for the same reason.

**Fragment matching against a JMRI system id.** All five non-roster
resolvers (`resolve_turnout`, `resolve_light`, `resolve_sensor`,
`resolve_signal`, `resolve_block`) had the same bug: the *exact*-match
branch already checked both `name` (system id, e.g. `"IT100"`) and
`userName`, but the *partial/substring fallback* checked only `userName` —
so a fragment of a system id (e.g. `"IT10"`, or any id whose `userName` is
unset) never matched even though the full id already resolved via exact
match. Fixed identically in all five files: the partial-match filter now
also checks `str(x.get("name", "")).casefold()`, one line per resolver.

## `set_all_turnouts`: every turnout to the same state at once

`tools/turnout.py`'s `set_all_turnouts(thrown: bool)` loops `get_turnouts()`
and calls the existing `_set_turnout(name, thrown)` per entry, catching
`JmriError` per turnout so one failure (a JMRI error, unsettled feedback)
doesn't abort the rest. Returns `{"succeeded": [...], "failed": [...]}`,
each `succeeded` entry shaped like `set_turnout`'s own return value
(including `confirmed`) plus a `name`.

**Sets every turnout to the SAME target state — this is explicitly not a
"restore each turnout to its own previous/default position" operation**;
there is no per-turnout memory to restore from. This ambiguity was raised
and resolved with the user before implementation and is pinned down in the
tool's own docstring (both to prevent relitigating it and so the LLM
doesn't infer the wrong semantics from the tool name alone).

Same native-bulk-tool rationale as `set_layout_lights` above: required so
the LLM never loops `set_turnout` itself for a "close/throw every turnout"
request. No new CLI code was needed — `jmri-cli turnout close`/`turnout
throw` already loop every turnout when `[name]` is omitted (see
`docs/cli.md`), confirmed by a regression test
(`test_turnout_throw_bare_confirms_every_turnout` in
`packages/jmri-cli/tests/test_cli.py`) that both agree against the same
fixture data.

## Sensors: `list_sensors` / `get_sensor` (read-only)

`jmri_client/sensor.py` mirrors `light.py`/`turnout.py`'s read side only —
`/json/sensors` (list) and `/json/sensor/<name>` (single get), state
2=ACTIVE/4=INACTIVE (0=UNKNOWN, 8=INCONSISTENT — see `SENSOR_STATE_NAMES`).
There is deliberately **no `set_sensor`**, in either `jmri_client/`,
`tools/`, or `jmri_cli/`: a sensor reports real-world state JMRI detects from
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

## Blocks: `list_blocks` / `get_block` (read-only, #35)

`jmri_client/block.py` mirrors `sensor.py`'s read-only shape —
`/json/blocks` (list), state 2=OCCUPIED/4=UNOCCUPIED (0=UNKNOWN,
8=INCONSISTENT — see `BLOCK_STATE_NAMES`) — but exposes JMRI's native
Layout Block object rather than a plain sensor. A block is richer than the
sensor-based occupancy already covered by `sensor.py`/#16: each entry also
carries `sensor` (the system name of the occupancy sensor driving it, e.g.
`"RS24"`) and `value` (whatever JMRI's reporting hardware — an RFID reader,
a `Reporter` — detected occupying the block, e.g. a roster entry or tag id;
verified live to be `null` on the user's layout, which has no such
hardware, but not guaranteed null in general). There is deliberately **no
`set_block`**, for the same reason as sensors: occupancy is detected from
real-world hardware, not a command this project should issue.
`resolve_block()` uses the same tolerant exact/fragment match as
`resolve_sensor()`.

Confirmed live against the user's real JMRI (`GET /json/blocks`): envelope
shape `{"type": "block", "data": {...}}` like every other domain, fields
`name`/`userName`/`comment`/`properties`/`state`/`value`/`sensor`/
`reporter`/`speed`/`curvature`/`direction`/`length`/`permissive`/
`speedLimit`/`denied` — this project surfaces only the subset relevant to
occupancy reporting (`name`, `state`, `sensor`, `value`) via `compact_block()`,
the same "compact for LLM output" treatment as every other list tool.

## Signal masts: `list_signals` / `get_signal` / `set_signal` (#26)

`jmri_client/signal.py` is a structural copy of `turnout.py`: JMRI's
`/json/signalMasts` (list) and `/json/signalMast/<name>` (single get/set).
Unlike turnout/light/sensor/block, a mast's state is not a small numeric enum —
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

**Welcome banner + per-leaf epilogs** (`jmri_cli/banner.py`, `jmri_cli/__init__.py`,
`i18n/en.json`'s `help.group.*` keys). Bare `jmri-cli`, `jmri-cli -h`, and
`jmri-cli --help` all print a byte-identical, non-technical welcome banner
(name, version via `importlib.metadata`, repo link, one-line purpose,
command list) instead of argparse's default technical help — no
implementation detail (`JMRI_URL`, "no MCP client" framing) belongs there.
Each top-level group gets a short, inviting one-liner via `i18n.t("help.group.<name>")`
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
  `roster`→`list`, `throttle`→`list`, `light`/`turnout`/`sensor`/`block`/`signal`→
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
throttle` calls. `jmri_cli/state.py` is a small local JSON cache
(`~/.jmri-cli/throttle_state.json`, keyed by DCC address) that every
throttle-touching command writes to and that `throttle list`/`speed`
(no value)/`stop` (no address) read from — a convenience cache the CLI
keeps for itself, not a live source of truth (see `docs/cli.md` for the
staleness caveat). This file, plus the interactive shell's own
`~/.jmri-cli/shell_history` (readline command history), are inspected and
cleared by `jmri_cli/cache.py`'s `cache info`/`cache clean` — see
`docs/cli.md` for the full command reference; neither touches JMRI, so
both work identically one-shot or from inside the shell.

`throttle on`/`off` with no function number resolves
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
  **`--hold` inside the shell also returns immediately**, unlike one-shot:
  `speed 3 60 --hold 10` prints an acknowledgement right away and hands the
  prompt straight back, while the ramp/hold/auto-stop sequence runs as a
  background `asyncio.Task` under the shell's shared connection (see
  `_common.run_hold_in_background`/`background_holds`) rather than blocking
  the caller for those 10 seconds. A second `--hold` on the same address
  supersedes (cancels) any hold already pending for it. Because `;` on one
  typed line is purely a line-separator with no waiting of its own (see
  "Multiple commands on one line" below), a `--hold` and a following
  command chained on the same line race unless `throttle wait [loco]` is
  inserted between them to block until the pending hold actually finishes.
  Any hold still pending when the shell exits is awaited to completion
  during shutdown rather than left to race the exit sequence.

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

**`shell.py`: bare `jmri-cli` launches it, not a subcommand.** `jmri_cli/__init__.py`'s
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

**Multiple commands on one line (`;`).** A typed (or piped) line is split
on `;` into a `pending_lines` queue before any of it is parsed; each
segment is then dispatched one at a time through the exact same
parse-then-`args.func(...)` path a normally-typed line uses — not a
separate inner loop, not special-cased dispatch. `;` is purely a
line-separator: it adds no waiting of its own between segments, and an
exit word (`exit`/`quit`/`bye`) among the segments stops processing the
rest of the line and exits immediately, same as typing it alone. Because
`--hold` returns immediately even inside the shell (see above), a `--hold`
and a following command chained on the same line race — e.g. `speed 4 20
--hold 5; release 4` releases the throttle right away, before the hold's
5 seconds are up, so the hold's own speed command then fails once it acts
on the now-released throttle (reproduced live, JMRI error "Throttles must
be requested with an address"). `throttle_wait(args, *, client=None)` in
`throttle.py` (backed by `_common.wait_for_holds`, which awaits either one
address's task from `background_holds` or every task currently pending,
suppressing `asyncio.CancelledError`) is the fix: it blocks until the
named locomotive's hold (or every pending hold, with no address given)
actually finishes, so a batch can sequence `speed 4 20 --hold 5; wait 4;
release 4` and have the release only ever run after the hold completes.
This is a distinct mechanism from `run_shell()`'s own shutdown-time
awaiting of every pending hold (see exit-confirmation below) — `wait` is
available mid-session, on demand, for any `;`-chained batch, not just at
exit.

**Sentence syntax (`speed`/`move`), shell-only.** `run_shell()` recognizes
two friendlier alternatives to `speed <loco> <pct> [--rampup U] [--hold H]
[--rampdown D]` before falling through to the ordinary `parser.parse_args()`
path — a pure syntax translation, not a new algorithm:

```
speed <loco> [at] <pct> [for D] [up D] [down D] [forward|reverse]
move  <loco> [forward|reverse] [at] <pct> [for D] [up D] [down D]
```

Detection is cheap and narrow: a line starting with `speed` is only
intercepted if at least one sentence keyword (`at`/`for`/`up`/`down`/
`forward`/`reverse`) is actually present (`_SENTENCE_KEYWORDS`), so a plain
`speed 3 40` is untouched and still goes through the normal shortcut/argparse
path below it. A line starting with `move` is *always* intercepted, since
`move` has no argparse leaf of its own — there is nothing to fall back to,
so a line that fails to parse prints `cli.shell_move_sentence_invalid`
directly instead of an argparse error.

`_parse_speed_sentence`/`_parse_move_sentence` (`shell.py`) tokenize the
line into the exact same `argparse.Namespace` shape `throttle speed`'s own
parser leaf produces (`loco`, `speed_percent`, `rampup`, `rampdown`,
`seconds`), plus a plain `direction: str | None` field that is *not* folded
into `speed_percent`'s sign — `for`→`seconds`, `up`→`rampup`, `down`→
`rampdown` are pure textual renames of `--hold`/`--rampup`/`--rampdown`,
and `_parse_duration` adds an optional `10s`/`5m`/`1h` unit suffix on top
of the existing plain-float-means-seconds convention (a bare number is
unchanged). `move`'s tokenizer differs only in argument order (loco, then
an optional leading direction keyword, then the same `[at] <pct> [for D]
[up D] [down D]` tail `_parse_speed_sentence` already parses — reused via a
direct call, not duplicated).

`_dispatch_speed_sentence` is deliberately **two independent, sequential
calls to the existing, unmodified `throttle_direction`/`throttle_speed`**
when a direction keyword is present — first `throttle_direction(forward=...)`
with a synthesized `Namespace(loco, rampup, rampdown, seconds=None)`, then
`throttle_speed` with the (always-positive) parsed speed Namespace. This is
exactly what typing `throttle forward <loco>` followed by `throttle speed
<loco> <pct> ...` as two separate lines would do — no address/prefix
resolution of its own, no acquire-to-read-current-direction step, and no
computed sign flip. An earlier implementation attempt did exactly that
(resolved the address, acquired the throttle, read its live direction, and
flipped `speed_percent`'s sign to match) and was rejected during review:
the sentence syntax's whole point is a friendlier *front end* for typing,
not a new decision-making layer, so direction is handled by literally
reusing `throttle_direction` rather than reimplementing what it already
does. Because the pre-flip `Namespace` always passes `seconds=None`, it
never backgrounds its own hold — only the second, `throttle_speed` call's
`seconds` (from `for`) can do that, matching a hand-typed `throttle forward
<loco>` immediately followed by `throttle speed <loco> <pct> --hold H`.

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

**TAB completion** (`_install_completer`, `_make_completer`, guarded by the
same `readline is None` check as history) derives its candidates from
`build_parser()`'s own argparse tree rather than a hand-maintained word
list, via two small helpers: `_subparsers_action(parser)` returns the
`argparse._SubParsersAction` directly below a given parser node (or `None`
at a leaf), and `_leaf_names(parser)` sorts its `.choices` keys. This is
deliberately not the same pattern as the pre-existing `_GROUP_NAMES`/
`_SHORTCUT_NAMES` module constants used for the front-page command list —
those are acceptable to hand-maintain since they're purely decorative help
text, but a functional completion feature drifting out of sync with the
real command tree would be a real bug, so it walks the tree directly
instead. `_make_completer(parser)` closes over the parser once and returns
readline's expected `complete(text, state)` signature: on every TAB press
it re-slices `readline.get_line_buffer()` up to `readline.get_endidx()`
(the text left of the cursor, ignoring anything after it), re-tokenizes
with the same `shlex.split()` the real dispatch path uses (falling back to
plain `.split()` on `ValueError`, since TAB is pressed mid-edit — with
unbalanced quotes — far more often than on a fully-valid line), then walks
the parser tree one token at a time via `_subparsers_action` to find which
node the cursor is currently under — skipping any token that starts with
`-` (a flag, or a value already consumed by one) during the walk, since
those don't advance which subcommand node the cursor is under; hitting an
unrecognized *positional* token stops the walk (`break`, not an early
`return None`) rather than discarding all completions, so a value already
typed (a loco address, a percentage) doesn't prevent that node's own
flags from still being offered afterward. Once the word being completed
starts with `-`, the candidates are that node's own `--flag`/`-f` strings
(`_option_strings`, reading `parser._optionals._group_actions` the same
way `_leaf_names` reads the subparsers action — e.g. `--rampup`/
`--rampdown`/`--hold` on `throttle speed`); at the top level they're
groups + shortcuts + `exit`/`quit`/`help`; anywhere else (a leaf, with the
in-progress word not yet starting with `-`) they're the union of that
node's own `_leaf_names` (usually empty for a true leaf) and its
`_option_strings` — a bare TAB right after `throttle speed 3 40`, with
nothing typed yet, must still offer `--rampup`/`--rampdown`/`--hold`, not
just once the user has already typed a literal `-`. Either way, candidates
are filtered by the in-progress word's prefix and returned one at a time
as `state` increments, per readline's completer contract — except when
exactly one candidate matches, where `complete()` appends a trailing space
to it before returning: GNU readline was found empirically (via a real
pseudo-terminal, not just its documented behavior) to not reliably
auto-append one itself in this project's target environments, and without
it the next character typed lands glued to the tail of the just-completed
word (e.g. "throttle spe"+TAB+"3" producing "throttle speed3" instead of
"throttle speed 3"). `_install_completer` also strips `-` from
`readline.get_completer_delims()`'s default set — GNU readline treats
delimiter characters as word boundaries for completion purposes, and `-`
being one by default splits a flag like `--rampup` into a bare word after
the dashes, breaking prefix matching against `_option_strings`.

**Ramping** (`ramp_speed`, `execute_speed_change`, both in the shared module
`jmri_ws/ramp.py` — moved out of `jmri_cli/throttle.py` when `tools/throttle.py`
gained its own ramped MCP tool, see "Ramped speed changes over MCP" below;
`jmri_ws/` has no dependency on `jmri_cli/`, so this is the correct lowest-common
home for logic both surfaces need, keeping `tools/` from ever importing
`jmri_cli/`-private code). `ramp_speed` is the shared linear-ramp primitive:
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
distinct command from a controlled stop). `stop`/`emergency_stop`, and
`set_speed` when called without its optional `direction` argument, go
through `JmriWsClient.set_speed()` directly; `set_speed` with `direction`
given instead routes through `jmri_ws.ramp.execute_speed_change` (see
"Ramped speed changes" below) so speed and a direction flip land as one
atomic call. `set_direction`
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

### `direction` parameter: setting speed and direction atomically

Speed and direction are independent JMRI decoder commands — a plain speed
change never touches direction. This surfaced as a real bug: telling the
assistant "avance" (forward) while a locomotive was moving in reverse just
increased speed magnitude in whatever direction it already faced, since
nothing called `set_direction` and no tool let the LLM set both together.
Both `set_speed` and `set_speed_ramped` now take an optional `direction`
("forward"/"reverse", case-insensitive) so a combined request sets both in
one server-guaranteed call — `_SERVER_INSTRUCTIONS`' "Direction routing"
paragraph tells the LLM to always prefer this over chaining a separate
`set_direction` call. Both route through `execute_speed_change` when
`direction` is given (`set_speed` with `rampup=rampdown=0` for an instant
flip; `set_speed_ramped` with its own rampup/rampdown), which already
ramps to 0 before flipping if the locomotive is moving the other way —
no new ramp/flip logic was needed, this is the same primitive
`set_speed_ramped` already used for its pre-existing negative-`speed_percent`
CLI shorthand ("flip whichever direction the loco currently faces, then
go at |value|%" — a toggle relative to current state, not an absolute
"always reverse").

`set_speed_ramped` keeps that legacy shorthand for backward compatibility,
but only consults it when `direction` is omitted — an explicit `direction`
always wins. When both are given, `speed_percent`'s magnitude is *clamped*
(`max(0, min(100, speed_percent))`), not `abs()`'d: `direction="reverse",
speed_percent=-40` yields 0%, not 40%. This is deliberate — mixing the old
sign idiom with the new explicit parameter is almost certainly a caller
mistake, and failing loud (0% speed) is safer than silently guessing which
idiom was meant. `set_speed`'s return dict gains a `"direction"` key only
when `direction` was passed as an argument, keeping the old 2-key shape
byte-for-byte unchanged for every existing caller that never uses it.

### Long holds run in the background, not inline

Blocking the MCP tool call for the full `hold_seconds` duration (above)
turned out to cause a second, distinct problem once LLM routing to this
tool actually worked: a voice client (Kira/xiaozhi) sits completely silent
for the whole wait, since nothing is returned until the call finishes, and
xiaozhi's own conversation-turn timeout can fire before a long hold (e.g.
10s) completes — even though the ramp itself was working correctly
server-side the whole time. The fix is a threshold, not a client-side
change (nothing in this repo can alter xiaozhi's own turn timeout — see
`packages/jmri-mcp/src/xiaozhi_wrapper`'s bridge, which has no
request-level timeout of its own and simply relays whatever `jmri-mcp`
writes to stdout, whenever it arrives):

- `rampup_seconds + hold_seconds + rampdown_seconds` at or below
  `jmri_core.constants.client_tuning.RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS`
  (4.0s): unchanged, blocks and returns the real final speed/direction.
- Above that threshold: `tools._common.run_in_background()` schedules
  `execute_speed_change(...)` as an `asyncio.Task` on the shared, process-wide
  `JmriWsClient` (the same connection the tool call was about to use
  inline), and the tool returns immediately with `{"address", "status":
  "started", "speed_percent", "direction", "seconds_total"}` — the ramp,
  hold, and auto-stop keep running after the response is sent. The
  locomotive still stops itself automatically; nothing further is required
  from the caller.

`run_in_background` keeps a strong reference to each task in a module-level
`background_tasks: set` (asyncio only weakly references bare
`create_task()` results, so an untracked task risks silent garbage
collection mid-ramp) and self-removes on completion via
`task.add_done_callback`. `server/__init__.py`'s `_run()` awaits whatever's
left in `background_tasks` in its shutdown `finally`, before closing the
`JmriWsClient` — so a clean server exit lets an in-flight background ramp
finish (or at least run its cancellation/rampdown path) rather than
abandoning the locomotive mid-ramp.

`_SERVER_INSTRUCTIONS` (see below) explicitly tells the LLM that
`"status": "started"` is a normal success acknowledgement, not a dropped
request or a failure — without this, an LLM seeing a non-final-looking
response for what it expected to be a blocking call could plausibly retry
or report an error.

## `set_loco_lights` / `set_all_locos_lights`: every light-labeled function, not just F0

`tools/throttle.py`'s `set_loco_lights(address, state)` is different from
`lights_on`/`lights_off` (which only ever touch F0): it reads the
locomotive's roster function *labels* (`jmri_client.get_roster_function_labels`,
the same source `get_locomotive_functions` uses) and calls the existing
`set_function(address, n, state)` — same-module closure call, the
established precedent from `lights_on`/`lights_off` — for every function
number whose label matches `jmri_core.constants.lighting.is_light_label`
(keywords like light/lamp/headlight, lumière/feu/lampe/phare,
case-/accent-insensitive via `jmri_core.text.fold`). Motivating example,
verified against this layout's real roster: the Autorail has F0="Lumières
avant", F1="Lumières cabine", F2="Lumières arrière" — all three are
light-labeled, so "turn on all the Autorail's lights" must flip all three,
not just F0. Each function switch is attempted independently
(catch-and-continue), returning `{"address": ..., "applied": [{"function",
"label", "state"}...], "failed": [...]}`. A locomotive with **no**
light-labeled functions is not an error: `applied` is empty and a `"note"`
explains why (most locos have no roster labels set at all — see the M3
roster work), so the LLM falls back to asking for an explicit F-number only
in that case, not on every call.

`set_all_locos_lights(state)` loops every address this MCP session
currently holds a throttle for, via `JmriWsClient.all_throttle_states()`
(the client's public accessor — not the private `_throttles` dict some
older code reaches into), calling `set_loco_lights` per address and
returning `{"locomotives": [<one set_loco_lights result per address>]}`.
Same scope limitation as `emergency_stop_all`, stated explicitly in its
docstring: only locomotives this session has acquired are reachable, not
every locomotive on the layout. Returns `{"locomotives": []}`, not an
error, if nothing has been acquired yet.

Both are the native, server-side bulk tools required by the standing rule
against the LLM looping single-entity tool calls itself (see
`_SERVER_INSTRUCTIONS` below). Routing is the mirror image of
`set_layout_lights`: a lighting request that **names a locomotive** routes
here; one that doesn't routes to `set_layout_lights` instead. Both tools'
docstrings state this rule from both directions.

CLI parity is a single `--lights-only` flag on `throttle on`/`throttle off`,
in `jmri_cli/throttle.py`: it filters `_resolve_function_numbers`'s label
lookup through `is_light_label` before falling through to the existing
`_throttle_set_functions`. Combined with `on`/`off`'s own "loco optional,
defaults to `state.py`'s local touched-address cache" behavior (see the CLI
parity paragraph in the `prepare_locomotive`/`park_locomotive` section below),
`throttle on --lights-only`/`throttle off --lights-only` with no loco is the
CLI equivalent of `set_loco_lights` (one address) or `set_all_locos_lights`
(every touched address) depending on whether `[loco]` is given — there is
no separate bulk verb; a locomotive with no light-labeled functions is
skipped with a printed note rather than treated as a failure when acting on
every touched address, and an empty cache prints a note and exits 0,
mirroring `set_all_locos_lights`'s `{"locomotives": []}` case.

## `prepare_locomotive` / `park_locomotive` / `park_all_locomotives`: session on/off for a locomotive

`tools/throttle.py`'s `prepare_locomotive(address, prefix=None)` and
`park_locomotive(address)` are single-call counterparts covering the
"wake up"/"put to bed" case for one locomotive, so the LLM never has to
chain acquire/direction/lights/speed/release calls itself.

`prepare_locomotive` runs three steps: acquire the throttle, flip to
forward only if not already facing that way (`data.get("forward", True)`
— avoids an unnecessary direction call when already forward), and call
`set_loco_lights(address, True)`. It does not touch speed — waking a
locomotive up is distinct from starting it moving.

`park_locomotive` runs four steps: ramp down to speed 0 via the shared
`execute_speed_change` (see the ramping section below) with duration
`current_fraction * STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED`
(`jmri_core.constants.client_tuning`, 3.0s) — proportional to the
locomotive's speed at the moment the call starts, so an already-slow or
stopped locomotive doesn't wait through a fixed delay with nothing to
ramp down from, and a locomotive at full speed still gets a smooth,
bounded stop. This is deliberately capped below
`RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS` (4.0s) so `park_locomotive`
can stay a simple blocking call, unlike `set_speed_ramped`'s
background-task path. After the ramp: flip to forward (always safe here,
since speed is 0 by construction), turn off every light-related function
via `set_loco_lights(address, False)`, then release the throttle.

If this session never acquired the locomotive, the ramp/direction step is
skipped entirely (nothing to stop) — but the lights step still runs and
auto-acquires the throttle the same way `set_loco_lights`/`set_function`
always does, so the release step always has something to release
regardless of the starting state, and nothing is left dangling either
way. The returned dict is honest about total failure: if both the lights
step and the release step failed (e.g. JMRI unreachable throughout), a
top-level `"error"` key is set rather than reporting `"released": true`
with no basis for it.

`park_all_locomotives()` is the bulk counterpart, looping
`park_locomotive` over every address `JmriWsClient.all_throttle_states()`
currently holds — same scope limitation as `emergency_stop_all`/
`set_all_locos_lights` (only reaches locomotives this session has
acquired), same `{"locomotives": []}` empty case.

CLI parity in `jmri_cli/throttle.py`: `throttle_engine_start` (verb
`engine-start`) and `throttle_engine_stop` (verb `engine-stop`), both
with `loco` optional. This is the same "loco optional, defaults to
`state.py`'s local touched-address cache" pattern shared by seven of the
eight throttle verbs — `on`, `off`, `stop`, `estop`, `forward`, `reverse`,
`engine-start` (`engine-stop` already had it) — each implemented as a
small per-address helper (`_engine_start_one`, `_set_functions_one`,
`_direction_one`, and `stop`'s/`estop`'s own inline loop bodies) looped by
the public `throttle_<verb>` function over either `[resolved_address]` (an
explicit `loco` given) or every address in the cache (`loco` omitted), so
one address failing doesn't abort the rest. None of the seven is
loco-mandatory inside the interactive shell: with no `loco`, all fall back
to the same disk-persisted cache — the same population bare `throttle`'s
status table and each other already use — regardless of whether `client`
is set (shell) or `None` (one-shot). That cache, not the shell's own
in-memory `client.all_throttle_states()`, is what "every known locomotive"
means to a user driving from the shell: it's what bare `throttle` itself
already shows them, and it survives shell restarts (an in-memory-only
source would silently go empty on every new shell process, contradicting
what the status table just displayed). **`throttle_speed` is the sole
exception**: it always requires an explicit `loco`, since a bare speed
target has no unambiguous "apply this same percentage to everything
known" reading the way a stop/estop/direction-flip/function-toggle does.
`throttle_engine_start`/`throttle_engine_stop` additionally merge what
were originally separate single-address/bulk functions into one,
mirroring `throttle_stop`'s own established "optional trailing loco = one
vs. all" idiom rather than a separate bulk verb or an `--all` flag. CLI
verbs are named `engine-start`/
`engine-stop` rather than `start`/`stop`-alone or `power-on`/`power-off`
specifically to avoid colliding with the pre-existing `power on/off`
verb — DCC system power (the whole layout) and one locomotive's own
throttle/lights are different concepts, and a name collision here risks
the LLM confusing the two, not just CLI readability. The MCP tool names
(`prepare_locomotive`, `park_locomotive`, `park_all_locomotives`) use
different words again, for the same reason applied one level further: an
LLM routing a voice/chat request also needs to distinguish a session
start/end from `stop`/`emergency_stop` (speed-only, mid-run) — a bare
"stop" in the tool name risked exactly that confusion in practice. The
CLI's `engine-*` verbs and the MCP tools' `prepare`/`park` names are not
required to match each other; each was chosen to avoid collisions within
its own surface. The one-shot CLI's `engine-stop`
acquires the throttle explicitly before its lights step, unlike the MCP
tool's `set_loco_lights`/`set_function`, which auto-acquire internally —
a fresh one-shot connection never already holds a throttle, so without an
explicit acquire here JMRI would reject the function calls with
"Throttles must be requested with an address."
(caught by `test_throttle_engine_stop_never_acquired_still_turns_off_lights_and_releases`).

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

## `set_power`: OFF/wait/ON recovery when a power-ON lands in UNKNOWN

A second, distinct UNKNOWN failure mode from the redundant-POST bug
above: a command station can also reject or lose a genuine ON request,
landing the post-POST re-read on state UNKNOWN instead of ON — and it
does not self-recover from this on its own.

When `set_power(prefix, turn_on=True)`'s post-POST re-read observes
UNKNOWN, it posts OFF for that system, waits
`POWER_UNKNOWN_RECOVERY_DELAY_SECONDS`, then retries ON once more and
re-reads. Only one retry is attempted — a second failure is still
reported honestly via `confirmed: False` rather than retried
indefinitely. This recovery path only triggers for `turn_on=True`; a
power-OFF that lands in UNKNOWN is reported honestly with no retry, since
the recovery cycle itself ends in an ON state and would contradict the
caller's OFF request.

Every caller of `set_power` (the MCP tool, `jmri-cli power on`/`off`, and
`_set_power_all` behind `power_off_all`/`power_on_all`) inherits this
recovery automatically, same as the redundant-POST guard above.

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
with no `loco` given, it reads every address key out of `jmri_cli/state.py`'s
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
shared loop — same reasoning as `_power_set(args, turn_on)` in `jmri_cli/power.py`
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

Concise, no-narration responses are the **server-wide default**, set via
`_SERVER_INSTRUCTIONS`' "Response style" paragraph (see the section below)
— delivered once at `initialize`, before any tool has been called, so
terse responses hold from the very first turn without the LLM or user
having to ask for them. `tools/mode.py` exists only for the opposite
direction: letting the user explicitly ask for normal, explanatory
responses instead ("explain more", "stop being so terse"), and switch back
afterward if they want concise again.

MCP's `instructions` field is static and one-shot — set once at server
construction, delivered once at `initialize`, no way to update
mid-conversation — so it cannot by itself carry a flag that flips
mid-session once the user asks to change the response style.
`@mcp.prompt()` is dynamic but opt-in and client-controlled (e.g. a user
must manually invoke it as a slash command in Claude Desktop), not
something a tool call can force either. The only mechanism actually
available to a tool at any point in the conversation is its own **return
value**, since the LLM reads every tool result before deciding what to say
next.

So "executor mode" is a module-level flag, `_executor_mode` — process-wide
is correct here, not a bug, because this MCP server runs one process per
stdio client session, so there's no cross-session leakage to worry about.
It **starts `True`**, matching `_SERVER_INSTRUCTIONS`' concise-by-default
behavior, so a fresh session needs no tool call to already be terse.
`set_executor_mode(enabled)` flips it and returns an explicit natural-
language instruction string (either the terse one — no narration, no
restating the request, report outcomes only — or, for `enabled=False`, one
telling the LLM to resume normal explanations); `get_executor_mode()`
re-delivers the same instruction for whichever state is current, for a
caller unsure whether it's still active after a long gap. The instruction
is re-delivered on every call rather than sent once and assumed to
"stick," since there's no system-prompt-level way for this server to keep
reminding the LLM otherwise — this is a behavioral nudge via tool output,
not an enforced constraint.

`mode.py` deliberately has **no `jmri_client`/`jmri_ws` counterpart and no
`jmri_cli/` equivalent** — it holds no JMRI state and makes no JMRI calls at
all, so there's nothing for a one-shot `jmri-cli` process to usefully
exercise; the whole point of the flag is that it persists across tool
calls within one long-lived MCP session, which a fresh CLI invocation
never has.

## Exhibition mode: `enter_exhibition_mode` / `exit_exhibition_mode` / `get_exhibition_mode`

A restricted-safety mode for public demos — exhibitions, kids trying voice
control — where the layout must stay safe to operate unsupervised. Same
module-level, process-wide flag pattern as executor mode above
(`_exhibition_mode` in `tools/mode.py`, read via `is_exhibition_mode()` so
callers always see the live value rather than a stale import-time copy),
but **asymmetric** rather than a single toggle: `enter_exhibition_mode()`
takes no arguments and is always callable, while `exit_exhibition_mode
(password)` requires a password so a member of the public can't casually
turn the restrictions back off. The password comes from
`get_exhibition_password()` (`jmri_core.config`, `EXHIBITION_PASSWORD` env
var), defaulting to `"this is sparta"` if unset — not a real security
boundary, just a deterrent against casual tampering during a demo. A wrong
password leaves the flag unchanged and returns an honest error plus an
instruction telling the LLM not to guess or reveal the password. The
password comparison is tolerant (case/accent/whitespace-insensitive, via
`jmri_core.text.fold`, the same helper used for locomotive name matching)
since this password is normally spoken aloud through voice transcription
rather than typed — an exact-match comparison turned out to be too brittle
in practice (an operator's spoken password can come back transcribed with
different capitalization or stray whitespace).

`_exhibition_mode` can also start already `True` instead of the normal
`False` default, via `get_exhibition_start_on()` (`jmri_core.config`,
`EXHIBITION_START_ON` env var — any of `"1"`/`"true"`/`"yes"`/`"on"`,
case-insensitive) — read once at module-import time, so an exhibition
host can configure this once at `.mcpb` install time instead of having to
say "passe en mode exposition" at the start of every session. Test
isolation (`reset_exhibition_mode` in `tests/conftest.py`) always resets
to `False` regardless of this env var, since tests must not depend on
whatever happens to be set in the environment they run in.

While active, exhibition mode enforces four restrictions, each checked at
the point closest to where it applies rather than in a central gate:

- **Power stays on-only-by-cut**: `set_power(turn_on=True)` and
  `power_on_all` (`tools/power.py`) raise `exhibition_power_restricted`
  before touching JMRI. `set_power(turn_on=False)` and `power_off_all` are
  untouched, so an emergency power cut always stays available.
- **Every locomotive moves forward-only, at one fixed speed**:
  `set_speed`/`set_speed_ramped` (`tools/throttle.py`) overwrite whatever
  `speed_percent`/`direction` was requested with
  `EXHIBITION_SPEED_PERCENT` (`jmri_core.constants.client_tuning`, 30%) and
  `"forward"` right after acquiring the client, before any of the normal
  speed logic runs — so the override is transparent to the rest of the
  function, and the caller still gets a normal-shaped success response
  rather than an error (the request "worked", just not at the speed
  asked). `set_direction(direction="reverse")` is refused outright with
  `exhibition_reverse_restricted` instead, since there's no speed value to
  fall back to that would make "moving anyway" true.
- **DCC addresses can be allow-listed**: `get_exhibition_allowed_addresses()`
  (`jmri_core.config`, `EXHIBITION_ALLOWED_ADDRESSES` env var, comma-
  separated integers) returns `None` when unset, meaning no address
  restriction even while exhibition mode is otherwise active.
  `check_exhibition_address_allowed()` (`tools/_common.py`) is called from
  `ensure_acquired()` on first acquire of an address (covering every
  throttle tool's auto-acquire path, not just `acquire_throttle` itself),
  so a disallowed address is rejected before any WebSocket traffic is sent
  for it.
- **Lights and functions are intentionally NOT restricted** — an exhibition
  visitor toggling headlights or a bell is part of the demo, not a safety
  concern.

`_SERVER_INSTRUCTIONS` (see the `server/__init__.py` section below) routes
French/English enter/exit phrases to these three tools and tells the LLM
to report the speed/power restrictions honestly rather than retry or claim
failure.

**No `jmri-cli` equivalent** — a deliberate, user-decided exception to this
project's usual CLI-parity rule. Exhibition mode is a flag on the
long-lived MCP server process; `jmri-cli` is one-shot per invocation with
no persistent state to hold it, and exhibition mode's whole premise
(restricting a general public audience interacting by voice/chat) has no
realistic CLI usage scenario — anyone with CLI access already has direct
access to the layout.

## `meta.py`: layout-wide tools composing several low-level operations into one call

`tools/meta.py` holds seven tools that answer a request shaped around the
whole layout rather than one system/locomotive: `layout_status`,
`secure_layout`, `release_all_locomotives`, `night_mode`, `day_mode`,
`start_session`, `end_session`. Each is a natural-language-sized command
a model railroader would actually give another operator ("what's
happening?", "secure the layout") rather than the sequence of individual
JMRI calls that implements it.

**Cross-module composition constraint.** `@mcp.tool()`-decorated
functions are closures created inside each module's own `register(mcp)`
call, not plain importable module-level functions — `park_all_locomotives`
can call `park_locomotive` directly only because both are defined in the
same `register()` scope in `throttle.py`. `FastMCP` itself exposes no API
to look up and invoke an already-registered tool as a plain callable from
another module (only `add_tool`/`call_tool`/`list_tools`/`remove_tool`/
`tool` exist, and `call_tool` requires JSON-serialized arguments and
returns protocol-wrapped content blocks — the wrong shape for internal
composition). So `meta.py` cannot import `set_loco_lights` from
`throttle.py` or `set_layout_lights` from `light.py` and call them
directly. Instead it composes on the same low-level `jmri_client`/
`jmri_ws` functions every other tool module builds on — exactly the
existing convention that `light.py` and `turnout.py` already follow
(sibling tool modules never import each other, each composes
independently on the shared client layer). `meta.py` reimplements a
private `_set_loco_lights(address, state)` helper, field-for-field
identical in output shape to `throttle.py`'s `set_loco_lights` tool
(same `applied`/`failed`/`label`/`note` keys), rather than depending on
that module.

`layout_status()` is read-only: version + reachability, every DCC
system's power state, every locomotive this session currently holds a
throttle for (via `JmriWsClient.all_throttle_states()`), every block, and
every sensor. Each section is fetched independently and wrapped in its
own `try/except JmriError`, so one JMRI subsystem being unreachable
(e.g. `/json/blocks` erroring) reports a `<section>_error` key for that
section alone without blocking the others — the same
independent-failure-reporting shape used elsewhere in this codebase
(`secure_layout`'s per-locomotive/per-light loops below). If JMRI itself
is unreachable, the function returns immediately after `version` fails,
with `reachable: False` and a top-level `error`, since nothing else is
worth attempting.

`secure_layout(release_throttles=True)` is the "I'm done for today"
command: for every address this session holds a throttle for, it ramps
speed down to 0 via the same shared `execute_speed_change` state machine
`park_locomotive` uses (`rampdown = current_fraction *
STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED`, proportional to current
speed), turns off that locomotive's light-labeled functions via
`_set_loco_lights`, and — unless the caller passes
`release_throttles=False` — releases the throttle. It then turns off
every JMRI Light on the layout via `get_lights()`/`set_light()`,
reporting `succeeded`/`failed` per light the same way `set_layout_lights`
does. This is deliberately distinct from both existing whole-layout stop
tools: `power_off_all` cuts power (reaching locomotives with no throttle
held here too, but a more drastic, harder-to-undo action) and
`emergency_stop_all` only stops motion (no lights, no release, no
controlled ramp — a decoder e-stop). `secure_layout` is the routine,
gentle "put everything away" tool; the other two remain for their own
distinct cases (see their own sections above). Its scope is the same as
`park_all_locomotives`/`emergency_stop_all`: only locomotives *this*
session has acquired a throttle for.

`release_all_locomotives()` releases every held throttle without
touching speed, direction, or lights at all — the narrow case where a
user wants to hand control back (e.g. to a JMRI panel or another
session) without changing anything about the layout's current state,
distinct from `secure_layout`'s full shutdown sequence.

`night_mode()`/`day_mode()` share a private `_set_mode_lights(loco_state,
layout_state)` helper: turn every acquired locomotive's light-labeled
functions and every JMRI Light on or off together, in one call.
`night_mode()` is `_set_mode_lights(True, True)`, `day_mode()` is
`_set_mode_lights(False, False)` — thin wrappers, same shape as
`power_off_all`/`power_on_all` sharing `_set_power_all`. Like
`secure_layout`, the locomotive side only reaches this session's
currently-acquired addresses; a locomotive never acquired here keeps
whatever light state it already had.

`start_session()` powers on every DCC system (`power_on_all`, refused
under the same `is_exhibition_mode()` restriction that tool itself
enforces), then, for every address this session already holds a
throttle for, faces it forward (only if needed) and turns on its
light-labeled functions via `_set_loco_lights` — the same steps
`prepare_locomotive` runs, one address at a time. Unlike the CLI's
`session-start` (below), it has no roster-wide "every locomotive you
usually drive" fallback: MCP sessions have no equivalent of the CLI's
disk-persisted touched-address cache, only whichever throttles are
already acquired in memory, which is typically none at the very start of
a fresh session — not an error, just a no-op locomotive step. Follow up
with `prepare_locomotive`/`acquire_throttle` once a locomotive is named.

`end_session()` is `start_session`'s inverse and shares `secure_layout`'s
per-locomotive loop (ramped stop, lights off, release — one locomotive's
failure doesn't block the rest), but skips the layout-lights step and
appends `power_off_all` afterward, strictly after every locomotive has
been stopped so power is never cut mid-motion. It is deliberately
narrower than `secure_layout` (no layout lights) and safer than calling
`power_off_all` alone (which cuts power without a controlled stop
first). An empty session reduces it to `power_off_all` alone.

**CLI equivalent, unlike the other five tools.** `jmri-cli session-start`
/`session-end` (`jmri_cli/session.py`) implement the same idea but
against the CLI's own primitives and scope: `power on`/`power off` plus
`throttle engine-start`/`engine-stop`/`stop`, each falling back to
`state.py`'s disk-persisted touched-address cache (not an in-memory
acquired-throttle set) when no locomotive is named — the one CLI-side
difference from the MCP tools' scope, since the CLI has no long-lived
session to hold throttles across process restarts the way MCP does. Pure
orchestration: no new low-level throttle/power logic, just the existing
`power`/`throttle` module functions called in sequence with an
`argparse.Namespace(...)` built locally rather than routed through
argparse dispatch. Works identically one-shot or from the interactive
shell — `session_start`/`session_end` match the shell's established
`async def f(args, *, client=None)` signature convention
(`shell.py`'s `_is_ws_func` detects the `client` keyword and injects the
shared connection automatically), so no shell.py changes were needed, the
same way issue #45's shortcuts worked "for free."

No CLI equivalent was added for the other five tools: `layout_status` is
a read aggregation the CLI already exposes piecemeal (`status`, `roster`,
`turnout list`, `sensor list`, `block list`), and `secure_layout`/
`release_all_locomotives`/`night_mode`/`day_mode` all assume a
long-lived session holding multiple throttles at once — the CLI's
one-shot commands don't have that (see the `throttle speed` connection-
lifetime limitation documented above), and its interactive shell already
covers the same ground per-address via the existing `throttle stop`/
`engine-stop`/`light on`/`light off` verbs with no `loco` argument.

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
`FastMCP("JMRI", instructions=_SERVER_INSTRUCTIONS)`. Content started
scoped to exactly one thing — mapping the four whole-layout, no-argument
tools to the French/English phrases that should trigger them
(`emergency_stop_all`, `power_off_all`, `power_on_all`, `set_executor_mode`
— the last one's mapped phrases later narrowed, see "Response style" below,
once conciseness became the default rather than something to opt into)
— without this, the LLM has no signal connecting a generic, no-target-named
command like "arrête tout" to the right tool until it has already read
that tool's own docstring, which only happens if it guesses to look there
first. This is still deliberately narrow: a general safety reminder (e.g.
about unauthorized motion commands) and general project context were both
considered and left out, kept instead in `CLAUDE.md`/this repo's docs, not
the MCP protocol payload.

A **"Response style" paragraph** was later prepended, ahead of all the
others: concise, no-narration responses are the default from the very
first turn of every conversation (see "Executor mode" above), so the LLM
doesn't need to be told or asked before responding tersely — the standing
default lives here specifically because `instructions` is the one channel
guaranteed to reach the LLM before its first response, unlike a tool's own
docstring (only read once that tool is called) or `set_executor_mode`
(only reachable via an explicit call the LLM would have no reason to make
on a fresh session that's already meant to be terse).

Card #34 added three more paragraphs to `_SERVER_INSTRUCTIONS`, in direct
response to real user friction, not hypothetical:
- **Act, don't recite** — when a tool call fails on an unrecognized name
  (`unknown_entity`/`ambiguous_entity`), the instruction tells the LLM not
  to read the tool's full available-entity list back to the user as its
  answer (the user's own words: "un enfer d'inutilité" — a hell of
  uselessness), and to ask one short clarifying question instead. This is
  the behavioral half of the `i18n` list-capping fix above — capping bounds
  the *payload*, this paragraph addresses what the LLM *does* with it.
- **Bulk routing** — any request naming "all"/"every"/"tout(e)(s)" must go
  to the matching whole-layout tool (now seven: `power_off_all`,
  `power_on_all`, `emergency_stop_all`, `set_all_turnouts`,
  `set_layout_lights`, `set_loco_lights`, `set_all_locos_lights`) in ONE
  call — the instruction states explicitly that looping a single-entity
  tool (`set_turnout`, `set_light`, `set_function`, ...) itself is wrong,
  not just slow, since that is exactly the failure mode ("turn off all
  locos" needing the user to insist/repeat) that motivated building these
  tools as native and server-side in the first place.
- **Loco-lights disambiguation** — restates, at the protocol-instructions
  level, the same rule each tool's own docstring states: naming a
  locomotive routes to `set_loco_lights`/`set_all_locos_lights`; not naming
  one routes to `set_layout_lights`. Stated in both places deliberately,
  same reasoning as the power/emergency_stop "NOT interchangeable" clause
  below — a single mention doesn't reliably win against pattern-matching.
- **Duration routing** — added after a real user report ("le LLM ne
  comprend pas quand je lui parle de durée genre avance pendant 10s"):
  `set_speed_ramped` with `hold_seconds` already existed and already
  handles a duration entirely server-side (wait + auto-stop, before the
  tool call returns), but nothing pointed the LLM at it for a plain "run
  forward for 10 seconds" request — it would reach for `set_speed` first
  (the obvious match for "speed"), find no duration parameter there, and
  either give up or try to time a separate stop call itself. This
  paragraph states the routing rule explicitly ("a duration always means
  set_speed_ramped's hold_seconds, never plain set_speed + a separately-
  timed stop"), and `set_speed`'s own docstring got the same forward
  pointer, so whichever tool the LLM reads first still leads to the right
  one. This routing fix surfaced a second, previously-latent problem: once
  the LLM correctly reached `set_speed_ramped`, a long `hold_seconds` blocked
  the tool call long enough to trip Kira/xiaozhi's own conversation-turn
  timeout (reported live: "le LLM continue d'indiquer qu'il tente de faire
  rouler pendant x secondes puis me dit timeout"). Fixed by the background-
  task path described above ("Long holds run in the background, not
  inline"), plus a matching instructions paragraph telling the LLM that a
  `"status": "started"` reply is a normal success, not a timeout or dropped
  call — a routing fix alone couldn't have caught this, since the symptom
  only exists once routing already works.

- **Session on/off routing** — added alongside `prepare_locomotive`/
  `park_locomotive`/`park_all_locomotives` (see the dedicated section
  above): maps "allume la loco"/"start up the 3"/"wake up the autorail" to
  `prepare_locomotive`, "éteins la loco"/"put the 3 to bed"/"shut down the
  autorail" to `park_locomotive`, and "éteins toutes les locos"/"shut down
  every locomotive"/"put everything to bed" to `park_all_locomotives`
  (never a loop of `park_locomotive` calls). Explicitly tells the LLM
  never to chain acquire_throttle/set_direction/set_loco_lights/
  set_speed(_ramped)/release_throttle itself for any of these three
  requests — each already has one native tool, the same rationale as the
  bulk-routing paragraph above.
- **Meta-tools routing** — added alongside `meta.py` (see its dedicated
  section above): maps a general status question ("what's happening on
  the layout", "donne-moi l'état du layout") to `layout_status`, an
  end-of-session command ("secure the layout", "sécurise le layout") to
  `secure_layout`, a throttle-only handback ("release the locomotives",
  "libère les locos") to `release_all_locomotives`, and a whole-layout
  lighting mode ("night mode"/"mode nuit", "day mode"/"mode jour") to
  `night_mode`/`day_mode`. Explicitly restates `secure_layout`'s
  distinction from `power_off_all`/`emergency_stop_all` here too, same
  reasoning as the power/emergency_stop "NOT interchangeable" clause
  below.
- **Exhibition mode routing** — added alongside `tools/mode.py`'s
  `enter_exhibition_mode`/`exit_exhibition_mode` (see the dedicated
  section above): maps "mode exposition"/"exhibition mode"/"passe en mode
  démo" to `enter_exhibition_mode` (no password, always call immediately),
  and "sors du mode exposition"/"exit exhibition mode"/"désactive le mode
  démo" to `exit_exhibition_mode(password)` — explicitly tells the LLM to
  ask the user for the password rather than guess or supply one itself
  when it wasn't given in the same request. Also tells the LLM how to
  narrate the restrictions honestly while active: report a refused
  `power_on_all`/`set_power(turn_on=True)` as a real refusal (don't retry),
  but describe a speed/direction request that got silently overridden to
  the fixed exhibition speed as the locomotive moving, not as a failure.

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
