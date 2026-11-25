"""Tests for IB-grade Excel features: verified rewrites, blocks, panels, live scenarios, and Model omission."""
from __future__ import annotations

import openpyxl
import pytest

import boki as b
from boki.units import USD, year


def _recalc(path) -> dict[tuple[str, str], object]:
    import formulas

    xl = formulas.ExcelModel().loads(str(path)).finish()
    sol = xl.calculate()
    out = {}
    for key, rng in sol.items():
        k = str(key).upper()
        if "!" not in k or ":" in k.split("!")[1]:
            continue
        sheet, cell = k.split("]", 1)[1].split("'!")
        out[(sheet.strip("'"), cell)] = rng.value[0, 0]
    return out


def _row(ws, label: str) -> int:
    return next(r for r in range(1, ws.max_row + 1) if (ws.cell(r, 1).value or "").strip() == label)


recalc = _recalc


def _verified_3stmt():
    """Minimal airtight 3-statement model (1 actual + 3 forecast years) with AR, AP, PP&E, Tax, Dividends."""
    m = b.Model("MiniCo", start="2024", periods=4, step=year, actual_until="2024")
    co = m.entity("MiniCo", standard=b.USGAAP, currency=USD)

    rev_growth = m.input(
        "Revenue growth", 0.10,
        scenarios={"Bull": 0.18, "Bear": 0.03},
        source="Consensus estimates",
    )
    cogs_pct = m.input(
        "COGS % of revenue", 0.45,
        scenarios={"Bull": 0.42, "Bear": 0.49},
        source="FY2024 10-K",
    )
    sga_pct = m.input("SG&A % of revenue", 0.25, scenarios={"Bull": 0.23, "Bear": 0.27}, source="FY2024 10-K")
    ar_pct = m.input("AR % of revenue", 0.10, source="FY2024 10-K")
    ap_pct = m.input("AP % of COGS", 0.10, source="FY2024 10-K")
    capex_pct = m.input("CapEx % of revenue", 0.08, source="Management guidance")
    tax_rate = m.input("Tax rate", 0.25, source="Statutory rate")
    payout = m.input("Dividend payout", 0.20, source="Board policy")

    rev_fcst = m.series("Revenue forecast")
    rev = co.pl.revenue("Revenue", rev_fcst, actuals={"2024": 100 * USD})
    rev_fcst.define(rev.lag(1) * (1 + rev_growth))
    cogs = co.pl.cogs("COGS", rev * cogs_pct, actuals={"2024": 45 * USD})
    sga = co.pl.sga("SG&A", rev * sga_pct, actuals={"2024": 25 * USD})

    # Fixed asset via boki's fixed_asset program (adds CapEx + depreciation cleanly)
    capex = m.series("CapEx", (rev * capex_pct).where(m.is_forecast, 0 * USD))
    ppe = co.bs.fixed_asset("PP&E", cost=capex, life=10 * year, actuals={"2024": 80 * USD})

    # Working capital accounts tied to AR% and AP% via target balances
    ar = co.bs.other_asset("Accounts receivable", target=rev * ar_pct, cf="operating", actuals={"2024": 10 * USD})
    ap = co.bs.other_liability("Accounts payable", target=cogs * ap_pct, cf="operating", actuals={"2024": 4.5 * USD})

    tax = co.pl.income_tax("Income tax", rate=tax_rate, base=co.pl.pretax_income, nol=False,
                           actuals={"2024": 5.5 * USD})
    div_amt = m.series("Dividends", (co.pl.net_income * payout).where(m.is_forecast, 0 * USD))
    div = co.bs.dividend("Dividends", div_amt)

    # 2024A BS: Cash 30 + AR 10 + PP&E 80 = 120; AP 4.5 + Equity(Common 50 + RE 65.5) = 120
    common = co.bs.capital("Common stock", actuals={"2024": 50 * USD})
    co.load_actuals({
        co.bs.cash: {"2024": 30 * USD},
        co.bs.retained_earnings: {"2024": 65.5 * USD},
    })

    return m, dict(
        co=co, rev=rev, cogs=cogs, sga=sga, ppe=ppe, capex=capex, ar=ar, ap=ap,
        tax=tax, div=div_amt, common=common, rev_growth=rev_growth,
    )


