"""Opt-in tests against a real, reachable JMRI server.

Skipped by default (the rest of the suite uses an autouse fixture that
points JMRI_URL at a mock host, which this file overrides). Run explicitly
against your layout with:

    JMRI_URL_LIVE=http://10.0.20.20:12080 pytest -m live
"""

import os

import pytest

from jmri_mcp.jmri_client import get_systems, resolve_system

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def real_jmri_url(monkeypatch):
    url = os.environ.get("JMRI_URL_LIVE")
    if not url:
        pytest.skip("Set JMRI_URL_LIVE to a real JMRI server to run live tests")
    monkeypatch.setenv("JMRI_URL", url)


async def test_discovers_real_systems():
    systems = await get_systems()
    assert systems, "expected at least one power system from the real JMRI"
    for s in systems:
        assert "name" in s and "state" in s and "prefix" in s


async def test_resolves_default_system():
    systems = await get_systems()
    default = resolve_system(None, systems)
    assert default.get("default") is True or len(systems) == 1
