import json

import respx
from httpx import Response

from jmri_mcp.jmri_client import POWER_OFF, POWER_ON, power_off_all, power_on_all
from tests.conftest import MOCK_JMRI_URL


def _systems_payload(states: dict[str, int]) -> list[dict]:
    prefixes = {"O": "DCC++ Ohara", "Z": "DCC++ Zou", "R": "DCC++ Raijin"}
    return [
        {"type": "power", "data": {"name": prefixes[p], "prefix": p, "state": s, "default": p == "R"}}
        for p, s in states.items()
    ]


def _make_router(initial_states: dict[str, int]):
    """A stateful fake JMRI: GET reflects live_state, POST mutates it.

    set_power() now re-reads current state *before* POSTing (to skip a
    redundant same-state POST, which is a real JMRI bug that knocks a
    system into UNKNOWN) as well as after — so GET is called twice per
    system that actually changes state, not once. A stateful fake models
    this correctly regardless of exact call counts.
    """
    live_state = dict(initial_states)

    def get_side_effect(request):
        return Response(200, json=_systems_payload(live_state))

    def post_side_effect(request):
        body = json.loads(request.content)
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    return get_side_effect, post_side_effect


async def test_power_off_all_confirms_every_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    get_side_effect, post_side_effect = _make_router({"O": POWER_ON, "Z": POWER_ON, "R": POWER_ON})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_off_all()

    assert len(results) == 3
    assert {r["prefix"] for r in results} == {"O", "Z", "R"}
    assert all(r["confirmed"] for r in results)
    assert all(r["state"] == POWER_OFF for r in results)


async def test_power_off_all_reports_unconfirmed_system_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    live_state = {"O": POWER_ON, "Z": POWER_ON}

    def get_side_effect(request):
        return Response(200, json=_systems_payload(live_state))

    def post_side_effect(request):
        body = json.loads(request.content)
        # Z is stuck: its POST is accepted but never actually changes state.
        if body["prefix"] == "O":
            live_state["O"] = body["state"]
        return Response(200, json={})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_off_all()

    by_prefix = {r["prefix"]: r for r in results}
    assert by_prefix["O"]["confirmed"] is True
    assert by_prefix["Z"]["confirmed"] is False


async def test_power_off_all_with_single_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    get_side_effect, post_side_effect = _make_router({"R": POWER_ON})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_off_all()

    assert len(results) == 1
    assert results[0]["prefix"] == "R"
    assert results[0]["confirmed"] is True


async def test_power_on_all_confirms_every_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    get_side_effect, post_side_effect = _make_router({"O": POWER_OFF, "Z": POWER_OFF, "R": POWER_OFF})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_on_all()

    assert len(results) == 3
    assert {r["prefix"] for r in results} == {"O", "Z", "R"}
    assert all(r["confirmed"] for r in results)
    assert all(r["state"] == POWER_ON for r in results)


async def test_power_on_all_reports_unconfirmed_system_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    live_state = {"O": POWER_OFF, "Z": POWER_OFF}

    def get_side_effect(request):
        return Response(200, json=_systems_payload(live_state))

    def post_side_effect(request):
        body = json.loads(request.content)
        # Z is stuck: its POST is accepted but never actually changes state.
        if body["prefix"] == "O":
            live_state["O"] = body["state"]
        return Response(200, json={})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_on_all()

    by_prefix = {r["prefix"]: r for r in results}
    assert by_prefix["O"]["confirmed"] is True
    assert by_prefix["Z"]["confirmed"] is False


async def test_power_off_all_skips_post_for_already_off_system(monkeypatch):
    """The JMRI bug this guards against: re-POSTing the same state can knock
    the system into UNKNOWN. power_off_all must never POST to a system
    that's already OFF."""
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    live_state = {"O": POWER_OFF, "Z": POWER_ON}
    post_calls = []

    def get_side_effect(request):
        return Response(200, json=_systems_payload(live_state))

    def post_side_effect(request):
        body = json.loads(request.content)
        post_calls.append(body["prefix"])
        live_state[body["prefix"]] = body["state"]
        return Response(200, json={})

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=post_side_effect)

        results = await power_off_all()

    assert post_calls == ["Z"]
    by_prefix = {r["prefix"]: r for r in results}
    assert by_prefix["O"]["confirmed"] is True
    assert by_prefix["Z"]["confirmed"] is True
