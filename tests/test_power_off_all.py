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


async def test_power_off_all_confirms_every_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)

    def get_side_effect(request):
        # First GET is the initial discovery (all ON); every GET after a
        # POST is a re-read, by which point that system should read OFF.
        get_side_effect.calls += 1
        if get_side_effect.calls == 1:
            return Response(200, json=_systems_payload({"O": POWER_ON, "Z": POWER_ON, "R": POWER_ON}))
        return Response(200, json=_systems_payload({"O": POWER_OFF, "Z": POWER_OFF, "R": POWER_OFF}))

    get_side_effect.calls = 0

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))

        results = await power_off_all()

    assert len(results) == 3
    assert {r["prefix"] for r in results} == {"O", "Z", "R"}
    assert all(r["confirmed"] for r in results)
    assert all(r["state"] == POWER_OFF for r in results)


async def test_power_off_all_reports_unconfirmed_system_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    call_count = {"n": 0}

    def get_side_effect(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # initial discovery: two systems, both ON
            return Response(200, json=_systems_payload({"O": POWER_ON, "Z": POWER_ON}))
        if call_count["n"] == 2:
            # re-read after posting OFF to O: confirms
            return Response(200, json=_systems_payload({"O": POWER_OFF, "Z": POWER_ON}))
        # re-read after posting OFF to Z: still ON (stuck)
        return Response(200, json=_systems_payload({"O": POWER_OFF, "Z": POWER_ON}))

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))

        results = await power_off_all()

    by_prefix = {r["prefix"]: r for r in results}
    assert by_prefix["O"]["confirmed"] is True
    assert by_prefix["Z"]["confirmed"] is False


async def test_power_off_all_with_single_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)

    def get_side_effect(request):
        get_side_effect.calls += 1
        state = POWER_ON if get_side_effect.calls == 1 else POWER_OFF
        return Response(200, json=_systems_payload({"R": state}))

    get_side_effect.calls = 0

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))

        results = await power_off_all()

    assert len(results) == 1
    assert results[0]["prefix"] == "R"
    assert results[0]["confirmed"] is True


async def test_power_on_all_confirms_every_system(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)

    def get_side_effect(request):
        get_side_effect.calls += 1
        if get_side_effect.calls == 1:
            return Response(200, json=_systems_payload({"O": POWER_OFF, "Z": POWER_OFF, "R": POWER_OFF}))
        return Response(200, json=_systems_payload({"O": POWER_ON, "Z": POWER_ON, "R": POWER_ON}))

    get_side_effect.calls = 0

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))

        results = await power_on_all()

    assert len(results) == 3
    assert {r["prefix"] for r in results} == {"O", "Z", "R"}
    assert all(r["confirmed"] for r in results)
    assert all(r["state"] == POWER_ON for r in results)


async def test_power_on_all_reports_unconfirmed_system_honestly(monkeypatch):
    monkeypatch.setattr("jmri_mcp.jmri_client.power._POST_RECHECK_DELAY", 0)
    call_count = {"n": 0}

    def get_side_effect(request):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # initial discovery: two systems, both OFF
            return Response(200, json=_systems_payload({"O": POWER_OFF, "Z": POWER_OFF}))
        if call_count["n"] == 2:
            # re-read after posting ON to O: confirms
            return Response(200, json=_systems_payload({"O": POWER_ON, "Z": POWER_OFF}))
        # re-read after posting ON to Z: still OFF (stuck)
        return Response(200, json=_systems_payload({"O": POWER_ON, "Z": POWER_OFF}))

    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/power").mock(side_effect=get_side_effect)
        router.post(f"{MOCK_JMRI_URL}/json/power").mock(return_value=Response(200, json={}))

        results = await power_on_all()

    by_prefix = {r["prefix"]: r for r in results}
    assert by_prefix["O"]["confirmed"] is True
    assert by_prefix["Z"]["confirmed"] is False
