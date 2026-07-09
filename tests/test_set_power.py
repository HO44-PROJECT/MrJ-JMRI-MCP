import respx
from httpx import Response

from jmri_mcp.jmri_client import POWER_OFF, POWER_ON, set_power
from tests.conftest import MOCK_JMRI_URL


def _power_payload(prefix: str, state: int, name: str = "DCC++ Ohara", default=False):
    return [{"type": "power", "data": {"name": name, "prefix": prefix, "state": state, "default": default}}]


async def test_set_power_confirms_on(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=_power_payload("O", 0))  # transient, per CLAUDE.md
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=_power_payload("O", POWER_ON))
        )
        result = await set_power("O", turn_on=True)

    assert result["confirmed"] is True
    assert result["state"] == POWER_ON


async def test_set_power_not_confirmed_reports_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))
        # re-read still shows OFF even though we asked for ON (e.g. unreachable system)
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=_power_payload("Z", POWER_OFF))
        )
        result = await set_power("Z", turn_on=True)

    assert result["confirmed"] is False
    assert result["state"] == POWER_OFF


async def test_set_power_posts_documented_body_shape(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=_power_payload("R", POWER_ON))
        )
        await set_power("R", turn_on=True)

    assert post_route.calls.last.request.content == b'{"state":2,"prefix":"R"}'
