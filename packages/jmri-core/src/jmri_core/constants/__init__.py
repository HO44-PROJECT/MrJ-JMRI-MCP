"""Dedicated constants modules, organized by the layer that owns each value.

    protocol.py       JMRI JSON field names, WebSocket message types.
    endpoints.py       JMRI REST path templates.
    client_tuning.py   Timeouts, delays, ramp granularity.
    cli.py             State-name lookup tables and CLI-only tuning values.

Import from the specific module (e.g. `from jmri_core.constants import
endpoints` then `endpoints.TURNOUT`) to keep the source of a constant
obvious at the call site.
"""

from jmri_core.constants import cli, client_tuning, endpoints, protocol

__all__ = ["protocol", "endpoints", "client_tuning", "cli"]
