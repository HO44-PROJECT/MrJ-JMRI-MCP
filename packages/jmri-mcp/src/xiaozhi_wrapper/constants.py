"""Shared constants for xiaozhi_wrapper."""

# Environment variables this package reads.
ENV_MCP_ENDPOINT = "MCP_ENDPOINT"  # xiaozhi WebSocket URL to bridge to (required)
ENV_MCP_CONFIG = "MCP_CONFIG"  # override path for mcp_config.json (optional)

# mcp_config.json's transport "type"/"transportType" values (transportType is
# an accepted alias, matching mcp_pipe.py's original upstream behavior).
TRANSPORT_STDIO = "stdio"
TRANSPORT_SSE = "sse"
TRANSPORT_HTTP = "http"
TRANSPORT_STREAMABLE_HTTP = "streamablehttp"
HTTP_LIKE_TRANSPORTS = (TRANSPORT_SSE, TRANSPORT_HTTP, TRANSPORT_STREAMABLE_HTTP)

# mcp_config.json top-level/per-server keys.
CONFIG_KEY_MCP_SERVERS = "mcpServers"
SERVER_KEY_DISABLED = "disabled"
SERVER_KEY_TYPE = "type"
SERVER_KEY_TRANSPORT_TYPE = "transportType"
SERVER_KEY_COMMAND = "command"
SERVER_KEY_ARGS = "args"
SERVER_KEY_URL = "url"
SERVER_KEY_HEADERS = "headers"
SERVER_KEY_ENV = "env"

# Reconnection backoff (connect_with_retry), seconds.
INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 600

# How much of a piped message to show in a debug log line, so a large
# JSON-RPC payload doesn't flood the terminal.
LOG_PREVIEW_CHARS = 120

# Seconds to wait for the child MCP server process to exit cleanly after
# terminate() before escalating to kill().
PROCESS_TERMINATE_TIMEOUT_SECONDS = 5
