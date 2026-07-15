from pathlib import Path
import argparse
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


# Générer le manifest en mémoire
template_content = TEMPLATE.read_text(encoding="utf-8")

manifest_content = template_content.replace(
    "{{VERSION}}",
    version
)


# Générer le fichier .mcpb
output = OUT_DIR / f"jmri-mcp-{version}.mcpb"

with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr(
        "manifest.json",
        manifest_content
    )

    # Ajouter une icône si elle existe
    icon = ROOT / "mcpb" / "icon.png"
    if icon.exists():
        archive.write(
            icon,
            "icon.png"
        )


print(f"Created {output}")