from pathlib import Path
import argparse
import shutil
import tempfile
import tomllib
import zipfile


parser = argparse.ArgumentParser(description="Build MCPB bundle")
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

TEMPLATE = ROOT / "mcpb" / "manifest.template.json"
PYPROJECT = ROOT / "pyproject.toml"


# Lire la version depuis pyproject.toml
with open(PYPROJECT, "rb") as f:
    project = tomllib.load(f)["project"]

version = str(project["version"])
jmri_core_pin = next(
    dep for dep in project["dependencies"] if dep.startswith("jmri-core")
)
mcp_pin = next(dep for dep in project["dependencies"] if dep.startswith("mcp"))


# Générer le manifest en mémoire
template_content = TEMPLATE.read_text(encoding="utf-8")

manifest_content = template_content.replace(
    "{{VERSION}}",
    version
)


# pyproject.toml bundlé dans le zip : projet autonome que `uv` (côté hôte,
# Claude Desktop) résout et exécute au lancement. jmri-core et mcp restent
# des dépendances PyPI normales (jmri-core est déjà publié) plutôt que d'être
# bundlés en source — MCPB "uv" ne demande pas un bundle 100% hors-ligne,
# seulement que le serveur MCP lui-même (jmri_mcp) soit fourni en source.
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


# Générer le fichier .mcpb
output = OUT_DIR / f"jmri-mcp-{version}.mcpb"

with tempfile.TemporaryDirectory() as tmp:
    staging = Path(tmp)

    (staging / "manifest.json").write_text(manifest_content, encoding="utf-8")
    (staging / "pyproject.toml").write_text(BUNDLED_PYPROJECT, encoding="utf-8")
    shutil.copy(ROOT / "README.md", staging / "README.md")
    shutil.copy(ROOT / "LICENSE", staging / "LICENSE")
    shutil.copytree(
        ROOT / "src" / "jmri_mcp",
        staging / "src" / "jmri_mcp",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    icon = ROOT / "mcpb" / "icon.png"
    if icon.exists():
        shutil.copy(icon, staging / "icon.png")

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(staging))

print(f"Created {output}")
