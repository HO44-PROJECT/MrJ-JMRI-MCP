# Release procedure

How to build and publish `jmri-core`, `jmri-cli`, and `jmri-mcp` to PyPI, and
the `.mcpb` bundle to GitHub Releases and the MCP Registry. Driven by the
root [`Makefile`](../Makefile).

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) — builds each package with `uv build`.
- [`gh`](https://cli.github.com/) (GitHub CLI), authenticated — used by
  `make release` to push, tag, and create the GitHub Release.
- A `~/.pypirc` with `[pypi]` and `[testpypi]` sections (separate accounts,
  separate tokens — see below), `username = __token__` in each. Twine itself
  doesn't need a local install — the Makefile runs it via `uv tool run
  twine`, isolated from any system Python.
- [`mcp-publisher`](https://github.com/modelcontextprotocol/registry) (`brew
  install mcp-publisher`), authenticated (`mcp-publisher login github`) — only
  needed if also publishing to the official MCP Registry (see below).

```ini
# ~/.pypirc
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-<your-pypi-token>

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-<your-testpypi-token>
```

PyPI and TestPyPI are entirely separate systems — a token created on
pypi.org does **not** work against test.pypi.org, even for the same
username. Register and generate a token on each site separately.

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

Runs `uv build` for all three packages into `dist/`, builds the `.mcpb`
bundle (`packages/jmri-mcp/mcpb/build_mcpb.py`), then `twine check
dist/*.whl dist/*.tar.gz` to validate metadata (the `.mcpb` file is excluded
from this check — it isn't a PyPI distribution format). Fails fast if any
package fails to build or check.

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
make testdeploy
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
make deploy
```

Uploads all three packages from `dist/`. **PyPI does not allow re-uploading
or overwriting a version once published** — double-check the version bump
and `make testdeploy` dry run before running this.

## Publish the GitHub Release (`.mcpb`)

```bash
make release
```

Rebuilds (so the `.mcpb` reflects the current `pyproject.toml` version),
pushes `main`, tags `vX.Y.Z` (read automatically from
`packages/jmri-mcp/pyproject.toml`), pushes the tag, and creates a GitHub
Release (marked pre-release) with the `.mcpb` attached as a downloadable
asset. Requires `jmri-mcp==X.Y.Z` to already be on PyPI (run `make deploy`
first) — the `.mcpb`'s manifest pins that exact version, so Claude Desktop
can't install it otherwise.

## Publish to the MCP Registry (optional)

Requires `mcp-publisher`, authenticated via `mcp-publisher login github`
(see Prerequisites above), and `server.json` at the repo root (already
checked in — update its `version` and the release download `url` to match
the new tag before running this). Requires the GitHub Release from `make
release` above to already exist, since `server.json` points at that
release's `.mcpb` asset URL.

```bash
mcp-publisher publish
```

## After publishing

- Update `docs/install.md`/`INSTALL.md` if the recommended install method
  changed.
