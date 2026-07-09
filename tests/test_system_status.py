import respx
from httpx import Response

from jmri_mcp.jmri_client import JmriError, get_version
from tests.conftest import MOCK_JMRI_URL


async def test_get_version_parses_key_as_version(version_fixture):
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/version").mock(
            return_value=Response(200, json=version_fixture)
        )
        version = await get_version()

    assert version == "5.4.0"


async def test_get_version_raises_on_unreachable():
    with respx.mock() as router:
        router.get(f"{MOCK_JMRI_URL}/json/version").mock(
            return_value=Response(500)
        )
        try:
            await get_version()
            assert False, "expected JmriError"
        except JmriError:
            pass
