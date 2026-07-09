# Architecture

```
src/jmri_mcp/
├── config.py       # env vars: JMRI_URL (e.g. http://10.0.20.20:12080)
├── jmri_client.py  # async HTTP client for JMRI's JSON API (power, version, ...)
├── jmri_ws.py      # persistent WebSocket client (ws://<jmri>/json/) for throttles
├── tools.py        # MCP tools exposed to the LLM (list_systems, get_power, set_power,
│                   #   system_status, acquire_throttle, release_throttle)
├── cli.py          # jmri-cli: manual command-line tool, no MCP client needed
└── server.py       # FastMCP entry point (stdio; logging → stderr only)
```

More tools (speed/direction/function control, roster, turnouts, sensors,
lights) will land here as their milestones are implemented — see the
[project board](https://github.com/orgs/HO44-PROJECT/projects/3).

## Two JMRI clients, two different shapes

JMRI exposes the same data over two transports, and this project uses both
for different reasons:

- **`jmri_client.py`** — plain async HTTP (`httpx`) against JMRI's REST-ish
  `/json/*` endpoints. One request, one response, no state kept between
  calls. Used for anything that doesn't need a throttle: power, version,
  roster, system discovery.
- **`jmri_ws.py`** — a persistent WebSocket (`ws://<jmri>:12080/json/`).
  This exists for one reason: **a JMRI throttle is bound to the connection
  that acquired it**. HTTP can't hold a throttle open between requests, so
  cab control needs a long-lived connection — see `JmriWsClient` below.
  Wired into the MCP surface as `acquire_throttle`/`release_throttle` in
  `tools.py`.

Port 12021 (the raw "JSON server" TCP socket, not HTTP) is never used —
the original prototype tried to `POST` HTTP to it, which cannot work. Both
clients above talk only to port 12080 (the Web Server), just over two
different protocols on that same port.

## `JmriWsClient` design

- **Lazy connection.** Nothing connects at server startup; the first
  `request()`/`acquire_throttle()` call triggers `connect()`. This keeps
  the stdio server's boot instant even if JMRI is unreachable.
- **Auto-reconnect.** If the read loop sees the connection drop, it
  retries with exponential backoff (`_RECONNECT_DELAY` doubling up to
  `_MAX_RECONNECT_DELAY`) until it succeeds.
- **Keepalive.** JMRI's `hello` message on connect carries a
  `heartbeat` value in milliseconds; the client pings at half that
  interval so JMRI never times the connection out.
- **Throttle re-acquisition.** Acquired throttles are remembered
  (`_throttles`); after a reconnect, `_reacquire_throttles()` re-sends
  the same acquire message for each one before the connection is handed
  back to callers.
- **Serialized request/response.** JMRI's JSON protocol has no
  request-id field, and — verified live against a real JMRI 5.4.0 server —
  concurrent requests of *different* types can come back in an order that
  doesn't match send order, and `{"type":"error",...}` replies don't name
  the request that caused them. There is no reliable way to correlate
  concurrent, mixed-type requests. So `request()` takes a lock: only one
  request is ever in flight on the socket at a time, and the next message
  read off the socket is assumed to be its reply. Messages that arrive
  with nothing pending (other clients' throttle moves, etc.) are handed to
  an optional `on_event` callback instead of being dropped.

See `CLAUDE.md`'s "Verified facts" section for the exact wire format
(hello/ping/pong/power/throttle payloads) captured from the user's JMRI.

## Throttle tool surface: DCC address as the only key

`acquire_throttle`/`release_throttle` (in `tools.py`) key everything on the
locomotive's **DCC address** — JMRI's own `throttle` id is never exposed to
the LLM. `_throttle_id(address)` derives a stable internal id
(`f"addr{address}"`) from the address, so the same loco always maps to the
same JMRI throttle across calls without the caller having to track an
opaque handle.

On server shutdown, `server.py` closes the shared `JmriWsClient`; JMRI
releases every throttle bound to that connection automatically, so no
explicit "release all" call is needed on exit.
