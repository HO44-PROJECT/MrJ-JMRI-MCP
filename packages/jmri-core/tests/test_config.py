import pytest

from jmri_core.config import DEFAULT_JMRI_URL, get_exhibition_start_on, get_jmri_url


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv("JMRI_URL", raising=False)
    assert get_jmri_url() == DEFAULT_JMRI_URL


def test_reads_env(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://192.0.2.1:12080")
    assert get_jmri_url() == "http://192.0.2.1:12080"


def test_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("JMRI_URL", "http://192.0.2.1:12080/")
    assert get_jmri_url() == "http://192.0.2.1:12080"


@pytest.mark.parametrize("bad", ["banana", "ftp://192.0.2.1", "", "   ", "http://"])
def test_rejects_invalid_url(monkeypatch, bad):
    monkeypatch.setenv("JMRI_URL", bad)
    with pytest.raises(ValueError, match="Invalid JMRI_URL"):
        get_jmri_url()


def test_exhibition_start_on_default_false(monkeypatch):
    monkeypatch.delenv("EXHIBITION_START_ON", raising=False)
    assert get_exhibition_start_on() is False


@pytest.mark.parametrize("value", ["1", "true", "True", "YES", "on", " on "])
def test_exhibition_start_on_truthy_values(monkeypatch, value):
    monkeypatch.setenv("EXHIBITION_START_ON", value)
    assert get_exhibition_start_on() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "banana"])
def test_exhibition_start_on_falsy_values(monkeypatch, value):
    monkeypatch.setenv("EXHIBITION_START_ON", value)
    assert get_exhibition_start_on() is False
