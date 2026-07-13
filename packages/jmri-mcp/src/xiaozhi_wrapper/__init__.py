"""Generic stdio <-> WebSocket bridge for xiaozhi/Kira MCP integration.

This package is **JMRI-agnostic** — it doesn't import anything from
jmri_mcp. It pipes any number of configured stdio MCP servers (started as
subprocesses) to a xiaozhi WebSocket endpoint, so any MCP server (this
repo's `jmri-mcp`, or any other) can be exposed to a xiaozhi/Kira device
without xiaozhi-specific code living inside the MCP server itself. Ported
from the `kira` project's standalone `mcp_pipe.py` script, itself adapted
from the MCP pipe example in xiaozhi-esp32
(https://github.com/78/xiaozhi-esp32), so this repo can version it
alongside the `jmri-mcp`/`jmri-cli` entry points it's usually paired with
via mcp_config.json's `"command": "jmri-mcp"`.

Original xiaozhi-esp32 MCP pipe example: MIT License, Copyright (c) 2025
Shenzhen Xinzhi Future Technology Co., Ltd. and Project Contributors
(https://github.com/78/xiaozhi-esp32/blob/main/LICENSE). Reused/modified
here under those terms.

Usage (env):
    export MCP_ENDPOINT=<ws_endpoint>

Run all enabled servers from config (default):
    jmri-xiaozhi-bridge
    python -m xiaozhi_wrapper

Run a single local server script (back-compat, bypasses config):
    jmri-xiaozhi-bridge path/to/server.py

Config discovery order:
    $MCP_CONFIG, then this package's own mcp_config.json (checked in, works
    from any directory — one entry per MCP server, keyed by name; has no
    `env` block, JMRI_URL is inherited from the shell that launches the
    bridge, see build_server_command()).

Package layout:
    constants.py  Env var names, mcp_config.json key/transport-type
                  literals, backoff/timeout/logging tunables.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import sys

import websockets
from dotenv import load_dotenv

from xiaozhi_wrapper.constants import (
    CONFIG_KEY_MCP_SERVERS,
    ENV_MCP_CONFIG,
    ENV_MCP_ENDPOINT,
    HTTP_LIKE_TRANSPORTS,
    INITIAL_BACKOFF_SECONDS,
    LOG_PREVIEW_CHARS,
    MAX_BACKOFF_SECONDS,
    PROCESS_TERMINATE_TIMEOUT_SECONDS,
    SERVER_KEY_ARGS,
    SERVER_KEY_COMMAND,
    SERVER_KEY_DISABLED,
    SERVER_KEY_ENV,
    SERVER_KEY_HEADERS,
    SERVER_KEY_TRANSPORT_TYPE,
    SERVER_KEY_TYPE,
    SERVER_KEY_URL,
    TRANSPORT_HTTP,
    TRANSPORT_STDIO,
    TRANSPORT_STREAMABLE_HTTP,
)

# Auto-load MCP_ENDPOINT (and anything else) from a .env file next to the
# process's cwd, if present — convenient for local runs, optional otherwise.
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("xiaozhi_wrapper")


async def connect_with_retry(uri: str, target: str) -> None:
    """Keep a bridge connection to `uri` alive for `target`, forever.

    Calls `connect_to_server()` in a loop: each time it raises (WebSocket
    dropped, child process died, ...), wait with exponential backoff
    (`INITIAL_BACKOFF_SECONDS` doubling up to `MAX_BACKOFF_SECONDS`) and
    reconnect. Never returns on its own — this is the top-level task per
    configured server, meant to be wrapped in `asyncio.gather`/`create_task`.
    """
    reconnect_attempt = 0
    backoff = INITIAL_BACKOFF_SECONDS
    while True:  # infinite reconnection
        try:
            if reconnect_attempt > 0:
                logger.info(
                    "[%s] Waiting %ss before reconnection attempt %s...",
                    target, backoff, reconnect_attempt,
                )
                await asyncio.sleep(backoff)
            await connect_to_server(uri, target)
        except Exception as e:
            reconnect_attempt += 1
            logger.warning("[%s] Connection closed (attempt %s): %s", target, reconnect_attempt, e)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


async def connect_to_server(uri: str, target: str) -> None:
    """Open one WebSocket connection and pipe stdio for `target` until it drops.

    Connects to `uri`, starts `target`'s MCP server as a subprocess (per
    `build_server_command()`), and runs three concurrent pump tasks
    (WebSocket->stdin, stdout->WebSocket, stderr->terminal) until any one of
    them raises — at which point the child process is terminated (SIGTERM,
    then SIGKILL after `PROCESS_TERMINATE_TIMEOUT_SECONDS`) and the
    exception propagates to the caller (`connect_with_retry`, which decides
    whether/when to reconnect).
    """
    process = None
    try:
        logger.info("[%s] Connecting to WebSocket server...", target)
        async with websockets.connect(uri) as websocket:
            logger.info("[%s] Successfully connected to WebSocket server", target)

            cmd, env = build_server_command(target)
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                text=True,
                env=env,
            )
            logger.info("[%s] Started server process: %s", target, " ".join(cmd))

            await asyncio.gather(
                pipe_websocket_to_process(websocket, process, target),
                pipe_process_to_websocket(process, websocket, target),
                pipe_process_stderr_to_terminal(process, target),
            )
    except websockets.exceptions.ConnectionClosed as e:
        logger.error("[%s] WebSocket connection closed: %s", target, e)
        raise
    except Exception as e:
        logger.error("[%s] Connection error: %s", target, e)
        raise
    finally:
        if process is not None:
            logger.info("[%s] Terminating server process", target)
            try:
                process.terminate()
                process.wait(timeout=PROCESS_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
            logger.info("[%s] Server process terminated", target)


async def pipe_websocket_to_process(websocket, process: subprocess.Popen, target: str) -> None:
    """Forward each WebSocket message to the child process's stdin, one line per message.

    This is the direction xiaozhi -> MCP server: every JSON-RPC request/
    notification xiaozhi sends arrives here and is written verbatim (plus a
    newline, since the MCP server reads stdio line-delimited) to the child's
    stdin. Closes stdin when the loop ends (WebSocket closed or errored),
    which signals EOF to the child so it can shut down cleanly.
    """
    try:
        while True:
            message = await websocket.recv()
            logger.debug("[%s] << %s...", target, message[:LOG_PREVIEW_CHARS])
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            process.stdin.write(message + "\n")
            process.stdin.flush()
    except Exception as e:
        logger.error("[%s] Error in WebSocket to process pipe: %s", target, e)
        raise
    finally:
        if not process.stdin.closed:
            process.stdin.close()


async def pipe_process_to_websocket(process: subprocess.Popen, websocket, target: str) -> None:
    """Forward each line the child process writes to stdout onto the WebSocket.

    This is the direction MCP server -> xiaozhi: every JSON-RPC response/
    notification the server prints on stdout is sent as one WebSocket
    message. `readline()` runs in a thread (`asyncio.to_thread`) since
    `subprocess.Popen`'s pipes are blocking file objects, not asyncio
    streams. An empty read means the process closed stdout (exited), which
    ends this pump normally rather than raising.
    """
    try:
        while True:
            data = await asyncio.to_thread(process.stdout.readline)
            if not data:
                logger.info("[%s] Process has ended output", target)
                break
            logger.debug("[%s] >> %s...", target, data[:LOG_PREVIEW_CHARS])
            await websocket.send(data)
    except Exception as e:
        logger.error("[%s] Error in process to WebSocket pipe: %s", target, e)
        raise


async def pipe_process_stderr_to_terminal(process: subprocess.Popen, target: str) -> None:
    """Mirror the child process's stderr onto this process's stderr.

    The MCP server's own logs (this repo's `jmri-mcp` logs to stderr, never
    stdout — see `jmri_mcp/server`) aren't part of the MCP protocol and
    shouldn't go over the WebSocket; this just makes them visible wherever
    the bridge itself is running, for local debugging.
    """
    try:
        while True:
            data = await asyncio.to_thread(process.stderr.readline)
            if not data:
                logger.info("[%s] Process has ended stderr output", target)
                break
            sys.stderr.write(data)
            sys.stderr.flush()
    except Exception as e:
        logger.error("[%s] Error in process stderr pipe: %s", target, e)
        raise


def _signal_handler(sig, frame) -> None:
    """SIGINT handler: log and exit rather than dumping a traceback on Ctrl-C."""
    logger.info("Received interrupt signal, shutting down...")
    sys.exit(0)


def load_config() -> dict:
    """Load JSON config from $MCP_CONFIG, else this package's own mcp_config.json.

    Resolving next to __init__.py (not the current working directory) means
    `jmri-xiaozhi-bridge` works from any directory, not just
    src/xiaozhi_wrapper/ — the checked-in mcp_config.json travels with the
    installed package. Returns {} (not an error) if no config file is found
    at all, or if the resolved file fails to parse — callers treat an empty
    config as "no servers configured" rather than crashing the bridge.
    """
    default_path = os.path.join(os.path.dirname(__file__), "mcp_config.json")
    path = os.environ.get(ENV_MCP_CONFIG) or default_path
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load config %s: %s", path, e)
        return {}


def _resolve_command(command: str) -> str:
    """Resolve a bare config `command` (e.g. "jmri-mcp") to a runnable path.

    `shutil.which()` only searches `$PATH`, which doesn't necessarily
    include the env this bridge itself was launched from (e.g. invoked via
    an absolute path, as happens with Claude Desktop / xiaozhi launchers
    that don't activate the env's shell first) — see the bridge's own
    `sys.executable` directory, which is a sibling of `jmri-mcp` in any
    venv/conda env where both were installed together (both are
    `[project.scripts]` entry points of packages in this same workspace).
    Falls back to the bare command unchanged if not found there either, so
    `subprocess.Popen` raises its normal FileNotFoundError.
    """
    if os.path.isabs(command) or shutil.which(command):
        return command
    sibling = os.path.join(os.path.dirname(sys.executable), command)
    if os.path.isfile(sibling) and os.access(sibling, os.X_OK):
        return sibling
    return command


def build_server_command(target: str | None = None) -> tuple[list[str], dict]:
    """Build the [cmd, ...] argv and env for one server target.

    `target` is looked up in `load_config()`'s `mcpServers` map first:
      - `type`/`transportType: "stdio"` (the default if omitted) runs
        `command` with `args` directly — this is how `jmri-mcp` is launched.
      - `type` one of "sse"/"http"/"streamablehttp" instead runs
        `python -m mcp_proxy` against `url` (optionally with `-H` headers),
        translating a remote HTTP/SSE MCP server into a local stdio one so
        the same piping logic in `connect_to_server()` works either way.
      - `disabled: true` raises rather than silently skipping — callers
        that reach here already decided to start this specific target.
    Per-server `env` entries are merged onto a copy of this process's own
    environment (not replacing it), so the child still inherits things like
    PATH.

    If `target` isn't a name in the config (or config load found nothing),
    falls back to treating it as a local Python script path, run with the
    current interpreter (`sys.executable`) — this is `mcp_pipe.py`'s
    original back-compat mode, kept for running an ad hoc server script
    without adding it to mcp_config.json.

    target=None reads sys.argv[1] instead (used when this is invoked as
    `jmri-xiaozhi-bridge <script.py>` from the command line).
    """
    if target is None:
        assert len(sys.argv) >= 2, "missing server name or script path"
        target = sys.argv[1]
    cfg = load_config()
    servers = cfg.get(CONFIG_KEY_MCP_SERVERS, {}) if isinstance(cfg, dict) else {}

    if target in servers:
        entry = servers[target] or {}
        if entry.get(SERVER_KEY_DISABLED):
            raise RuntimeError(f"Server '{target}' is disabled in config")
        typ = (entry.get(SERVER_KEY_TYPE) or entry.get(SERVER_KEY_TRANSPORT_TYPE) or TRANSPORT_STDIO).lower()

        child_env = os.environ.copy()
        for k, v in (entry.get(SERVER_KEY_ENV) or {}).items():
            child_env[str(k)] = str(v)

        if typ == TRANSPORT_STDIO:
            command = entry.get(SERVER_KEY_COMMAND)
            args = entry.get(SERVER_KEY_ARGS) or []
            if not command:
                raise RuntimeError(f"Server '{target}' is missing 'command'")
            command = _resolve_command(command)
            return [command, *args], child_env

        if typ in HTTP_LIKE_TRANSPORTS:
            url = entry.get(SERVER_KEY_URL)
            if not url:
                raise RuntimeError(f"Server '{target}' (type {typ}) is missing 'url'")
            cmd = [sys.executable, "-m", "mcp_proxy"]
            if typ in (TRANSPORT_HTTP, TRANSPORT_STREAMABLE_HTTP):
                cmd += ["--transport", "streamablehttp"]
            headers = entry.get(SERVER_KEY_HEADERS) or {}
            for hk, hv in headers.items():
                cmd += ["-H", hk, str(hv)]
            cmd.append(url)
            return cmd, child_env

        raise RuntimeError(f"Unsupported server type: {typ}")

    script_path = target
    if not os.path.exists(script_path):
        raise RuntimeError(f"'{target}' is neither a configured server nor an existing script")
    return [sys.executable, script_path], os.environ.copy()


async def _amain() -> None:
    """Async body of `main()`: validate env, then run one or all configured servers.

    With no CLI argument, starts every non-disabled server in
    `mcpServers` concurrently (one `connect_with_retry` task each) and
    waits on all of them forever. With a script-path argument, runs just
    that one target instead (see `build_server_command()`'s fallback mode).
    """
    endpoint_url = os.environ.get(ENV_MCP_ENDPOINT)
    if not endpoint_url:
        logger.error("Please set the `%s` environment variable", ENV_MCP_ENDPOINT)
        sys.exit(1)

    target_arg = sys.argv[1] if len(sys.argv) >= 2 else None

    if not target_arg:
        cfg = load_config()
        servers_cfg = cfg.get(CONFIG_KEY_MCP_SERVERS) or {}
        all_servers = list(servers_cfg.keys())
        enabled = [name for name, entry in servers_cfg.items() if not (entry or {}).get(SERVER_KEY_DISABLED)]
        skipped = [name for name in all_servers if name not in enabled]
        if skipped:
            logger.info("Skipping disabled servers: %s", ", ".join(skipped))
        if not enabled:
            raise RuntimeError("No enabled mcpServers found in config")
        logger.info("Starting servers: %s", ", ".join(enabled))
        tasks = [asyncio.create_task(connect_with_retry(endpoint_url, t)) for t in enabled]
        await asyncio.gather(*tasks)
    else:
        if os.path.exists(target_arg):
            await connect_with_retry(endpoint_url, target_arg)
        else:
            logger.error(
                "Argument must be a local Python script path. "
                "To run configured servers, run without arguments."
            )
            sys.exit(1)


def main() -> None:
    """Run the bridge (entry point for the `jmri-xiaozhi-bridge` script).

    Installs a SIGINT handler for a clean Ctrl-C exit, then runs `_amain()`
    to completion. `_amain()` normally never returns (its tasks loop
    forever via `connect_with_retry`) — this only returns if it raises,
    which is caught and logged here rather than propagating a traceback,
    matching the ported script's original top-level error handling.
    """
    signal.signal(signal.SIGINT, _signal_handler)
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
    except Exception as e:
        logger.error("Program execution error: %s", e)
