import pytest


@pytest.fixture(autouse=True)
def isolated_cli_state(monkeypatch, tmp_path):
    """Point jmri-cli's local throttle-state cache at a tmp file, never the
    real user's ~/.jmri-cli/throttle_state.json."""
    import jmri_cli.state as state_module

    monkeypatch.setattr(state_module, "STATE_FILE", tmp_path / "throttle_state.json")
