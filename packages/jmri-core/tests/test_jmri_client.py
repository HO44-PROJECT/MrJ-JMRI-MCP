import re

import pytest
import respx
from httpx import ConnectError, Response

from jmri_core.jmri_client import (
    JmriError,
    get_blocks,
    get_lights,
    get_roster,
    get_roster_function_labels,
    get_sensors,
    get_systems,
    get_turnouts,
    resolve_block,
    resolve_light,
    resolve_roster_entry,
    resolve_sensor,
    resolve_signal,
    resolve_system,
    resolve_turnout,
)
from jmri_core.testing.plugin import MOCK_JMRI_URL, expect_error


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


# --- get_lights ---


async def test_get_lights_unwraps_envelope_and_matches_fixture(mock_lights, lights_fixture):
    lights = await get_lights()
    assert lights == [entry["data"] for entry in lights_fixture]


async def test_get_lights_accepts_bare_data():
    bare = [{"name": "IL1", "userName": "Depot Lighting", "state": 4}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(return_value=Response(200, json=bare))
        lights = await get_lights()
    assert lights == bare


async def test_get_lights_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_lights()


async def test_get_lights_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/lights payload"):
            await get_lights()


# --- resolve_light: pure function, no I/O ---

LIGHTS = [
    {"name": "IL1", "userName": "Depot Lighting", "state": 4},
    {"name": "IL2", "userName": "Street Lamps", "state": 2},
    {"name": "IL3", "userName": None, "state": 4},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Depot Lighting", "IL1"),
        ("depot lighting", "IL1"),
        ("DEPOT LIGHTING", "IL1"),
        ("depot", "IL1"),
        ("IL1", "IL1"),
        ("il1", "IL1"),
        ("IL3", "IL3"),
    ],
)
def test_resolve_light_tolerant_match(query, expected_name):
    assert resolve_light(query, LIGHTS)["name"] == expected_name


def test_resolve_light_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous light"):
        resolve_light("l", LIGHTS)  # matches both "Depot Lighting" and "Street Lamps"


def test_resolve_light_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown light 'tgv'"):
        resolve_light("tgv", LIGHTS)


def test_resolve_light_empty_lights_raises():
    with pytest.raises(JmriError, match="no lights"):
        resolve_light("Depot Lighting", [])


def test_resolve_light_empty_query_raises():
    with pytest.raises(JmriError, match="No light name given"):
        resolve_light("", LIGHTS)
    with pytest.raises(JmriError, match="No light name given"):
        resolve_light("   ", LIGHTS)


def test_resolve_light_partial_system_id_fragment_matches():
    # Regression: the partial-match fallback used to check only userName,
    # never the system id - so a fragment of "IL3" (userName=None) always
    # failed even though the full id "IL3" already worked via exact match.
    assert resolve_light("L3", LIGHTS)["name"] == "IL3"


# --- get_turnouts ---


async def test_get_turnouts_unwraps_envelope_and_matches_fixture(mock_turnouts, turnouts_fixture):
    turnouts = await get_turnouts()
    assert turnouts == [entry["data"] for entry in turnouts_fixture]


async def test_get_turnouts_accepts_bare_data():
    bare = [{"name": "IT100", "userName": "Layout Turnout A", "state": 2}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(return_value=Response(200, json=bare))
        turnouts = await get_turnouts()
    assert turnouts == bare


async def test_get_turnouts_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_turnouts()


async def test_get_turnouts_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/turnouts payload"):
            await get_turnouts()


# --- resolve_turnout: pure function, no I/O ---

TURNOUTS = [
    {"name": "IT100", "userName": "Layout Turnout A", "state": 2},
    {"name": "IT101", "userName": "Layout Turnout BL", "state": 2},
    {"name": "OT23", "userName": "A / Mountain A -> Platform A/B", "state": 4},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Layout Turnout A", "IT100"),
        ("layout turnout a", "IT100"),
        ("LAYOUT TURNOUT A", "IT100"),
        ("IT100", "IT100"),
        ("it100", "IT100"),
        ("OT23", "OT23"),
    ],
)
def test_resolve_turnout_tolerant_match(query, expected_name):
    assert resolve_turnout(query, TURNOUTS)["name"] == expected_name


def test_resolve_turnout_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous turnout"):
        resolve_turnout("Layout Turnout", TURNOUTS)  # matches A and BL


def test_resolve_turnout_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown turnout 'tgv'"):
        resolve_turnout("tgv", TURNOUTS)


