import respx
from httpx import Response
from jmri_core.jmri_client import POWER_OFF, POWER_ON, POWER_UNKNOWN, set_power
from jmri_core.testing.plugin import MOCK_JMRI_URL


def _power_payload(prefix: str, state: int, name: str = "DCC++ Ohara", default=False):
    return [
        {
            "type": "power",
            "data": {"name": name, "prefix": prefix, "state": state, "default": default},
        }
    ]


def _version_payload(version: str):
    return {"type": "version", "data": {version: "v5"}}


def _mock_version(router, version: str):
    router.get(f"{MOCK_JMRI_URL}/json/version").mock(
        return_value=Response(200, json=_version_payload(version))
    )


async def test_set_power_confirms_on(monkeypatch):
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
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


async def test_set_power_recovers_from_unknown_after_on_old_jmri(monkeypatch):
    """On JMRI older than the JMRI/JMRI#15287 fix, a power ON that lands in
    UNKNOWN doesn't self-recover -- set_power must post OFF, wait, then
    retry ON once, and confirm on the final re-read. Result must flag
    outdated_jmri_version so callers can tell the user to upgrade."""
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_UNKNOWN_RECOVERY_DELAY_SECONDS", 0)
    with respx.mock() as router:
        _mock_version(router, "5.4.0")
        post_route = router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_OFF)),  # pre-check
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),  # post-ON re-read: UNKNOWN
                Response(200, json=_power_payload("R", POWER_OFF)),  # post-recovery-OFF re-read
                Response(200, json=_power_payload("R", POWER_ON)),  # post-recovery-ON re-read
            ]
        )
        result = await set_power("R", turn_on=True)

    assert result["confirmed"] is True
    assert result["state"] == POWER_ON
    assert result["outdated_jmri_version"] == "5.4.0"
    assert "recovered_by_jmri_fix" not in result
    posted_states = [call.request.content for call in post_route.calls]
    assert posted_states == [
        b'{"state":2,"prefix":"R"}',
        b'{"state":4,"prefix":"R"}',
        b'{"state":2,"prefix":"R"}',
    ]


async def test_set_power_unknown_recovery_failure_reported_honestly(monkeypatch):
    """If the retried ON still doesn't confirm, report confirmed=False rather
    than retrying indefinitely."""
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_UNKNOWN_RECOVERY_DELAY_SECONDS", 0)
    with respx.mock() as router:
        _mock_version(router, "5.4.0")
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_OFF)),  # pre-check
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),  # post-ON re-read: UNKNOWN
                Response(200, json=_power_payload("R", POWER_OFF)),  # post-recovery-OFF re-read
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),  # retry still UNKNOWN
            ]
        )
        result = await set_power("R", turn_on=True)

    assert result["confirmed"] is False
    assert result["state"] == POWER_UNKNOWN


async def test_set_power_self_recovers_from_unknown_on_fixed_jmri(monkeypatch):
    """On JMRI >= POWER_UNKNOWN_JMRI_FIX_VERSION, a power ON that lands in
    UNKNOWN is NOT force-cycled OFF/ON -- set_power only waits the
    self-recovery delay and re-reads once. No extra POST is sent, and the
    result flags recovered_by_jmri_fix instead of outdated_jmri_version."""
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_UNKNOWN_SELF_RECOVERY_WAIT_SECONDS", 0)
    with respx.mock() as router:
        _mock_version(router, "5.17.1")
        post_route = router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_OFF)),  # pre-check
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),  # post-ON re-read: UNKNOWN
                Response(200, json=_power_payload("R", POWER_ON)),  # self-recovery re-read
            ]
        )
        result = await set_power("R", turn_on=True)

    assert result["confirmed"] is True
    assert result["state"] == POWER_ON
    assert result["recovered_by_jmri_fix"] is True
    assert "outdated_jmri_version" not in result
    assert post_route.call_count == 1  # only the original ON, no forced OFF/ON cycle


async def test_set_power_newer_than_fix_version_also_self_recovers(monkeypatch):
    """A JMRI version newer than the fix version (e.g. 5.18.0, or a future
    5.17.10) must still compare as >= the fix version -- this guards
    against a naive string compare, which would wrongly sort "5.9" after
    "5.17" and "5.17.10" before "5.17.1"."""
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_UNKNOWN_SELF_RECOVERY_WAIT_SECONDS", 0)
    with respx.mock() as router:
        _mock_version(router, "5.17.10")
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_OFF)),
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),
                Response(200, json=_power_payload("R", POWER_ON)),
            ]
        )
        result = await set_power("R", turn_on=True)

    assert result["confirmed"] is True
    assert result["recovered_by_jmri_fix"] is True


async def test_set_power_no_recovery_when_turning_off(monkeypatch):
    """The UNKNOWN recovery cycle is only for turn_on=True -- a turn-off that
    lands in UNKNOWN must not trigger an OFF/wait/ON cycle."""
    monkeypatch.setattr("jmri_core.jmri_client.power.POWER_POST_RECHECK_DELAY_SECONDS", 0)
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/power").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(
            side_effect=[
                Response(200, json=_power_payload("R", POWER_ON)),  # pre-check
                Response(200, json=_power_payload("R", POWER_UNKNOWN)),  # post-OFF re-read: UNKNOWN
            ]
        )
        result = await set_power("R", turn_on=False)

    assert post_route.call_count == 1
    assert result["confirmed"] is False
    assert result["state"] == POWER_UNKNOWN
