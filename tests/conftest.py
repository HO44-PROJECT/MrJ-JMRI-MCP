import json
from pathlib import Path

import pytest
import respx
from httpx import Response

FIXTURES = Path(__file__).parent / "fixtures"
MOCK_JMRI_URL = "http://mock-jmri:12080"


@pytest.fixture(autouse=True)
def jmri_url(monkeypatch):
    """Point every test at a fake host by default; mocked via respx, never hits the network."""
    monkeypatch.setenv("JMRI_URL", MOCK_JMRI_URL)


@pytest.fixture
def power_fixture() -> list[dict]:
    return json.loads((FIXTURES / "power_response.json").read_text())


@pytest.fixture
def mock_power(power_fixture):
    """Mock GET /json/power to return the captured JMRI 5.4 fixture."""
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=power_fixture)
        )
        yield router


@pytest.fixture
def version_fixture() -> list[dict]:
    return json.loads((FIXTURES / "version_response.json").read_text())
