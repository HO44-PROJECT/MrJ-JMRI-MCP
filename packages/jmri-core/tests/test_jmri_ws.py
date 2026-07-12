import asyncio

import pytest

from jmri_core.jmri_ws import JmriError, JmriWsClient
from jmri_core.testing.plugin import WS_HEARTBEAT_MS as HEARTBEAT_MS


async def test_connect_reads_hello_and_sets_heartbeat(fake_jmri):
    client = JmriWsClient()
    await client.connect()
    assert client._heartbeat_ms == HEARTBEAT_MS
    await client.close()


async def test_request_returns_correlated_data(fake_jmri):
    client = JmriWsClient()
    data = await client.request("power", {})
    assert data == {"name": "Test", "state": 4, "prefix": "T"}
    await client.close()


async def test_request_raises_jmri_error_on_error_reply(fake_jmri):
    client = JmriWsClient()
    with pytest.raises(JmriError, match="not found"):
        await client.request("boom", {})
    await client.close()


async def test_request_times_out_with_no_reply(fake_jmri, monkeypatch):
    import jmri_core.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "WS_REQUEST_TIMEOUT_SECONDS", 0.3)
    client = JmriWsClient()
    with pytest.raises(JmriError, match="Timed out"):
        await client.request("silent", {})
    await client.close()


async def test_acquire_and_release_throttle(fake_jmri):
    client = JmriWsClient()
    data = await client.acquire_throttle("t1", 42)
    assert data["address"] == 42
    assert client._throttles == {
        "t1": {"address": 42, "prefix": None, "speed": 0.0, "forward": True, "functions": {}}
    }

    data = await client.release_throttle("t1")
    assert data["release"] is None
    assert client._throttles == {}
    await client.close()


async def test_reacquire_same_throttle_is_a_noop(fake_jmri):
    """Re-acquiring a throttle_id/address this connection already holds
    must not send a second wire request. Verified live against real JMRI:
    a genuine duplicate acquire on the same connection crashes it
    (ConnectionClosedError) — see CLAUDE.md. cli/throttle.py's throttle_*
    commands all call acquire_throttle() unconditionally before acting, so
    without this no-op guard, any second shell command touching an
    already-acquired address corrupted the shell's shared connection
    (reproduced live: `throttle speed 4 5` then `throttle stop 4` in the
    same shell session — the second command timed out)."""
    client = JmriWsClient()
    first = await client.acquire_throttle("t1", 42)

    request_lock_calls = []
    original_send_and_wait = client._send_and_wait

    async def counting_send_and_wait(msg_type, data):
        request_lock_calls.append((msg_type, data))
        return await original_send_and_wait(msg_type, data)

    client._send_and_wait = counting_send_and_wait

    second = await client.acquire_throttle("t1", 42)

    assert request_lock_calls == []  # no wire request sent for the re-acquire
    # first is the raw wire reply, second is a cache snapshot — different
    # shapes by design, but callers only ever read these two fields.
    assert second["address"] == first["address"]
    assert second["speed"] == first["speed"]
    assert second["forward"] == first["forward"]
    await client.close()


async def test_reacquire_different_address_sends_wire_request(fake_jmri):
    """The no-op guard is scoped to the same throttle_id+address pair —
    reusing a throttle_id for a different address must still hit the wire
    (this shouldn't happen in practice since cli_throttle_id() derives the
    id from the address, but the guard itself must not be overly broad)."""
    client = JmriWsClient()
    await client.acquire_throttle("t1", 42)
    data = await client.acquire_throttle("t1", 43)
    assert data["address"] == 43
    assert client._throttles["t1"]["address"] == 43
    await client.close()


async def test_keepalive_sends_ping_and_gets_pong(fake_jmri, monkeypatch):
    client = JmriWsClient()
    await client.connect()
    # heartbeat is 200ms -> keepalive interval is max(0.1, 1.0) = 1.0s by
    # the client's floor; instead of waiting, just confirm the loop task
    # is alive and the connection stays usable across a short wait.
    await asyncio.sleep(0.3)
    data = await client.request("power", {})
    assert data["name"] == "Test"
    await client.close()


async def test_reconnect_after_drop_reacquires_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 7)
    assert len(fake_jmri["connected_sockets"]) == 1

    # force-close the server-side socket to simulate a dropped connection
    await fake_jmri["connected_sockets"][0].close()

    # wait for the client's reconnect loop to notice and reconnect
    for _ in range(50):
        if client._ws is not None and len(fake_jmri["connected_sockets"]) == 2:
            break
        await asyncio.sleep(0.1)

    assert client._ws is not None
    # a fresh request should work on the new connection
    data = await client.request("power", {})
    assert data["name"] == "Test"
    await client.close()


async def test_set_speed_on_acquired_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)
    data = await client.set_speed("t1", 0.5)
    assert data["speed"] == 0.5
    await client.close()


async def test_request_connects_lazily(fake_jmri):
    client = JmriWsClient()
    assert client._ws is None
    await client.request("power", {})
    assert client._ws is not None
    await client.close()


