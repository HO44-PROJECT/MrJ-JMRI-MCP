from jmri_cli._dcc_system import dcc_system_display, system_names_by_prefix


async def test_system_names_by_prefix_maps_prefix_to_full_name(mock_power):
    names = await system_names_by_prefix()
    assert names == {"O": "DCC++ Ohara", "Z": "DCC++ Zou", "R": "DCC++ Raijin"}


async def test_system_names_by_prefix_empty_on_jmri_error(monkeypatch):
    async def raise_error():
        from jmri_core.jmri_client import JmriError

        raise JmriError("unreachable")

    monkeypatch.setattr("jmri_cli._dcc_system.get_systems", raise_error)
    names = await system_names_by_prefix()
    assert names == {}


def test_dcc_system_display_matches_known_prefix():
    names = {"O": "DCC++ Ohara", "R": "DCC++ Raijin"}
    assert dcc_system_display("OT23", names) == "DCC++ Ohara"


def test_dcc_system_display_unmatched_prefix_returns_dash():
    names = {"O": "DCC++ Ohara"}
    assert dcc_system_display("IT100", names) == "-"


def test_dcc_system_display_empty_system_id_returns_dash():
    assert dcc_system_display("", {"O": "DCC++ Ohara"}) == "-"


def test_dcc_system_display_empty_names_dict_returns_dash():
    assert dcc_system_display("OT23", {}) == "-"
