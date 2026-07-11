"""Shared HTTP plumbing for jmri_client's domain modules (power.py, roster.py).

All layout data (systems, roster, turnouts, ...) is discovered live from
JMRI; nothing is hardcoded here.
"""

from typing import Any

import httpx

from jmri_mcp.config import get_jmri_url
from jmri_mcp.constants.client_tuning import HTTP_TIMEOUT_SECONDS
from jmri_mcp.constants.protocol import FIELD_DATA, FIELD_TYPE
from jmri_mcp.jmri_errors import JmriError

__all__ = ["JmriError", "_get_json", "_post_json", "_unwrap"]


def _unwrap(obj: Any) -> Any:
    """Strip the JMRI message envelope {"type": ..., "data": {...}} if present."""
    if isinstance(obj, dict) and FIELD_DATA in obj and FIELD_TYPE in obj:
        return obj[FIELD_DATA]
    return obj


async def _get_json(path: str) -> Any:
    url = f"{get_jmri_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise JmriError("http_get_failed", url=url, exc=exc) from exc


async def _post_json(path: str, body: dict) -> Any:
    url = f"{get_jmri_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise JmriError("http_post_failed", url=url, exc=exc) from exc
