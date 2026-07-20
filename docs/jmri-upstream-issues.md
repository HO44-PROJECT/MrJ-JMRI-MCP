# Known JMRI issues reported upstream

Bugs found in JMRI itself (not this project) while building and using MrJ-JMRI-MCP
against a real layout, reported to the [JMRI project](https://github.com/JMRI/JMRI)
so other users hit them less. Kept here as a durable reference: what's broken,
what this project does to work around it, and where to track a real fix.

## DCC-EX connection power state stuck at UNKNOWN after a physical power cycle

**JMRI issue**: [JMRI/JMRI#15278](https://github.com/JMRI/JMRI/issues/15278)

After a DCC-EX command station has its power physically cut and restored, JMRI/PanelPro
can get stuck reporting that connection's power state as `UNKNOWN` for an extended
period, with no reliable way to force a refresh short of restarting PanelPro. The same
stale state is observable over `/json/power`, not just in the PanelPro UI, so it's a
state-tracking issue in JMRI's connection/power manager itself.

**Workaround in this project**: `power.py`'s `set_power` only trusts a re-read taken
`POWER_POST_RECHECK_DELAY_SECONDS` after the POST, never the POST response itself —
this recovers a transient `UNKNOWN` seen right after a command, but cannot fix a
connection stuck at `UNKNOWN` from an external power cycle JMRI never resolved on its
own; that still needs a PanelPro restart on the user's side.

## Sending ON to an already-ON DCC-EX connection flips its state to UNKNOWN

**JMRI issue**: [JMRI/JMRI#15279](https://github.com/JMRI/JMRI/issues/15279)

Sending an `ON` power command to a DCC-EX connection that is already reporting `ON`
causes its state to flip to `UNKNOWN` instead of staying `ON`. Reproducible both from
PanelPro's own power control and by POSTing `{"state":2}` to `/json/power` for that
connection's prefix.

**Workaround in this project**: `power.py`'s `set_power` always re-reads the system's
current state first and skips the POST entirely if it already matches the request —
"already ON" and "turn ON" are made indistinguishable from the caller's point of view,
so this project's own tools/CLI never trigger the bug. It also handles the case where
JMRI rejects/loses an ON despite the guard: if a post-POST re-read observes `UNKNOWN`
rather than the requested state, `set_power` posts OFF, waits
`POWER_UNKNOWN_RECOVERY_DELAY_SECONDS`, and retries ON once before giving up and
reporting `"confirmed": False` honestly rather than retrying indefinitely.
