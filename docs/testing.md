# Testing

Two tiers: a mocked suite that runs by default and never touches the network,
and an opt-in suite that talks to a real JMRI server.

## Mocked suite (default)

```bash
pip install -e ".[dev]"
pytest
```

Every test is pointed at a fake host (`tests/conftest.py`'s autouse `jmri_url`
fixture). No real network calls, no hardware side effects. This is what runs
in CI and what you should run after any code change.

- HTTP calls (`jmri_client/`) are mocked with [`respx`](https://lundberg.github.io/respx/)
  using fixtures captured from a real JMRI 5.4.0 server (`tests/fixtures/*.json`).
- The WebSocket client (`jmri_ws/`, see `tests/test_jmri_ws.py`) is tested
  against a real local `websockets` server fixture (`fake_jmri`) that speaks
  the subset of JMRI's protocol needed to exercise connect/hello, ping/pong,
  request-response, throttle acquire/release, and reconnect — `respx` only
  mocks HTTP, so this can't reuse the same approach as `jmri_client/`.

## Live suite (opt-in)

`tests/test_live.py` talks to a real, reachable JMRI server. It's excluded by
default (`addopts = "-m 'not live'"` in `pyproject.toml`) — run it explicitly:

```bash
pytest -m live
```

### Configuring it

Copy `config/live.example.ini` to `config/live.ini` (gitignored — it names
your private network address) and fill in the `[jmri]` section:

```ini
[jmri]
url = http://10.0.20.20:12080
write_test_system = Zou
enable_write_tests = true
min_toggle_interval_seconds = 5
```

Every key can also be overridden with an environment variable
(`JMRI_URL_LIVE`, `JMRI_WRITE_TEST_SYSTEM`, `JMRI_ENABLE_WRITE_TESTS`,
`JMRI_MIN_TOGGLE_INTERVAL_SECONDS`), which takes priority over the ini file.

If `url` isn't set (no config file, no env var), the whole live suite is
skipped with an explanatory message — it's never silently run against nothing.

### Hardware safety

`DCC++` command stations drive real relays on real electronics. Rapid on/off
cycling is hard on them (relay wear, inrush current), so the live suite treats
writes with extra care:

- **Read-only live tests** (discovering systems, resolving the default) always
  run once a `url` is configured — no further opt-in needed, since they never
  change state.
- **Write tests** (`power set` round-trips) are skipped unless
  `enable_write_tests = true` **and** `write_test_system` names a system —
  both must be set deliberately.
- The round-trip test waits at least `min_toggle_interval_seconds` (default 5s)
  between toggling a system and restoring it to its original state, and always
  restores in a `finally` block so a failed assertion still attempts to leave
  the hardware as it found it.

If a restore ever fails, the test message says so explicitly (`FAILED TO
RESTORE ... — check it manually`) — check the system's actual state by hand
(`jmri-cli power status <system>`, see [cli.md](cli.md)) rather than trusting
that a later test run will fix it.
