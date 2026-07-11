"""Shared constants for jmri-cli's command modules."""

POWER_STATE_NAMES: dict[int, str] = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}
LIGHT_STATE_NAMES: dict[int, str] = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "INCONSISTENT"}
TURNOUT_STATE_NAMES: dict[int, str] = {2: "CLOSED", 4: "THROWN", 0: "UNKNOWN", 8: "INCONSISTENT"}
SENSOR_STATE_NAMES: dict[int, str] = {2: "ACTIVE", 4: "INACTIVE", 0: "UNKNOWN", 8: "INCONSISTENT"}

CLI_THROTTLE_ID_PREFIX = "cli"
SNIFF_THROTTLE_ID_PREFIX = "sniff"

MIN_FUNCTION_NUMBER = 0
MAX_FUNCTION_NUMBER = 28

MIN_SPEED_PERCENT = 0.0
MAX_SPEED_PERCENT = 100.0

# How long a persistent connection (e.g. `throttle sniff`) idles between
# wake-ups while waiting for Ctrl-C. Not a protocol value - JMRI's own
# keepalive is handled separately by JmriWsClient's heartbeat ping/pong.
IDLE_POLL_SECONDS = 3600

# Ramp granularity: how many intermediate `set_speed` calls per second of
# --rampup/--rampdown. Each step is a real network round-trip to JMRI, so
# this trades ramp smoothness against total command count / wall-clock time.
RAMP_STEPS_PER_SECOND = 4.0

# Fallback ramp-down duration used by the interactive shell's exit
# confirmation (see shell.py) when stopping locomotives left in motion, on
# the way out. Fixed rather than per-address, to keep the exit flow simple.
SHELL_EXIT_RAMPDOWN_DEFAULT_SECONDS = 3.0
