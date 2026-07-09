# CLI reference

`jmri-cli` talks to JMRI directly — no MCP/JSON-RPC involved. It's a
convenience tool for exercising the same JMRI logic the MCP tools use, without
needing an MCP client (Claude, Kira, ...) in the loop. Useful for quick manual
checks against a real layout, or for debugging. `power`/`status` use
`jmri_client.py` (one-shot HTTP); `throttle` uses `jmri_ws.py` (a fresh
WebSocket connection for the one command, then closed).

See [install.md](install.md) if `jmri-cli` isn't found on your PATH.

Every command needs to know where JMRI is — set `JMRI_URL`, or rely on the
default `http://localhost:12080`:

```bash
export JMRI_URL=http://10.0.20.20:12080
```

## `jmri-cli status`

One-call diagnostic: is JMRI reachable, what version is it, and what state is
each power system in. No side effects — this is the first thing to run when
something isn't responding.

```bash
$ jmri-cli status
JMRI reachable, version 5.4.0
  DCC++ Ohara    : OFF
  DCC++ Zou      : OFF
  DCC++ Raijin   : OFF (default)
```

## `jmri-cli power status [system]`

Show the power state of every system, or just one if given a name/prefix/fragment
(case-insensitive, tolerant matching — `"ohara"`, `"Ohara"`, `"O"` all resolve to
`DCC++ Ohara`). No side effects.

```bash
$ jmri-cli power status
DCC++ Ohara    : OFF
DCC++ Zou      : OFF
DCC++ Raijin   : OFF (default)

$ jmri-cli power status ohara
DCC++ Ohara    : OFF
```

## `jmri-cli power set <system> <on|off>`

Turn a system's power on or off. **This writes to JMRI** — on real DCC++
hardware, this actuates a physical relay.

```bash
$ jmri-cli power set zou on
DCC++ Zou      : ON
```

The reported state is re-read ~1s after the command, because JMRI/DCC++'s
immediate POST response is transient/unreliable (see [CLAUDE.md](../CLAUDE.md)).
If the observed state doesn't confirm the request, the command prints a warning
to stderr and exits with code 1 — it never silently reports success:

```bash
$ jmri-cli power set zou on
DCC++ Zou      : OFF
WARNING: requested ON but observed state did not confirm after re-read
```

## `jmri-cli throttle acquire <address> [--prefix P]`

Acquire a loco by DCC address on a fresh WebSocket connection, print its
reported speed/direction, then close the connection (which releases the
throttle JMRI-side — this is a one-shot check, not a way to hold a throttle
open from the shell). `--prefix` targets a specific command station (e.g.
`R` for DCC++ Raijin) when more than one is connected.

```bash
$ jmri-cli throttle acquire 3
address=3 speed=0.0 forward=True (acquired)
```

(This raw `forward=True/False` is `acquire`'s own direct print of JMRI's
field — `direction`'s subcommand below reports the readable
`forward`/`reverse` strings instead, matching what the MCP tools expose.)

## `jmri-cli throttle release <address>`

Acquire then immediately release a loco by DCC address on a fresh
connection — mirrors what closing an MCP client's connection does for a
throttle it was holding. Since a throttle only means something on the
connection that holds it, a brand-new CLI connection can't release a
throttle another session is holding onto (that one releases itself when
*that* connection closes); this command exists mainly to confirm the
release round-trip works.

```bash
$ jmri-cli throttle release 3
address=3 released
```

## `jmri-cli throttle speed <address> <speed_percent>`

Acquire a loco by DCC address (if not already held) on a fresh connection,
set its speed as a 0-100 percentage of maximum, print the speed JMRI
actually reports, then close the connection.

```bash
$ jmri-cli throttle speed 3 40
address=3 speed=40%
```

## `jmri-cli throttle stop <address>`

Controlled stop: sets speed to 0. Different from `estop` below — this is a
normal speed command, not JMRI's decoder emergency stop.

```bash
$ jmri-cli throttle stop 3
address=3 stopped
```

## `jmri-cli throttle estop <address>`

Emergency stop: JMRI's decoder e-stop command (`speed=-1.0`), not just
speed 0. Use for safety-critical stops.

```bash
$ jmri-cli throttle estop 3
address=3 emergency-stopped
```

## `jmri-cli throttle direction <address> <forward|reverse>`

Acquire a loco by DCC address (if not already held) on a fresh connection,
set its direction, print the direction JMRI actually reports back, then
close the connection. `forward`/`reverse` are the loco's own decoder-wired
notion of front/back, not compass direction. Safe to call repeatedly with
the same direction — same no-op/cache behavior as `speed`/`stop`/`estop`
(see below).

```bash
$ jmri-cli throttle direction 3 reverse
address=3 direction=reverse
```

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

`stop`, `estop`, `speed`, and `direction` are all safe to call repeatedly
with the same target state — JMRI sends no reply at all when the requested
value already matches the current one, and the client checks a live local
cache of the throttle's state before sending, so a repeat call reports the
same result immediately instead of hanging until timeout. That cache is
kept fresh by JMRI itself: it pushes every throttle state change to all
connections holding the same address, not only the one that made the
change, so this also correctly reflects a speed/direction change made by
another client (a JMRI panel, another `jmri-cli`/MCP session) — see
[architecture.md](architecture.md) for the wire-level detail.

## Exit codes

All subcommands return 0 on success, 1 on error (JMRI unreachable, unknown
system, ambiguous system name, or an unconfirmed `power set`). Errors go to
stderr; normal output goes to stdout.
