.PHONY: build test clean deploy-testpypi deploy-pypi release release-github mcpb release-github-asset release-mcp-registry

# --- Variables ---

PACKAGES := jmri-core jmri-cli jmri-mcp
DIST_DIR := dist
TWINE := uv tool run twine
VERSION := $(shell uv run python -c "import tomllib; print(tomllib.load(open('packages/jmri-mcp/pyproject.toml','rb'))['project']['version'])")
TAG := v$(VERSION)
MCPB := $(DIST_DIR)/jmri-mcp-$(VERSION).mcpb
MCPB_JSON := $(DIST_DIR)/jmri-mcp-$(VERSION).mcpb.json

# --- Build / test / clean ---

# Build sdist+wheel for all 3 packages, build the .mcpb bundle, then
# validate PyPI metadata on the wheels/sdists (not the .mcpb).
build: clean
	@for pkg in $(PACKAGES); do \
		uv build --package $$pkg --out-dir $(DIST_DIR) || exit 1; \
	done
	uv run python packages/jmri-mcp/mcpb/build_mcpb.py --out-dir $(DIST_DIR)
	$(TWINE) check $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

# Run the full mocked test suite across all packages (live suite is opt-in, see docs/testing.md).
test:
	uv run --all-packages pytest

# Remove all build artifacts (dist/).
clean:
	rm -rf $(DIST_DIR)

# --- Deploy to PyPI ---

# Dry-run deploy to TestPyPI, to catch packaging issues before a real release.
deploy-testpypi: build
	$(TWINE) upload --repository testpypi $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

# Deploy all 3 packages to the real PyPI. Irreversible: PyPI never allows
# re-uploading or overwriting a version once published.
deploy-pypi: build
	$(TWINE) upload $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

# --- Release: GitHub Release + MCP Registry ---
# `release` runs these in order; each is also runnable standalone (see `mcpb`
# below for republishing just the .mcpb without re-tagging).

# Push/tag on GitHub, then build+publish the .mcpb (GitHub Release asset +
# MCP Registry) via `mcpb`.
release: release-github mcpb

# Push main and the vX.Y.Z tag to origin.
release-github:
	git push origin main
	git tag -a $(TAG) -m "$(TAG)"
	git push origin $(TAG)

# Rebuild the .mcpb and republish it end to end: GitHub Release asset, then
# MCP Registry — without re-tagging or touching PyPI. This is the target to
# re-publish a fixed .mcpb onto an already-tagged release (e.g. `v1.0.0rc1`
# already exists, only the .mcpb itself changed).
mcpb: release-github-asset release-mcp-registry

# (Re)create the GitHub Release for this tag, marked pre-release, with the
# built .mcpb attached as a downloadable asset. Standalone-safe: rebuilds
# first.
release-github-asset: build
	gh release delete $(TAG) -y || true
	gh release create $(TAG) $(MCPB) \
		--title "$(TAG)" \
		--prerelease \
		--generate-notes

# Render server.json from the template (version, tag, .mcpb SHA-256,
# filename) and publish it to the official MCP Registry. Depends on
# release-github-asset so the SHA-256 always matches the .mcpb actually
# attached to the GitHub Release, never a stale local dist/ copy.
release-mcp-registry: release-github-asset
	mcp-publisher login github --non-interactive || mcp-publisher login github
	sed \
		-e "s/__VERSION__/$(VERSION)/g" \
		-e "s/__TAG__/$(TAG)/g" \
		-e "s/__SHA256__/$$(openssl dgst -sha256 $(MCPB) | awk '{print $$NF}')/g" \
		-e "s/__FILENAME__/$$(basename $(MCPB))/g" \
		packages/jmri-mcp/mcpb/server.json.template > $(MCPB_JSON)
	mcp-publisher publish $(MCPB_JSON)
