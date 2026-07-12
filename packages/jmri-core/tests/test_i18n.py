from jmri_core.i18n import lookup


def test_lookup_joins_available_list_under_cap():
    message = lookup("en", "errors.unknown_entity", kind="turnout", query="tgv", available=["A", "B", "C"])
    assert message == "Unknown turnout 'tgv'. Available: A, B, C"


def test_lookup_truncates_available_list_over_cap():
    available = [f"T{i}" for i in range(20)]
    message = lookup("en", "errors.unknown_entity", kind="turnout", query="tgv", available=available)
    shown = ", ".join(f"T{i}" for i in range(15))
    assert message == f"Unknown turnout 'tgv'. Available: {shown}, ... (+5 more)"


def test_lookup_truncates_matches_list_over_cap():
    matches = [f"T{i}" for i in range(18)]
    message = lookup("en", "errors.ambiguous_entity", kind="turnout", query="layout", matches=matches)
    shown = ", ".join(f"T{i}" for i in range(15))
    assert message == f"Ambiguous turnout 'layout': matches {shown}, ... (+3 more)"


def test_lookup_exactly_at_cap_is_not_truncated():
    available = [f"T{i}" for i in range(15)]
    message = lookup("en", "errors.unknown_entity", kind="turnout", query="tgv", available=available)
    assert "more" not in message
    assert message == f"Unknown turnout 'tgv'. Available: {', '.join(available)}"


def test_resolver_exception_kwargs_keep_full_uncapped_list():
    # Capping happens only at render time in lookup() - the raised
    # exception's own .kwargs must keep the full list so callers that
    # inspect it programmatically (not just print it) see everything.
    from jmri_core.jmri_client import JmriError, resolve_turnout

    turnouts = [{"name": f"IT{i}", "userName": f"Turnout {i}"} for i in range(20)]
    try:
        resolve_turnout("tgv", turnouts)
    except JmriError as exc:
        assert len(exc.kwargs["available"]) == 20
    else:
        raise AssertionError("expected JmriError")
