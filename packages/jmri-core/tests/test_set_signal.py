import pytest
import respx
from httpx import Response
from jmri_core.jmri_client import JmriError, get_signal_aspects, set_signal
from jmri_core.testing.plugin import MOCK_JMRI_URL

_MAST_NAME = "ZF$dsm:DB-HV-1969:block(31)"

_APPEARANCE_XML = """<?xml version="1.0"?>
<appearancetable>
  <aspecttable>
    <aspect>
      <aspectname>Hp0</aspectname>
    </aspect>
    <aspect>
      <aspectname>Hp1</aspectname>
    </aspect>
  </aspecttable>
</appearancetable>
"""


def _mast_payload(name: str, aspect: str = "Hp0", lit: bool = True):
    return [{"type": "signalMast", "data": {"name": name, "aspect": aspect, "lit": lit}}]


# --- get_signal_aspects ---


async def test_get_signal_aspects_parses_xml():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/xml/signals/DB-HV-1969/appearance-block.xml").mock(
            return_value=Response(200, text=_APPEARANCE_XML)
        )
        aspects = await get_signal_aspects(_MAST_NAME)

    assert aspects == ["Hp0", "Hp1"]


async def test_get_signal_aspects_never_includes_unlit_or_off():
    # Regression test for the session-71 design correction: unlit/off are a
    # separate per-mast PanelPro setting, not part of the XML-derived aspect
    # vocabulary, even though the XML fixture here doesn't mention them -
    # this pins the *return*, not just the fixture, against ever leaking
    # them back in.
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/xml/signals/DB-HV-1969/appearance-block.xml").mock(
            return_value=Response(200, text=_APPEARANCE_XML)
        )
        aspects = await get_signal_aspects(_MAST_NAME)

    assert "unlit" not in aspects
    assert "off" not in aspects


async def test_get_signal_aspects_raises_on_non_standard_name():
    with pytest.raises(JmriError) as exc_info:
        await get_signal_aspects("a manually renamed mast")
    assert exc_info.value.code == "aspects_not_derivable"


# --- set_signal: normal aspect path ---


async def test_set_signal_confirms_aspect():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=_mast_payload(_MAST_NAME, aspect="Hp1", lit=True))
        )
        result = await set_signal(_MAST_NAME, "Hp1")

    assert result["confirmed"] is True
    assert result["aspect"] == "Hp1"


async def test_set_signal_posts_state_and_relights():
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=_mast_payload(_MAST_NAME, aspect="Hp1", lit=True))
        )
        await set_signal(_MAST_NAME, "Hp1")

    import json

    body = json.loads(post_route.calls.last.request.content)
    assert body == {"name": _MAST_NAME, "state": "Hp1", "lit": "true"}


async def test_set_signal_not_confirmed_reports_honestly():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        # re-read still shows Hp0 even though Hp1 was requested
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=_mast_payload(_MAST_NAME, aspect="Hp0", lit=True))
        )
        result = await set_signal(_MAST_NAME, "Hp1")

    assert result["confirmed"] is False
    assert result["aspect"] == "Hp0"


async def test_set_signal_raises_if_mast_vanishes():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(return_value=Response(200, json=[]))
        with pytest.raises(JmriError, match="vanished after POST"):
            await set_signal(_MAST_NAME, "Hp1")


# --- set_signal: unlit/off special-case path ---


@pytest.mark.parametrize("requested", ["unlit", "off", "UNLIT", "Off", "  unlit  "])
async def test_set_signal_unlit_variants_post_lit_false(requested):
    with respx.mock() as router:
        post_route = router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=_mast_payload(_MAST_NAME, aspect="Hp0", lit=False))
        )
        result = await set_signal(_MAST_NAME, requested)

    import json

    body = json.loads(post_route.calls.last.request.content)
    assert body == {"name": _MAST_NAME, "lit": "false"}
    assert "state" not in body
    assert result["confirmed"] is True


async def test_set_signal_unlit_not_confirmed_if_still_lit():
    with respx.mock() as router:
        router.post(f"{MOCK_JMRI_URL}/json/signalMast/{_MAST_NAME}").mock(
            return_value=Response(200, json={})
        )
        # mast ignored the lit request and is still lit
        router.get(f"{MOCK_JMRI_URL}/json/signalMasts").mock(
            return_value=Response(200, json=_mast_payload(_MAST_NAME, aspect="Hp0", lit=True))
        )
        result = await set_signal(_MAST_NAME, "off")

    assert result["confirmed"] is False
