"""Generate the reference pages that autodoc cannot discover: the line makers.

Makers exist only on entity instances, so this pre-build step reads them from live entities and writes
reStructuredText into docs/reference/api/makers/ (gitignored; docs/conf.py runs this script before Sphinx reads
the sources):

* one page per maker template, with the signature and the full numpydoc text rendered once, and
* one page per built-in layout, with a table of every maker kind: statement, template, side, section, and
  cash-flow class, and
* one page for the members that only loan lines have (``LineItem.draw_or_repay``).

Usage:
    uv run python tools/generate_reference.py
"""
from __future__ import annotations

import inspect
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "reference" / "api" / "makers"

TITLES = {
    "pl_line": "Revenue and expense lines",
    "income_tax": "Income tax",
    "line": "Balance-sheet lines",
    "fixed_asset": "Fixed assets",
    "loan": "Loans",
    "construction": "Construction in progress",
    "capital": "Capital and other equity lines",
    "dividend": "Dividends",
}


def _heading(text: str, char: str) -> str:
    return f"{text}\n{char * len(text)}\n\n"


def _slug(layout_name: str) -> str:
    return layout_name.lower().replace(" ", "-")


def _signature_text(signature: inspect.Signature) -> str:
    """The signature without annotations: Sphinx would turn annotation names into unresolved references."""
    bare = signature.replace(
        parameters=[parameter.replace(annotation=inspect.Parameter.empty)
                    for parameter in signature.parameters.values()],
        return_annotation=inspect.Signature.empty,
    )
    return str(bare)


def collect() -> dict:
    """The makers of the built-in layouts, grouped by layout and by template."""
    sys.path.insert(0, str(ROOT / "src"))
    import boki as b
    from boki._maker_docs import TEMPLATES
    from boki.layouts import Kind

    model = b.Model("Reference", start="2027-01", periods=2, step=b.month)
    entities = [
        model.entity("IFRS", standard=b.IFRS),
        model.entity("US GAAP", standard=b.USGAAP),
        model.entity("J-GAAP", standard=b.JGAAP),
        model.entity("bank", standard=b.IFRS, layout=b.layouts.bank),
    ]
    layouts = []
    templates: dict[str, dict] = {}
    for entity in entities:
        layout = entity.layout
        rows = []
        for item in layout.pl:
            if isinstance(item, Kind):
                rows.append(("PL", item, entity.pl))
        for item in layout.bs:
            rows.append(("BS", item, entity.bs))
        kinds = []
        for statement, kind, namespace in rows:
            maker = getattr(namespace, kind.name)
            kinds.append((statement, kind, maker._template))
            entry = templates.setdefault(maker._template, {
                "signature": inspect.signature(maker), "makers": {}, "first": (statement.lower(), kind.name)})
            if entry["signature"] != inspect.signature(maker):
                raise ValueError(f"template {maker._template!r} is used with different signatures")
            entry["makers"].setdefault(layout.name, []).append((statement.lower(), kind.name))
        layouts.append({"layout": layout, "kinds": kinds, "general": layout is entity.standard.general})
    if set(templates) != set(TEMPLATES) or set(TITLES) != set(TEMPLATES):
        raise ValueError("every template needs a title and at least one maker in a built-in layout")
    return {"layouts": layouts, "templates": templates}


def template_page(key: str, entry: dict, layout_names: list[str]) -> str:
    from numpydoc.docscrape_sphinx import SphinxDocString

    from boki._maker_docs import maker_doc

    statement, kind = entry["first"]
    doc = str(SphinxDocString(inspect.cleandoc(maker_doc(key)), config={}))
    text = f".. _maker-template-{key}:\n\n" + _heading(f"{TITLES[key]} (``{key}``)", "=")
    text += (
        "One signature and one documentation text are shared by every maker listed at the end of this page. The "
        f"call is shown for ``co.{statement}.{kind}``; the other kinds take the same arguments.\n\n"
        f".. py:function:: co.{statement}.{kind}{_signature_text(entry['signature'])}\n\n"
    )
    text += "\n".join(f"   {line}" if line.strip() else "" for line in doc.splitlines()) + "\n\n"
    text += _heading("Makers that use this template", "-")
    for layout_name in layout_names:
        makers = entry["makers"].get(layout_name)
        if makers:
            names = ", ".join(f"``co.{statement}.{name}``" for statement, name in makers)
            text += f"* :doc:`{layout_name} <layout-{_slug(layout_name)}>`: {names}\n"
    return text + "\n"


