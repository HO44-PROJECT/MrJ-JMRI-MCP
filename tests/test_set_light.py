import pytest
import respx
from httpx import Response

from jmri_mcp.jmri_client import LIGHT_OFF, LIGHT_ON, JmriError, set_light
from tests.conftest import MOCK_JMRI_URL


def _light_payload(name: str, state: int, user_name: str = "Depot Lighting"):
    return [{"type": "light", "data": {"name": name, "userName": user_name, "state": state}}]


async def test_set_light_confirms_on():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(
            return_value=Response(200, json=_light_payload("IL1", LIGHT_ON))
        )
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=_light_payload("IL1", LIGHT_ON))
        )
        result = await set_light("IL1", turn_on=True)

    assert result["confirmed"] is True
    assert result["state"] == LIGHT_ON


async def test_set_light_not_confirmed_reports_honestly():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(return_value=Response(200, json={}))
        # re-read still shows OFF even though we asked for ON
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=_light_payload("IL1", LIGHT_OFF))
        )
        result = await set_light("IL1", turn_on=True)

    assert result["confirmed"] is False
    assert result["state"] == LIGHT_OFF


async def test_set_light_posts_documented_body_shape():
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(
            return_value=Response(200, json=_light_payload("IL1", LIGHT_ON))
        )
        await set_light("IL1", turn_on=True)

    assert post_route.calls.last.request.content == b'{"name":"IL1","state":2}'


async def test_set_light_raises_if_light_vanishes():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/light/IL1").mock(return_value=Response(200, json={}))
        router.get(f"{MOCK_JMRI_URL}/json/lights").mock(return_value=Response(200, json=[]))
        with pytest.raises(JmriError, match="vanished after POST"):
            await set_light("IL1", turn_on=True)