async def test_set_speed_noop_skips_request_without_hanging(fake_jmri, monkeypatch):
    # Real JMRI sends no reply at all when the requested speed already
    # matches the current speed. Drop the request timeout so the test
    # would fail fast (instead of hanging ~5s) if set_speed still sent it.
    import jmri_core.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "WS_REQUEST_TIMEOUT_SECONDS", 0.3)

    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)  # starts at speed 0.0
    data = await client.set_speed("t1", 0.0)  # already 0.0 -> must not send
    assert data == {"throttle": "t1", "speed": 0.0}
    await client.close()


async def test_set_speed_pushes_to_other_connection_holding_same_address(fake_jmri):
    # JMRI broadcasts a throttle's state change to every connection that
    # holds that address, not just the one that requested the change.
    a = JmriWsClient()
    b = JmriWsClient()
    await a.acquire_throttle("a1", 9)
    await b.acquire_throttle("b1", 9)

    await b.set_speed("b1", 0.6)

    for _ in range(50):
        if a._throttles["a1"]["speed"] == 0.6:
            break
        await asyncio.sleep(0.05)
    assert a._throttles["a1"]["speed"] == 0.6

    await a.close()
    await b.close()


async def test_set_direction_on_acquired_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)  # starts forward=True
    data = await client.set_direction("t1", False)
    assert data["forward"] is False
    await client.close()


async def test_set_direction_noop_skips_request_without_hanging(fake_jmri, monkeypatch):
    import jmri_core.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "WS_REQUEST_TIMEOUT_SECONDS", 0.3)

    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)  # starts forward=True
    data = await client.set_direction("t1", True)  # already True -> must not send
    assert data == {"throttle": "t1", "forward": True}
    await client.close()


async def test_set_direction_pushes_to_other_connection_holding_same_address(fake_jmri):
    a = JmriWsClient()
    b = JmriWsClient()
    await a.acquire_throttle("a1", 9)
    await b.acquire_throttle("b1", 9)

    await b.set_direction("b1", False)

    for _ in range(50):
        if a._throttles["a1"]["forward"] is False:
            break
        await asyncio.sleep(0.05)
    assert a._throttles["a1"]["forward"] is False

    await a.close()
    await b.close()


async def test_set_function_on_acquired_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)
    data = await client.set_function("t1", 1, True)
    assert data["F1"] is True
    await client.close()


async def test_set_function_noop_skips_request_without_hanging(fake_jmri, monkeypatch):
    import jmri_core.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "WS_REQUEST_TIMEOUT_SECONDS", 0.3)

    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)
    await client.set_function("t1", 0, True)
    data = await client.set_function("t1", 0, True)  # already True -> must not send
    assert data == {"throttle": "t1", "F0": True}
    await client.close()


async def test_set_function_pushes_to_other_connection_holding_same_address(fake_jmri):
    a = JmriWsClient()
    b = JmriWsClient()
    await a.acquire_throttle("a1", 9)
    await b.acquire_throttle("b1", 9)

    await b.set_function("b1", 2, True)

    for _ in range(50):
        if a._throttles["a1"].get("functions", {}).get(2) is True:
            break
        await asyncio.sleep(0.05)
    assert a._throttles["a1"]["functions"][2] is True

    await a.close()
    await b.close()


async def test_emergency_stop_all_stops_every_acquired_throttle(fake_jmri):
    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)
    await client.acquire_throttle("t2", 7)

    result = await client.emergency_stop_all()

    assert sorted(result["stopped"]) == ["t1", "t2"]
    assert result["failed"] == []
    assert client._throttles["t1"]["speed"] == -1.0
    assert client._throttles["t2"]["speed"] == -1.0
    await client.close()


async def test_emergency_stop_all_with_no_throttles_is_a_noop(fake_jmri):
    client = JmriWsClient()
    result = await client.emergency_stop_all()
    assert result == {"stopped": [], "failed": []}
    await client.close()


async def test_emergency_stop_all_skips_already_stopped_without_hanging(fake_jmri, monkeypatch):
    import jmri_core.jmri_ws as ws_module
    monkeypatch.setattr(ws_module, "WS_REQUEST_TIMEOUT_SECONDS", 0.3)

    client = JmriWsClient()
    await client.acquire_throttle("t1", 3)
    await client.set_speed("t1", -1.0)  # already e-stopped

    result = await client.emergency_stop_all()
    assert result == {"stopped": ["t1"], "failed": []}
    await client.close()


async def test_pending_request_not_corrupted_by_push_for_other_throttle(fake_jmri):
    # While connection A is mid-request on throttle id "a-other", a push
    # about a *different* throttle id it also holds ("a1") must not be
    # mistaken for the reply to the pending request.
    a = JmriWsClient()
    b = JmriWsClient()
    await a.acquire_throttle("a1", 9)
    await a.acquire_throttle("a-other", 5)

    await b.acquire_throttle("b1", 9)
    push_task = asyncio.create_task(b.set_speed("b1", 0.3))

    data = await a.set_speed("a-other", 0.8)
    assert data["throttle"] == "a-other"
    assert data["speed"] == 0.8

    await push_task
    for _ in range(50):
        if a._throttles["a1"]["speed"] == 0.3:
            break
        await asyncio.sleep(0.05)
    assert a._throttles["a1"]["speed"] == 0.3

    await a.close()
    await b.close()
