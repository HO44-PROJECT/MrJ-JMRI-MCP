# Release procedure

How to build and publish `jmri-core`, `jmri-cli`, and `jmri-mcp` to PyPI.
Driven by the root [`Makefile`](../Makefile).

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — builds each package with `uv build`.
- A PyPI API token (scoped to the three project names, or your account) for
  `deploy`, and/or a [TestPyPI](https://test.pypi.org/) token for
  `testdeploy`. Twine itself doesn't need a local install — the Makefile runs
  it via `uv tool run twine`, isolated from any system Python.

## Bump the version

Each package's version is declared in two places that must match:

- `packages/<pkg>/pyproject.toml` — `version = "X.Y.Z"`
- `packages/<pkg>/src/<module>/__init__.py` — `__version__ = "X.Y.Z"`

`jmri-cli` and `jmri-mcp` also pin their `jmri-core` dependency by exact
version (`jmri-core==X.Y.Z`) — bump that pin too when `jmri-core`'s version
changes, even if `jmri-cli`/`jmri-mcp`'s own version doesn't.

## Build

```bash
make build
```

Runs `uv build` for all three packages into `dist/`, then `twine check
dist/*` to validate metadata. Fails fast if any package fails to build or
check.

## Test

```bash
make test
```

Runs the full mocked test suite (`uv run --all-packages pytest`) — see
[testing.md](testing.md) for what this covers and how to additionally run the
opt-in live suite. `make build` does not run tests; run `make test`
separately before publishing.

## Publish to TestPyPI (dry run)

Recommended before the first real publish of a new version, to catch
packaging issues without consuming the real PyPI listing:

```bash
TWINE_PASSWORD=<testpypi-token> make testdeploy
```

Then verify the install works from TestPyPI in a scratch environment:

```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ jmri-mcp
```

(`--extra-index-url` is needed because TestPyPI doesn't mirror `jmri-mcp`'s
own dependencies like `mcp`.)

## Publish to PyPI

```bash
TWINE_PASSWORD=<pypi-token> make deploy
```

Uploads all three packages from `dist/`. **PyPI does not allow re-uploading
or overwriting a version once published** — double-check the version bump
and `make testdeploy` dry run before running this.

## After publishing

- Tag the release in git: `git tag vX.Y.Z && git push origin vX.Y.Z`.
- Update `docs/install.md` if the recommended install method changed.
