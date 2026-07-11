# CLI reference

`jmri-cli` talks to JMRI directly — no MCP/JSON-RPC involved. It's a
convenience tool for exercising the same JMRI logic the MCP tools use, without
needing an MCP client (Claude, Kira, ...) in the loop. Useful for quick manual
checks against a real layout, or for debugging. `power`/`roster`/`status`/
`light`/`turnout`/`sensor`/`signal` use `jmri_client/` (one-shot HTTP);
`throttle` uses `jmri_ws/` (a fresh WebSocket connection for the one command,
then closed).

See [install.md](install.md) if `jmri-cli` isn't found on your PATH.

Every command needs to know where JMRI is — set `JMRI_URL`, or rely on the
default `http://localhost:12080`:

```bash
export JMRI_URL=http://localhost:12080
```

Run `jmri-cli` with **no arguments at all** to launch the interactive shell
(see below) — a single long-lived connection for indefinite locomotive
control. `jmri-cli -h`/`--help` instead prints the welcome banner and full
command list and exits immediately, same as always; it does **not** launch
the shell. Every leaf subcommand's own `-h` shows a copy-pasteable example in
its epilog — there's no separate `examples` command, the examples live where
you're already looking.

## Design pattern: bare group = smart default, verb elevation

Two rules apply consistently across every command group below:

- **A group whose members share an obvious "just show me the state" default
  doesn't force typing a leaf name.** Bare `jmri-cli power` behaves exactly
  like `power status`; bare `roster` like `roster list`; bare `throttle`
  like `throttle list`; bare `light`/`turnout`/`sensor`/`signal` like their
  own `list`.
- **A state value that would otherwise be a positional argument (on/off,
  forward/reverse, closed/thrown) is elevated to be the subcommand name
  itself**, and the target becomes an *optional* fuzzy argument that
  defaults to "every member of the group" when omitted — `power on`/`power
  off`, `throttle forward`/`throttle reverse`, `light on`/`light off`,
  `turnout closed`/`turnout thrown`. `jmri-cli power on` turns every system
  on; `jmri-cli power on zou` turns on just the one matching `"zou"`.

## Interactive shell (`jmri-cli` with no arguments)

```bash
$ jmri-cli
jmri-cli interactive shell. Type `exit`, `quit`, or Ctrl-D to leave.
jmri-cli> throttle acquire 3
address=3 speed=0.0 forward=True (acquired)
jmri-cli> throttle speed 3 40
address=3 speed=40%
jmri-cli> throttle stop 3
address=3 stopped
jmri-cli> exit
```

The shell opens **one WebSocket connection for the whole session** and reuses
it for every command you type — this is the fix for one-shot mode's core
limitation (see "Why `throttle` has a local cache" below): a throttle only
means anything on the connection that acquired it, and one-shot commands
close their connection (and thus release the throttle) the instant they
return. Inside the shell, a nonzero speed genuinely keeps a locomotive moving
between commands, because the connection stays open until you exit.

Every command works exactly as in one-shot mode, with one difference:
`--hold` is **optional** inside the shell (see "Mandatory `--hold`"
below) — omitting it just means "hold this speed until I type another
command," since the shell itself is the indefinite hold. `throttle stop`
additionally **requires** a locomotive argument inside the shell (e.g.
`throttle stop 3`) — the CLI-wide `~/.jmri-cli/throttle_state.json` cache of
every one-shot-touched address doesn't apply to the shell's own held
throttles, so there's no "stop everything" target to default to.

`throttle sniff` is rejected inside the shell with a message pointing you at
running it in a second terminal instead — it needs its own connection and
its own indefinite Ctrl-C loop, which would otherwise block the shell's own
prompt.

Type `help`, `-h`, or `--help` at the prompt for the same banner and command
list `jmri-cli -h` shows outside the shell. `help` also works mid-line as a
stand-in for `-h`, e.g. `throttle help` or `throttle speed help` show that
subcommand's own help text, same as `throttle -h`/`throttle speed -h`.