def layout_page(item: dict) -> str:
    layout = item["layout"]
    how = ("Entities whose standard has no ``layout=`` use it." if item["general"]
           else "Select it with ``m.entity(..., layout=b.layouts.bank)``; it works with any standard.")
    text = _heading(f"{layout.name} layout", "=")
    text += (
        f"{how} Each row below is a maker, ``co.pl.<kind>`` or ``co.bs.<kind>``, and a :doc:`../line-maker`. "
        "The template column links to the page with the maker's signature and documentation. Income and expense "
        "kinds have cash-flow class ``pl``: cash that moves against them is classified as operating.\n\n"
    )
    text += ".. list-table::\n   :header-rows: 1\n\n"
    text += "   * - Maker\n     - Statement\n     - Template\n     - Side\n     - Section\n     - Cash-flow class\n"
    for statement, kind, key in item["kinds"]:
        text += (
            f"   * - ``co.{statement.lower()}.{kind.name}``\n"
            f"     - {statement}\n"
            f"     - :doc:`{key} <template-{key}>`\n"
            f"     - {kind.side}\n"
            f"     - {kind.section or 'none'}\n"
            f"     - {kind.cf}\n"
        )
    stages = [stage.name for stage in layout.stages]
    if stages:
        names = ", ".join(f"``co.pl.{name}``" for name in stages)
        text += f"\nThe subtotals {names} are series, not makers.\n"
    return text


def loan_line_page() -> str:
    """The loan-only members of ``LineItem``, which exist on instances and so cannot be found by autodoc."""
    import boki as b
    from numpydoc.docscrape_sphinx import SphinxDocString

    model = b.Model("Reference", start="2027-01", periods=2, step=b.month)
    loan = model.entity("Reference", standard=b.IFRS).bs.loan("Loan", rate=0)
    text = _heading("Loan line members", "=")
    text += (
        "A line created by ``co.bs.loan`` has the series attributes described under :class:`boki.LineItem` and the "
        "method below. The method exists on loan lines only, so it is generated here from a live loan.\n\n"
        f".. py:method:: boki.LineItem.draw_or_repay{_signature_text(inspect.signature(loan.draw_or_repay))}\n\n"
    )
    doc = str(SphinxDocString(inspect.cleandoc(loan.draw_or_repay.__doc__), config={}))
    return text + "\n".join(f"   {line}" if line.strip() else "" for line in doc.splitlines()) + "\n"


def index_page(layout_names: list[str], keys: list[str]) -> str:
    text = _heading("Line makers", "=")
    text += (
        "Every ``co.pl.<kind>`` and ``co.bs.<kind>`` is a :doc:`../line-maker`. Its signature and documentation "
        "come from one of eight templates. A layout page lists the makers of a layout; a template page documents "
        "a call once for all the kinds that share it.\n\n"
        ".. toctree::\n   :maxdepth: 1\n   :caption: Layouts\n\n"
    )
    text += "".join(f"   layout-{_slug(name)}\n" for name in layout_names)
    text += "\n.. toctree::\n   :maxdepth: 1\n   :caption: Templates\n\n"
    text += "".join(f"   template-{key}\n" for key in keys)
    return text


def generate() -> None:
    data = collect()
    layout_names = [item["layout"].name for item in data["layouts"]]
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    for key, entry in data["templates"].items():
        (OUTPUT / f"template-{key}.rst").write_text(template_page(key, entry, layout_names), encoding="utf-8")
    for item in data["layouts"]:
        (OUTPUT / f"layout-{_slug(item['layout'].name)}.rst").write_text(layout_page(item), encoding="utf-8")
    (OUTPUT / "index.rst").write_text(index_page(layout_names, list(data["templates"])), encoding="utf-8")
    (OUTPUT / "line-item-loan.rst").write_text(loan_line_page(), encoding="utf-8")


if __name__ == "__main__":
    generate()
