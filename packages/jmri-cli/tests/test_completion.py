import json

from jmri_cli import completion


def _use_tmp_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(completion, "CACHE_DIR", tmp_path / "completion_cache")


def test_names_for_system_fetches_live_and_caches(monkeypatch, tmp_path, mock_power):
    _use_tmp_cache_dir(monkeypatch, tmp_path)

    names = completion._names_for("system")

    assert set(names) == {"DCC++ Ohara", "DCC++ Zou", "DCC++ Raijin"}
    cached = json.loads(completion._cache_path("system").read_text())
    assert set(cached["names"]) == set(names)


def test_names_for_light_prefers_username_over_system_name(monkeypatch, tmp_path, mock_lights):
    _use_tmp_cache_dir(monkeypatch, tmp_path)

    names = completion._names_for("light")

    # lights_response.json fixture: IL1/"Depot Lighting", IL2/"Street
    # Lamps", IL3/userName=null -> falls back to "IL3".
    assert set(names) == {"Depot Lighting", "Street Lamps", "IL3"}


def test_names_for_roster_fetches_live_and_caches(monkeypatch, tmp_path, mock_roster):
    _use_tmp_cache_dir(monkeypatch, tmp_path)

    names = completion._names_for("roster")

    assert len(names) > 0
    cached = json.loads(completion._cache_path("roster").read_text())
    assert cached["names"] == names


def test_names_for_reuses_fresh_cache_without_refetching(monkeypatch, tmp_path, mock_power):
    _use_tmp_cache_dir(monkeypatch, tmp_path)

    first = completion._names_for("system")

    # A second call within the TTL must not hit JMRI again -- break the
    # mock so any real fetch attempt would raise, proving the cache path
    # was taken instead.
    monkeypatch.setattr(completion, "_FETCHERS", {"system": _boom})
    second = completion._names_for("system")

    assert second == first


async def _boom():
    raise AssertionError("should not have refetched from JMRI")


def test_names_for_falls_back_to_stale_cache_on_fetch_failure(monkeypatch, tmp_path):
    _use_tmp_cache_dir(monkeypatch, tmp_path)
    completion.CACHE_DIR.mkdir(parents=True)
    completion._write_cache("system", ["Stale System"])
    # Force the cache to be considered expired.
    monkeypatch.setattr(completion, "COMPLETION_CACHE_TTL_SECONDS", 0)

    async def raise_error():
        raise RuntimeError("JMRI unreachable")

    monkeypatch.setattr(completion, "_FETCHERS", {"system": raise_error})

    names = completion._names_for("system")

    assert names == ["Stale System"]


def test_names_for_returns_empty_list_with_no_cache_and_fetch_failure(monkeypatch, tmp_path):
    _use_tmp_cache_dir(monkeypatch, tmp_path)

    async def raise_error():
        raise RuntimeError("JMRI unreachable")

    monkeypatch.setattr(completion, "_FETCHERS", {"system": raise_error})

    names = completion._names_for("system")

    assert names == []


def test_names_for_reads_freshly_written_cache_directly(monkeypatch, tmp_path):
    _use_tmp_cache_dir(monkeypatch, tmp_path)
    completion.CACHE_DIR.mkdir(parents=True)
    completion._write_cache("system", ["DCC++ Ohara"])

    assert completion._names_for("system") == ["DCC++ Ohara"]