def test_verified_formula_rewrite_passes_and_catches_subtle_mismatch(tmp_path):
    m = b.Model("Rewrite", start="2025", periods=3, step=year)
    x = m.input("X", 10.0)
    y = m.input("Y", 5.0)
    z = m.series("Z", (x + y) * 2)
    r = m.render()

    # Exact rewrite passes perturbation check
    ok_path = tmp_path / "ok.xlsx"
    r.to_excel(ok_path, sheets=[b.sheet("Main", [b.row(z, formula=2 * x + 2 * y)])])
    got = recalc(ok_path)
    ws = openpyxl.load_workbook(ok_path)["Main"]
    assert got[("MAIN", f"C{_row(ws, 'Z')}")] == pytest.approx(30)

    # Coincidentally equal on base (30 == 3 * 10), fails under input perturbation!
    with pytest.raises(b.EquivalenceError, match="mismatch"):
        r.to_excel(tmp_path / "bad.xlsx", sheets=[b.sheet("Main", [b.row(z, formula=3 * x)])])

    # verify="base" allows base-only match
    base_path = tmp_path / "base.xlsx"
    r.to_excel(base_path, sheets=[b.sheet("Main", [b.row(z, formula=3 * x, verify="base")])])
    assert base_path.exists()

    # verify="off" skips check completely
    off_path = tmp_path / "off.xlsx"
    r.to_excel(off_path, sheets=[b.sheet("Main", [b.row(z, formula=x * 99, verify="off")])])
    assert off_path.exists()


def test_verified_block_indirect_cf_and_error_on_omission(tmp_path):
    m, d = _verified_3stmt()
    co = d["co"]
    da = co.depreciation
    d_ar = m.series("Change in AR", (-(d["ar"] - d["ar"].lag(1, fill=0 * USD))).where(m.is_forecast, 0 * USD))
    d_ap = m.series("Change in AP", (d["ap"] - d["ap"].lag(1, fill=0 * USD)).where(m.is_forecast, 0 * USD))
    ni_fcst = m.series("Net income (CF)", co.pl.net_income.where(m.is_forecast, 0 * USD))
    da_fcst = m.series("D&A (CF)", da.where(m.is_forecast, 0 * USD))

    r = m.render()

    # Missing d_ap fails verification
    bad_sheets = [
        b.sheet("CF", [
            b.section("Operating", [
                b.block(co.cf.operating, [ni_fcst, da_fcst, d_ar], label="Cash flow from operations"),
            ]),
        ]),
    ]
    with pytest.raises(b.EquivalenceError, match="Cash flow from operations"):
        r.to_excel(tmp_path / "bad_cf.xlsx", sheets=bad_sheets)

    # Complete indirect CF block passes verification and writes =SUM(...)
    ok_sheets = [
        b.sheet("CF", [
            b.section("Operating", [
                b.block(co.cf.operating, [ni_fcst, da_fcst, d_ar, d_ap], label="Cash flow from operations"),
            ]),
        ]),
    ]
    ok_path = tmp_path / "ok_cf.xlsx"
    report = r.to_excel(ok_path, sheets=ok_sheets)
    assert report.values == 0
    wb = openpyxl.load_workbook(ok_path)
    ws_cf = wb["CF"]
    cfo_row = _row(ws_cf, "Cash flow from operations")
    assert ws_cf[f"D{cfo_row}"].value.startswith("=SUM(")
    got = recalc(ok_path)
    assert [got[("CF", f"{c}{cfo_row}")] for c in "DEF"] == pytest.approx(r[co.cf.operating][1:])


def test_panel_live_formulas_recalculate(tmp_path):
    m = b.Model("Valuation", start="2025", periods=3, step=year)
    co = m.entity("ValCo", standard=b.USGAAP, currency=USD)
    rev = co.pl.revenue("Revenue", m.input("Revenue", 200 * USD))
    ebitda = m.series("EBITDA", rev * m.input("Margin", 0.25))
    mult = m.input("Exit multiple", 10.0)
    ev = m.series("Enterprise value", ebitda.last() * mult)
    debt = m.input("Net debt", 100 * USD)
    eq_val = m.series("Equity value", ev - debt)

    r = m.render()
    summary = b.sheet("Summary", [
        b.section("Operating", [b.row(rev), b.row(ebitda, total=True)]),
        b.panel("Valuation Bridge", ["$mm", "x EBITDA"], [
            ("Terminal EBITDA", [ebitda.last(), 1.0], {"fmt": ["money", "multiple"]}),
            ("Enterprise Value", [ev, mult], {"total": True, "fmt": ["money", "multiple"]}),
            ("Less: Net Debt", [-debt, -debt / ebitda.last()], {"fmt": ["money", "multiple"]}),
            ("Implied Equity Value", [eq_val, eq_val / ebitda.last()], {"total": "grand", "fmt": ["money", "multiple"]}),
        ]),
    ])
    path = tmp_path / "panel.xlsx"
    report = r.to_excel(path, sheets=[summary], statements=False, checks=False, omit_unused_model=True)
    assert report.values == 0
    wb = openpyxl.load_workbook(path)
    assert "Model" not in wb.sheetnames
    ws = wb["Summary"]
    ev_r = _row(ws, "Enterprise Value")
    eq_r = _row(ws, "Implied Equity Value")
    assert str(ws[f"C{ev_r}"].value).startswith("=")
    assert str(ws[f"C{eq_r}"].value).startswith("=")
    got = recalc(path)
    assert got[("SUMMARY", f"C{ev_r}")] == pytest.approx(500.0)
    assert got[("SUMMARY", f"C{eq_r}")] == pytest.approx(400.0)
    assert got[("SUMMARY", f"D{eq_r}")] == pytest.approx(8.0)


