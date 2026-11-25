"""Acme Industrial Corp. — Investment-Banking 3-Statement Operating Model (2022A–2029E).

Benchmark #1 for IB-grade financial modeling in boki:
- 3 historical actual years (2022A–2024A) + 5 forecast years (2025E–2029E), US GAAP, $mm.
- Historical DSO/DIO/DPO and margins flow cleanly into forecast operating drivers.
- Live Base / Bull / Bear scenario switch in Excel (Inputs!$C$3) with source provenance.
- Full indirect Cash Flow Statement via verified ``b.block`` SUM totals.
- Direct Balance Sheet links (Cash = CF!Ending Cash, Retained Earnings = Prior + NI - Dividends)
  via perturbation-verified ``b.row(..., formula=...)``.
- Executive Summary with 2D Credit & Valuation Bridge ``b.panel``.
- Zero ``Model`` sheet (``omit_unused_model=True``) and live inline ``Checks`` sheet.

Run:
    uv run python examples/ib_3statement/plan.py [out-dir]
    uv run python tools/excel_check.py examples/ib_3statement
"""
from __future__ import annotations

import sys
from pathlib import Path

import boki as b
from boki.units import USD, year

MM = 1_000_000 * USD

# ---- Model & Entity -----------------------------------------------------------------

m = b.Model("Acme Industrial Corp.", start="2022", periods=8, step=year, actual_until="2024")
co = m.entity("Acme Industrial", standard=b.USGAAP, currency=USD)

# ---- Assumptions (with live scenarios & provenance) ---------------------------------

rev_growth = m.input(
    "Revenue growth", 0.08,
    scenarios={"Bull": 0.125, "Bear": 0.03},
    source="Equity research consensus",
)
cogs_pct = m.input(
    "COGS % of revenue", 0.57,
    scenarios={"Bull": 0.555, "Bear": 0.595},
    source="FY2024 10-K & guidance",
)
sga_pct = m.input(
    "SG&A % of revenue", 0.185,
    scenarios={"Bull": 0.175, "Bear": 0.20},
    source="FY2024 10-K p.38",
)
rd_pct = m.input(
    "R&D % of revenue", 0.045,
    scenarios={"Bull": 0.045, "Bear": 0.045},
    source="Management R&D target",
)
dso_days = m.input("DSO (days)", 45.0, source="3-yr historical avg (45.2d)")
dio_days = m.input("DIO (days)", 60.0, source="3-yr historical avg (59.9d)")
dpo_days = m.input("DPO (days)", 38.0, source="3-yr historical avg (37.9d)")
capex_pct = m.input(
    "CapEx % of revenue", 0.055,
    scenarios={"Bull": 0.06, "Bear": 0.045},
    source="FY2024 10-K capex plan",
)
depr_rate = m.input("Depreciation % of opening PP&E", 0.12, source="8.3-yr implied useful life")
debt_rate = m.input("Term loan interest rate", 0.065, source="Credit agreement (SOFR + 225bps)")
mandatory_amort = m.input("Term loan mandatory amortization", 15.0 * MM, source="Senior credit facility")
tax_rate = m.input("Effective tax rate", 0.24, source="US federal 21% + state 3%")
payout_ratio = m.input("Dividend payout ratio", 0.25, source="Board capital return policy")
exit_multiple = m.input(
    "Exit EV / EBITDA multiple", 9.5,
    scenarios={"Bull": 11.0, "Bear": 8.0},
    source="Industrial peers median",
)

# ---- Income Statement & Supporting Schedules ---------------------------------------

rev_fcst = m.series("Revenue forecast")
revenue = co.pl.revenue(
    "Revenue",
    rev_fcst,
    actuals={"2022": 400.0 * MM, "2023": 440.0 * MM, "2024": 485.0 * MM},
)
rev_fcst.define(revenue.lag(1) * (1 + rev_growth))

