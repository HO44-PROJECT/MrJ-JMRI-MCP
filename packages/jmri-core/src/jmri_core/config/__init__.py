"""Runtime configuration read from environment variables."""

import os
from urllib.parse import urlsplit

from jmri_core import i18n

DEFAULT_JMRI_URL = "http://localhost:12080"

# Playful, memorable default so an exhibition host who didn't set a custom
# password at .mcpb install time still has SOME phrase to exit with, rather
# than being locked into exhibition mode. Not meant as real security (this
# is a demo-mode guard against curious visitors, not an auth system) — see
# jmri_mcp.tools.mode for how it's used.
DEFAULT_EXHIBITION_PASSWORD = "this is sparta"


def get_jmri_url() -> str:
    """Return the JMRI web server base URL from JMRI_URL, validated.

    Accepts http(s)://host[:port]; a trailing slash is stripped so callers
    can safely append /json/... paths.
    """
    url = os.environ.get("JMRI_URL", DEFAULT_JMRI_URL).strip().rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(i18n.t("errors.invalid_jmri_url", url=url, default=DEFAULT_JMRI_URL))
    return url


def get_exhibition_password() -> str:
    """Return the password required to exit exhibition mode, from EXHIBITION_PASSWORD.

    Falls back to DEFAULT_EXHIBITION_PASSWORD if unset — exhibition mode
    stays exitable even when the .mcpb installer's password field was left
    blank. The caller (jmri_mcp.tools.mode.exit_exhibition_mode) compares
    this tolerantly (case/accent/whitespace-insensitive), since the
    password is normally spoken aloud through voice transcription — this
    guards against a general audience poking at a demo, not a real threat
    model, so a transcription quirk shouldn't lock the operator out.
    """
    return os.environ.get("EXHIBITION_PASSWORD") or DEFAULT_EXHIBITION_PASSWORD


def get_exhibition_allowed_addresses() -> set[int] | None:
    """Return the DCC address allowlist for exhibition mode, from EXHIBITION_ALLOWED_ADDRESSES.

    Parses a comma-separated list of integers (e.g. "4,5,6"). Returns None
    when unset or empty — meaning no address restriction is applied even
    while exhibition mode is otherwise active (only the power/speed/
    direction restrictions apply). Non-integer entries are skipped rather
    than raising, since this is read once at call time from a value a user
    typed into an install-time form, and a single typo shouldn't take the
    whole server down.
    """
    raw = os.environ.get("EXHIBITION_ALLOWED_ADDRESSES", "").strip()
    if not raw:
        return None
    addresses = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            addresses.add(int(part))
    return addresses or None


def get_exhibition_start_on() -> bool:
    """Return whether the server should start already in exhibition mode, from EXHIBITION_START_ON.

    True for any of "1"/"true"/"yes"/"on" (case-insensitive), False
    otherwise or when unset — matches the .mcpb installer's likely
    representation of a checkbox/toggle input. Lets an exhibition host
    configure this once at install time instead of having to say "passe
    en mode exposition" at the start of every session.
    """
    raw = os.environ.get("EXHIBITION_START_ON", "").strip().casefold()
    return raw in ("1", "true", "yes", "on")
