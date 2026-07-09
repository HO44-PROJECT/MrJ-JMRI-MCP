# CLI reference

`jmri-cli` talks to `jmri_client.py` directly — no MCP/JSON-RPC involved. It's a
convenience tool for exercising the same JMRI logic the MCP tools use, without
needing an MCP client (Claude, Kira, ...) in the loop. Useful for quick manual
checks against a real layout, or for debugging.

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

## Exit codes

All subcommands return 0 on success, 1 on error (JMRI unreachable, unknown
system, ambiguous system name, or an unconfirmed `power set`). Errors go to
stderr; normal output goes to stdout.
