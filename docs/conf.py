import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = Path(__file__).resolve().parent

# Generate the line-maker pages (one per template and per layout) from the live makers before Sphinx reads sources.
subprocess.run(
    [sys.executable, str(ROOT / "tools" / "generate_reference.py")],
    cwd=ROOT,
    check=True,
)

project = "boki"
copyright = "2026, boki contributors"
author = "boki contributors"
release = "0.1.0.dev0"

extensions = [
    "sphinx.ext.autodoc",
    "numpydoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
exclude_patterns = sorted(
    [path.name for path in DOCS.glob("*.md") if path.name != "index.md"]
    + ["_build/**"]
)

autodoc_typehints = "none"
autosummary_generate = False
numpydoc_show_class_members = False
numpydoc_class_members_toctree = False

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}
nitpicky = True

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_js_files = ["home-link.js"]
html_title = "boki"
html_logo = "assets/icon.svg"
html_favicon = "assets/icon.svg"
html_theme_options = {
    "logo": {"text": "boki"},
    "icon_links": [{"name": "GitHub", "url": "https://github.com/combinatrix-ai/boki", "icon": "fa-brands fa-github"}],
}
