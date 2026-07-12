"""Runtime configuration read from environment variables."""

import os
from urllib.parse import urlsplit

from jmri_core import i18n

DEFAULT_JMRI_URL = "http://localhost:12080"


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