cogs = co.pl.cogs(
    "Cost of goods sold",
    revenue * cogs_pct,
    actuals={"2022": 232.0 * MM, "2023": 253.0 * MM, "2024": 276.5 * MM},
)
sga = co.pl.sga(
    "Selling, general & administrative",
    revenue * sga_pct,
    actuals={"2022": 76.0 * MM, "2023": 82.0 * MM, "2024": 89.7 * MM},
)
rd = co.pl.sga(
    "Research & development",
    revenue * rd_pct,
    actuals={"2022": 18.0 * MM, "2023": 20.0 * MM, "2024": 21.8 * MM},
)

# PP&E rollforward: Opening + CapEx - D&A = Closing
ppe = co.bs.other_asset(
    "PP&E, net",
    cf="investing",
    actuals={"2022": 165.0 * MM, "2023": 173.5 * MM, "2024": 182.0 * MM},
)
capex = m.series("Capital expenditures", (revenue * capex_pct).where(m.is_forecast, 0 * USD))
co.journal("Capital expenditures", debit=ppe, credit=co.bs.cash, amount=capex, cf="investing")

da_fcst = m.series("D&A forecast", ppe.lag(1, fill=0 * USD) * depr_rate)
da = co.pl.sga(
    "Depreciation & amortization",
    da_fcst,
    against=ppe,
    actuals={"2022": 20.0 * MM, "2023": 21.5 * MM, "2024": 23.0 * MM},
)

# Working capital schedules driven by DSO / DIO / DPO
ar = co.bs.other_asset(
    "Accounts receivable",
    target=revenue * dso_days / 365,
    cf="operating",
    actuals={"2022": 49.5 * MM, "2023": 54.5 * MM, "2024": 60.0 * MM},
)
inventory = co.bs.other_asset(
    "Inventory",
    target=cogs * dio_days / 365,
    cf="operating",
    actuals={"2022": 38.0 * MM, "2023": 41.5 * MM, "2024": 45.5 * MM},
)
ap = co.bs.other_liability(
    "Accounts payable",
    target=cogs * dpo_days / 365,
    cf="operating",
    actuals={"2022": 24.0 * MM, "2023": 26.3 * MM, "2024": 28.8 * MM},
)

# Debt schedule: Senior Term Loan with mandatory amortization (interest on opening balance -> acyclic)
term_loan = co.bs.loan(
    "Senior term loan",
    rate=None,
    repay=mandatory_amort,
    actuals={"2022": 180.0 * MM, "2023": 165.0 * MM, "2024": 150.0 * MM},
)
interest = co.pl.interest_expense(
    "Interest expense",
    term_loan.lag(1, fill=0 * USD) * debt_rate,
    actuals={"2022": 12.0 * MM, "2023": 11.0 * MM, "2024": 9.8 * MM},
)

# Taxes & capital allocation
taxes = co.pl.income_tax(
    "Income taxes",
    rate=tax_rate,
    base=co.pl.pretax_income,
    nol=False,
    actuals={"2022": 10.1 * MM, "2023": 12.6 * MM, "2024": 15.4 * MM},
)
dividends_amt = m.series(
    "Common dividends",
    (b.max(co.pl.net_income, 0 * USD) * payout_ratio).where(m.is_forecast, 0 * USD),
)
co.bs.dividend("Common dividends", dividends_amt)

# Equity & Cash historical actuals (all 3 actual years balance identically)
common_stock = co.bs.capital(
    "Common stock & APIC",
    actuals={"2022": 50.0 * MM, "2023": 50.0 * MM, "2024": 50.0 * MM},
)
co.load_actuals({
    co.bs.cash: {"2022": 45.0 * MM, "2023": 45.2 * MM, "2024": 51.3 * MM},
    co.bs.retained_earnings: {"2022": 43.5 * MM, "2023": 73.4 * MM, "2024": 110.0 * MM},
})

# ---- Derived IB Metrics, Indirect CF Lines & Schedule Rollforwards ------------------

ebitda = m.series("EBITDA", co.pl.operating_income + da)
rev_growth_disp = m.series("Revenue % growth", (revenue / revenue.lag(1) - 1).where(m.t > 0, 0))
gp_margin = m.series("Gross % margin", co.pl.gross_profit / revenue)
ebitda_margin = m.series("EBITDA % margin", ebitda / revenue)
ebit_margin = m.series("EBIT % margin", co.pl.operating_income / revenue)
eff_tax_rate = m.series("Implied effective tax rate", taxes / co.pl.pretax_income)
net_margin = m.series("Net % margin", co.pl.net_income / revenue)