def test_resolve_turnout_empty_turnouts_raises():
    with pytest.raises(JmriError, match="no turnouts"):
        resolve_turnout("Layout Turnout A", [])


def test_resolve_turnout_empty_query_raises():
    with pytest.raises(JmriError, match="No turnout name given"):
        resolve_turnout("", TURNOUTS)
    with pytest.raises(JmriError, match="No turnout name given"):
        resolve_turnout("   ", TURNOUTS)


def test_resolve_turnout_partial_system_id_fragment_matches():
    # Regression: the partial-match fallback used to check only userName,
    # never the system id - so a fragment of "OT23" (e.g. "OT2") always
    # failed even though the full id "OT23" already worked via exact match.
    assert resolve_turnout("OT2", TURNOUTS)["name"] == "OT23"


# --- get_sensors ---


async def test_get_sensors_unwraps_envelope_and_matches_fixture(mock_sensors, sensors_fixture):
    sensors = await get_sensors()
    assert sensors == [entry["data"] for entry in sensors_fixture]


async def test_get_sensors_accepts_bare_data():
    bare = [{"name": "RS22", "userName": "Montagne B", "state": 4}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/sensors").mock(return_value=Response(200, json=bare))
        sensors = await get_sensors()
    assert sensors == bare


async def test_get_sensors_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/sensors").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_sensors()


async def test_get_sensors_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/sensors").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/sensors payload"):
            await get_sensors()


# --- resolve_sensor: pure function, no I/O ---

SENSORS = [
    {"name": "ISCLOCKRUNNING", "userName": None, "state": 2},
    {"name": "RS22", "userName": "Montagne B", "state": 4},
    {"name": "RS23", "userName": "Montagne A int", "state": 2},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Montagne B", "RS22"),
        ("montagne b", "RS22"),
        ("MONTAGNE B", "RS22"),
        ("RS22", "RS22"),
        ("rs22", "RS22"),
        ("ISCLOCKRUNNING", "ISCLOCKRUNNING"),
        ("isclockrunning", "ISCLOCKRUNNING"),
    ],
)
def test_resolve_sensor_tolerant_match(query, expected_name):
    assert resolve_sensor(query, SENSORS)["name"] == expected_name


def test_resolve_sensor_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous sensor"):
        resolve_sensor("Montagne", SENSORS)  # matches "Montagne B" and "Montagne A int"


def test_resolve_sensor_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown sensor 'tgv'"):
        resolve_sensor("tgv", SENSORS)


def test_resolve_sensor_empty_sensors_raises():
    with pytest.raises(JmriError, match="no sensors"):
        resolve_sensor("Montagne B", [])


def test_resolve_sensor_empty_query_raises():
    with pytest.raises(JmriError, match="No sensor name given"):
        resolve_sensor("", SENSORS)
    with pytest.raises(JmriError, match="No sensor name given"):
        resolve_sensor("   ", SENSORS)


def test_resolve_sensor_partial_system_id_fragment_matches():
    # Regression: the partial-match fallback used to check only userName,
    # never the system id - so a fragment of "ISCLOCKRUNNING" (userName=None)
    # always failed even though the full id already worked via exact match.
    assert resolve_sensor("CLOCKRUN", SENSORS)["name"] == "ISCLOCKRUNNING"


# --- get_blocks ---


async def test_get_blocks_unwraps_envelope_and_matches_fixture(mock_blocks, blocks_fixture):
    blocks = await get_blocks()
    assert blocks == [entry["data"] for entry in blocks_fixture]


async def test_get_blocks_accepts_bare_data():
    bare = [{"name": "IB1", "userName": "Montagne A", "state": 4, "sensor": "RS24", "value": None}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/blocks").mock(return_value=Response(200, json=bare))
        blocks = await get_blocks()
    assert blocks == bare


async def test_get_blocks_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/blocks").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_blocks()


async def test_get_blocks_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/blocks").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/blocks payload"):
            await get_blocks()


# --- resolve_block: pure function, no I/O ---

BLOCKS = [
    {"name": "IB1", "userName": "Montagne A", "state": 4, "sensor": "RS24", "value": None},
    {"name": "IB2", "userName": "Montagne B", "state": 2, "sensor": "RS42", "value": None},
    {"name": "IB3", "userName": "Montagne A int", "state": 4, "sensor": "RS45", "value": None},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Montagne B", "IB2"),
        ("montagne b", "IB2"),
        ("MONTAGNE B", "IB2"),
        ("IB2", "IB2"),
        ("ib2", "IB2"),
    ],
)
def test_resolve_block_tolerant_match(query, expected_name):
    assert resolve_block(query, BLOCKS)["name"] == expected_name


