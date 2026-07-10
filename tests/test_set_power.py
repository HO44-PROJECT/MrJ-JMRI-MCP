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
        # pre-check sees OFF (so the POST is actually sent), post-POST re-read sees ON
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("O", POWER_OFF)),
                Response(200, json=_power_payload("O", POWER_ON)),
            ]
        )
        result = await set_power("O", turn_on=True)

    assert result["confirmed"] is True
    assert result["state"] == POWER_ON


async def test_set_power_not_confirmed_reports_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))
        # pre-check sees OFF, re-read after POST still shows OFF (e.g. unreachable system)
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
        # pre-check sees OFF (so the POST is actually sent), post-POST re-read sees ON
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_OFF)),
                Response(200, json=_power_payload("R", POWER_ON)),
            ]
        )
        await set_power("R", turn_on=True)

    assert post_route.calls.last.request.content == b'{"state":2,"prefix":"R"}'


async def test_set_power_skips_post_when_already_desired_state(monkeypatch):
    """The JMRI bug this guards against: re-POSTing the same state can knock
    the system into UNKNOWN. Confirming ON on an already-ON system must
    never send a POST at all."""
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    with respx.mock(assert_all_called=False) as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json=_power_payload("O", POWER_ON))
        )
        result = await set_power("O", turn_on=True)

    assert post_route.call_count == 0
    assert result["confirmed"] is True
    assert result["state"] == POWER_ON