# Balance Sheet subtotals
total_current_assets = m.series("Total current assets", co.bs.cash + ar + inventory)
total_liab_equity = m.series("Total liabilities & equity", co.bs.total_liabilities + co.bs.total_equity)
bs_check = m.series("Balance check", co.bs.total_assets - total_liab_equity)

# Indirect Cash Flow components (forecast years; 0 in actual years where CF is not posted)
cf_ni = m.series("Net income (CF)", co.pl.net_income.where(m.is_forecast, 0 * USD))
cf_da = m.series("Depreciation & amortization (CF)", da.where(m.is_forecast, 0 * USD))
cf_d_ar = m.series("Change in accounts receivable", (-(ar - ar.lag(1, fill=0 * USD))).where(m.is_forecast, 0 * USD))
cf_d_inv = m.series("Change in inventory", (-(inventory - inventory.lag(1, fill=0 * USD))).where(m.is_forecast, 0 * USD))
cf_d_ap = m.series("Change in accounts payable", (ap - ap.lag(1, fill=0 * USD)).where(m.is_forecast, 0 * USD))
cf_capex = m.series("Capital expenditures (CF)", (-capex).where(m.is_forecast, 0 * USD))
cf_debt_repay = m.series("Term loan repayment", (-term_loan.principal).where(m.is_forecast, 0 * USD))
cf_dividends = m.series("Dividends paid", (-dividends_amt).where(m.is_forecast, 0 * USD))

net_change_cash = m.series("Net change in cash", co.cf.operating + co.cf.investing + co.cf.financing)
beg_cash = m.series("Beginning cash", co.bs.cash.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))
end_cash = m.series("Ending cash", (beg_cash + net_change_cash).where(m.is_forecast, co.bs.cash))
fcf = m.series("Free cash flow (FCF)", (co.cf.operating - capex).where(m.is_forecast, 0 * USD))
fcf_conversion = m.series("FCF / EBITDA", (fcf / ebitda).where(m.is_forecast, 0))

# Schedule metrics (historical back-calculated DSO/DIO/DPO seamlessly flow into forecast)
dso_actual_and_fcst = m.series("Implied DSO (days)", ar / revenue * 365)
dio_actual_and_fcst = m.series("Implied DIO (days)", inventory / cogs * 365)
dpo_actual_and_fcst = m.series("Implied DPO (days)", ap / cogs * 365)
nwc = m.series("Net working capital", ar + inventory - ap)
change_nwc = m.series("Change in NWC", (nwc - nwc.lag(1, fill=0 * USD)).where(m.t > 0, 0 * USD))

ppe_open = m.series("PP&E opening balance", ppe.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))
debt_open = m.series("Term loan opening balance", term_loan.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))
sched_amort = m.series("Term loan amortization (sched)", (-term_loan.principal).where(m.is_forecast, 0 * USD))
net_debt = m.series("Net debt", term_loan - co.bs.cash)
net_leverage = m.series("Net debt / EBITDA", net_debt / ebitda)
interest_cov = m.series("EBITDA / Interest", ebitda / interest)

# Terminal Valuation & Credit Bridge scalars (FY2029E)
terminal_ebitda = m.series("Terminal EBITDA", ebitda.last())
implied_ev = m.series("Implied enterprise value", terminal_ebitda * exit_multiple)
terminal_debt = m.series("Terminal debt", term_loan.last())
terminal_cash = m.series("Terminal cash", co.bs.cash.last())
implied_equity = m.series("Implied equity value", implied_ev - terminal_debt + terminal_cash)

# ---- IB Multi-Sheet Layout (Zero Model Sheet) ---------------------------------------

