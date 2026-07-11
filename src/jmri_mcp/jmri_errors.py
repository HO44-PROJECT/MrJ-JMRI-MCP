"""Shared, structured JmriError, raised by both jmri_client (HTTP) and jmri_ws (WebSocket).

Carries a machine-readable code + interpolation kwargs rather than a
pre-formatted English message, so cli/tools can translate at the catch
site via jmri_mcp.i18n while str(exc)/logging stays fixed English
regardless of the active JMRI_MCP_LANG (this project's repo/code content
is English by convention — see CLAUDE.md).

Sits above jmri_client and jmri_ws (which don't import each other) to
avoid a new inter-package dependency; both import this shared class
instead of each defining their own.
"""

from typing import Any


class JmriError(Exception):
    """JMRI is unreachable, or returned an unusable/ambiguous response.

    Args:
        code: short machine-readable i18n message key under "errors.",
            e.g. "unknown_entity".
        **kwargs: interpolation values for that code's message template
            (see jmri_mcp.i18n's en.json/fr.json).
    """

    def __init__(self, code: str, **kwargs: Any) -> None:
        self.code = code
        self.kwargs = kwargs
        super().__init__(code)

    def __str__(self) -> str:
        from jmri_mcp.i18n import lookup

        return lookup("en", f"errors.{self.code}", **self.kwargs)
