.PHONY: build test clean testdeploy deploy release

PACKAGES := jmri-core jmri-cli jmri-mcp
DIST_DIR := dist
TWINE := uv tool run twine
VERSION := $(shell uv run python -c "import tomllib; print(tomllib.load(open('packages/jmri-mcp/pyproject.toml','rb'))['project']['version'])")
TAG := v$(VERSION)
MCPB := $(DIST_DIR)/jmri-mcp-$(VERSION).mcpb
MCPB_JSON := $(DIST_DIR)/jmri-mcp-$(VERSION).mcpb.json

build: clean
	@for pkg in $(PACKAGES); do \
		uv build --package $$pkg --out-dir $(DIST_DIR) || exit 1; \
	done
	uv run python packages/jmri-mcp/mcpb/build_mcpb.py --out-dir $(DIST_DIR)
	$(TWINE) check $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

test:
	uv run --all-packages pytest

clean:
	rm -rf $(DIST_DIR)

testdeploy: build
	$(TWINE) upload --repository testpypi $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

deploy: build
	$(TWINE) upload $(DIST_DIR)/*.whl $(DIST_DIR)/*.tar.gz

release: build publish-github release-mcpb publish-mcpb-json

publish-github:
	git push origin main
	git tag -a $(TAG) -m "$(TAG)"
	git push origin $(TAG)

release-mcpb:
	gh release create $(TAG) $(MCPB) \
		--title "$(TAG)" \
		--prerelease \
		--generate-notes

publish-mcpb-json:
	sed \
		-e "s/__VERSION__/$(VERSION)/g" \
		-e "s/__TAG__/$(TAG)/g" \
		-e "s/__SHA256__/$$(openssl dgst -sha256 $(MCPB) | awk '{print $$NF}')/g" \
		-e "s/__FILENAME__/$$(basename $(MCPB))/g" \
		packages/jmri-mcp/mcpb/server.json.template > $(MCPB_JSON)
	mcp-publisher publish $(MCPB_JSON)
