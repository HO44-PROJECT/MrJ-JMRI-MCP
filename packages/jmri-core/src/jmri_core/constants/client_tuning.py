"""Timeouts, delays, and ramp tuning shared by jmri_client (HTTP) and jmri_ws (WebSocket)."""

HTTP_TIMEOUT_SECONDS = 5.0
POWER_POST_RECHECK_DELAY_SECONDS = 1.0

# When a power ON is requested but the post-POST re-read observes UNKNOWN
# (not ON, not the pre-existing OFF) -- the command station rejected/lost
# the ON and needs a clean OFF->ON cycle to recover -- set_power posts OFF,
# waits this long, then retries ON once. Verified against the user's real
# DCC++ station on JMRI < POWER_UNKNOWN_JMRI_FIX_VERSION: an ON that lands
# in UNKNOWN never self-recovers on its own there. On JMRI >=
# POWER_UNKNOWN_JMRI_FIX_VERSION this forced OFF/ON cycle is no longer used
# -- see POWER_UNKNOWN_SELF_RECOVERY_WAIT_SECONDS below.
POWER_UNKNOWN_RECOVERY_DELAY_SECONDS = 2.0

# JMRI version (JMRI/JMRI#15279, fixed by JMRI/JMRI#15287, shipped from
# build 1381) from which a DCC-EX connection self-recovers from a
# redundant-power-command UNKNOWN flip on its own, typically within a few
# seconds -- no OFF/ON cycle needed or wanted anymore. Verified live by the
# user against their own DCC-EX stations post-upgrade: UNKNOWN clears back
# to the correct state by itself around ~5s, and any power command sent
# while still UNKNOWN is honored immediately rather than fought by a
# leftover forced cycle. Compared as a (major, minor, patch) tuple via
# _parse_jmri_version, not a string compare (e.g. "5.9" must sort before
# "5.17").
POWER_UNKNOWN_JMRI_FIX_VERSION = "5.17.1"

# How long to wait before re-reading state after a redundant power command
# lands in UNKNOWN, on JMRI >= POWER_UNKNOWN_JMRI_FIX_VERSION -- just long
# enough for the DCC-EX connection's own self-recovery (observed ~5s by the
# user) to have happened, so the re-read reports the real settled state
# instead of a still-in-flight UNKNOWN.
POWER_UNKNOWN_SELF_RECOVERY_WAIT_SECONDS = 5.0

WS_CONNECT_TIMEOUT_SECONDS = 5.0
WS_REQUEST_TIMEOUT_SECONDS = 5.0
WS_RECONNECT_DELAY_SECONDS = 2.0
WS_MAX_RECONNECT_DELAY_SECONDS = 30.0
WS_DEFAULT_HEARTBEAT_MS = 10_000

# Ramp granularity: how many intermediate `set_speed` calls per second of
# --rampup/--rampdown. Each step is a real network round-trip to JMRI, so
# this trades ramp smoothness against total command count / wall-clock time.
RAMP_STEPS_PER_SECOND = 4.0

# Above this total ramp+hold+ramp duration, set_speed_ramped's MCP tool runs
# the sequence in the background and returns immediately instead of
# blocking the tool call until it finishes — a voice client (xiaozhi/Kira)
# has no per-turn feedback while a tool call is in flight, and a long silent
# wait can trip the client's own conversation-turn timeout even though the
# ramp itself would have completed successfully. Short ramps stay
# synchronous since an immediate real result is more useful than a
# "started" acknowledgement when the wait is trivial.
RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS = 4.0

# park_locomotive's rampdown-to-stop duration at full speed (100%), scaled
# linearly down to ~0s for a locomotive already stopped -- current_fraction
# * this constant. Keeps the shutdown proportional to how fast the loco is
# actually going instead of a single fixed wait that's needlessly slow for
# a nearly-stopped loco or too abrupt for one at full speed. Capped at this
# value, so it never crosses RAMPED_SPEED_BACKGROUND_THRESHOLD_SECONDS and
# park_locomotive can stay a simple blocking call.
STOP_LOCOMOTIVE_RAMPDOWN_SECONDS_AT_FULL_SPEED = 3.0

# How long to wait after the last function-off command before releasing a
# throttle. JMRI's WebSocket reply/ack only confirms the JSON message was
# received -- it says nothing about whether the DCC command has actually
# reached the decoder over the rails yet (JMRI has no such readback, see
# CLAUDE.md's verified facts). Verified live (issue #59): releasing
# immediately after an F-off ack that already printed/returned still raced
# the real decoder command and left lights on / direction flipped, even
# though every function-off call had already completed successfully from
# this client's point of view. A fixed settle delay here is the fix, not a
# faster/differently-ordered request.
RELEASE_FUNCTION_SETTLE_DELAY_SECONDS = 0.5

# Exhibition mode's fixed speed: any requested speed_percent is replaced by
# this constant rather than honored, so a member of the public asking for
# "full speed" can't get one. Moderate on purpose -- fast enough to be
# visibly a moving train, slow enough to stay safe unsupervised in a public
# demo. See jmri_mcp.tools.mode / tools.throttle for where this is applied.
EXHIBITION_SPEED_PERCENT = 30.0

# jmri-cli shell tab-completion (completion.py): how long a cached name list
# (systems/roster/lights/turnouts/sensors/signals/blocks) is trusted before
# a completer tries a fresh live read again. Short enough that a locomotive
# added to the roster minutes ago shows up in the same terminal session
# without an explicit `cache clean`, long enough that repeated Tab presses
# while typing one command don't each trigger their own HTTP round-trip.
COMPLETION_CACHE_TTL_SECONDS = 60.0

# Max time a completer will wait on a live JMRI read before falling back to
# whatever's already cached (or an empty list). A completer runs
# synchronously the instant the user presses Tab -- it must never hang
# noticeably even if JMRI is slow or unreachable.
COMPLETION_TIMEOUT_SECONDS = 1.0
