from pathlib import Path
import argparse
import shutil
import tempfile
import tomllib
import zipfile


parser = argparse.ArgumentParser(description="Build the standalone Codex distributable")
parser.add_argument(
    "--out-dir",
    type=Path,
    default=Path("dist"),
    help="Output directory"
)

args = parser.parse_args()

OUT_DIR = args.out_dir
OUT_DIR.mkdir(parents=True, exist_ok=True)

# packages/jmri-mcp
ROOT = Path(__file__).parent.parent

PYPROJECT = ROOT / "pyproject.toml"


with open(PYPROJECT, "rb") as f:
    project = tomllib.load(f)["project"]

version = str(project["version"])
jmri_core_pin = next(
    dep for dep in project["dependencies"] if dep.startswith("jmri-core")
)
mcp_pin = next(dep for dep in project["dependencies"] if dep.startswith("mcp"))


# pyproject.toml bundled in the zip: a standalone project that `uv` (invoked
# by jmri_mcpctl.py, unzipped locally by the user) resolves and runs. Same
# approach as build_mcpb.py: jmri-core and mcp stay normal PyPI dependencies
# rather than vendored source, only jmri_mcp itself is bundled in source form.
BUNDLED_PYPROJECT = f"""[project]
name = "jmri-mcp"
version = "{version}"
description = "MCP server for JMRI - voice/chat control of DCC model railroads"
readme = "README.md"
requires-python = ">=3.10"
license = "AGPL-3.0-or-later"
license-files = ["LICENSE"]
dependencies = [
    "{jmri_core_pin}",
    "{mcp_pin}",
]

[project.scripts]
jmri-mcp = "jmri_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jmri_mcp"]
"""


output = OUT_DIR / f"jmri-mcp-{version}.codex.zip"

with tempfile.TemporaryDirectory() as tmp:
    staging = Path(tmp)

    (staging / "pyproject.toml").write_text(BUNDLED_PYPROJECT, encoding="utf-8")
    shutil.copy(ROOT / "README.md", staging / "README.md")
    shutil.copy(ROOT / "LICENSE", staging / "LICENSE")
    shutil.copy(ROOT / "codex" / "jmri_mcpctl.py", staging / "jmri_mcpctl.py")
    shutil.copy(
        ROOT.parent.parent / "docs" / "llm-setup-codex.md",
        staging / "SETUP.md",
    )
    shutil.copytree(
        ROOT / "src" / "jmri_mcp",
        staging / "src" / "jmri_mcp",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging))

print(f"Created {output}")
