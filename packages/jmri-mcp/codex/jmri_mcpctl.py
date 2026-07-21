#!/usr/bin/env python3
"""Cross-platform installer and controller for JMRI MCP in Codex."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


def default_source_dir() -> Path:
    """The nearest ancestor of this script with a pyproject.toml.

    Standalone .codex.zip layout: jmri_mcpctl.py sits right next to its own
    bundled pyproject.toml (see build_codex_zip.py), so this resolves to the
    unzip directory itself. Monorepo dev layout: it's four levels up
    (packages/jmri-mcp/codex/jmri_mcpctl.py -> repo root's workspace
    pyproject.toml). Walking up covers both without hardcoding either depth.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit(
        "Error: no pyproject.toml found above jmri_mcpctl.py; "
        "set JMRI_MCP_SOURCE_DIR explicitly."
    )


MCP_NAME = os.environ.get("JMRI_MCP_NAME", "jmri")
SOURCE_DIR = Path(
    os.environ.get("JMRI_MCP_SOURCE_DIR") or default_source_dir()
).expanduser().resolve()

# Dedicated venv name (not uv's default ".venv"): SOURCE_DIR defaults to this
# repo's own root, which already has its own dev ".venv" shared by other
# integrations (Claude Desktop, Kira/xiaozhi, jmri-cli dev use). A uniquely
# named venv keeps `uninstall --purge` safe by construction — it can only
# ever be this script's own isolated environment, never the shared one.
VENV_NAME = ".venv-jmri-mcp-codex"


def uv_env() -> dict[str, str]:
    env = os.environ.copy()
    env["UV_PROJECT_ENVIRONMENT"] = VENV_NAME
    return env


def find_executable(name: str, candidates: list[Path]) -> str:
    found = shutil.which(name)
    if found:
        return found
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SystemExit(f"Error: {name} executable not found.")


def find_codex() -> str:
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
                Path("/Applications/Codex.app/Contents/Resources/codex"),
            ]
        )
    elif os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        programs = Path(os.environ.get("ProgramFiles", ""))
        candidates.extend(
            [
                local / "Programs" / "ChatGPT" / "resources" / "codex.exe",
                local / "Programs" / "Codex" / "resources" / "codex.exe",
                programs / "ChatGPT" / "resources" / "codex.exe",
                programs / "Codex" / "resources" / "codex.exe",
            ]
        )
    return find_executable("codex", candidates)


CODEX = find_codex()


def run(
    command: list[str],
    *,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=capture,
        env=env,
    )


def get_registration() -> dict | None:
    result = run([CODEX, "mcp", "get", MCP_NAME, "--json"], capture=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def require_project() -> None:
    if not (SOURCE_DIR / "pyproject.toml").is_file():
        raise SystemExit(f"Error: project not found: {SOURCE_DIR}")


def runtime_config() -> dict[str, str]:
    jmri_url = os.environ.get("JMRI_URL")
    if not jmri_url:
        raise SystemExit(
            "Error: set JMRI_URL, for example "
            'JMRI_URL="http://10.0.20.20:12080"'
        )
    return {
        "JMRI_URL": jmri_url,
        "EXHIBITION_PASSWORD": os.environ.get(
            "EXHIBITION_PASSWORD", "this is sparta"
        ),
        "EXHIBITION_ALLOWED_ADDRESSES": os.environ.get(
            "EXHIBITION_ALLOWED_ADDRESSES", ""
        ),
        "EXHIBITION_START_ON": os.environ.get("EXHIBITION_START_ON", "false"),
    }


def remove_registration() -> bool:
    if get_registration() is None:
        return False
    result = run([CODEX, "mcp", "remove", MCP_NAME], capture=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"Error: unable to remove MCP registration: {message}")
    return True


def register_server() -> None:
    require_project()
    config = runtime_config()
    remove_registration()

    command = [CODEX, "mcp", "add", MCP_NAME]
    for key, value in config.items():
        command.extend(["--env", f"{key}={value}"])
    # Codex launches this command itself later, on its own — UV_PROJECT_ENVIRONMENT
    # must travel as a registered --env, not just be set for this script's own
    # subprocess calls, so Codex's own `uv run` also targets VENV_NAME.
    command.extend(["--env", f"UV_PROJECT_ENVIRONMENT={VENV_NAME}"])
    command.extend(["--", "uv", "run", "--project", str(SOURCE_DIR), "jmri-mcp"])

    result = run(command, capture=True)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"Error: unable to register MCP server: {message}")

    print("JMRI MCP enabled.")
    print(f"  JMRI URL        : {config['JMRI_URL']}")
    print(f"  Exhibition mode : {config['EXHIBITION_START_ON']}")
    print("Open a new Codex task to apply the change.")


