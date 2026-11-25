"""Build the compact object graph used by the API registry tools."""
from __future__ import annotations

from pathlib import Path


MULTI_SAMPLE_TYPES = {"LineItem", "PL", "BS"}


def type_samples(samples: dict[str, object], type_name: str) -> tuple[object, ...]:
    value = samples[type_name]
    return tuple(value) if type_name in MULTI_SAMPLE_TYPES else (value,)


def build_api_samples(output_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Return module and type samples for registry checks and the Markdown inventory."""
    import boki as b
    from boki import evaluator, excel, model, statements

    m = b.Model("API sample", start="2027-01", periods=2, step=b.year)
    fy = b.fiscal("12-31")
    co = m.entity("Parent", standard=b.IFRS, fiscal=fy)
    sub = m.entity("Subsidiary", standard=b.IFRS, fiscal=fy)
    layout_entities = [co]
    seen_layouts = {id(co.layout)}
    for name in b.__all__:
        standard = getattr(b, name)
        if isinstance(standard, b.layouts.Standard) and id(standard.general) not in seen_layouts:
            layout_entities.append(m.entity(f"{standard.name} general", standard=standard, fiscal=fy))
            seen_layouts.add(id(standard.general))
    for name in b.layouts.__all__:
        layout = getattr(b.layouts, name)
        if isinstance(layout, b.layouts.Layout) and id(layout) not in seen_layouts:
            layout_entities.append(m.entity(layout.name, standard=b.IFRS, layout=layout, fiscal=fy))
            seen_layouts.add(id(layout))

    revenue = co.pl.revenue("Revenue", 100)
    loan = co.bs.loan("Loan", draw={0: 50}, rate=0.05)
    asset = co.bs.fixed_asset("Equipment", cost=20, at=0, life=5 * b.year)
    tax = co.pl.income_tax("Income tax", rate=0.25, base=revenue)
    group = m.group("Group", parent=co)
    group.own(sub, method="consolidate")
    fx = m.fx(b.units.USD, b.units.JPY, closing=150, average=150, opening=150)
    assumption = m.input("Assumption", 1)
    unknown = m.unknown("Unknown", init=1)
    series = m.series("Series", revenue + assumption)
    named = m.series("Named")
    named.define(1)
    m.check(series > 0, "Series is positive")

    def _sample_sensitivity(row_var, col_var):
        """Multiply row and column axis values.

        Parameters
        ----------
        row_var : Series
            Row axis placeholder.
        col_var : Series
            Column axis placeholder.

        Returns
        -------
        Series
            Product of the two axis variables.

        Examples
        --------
        >>> 2 * 3
        6
        """
        return row_var * col_var

    result = m.render()
    comparison = b.compare(result, {series: [101, 101]})
    row = b.row(series, "Series")
    samples = {
        "Model": m,
        "Result": result,
        "Entity": co,
        "EntityChecks": co.checks,
        "PL": tuple(entity.pl for entity in layout_entities),
        "BS": tuple(entity.bs for entity in layout_entities),
        "CF": co.cf,
        "LineMaker": co.pl.revenue,
        "LineItem": (revenue, loan, asset, tax),
        "Series": series,
        "Named": named,
        "Group": group,
        "Unit": b.units.USD,
        "Quantity": 2 * b.units.USD,
        "FxPair": fx,
        "Input": assumption,
        "Unknown": unknown,
        "Timeline": m.timeline,
        "Period": m.timeline.periods[0],
        "Fiscal": fy,
        "Calendar": b.calendar(m),
        "Kernel": b.delay(1),
        "Style": b.Style("sample"),
        "StylePresets": b.styles,
        "Bound": b.approx(1, tol=0.01),
        "Comparison": comparison,
        "Entry": comparison.entries[0],
        "CheckResult": result.checks[0],
        "PlacementLine": row,
        "Section": b.section("Sample", [row]),
        "Sheet": b.sheet("Sample", [row]),
        "Link": b.link(row),
        "Block": b.block(series, [revenue, assumption], label="Sample block"),
        "Panel": b.panel("Sample panel", ["Value"], [("Row", [1])]),
        "Sensitivity": b.sensitivity("Sample grid", [1.0], [2.0], _sample_sensitivity),
        "Table": result.table([series, revenue]),
        "Report": result.to_excel(output_path),
        "CircularReferenceWarning": excel.CircularReferenceWarning("sample"),
        "Untranslatable": excel.Untranslatable("sample"),
        "UnnamedAssumption": excel.UnnamedAssumption("sample"),
        "EquivalenceError": excel.EquivalenceError("sample"),
        "CheckFailed": model.CheckFailed("sample", result, []),
        "LedgerError": statements.LedgerError("sample"),
        "CycleError": evaluator.CycleError([]),
        "UnitError": b.UnitError("sample"),
        "NoRateOfReturn": b.lib.NoRateOfReturn("sample"),
        "NOL": tax.nol,
        "Equity": co.bs.equity,
        "Layout": b.layouts.bank,
        "Kind": b.layouts.bank.bs[0],
        "Stage": b.IFRS.general.stages[0],
        "Standard": b.IFRS,
    }
    samples["_layout_entities"] = tuple(layout_entities)
    samples["_receivers"] = {
        "co": co,
        "co.checks": co.checks,
        "co.pl": co.pl,
        "co.bs": co.bs,
        "co.cf": co.cf,
        "co.pl.revenue": co.pl.revenue,
        "m.series()": named,
        "m.group": group,
        "m.fx": fx,
        "m.input": assumption,
        "m.unknown": unknown,
        "m.timeline": m.timeline,
        "m.timeline.periods[0]": m.timeline.periods[0],
        "b.fiscal": fy,
        "b.calendar": samples["Calendar"],
        "r.checks[0]": result.checks[0],
        "b.row": row,
        "b.section": samples["Section"],
        "b.sheet": samples["Sheet"],
        "b.link": samples["Link"],
        "b.block": samples["Block"],
        "b.panel": samples["Panel"],
        "b.sensitivity": samples["Sensitivity"],
        "r.table": samples["Table"],
        "r.to_excel": samples["Report"],
        "tax.nol": tax.nol,
        "co.bs.equity": co.bs.equity,
    }
    modules = {
        "boki": b,
        "boki.units": b.units,
        "boki.lib": b.lib,
        "boki.shapes": __import__("boki.shapes", fromlist=["*"]),
        "boki.testing": __import__("boki.testing", fromlist=["*"]),
        "boki.export": b.export,
        "boki.layouts": b.layouts,
    }
    return modules, samples
