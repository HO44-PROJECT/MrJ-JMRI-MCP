.PHONY: build test clean testdeploy deploy

PACKAGES := jmri-core jmri-cli jmri-mcp
DIST_DIR := dist
TWINE := uv tool run twine

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
	@test -n "$$TWINE_PASSWORD" || (echo "TWINE_PASSWORD (TestPyPI API token) is not set" && exit 1)
	TWINE_USERNAME=__token__ $(TWINE) upload --repository testpypi $(DIST_DIR)/*

deploy: build
	@test -n "$$TWINE_PASSWORD" || (echo "TWINE_PASSWORD (PyPI API token) is not set" && exit 1)
	TWINE_USERNAME=__token__ $(TWINE) upload $(DIST_DIR)/*