**Exiting with something still moving**: typing `exit`/`quit`, pressing
Ctrl-D, or pressing Ctrl-C at the prompt all trigger the same check — if any
locomotive held by the shell's connection has a nonzero speed, you're asked:

```
1 loco(s) in motion (address(es) 3). Stop them all before exiting? [Y/n]
```

Enter or `y` ramps every moving locomotive down to 0 over a fixed 3-second
window, then exits cleanly. `n` exits immediately with a stderr warning that
the locomotive(s) are being left in their current state — JMRI will keep
them moving until something else (another client, physical intervention)
stops them, since releasing the throttle does not stop the loco. If nothing
is moving, you're not prompted at all.

## `jmri-cli status`

One-call diagnostic: is JMRI reachable, what version is it, and what state is
each power system in. No side effects — this is the first thing to run when
something isn't responding.

```bash
$ jmri-cli status
JMRI reachable, version 5.4.0
System              State    Default
------------------  -------  ---------
ohara (turnouts)    OFF
raijin (tracks)     OFF      yes
taya (accessories)  OFF
zou (test)          OFF
```

Systems are sorted alphabetically by name.

## `jmri-cli power` / `power status`

Show the power state of every system, sorted alphabetically, as a table with
a `Default` column marking which one JMRI treats as its default. No side
effects. Bare `jmri-cli power` is identical to `jmri-cli power status`.

```bash
$ jmri-cli power
System              State    Default
------------------  -------  ---------
ohara (turnouts)    OFF
raijin (tracks)     OFF      yes
taya (accessories)  OFF
zou (test)          OFF
```

The name shown is JMRI's connection name verbatim — if the user has added
a parenthetical in JMRI's own connection setup (e.g. `"zou (test)"`,
`"raijin (tracks)"`), it prints as part of the name unchanged, since
that's the only place JMRI records a connection's purpose (see issue #24
and `docs/architecture.md`).

## `jmri-cli power get [system]`

Print one system's power state as a bare `ON`/`OFF`/`UNKNOWN`/`IDLE` — no
table, just the word, meant for scripting/voice ("is Ohara on?"). `[system]`
is fuzzy (name/prefix/fragment, case-insensitive); omit it to check the
default system.

```bash
$ jmri-cli power get ohara
OFF
```

## `jmri-cli power default`

Print which system JMRI treats as the default (the one used when no system
is specified elsewhere).

```bash
$ jmri-cli power default
raijin (tracks)
```

## `jmri-cli power on [system]` / `power off [system]`

Turn a system's power on or off, or **every** system if `[system]` is
omitted — `power off` with no target is the layout-wide emergency stop,
since cutting power stops every locomotive regardless of who's driving it.
**This writes to JMRI** — on real DCC++ hardware, this actuates a physical
relay for each targeted system.

```bash
$ jmri-cli power on zou
System    State    Default
--------  -------  ---------
zou       ON

$ jmri-cli power off
System              State    Default
------------------  -------  ---------
ohara (turnouts)    OFF
raijin (tracks)     OFF      yes
taya (accessories)  OFF
zou (test)          OFF
```

Each targeted system is re-read ~1s after the command and confirmed, because
JMRI/DCC++'s immediate POST response is transient/unreliable (see
[CLAUDE.md](../CLAUDE.md)). If any system's observed state doesn't confirm
the request, the command prints a warning to stderr and exits with code 1 —
it never silently reports success.

Safe to run repeatedly with the same state, including right after another
`power on`/`power off` already set it: current state is checked first, and
if it already matches the request, nothing is sent to JMRI at all for that
system. This isn't just an optimization — re-POSTing a state JMRI already
reports is a real JMRI/DCC++ bug on this installation that knocks the system
into UNKNOWN instead of no-opping, which is awkward to recover from.

## `jmri-cli roster` / `roster list`

List every locomotive in JMRI's roster: DCC address, name, road, model, as a
sorted table. No side effects. Empty road/model print as `-` (the user
never filled them in in JMRI — not an error). Bare `jmri-cli roster` is
identical to `jmri-cli roster list`.

