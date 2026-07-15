# MCP tool inventory

The full list of MCP tools (`@mcp.tool()`) the server exposes to an LLM client (Claude
Desktop, Claude Code, xiaozhi/Kira, or any other MCP host). This is the actual surface a
model sees — distinct from `jmri-cli`'s subcommands, which are more numerous due to CLI
parity plus scripting-only flags (`--hold`/`--rampup`/`--rampdown`/etc.), see
[cli.md](cli.md). For design rationale behind any of these tools, see
[architecture.md](architecture.md).

**47 tools**, across 10 domains:

| Domain | Count |
|---|---|
| Throttle | 16 |
| Power | 6 |
| Layout lights | 4 |
| Turnouts | 4 |
| Roster | 3 |
| Signals | 3 |
| Mode | 2 |
| Sensors | 2 |
| Blocks | 2 |
| Meta | 5 |

## Throttle (16)

| Tool | Signature | Description |
|---|---|---|
| `acquire_throttle` | `(address: int, prefix: str \| None = None) -> dict` | Acquire control of a locomotive by its DCC address, and report its current state. |
| `release_throttle` | `(address: int) -> dict` | Release this session's control of a locomotive acquired with `acquire_throttle`. |
| `set_speed` | `(address: int, speed_percent: float) -> dict` | Set a locomotive's speed as a percentage of its maximum (0-100%). |
| `set_speed_ramped` | `(address: int, speed_percent: float, rampup_seconds: float = 0.0, rampdown_seconds: float = 0.0, hold_seconds: float \| None = None) -> dict` | Change a locomotive's speed gradually instead of instantly — a smooth ramp up and/or down. |
| `stop` | `(address: int) -> dict` | Bring a locomotive to a controlled stop (speed 0%), like releasing the throttle. |
| `emergency_stop` | `(address: int) -> dict` | Emergency-stop a locomotive immediately (JMRI's decoder e-stop command). |
| `emergency_stop_all` | `() -> dict` | Emergency-stop EVERY locomotive currently under this session's control at once. |
| `set_direction` | `(address: int, direction: str) -> dict` | Set a locomotive's direction of travel: "forward" or "reverse". |
| `set_function` | `(address: int, function: int, state: bool) -> dict` | Turn one of a locomotive's decoder functions (F0-F28) on or off. |
| `lights_on` | `(address: int) -> dict` | Turn on a locomotive's headlight(s): shortcut for `set_function(address, 0, True)`. |
| `lights_off` | `(address: int) -> dict` | Turn off a locomotive's headlight(s): shortcut for `set_function(address, 0, False)`. |
| `set_loco_lights` | `(address: int, state: bool) -> dict` | Turn ON/OFF EVERY light-related function of ONE locomotive in a single call. |
| `set_all_locos_lights` | `(state: bool) -> dict` | Turn ON/OFF EVERY light-related function of EVERY currently-acquired locomotive at once. |
| `prepare_locomotive` | `(address: int, prefix: str \| None = None) -> dict` | Prepare ONE locomotive for a session: acquire, face forward, lights on. |
| `park_locomotive` | `(address: int) -> dict` | Put ONE locomotive to rest for the session: smooth stop, forward, lights off, throttle released. |
| `park_all_locomotives` | `() -> dict` | Put EVERY currently-acquired locomotive to rest at once: smooth stop, forward, lights off, released. |

## Power (6)

| Tool | Signature | Description |
|---|---|---|
| `list_systems` | `() -> dict` | List every DCC power system known to JMRI, with its current power state. |
| `get_power` | `(system: str \| None = None) -> dict` | Get the current power state (ON/OFF/UNKNOWN/IDLE) of one DCC system. |
| `set_power` | `(system: str \| None, turn_on: bool) -> dict` | Turn a DCC system's power ON or OFF, and report the state actually observed. |
| `power_off_all` | `() -> dict` | Cut power to EVERY DCC system at once — the real "stop absolutely everything" button. |
| `power_on_all` | `() -> dict` | Restore power to EVERY DCC system at once. |
| `system_status` | `() -> dict` | One-call diagnostic: is JMRI reachable, and what state is it in? |

## Layout lights (4)

JMRI Light objects (decor/building lights) — not a locomotive's own lights, see
`set_loco_lights`/`set_all_locos_lights` above for that.

| Tool | Signature | Description |
|---|---|---|
| `list_lights` | `() -> dict` | List every layout light known to JMRI, with its current ON/OFF state. |
| `get_light` | `(name: str) -> dict` | Get the current ON/OFF state of one layout light. |
| `set_light` | `(name: str, turn_on: bool) -> dict` | Turn a layout light ON or OFF, and report the state actually observed. |
| `set_layout_lights` | `(turn_on: bool) -> dict` | Turn EVERY layout light ON or OFF at once (depot, street, signal lamps — JMRI Light objects). |

## Turnouts (4)

| Tool | Signature | Description |
|---|---|---|
| `list_turnouts` | `() -> dict` | List every turnout known to JMRI, with its current CLOSED/THROWN state. |
| `get_turnout` | `(name: str) -> dict` | Get the current CLOSED/THROWN state of one turnout. |
| `set_turnout` | `(name: str, thrown: bool) -> dict` | Set a turnout CLOSED or THROWN, and report the state actually observed. |
| `set_all_turnouts` | `(thrown: bool) -> dict` | Set EVERY turnout on the layout to the SAME state (all CLOSED, or all THROWN) in one call. |

## Roster (3)

| Tool | Signature | Description |
|---|---|---|
| `list_roster` | `() -> dict` | List every locomotive in JMRI's roster: name, DCC address, road, road number, manufacturer, model, owner, last-modified date, and roster groups. |
| `find_locomotive` | `(name: str) -> dict` | Resolve a locomotive's spoken/typed name to its DCC address. |
| `get_locomotive_functions` | `(name: str) -> dict` | List a locomotive's named decoder functions (e.g. "F2": "Rear lights"). |

## Signals (3)

| Tool | Signature | Description |
|---|---|---|
| `list_signals` | `() -> dict` | List every signal mast known to JMRI, with its current aspect. |
| `get_signal` | `(name: str) -> dict` | Get the current aspect of one signal mast. |
| `set_signal` | `(name: str, aspect: str) -> dict` | Set a signal mast's aspect, and report the aspect actually observed. |

## Mode (2)

| Tool | Signature | Description |
|---|---|---|
| `set_executor_mode` | `(enabled: bool) -> dict` | Turn "executor mode" on or off: a concise, no-narration response style. |
| `get_executor_mode` | `() -> dict` | Report whether executor mode (concise, no-narration responses) is currently on. |

## Sensors (2, read-only)

| Tool | Signature | Description |
|---|---|---|
| `list_sensors` | `() -> dict` | List every sensor known to JMRI, with its current ACTIVE/INACTIVE state. |
| `get_sensor` | `(name: str) -> dict` | Get the current ACTIVE/INACTIVE state of one sensor. |

## Blocks (2, read-only)

| Tool | Signature | Description |
|---|---|---|
| `list_blocks` | `() -> dict` | List every layout block known to JMRI, with its current OCCUPIED/UNOCCUPIED state. |
| `get_block` | `(name: str) -> dict` | Get the current OCCUPIED/UNOCCUPIED state of one layout block. |

## Meta (5)

Higher-level tools that combine several low-level operations into one call, matching how
a model railroader would naturally ask an assistant to operate the layout.

| Tool | Signature | Description |
|---|---|---|
| `layout_status` | `() -> dict` | One-call overview of the whole layout: connectivity, power, active locomotives, blocks, sensors. |
| `secure_layout` | `(release_throttles: bool = True) -> dict` | Put the whole layout into a known safe resting state: stop every acquired locomotive smoothly, turn off its lights, turn off every layout light, and release throttles. |
| `release_all_locomotives` | `() -> dict` | Release this session's throttle on EVERY currently-acquired locomotive, without changing their state. |
| `night_mode` | `() -> dict` | Set the layout to night operation mode: turn on every layout light and every acquired locomotive's lights. |
| `day_mode` | `() -> dict` | Set the layout to daytime operation mode: turn off every layout light and every acquired locomotive's lights. |
