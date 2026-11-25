"""The Excel export writes formulas that recalculate to boki's own values."""
import math

import pytest

import boki as b
from boki.lib import compound, npv
from boki.units import JPY, USD, year

formulas = pytest.importorskip("formulas")


def recalc(path):
    sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    out = {}
    for key, rng in sol.items():
        k = str(key).upper()
        if "]" in k and "!" in k and ":" not in k.split("!")[1]:
            sheet, cell = k.split("]", 1)[1].split("'!")
            out[(sheet.strip("'"), cell)] = rng.value[0, 0]
    return out


def test_export_recalculates_to_the_same_numbers(tmp_path):
    m = b.Model("shop", start="2027-01", periods=4, step=year)
    growth = m.input("growth", 0.1)
    co = m.entity("Shop", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=50 * USD)
    sales = co.pl.revenue("sales", compound(100 * USD, growth))
    co.pl.cogs("cogs", 0.4 * sales, settle=b.delay(1))
    co.bs.fixed_asset("oven", 80 * USD, at=0, life=4 * year)
    co.bs.loan("loan", draw={0: 60 * USD}, rate=0.05, repay=15 * USD)
    co.pl.income_tax("tax", rate=0.3, base=co.pl.pretax_income)
    value = m.series("value", npv(co.cf.operating, 0.1))
    r = m.render()
    report = r.to_excel(tmp_path / "shop.xlsx")
    assert report.values == 0 and report.formulas > 50
    got = recalc(tmp_path / "shop.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "shop.xlsx")["Model"]
    rows = {ws.cell(i, 1).value.strip(): i for i in range(3, ws.max_row + 1) if ws.cell(i, 1).value}
    for label, node in (("sales", sales), ("net_income", co.pl.net_income), ("Cash", co.bs.cash)):
        for t, want in enumerate(r[node]):
            assert math.isclose(got[("MODEL", f"{chr(67 + t)}{rows[label]}")], want, abs_tol=1e-9), label
    assert math.isclose(got[("MODEL", f"C{rows['value']}")], r[value])
    wb = openpyxl.load_workbook(tmp_path / "shop.xlsx")
    assert wb.sheetnames == ["Inputs", "Shop IS", "Shop BS", "Shop CF", "Shop Schedules", "Checks", "Model"]
    assert got[("CHECKS", "B5")] == "OK"                    # every check holds in every period
    for sheet, label, want in (("Shop IS", "Net income", r[co.pl.net_income]),
                               ("Shop IS", "Revenue", r[sales]),
                               ("Shop CF", "Cash, end of period", r[co.bs.cash]),
                               ("Shop BS", "Balance check", [0] * 4)):
        row = _row(wb[sheet], label)
        for t, w in enumerate(want):
            assert math.isclose(got[(sheet.upper(), f"{chr(67 + t)}{row}")], w, abs_tol=1e-9), (sheet, label)
    # banker: expenses negative, subtotals are sums of the lines above
    ws = wb["Shop IS"]
    assert ws.cell(_row(ws, "Cost of revenue"), 3).value.startswith("=-Model!")
    assert math.isclose(got[("SHOP IS", f"C{_row(ws, 'Cost of revenue')}")], -r[co.pl.cogs.total][0])
    assert ws.cell(4, 3).value == 2027 and ws.cell(4, 3).number_format == '"FY"0"E"_)'


def _row(ws, label):
    return next(i for i in range(1, ws.max_row + 1) if (ws.cell(i, 1).value or "").strip() == label)


def _shop():
    m = b.Model("shop", start="2027-01", periods=3, step=year)
    co = m.entity("Shop", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=5_000_000 * USD)
    sales = co.pl.revenue("sales", compound(3_000_000 * USD, 0.1))
    co.pl.cogs("cogs", 0.4 * sales)
    co.pl.sga("rent", 500_000 * USD)
    co.pl.sga("staff", 0.2 * sales)
    return m, co, sales


def test_money_scale_and_japanese_preset(tmp_path):
    import openpyxl
    m, co, sales = _shop()
    r = m.render()
    r.to_excel(tmp_path / "mm.xlsx", money="$mm")
    got = recalc(tmp_path / "mm.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "mm.xlsx")["Shop IS"]
    assert ws["A2"].value == "($ in millions)"
    assert math.isclose(got[("SHOP IS", f"C{_row(ws, 'Revenue')}")], 3.0)
    assert math.isclose(got[("SHOP IS", f"C{_row(ws, 'Total operating expenses')}")], -(0.5 + 0.6))
    model = openpyxl.load_workbook(tmp_path / "mm.xlsx")["Model"]
    sales_row = _row(model, "sales")
    assert ",," in model.cell(sales_row, 3).number_format and model.cell(sales_row, 2).value == "USD (millions)"

    r.to_excel(tmp_path / "jp.xlsx", style=b.styles.japanese(money="millions JPY"))
    got = recalc(tmp_path / "jp.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "jp.xlsx")
    ws = wb["Shop PL"]
    assert ws["A2"].value == "($ in millions)" and ws.cell(4, 3).value == 2027
    assert math.isclose(got[("SHOP PL", f"C{_row(ws, 'Cost of revenue')}")], 1.2)      # expenses shown positive
    assert '"△"' in ws.cell(_row(ws, "Cost of revenue"), 3).number_format
    assert _row(wb["Shop BS"], "Cash")


def test_plain_preset_keeps_the_link_sheets(tmp_path):
    import openpyxl
    m, co, sales = _shop()
    m.render().to_excel(tmp_path / "p.xlsx", style=b.styles.plain)
    assert openpyxl.load_workbook(tmp_path / "p.xlsx").sheetnames == ["Model", "Shop PL", "Shop BS", "Shop CF"]


def test_style_settings_are_checked():
    with pytest.raises(TypeError, match="colour"):
        b.styles.banker(colour=False)
    with pytest.raises(ValueError, match="money"):
        b.styles.banker(money="$zillions")
    assert b.styles.banker(money="thousands JPY").scale == 1e3 and b.styles.banker.scale == 1


def test_helpers_fold_and_rows_show_in_their_units(tmp_path):
    import openpyxl
    from boki.units import MWh, kW, h
    m = b.Model("pv", start="2027-01", periods=3, step=year)
    capacity = m.input("capacity", 1000 * kW)
    generation = m.series("generation", capacity * (1000 * h) * compound(1.0, -0.005))
    shown = m.series("shown", generation * 1)
    secret = m.series("secret", generation * 2)
    m.render().to_excel(tmp_path / "pv.xlsx", units={generation: MWh}, hide=[secret])
    ws = openpyxl.load_workbook(tmp_path / "pv.xlsx")["Model"]
    g = _row(ws, "generation")
    assert ws.cell(g, 2).value == "MWh" and ws.cell(g, 3).number_format.startswith("#,##0,,_)")
    assert ws.row_dimensions[_row(ws, "secret")].hidden
    helpers = [i for i in range(1, ws.max_row + 1) if (ws.cell(i, 1).value or "").startswith("  ")]
    assert helpers and all(ws.row_dimensions[i].hidden for i in helpers)
    with pytest.raises(ValueError, match="not USD"):
        m.render().to_excel(tmp_path / "x.xlsx", units={generation: USD})


def test_a_failing_check_shows_on_the_checks_sheet(tmp_path):
    import openpyxl
    m = b.Model("cafe", start="2027-01", periods=3, step=year)
    co = m.entity("Cafe", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=10 * USD)
    co.pl.sga("Rent", 8 * USD)
    m.check(co.bs.cash >= 0, "never runs out of cash")
    m.check(co.bs.cash >= -100 * USD, "switched off", level="off")
    m.render(checks="warn").to_excel(tmp_path / "c.xlsx")
    got = recalc(tmp_path / "c.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Checks"]
    assert not any(c.value == "switched off" for c in ws["A"])
    # a cell that evaluates FALSE (0) is shown in red
    rules = [(str(cf.sqref), r) for cf in ws.conditional_formatting for r in cf.rules]
    cells = [r for ref, r in rules if ref.startswith("C6:") and r.type == "cellIs" and r.formula == ["0"]]
    assert cells and cells[0].dxf.fill.fgColor.rgb.endswith("F8D7DA")
    row = _row(ws, "never runs out of cash")
    assert got[("CHECKS", "B5")] == "FAIL" and got[("CHECKS", f"B{row}")] == "FAIL"
    assert [got[("CHECKS", f"{c}{row}")] for c in "CDE"] == [1, 0, 0]
    assert got[("CHECKS", f"B{_row(ws, 'Cafe: assets = liabilities + equity')}")] == "OK"


def test_deferred_tax_and_oci_recalculate_in_excel(tmp_path):
    import openpyxl

    m = b.Model("oci", start=0, periods=3, step=year)
    co = m.entity("Co", standard=b.IFRS, currency=USD, tax_rate=0.3)
    security = co.bs.other_asset("security", opening=0 * USD)
    difference = m.series("temporary difference", data={
        0: 100 * USD,
        1: 150 * USD,
        2: 50 * USD,
    })
    amount = m.series("fair value change", data={
        0: 100 * USD,
        2: -40 * USD,
    })
    co.bs.deferred_tax("depreciation", difference)
    co.oci("fair value reserve", amount, against=security, tax=True)
    r = m.render()
    path = tmp_path / "oci.xlsx"

    report = r.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    is_sheet, bs_sheet = wb["Co IS"], wb["Co BS"]
    deferred_tax_row = _row(is_sheet, "Deferred tax")
    other_comprehensive_income_row = _row(is_sheet, "Other comprehensive income")
    comprehensive_income_row = _row(is_sheet, "Comprehensive income")
    liability_row = _row(bs_sheet, "Deferred tax liability: depreciation")
    oci_liability_row = _row(bs_sheet, "Deferred tax liability: fair value reserve OCI")
    oci_equity_row = _row(bs_sheet, "Other components of equity: fair value reserve")

    assert report.values == 0
    assert [got[("CO IS", f"{col}{deferred_tax_row}")] for col in "CDE"] == pytest.approx([-30, -15, 30])
    assert [got[("CO IS", f"{col}{other_comprehensive_income_row}")] for col in "CDE"] == pytest.approx([70, 0, -28])
    assert [got[("CO IS", f"{col}{comprehensive_income_row}")] for col in "CDE"] == pytest.approx([40, -15, 2])
    assert [got[("CO BS", f"{col}{liability_row}")] for col in "CDE"] == pytest.approx([30, 45, 15])
    assert [got[("CO BS", f"{col}{oci_liability_row}")] for col in "CDE"] == pytest.approx([30, 30, 18])
    assert [got[("CO BS", f"{col}{oci_equity_row}")] for col in "CDE"] == pytest.approx([70, 70, 42])
    assert got[("CHECKS", "B5")] == "OK"


def test_taxed_oci_releases_recalculate_in_excel(tmp_path):
    import openpyxl

    m = b.Model("oci release", start=0, periods=2, step=year)
    co = m.entity("Co", standard=b.IFRS, currency=USD, tax_rate=0.3)
    co.bs.opening(cash=20 * USD)
    recycled_security = co.bs.other_asset("recycled security", opening=0 * USD)
    retained_security = co.bs.other_asset("retained security", opening=0 * USD)
    gain = m.series("fair value gain", data={0: 100 * USD})
    release = m.series("released gain", data={1: 40 * USD})
    co.oci("recycled reserve", gain, against=recycled_security, tax=True)
    co.oci("retained reserve", gain, against=retained_security, recycle=False, tax=True)
    co.pl.income_tax("realized gain tax", data={1: 12 * USD})
    co.oci_release("recycled reserve", release)
    co.oci_release("retained reserve", release)
    path = tmp_path / "oci-release.xlsx"

    report = m.render().to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    is_sheet, bs_sheet = wb["Co IS"], wb["Co BS"]
    other_comprehensive_income_row = _row(is_sheet, "Other comprehensive income")
    comprehensive_income_row = _row(is_sheet, "Comprehensive income")
    other_income_row = _row(is_sheet, "Other income")
    recycled_equity_row = _row(bs_sheet, "Other components of equity: recycled reserve")
    retained_equity_row = _row(bs_sheet, "Other components of equity: retained reserve")
    recycled_tax_row = _row(bs_sheet, "Deferred tax liability: recycled reserve OCI")
    retained_tax_row = _row(bs_sheet, "Deferred tax liability: retained reserve OCI")
    retained_earnings_row = _row(bs_sheet, "Retained earnings")
    balance_check_row = _row(bs_sheet, "Balance check")

    assert report.values == 0
    assert [got[("CO IS", f"{col}{other_comprehensive_income_row}")] for col in "CD"] == pytest.approx([140, -28])
    assert [got[("CO IS", f"{col}{comprehensive_income_row}")] for col in "CD"] == pytest.approx([140, 0])
    assert [got[("CO IS", f"{col}{other_income_row}")] for col in "CD"] == pytest.approx([0, 40])
    assert [got[("CO BS", f"{col}{recycled_equity_row}")] for col in "CD"] == pytest.approx([70, 42])
    assert [got[("CO BS", f"{col}{retained_equity_row}")] for col in "CD"] == pytest.approx([70, 42])
    assert [got[("CO BS", f"{col}{recycled_tax_row}")] for col in "CD"] == pytest.approx([30, 18])
    assert [got[("CO BS", f"{col}{retained_tax_row}")] for col in "CD"] == pytest.approx([30, 18])
    assert [got[("CO BS", f"{col}{retained_earnings_row}")] for col in "CD"] == pytest.approx([20, 88])
    assert [got[("CO BS", f"{col}{balance_check_row}")] for col in "CD"] == pytest.approx([0, 0])
    assert got[("CHECKS", "B5")] == "OK"


def test_plain_statements_include_oci_and_comprehensive_income(tmp_path):
    import openpyxl

    m = b.Model("oci", start=0, periods=2, step=year)
    co = m.entity("Co", standard=b.IFRS, currency=USD, tax_rate=0.3)
    security = co.bs.other_asset("security", opening=0 * USD)
    amount = m.series("fair value change", data={0: 100 * USD})
    co.oci("fair value reserve", amount, against=security, tax=True)
    path = tmp_path / "oci-plain.xlsx"

    m.render().to_excel(path, style=b.styles.plain)
    wb = openpyxl.load_workbook(path)
    pl_sheet, bs_sheet = wb["Co PL"], wb["Co BS"]

    assert _row(pl_sheet, "Other comprehensive income")
    assert _row(pl_sheet, "fair value reserve")
    assert _row(pl_sheet, "Comprehensive income")
    assert _row(bs_sheet, "Deferred tax liability: fair value reserve OCI")
    assert _row(bs_sheet, "Other components of equity: fair value reserve")


def test_excel_cash_flow_includes_fx_class(tmp_path):
    import openpyxl

    m = b.Model("fx", start=0, periods=2, step=year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=100 * USD)
    foreign_cash = co.bs.other_asset("foreign cash", opening=20 * USD)
    fx = m.series("FX revaluation", data={0: 10 * USD})
    co.journal("FX revaluation", fx, debit=co.bs.cash, credit=foreign_cash, cf="fx")
    path = tmp_path / "fx.xlsx"

    m.render().to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    sheet = wb["Co CF"]
    fx_row = _row(sheet, "Effect of exchange rates")
    net_row = _row(sheet, "Net change in cash")

    assert [got[("CO CF", f"{col}{fx_row}")] for col in "CD"] == pytest.approx([10, 0])
    assert [got[("CO CF", f"{col}{net_row}")] for col in "CD"] == pytest.approx([10, 0])


def test_a_lag_by_a_series_offset_recalculates(tmp_path):
    m = b.Model("t", start="2027-01", periods=4, step=b.month)
    x = m.series("x", m.t * 10)
    k = m.series("k", data={0: 1, 1: 0, 2: 2, 3: 5})
    y = m.series("y", x.lag(k, fill=-1))
    r = m.render()
    report = r.to_excel(tmp_path / "lag.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "lag.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "lag.xlsx")["Model"]
    row = next(i for i in range(1, ws.max_row + 1) if ws.cell(i, 1).value == "y")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(4)] == r[y] == [-1, 10, 0, -1]


def test_a_period_chosen_by_an_input_follows_the_input_in_excel(tmp_path):
    m = b.Model("t", start="2027-01", periods=4, step=b.month)
    pick = m.input("pick", 2)
    x = m.series("x", m.t * 10)
    chosen = m.series("chosen", x[pick])
    last = m.series("last", x[m.input("from end", -1)])
    r = m.render()
    report = r.to_excel(tmp_path / "pick.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "pick.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "pick.xlsx")["Model"]
    rows = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    assert "INDEX(" in ws.cell(rows["chosen"], 3).value
    assert got[("MODEL", f"C{rows['chosen']}")] == r[chosen] == 20
    assert got[("MODEL", f"C{rows['last']}")] == r[last] == 30


def test_a_reduction_over_a_constant_is_not_one_cell(tmp_path):
    m = b.Model("t", start=0, periods=3, step=year)
    saving = m.series("saving", 100 * USD)
    total = m.series("total", saving.sum())
    value = m.series("value", npv(saving, 0.1))
    r = m.render()
    assert r[total] == 300
    report = r.to_excel(tmp_path / "c.xlsx")
    got = recalc(tmp_path / "c.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Model"]
    rows = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    assert report.values == 2
    assert got[("MODEL", f"C{rows['total']}")] == 300
    assert math.isclose(got[("MODEL", f"C{rows['value']}")], r[value])


def test_nol_recalculates(tmp_path):
    m = b.Model("t", start=0, periods=6, step=year)
    ebt = m.input("ebt", b.step({0: -100, 1: 30, 2: 50, 3: 200, 4: -20, 5: 100}) * USD)
    carried = m.input("carried in", 40 * USD)
    n = b.nol(ebt, opening=carried, cap=0.8)
    rows = {"balance": m.series("balance", n.balance), "taxable": m.series("taxable", n.taxable)}
    r = m.render()
    assert r.to_excel(tmp_path / "n.xlsx").values == 0
    got = recalc(tmp_path / "n.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "n.xlsx")["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    for name, node in rows.items():
        assert [got[("MODEL", f"{c}{at[name]}")] for c in "CDEFGH"] == pytest.approx(r[node]), name


def test_dates_by_days_xnpv_and_xirr_recalculate(tmp_path):
    from boki.lib import xirr, xnpv
    m = b.Model("t", start="2027-01", periods=4, step=b.month)
    rate = m.input("rate", 0.1)
    last_day = m.series("last day", m.period_end - 1 * b.day)
    cf = m.series("cf", m.input("flows", b.step({0: -100, 1: 30, 2: 40, 3: 50}) * USD))
    rows = {"xnpv": m.series("xnpv", xnpv(cf, rate, last_day)), "xirr": m.series("xirr", xirr(cf, last_day))}
    days = m.series("days", (m.period_end - m.date) / b.day)
    hours = m.series("hours", (m.period_end - m.date) * (24 / b.day))
    accrued = m.series("accrued", 1000 * USD * rate * ((m.period_end - m.date) / (365 * b.day)))
    yr = m.series("year", m.date.year)
    january = m.series("january", (m.period_end - 1 * b.day).month == 1)
    r = m.render()
    report = r.to_excel(tmp_path / "d.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "d.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "d.xlsx")["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    for name, node in rows.items():
        assert math.isclose(got[("MODEL", f"C{at[name]}")], r[node], rel_tol=1e-9), name
    for name, node in {"days": days, "hours": hours, "accrued": accrued, "year": yr, "january": january}.items():
        assert [got[("MODEL", f"{c}{at[name]}")] for c in "CDEF"] == pytest.approx([float(v) for v in r[node]]), name
    assert r[days] == [31, 28, 31, 30]


def test_lookup_tables_go_to_the_inputs_sheet_and_recalculate(tmp_path):
    from datetime import date
    from boki.lib import lookup
    m = b.Model("t", start="2026-11", periods=6, step=b.month)
    coverage = m.input("coverage", b.step({0: 0.2, 1: 0.6, 2: 3, 3: 13, 4: 1, 5: 0.5}))
    rows = {
        "inflation": m.series("inflation", lookup(m.date, {date(2026, 1, 1): 0.02, date(2027, 1, 1): 0.03})),
        "spread": m.series("spread", 0.01 + lookup(coverage, {-1e9: 0.19, 0.5: 0.155, 12.5: 0.0045})),
        "price": m.series("price", lookup(m.date.month, {1: 3 * USD, 2: 5 * USD, 12: 4 * USD})),
    }
    r = m.render()
    report = r.to_excel(tmp_path / "l.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "l.xlsx")
    import openpyxl
    wb = openpyxl.load_workbook(tmp_path / "l.xlsx")
    ws = wb["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    for name, node in rows.items():
        assert [got[("MODEL", f"{c}{at[name]}")] for c in "CDEFGH"] == pytest.approx(r[node]), name
    assert ws.cell(at["inflation"], 3).value.startswith("=LOOKUP(")
    inputs = {row[0].value: [c.value for c in row[2:]] for row in wb["Inputs"].iter_rows() if row[0].value}
    assert inputs["inflation table"][:2] == [0.02, 0.03]
    assert inputs["spread: lookup table: from"][:3] == [-1e9, 0.5, 12.5]


def test_a_running_count_of_a_condition_starts_as_a_number(tmp_path):
    m = b.Model("t", start=0, periods=4, step=year)
    x = m.input("x", b.step({0: 1, 1: 0, 2: 1, 3: 1}))
    count = m.series("count", ((x > 0) & (m.t >= 0)).cumsum())
    ahead = m.series("ahead", ((x > 0) & (m.t >= 0)).reverse_cumsum())
    rows = {"count": count, "ahead": ahead, "total": m.series("total", count.sum() + ahead.sum())}
    r = m.render()
    r.to_excel(tmp_path / "c.xlsx")
    got = recalc(tmp_path / "c.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    assert got[("MODEL", f"C{at['total']}")] == r[rows["total"]] == 7 + 8


def test_reductions_over_a_year_recalculate(tmp_path):
    m = b.Model("t", start="2027-01", periods=18, step=b.month)
    price = m.input("price", 2 * USD)
    x = m.series("x", (m.t + 1) * price)
    rows = {name: m.series(name, expr) for name, expr in {
        "sum0": x.sum(year=0), "sum1": x.sum(year=1), "mean1": x.mean(year=1), "min1": x.min(year=1),
        "max0": x.max(year=0), "last1": x.last(year=1)}.items()}
    r = m.render()
    report = r.to_excel(tmp_path / "y.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "y.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "y.xlsx")["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    for name, node in rows.items():
        assert math.isclose(got[("MODEL", f"C{at[name]}")], r[node]), name
    assert "SUM(" in ws.cell(at["sum1"], 3).value and "AVERAGE(" in ws.cell(at["mean1"], 3).value


def test_rounding_and_math_functions_recalculate(tmp_path):
    m = b.Model("t", start=0, periods=4, step=year)
    x = m.input("x", b.by_year({0: 2.675, 1: -2.675, 2: 1234.5, 3: 7.0}))
    rows = {name: m.series(name, expr) for name, expr in {
        "round2": b.round(x, 2), "down1": b.rounddown(x, 1), "up1": b.roundup(x, 1), "floor": b.floor(x),
        "mod": x % 2, "intdiv": x // 2, "exp": b.exp(m.t / 10), "log": b.log(m.t + 1), "sqrt": b.sqrt(m.t),
        "mean": x.where(m.t >= 1).mean()}.items()}
    r = m.render()
    report = r.to_excel(tmp_path / "f.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "f.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "f.xlsx")["Model"]
    at = {ws.cell(i, 1).value: i for i in range(1, ws.max_row + 1)}
    for name, node in rows.items():
        want = r[node] if isinstance(r[node], list) else [r[node]]
        for t, w in enumerate(want):
            assert math.isclose(got[("MODEL", f"{chr(67 + t)}{at[name]}")], w, abs_tol=1e-12), (name, t)


def test_python_functions_are_written_as_shaded_values(tmp_path):
    m = b.Model("m", start=0, periods=3, step=year)

    @m.series
    def odd(t):
        return t * 7 % 3

    report = m.render().to_excel(tmp_path / "m.xlsx")
    assert report.values == 3 and report.reasons == {"Fn": 3}


def test_construction_completed_at_a_period_index_recalculates(tmp_path):
    """Depreciation before service refers to the book value at completion only in a branch boki never takes;
    the export writes the branch that applies, so Excel sees no circular reference."""
    m = b.Model("plant", start="2027-01", periods=8, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1_000 * USD)
    plant = co.bs.construction("plant", spend=600 * USD * (m.t == 1), complete_at=3, life=b.year / 2)
    r = m.render()
    assert r[plant.depreciation] == pytest.approx([0, 0, 0, 100, 100, 100, 100, 100])
    report = r.to_excel(tmp_path / "plant.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "plant.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "plant.xlsx")["Model"]
    row = _row(ws, "plant depreciation")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(8)] == pytest.approx(r[plant.depreciation])


def test_capex_program_depreciation_recalculates(tmp_path):
    m = b.Model("stores", start="2027-01", periods=8, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1_000 * USD)
    capex = m.series("capex", data={0: 60 * USD, 3: 120 * USD})
    stores = co.bs.fixed_asset("stores", capex, life=b.year / 2)
    r = m.render()
    assert r[stores.depreciation] == pytest.approx([0, 10, 10, 10, 30, 30, 30, 20])
    report = r.to_excel(tmp_path / "stores.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "stores.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "stores.xlsx")["Model"]
    row = _row(ws, "stores depreciation")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(8)] == pytest.approx(r[stores.depreciation])


def test_running_irr_and_irr_default_recalculate(tmp_path):
    from boki.lib import irr
    m = b.Model("flip", start="2027-01", periods=8, step=year)
    project = m.series("project", b.by_year({0: -100}, default=25))
    share = m.series("share")
    investor = m.series("investor", project * share)
    to_date = m.series("IRR to date", irr(investor, running=True, default=0))
    share.define(0.99 - 0.94 * (to_date.lag(1, fill=0) >= 0.08))
    never = m.series("never", irr(m.series("costs", m.t * 0 - 1.0), default=0))
    r = m.render()
    report = r.to_excel(tmp_path / "flip.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "flip.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "flip.xlsx")["Model"]
    row = _row(ws, "IRR to date")
    assert ws.cell(row, 4).value.startswith("=IFERROR(IRR($C$")
    for label, node in (("IRR to date", to_date), ("investor", investor)):
        row = _row(ws, label)
        assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(8)] == pytest.approx(r[node], abs=1e-9)
    assert got[("MODEL", f"C{_row(ws, 'never')}")] == 0


def test_by_month_seasonality_recalculates(tmp_path):
    m = b.Model("shop", start="2027-10", periods=6, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    season = m.input("season", b.by_month({12: 1.5, 1: 1.2}, default=1.0))
    sales = co.pl.revenue("sales", 100 * USD * season)
    r = m.render()
    report = r.to_excel(tmp_path / "shop.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "shop.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "shop.xlsx")["Model"]
    row = _row(ws, "sales")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(6)] == pytest.approx([100, 100, 150, 120, 100, 100])


def test_interest_capitalized_into_a_construction_recalculates(tmp_path):
    m = b.Model("plant", start="2027-01", periods=8, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1_000 * USD)
    plant = co.bs.construction("plant", spend=600 * USD * (m.t == 0), complete_at=3, life=b.year / 2)
    co.bs.loan("loan", draw={0: 600 * USD}, rate=0.12 / year, capitalize_during=m.t < 3, capitalize_into=plant)
    r = m.render()
    assert r[plant.depreciation] == pytest.approx([0, 0, 0, 102, 102, 102, 102, 102])
    report = r.to_excel(tmp_path / "plant.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "plant.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "plant.xlsx")["Model"]
    row = _row(ws, "plant depreciation")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(8)] == pytest.approx(r[plant.depreciation])


def test_monthly_models_show_fiscal_years_on_the_statements(tmp_path):
    import openpyxl
    m = b.Model("m", start="2027-04", periods=18, step=b.month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD, fiscal=b.fiscal(year_end="03-31"))
    co.bs.opening(cash=100 * USD)
    sales = co.pl.revenue("sales", 10 * USD + m.t * USD)
    r = m.render()
    r.to_excel(tmp_path / "m.xlsx")
    got = recalc(tmp_path / "m.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "m.xlsx")["Co IS"]
    assert [ws.cell(4, c).value for c in (3, 4, 5)] == [2028, 2029, None]
    row = _row(ws, "Revenue")
    assert got[("CO IS", f"C{row}")] == pytest.approx(sum(r[sales][:12]))
    assert got[("CO IS", f"D{row}")] == pytest.approx(sum(r[sales][12:]))
    cf = openpyxl.load_workbook(tmp_path / "m.xlsx")["Co CF"]
    assert got[("CO CF", f"D{_row(cf, 'Cash, end of period')}")] == pytest.approx(r[co.bs.cash][-1])
    r.to_excel(tmp_path / "p.xlsx", columns="periods")
    assert openpyxl.load_workbook(tmp_path / "p.xlsx")["Co IS"].cell(4, 3).value == "Apr-27"


def test_sec_style_and_ifrs_presentation(tmp_path):
    import openpyxl
    for standard in (b.USGAAP, b.IFRS):
        m = b.Model("w", start="2027-01", periods=2, step=year)
        co = m.entity("W", standard=standard, currency=USD)
        co.bs.opening(cash=10 * USD)
        co.pl.revenue("sales", 100 * USD)
        co.bs.fixed_asset("Plant", 30 * USD, at=0, life=10 * year)
        co.bs.loan("Loan", draw={0: 20 * USD}, rate=0.05, repay=5 * USD)
        r = m.render()
        r.to_excel(tmp_path / "w.xlsx", style=b.styles.sec)
        wb = openpyxl.load_workbook(tmp_path / "w.xlsx")
        bs = [wb["W BS"].cell(i, 1).value for i in range(5, wb["W BS"].max_row + 1)]
        is_ = wb["W IS"]
        assert is_.cell(4, 3).value == 2027 and is_.cell(3, 3).value == "Year Ended December 31,"
        assert '"$"' in is_.cell(5, 3).number_format          # the first line carries the dollar sign
        if standard is b.USGAAP:
            assert is_["A2"].value == "CONSOLIDATED STATEMENTS OF OPERATIONS"
            assert bs.index("Cash") < bs.index("Plant") and bs.index("Total liabilities") < bs.index("Total equity")
        else:
            assert is_["A2"].value == "STATEMENT OF PROFIT OR LOSS"
            assert "Profit for the year" in [is_.cell(i, 1).value for i in range(5, is_.max_row + 1)]
            assert bs.index("Plant") < bs.index("Cash and cash equivalents")
            assert bs.index("Total equity") < bs.index("Total liabilities")
            assert "Total equity and liabilities" in bs
        got = recalc(tmp_path / "w.xlsx")
        check = bs.index("Balance check") + 5
        assert got[("W BS", f"C{check}")] == pytest.approx(0)


def test_schedules_roll_forward_to_the_ledger_balances(tmp_path):
    import openpyxl
    m = b.Model("w", start="2027-01", periods=3, step=year)
    co = m.entity("W", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=10 * USD)
    co.pl.revenue("Sales", 100 * USD, settle=b.delay(1))
    plant = co.bs.fixed_asset("Plant", 30 * USD, at=0, life=3 * year)
    loan = co.bs.loan("Term loan", draw={0: 20 * USD}, rate=0.05, repay=5 * USD)
    r = m.render()
    r.to_excel(tmp_path / "w.xlsx")
    got = recalc(tmp_path / "w.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "w.xlsx")["W Schedules"]
    labels = [ws.cell(i, 1).value for i in range(1, ws.max_row + 1)]
    closing = [i + 1 for i, v in enumerate(labels) if v == "Closing balance"]
    assert labels[labels.index("Term loan") + 1:labels.index("Term loan") + 4] == ["Opening balance", "Drawn", "Repaid"]
    for row, node in zip(closing, (loan.balance, plant.balance)):
        assert [got[("W SCHEDULES", f"{c}{row}")] for c in "CDE"] == pytest.approx(r[node])


def test_a_where_without_else_sums_like_boki(tmp_path):
    m = b.Model("w", start=0, periods=4, step=year)
    x = m.series("x", (m.t + 1) * 10)
    total = m.series("first two years", x.where(m.t < 2).sum())
    r = m.render()
    r.to_excel(tmp_path / "w.xlsx", style=b.styles.plain)
    got = recalc(tmp_path / "w.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "w.xlsx")["Model"]
    assert got[("MODEL", f"C{_row(ws, 'first two years')}")] == pytest.approx(r[total]) == 30


def test_irr_with_several_roots_starts_excel_at_boki_s_root(tmp_path):
    from boki.lib import irr
    m = b.Model("i", start=0, periods=4, step=year)
    flows = m.series("flows", b.by_year({0: -31, 1: 56, 2: 47, 3: -6}))      # roots near 1.4 and −0.9
    rate = m.series("IRR", irr(flows))
    r = m.render()
    r.to_excel(tmp_path / "i.xlsx", style=b.styles.plain)
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "i.xlsx")["Model"]
    formula = ws[f"C{_row(ws, 'IRR')}"].value
    # Excel's IRR searches from its guess; boki's root as the guess makes Excel land on the same root.
    # (The formulas package used by recalc() ignores the guess, so this checks the formula itself.)
    assert formula.startswith("=IRR(") and float(formula.rstrip(")").rsplit(",", 1)[1]) == pytest.approx(r[rate])
    assert r[rate] == pytest.approx(1.4037, abs=1e-3)


def test_a_pl_line_holds_its_formula_and_its_posting_adds_no_row(tmp_path):
    m = b.Model("p", start=0, periods=3, step=year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    sales = co.pl.revenue("Product sales", compound(100 * USD, 0.1))
    co.pl.cogs("Cost of sales", 0.4 * sales)
    r = m.render()
    r.to_excel(tmp_path / "p.xlsx", style=b.styles.plain)
    import openpyxl
    ws = openpyxl.load_workbook(tmp_path / "p.xlsx")["Model"]
    labels = [(ws.cell(i, 1).value or "").strip() for i in range(1, ws.max_row + 1)]
    assert labels.count("Product sales") == labels.count("Cost of sales") == 1
    assert not any(x.endswith("postings") for x in labels)                      # each posting is its PL line
    row = _row(ws, "Product sales")
    assert ws[f"D{row}"].value == f"=C{row}*(1+0.1)"                            # the recurrence is on the PL line
    got = recalc(tmp_path / "p.xlsx")
    assert got[("MODEL", f"E{_row(ws, 'Cost of sales')}")] == pytest.approx(0.4 * 121)


def test_a_shared_sub_expression_is_written_inline_until_a_formula_gets_too_long(tmp_path):
    from boki import excel
    import openpyxl
    m = b.Model("s", start=0, periods=3, step=year)
    x = m.input("x", 2.0)
    short = x * 3 + 1                                                   # used twice, short: written in place
    m.series("a", short * 2)
    m.series("b", short + 5)
    long = sum((x + k) * (x - k) for k in range(1, 12))                 # used twice, long: gets a row
    m.series("c", long * 2)
    m.series("d", long + 5)
    r = m.render()
    r.to_excel(tmp_path / "s.xlsx", style=b.styles.plain)
    ws = openpyxl.load_workbook(tmp_path / "s.xlsx")["Model"]
    labels = [(ws.cell(i, 1).value or "").strip() for i in range(1, ws.max_row + 1)]
    assert labels.count("(op)") == 1                                    # only the long one
    assert ws[f"C{_row(ws, 'a')}"].value == "=(((Inputs!$C$3*3)+1)*2)"
    op = _row(ws, "(op)")
    assert ws[f"C{_row(ws, 'c')}"].value == f"=($C${op}*2)"               # refers to the (scalar) row
    assert len(ws[f"C{_row(ws, 'd')}"].value) <= excel.MAX_FORMULA
    got = recalc(tmp_path / "s.xlsx")
    assert got[("MODEL", f"C{_row(ws, 'd')}")] == pytest.approx(r[m._named["d"]])


def test_an_unnamed_assumption_is_an_error_and_a_named_input_is_not(tmp_path):
    import openpyxl
    m = b.Model("u", start=0, periods=3, step=year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    sales = co.pl.revenue("sales", m.input("sales plan", b.by_year({0: 100, 1: 120, 2: 150}) * USD))
    ratio = b.by_year({0: 0.4, 1: 0.38, 2: 0.36})                              # a ratio with no name
    co.pl.cogs("cost", ratio * sales)
    from boki.excel import UnnamedAssumption
    with pytest.raises(UnnamedAssumption, match=r"test_excel\.py:\d+, used in 'cost'"):
        m.render().to_excel(tmp_path / "u.xlsx", style=b.styles.plain)
    m = b.Model("u", start=0, periods=3, step=year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    sales = co.pl.revenue("sales", m.input("sales plan", b.by_year({0: 100, 1: 120, 2: 150}) * USD))
    co.pl.cogs("cost", m.input("cost ratio", b.by_year({0: 0.4, 1: 0.38, 2: 0.36})) * sales)
    report = m.render().to_excel(tmp_path / "u.xlsx", style=b.styles.plain)
    assert report.unnamed == []
    labels = [(c.value or "").strip() for c in openpyxl.load_workbook(tmp_path / "u.xlsx")["Model"]["A"]]
    assert not any(x.endswith("postings") for x in labels)                    # the input is booked without a row


def test_a_running_sum_of_a_row_is_sum_over_its_cells(tmp_path):
    import openpyxl
    m = b.Model("c", start=0, periods=4, step=year)
    x = m.series("x", (m.t + 1) * 10)
    to_date = m.series("x to date", x.cumsum())
    other = m.series("y to date", (x * 2 + 1).cumsum())                   # no row to sum over: a recurrence
    r = m.render()
    r.to_excel(tmp_path / "c.xlsx", style=b.styles.plain)
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Model"]
    row, xr = _row(ws, "x to date"), _row(ws, "x")
    assert ws[f"F{row}"].value == f"=SUM($C{xr}:F{xr})"
    assert ws[f"D{_row(ws, 'y to date')}"].value.startswith(f"=(C{_row(ws, 'y to date')}+")
    got = recalc(tmp_path / "c.xlsx")
    assert got[("MODEL", f"F{row}")] == r[to_date][3] == 100
    assert got[("MODEL", f"F{_row(ws, 'y to date')}")] == pytest.approx(r[other][3])


def _saas():
    from boki.units import month
    account = b.unit("account")
    m = b.Model("saas", start="2027-01", periods=6, step=month)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=1_000 * USD)
    price = m.input("price", 30 * USD / account / month)
    churn_rate = m.input("churn rate", 0.02)
    customers = m.series("customers", unit=account)
    opening = customers.lag(1, fill=100 * account)
    new = m.series("new", 20 * account + 0 * m.t * account)
    churned = m.series("churned", opening * churn_rate)
    customers.define(opening + new - churned)
    arpa = m.series("ARPA", price * 1)                                      # placed nowhere: written inline
    revenue = co.pl.revenue("revenue", customers * arpa)
    cost = co.pl.cogs("hosting", customers * 3 * USD / account / month)
    margin = m.series("gross margin", revenue - cost)
    return m, dict(customers=customers, new=new, churned=churned, price=price, revenue=revenue, cost=cost,
                   margin=margin, arpa=arpa)


def test_rows_placed_on_sheets_recalculate_and_links_refer_to_them(tmp_path):
    import openpyxl
    m, n = _saas()
    revenue_row = b.row(n["revenue"], label="Revenue")
    sheets = [
        b.sheet("Sales", [b.section("Customers", [n["new"], n["churned"], n["customers"]]),
                          b.section("Pricing", [n["price"], revenue_row])]),
        b.sheet("Summary", [b.link(revenue_row), b.row(n["cost"]), n["margin"]]),
    ]
    r = m.render()
    report = r.to_excel(tmp_path / "s.xlsx", sheets=sheets)
    wb = openpyxl.load_workbook(tmp_path / "s.xlsx")
    assert wb.sheetnames[:3] == ["Inputs", "Sales", "Summary"]
    sales, summary = wb["Sales"], wb["Summary"]
    rev, link = _row(sales, "Revenue"), _row(summary, "Revenue")
    assert summary[f"E{link}"].value == f"=Sales!E{rev}"                       # shown again, one formula
    assert sales[f"C{_row(sales, 'price')}"].value.startswith("=Inputs!")      # an input is a link to Inputs
    assert "ARPA" not in [(c.value or "").strip() for c in wb["Model"]["A"]]   # not placed: written inline
    assert "Inputs!" in sales[f"E{rev}"].value                                 # ... inside the revenue formula
    got = recalc(tmp_path / "s.xlsx")
    for sheet, ws, label, node in (("SALES", sales, "customers", n["customers"]), ("SALES", sales, "Revenue", n["revenue"]),
                                   ("SUMMARY", summary, "Revenue", n["revenue"]),
                                   ("SUMMARY", summary, "gross margin", n["margin"])):
        row = _row(ws, label)
        assert [got[(sheet, f"{c}{row}")] for c in "CDEFGH"] == pytest.approx(r[node])
    assert report.values == 0


def test_placement_errors_name_the_row():
    m, n = _saas()
    r = m.render()
    with pytest.raises(ValueError, match="placed twice"):
        r.to_excel("x.xlsx", sheets=[b.sheet("A", [n["new"]]), b.sheet("B", [n["new"]])])
    with pytest.raises(ValueError, match="not placed"):
        r.to_excel("x.xlsx", sheets=[b.sheet("A", [b.link(n["new"])])])
    with pytest.raises(ValueError, match="needs label"):
        r.to_excel("x.xlsx", sheets=[b.sheet("A", [n["new"] * 2])])
    with pytest.raises(ValueError, match="workbook's own sheet"):
        b.sheet("Model", [])


def test_a_group_s_consolidated_statements_are_written_and_tie_out(tmp_path):
    import openpyxl
    from boki.units import JPY
    m = b.Model("g", start=0, periods=4, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.capital("paid-in", 300 * JPY, at=0, counterparty=parent)
    sub.bs.loan("parent loan", draw={0: 200 * JPY}, rate=0.05, repay=50 * JPY, counterparty=parent)
    sub.pl.revenue("sales", 400 * JPY, settle=b.delay(1))
    sub.pl.sga("costs", 300 * JPY)
    parent.pl.revenue("fee", 10 * JPY, counterparty=sub.pl.sga)
    sub.bs.dividend("dividend", 20 * JPY, counterparty=parent)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", goodwill_life=10 * year)
    r = m.render()
    report = r.to_excel(tmp_path / "g.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "g.xlsx")
    assert {"Group IS", "Group BS", "Group CF"} <= set(wb.sheetnames)
    got = recalc(tmp_path / "g.xlsx")
    assert got[("CHECKS", "B5")] == "OK" and report.values == 0               # every entity and the group tie out
    ws = wb["Group IS"]
    row = next(c[0].row for c in ws.iter_rows() if (c[0].value or "").strip() == "Net income")
    assert [got[("GROUP IS", f"{col}{row}")] for col in "CDEF"] == pytest.approx(r.pl(g).row("Net income"))


def test_a_group_s_nci_statements_recalculate_from_formulas(tmp_path):
    import openpyxl
    from boki.units import JPY, year

    m = b.Model("s2", start=0, periods=2, step=year)
    parent, sub = m.entity("Parent", currency=JPY), m.entity("Sub", currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY, goodwill_life=10 * year)

    r = m.render()
    report = r.to_excel(tmp_path / "nci.xlsx")
    got = recalc(tmp_path / "nci.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "nci.xlsx")
    income = wb["Group IS"]
    balance = wb["Group BS"]
    income_rows = {str(c[0].value).strip(): c[0].row for c in income.iter_rows() if c[0].value}
    balance_rows = {str(c[0].value).strip(): c[0].row for c in balance.iter_rows() if c[0].value}

    assert report.values == 0 and got[("CHECKS", "B5")] == "OK"
    nci_row = income_rows["Profit attributable to noncontrolling interests"]
    parent_row = income_rows["Profit attributable to parent shareholders"]
    balance_nci_row = balance_rows["Noncontrolling interests"]
    assert [got[("GROUP IS", f"{col}{nci_row}")] for col in "CD"] == pytest.approx([20, 20])
    assert [got[("GROUP IS", f"{col}{parent_row}")] for col in "CD"] == pytest.approx([80, 80])
    assert [got[("GROUP BS", f"{col}{balance_nci_row}")] for col in "CD"] == pytest.approx([120, 140])


def test_a_group_s_equity_method_statements_recalculate_from_formulas(tmp_path):
    import openpyxl
    from boki.units import JPY

    m = b.Model("S5 equity method", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY)
    associate = m.entity("Associate", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    associate.bs.opening(cash=6 * JPY)
    associate.bs.other_asset("Net assets", opening=594 * JPY)
    associate.pl.revenue("Profit", 50 * JPY)
    associate.bs.dividend("Dividend to parent", 6 * JPY, counterparty=parent)
    group = m.group("Group", parent=parent)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    path = tmp_path / "s5-equity-method.xlsx"
    report = result.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    is_sheet, bs_sheet, cf_sheet = wb["Group IS"], wb["Group BS"], wb["Group CF"]

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    earnings_row = _row(is_sheet, "Equity method earnings")
    investment_row = _row(bs_sheet, "Investments in associates: Associate")
    investing_row = _row(cf_sheet, "Cash flow from investing")
    assert [got[("GROUP IS", f"{col}{earnings_row}")] for col in "CD"] == pytest.approx([13, 13])
    assert [got[("GROUP BS", f"{col}{investment_row}")] for col in "CD"] == pytest.approx([207, 214])
    assert [got[("GROUP CF", f"{col}{investing_row}")] for col in "CD"] == pytest.approx([-200, 0])


def test_a_group_s_two_equity_method_lots_and_partial_sale_recalculate_from_formulas(tmp_path):
    import openpyxl
    from boki.units import JPY

    m = b.Model("S5 equity method lots", start=0, periods=3, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY)
    associate = m.entity("Associate", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    plant = associate.bs.other_asset("Plant", opening=600 * JPY)
    associate.pl.revenue("Profit", 50 * JPY)
    group = m.group("Group", parent=parent)
    group.own(associate, 0.3, since=0, method="equity", consideration=200 * JPY,
              goodwill_life=10 * year)
    group.own(associate, 0.4, since=1, method="equity", consideration=80 * JPY,
              fair_value={plant: (50 * JPY, 5 * year)}, goodwill_life=10 * year)
    group.own(associate, 0.3, since=2, method="equity", proceeds=90 * JPY)

    result = m.render()
    path = tmp_path / "s5-equity-method-lots.xlsx"
    report = result.to_excel(path)
    got = recalc(path)
    workbook = openpyxl.load_workbook(path)
    income, balance, cash_flow = workbook["Group IS"], workbook["Group BS"], workbook["Group CF"]

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    earnings_row = _row(income, "Equity method earnings")
    gain_row = _row(income, "Gain on sale of investments in affiliates")
    investment_row = _row(balance, "Investments in associates: Associate")
    investing_row = _row(cash_flow, "Cash flow from investing")
    assert [got[("GROUP IS", f"{col}{earnings_row}")] for col in "CDE"] == pytest.approx(
        [13, 16.15, 12.1125])
    assert [got[("GROUP IS", f"{col}{gain_row}")] for col in "CDE"] == pytest.approx(
        [0, 0, 12.7125])
    assert [got[("GROUP BS", f"{col}{investment_row}")] for col in "CDE"] == pytest.approx(
        [213, 309.15, 243.975])
    assert [got[("GROUP CF", f"{col}{investing_row}")] for col in "CDE"] == pytest.approx(
        [-200, -80, 90])


def test_rows_shown_negative_or_in_thousands_keep_every_result(tmp_path):
    import openpyxl
    m, n = _saas()
    to_date = m.series("revenue to date", n["revenue"].cumsum())
    churned = b.row(n["churned"], sign=-1)                                     # shown as a decrease
    revenue = b.row(n["revenue"], label="Revenue (thousands)", scale=1000)
    cost = b.row(n["cost"], label="Hosting", sign=-1)
    sheets = [b.sheet("Plan", [b.section("Customers", [n["new"], churned, n["customers"]]),
                               b.section("P&L", [revenue, cost, n["margin"], to_date])]),
              b.sheet("Summary", [b.link(revenue)])]
    r = m.render()
    report = r.to_excel(tmp_path / "t.xlsx", sheets=sheets)
    wb = openpyxl.load_workbook(tmp_path / "t.xlsx")
    ws, got = wb["Plan"], recalc(tmp_path / "t.xlsx")
    shown = lambda sheet, w, label: [got[(sheet, f"{c}{_row(w, label)}")] for c in "CDEFGH"]
    assert shown("PLAN", ws, "churned") == pytest.approx([-x for x in r[n["churned"]]])
    assert shown("PLAN", ws, "Revenue (thousands)") == pytest.approx([x / 1000 for x in r[n["revenue"]]])
    assert shown("SUMMARY", wb["Summary"], "Revenue (thousands)") == pytest.approx([x / 1000 for x in r[n["revenue"]]])
    assert shown("PLAN", ws, "Hosting") == pytest.approx([-x for x in r[n["cost"]]])
    for label, node in (("customers", n["customers"]), ("gross margin", n["margin"]), ("revenue to date", to_date)):
        assert shown("PLAN", ws, label) == pytest.approx(r[node])               # results unchanged by the display
    assert got[("CHECKS", "B5")] == "OK" and report.values == 0
    rev_is = next(c[0].row for c in wb["Co IS"].iter_rows() if (c[0].value or "").strip() == "Revenue")
    assert got[("CO IS", f"C{rev_is}")] == pytest.approx(sum(r[n["revenue"]]))   # the statement sums the value
    with pytest.raises(ValueError, match="sign="):
        b.row(n["new"], sign=2)


def test_calendar_rows_are_a_timeline_at_the_top(tmp_path):
    import openpyxl
    m = b.Model("c", start="2027-01", periods=4, step=year)
    x = m.input("x", 10.0)
    y = m.series("y", x * m.t + 1)
    r = m.render()
    r.to_excel(tmp_path / "c.xlsx", style=b.styles.plain)
    ws = openpyxl.load_workbook(tmp_path / "c.xlsx")["Model"]
    labels = [(c.value or "").strip() for c in ws["A"]]
    assert labels.index("timeline") < labels.index("period number") < labels.index("y")
    n = _row(ws, "period number")
    assert ws[f"E{_row(ws, 'y')}"].value == f"=((Inputs!$C$3*E{n})+1)"
    assert recalc(tmp_path / "c.xlsx")[("MODEL", f"F{_row(ws, 'y')}")] == r[y][3] == 31


def test_index_and_fade_follow_changed_inputs_in_excel(tmp_path):
    from boki.lib import fade, index
    import openpyxl

    m = b.Model("live", start="2027-01", periods=4, step=year)
    rate = m.input("growth", 0.1)
    indexed = m.series("index", index(rate))
    gated = m.series("gated index", index(rate, when=m.t != 2, start="2028-01"))
    start, end = m.input("start", 10.0), m.input("end", 30.0)
    fading = m.series("fade", fade(start, end, over=(1, 3)))
    path = tmp_path / "live.xlsx"
    m.render().to_excel(path, style=b.styles.plain)

    wb = openpyxl.load_workbook(path)
    inputs = wb["Inputs"]
    inputs.cell(_row(inputs, "growth"), 3, 0.2)
    inputs.cell(_row(inputs, "start"), 3, 20.0)
    inputs.cell(_row(inputs, "end"), 3, 40.0)
    wb.save(path)
    got = recalc(path)
    ws = openpyxl.load_workbook(path)["Model"]

    assert [got[("MODEL", f"{c}{_row(ws, 'index')}")] for c in "CDEF"] == pytest.approx([1, 1.2, 1.44, 1.728])
    assert [got[("MODEL", f"{c}{_row(ws, 'gated index')}")] for c in "CDEF"] == pytest.approx([1, 1.2, 1.2, 1.44])
    assert [got[("MODEL", f"{c}{_row(ws, 'fade')}")] for c in "CDEF"] == pytest.approx([20, 20, 30, 40])


def test_dynamic_by_year_and_step_values_follow_changed_inputs(tmp_path):
    import openpyxl

    m = b.Model("tables", start="2027-01", periods=4, step=year)
    first, second = m.input("first", 0.05), m.input("second", 0.15)
    by_year = m.series("by year", b.by_year({0: first, 1: first, 2: second, 3: second}))
    step = m.series("step", b.step({0: first, 2: second}))
    constant = m.series("constant", b.by_year({0: 1, 1: 1, 2: 3, 3: 3}))
    scaled = m.series("scaled", b.by_year({0: first, 1: first, 2: second, 3: second}) * 2)
    path = tmp_path / "tables.xlsx"
    report = m.render().to_excel(path, style=b.styles.plain)
    assert report.data == 4 and report.unnamed == []

    wb = openpyxl.load_workbook(path)
    inputs = wb["Inputs"]
    inputs.cell(_row(inputs, "first"), 3, 0.3)
    inputs.cell(_row(inputs, "second"), 3, 0.4)
    wb.save(path)
    got = recalc(path)
    ws = openpyxl.load_workbook(path)["Model"]

    for label in ("by year", "step"):
        assert [got[("MODEL", f"{c}{_row(ws, label)}")] for c in "CDEF"] == pytest.approx([0.3, 0.3, 0.4, 0.4])
    assert [got[("MODEL", f"{c}{_row(ws, 'scaled')}")] for c in "CDEF"] == \
        pytest.approx([0.6, 0.6, 0.8, 0.8])
    assert [got[("MODEL", f"{c}{_row(ws, 'constant')}")] for c in "CDEF"] == \
        pytest.approx([1, 1, 3, 3])


def test_spread_does_not_get_a_helper_row(tmp_path):
    import openpyxl

    m = b.Model("spread", start=0, periods=4, step=year)
    source = m.series("sales", (m.t + 1) * 10)
    result = m.series("recognized", source.spread(b.delay(1)) + 5)
    r = m.render()
    path = tmp_path / "spread.xlsx"
    r.to_excel(path, style=b.styles.plain)
    ws = openpyxl.load_workbook(path)["Model"]
    labels = [(c.value or "").strip() for c in ws["A"]]

    assert "sales.spread(delay(1))" not in labels
    got = recalc(path)
    assert [got[("MODEL", f"{c}{_row(ws, 'recognized')}")] for c in "CDEF"] == pytest.approx(r[result])


def test_npv_at_a_rate_per_period_discounts_by_a_factor_row(tmp_path):
    from boki.lib import npv
    import openpyxl

    m = b.Model("npv", start=0, periods=3, step=year)
    cash = m.series("cash", b.by_year({0: 40, 1: 50, 2: 60}))
    rate = m.series("rate", 0.1 + 0.05 * m.t)
    initial = m.series("initial", -100 + 0 * m.t)
    value = m.series("NPV", npv(cash, rate, initial=initial))
    later = m.series("NPV at the end of period 1", npv(cash, rate, at=1, initial=initial))
    r = m.render()
    assert r[value] == pytest.approx(-100 + 40 / 1.1 + 50 / (1.1 * 1.15) + 60 / (1.1 * 1.15 * 1.2))
    path = tmp_path / "npv.xlsx"
    report = r.to_excel(path, style=b.styles.plain)
    assert report.values == 0
    got = recalc(path)
    ws = openpyxl.load_workbook(path)["Model"]
    for label, node in (("NPV", value), ("NPV at the end of period 1", later)):
        actual = got[("MODEL", f"C{_row(ws, label)}")]
        assert isinstance(actual, (int, float)), actual
        assert actual == pytest.approx(r[node])
    formula = ws[f"C{_row(ws, 'NPV')}"].value
    cash_row, initial_row, factor_row = _row(ws, "cash"), _row(ws, "initial"), _row(ws, "discount")
    # each flow times the cumulative discount factor (the row discount() writes), plus the flow at the start
    assert formula == f"=(SUMPRODUCT($C${cash_row}:$E${cash_row},$C${factor_row}:$E${factor_row})+C{initial_row})"
    assert ws[f"C{_row(ws, 'NPV at the end of period 1')}"].value.endswith(f"/D{factor_row})")
    assert ws[f"D{factor_row}"].value == f"=(C{factor_row}/(1+D{_row(ws, 'rate')}))"


def test_npv_at_a_constant_rate_is_excel_npv(tmp_path):
    from boki.lib import npv
    import openpyxl

    m = b.Model("npv", start=0, periods=3, step=year)
    cash = m.series("cash", b.by_year({0: 40, 1: 50, 2: 60}))
    rate = m.input("rate", 0.1)
    m.series("NPV", npv(cash, rate, at=0, initial=-100))
    path = tmp_path / "npv.xlsx"
    m.render().to_excel(path, style=b.styles.plain)
    ws = openpyxl.load_workbook(path)["Model"]
    c = _row(ws, "cash")
    assert ws[f"C{_row(ws, 'NPV')}"].value == f"=((-100+NPV(Inputs!$C$3,$C${c}:$E${c}))*(1+Inputs!$C$3)^(0+1))"


def test_reductions_inside_an_expression_keep_their_own_parentheses(tmp_path):
    from boki.lib import irr, levelized, npv, xnpv
    m = b.Model("ratio", start="2027-01", periods=3, step=year)
    cash = m.series("cash", b.by_year({0: -40, 1: 50, 2: 60}))
    cost = m.series("cost", b.by_year({0: 30, 1: 20, 2: 25}))
    energy = m.series("energy", b.by_year({0: 10, 1: 11, 2: 12}))
    rate = m.input("rate", 0.1)
    by_year = m.series("rate by year", 0.1 + 0.02 * m.t)
    a = m.input("a", 7.0)
    exprs = {
        "a / npv at 0": a / npv(cash, rate, at=0),
        "a / npv at 0 with initial": a / npv(cash, rate, at=0, initial=-10),
        "a / npv by year at 1": a / npv(cash, by_year, at=1),
        "a / npv by year": a / npv(cash, by_year, initial=-10),
        "npv squared": npv(cost, rate, at=1) ** 2,
        "a / levelized": a / levelized(cost, energy, rate),
        "a - irr": a - irr(cash),
        "a / xnpv": a / xnpv(cash, rate, m.date),
        "a / sum": a / cash.sum(),
    }
    nodes = {label: m.series(label, x) for label, x in exprs.items()}
    r = m.render()
    path = tmp_path / "ratio.xlsx"
    r.to_excel(path, style=b.styles.plain)
    got = recalc(path)
    import openpyxl
    ws = openpyxl.load_workbook(path)["Model"]
    for label, node in nodes.items():
        assert got[("MODEL", f"C{_row(ws, label)}")] == pytest.approx(r[node]), (label, ws[f"C{_row(ws, label)}"].value)


def test_plain_cash_flow_includes_fx(tmp_path):
    import openpyxl

    m = b.Model("fx", start=0, periods=2, step=year)
    co = m.entity("Co", standard=b.USGAAP, currency=USD)
    co.bs.opening(cash=100 * USD)
    foreign_cash = co.bs.other_asset("Foreign cash", opening=20 * USD)
    co.journal("FX revaluation", 10 * USD, debit=co.bs.cash, credit=foreign_cash, cf="fx")
    r = m.render()
    path = tmp_path / "fx.xlsx"
    r.to_excel(path, style=b.styles.plain)
    wb = openpyxl.load_workbook(path)
    ws = wb["Co CF"]
    labels = [(c.value or "").strip() for c in ws["A"]]

    assert "fx cash flow" in labels
    got = recalc(path)
    row = _row(ws, "net change in cash")
    assert got[("CO CF", f"C{row}")] == pytest.approx(r[co.bs.cash][0] - r[co.bs.cash.opening][0]) == 10


def test_deep_shared_expressions_are_shortened_with_bounded_time(tmp_path):
    import time
    import openpyxl
    from boki import excel

    m = b.Model("deep", start=0, periods=3, step=year)
    growth = m.input("growth", 0.01)
    value = m.series("base", 2.0)
    for _ in range(18):
        value = value + value * growth
    result = m.series("result", value)
    r = m.render()
    path = tmp_path / "deep.xlsx"
    started = time.perf_counter()
    r.to_excel(path, style=b.styles.plain)
    elapsed = time.perf_counter() - started
    got = recalc(path)
    ws = openpyxl.load_workbook(path)["Model"]
    formulas_in_model = [c.value for row in ws.iter_rows() for c in row if c.data_type == "f"]

    assert elapsed < 5
    assert max(map(len, formulas_in_model)) <= excel.MAX_FORMULA
    assert got[("MODEL", f"C{_row(ws, 'result')}")] == pytest.approx(r[result])


def test_placed_input_row_applies_sign_and_scale(tmp_path):
    import openpyxl

    m = b.Model("input row", start=0, periods=3, step=year)
    amount = m.input("amount", 1500.0)
    r = m.render()
    path = tmp_path / "input-row.xlsx"
    r.to_excel(path, style=b.styles.plain, sheets=[b.sheet("Plan", [b.row(amount, sign=-1, scale=1000)])])
    wb = openpyxl.load_workbook(path)
    ws = wb["Plan"]
    got = recalc(path)

    assert got[("PLAN", f"C{_row(ws, 'amount')}")] == pytest.approx(-1.5)


@pytest.mark.parametrize("name", ["inputs", "model", "checks"])
def test_reserved_sheet_names_are_case_insensitive(name):
    with pytest.raises(ValueError, match="workbook's own sheet"):
        b.sheet(name, [])


def test_sheet_names_that_differ_only_by_case_are_rejected(tmp_path):
    m = b.Model("sheets", start=0, periods=2, step=year)
    first = m.series("first", 1)
    second = m.series("second", first + 1)

    with pytest.raises(ValueError, match="two sheets are named"):
        m.render().to_excel(tmp_path / "duplicate.xlsx", style=b.styles.plain,
                            sheets=[b.sheet("Plan", [first]), b.sheet("plan", [second])])


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_literals_are_written_as_values(tmp_path, value):
    m = b.Model("nonfinite", start=0, periods=2, step=year)
    m.series("value", value)
    report = m.render().to_excel(tmp_path / "nonfinite.xlsx", style=b.styles.plain)

    assert report.formulas == 0 and report.values == 1


def test_several_spreads_summed_in_a_row_get_rows_of_their_own(tmp_path):
    import openpyxl
    from boki import excel
    from boki.lib import macrs
    m = b.Model("d", start=0, periods=20, step=year)
    capex = m.input("capex", b.by_year({0: 100.0, 3: 50.0}, default=0.0))
    tax_depreciation = m.series("tax depreciation", sum(capex.spread(macrs(k)) for k in (5, 7, 15)))
    r = m.render()
    r.to_excel(tmp_path / "d.xlsx", style=b.styles.plain)
    ws = openpyxl.load_workbook(tmp_path / "d.xlsx")["Model"]
    row = _row(ws, "tax depreciation")
    assert all(len(ws.cell(row, c).value) <= excel.MAX_FORMULA for c in range(3, 23))
    assert recalc(tmp_path / "d.xlsx")[("MODEL", f"V{row}")] == pytest.approx(r[tax_depreciation][19])


def test_a_group_with_goodwill_and_fair_value_adjustments_recalculates_in_excel(tmp_path):
    import openpyxl

    m = b.Model("S3 acquisition", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=USD)
    sub = m.entity("Sub", standard=b.JGAAP, currency=USD, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * USD)
    land = sub.bs.other_asset("Land", opening=200 * USD)
    plant = sub.bs.other_asset("Plant", opening=300 * USD)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=600 * USD,
              fair_value={land: 100 * USD, plant: (50 * USD, 5 * year)}, tax_basis="carryover",
              nci="proportionate", goodwill_life=10 * year)
    result = m.render()
    path = tmp_path / "s3-acquisition.xlsx"

    report = result.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    bs = wb["Group BS"]

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    assert [got[("GROUP BS", f"{col}{_row(bs, 'Goodwill')}")] for col in "CD"] == pytest.approx([104.4, 92.8])
    assert [got[("GROUP BS", f"{col}{_row(bs, 'Plant')}")] for col in "CD"] == pytest.approx([340, 330])


def test_s8_translated_group_statements_recalculate_in_excel(tmp_path):
    import openpyxl
    from boki.units import JPY, USD, year

    m = b.Model("S8 foreign operation", start=0, periods=2, step=year)
    m.fx(USD, JPY,
         closing=m.series("USD/JPY closing", data={0: 150, 1: 160}, unit=JPY / USD),
         average=m.series("USD/JPY average", data={0: 145, 1: 155}, unit=JPY / USD),
         opening=150)
    parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
    sub = m.entity("US Inc.", standard=b.IFRS, currency=USD)
    parent.bs.opening(cash=15_000 * JPY)
    sub.bs.opening(cash=100 * USD)
    sub.pl.revenue("Profit", m.series("US profit", 10 * USD))
    group = m.group("Group", parent=parent)
    group.own(sub, 1, since=0, method="consolidate", consideration=15_000 * JPY)
    result = m.render()
    path = tmp_path / "s8-foreign-operation.xlsx"

    report = result.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)
    income, balance, cash_flow = wb["Group IS"], wb["Group BS"], wb["Group CF"]

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    assert [got[("GROUP IS", f"{col}{_row(income, 'Profit for the year')}")] for col in "CD"] == \
        pytest.approx([1_450, 1_550])
    assert [got[("GROUP BS", f"{col}{_row(balance, 'Cash and cash equivalents')}")] for col in "CD"] == \
        pytest.approx([16_500, 19_200])
    assert [got[("GROUP CF", f"{col}{_row(cash_flow, 'Effect of exchange rates')}")] for col in "CD"] == \
        pytest.approx([50, 1_150])


def test_s6_fixed_asset_trade_recalculates_in_excel(tmp_path):
    import openpyxl

    m = b.Model("S6 asset trade", start=0, periods=2, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    sub = m.entity("Sub", standard=b.JGAAP, currency=JPY, tax_rate=0.3)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    parent.pl.revenue("Machine", data={0: 200 * JPY}, counterparty=sub.bs.fixed_asset,
                      margin=0.25, life=5 * year)
    parent.pl.cogs("Machine production cost", {0: 150 * JPY})
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
              goodwill_life=10 * year)

    result = m.render()
    path = tmp_path / "s6-asset-trade.xlsx"
    report = result.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    for sheet, label, values in (
        ("Sub BS", "Machine (Parent)", [160, 120]),
        ("Group BS", "Machine (Parent)", [120, 90]),
    ):
        row = _row(wb[sheet], label)
        assert [got[(sheet.upper(), f"{col}{row}")] for col in "CD"] == pytest.approx(values)


def test_a_group_after_loss_of_control_recalculates_in_excel(tmp_path):
    import openpyxl
    from boki.units import JPY

    m = b.Model("S4 loss of control", start=0, periods=3, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = m.entity("Sub", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=1_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 100 * JPY)
    group = m.group("Group", parent=parent)
    group.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY,
              goodwill_life=10 * year)
    group.own(sub, 0.4, since=2, method="equity", proceeds=300 * JPY)

    result = m.render()
    path = tmp_path / "s4-loss-of-control.xlsx"
    report = result.to_excel(path)
    got = recalc(path)
    wb = openpyxl.load_workbook(path)

    assert report.values == 0 and report.formulas > 0
    assert got[("CHECKS", "B5")] == "OK"
    for sheet, label, values in (
        ("Group IS", "Net income", result.pl(group).row("Net income")),
        ("Group BS", "Noncontrolling interests", result.bs(group).row("Noncontrolling interests")),
        ("Group CF", "Cash flow from investing",
         result.cf(group).row("Cash flow from investing")),
    ):
        for period, want in enumerate(values):
            cell = f"{chr(67 + period)}{_row(wb[sheet], label)}"
            assert got[(sheet.upper(), cell)] == pytest.approx(want)


@pytest.mark.parametrize("collect", [None, {0: 50 * JPY, 2: 150 * JPY}])
def test_opening_receivable_and_payable_collections_recalculate(tmp_path, collect):
    import openpyxl
    from boki.units import month
    m = b.Model("opening", start="2027-01", periods=6, step=month)
    co = m.entity("Co", standard=b.JGAAP, currency=JPY)
    co.bs.opening(cash=1000 * JPY)
    sales = co.pl.revenue("sales", 100 * JPY / month, settle=b.mix({b.delay(0): 0.25, b.delay(2): 0.75}),
                          opening=200 * JPY, opening_collect=collect)
    co.pl.cogs("purchases", 40 * JPY / month, settle=b.delay(2), opening=60 * JPY)
    r = m.render()
    report = r.to_excel(tmp_path / "o.xlsx", style=b.styles.plain)
    if collect is None:
        assert report.values == 0                                 # the collections are formulas, not typed values
    got = recalc(tmp_path / "o.xlsx")
    wb = openpyxl.load_workbook(tmp_path / "o.xlsx")
    for label in ("Accounts receivable", "Accounts payable", "Cash"):
        want = r.bs(co).row(label)
        row = _row(wb["Co BS"], label)
        for t, w in enumerate(want):
            assert math.isclose(got[("CO BS", f"{chr(67 + t)}{row}")], w, abs_tol=1e-9), (label, t)
    assert r.bs(co).row("Accounts receivable")[0] != 0


def test_ebitda_built_from_the_parts_recalculates_in_excel(tmp_path):
    import openpyxl
    m = b.Model("parts", start=0, periods=4, step=year)
    co = m.entity("Co", standard=b.JGAAP, currency=JPY)
    co.bs.opening(cash=1_000 * JPY)
    co.pl.revenue("sales", 500 * JPY)
    co.pl.sga("rent", 50 * JPY, category="Rent")
    co.bs.fixed_asset("press", 40 * JPY, at=0, life=4 * year, category="Lease costs")
    co.bs.intangible("licence", 20 * JPY, at=0, life=2 * year)
    co.bs.construction("plant", spend=30 * JPY, complete_at=1, life=3 * year)
    ebitda = m.series("EBITDA", co.operating_income + co.depreciation + co.amortization)
    covenant = m.series("Covenant EBITDA", ebitda - 5 * JPY)
    r = m.render()
    assert r[ebitda] == pytest.approx([450] * 4)
    report = r.to_excel(tmp_path / "parts.xlsx")
    assert report.values == 0                                   # live formulas, no pasted values
    got = recalc(tmp_path / "parts.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "parts.xlsx")["Model"]
    for label, series in (("EBITDA", ebitda), ("Covenant EBITDA", covenant)):
        row = _row(ws, label)
        assert str(ws.cell(row, 3).value).startswith("=")
        assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(4)] == pytest.approx(r[series])


def test_a_group_s_ebitda_parts_recalculate_in_excel(tmp_path):
    import openpyxl
    m = b.Model("gparts", start=0, periods=3, step=year)
    parent = m.entity("Parent", standard=b.JGAAP, currency=JPY)
    sub = m.entity("Sub", standard=b.JGAAP, currency=JPY)
    parent.bs.opening(cash=3_000 * JPY)
    sub.bs.opening(cash=500 * JPY)
    sub.pl.revenue("Sales", 300 * JPY)
    sub.bs.fixed_asset("Machine", 60 * JPY, at=0, life=3 * year)
    parent.pl.revenue("Fees", 100 * JPY)
    g = m.group("Group", parent=parent)
    g.own(sub, method="consolidate", consideration=1_000 * JPY, goodwill_life=10 * year)
    ebitda = m.series("Group EBITDA", g.operating_income + g.depreciation + g.amortization)
    r = m.render()
    assert r[g.amortization][1] == pytest.approx(50)                        # goodwill 500 over 10 years
    report = r.to_excel(tmp_path / "gparts.xlsx")
    assert report.values == 0
    got = recalc(tmp_path / "gparts.xlsx")
    ws = openpyxl.load_workbook(tmp_path / "gparts.xlsx")["Model"]
    row = _row(ws, "Group EBITDA")
    assert [got[("MODEL", f"{chr(67 + t)}{row}")] for t in range(3)] == pytest.approx(r[ebitda])


# -- circular references boki does not have ------------------------------------------------------------------
# boki reads each (series, period) it needs and only the branch of a where that is taken; Excel's dependency
# graph counts every reference in a formula. A model can be acyclic in boki and circular in Excel.

def _formula_cells(r, path):
    """(label, period, formula, boki's value, Excel's value) for every formula cell on the Model sheet."""
    import openpyxl
    from boki import excel
    got = recalc(path)
    ws = openpyxl.load_workbook(path)["Model"]
    w = excel._Writer(r)
    w.plan()
    out = []
    for row in w.rows:
        for t in range(1 if row.node.scalar else w.n):
            cell = ws.cell(row.number, excel.FIRST_COL + t)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                want = r._r.value(row.node, None if row.node.scalar else t)
                out.append((row.label.strip(), t, cell.value, want, got.get(("MODEL", cell.coordinate))))
    return out


def _sculpted_toll_road():
    """A toll concession: CFADS includes the equity and debt drawn in construction, the drawdown includes a fee on
    the debt commitment, and the commitment is sized on the NPV of CFADS over the debt period. The debt period
    depends on an input (the opening year), so boki reads CFADS only in the debt years: no cycle. Excel sees the
    CFADS of the construction years in the IF that masks them, and fee -> commitment -> NPV -> CFADS."""
    m = b.Model("toll", start="2020", periods=8, step=year)
    calendar = m.date.year
    start = m.input("construction start", 2020)
    opening = m.input("opening year", 2022)
    building = (calendar >= start) & (calendar < opening)
    operating = calendar >= opening
    debt_period = operating & (calendar < opening + 4)
    rate = m.input("debt rate", 0.05)
    capex = m.series("capex", (60 * USD).where(building, 0 * USD))
    revenue = m.series("net revenue", (40 * USD).where(operating, 0 * USD))
    commitment = m.series("debt commitment")
    fee = m.series("arrangement fee", (0.02 * commitment).where(calendar == start, 0 * USD))
    drawdown = m.series("drawdown", (0.7 * (capex + fee)).where(building, 0 * USD))
    equity = m.series("equity", (0.3 * (capex + fee)).where(building, 0 * USD))
    cfads = m.series("CFADS", revenue - capex + equity + drawdown - fee)
    factor = m.series("debt discount factor", (1 + rate) ** -(calendar - opening + 1))
    cfads_npv = m.series("NPV of CFADS", (cfads * factor).where(debt_period, 0 * USD).sum())
    commitment.define(cfads_npv / 1.3)
    return m, opening, cfads_npv


def test_a_branch_boki_never_reads_is_guarded_where_excel_would_be_circular(tmp_path):
    import openpyxl
    from boki.excel import CircularReferenceWarning
    m, opening, cfads_npv = _sculpted_toll_road()
    r = m.render()
    path = tmp_path / "toll.xlsx"
    with pytest.warns(CircularReferenceWarning, match="8 cells"):
        report = r.to_excel(path)
    # one cell per period breaks each loop: there are eight periods, each with its own loop through the commitment
    assert report.guarded == 8 and report.values == 0
    cells = _formula_cells(r, path)
    wrong = [(label, t, f, want, got) for label, t, f, want, got in cells
             if not isinstance(got, (int, float)) or not math.isclose(got, want, abs_tol=1e-9)]
    assert not wrong, wrong[:5]                                  # every cell recalculates: no circular reference
    ws = openpyxl.load_workbook(path)["Model"]
    guarded = [(label, t, f) for label, t, f, _, _ in cells if "NA()" in f]
    assert len(guarded) == 8
    for label, t, f in guarded:
        assert f.startswith("=IF(")                              # the condition stays live
    first = next(ws.cell(row, col) for row in range(1, ws.max_row + 1) for col in range(3, 11)
                 if "NA()" in str(ws.cell(row, col).value))
    assert "circular" in first.comment.text and first.fill.fgColor.rgb.endswith("FCE4D6")
    # IFs that close no loop keep both branches
    capex_row = _row(ws, "capex")
    assert all(",60,0)" in ws.cell(capex_row, 3 + t).value for t in range(8))
    # the same model gives the same workbook
    again = tmp_path / "again.xlsx"
    with pytest.warns(CircularReferenceWarning):
        r.to_excel(again)
    assert [f for _, _, f, _, _ in _formula_cells(r, again)] == [f for _, _, f, _, _ in cells]


def test_a_guarded_cell_shows_na_when_a_changed_input_takes_the_other_branch(tmp_path):
    import warnings
    import openpyxl
    m, opening, cfads_npv = _sculpted_toll_road()
    path = tmp_path / "toll.xlsx"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m.render().to_excel(path)
    wb = openpyxl.load_workbook(path)
    inputs = wb["Inputs"]
    k = next(i for i in range(1, inputs.max_row + 1) if inputs.cell(i, 1).value == "opening year")
    inputs.cell(k, 3).value = 2023                               # the debt period moves a year later
    wb.save(path)
    moved = m.render(inputs={opening: 2023})
    cells = _formula_cells(moved, path)
    # never a wrong number: each cell is boki's value for the new input, or #N/A where a guard was hit
    for label, t, f, want, got in cells:
        if isinstance(got, (int, float)):
            assert math.isclose(got, want, abs_tol=1e-9), (label, t, f, want, got)
        else:
            assert "#N/A" in str(got), (label, t, f, got)
    assert any("#N/A" in str(got) for *_, got in cells if not isinstance(got, (int, float)))


def test_an_index_over_a_row_reads_one_cell_where_the_whole_row_would_be_circular(tmp_path):
    from boki.excel import CircularReferenceWarning
    m = b.Model("cod", start=0, periods=6, step=year)
    cod = m.input("COD period", 2)
    balance = m.series("balance")
    draw = m.series("draw", (100 * USD).where(m.t <= cod, 0 * USD))
    repay = m.series("repayment", (balance[cod] / 3).where(m.t > cod, 0 * USD))
    balance.define(balance.lag(1, fill=0 * USD) + draw - repay)
    r = m.render()
    assert r[balance] == pytest.approx([100, 200, 300, 200, 100, 0])
    path = tmp_path / "cod.xlsx"
    with pytest.warns(CircularReferenceWarning):
        report = r.to_excel(path)
    assert report.guarded == 6
    cells = _formula_cells(r, path)
    wrong = [c for c in cells if not isinstance(c[4], (int, float)) or not math.isclose(c[4], c[3], abs_tol=1e-9)]
    assert not wrong, wrong[:5]
    repayments = [f for label, t, f, _, _ in cells if label == "repayment"]
    assert all("INDEX(" not in f for f in repayments[3:])        # the balance at COD, guarded by the input
    assert all("NA()" in f for f in repayments)


def test_an_acyclic_model_gets_no_guards_and_no_warning(tmp_path):
    import warnings
    m = b.Model("plain", start=0, periods=4, step=year)
    switch = m.input("switch year", 2)
    x = m.series("x", (10 * USD).where(m.t >= switch, 5 * USD))
    m.series("total", x.where(m.t < switch, 0 * USD).sum())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = m.render().to_excel(tmp_path / "plain.xlsx")
    assert report.guarded == 0