```bash
$ jmri-cli roster
  Address  Name         Road                            Model
---------  -----------  ------------------------------  -------
        2  141R         Mikado 141 R                    8273
        3  Corentine    Locotender 030T                 63338
        4  Autorail     Railcar                         4185A
        8  Boite à Sel  -                                -
```

## `jmri-cli roster find <name-or-address>`

Resolve a locomotive name **or DCC address** to its roster entry — fuzzy,
case- and accent-insensitive for names (exact match first, then an
unambiguous partial match); a purely numeric argument matches the `address`
field directly instead (always exact, never ambiguous, since addresses are
unique). This is the fast path to confirm what a name/address resolves to
before feeding it to `throttle`.

```bash
$ jmri-cli roster find autorail
address=4 name=Autorail road=Railcar model=4185A

$ jmri-cli roster find 4
address=4 name=Autorail road=Railcar model=4185A

$ jmri-cli roster find tgv
Error: Unknown locomotive 'tgv'. Available: ['141R', 'Autorail', ...]
```

A name matching more than one entry (e.g. `"a"`) is reported as an
`Ambiguous locomotive` error listing every match, rather than guessing one.

## `jmri-cli roster functions <name-or-address>`

List a locomotive's user-labeled decoder functions — the names the user
typed into JMRI's own roster editor (PanelPro's Roster Entry, Function
Panel). Resolves `<name-or-address>` the same way as `roster find` (name,
fragment, or DCC address). Most locos have no labels set at all (JMRI always
has 29 possible slots, F0-F28, per loco — only the ones the user actually
named are shown); that's reported plainly, not as an error.

```bash
$ jmri-cli roster functions autorail
Autorail (address=4)
Function    Label
----------  -----------------
F0          Lumières avant
F1          Lumières cabine
F2          Lumières arrières

$ jmri-cli roster functions 2
141R (address=2)
  no labeled functions
```

Use this to find the right F-number for `throttle on`/`throttle off` when
the user names a function by what it does ("the rear lights") instead of a
number — `throttle on`/`off` can also match a label fragment directly (see
below), so this is mainly for confirming what's available.

## `jmri-cli throttle` / `throttle list`

Print last-known speed/direction/functions for every locomotive this CLI has
touched. **Reads a local cache, not live JMRI state** — see "Why `throttle`
has a local cache" below. Empty until at least one `throttle speed`/
`forward`/`reverse`/`on`/`off`/etc has been run. Bare `jmri-cli throttle` is
identical to `jmri-cli throttle list`.

```bash
$ jmri-cli throttle
No locomotives touched yet by this CLI. Run e.g. `jmri-cli throttle speed <loco> <value>` first.

$ jmri-cli throttle speed 3 40 --hold 5
address=3 speed=0%
$ jmri-cli throttle
  Address  Speed    Direction    Functions on
---------  -------  -----------  --------------
        3  0%       forward      -
```

### Why `throttle` has a local cache

Every `jmri-cli throttle` invocation opens a fresh WebSocket connection,
acquires the loco, acts, then closes the connection — and JMRI releases the
throttle the instant that connection closes (verified live, see
[CLAUDE.md](../CLAUDE.md)). That means there is no live per-address state
left to query back from JMRI between two separate `jmri-cli throttle`
invocations. `~/.jmri-cli/throttle_state.json` is this CLI's own memory of
what it last saw for each address; it's a convenience cache, not a source of
truth — another client (a JMRI panel, an MCP session) changing a loco's
speed between two `jmri-cli` calls won't be reflected here until the next
`jmri-cli throttle ...` command touches that address again and resyncs from
JMRI's own reply.

## `jmri-cli throttle acquire <loco> [--prefix P]`

Acquire a loco (by name, fragment, or DCC address) on a fresh WebSocket
connection, print its reported speed/direction, then close the connection
(which releases the throttle JMRI-side — this is a one-shot check, not a way
to hold a throttle open from the shell). `--prefix` targets a specific
command station (e.g. `R` for DCC++ Raijin) when more than one is connected.

```bash
$ jmri-cli throttle acquire 3
address=3 speed=0.0 forward=True (acquired)
```

