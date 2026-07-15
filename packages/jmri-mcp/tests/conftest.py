import pytest


@pytest.fixture(autouse=True)
def reset_executor_mode():
    """Reset tools.mode's process-wide flag so tests don't leak state across each other.

    Reset to True, matching the module's real default (concise-by-default,
    see tools/mode.py) — not an arbitrary reset value.
    """
    import jmri_mcp.tools.mode as mode_module

    mode_module._executor_mode = True
    yield
    mode_module._executor_mode = True
