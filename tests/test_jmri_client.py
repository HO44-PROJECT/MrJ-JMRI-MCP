import pytest
import respx
from httpx import ConnectError, Response

from jmri_mcp.jmri_client import JmriError, get_systems, resolve_system
from tests.conftest import MOCK_JMRI_URL


async def test_get_systems_unwraps_envelope_and_matches_fixture(mock_power, power_fixture):
    systems = await get_systems()
    assert systems == [entry["data"] for entry in power_fixture]


async def test_get_systems_accepts_bare_data(monkeypatch):
    bare = [{"name": "DCC++ Raijin", "state": 2, "default": True, "prefix": "R"}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json=bare))
        systems = await get_systems()
    assert systems == bare


async def test_get_systems_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_systems()


async def test_get_systems_raises_on_unexpected_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={"unexpected": "shape"})
        )
        systems = await get_systems()
        assert systems == [{"unexpected": "shape"}]  # single dict wrapped as a list


async def test_get_systems_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/power payload"):
            await get_systems()


# --- resolve_system: pure function, no I/O ---

SYSTEMS = [
    {"name": "DCC++ Ohara", "prefix": "O", "state": 4, "default": False},
    {"name": "DCC++ Zou", "prefix": "Z", "state": 4, "default": False},
    {"name": "DCC++ Raijin", "prefix": "R", "state": 4, "default": True},
]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("ohara", "DCC++ Ohara"),
        ("OHARA", "DCC++ Ohara"),
        ("o", "DCC++ Ohara"),
        ("zou", "DCC++ Zou"),
        ("z", "DCC++ Zou"),
        ("raijin", "DCC++ Raijin"),
        ("DCC++ Ohara", "DCC++ Ohara"),
        (None, "DCC++ Raijin"),
        ("   ", "DCC++ Raijin"),
    ],
)
def test_resolve_system_tolerant_match(query, expected):
    assert resolve_system(query, SYSTEMS)["name"] == expected


def test_resolve_system_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous system 'dcc'"):
        resolve_system("dcc", SYSTEMS)


def test_resolve_system_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown system 'tgv'"):
        resolve_system("tgv", SYSTEMS)


def test_resolve_system_no_systems_raises():
    with pytest.raises(JmriError, match="no power systems"):
        resolve_system(None, [])