def test_live_excel_scenario_switch_and_zero_model_sheet(tmp_path):
    m, d = _verified_3stmt()
    co = d["co"]
    da = co.depreciation
    d_ar = m.series("Change in AR", (-(d["ar"] - d["ar"].lag(1, fill=0 * USD))).where(m.is_forecast, 0 * USD))
    d_ap = m.series("Change in AP", (d["ap"] - d["ap"].lag(1, fill=0 * USD)).where(m.is_forecast, 0 * USD))
    ni_fcst = m.series("Net income (CF)", co.pl.net_income.where(m.is_forecast, 0 * USD))
    da_fcst = m.series("D&A (CF)", da.where(m.is_forecast, 0 * USD))
    neg_capex = m.series("Capital expenditures", (-d["capex"]).where(m.is_forecast, 0 * USD))
    neg_div = m.series("Dividends paid", (-d["div"]).where(m.is_forecast, 0 * USD))
    net_cash_chg = m.series("Net change in cash", co.cf.operating + co.cf.investing + co.cf.financing)
    beg_cash = m.series("Beginning cash", co.bs.cash.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))
    end_cash = m.series("Ending cash", (beg_cash + net_cash_chg).where(m.is_forecast, co.bs.cash))

    ebit_row = b.row(co.pl.operating_income, "Operating income (EBIT)", total=True)
    ni_row = b.row(co.pl.net_income, "Net income", total="grand")
    gross_margin = m.series("Gross margin", co.pl.gross_profit / d["rev"])

    sheets = [
        b.sheet("IS", [
            b.section("Income Statement", [
                b.row(d["rev"], "Revenue"),
                b.row(d["cogs"], "Cost of goods sold", sign=-1),
                b.row(co.pl.gross_profit, "Gross profit", total=True),
                b.row(gross_margin, "% margin", fmt="percent"),
                b.row(d["sga"], "SG&A", sign=-1),
                b.row(da, "Depreciation & amortization", sign=-1),
                ebit_row,
                b.row(d["tax"], "Income tax", sign=-1),
                ni_row,
            ]),
        ]),
        b.sheet("BS", [
            b.section("Assets", [
                b.row(co.bs.cash, "Cash", formula=end_cash),
                b.row(d["ar"], "Accounts receivable"),
                b.row(d["ppe"], "PP&E, net"),
                b.row(co.bs.total_assets, "Total assets", total="grand"),
            ]),
            b.section("Liabilities & Equity", [
                b.row(d["ap"], "Accounts payable"),
                b.row(co.bs.total_liabilities, "Total liabilities", total=True),
                b.row(d["common"], "Common stock"),
                b.row(
                    co.bs.retained_earnings,
                    "Retained earnings",
                    formula=co.bs.retained_earnings.lag(1, fill=0 * USD) + co.pl.net_income - d["div"],
                ),
                b.row(co.bs.total_equity, "Total equity", total=True),
                b.row(
                    m.series("Total liabilities & equity", co.bs.total_liabilities + co.bs.total_equity),
                    "Total liabilities & equity",
                    total="grand",
                ),
            ]),
        ]),
        b.sheet("CF", [
            b.section("Operating Activities", [
                b.block(co.cf.operating, [ni_fcst, da_fcst, d_ar, d_ap], label="Cash flow from operations"),
            ]),
            b.section("Investing Activities", [
                b.block(co.cf.investing, [neg_capex], label="Cash flow from investing"),
            ]),
            b.section("Financing Activities", [
                b.block(co.cf.financing, [neg_div], label="Cash flow from financing"),
            ]),
            b.section("Cash Reconciliation", [
                b.row(net_cash_chg, "Net change in cash", total=True),
                b.row(beg_cash, "Beginning cash"),
                b.row(end_cash, "Ending cash", total="grand"),
            ]),
        ]),
    ]

    r_base = m.render()
    path = tmp_path / "minico_ib.xlsx"
    report = r_base.to_excel(
        path,
        sheets=sheets,
        scenarios=["Base", "Bull", "Bear"],
        statements=False,
        checks=True,
        omit_unused_model=True,
    )
    assert report.values == 0
    assert report.unplaced == []

    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Inputs", "IS", "BS", "CF", "Checks"]
    assert "Model" not in wb.sheetnames

    # Check Inputs sheet has Active Case switch and Source column
    ws_in = wb["Inputs"]
    assert ws_in["C3"].value == 1
    assert ws_in["C6"].value.startswith("=INDEX(")
    assert ws_in["G5"].value == "Source"
    assert any(ws_in.cell(r, 7).value == "Consensus estimates" for r in range(6, ws_in.max_row + 1))

    # Check BS Cash and Retained Earnings carry rewritten IB formulas
    ws_bs = wb["BS"]
    cash_r = _row(ws_bs, "Cash")
    re_r = _row(ws_bs, "Retained earnings")
    assert ws_bs[f"C{cash_r}"].value == 30                       # 2024A actual data
    assert "CF!" in ws_bs[f"D{cash_r}"].value                    # 2025E links directly to CF!Ending cash
    assert ws_bs[f"C{re_r}"].value == 65.5                       # 2024A actual data
    assert f"C{re_r}" in ws_bs[f"D{re_r}"].value and "IS!" in ws_bs[f"D{re_r}"].value

    # Recalculate for Base (1), Bull (2), Bear (3) by flipping ONLY Inputs!$C$3!
    ws_is = wb["IS"]
    rev_r = _row(ws_is, "Revenue")
    ni_r = _row(ws_is, "Net income")
    for idx, scen in ((1, None), (2, "Bull"), (3, "Bear")):
        wb_case = openpyxl.load_workbook(path)
        wb_case["Inputs"]["C3"].value = idx
        case_path = tmp_path / f"case_{idx}.xlsx"
        wb_case.save(case_path)
        got = recalc(case_path)
        assert got[("CHECKS", "B5")] == "OK", f"Checks failed in scenario {scen or 'Base'}"
        expected = m.render(scenario=scen)
        assert [got[("IS", f"{c}{rev_r}")] for c in "CDEF"] == pytest.approx(expected[d["rev"]], rel=1e-6)
        assert [got[("IS", f"{c}{ni_r}")] for c in "CDEF"] == pytest.approx(expected[co.pl.net_income], rel=1e-6)
        assert [got[("BS", f"{c}{cash_r}")] for c in "CDEF"] == pytest.approx(expected[co.bs.cash], rel=1e-6)


