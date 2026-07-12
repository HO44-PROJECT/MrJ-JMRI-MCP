"""Block domain: list JMRI Layout `block` objects (occupancy + linked sensor/value).

One-shot async HTTP against JMRI's /json/blocks (list) endpoint (see
jmri_mcp.jmri_client._http for the shared GET/POST plumbing). Read-only,
like sensor.py: a block's occupancy is detected by JMRI from its linked
sensor, not set directly by this project.

A block is richer than a plain sensor: verified live against JMRI 5.4
(GET /json/blocks) that each entry also carries the name of the occupancy
sensor driving it ("sensor", e.g. "RS24") and a "value" field JMRI can
populate with whatever occupied the block (a roster entry, an RFID tag,
...) when reporting hardware is in use — null on this layout, since it has
no such reporting hardware, but not guaranteed null in general.
"""

import logging
from typing import Any

from jmri_mcp.constants import endpoints
from jmri_mcp.jmri_client._http import JmriError, _get_json, _unwrap

logger = logging.getLogger("jmri_mcp.client")

BLOCK_OCCUPIED = 2
BLOCK_UNOCCUPIED = 4


async def get_blocks() -> list[dict[str, Any]]:
    """Return every block known to JMRI.

    Each entry has at least: name (JMRI system name, e.g. "IB1"), userName
    (may be None if never set in JMRI), state (2=OCCUPIED, 4=UNOCCUPIED;
    JMRI can also report 0=UNKNOWN), sensor (system name of the occupancy
    sensor driving this block, or None if unlinked), and value (whatever
    JMRI's reporting hardware detected occupying the block, e.g. a roster
    entry or RFID tag id — usually None unless that hardware exists).
    """
    payload = await _get_json(endpoints.BLOCKS)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise JmriError("unexpected_payload", endpoint=endpoints.BLOCKS, payload=payload)
    blocks = [_unwrap(entry) for entry in payload]
    logger.info("Discovered %d block(s): %s",
                len(blocks), [b.get("userName") or b.get("name") for b in blocks])
    return blocks


def resolve_block(query: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Match a user-supplied block name against discovered blocks.

    Tolerant like resolve_sensor/resolve_light: case-insensitive, matches
    either the JMRI system name ("IB1") or the user-friendly userName
    exactly first, then an unambiguous substring fragment of userName. No
    default fallback — a block must be named.
    """
    if not blocks:
        raise JmriError("none_available", kind="block")
    if not query or not query.strip():
        raise JmriError("no_query_given", kind="block")

    q = query.strip().casefold()
    labels = [str(b.get("userName") or b.get("name", "")) for b in blocks]

    exact = [
        b for b in blocks
        if str(b.get("name", "")).casefold() == q
        or str(b.get("userName") or "").casefold() == q
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [b for b in blocks if q in str(b.get("userName") or "").casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = [str(b.get("userName") or b.get("name")) for b in partial]
        raise JmriError("ambiguous_entity", kind="block", query=query, matches=matches)

    raise JmriError("unknown_entity", kind="block", query=query, available=labels)