## `jmri-cli throttle release <loco>`

Acquire then immediately release a loco on a fresh connection — mirrors what
closing an MCP client's connection does for a throttle it was holding.

```bash
$ jmri-cli throttle release 3
address=3 released
```

## `jmri-cli throttle speed <loco> [speed_percent] [--rampup S] [--rampdown S] [--hold S]`

Get or set a loco's speed. With `speed_percent` given (0-100, or negative —
see below), acquires the loco (if not already held) on a fresh connection,
sets its speed, holds it, then auto-stops and closes the connection —
**this writes to JMRI**. With `speed_percent` omitted, it's a read: acquires
the loco (which resyncs on JMRI's real current speed) and prints it without
sending any speed command.

```bash
$ jmri-cli throttle speed 3 40 --hold 5
address=3 speed=0%

$ jmri-cli throttle speed 3
address=3 speed=0%

$ jmri-cli throttle speed 3 40 --rampup 5 --hold 30 --rampdown 5
address=3 speed=0%
```

### Mandatory `--hold` outside the shell

One-shot mode has no way to hold a speed indefinitely (see "Why `throttle`
has a local cache" below for the root cause), so **`--hold` is required
whenever the target speed is nonzero** — omitting it is a hard usage error,
exit code 2, rejected before any JMRI contact:

```
Error: --hold is required when setting a nonzero speed outside the interactive shell (use the bare `jmri-cli` shell for an indefinite hold).
```

After the `--hold` hold ends, the locomotive **always auto-stops** —
ramped via `--rampdown` if given, else instantly — before the process exits.
That's why the examples above all print `speed=0%`: that's the state *after*
the auto-stop, not the held speed. This is a safety-first default: a
one-shot command can never leave a locomotive moving unattended once it
returns.

For `forward`/`reverse` (below), the same rule applies but can only be
checked *after* the initial acquire (the current speed has to be read first
to know whether the rule even applies to a pure direction change).

Use the [interactive shell](#interactive-shell-jmri-cli-with-no-arguments)
instead whenever you actually want a locomotive to keep moving after the
command returns.

### `--rampup`/`--rampdown`

Ramp linearly to the target speed (or down to 0 for `--rampdown`) over the
given number of seconds instead of jumping instantly. Both flags can be used
together (ramp up, hold, ramp down) or independently.

### Negative `speed_percent` is reverse shorthand, not emergency stop

`throttle speed 3 -40` means "reverse at 40%" — a pure CLI convenience,
resolved entirely client-side into a direction flip plus a normal
`speed=0.4` command. It is **not** related to JMRI's real emergency-stop
sentinel (`speed=-1.0`, sent only by `throttle estop`, below) — the two
never share a code path, so there's no risk of a negative speed value
accidentally triggering a decoder e-stop.

## `jmri-cli throttle stop [loco] [--rampdown S]`

Controlled stop (speed 0) of one loco, or **every locomotive this CLI's
local cache knows about** if `[loco]` is omitted — the CLI's own "stop
everything I've driven" primitive, mirroring `power off`'s "no target =
everything" pattern. Different from `estop` below — this is a normal speed
command, not JMRI's decoder emergency stop. Inside the interactive shell,
`[loco]` is **mandatory** (the shell's held throttles aren't reflected in
the CLI-wide cache, so there's no "stop everything" target to fall back to).

```bash
$ jmri-cli throttle stop 3
address=3 stopped

$ jmri-cli throttle stop
address=3 stopped
address=7 stopped

$ jmri-cli throttle stop 3 --rampdown 5
address=3 stopped
```

**Known limitation**: with no `[loco]`, this only reaches addresses the
local cache knows about (i.e. ones this CLI has already touched this
session or a previous one) — a locomotive only ever driven from a JMRI
panel or another client is out of reach here, same limitation any
cache-driven CLI command has. Use `power off` to cut power to the whole
layout regardless of who's driving.

## `jmri-cli throttle estop <loco>`

Emergency stop: JMRI's decoder e-stop command (`speed=-1.0`), not just
speed 0. Use for safety-critical stops.

```bash
$ jmri-cli throttle estop 3
address=3 emergency-stopped
```

## `jmri-cli throttle forward <loco>` / `throttle reverse <loco>` `[--rampup S] [--rampdown S] [--hold S]`

Acquire a loco (if not already held) on a fresh connection, set its
direction, print the direction JMRI actually reports back, then close the
connection. `forward`/`reverse` are the loco's own decoder-wired notion of
front/back, not compass direction. Safe to call repeatedly with the same
direction — same no-op/cache behavior as `speed`/`stop`/`estop` (see below).

```bash
$ jmri-cli throttle reverse 3
address=3 direction=reverse

$ jmri-cli throttle reverse 3 --rampup 5 --hold 30 --rampdown 5
address=3 direction=reverse
```

If the loco is **moving** when a direction flip is requested, it's ramped
down to 0 first (using `--rampdown` if given, else instantly), the direction
is flipped, then it's ramped back up to the speed it was at before the flip
(using `--rampup` if given, else instantly) — never an instant in-place
direction reversal at speed. If the loco is **stationary**, `--rampup`/
`--rampdown` are accepted but inert: it's a pure direction change, same as
before this feature existed.

Mandatory `--hold` applies here too, but only once the loco is confirmed
moving (checked after the initial acquire, since that's the only way to know
the current speed) — a `forward`/`reverse` on a stationary loco never
requires `--hold`.

## `jmri-cli throttle on <loco> [function]` / `throttle off <loco> [function]`

Turn one or more decoder functions on or off. `[function]` may be a bare
number (`0`-`28`), a fragment of a roster-set function label (e.g. `"phares"`
matches a label containing it), or **omitted entirely to act on every
labeled function for this loco**. There is no F0-is-headlight fallback:
F-number meaning is decoder/roster-specific, not a protocol guarantee — a
loco with no labeled functions and no function number given is a clear
error asking for one, not a guess.

```bash
$ jmri-cli throttle on 3 1
address=3 F1=on

$ jmri-cli throttle on autorail
address=4 F0=on
address=4 F1=on
address=4 F2=on

$ jmri-cli throttle on 141r
Error: 141R (address=2) has no labeled functions in JMRI's roster — specify a function number, e.g. `throttle on 2 0`
```

Out-of-range numbers (outside 0-28) are rejected locally without contacting
JMRI. Safe to call repeatedly with the same state — same no-op/cache
behavior as `speed`/`stop`/`estop`/`forward`/`reverse`.

## `jmri-cli throttle sniff [-a N ...] [--show-pong]`

Opens a WebSocket connection and prints every JMRI message it receives,
timestamped, until Ctrl-C — a live protocol dump for debugging. With no
`-a`/`--address`, it only sees `hello`/`pong` and whatever this same
connection triggers. Pass `-a`/`--address` (repeatable) to also acquire
those locos first: JMRI then pushes every state change on them from *any*
client (another `jmri-cli`/MCP session, a JMRI panel, another throttle
app) to this connection too, so you can watch what's actually happening
on the layout in real time, not just what this one connection does.

Keepalive `pong` messages are hidden by default — they fire every few
seconds regardless of layout activity and carry no information; pass
`--show-pong` to include them anyway. Throttle messages' 69 function-key
fields (`F0`-`F68`, almost always `false`) are collapsed to a single
`functions_on` list of the ones actually on (omitted entirely if none are),
so the field that changed isn't buried in noise.

```bash
$ jmri-cli throttle sniff -a 3
Listening for JMRI messages, Ctrl-C to stop...
[13:35:56.183] throttle: {"address": 3, "speed": 0.0, "forward": true, "speedSteps": 126, "clients": 1, "rosterEntry": "Autorail", "name": "sniff3", "throttle": "sniff3"}
(acquired address=3 for observation)
[13:35:58.201] throttle: {"clients": 2, "name": "sniff3", "throttle": "sniff3"}
[13:35:58.203] throttle: {"speed": 0.25, "name": "sniff3", "throttle": "sniff3"}
```

That `speed: 0.25` line above came from a *different* `jmri-cli throttle
speed 3 25` run concurrently in another terminal — this is JMRI's
cross-connection push in action (see [architecture.md](architecture.md)).

`stop`, `estop`, `speed`, `forward`/`reverse`, and `on`/`off` are all safe to
call repeatedly with the same target state — JMRI sends no reply at all when
the requested value already matches the current one, and the client checks a
live local cache of the throttle's state before sending, so a repeat call
reports the same result immediately instead of hanging until timeout. That
cache is kept fresh by JMRI itself: it pushes every throttle state change to
all connections holding the same address, not only the one that made the
change, so this also correctly reflects a speed/direction/function change
made by another client (a JMRI panel, another `jmri-cli`/MCP session) —
see [architecture.md](architecture.md) for the wire-level detail. (This is
JMRI's own live-push cache inside `jmri_ws.py`, distinct from the
`~/.jmri-cli/throttle_state.json` local file described above — the former
lives only within one connection's lifetime, the latter persists across CLI
invocations.)

## `jmri-cli light` / `light list`

Show the state of every layout light known to JMRI — depot lighting,
street lamps, signal lamps, etc, wired up in JMRI as their own `light`
objects. **Not** a locomotive's headlight (that's a decoder function, see
`throttle on`/`throttle off` above). No side effects. Bare `jmri-cli light`
is identical to `jmri-cli light list`.

```bash
$ jmri-cli light
Light           State
--------------  -------
Depot Lighting  OFF
Street Lamps    ON
IL3             OFF
```

A light with no `userName` set in JMRI prints its raw system name (`IL3`
above) instead — not an error, just unlabeled.

## `jmri-cli light on [name]` / `light off [name]`

Turn a layout light on or off, or **every** light if `[name]` is omitted.
**This writes to JMRI.** Resolves `[name]` the same tolerant way as before
(system name or `userName`, case-insensitive, unambiguous fragment).

```bash
$ jmri-cli light on depot
Light           State
--------------  -------
Depot Lighting  ON
```

The state is re-read after the command and confirmed the same honest way
as `power on`/`off` — if the observed state doesn't match the request (e.g.
a feedback-wired light that didn't actually switch), the command prints a
warning to stderr and exits with code 1.

## `jmri-cli turnout` / `turnout list`

Show the state of every turnout known to JMRI. No side effects. Bare
`jmri-cli turnout` is identical to `jmri-cli turnout list`.

```bash
$ jmri-cli turnout
Turnout                         State
------------------------------  -------
Layout Turnout A                CLOSED
Layout Turnout BL               CLOSED
A / Mountain A -> Platform A/B  THROWN
```

## `jmri-cli turnout closed [name]` / `turnout thrown [name]`

Set a turnout closed or thrown, or **every** turnout if `[name]` is omitted.
**This writes to JMRI and can move a physical turnout motor on the real
layout** — omitting `[name]` moves every turnout JMRI knows about, so use it
deliberately. Resolves `[name]` the same tolerant way as before. Uses
JMRI/PanelPro's own CLOSED/THROWN vocabulary rather than "open"/"closed"
track terminology, which would be ambiguous about which route is which.

```bash
$ jmri-cli turnout thrown "layout turnout a"
Turnout            State
-----------------  -------
Layout Turnout A   THROWN
```

The state is re-read after the command and confirmed the same honest way
as `power on`/`off`/`light on`/`off` — if the observed state doesn't match
the request (e.g. a feedback-wired turnout that didn't settle), the command
prints a warning to stderr and exits with code 1.

## `jmri-cli sensor` / `sensor list`

Show the state of every sensor known to JMRI — block occupancy, turnout
motor feedback, utility flags like `ISCLOCKRUNNING`. Read-only: there is no
`sensor set`, since a sensor reports real-world state JMRI detects from its
own hardware inputs, not a command this project should issue. Bare
`jmri-cli sensor` is identical to `jmri-cli sensor list`.

```bash
$ jmri-cli sensor
ISCLOCKRUNNING      : ACTIVE
Montagne B          : INACTIVE
```

## `jmri-cli sensor status <name>`

Show one sensor's state. `<name>` matches either JMRI's system name
(`"RS22"`) or its user-friendly `userName` (`"Montagne B"`), case-
insensitive, tolerant of an unambiguous fragment. No side effects.

```bash
$ jmri-cli sensor status "montagne b"
Montagne B          : INACTIVE
```

## `jmri-cli signal` / `signal list`

Show the current aspect of every signal mast known to JMRI. Covers
`signalMast` objects only, not `signalHead` — see
[architecture.md](architecture.md#signal-masts-list_signals--get_signal--set_signal-26)
for why. No side effects. Bare `jmri-cli signal` is identical to
`jmri-cli signal list`.

```bash
$ jmri-cli signal
Entry Signal A      : Hp1
```

Aspect names (`Hp0`, `Hp1`, `Hp2`, ...) are whatever vocabulary the mast's
configured signal system uses (e.g. German `DB-HV-1969`) — passed through
verbatim, never hardcoded or translated by this project.

## `jmri-cli signal status <name>`

Show one signal mast's aspect. `<name>` matches either JMRI's system name
(e.g. `"ZF$dsm:DB-HV-1969:block(31)"`) or its user-friendly `userName`,
case-insensitive, tolerant of an unambiguous fragment of `userName` — but
**not** a fragment of the system name. JMRI auto-generates long system
names for DCC-driven masts and, unlike most turnouts, these are commonly
left without a `userName` set in PanelPro; if so, only the exact full
system name resolves. Set a `userName` per mast in PanelPro if you want
short-fragment matching to work. No side effects.

```bash
$ jmri-cli signal status "ZF\$dsm:DB-HV-1969:block(31)"
ZF$dsm:DB-HV-1969:block(31): Hp1
```

## `jmri-cli signal set <name> <aspect>`

Set a signal mast's aspect. **This writes to JMRI and, on a mast driven by
external hardware (e.g. a DCC accessory decoder or a custom
microcontroller), changes what the physical signal displays on the real
layout.** Resolves `<name>` the same tolerant way as `signal status`.
`<aspect>` is **not validated locally** — JMRI's JSON API does not expose
the list of valid aspects for a given mast (that vocabulary lives in the
mast's signal system definition inside JMRI, not over `/json/*`) — but
JMRI does validate it server-side, and an unknown aspect name comes back
as a hard error rather than a silent non-confirm.

```bash
$ jmri-cli signal set "ZF\$dsm:DB-HV-1969:block(31)" Hp0
```

The aspect is re-read after the command and confirmed the same honest way
as `power on`/`off`/`turnout closed`/`thrown` — if a *valid* aspect still
doesn't match after the command (e.g. unresponsive external hardware), the
command prints a warning to stderr and exits with code 1. **Fixed**: the
first live test of this command showed the POST completing with no HTTP
error but the aspect never actually changing — root-caused to this project
sending the wrong JSON field (`"aspect"` instead of the `"state"` key
JMRI's server actually reads), not a hardware issue. See
[architecture.md](architecture.md#signal-masts-list_signals--get_signal--set_signal-26)
for the full diagnosis.

## No CLI for executor mode

The MCP-only `set_executor_mode`/`get_executor_mode` tools (concise,
no-narration response style — see [architecture.md](architecture.md))
have no `jmri-cli` equivalent, unlike every other tool in this project.
They hold no JMRI state and make no JMRI calls at all — the whole point of
the flag is that it persists across tool calls within one long-lived MCP
session, which a fresh, one-shot `jmri-cli` invocation never has, so there
would be nothing for a CLI command to meaningfully exercise.

## Exit codes

All subcommands return 0 on success, 1 on error (JMRI unreachable, unknown
name, ambiguous name, or an unconfirmed write command). `throttle speed`/
`forward`/`reverse`/`stop` return 2 for a CLI usage error specific to
throttle commands — a missing mandatory `--hold` outside the shell, or a
missing locomotive argument to `stop` inside the shell. Errors go to
stderr; normal output goes to stdout.
