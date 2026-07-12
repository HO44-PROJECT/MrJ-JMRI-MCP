"""Shared pytest fixtures for testing against a simulated JMRI server.

Used by all three packages' test suites (jmri-core, jmri-cli, jmri-mcp) so
the JMRI HTTP/WebSocket simulation logic (fake_jmri, mock_power/mock_lights/
etc.) lives in exactly one place instead of being copy-pasted per package.
Installed as a pytest plugin — see `jmri_core.testing.plugin`.
"""