def install_server() -> None:
    require_project()
    runtime_config()
    uv = find_executable("uv", [])
    print("Installing dependencies...")
    result = run([uv, "sync", "--project", str(SOURCE_DIR)], env=uv_env())
    if result.returncode != 0:
        raise SystemExit("Error: dependency installation failed.")
    register_server()


def stop_server() -> None:
    if remove_registration():
        print("JMRI MCP disabled.")
        print("Open a new Codex task to apply the change.")
    else:
        print("JMRI MCP is already disabled.")


def registered_jmri_url(registration: dict | None) -> str | None:
    if not registration:
        return None
    transport = registration.get("transport", {})
    environment = transport.get("env", {})
    return environment.get("JMRI_URL")


def url_is_reachable(url: str) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, ValueError, TimeoutError):
        return False


def show_status() -> None:
    registration = get_registration()
    print(f"JMRI MCP: {'enabled' if registration else 'disabled'}")

    jmri_url = os.environ.get("JMRI_URL") or registered_jmri_url(registration)
    if not jmri_url:
        print("JMRI URL: not configured")
        return

    print(f"JMRI URL: {jmri_url}")
    state = "reachable" if url_is_reachable(jmri_url) else "unreachable or stopped"
    print(f"JMRI Web: {state}")


def uninstall_server(purge: bool) -> None:
    print("Uninstalling JMRI MCP")
    print()

    print("[1/3] Codex registration")
    if remove_registration():
        print(f"      MCP entry '{MCP_NAME}' removed.")
    else:
        print(f"      MCP entry '{MCP_NAME}' is not registered; nothing to remove.")

    print("[2/3] Python environment")
    venv = SOURCE_DIR / VENV_NAME
    if purge:
        if venv.name != VENV_NAME or venv.parent != SOURCE_DIR:
            raise SystemExit(f"      Unexpected path; refusing to remove: {venv}")
        if venv.is_dir():
            print(f"      Removing {venv}...")
            shutil.rmtree(venv)
            print("      Removed.")
        else:
            print(f"      No {VENV_NAME} found; nothing to remove.")
    else:
        print(f"      Preserved: {venv}")
        print("      Use 'uninstall --purge' to remove it as well.")

    print("[3/3] Verification")
    if get_registration() is not None:
        raise SystemExit("      Failed: the MCP entry is still registered.")
    print("      JMRI MCP is no longer registered in Codex.")
    print()
    print("Preserved:")
    print(f"  - source code: {SOURCE_DIR}")
    print("  - JMRI and its configuration")
    print("  - uv, Python, and Codex")
    print()
    print("Open a new Codex task to apply the change.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install and control the local JMRI MCP server in Codex."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "start", "stop", "restart", "status"):
        subparsers.add_parser(name)
    uninstall = subparsers.add_parser("uninstall")
    uninstall.add_argument(
        "--purge",
        action="store_true",
        help=f"also remove the project's {VENV_NAME} directory",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "install":
        install_server()
    elif args.command == "start":
        register_server()
    elif args.command == "stop":
        stop_server()
    elif args.command == "restart":
        stop_server()
        register_server()
    elif args.command == "status":
        show_status()
    elif args.command == "uninstall":
        uninstall_server(args.purge)


if __name__ == "__main__":
    main()