def build_sheets():
    """Return the IB-grade sheet layout (Summary, IS, BS, CF, Schedules)."""
    return [
        b.sheet("Summary", [
            b.section("Financial Highlights", [
                b.link(revenue, "Revenue"),
                b.link(rev_growth_disp, "% growth", fmt="percent"),
                b.link(co.pl.gross_profit, "Gross profit", total=True),
                b.link(gp_margin, "% margin", fmt="percent"),
                b.link(ebitda, "EBITDA", total=True),
                b.link(ebitda_margin, "% margin", fmt="percent"),
                b.link(co.pl.net_income, "Net income", total=True),
                b.link(fcf, "Free cash flow (FCF)"),
                b.link(fcf_conversion, "FCF / EBITDA", fmt="percent"),
            ]),
            b.section("Credit & Leverage Profile", [
                b.link(co.bs.cash, "Cash & cash equivalents"),
                b.link(term_loan, "Total debt"),
                b.row(net_debt, "Net debt", total=True),
                b.row(net_leverage, "Net debt / EBITDA", fmt="multiple"),
                b.row(interest_cov, "EBITDA / Interest", fmt="multiple"),
            ]),
            b.panel("Illustrative FY2029E Valuation & Credit Bridge", ["$mm", "x EBITDA"], [
                ("FY2029E EBITDA", [terminal_ebitda, terminal_ebitda / terminal_ebitda], {"fmt": ["money", "multiple"]}),
                ("Exit EV / EBITDA Multiple", ["", exit_multiple], {"fmt": [None, "multiple"]}),
                ("Implied Enterprise Value", [implied_ev, exit_multiple],
                 {"total": True, "fmt": ["money", "multiple"]}),
                ("Less: FY2029E Total Debt", [-terminal_debt, -terminal_debt / terminal_ebitda],
                 {"fmt": ["money", "multiple"]}),
                ("Plus: FY2029E Cash", [terminal_cash, terminal_cash / terminal_ebitda],
                 {"fmt": ["money", "multiple"]}),
                ("Implied Equity Value", [implied_equity, implied_equity / terminal_ebitda],
                 {"total": "grand", "fmt": ["money", "multiple"]}),
            ]),
        ]),
        b.sheet("IS", [
            b.section("Income Statement", [
                b.row(revenue, "Revenue"),
                b.row(rev_growth_disp, "% growth", fmt="percent"),
                b.row(cogs, "Cost of goods sold", sign=-1),
                b.row(co.pl.gross_profit, "Gross profit", total=True),
                b.row(gp_margin, "% margin", fmt="percent"),
                b.row(sga, "Selling, general & administrative", sign=-1),
                b.row(rd, "Research & development", sign=-1),
                b.row(da, "Depreciation & amortization", sign=-1),
                b.row(co.pl.operating_income, "Operating income (EBIT)", total=True),
                b.row(ebit_margin, "% margin", fmt="percent"),
                b.row(interest, "Interest expense", sign=-1),
                b.row(co.pl.pretax_income, "Pre-tax income (EBT)", total=True),
                b.row(taxes, "Income taxes", sign=-1),
                b.row(eff_tax_rate, "% effective tax rate", fmt="percent"),
                b.row(co.pl.net_income, "Net income", total="grand"),
                b.row(net_margin, "% margin", fmt="percent"),
            ]),
            b.section("Memo: Non-GAAP Profitability", [
                b.row(ebitda, "EBITDA", total=True),
                b.row(ebitda_margin, "% EBITDA margin", fmt="percent"),
            ]),
        ]),
        b.sheet("BS", [
            b.section("Assets", [
                b.row(co.bs.cash, "Cash & cash equivalents", formula=end_cash),
                b.row(ar, "Accounts receivable"),
                b.row(inventory, "Inventory"),
                b.row(total_current_assets, "Total current assets", total=True),
                b.row(ppe, "PP&E, net", formula=ppe_open + capex - da),
                b.row(co.bs.total_assets, "Total assets", total="grand"),
            ]),
            b.section("Liabilities & Shareholders' Equity", [
                b.row(ap, "Accounts payable"),
                b.row(term_loan, "Senior term loan", formula=debt_open - term_loan.principal),
                b.row(co.bs.total_liabilities, "Total liabilities", total=True),
                b.row(common_stock, "Common stock & APIC"),
                b.row(
                    co.bs.retained_earnings,
                    "Retained earnings",
                    formula=co.bs.retained_earnings.lag(1, fill=0 * USD) + co.pl.net_income - dividends_amt,
                ),
                b.row(co.bs.total_equity, "Total shareholders' equity", total=True),
                b.row(total_liab_equity, "Total liabilities & equity", total="grand"),
                b.row(bs_check, "Balance check"),
            ]),
        ]),
        b.sheet("CF", [
            b.section("Operating Activities", [
                b.block(
                    co.cf.operating,
                    [
                        b.row(cf_ni, "Net income"),
                        b.row(cf_da, "Depreciation & amortization"),
                        cf_d_ar,
                        cf_d_inv,
                        cf_d_ap,
                    ],
                    label="Cash flow from operations",
                ),
            ]),
            b.section("Investing Activities", [
                b.block(co.cf.investing, [b.row(cf_capex, "Capital expenditures")], label="Cash flow from investing"),
            ]),
            b.section("Financing Activities", [
                b.block(co.cf.financing, [cf_debt_repay, cf_dividends], label="Cash flow from financing"),
            ]),
            b.section("Cash Reconciliation", [
                b.row(net_change_cash, "Net change in cash", total=True),
                b.row(beg_cash, "Beginning cash"),
                b.row(end_cash, "Ending cash", total="grand"),
            ]),
            b.section("Memo: Free Cash Flow", [
                b.row(fcf, "Free cash flow (FCF)", total=True),
                b.row(fcf_conversion, "FCF / EBITDA", fmt="percent"),
            ]),
        ]),
        b.sheet("Schedules", [
            b.section("Working Capital Schedule", [
                b.row(dso_actual_and_fcst, "DSO (days)", fmt="days"),
                b.row(dio_actual_and_fcst, "DIO (days)", fmt="days"),
                b.row(dpo_actual_and_fcst, "DPO (days)", fmt="days"),
                b.link(ar, "Accounts receivable"),
                b.link(inventory, "Inventory"),
                b.link(ap, "Accounts payable"),
                b.row(nwc, "Net working capital", total=True),
                b.row(change_nwc, "Change in NWC"),
            ]),
            b.section("PP&E Rollforward", [
                b.row(ppe_open, "Beginning PP&E, net"),
                b.row(capex, "Capital expenditures"),
                b.link(da, "Less: Depreciation & amortization"),
                b.link(ppe, "Ending PP&E, net", total=True),
            ]),
            b.section("Debt & Capital Allocation Schedule", [
                b.row(debt_open, "Beginning term loan"),
                b.row(sched_amort, "Less: Mandatory amortization"),
                b.link(term_loan, "Ending term loan", total=True),
                b.link(interest, "Interest expense"),
                b.row(dividends_amt, "Common dividends"),
            ]),
        ]),
    ]


