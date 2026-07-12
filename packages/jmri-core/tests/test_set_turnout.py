import pytest
import respx
from httpx import Response

from jmri_core.jmri_client import TURNOUT_CLOSED, TURNOUT_THROWN, JmriError, set_turnout
from jmri_core.testing.plugin import MOCK_JMRI_URL


def _turnout_payload(name: str, state: int, user_name: str = "Layout Turnout A"):
    return [{"type": "turnout", "data": {"name": name, "userName": user_name, "state": state}}]


async def test_set_turnout_confirms_thrown():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(
            return_value=Response(200, json=_turnout_payload("IT100", TURNOUT_THROWN))
        )
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=_turnout_payload("IT100", TURNOUT_THROWN))
        )
        result = await set_turnout("IT100", thrown=True)

    assert result["confirmed"] is True
    assert result["state"] == TURNOUT_THROWN


async def test_set_turnout_not_confirmed_reports_honestly():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(return_value=Response(200, json={}))
        # re-read still shows CLOSED even though we asked for THROWN
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=_turnout_payload("IT100", TURNOUT_CLOSED))
        )
        result = await set_turnout("IT100", thrown=True)

    assert result["confirmed"] is False
    assert result["state"] == TURNOUT_CLOSED


async def test_set_turnout_posts_documented_body_shape():
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(
            return_value=Response(200, json=_turnout_payload("IT100", TURNOUT_THROWN))
        )
        await set_turnout("IT100", thrown=True)

    assert post_route.calls.last.request.content == b'{"name":"IT100","state":4}'


async def test_set_turnout_raises_if_turnout_vanishes():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/turnout/IT100").mock(return_value=Response(200, json={}))
        router.get(f"{MOCK_JMRI_URL}/json/turnouts").mock(return_value=Response(200, json=[]))
        with pytest.raises(JmriError, match="vanished after POST"):
            await set_turnout("IT100", thrown=True)