def test_ib_3statement_benchmark_live_scenarios_and_zero_model_sheet(tmp_path):
    import importlib.util
    from pathlib import Path

    plan_path = Path(__file__).resolve().parents[1] / "examples/ib_3statement/plan.py"
    spec = importlib.util.spec_from_file_location("ib_3statement_plan", plan_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = tmp_path / "acme.xlsx"
    report = mod.export_ib_workbook(out)
    assert report.values == 0
    assert report.unplaced == []

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Inputs", "Summary", "IS", "BS", "CF", "Schedules", "Checks"]
    ws_is = wb["IS"]
    gp_r = _row(ws_is, "Gross profit")
    assert ws_is[f"C{gp_r}"].value == "=(C6+C8)"                # clean banker sign convention, no -(-C8)

    for idx, scen in ((1, None), (2, "Bull"), (3, "Bear")):
        wb_case = openpyxl.load_workbook(out)
        wb_case["Inputs"]["C3"].value = idx
        p = tmp_path / f"acme_{idx}.xlsx"
        wb_case.save(p)
        got = recalc(p)
        assert got[("CHECKS", "B5")] == "OK"
        expected = mod.m.render(scenario=scen)
        ws_sum = wb_case["Summary"]
        eq_r = _row(ws_sum, "Implied Equity Value")
        assert got[("SUMMARY", f"C{eq_r}")] == pytest.approx(expected[mod.implied_equity], rel=1e-6)


def test_ib_lbo_benchmark_live_scenarios_and_zero_model_sheet(tmp_path):
    import importlib.util
    from pathlib import Path

    plan_path = Path(__file__).resolve().parents[1] / "examples/ib_lbo/plan.py"
    spec = importlib.util.spec_from_file_location("ib_lbo_plan", plan_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = tmp_path / "apex_lbo.xlsx"
    report = mod.export_ib_workbook(out)
    assert report.values == 0
    assert report.unplaced == []

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Inputs", "Transaction", "Returns", "IS", "BS", "CF", "Debt", "Checks"]

    for idx, scen in ((1, None), (2, "Bull"), (3, "Bear")):
        wb_case = openpyxl.load_workbook(out)
        wb_case["Inputs"]["C3"].value = idx
        p = tmp_path / f"lbo_{idx}.xlsx"
        wb_case.save(p)
        got = recalc(p)
        assert got[("CHECKS", "B5")] == "OK"
        expected = mod.m.render(scenario=scen)
        ws_ret = wb_case["Returns"]
        irr_r = _row(ws_ret, "Sponsor IRR (5-Year Hold)")
        moic_r = _row(ws_ret, "Sponsor MoIC")
        assert got[("RETURNS", f"D{irr_r}")] == pytest.approx(expected[mod.sponsor_irr], rel=1e-6)
        assert got[("RETURNS", f"D{moic_r}")] == pytest.approx(expected[mod.sponsor_moic], rel=1e-6)


def test_ib_dcf_benchmark_live_scenarios_and_zero_model_sheet(tmp_path):
    import importlib.util
    from pathlib import Path

    plan_path = Path(__file__).resolve().parents[1] / "examples/ib_dcf/plan.py"
    spec = importlib.util.spec_from_file_location("ib_dcf_plan", plan_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out = tmp_path / "veridian_dcf.xlsx"
    report = mod.export_ib_workbook(out)
    assert report.values == 0
    assert report.unplaced == []

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Inputs", "Summary", "DCF", "Operating", "CF", "Checks"]

    for idx, scen in ((1, None), (2, "Bull"), (3, "Bear")):
        wb_case = openpyxl.load_workbook(out)
        wb_case["Inputs"]["C3"].value = idx
        p = tmp_path / f"dcf_{idx}.xlsx"
        wb_case.save(p)
        got = recalc(p)
        assert got[("CHECKS", "B5")] == "OK"
        expected = mod.m.render(scenario=scen)
        ws_sum = wb_case["Summary"]
        px_r = _row(ws_sum, "Implied Share Price ($)")
        assert got[("SUMMARY", f"C{px_r}")] == pytest.approx(expected[mod.price_pgm], rel=1e-6)
        assert got[("SUMMARY", f"D{px_r}")] == pytest.approx(expected[mod.price_emm], rel=1e-6)


def test_sensitivity_references_live_axis_headers_and_panel_cells(tmp_path):
    m = b.Model("Sens", start="2025", periods=2, step=year)
    base_ebitda = m.input("EBITDA", 100.0)
    debt = m.input("Debt", 200.0)
    ev_base = m.series("Base EV", base_ebitda * 10.0)

    sheet = b.sheet("Summary", [
        b.panel("Base Bridge", ["Value"], [
            ("Base EV", [ev_base]),
        ]),
        b.sensitivity(
            "Equity Value Sensitivity",
            [8.0, 10.0, 12.0],
            [150.0, 200.0, 250.0],
            lambda mult, d: base_ebitda * mult - d,
            fmt="number",
            row_fmt='0.0"x"',
            col_fmt="#,##0",
            highlight=(1, 1),
            corner="Mult \\ Debt",
        ),
    ])
    path = tmp_path / "sens.xlsx"
    m.render().to_excel(path, sheets=[sheet], statements=False, checks=False, omit_unused_model=True)
    wb = openpyxl.load_workbook(path)
    ws = wb["Summary"]
    hdr_r = _row(ws, "Mult \\ Debt")
    # Axis headers hold raw numbers, and matrix cells reference $A<row> and <col>$<hdr>
    assert ws[f"A{hdr_r + 2}"].value == 10.0
    assert ws[f"D{hdr_r}"].value == 200.0
    formula = ws[f"D{hdr_r + 2}"].value
    assert f"$A{hdr_r + 2}" in formula and f"D${hdr_r}" in formula

    # Changing a column header directly in Excel dynamically updates that entire column!
    ws[f"D{hdr_r}"].value = 300.0
    edited = tmp_path / "sens_edited.xlsx"
    wb.save(edited)
    got = recalc(edited)
    assert got[("SUMMARY", f"D{hdr_r + 2}")] == pytest.approx(700.0)




