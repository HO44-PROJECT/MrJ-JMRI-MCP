"""Small helpers shared across jmri-cli's command modules."""

from jmri_core.constants.cli import CLI_THROTTLE_ID_PREFIX


def cli_throttle_id(address: int) -> str:
    """Derive this CLI's own JMRI throttle id for a DCC address.

    Each jmri-cli invocation opens a fresh WebSocket connection (see
    module docstring in jmri_cli), so there is no cross-invocation
    state to key off of — the address itself, prefixed, is enough to
    identify the throttle to JMRI for the lifetime of one command.

    Args:
        address: The locomotive's DCC address.

    Returns:
        A throttle id string unique to this address, e.g. "cli3".
    """
    return f"{CLI_THROTTLE_ID_PREFIX}{address}"