def test_resolve_block_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous block"):
        resolve_block("Montagne", BLOCKS)  # matches "Montagne A", "Montagne B", "Montagne A int"


def test_resolve_block_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown block 'tgv'"):
        resolve_block("tgv", BLOCKS)


def test_resolve_block_empty_blocks_raises():
    with pytest.raises(JmriError, match="no blocks"):
        resolve_block("Montagne B", [])


def test_resolve_block_empty_query_raises():
    with pytest.raises(JmriError, match="No block name given"):
        resolve_block("", BLOCKS)
    with pytest.raises(JmriError, match="No block name given"):
        resolve_block("   ", BLOCKS)


def test_resolve_block_partial_system_id_fragment_matches():
    # Regression: the partial-match fallback used to check only userName,
    # never the system id - so a fragment of "IB1" (e.g. "B1") always failed
    # even though the full id "IB1" already worked via exact match.
    assert resolve_block("B1", BLOCKS)["name"] == "IB1"


# --- resolve_signal: pure function, no I/O ---

SIGNALS = [
    {"name": "ZF$dsm:DB-HV-1969:block(31)", "userName": "Entry Signal A", "aspect": "Hp1", "lit": True, "held": False},
    {"name": "ZF$dsm:DB-HV-1969:block(45)", "userName": None, "aspect": "Hp0", "lit": True, "held": False},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Entry Signal A", "ZF$dsm:DB-HV-1969:block(31)"),
        ("entry signal a", "ZF$dsm:DB-HV-1969:block(31)"),
        ("ZF$dsm:DB-HV-1969:block(31)", "ZF$dsm:DB-HV-1969:block(31)"),
        ("ZF$dsm:DB-HV-1969:block(45)", "ZF$dsm:DB-HV-1969:block(45)"),
        ("entry", "ZF$dsm:DB-HV-1969:block(31)"),
    ],
)
def test_resolve_signal_tolerant_match(query, expected_name):
    assert resolve_signal(query, SIGNALS)["name"] == expected_name


def test_resolve_signal_partial_system_id_fragment_matches():
    # Regression: the partial-match fallback used to check only userName,
    # never the system id - so a fragment of "block(45)" (userName=None)
    # always failed even though the full id already worked via exact match.
    assert resolve_signal("block(45)", SIGNALS)["name"] == "ZF$dsm:DB-HV-1969:block(45)"


def test_resolve_signal_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous signal mast"):
        resolve_signal("DB-HV-1969", SIGNALS)  # matches both masts' system names


def test_resolve_signal_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown signal mast 'tgv'"):
        resolve_signal("tgv", SIGNALS)


def test_resolve_signal_empty_signals_raises():
    with pytest.raises(JmriError, match="no signal mast"):
        resolve_signal("Entry Signal A", [])


def test_resolve_signal_empty_query_raises():
    with pytest.raises(JmriError, match="No signal mast name given"):
        resolve_signal("", SIGNALS)
    with pytest.raises(JmriError, match="No signal mast name given"):
        resolve_signal("   ", SIGNALS)


# --- get_roster ---


async def test_get_roster_compacts_fixture_entries(mock_roster, roster_fixture):
    roster = await get_roster()
    assert roster == [
        {
            "name": "141R", "address": 2, "road": "Mikado 141 R",
            "road_number": "141 R 1246, dépôt de Miramas", "manufacturer": "Jouef",
            "model": "8273", "owner": "SNCF", "date_modified": "2024-01-20T13:18:40.774+00:00",
            "groups": ["test"],
        },
        {
            "name": "Autorail", "address": 4, "road": "Railcar",
            "road_number": "", "manufacturer": "", "model": "4185A",
            "owner": "", "date_modified": "2024-01-20T13:18:40.774+00:00",
            "groups": [],
        },
        {
            "name": "Boite à Sel", "address": 8, "road": "",
            "road_number": "", "manufacturer": "", "model": "",
            "owner": "", "date_modified": "2024-01-20T13:18:40.774+00:00",
            "groups": [],
        },
    ]


async def test_get_roster_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_roster()


