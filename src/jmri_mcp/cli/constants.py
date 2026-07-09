"""Shared constants for jmri-cli's command modules."""

POWER_STATE_NAMES: dict[int, str] = {2: "ON", 4: "OFF", 0: "UNKNOWN", 8: "IDLE"}

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
