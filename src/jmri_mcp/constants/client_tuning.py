"""Timeouts, delays, and ramp tuning shared by jmri_client (HTTP) and jmri_ws (WebSocket)."""

HTTP_TIMEOUT_SECONDS = 5.0
POWER_POST_RECHECK_DELAY_SECONDS = 1.0

WS_CONNECT_TIMEOUT_SECONDS = 5.0
WS_REQUEST_TIMEOUT_SECONDS = 5.0
WS_RECONNECT_DELAY_SECONDS = 2.0
WS_MAX_RECONNECT_DELAY_SECONDS = 30.0
WS_DEFAULT_HEARTBEAT_MS = 10_000

# Ramp granularity: how many intermediate `set_speed` calls per second of
# --rampup/--rampdown. Each step is a real network round-trip to JMRI, so
# this trades ramp smoothness against total command count / wall-clock time.
RAMP_STEPS_PER_SECOND = 4.0