r = m.render()


def export_ib_workbook(out_path: Path):
    """Export the full IB-grade multi-sheet workbook with live scenarios and zero Model sheet."""
    return r.to_excel(
        out_path,
        sheets=build_sheets(),
        scenarios=["Base", "Bull", "Bear"],
        money="$mm",
        statements=False,
        checks=True,
        omit_unused_model=True,
    )


if __name__ == "__main__":
    print(f"=== {m.name} (Base Case, $mm) ===")
    for name in ("Base", "Bull", "Bear"):
        res = m.render(scenario=None if name == "Base" else name)
        rev29 = res.value(revenue, "2029") / 1e6
        ebitda29 = res.value(ebitda, "2029") / 1e6
        fcf29 = res.value(fcf, "2029") / 1e6
        eq29 = res.value(implied_equity, "2029") / 1e6
        print(f"  {name:4s} | FY29E Rev ${rev29:6.1f}mm | EBITDA ${ebitda29:5.1f}mm | "
              f"FCF ${fcf29:5.1f}mm | Implied Equity ${eq29:6.1f}mm")
    if len(sys.argv) > 1:
        out_dir = Path(sys.argv[1])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "acme_ib_3statement.xlsx"
        report = export_ib_workbook(out_file)
        print(f"\nExported: {out_file}")
        print(f"Report: {report}")
        print(f"Unplaced Model rows: {report.unplaced}")
