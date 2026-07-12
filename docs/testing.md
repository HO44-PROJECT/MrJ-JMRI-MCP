# Testing

Two tiers: a mocked suite that runs by default and never touches the network,
and an opt-in suite that talks to a real JMRI server.

## Mocked suite (default)

```bash
uv sync --all-packages --extra test
uv run pytest
```

Every test is pointed at a fake host (an autouse `jmri_url` fixture in
`jmri_core.testing.plugin`, a pytest plugin registered via the `pytest11` entry
point — any package with `jmri-core[test]` installed gets it automatically).
No real network calls, no hardware side effects. This is what runs in CI and
what you should run after any code change.

- HTTP calls (`jmri_client/`) are mocked with [`respx`](https://lundberg.github.io/respx/)
  using fixtures captured from a real JMRI 5.4.0 server
  (`packages/jmri-core/src/jmri_core/testing/fixtures/*.json`).
- The WebSocket client (`jmri_ws/`, see `packages/jmri-core/tests/test_jmri_ws.py`)
  is tested against a real local `websockets` server fixture (`fake_jmri`) that
  speaks the subset of JMRI's protocol needed to exercise connect/hello,
  ping/pong, request-response, throttle acquire/release, and reconnect —
  `respx` only mocks HTTP, so this can't reuse the same approach as `jmri_client/`.

## Live suite (opt-in)

`packages/jmri-core/tests/test_live.py` talks to a real, reachable JMRI
server. It's excluded by default (`addopts = "-m 'not live'"` in the root
`pyproject.toml`) — run it explicitly:

```bash
uv run pytest -m live
```

### Configuring it

The URL alone needs no extra setup: if you already have `JMRI_URL` exported
(the same variable used everywhere else in this project — CLI, MCP server),
the live suite picks it up automatically, in preference order `JMRI_URL_LIVE`
env var → `packages/jmri-core/tests/config/live.ini`'s `url` → plain
`JMRI_URL`. Set `JMRI_URL_LIVE` instead only if you want the live suite to
point somewhere different from your normal `JMRI_URL`.

Write tests need more than a URL — `packages/jmri-core/tests/config/live.ini`
is where the safety knobs live (there's no equivalent env var for these
elsewhere in the project). Copy
`packages/jmri-core/tests/config/live.example.ini` to
`packages/jmri-core/tests/config/live.ini` (gitignored — it names your
private network address) and fill in the `[jmri]` section:

```ini
[jmri]
; url is optional here — omit it to fall back to JMRI_URL, see above.
write_test_system = Zou
enable_write_tests = true
min_toggle_interval_seconds = 5
```

Every key can also be overridden with an environment variable
(`JMRI_URL_LIVE`, `JMRI_WRITE_TEST_SYSTEM`, `JMRI_ENABLE_WRITE_TESTS`,
`JMRI_MIN_TOGGLE_INTERVAL_SECONDS`), which takes priority over the ini file.

If no URL can be found anywhere (no `JMRI_URL`, no `JMRI_URL_LIVE`, no ini
`url`), the whole live suite is skipped with an explanatory message — it's
never silently run against nothing.

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
