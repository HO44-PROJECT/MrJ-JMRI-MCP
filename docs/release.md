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

## Deploy to TestPyPI (dry run)

Recommended before the first real publish of a new version, to catch
packaging issues without consuming the real PyPI listing:

```bash
make deploy-testpypi
```

Then verify the install works from TestPyPI in a scratch environment:

```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ jmri-mcp
```

(`--extra-index-url` is needed because TestPyPI doesn't mirror `jmri-mcp`'s
own dependencies like `mcp`.)

## Deploy to PyPI

```bash
make deploy-pypi
```

Uploads all three packages from `dist/`. **PyPI does not allow re-uploading
or overwriting a version once published** — double-check the version bump
and `make deploy-testpypi` dry run before running this.

## Publish the GitHub Release, then the MCP Registry

```bash
make release
```

Runs two steps in order, all driven by the version in
`packages/jmri-mcp/pyproject.toml`:

1. **`release-github`** — pushes `main`, tags `vX.Y.Z`, pushes the tag.
2. **`mcpb`** — builds and publishes the `.mcpb`, see below.

### Republishing just the `.mcpb`

```bash
make mcpb
```

Rebuilds `dist/` and republishes the `.mcpb` end to end, without re-tagging
or touching PyPI — the target to use when only the `.mcpb` itself changed
(e.g. fixing a bad manifest) and `vX.Y.Z` is already tagged and released.
Runs two steps in order:

1. **`release-github-asset`** — creates a GitHub Release (marked
   pre-release) with `dist/jmri-mcp-X.Y.Z.mcpb` attached as a downloadable
   asset (deleting and recreating the release if it already exists, so this
   is safe to re-run). The `.mcpb` bundles `jmri-mcp`'s own source directly
   (`server.type: "uv"`), so only its `jmri-core` dependency needs to
   already be on PyPI (run `make deploy-pypi` first) — `jmri-mcp` itself
   does not need to be published for the `.mcpb` to install.
2. **`release-mcp-registry`** — renders
   `packages/jmri-mcp/mcpb/server.json.template` into
   `dist/jmri-mcp-X.Y.Z.mcpb.json`, filling in the version, the tag (for the
   release download URL), the filename, and the `.mcpb`'s SHA-256 (computed
   from the file `release-github-asset` just uploaded, so it can never point
   at a stale local copy), then runs `mcp-publisher publish` on it. Requires
   `mcp-publisher`, authenticated via `mcp-publisher login github` (see
   Prerequisites above).

There is no `server.json` checked into the repo — it's generated fresh into
`dist/` on every release from the template, so it can never drift out of
sync with the version/tag/checksum actually being published.

## After publishing

- Update `docs/install.md`/`INSTALL.md` if the recommended install method
  changed.
