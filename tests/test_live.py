"""Opt-in tests against a real, reachable JMRI server.

Skipped by default (the rest of the suite uses an autouse fixture that
points JMRI_URL at a mock host, which this file overrides). Configure your
layout in config/live.ini (copy from config/live.example.ini), then run:

    pytest -m live

JMRI_URL_LIVE / JMRI_WRITE_TEST_SYSTEM env vars override config/live.ini if set.
"""

import asyncio
import configparser
import os
from pathlib import Path

import pytest

from jmri_mcp.jmri_client import get_systems, resolve_system, set_power

pytestmark = pytest.mark.live

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "live.ini"


def _read_config() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if _CONFIG_PATH.exists():
        parser.read(_CONFIG_PATH)
    return parser


def _config_value(env_var: str, ini_key: str) -> str | None:
    if os.environ.get(env_var):
        return os.environ[env_var]
    return _read_config().get("jmri", ini_key, fallback=None)


@pytest.fixture(autouse=True)
def real_jmri_url(monkeypatch):
    url = _config_value("JMRI_URL_LIVE", "url")
    if not url:
        pytest.skip(
            "No live JMRI configured: copy config/live.example.ini to "
            "config/live.ini, or set JMRI_URL_LIVE"
        )
    monkeypatch.setenv("JMRI_URL", url)


def _config_bool(env_var: str, ini_key: str, default: bool = False) -> bool:
    raw = _config_value(env_var, ini_key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _config_float(env_var: str, ini_key: str, default: float) -> float:
    raw = _config_value(env_var, ini_key)
    return float(raw) if raw is not None else default


@pytest.fixture
def write_test_system() -> str:
    if not _config_bool("JMRI_ENABLE_WRITE_TESTS", "enable_write_tests"):
        pytest.skip(
            "Write tests disabled: set enable_write_tests = true in "
            "config/live.ini to opt in (this drives a real relay)"
        )
    system = _config_value("JMRI_WRITE_TEST_SYSTEM", "write_test_system")
    if not system:
        pytest.skip(
            "No write-test system configured: set write_test_system in "
            "config/live.ini, or JMRI_WRITE_TEST_SYSTEM"
        )
    return system


@pytest.fixture
def min_toggle_interval() -> float:
    return _config_float("JMRI_MIN_TOGGLE_INTERVAL_SECONDS", "min_toggle_interval_seconds", 5.0)


async def test_discovers_real_systems():
    systems = await get_systems()
    assert systems, "expected at least one power system from the real JMRI"
    for s in systems:
        assert "name" in s and "state" in s and "prefix" in s


async def test_resolves_default_system():
    systems = await get_systems()
    default = resolve_system(None, systems)
    assert default.get("default") is True or len(systems) == 1


async def test_set_power_round_trip_restores_original_state(
    write_test_system, min_toggle_interval
):
    """Toggle the configured test system and leave it as we found it.

    Real DCC++ hardware drives a physical relay: rapid on/off cycling is
    hard on it (relay wear, inrush current), so this waits at least
    min_toggle_interval seconds between the toggle and the restore.
    """
    systems = await get_systems()
    target = resolve_system(write_test_system, systems)
    prefix = target["prefix"]
    original_state = target["state"]
    was_on = original_state == 2  # POWER_ON

    try:
        result = await set_power(prefix, turn_on=not was_on)
        assert result["confirmed"], (
            f"requested {'OFF' if was_on else 'ON'} on {target['name']} "
            f"but observed state {result['state']} after re-read"
        )
        await asyncio.sleep(min_toggle_interval)
    finally:
        restored = await set_power(prefix, turn_on=was_on)
        assert restored["confirmed"], (
            f"FAILED TO RESTORE {target['name']} to its original state "
            f"({'ON' if was_on else 'OFF'}) — check it manually"
        )
