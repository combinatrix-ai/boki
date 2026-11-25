"""Build the website: the landing page in site/ at the root and the Sphinx documentation under docs/.

Usage: uv run python tools/build_site.py [OUTPUT]   (default: _site)
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ["icon.svg", "outputs.png", "formula.png", "ib-3stmt-is.png", "ib-lbo-returns.png", "ib-dcf-summary.png"]


def build(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "site", output)
    (output / "assets").mkdir()
    for name in ASSETS:
        shutil.copy2(ROOT / "docs/assets" / name, output / "assets" / name)
    subprocess.run([sys.executable, "-m", "sphinx", "-W", "--keep-going", "-n", "-q", "-b", "html",
                    "-d", str(ROOT / "docs/_build/doctrees"), str(ROOT / "docs"), str(output / "docs")], check=True)
    (output / "docs/.buildinfo").unlink(missing_ok=True)


if __name__ == "__main__":
    build(ROOT / (sys.argv[1] if len(sys.argv) > 1 else "_site"))
