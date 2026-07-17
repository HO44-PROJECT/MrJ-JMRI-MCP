*[Français](ENGINEER.fr.md)*

# 🛠️ Engineer

**Wants to see how it works, and push on the edges.** You script sessions, care about
what happens when JMRI misbehaves, and want the full tool surface rather than the curated
phrasebook.

Everything in [CONDUCTOR.en.md](CONDUCTOR.en.md) and [TINKERER.en.md](TINKERER.en.md)
still applies — this adds the low-level tools, the CLI, and the behavior you'll hit once
you go past natural-language phrasing.

---

## Full tool reference

All 50 MCP tools, by signature: **[mcp-tools.md](mcp-tools.md)**.

Design rationale for any of them — why a tool is shaped the way it is, what JMRI quirk it
works around: **[docs/architecture.md](docs/architecture.md)**.

## Command-line interface

`jmri-cli` gives every tool's capability without an LLM in the loop — direct control,
scripting, automation, and the tool of choice for testing/troubleshooting against a real
or mocked JMRI. See **[docs/cli.md](docs/cli.md)**.

The interactive shell (bare `jmri-cli`) also accepts a friendlier sentence syntax for
speed/direction — `speed Autorail at 30 for 30 up 5 down 6 forward` or `move Autorail
forward at 30 for 30` — a pure typing shortcut for `throttle speed`/`throttle forward`,
not a different capability. See "Sentence syntax" in `docs/cli.md`.

## Low-level throttle control

Beyond `set_speed`/`set_direction`, there's `set_speed_ramped` (gradual speed change with
independent ramp-up/hold/ramp-down timing — the primitive behind `park_locomotive`'s
smooth stop), `set_function` (any decoder function F0-F28 by number, not just lights),
and `acquire_throttle`/`release_throttle` if you want to manage the JMRI throttle
lifecycle explicitly instead of relying on auto-acquire.

## Things that don't work the way you'd guess

- **JMRI sends no reply when a requested value already matches current state** — a
  genuine silent no-op, not a dropped message. Every throttle/power/turnout/light setter
  in this codebase checks a live cache before sending, specifically to avoid hanging on
  this.
- **Re-POSTing a power state JMRI already reports can knock the system into `UNKNOWN`** —
  a real DCC++ bug, not a transient response quirk. `set_power` always re-reads current
  state first and skips the POST if it's already correct.
- **A power-ON that lands in `UNKNOWN` doesn't self-recover** — `set_power` detects this
  and retries once via a full OFF → wait 2s → ON cycle before giving up and reporting
  `confirmed: false` honestly.
- **A JMRI throttle only means anything on the connection that acquired it** — release it
  and the decoder keeps coasting at its last commanded speed, it doesn't stop. The MCP
  server holds one long-lived connection for exactly this reason; `jmri-cli`'s one-shot
  commands have their own documented limitation here, see `docs/cli.md`.
- **State can change outside your session** — another JMRI panel, PanelPro, or a second
  MCP/CLI session can move a locomotive you're watching. Every read this project shows
  you is live, not self-referentially cached from only your own commands.
- **`jmri-cli throttle list` and shell command history are local files, not JMRI state**
  — `~/.jmri-cli/throttle_state.json` and `~/.jmri-cli/shell_history` are `jmri-cli`'s own
  bookkeeping and can go stale or just get in the way during repeated test runs. `jmri-cli
  cache info` shows their paths/status, `jmri-cli cache clean` resets one or both; neither
  touches JMRI. See `docs/cli.md`.

See `docs/architecture.md` for the full detail behind each of these, including how
they're tested.

## Testing and safety

Mocked (`fake_jmri`) fixtures cover the full suite; live tests against a real JMRI
instance are opt-in and gated, see **[docs/testing.md](docs/testing.md)**. If you're
scripting anything that moves a real locomotive or touches real power, treat that the way
this project's own contributors do: confirm the target JMRI instance before running
anything, and never assume a prior authorization carries forward to the next command.

## Contributing

Conventions, module layout, and how to propose a change: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

---

Just want to drive a train? [CONDUCTOR.en.md](CONDUCTOR.en.md). Managing the layout
without the protocol internals? [TINKERER.en.md](TINKERER.en.md).