async def test_get_roster_skips_entries_with_unusable_address():
    bad = [
        {"type": "rosterEntry", "data": {"name": "Ghost", "address": "not-a-number"}},
        {"type": "rosterEntry", "data": {"name": "141R", "address": "2", "road": "Mikado", "model": "8273"}},
    ]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(return_value=Response(200, json=bad))
        roster = await get_roster()
    assert roster == [{
        "name": "141R", "address": 2, "road": "Mikado",
        "road_number": "", "manufacturer": "", "model": "8273",
        "owner": "", "date_modified": "", "groups": [],
    }]


async def test_get_roster_accepts_bare_data():
    bare = [{"name": "141R", "address": "2", "road": "Mikado", "model": "8273"}]
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(return_value=Response(200, json=bare))
        roster = await get_roster()
    assert roster == [{
        "name": "141R", "address": 2, "road": "Mikado",
        "road_number": "", "manufacturer": "", "model": "8273",
        "owner": "", "date_modified": "", "groups": [],
    }]


async def test_get_roster_raises_on_non_list_non_dict_payload():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(return_value=Response(200, json="oops"))
        with pytest.raises(JmriError, match="Unexpected /json/roster payload"):
            await get_roster()


# --- get_roster_function_labels ---


async def test_get_roster_function_labels_returns_only_labeled(mock_roster):
    labels = await get_roster_function_labels("Autorail")
    assert labels == {0: "Lumières avant", 1: "Lumières cabine", 2: "Lumières arrière"}


async def test_get_roster_function_labels_empty_when_none_set(mock_roster):
    labels = await get_roster_function_labels("Boite à Sel")
    assert labels == {}


async def test_get_roster_function_labels_unknown_name_raises(mock_roster):
    with pytest.raises(JmriError, match="No roster entry named 'tgv'"):
        await get_roster_function_labels("tgv")


async def test_get_roster_function_labels_raises_on_connection_failure():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/roster").mock(side_effect=ConnectError("refused"))
        with pytest.raises(JmriError, match="GET .*failed"):
            await get_roster_function_labels("Autorail")


# --- resolve_roster_entry: pure function, no I/O ---

ROSTER = [
    {"name": "141R", "address": 2, "road": "Mikado 141 R", "model": "8273"},
    {"name": "Autorail", "address": 4, "road": "Railcar", "model": "4185A"},
    {"name": "Boite à Sel", "address": 8, "road": "", "model": ""},
]


@pytest.mark.parametrize(
    "query,expected_name",
    [
        ("Autorail", "Autorail"),
        ("autorail", "Autorail"),
        ("AUTORAIL", "Autorail"),
        ("auto", "Autorail"),
        ("141R", "141R"),
        ("141r", "141R"),
        ("boite a sel", "Boite à Sel"),
        ("Boite à Sel", "Boite à Sel"),
        ("BOITE A SEL", "Boite à Sel"),
    ],
)
def test_resolve_roster_entry_tolerant_match(query, expected_name):
    assert resolve_roster_entry(query, ROSTER)["name"] == expected_name


def test_resolve_roster_entry_ambiguous_fragment_raises():
    with pytest.raises(JmriError, match="Ambiguous locomotive"):
        resolve_roster_entry("a", ROSTER)  # matches both Autorail and Boite à Sel


def test_resolve_roster_entry_unknown_name_raises():
    with pytest.raises(JmriError, match="Unknown locomotive 'tgv'"):
        resolve_roster_entry("tgv", ROSTER)


def test_resolve_roster_entry_empty_roster_raises():
    expected = expect_error("none_available", kind="locomotive")
    with pytest.raises(JmriError, match=re.escape(expected)):
        resolve_roster_entry("Autorail", [])


def test_resolve_roster_entry_empty_query_raises():
    expected = expect_error("no_query_given", kind="locomotive")
    with pytest.raises(JmriError, match=re.escape(expected)):
        resolve_roster_entry("", ROSTER)
    with pytest.raises(JmriError, match=re.escape(expected)):
        resolve_roster_entry("   ", ROSTER)


@pytest.mark.parametrize(
    "query,expected_name",
    [("2", "141R"), ("4", "Autorail"), ("8", "Boite à Sel")],
)
def test_resolve_roster_entry_matches_by_dcc_address(query, expected_name):
    assert resolve_roster_entry(query, ROSTER)["name"] == expected_name


def test_resolve_roster_entry_unknown_address_raises():
    with pytest.raises(JmriError, match="No roster entry with address 99"):
        resolve_roster_entry("99", ROSTER)


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
