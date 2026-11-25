"""Apex Precision Manufacturing — Investment-Banking Leveraged Buyout (LBO) Model (FY2025E–FY2029E).

Benchmark #2 for IB-grade financial modeling in boki:
- Full Transaction Sources & Uses, Goodwill creation, and Opening Pro Forma Balance Sheet (all live formulas).
- Multi-tranche Debt Waterfall (Term Loan A + Term Loan B) with mandatory amortization and 100% Excess Cash Flow Sweep.
- Full 3-Statement Operating Model (IS, BS, Indirect CF via verified ``b.block``) with zero circularity.
- Sponsor Returns (Exit Valuation Bridge, Sponsor MoIC, Sponsor IRR) + live 2D Sensitivity Tables
  (Entry Multiple × Exit Multiple for IRR and MoIC).
- Live Base / Bull / Bear scenario switch in Excel (Inputs!$C$3) with source citations and zero ``Model`` sheet.

Run:
    uv run python examples/ib_lbo/plan.py [out-dir]
    uv run python tools/excel_check.py examples/ib_lbo
"""
from __future__ import annotations

import sys
from pathlib import Path

import boki as b
from boki.units import USD, year

MM = 1_000_000 * USD

# ---- Model & Entity -----------------------------------------------------------------

m = b.Model("Apex Precision LBO", start="2025", periods=5, step=year)
co = m.entity("Apex Precision", standard=b.USGAAP, currency=USD)

# ---- Assumptions (Transaction, Operating, Debt & Exit) ------------------------------

ltm_revenue = m.input("LTM (FY2024A) revenue", 500.0 * MM, source="CIM / FY2024A audited financials")
ltm_ebitda = m.input("LTM (FY2024A) EBITDA", 100.0 * MM, source="CIM / QoE adjusted EBITDA")
entry_mult = m.input("Entry EV / LTM EBITDA", 9.0, source="Sponsor LOI")
fee_pct = m.input("Transaction & financing fees (% EV)", 0.025, source="M&A advisory & debt commitment")
min_cash = m.input("Minimum cash balance", 25.0 * MM, source="Operating liquidity buffer")

# Debt financing terms
tla_turns = m.input("Term Loan A leverage (x EBITDA)", 3.0, source="Senior bank commitment letter")
tla_rate = m.input("Term Loan A interest rate", 0.070, source="SOFR + 250bps")
tla_amort_pct = m.input("Term Loan A mandatory amort (%)", 0.05, source="5% annual scheduled amort")
tlb_turns = m.input("Term Loan B leverage (x EBITDA)", 2.5, source="Institutional term loan")
tlb_rate = m.input("Term Loan B interest rate", 0.0825, source="SOFR + 375bps")
tlb_amort_pct = m.input("Term Loan B mandatory amort (%)", 0.01, source="1% annual scheduled amort")

# Operating assumptions (Base / Bull / Bear live scenarios)
rev_growth = m.input(
    "Revenue growth", 0.075,
    scenarios={"Bull": 0.11, "Bear": 0.03},
    source="Commercial diligence & management plan",
)
cogs_pct = m.input(
    "COGS % of revenue", 0.56,
    scenarios={"Bull": 0.545, "Bear": 0.585},
    source="Historical 3-yr avg + procurement savings",
)
sga_pct = m.input(
    "SG&A % of revenue", 0.185,
    scenarios={"Bull": 0.175, "Bear": 0.20},
    source="Cost structure diligence",
)
capex_pct = m.input(
    "CapEx % of revenue", 0.045,
    scenarios={"Bull": 0.05, "Bear": 0.04},
    source="Maintenance + growth capex plan",
)
depr_rate = m.input("Depreciation % of opening PP&E", 0.12, source="8.3-yr avg remaining life")
dso_days = m.input("DSO (days)", 44.0, source="FY2024A working capital")
dio_days = m.input("DIO (days)", 58.0, source="FY2024A working capital")
dpo_days = m.input("DPO (days)", 39.0, source="FY2024A working capital")
tax_rate = m.input("Effective tax rate", 0.25, source="US federal + state statutory")

exit_mult = m.input(
    "Exit EV / FY2029E EBITDA", 9.0,
    scenarios={"Bull": 10.0, "Bear": 8.0},
    source="Assume flat multiple in Base",
)

# Opening operating balance sheet items acquired at close
open_ar = m.input("Close accounts receivable", 60.0 * MM, source="FY2024A close balance sheet")
open_inv = m.input("Close inventory", 45.0 * MM, source="FY2024A close balance sheet")
open_ppe = m.input("Close PP&E, net", 180.0 * MM, source="FY2024A close balance sheet")
open_ap = m.input("Close accounts payable", 30.0 * MM, source="FY2024A close balance sheet")

# ---- Transaction Sources & Uses + Opening Pro Forma BS ------------------------------

purchase_ev = m.series("Purchase enterprise value", ltm_ebitda * entry_mult)
tx_fees = m.series("Transaction & financing fees", purchase_ev * fee_pct)
total_uses = m.series("Total uses", purchase_ev + min_cash + tx_fees)

tla_init = m.series("Term Loan A initial", ltm_ebitda * tla_turns)
tlb_init = m.series("Term Loan B initial", ltm_ebitda * tlb_turns)
total_debt_init = m.series("Total debt at close", tla_init + tlb_init)
sponsor_equity = m.series("Sponsor common equity", total_uses - total_debt_init)
total_sources = m.series("Total sources", tla_init + tlb_init + sponsor_equity)

net_op_assets_close = m.series("Identifiable net operating assets", open_ar + open_inv + open_ppe - open_ap)
goodwill_init = m.series("Goodwill & intangibles created", purchase_ev + tx_fees - net_op_assets_close)

# ---- Operating Model (IS, Working Capital, PP&E) ------------------------------------

rev_fcst = m.series("Revenue forecast", unit=USD)
revenue = co.pl.revenue("Revenue", rev_fcst)
rev_fcst.define(revenue.lag(1, fill=ltm_revenue) * (1 + rev_growth))

cogs = co.pl.cogs("Cost of goods sold", revenue * cogs_pct)
sga = co.pl.sga("Selling, general & administrative", revenue * sga_pct)

# PP&E rollforward
ppe = co.bs.other_asset("PP&E, net", opening=open_ppe, cf="investing")
capex = m.series("Capital expenditures", revenue * capex_pct)
co.journal("Capital expenditures", debit=ppe, credit=co.bs.cash, amount=capex, cf="investing")

da_expr = m.series("D&A forecast", ppe.opening * depr_rate)
da = co.pl.sga("Depreciation & amortization", da_expr, against=ppe)

goodwill = co.bs.other_asset("Goodwill & intangibles", opening=goodwill_init, cf="investing")

# Working capital
ar = co.bs.other_asset("Accounts receivable", opening=open_ar, target=revenue * dso_days / 365, cf="operating")
inventory = co.bs.other_asset("Inventory", opening=open_inv, target=cogs * dio_days / 365, cf="operating")
ap = co.bs.other_liability("Accounts payable", opening=open_ap, target=cogs * dpo_days / 365, cf="operating")

# Opening Cash and Sponsor Equity
co.bs.opening(cash=min_cash, retained_earnings=0 * USD)
sponsor_cap = co.bs.capital("Sponsor common equity (BS)", opening=sponsor_equity)

# ---- Multi-Tranche Debt Waterfall & Excess Cash Flow Sweep --------------------------

tla_repay_total = m.series("Term Loan A total repayment")
tlb_repay_total = m.series("Term Loan B total repayment")

tla = co.bs.loan("Term Loan A", opening=tla_init, rate=tla_rate, repay=tla_repay_total)
tlb = co.bs.loan("Term Loan B", opening=tlb_init, rate=tlb_rate, repay=tlb_repay_total)

# Taxes & Net Income (interest is on opening debt balances -> completely acyclic!)
taxes = co.pl.income_tax("Income taxes", rate=tax_rate, base=co.pl.pretax_income, nol=False)

# Cash available for debt service (CFADS) & Excess Cash Flow Sweep
d_ar = m.series("Change in accounts receivable", -(ar - ar.opening))
d_inv = m.series("Change in inventory", -(inventory - inventory.opening))
d_ap = m.series("Change in accounts payable", ap - ap.opening)

cfads = m.series("Cash flow available for debt service", co.cf.operating - capex)
cash_before_debt = m.series("Excess cash before debt service", b.max(co.bs.cash.opening + cfads - min_cash, 0 * USD))

tla_mand = m.series("Term Loan A mandatory amort", b.min(tla.opening, tla_init * tla_amort_pct))
tlb_mand = m.series("Term Loan B mandatory amort", b.min(tlb.opening, tlb_init * tlb_amort_pct))
total_mand = m.series("Total mandatory amortization", tla_mand + tlb_mand)

excess_for_sweep = m.series("Excess cash available for sweep", b.max(cash_before_debt - total_mand, 0 * USD))
tla_sweep = m.series("Term Loan A cash sweep", b.min(b.max(tla.opening - tla_mand, 0 * USD), excess_for_sweep))
excess_after_tla = m.series("Remaining excess cash after TLA", b.max(excess_for_sweep - tla_sweep, 0 * USD))
tlb_sweep = m.series("Term Loan B cash sweep", b.min(b.max(tlb.opening - tlb_mand, 0 * USD), excess_after_tla))

tla_repay_total.define(tla_mand + tla_sweep)
tlb_repay_total.define(tlb_mand + tlb_sweep)

# Model-level checks
m.check(abs(total_sources - total_uses) < 0.01 * USD, "Sources = Uses")
m.check(co.bs.cash >= min_cash - 0.01 * USD, "Cash >= Minimum cash")
m.check(tla >= -0.01 * USD, "Term Loan A >= 0")
m.check(tlb >= -0.01 * USD, "Term Loan B >= 0")

# ---- Derived Metrics, Ratios & Returns ----------------------------------------------

ebitda = m.series("EBITDA", co.pl.operating_income + da)
total_interest = m.series("Total interest expense", tla.interest + tlb.interest)
rev_growth_disp = m.series("Revenue % growth", revenue / revenue.lag(1, fill=ltm_revenue) - 1)
gp_margin = m.series("Gross % margin", co.pl.gross_profit / revenue)
ebitda_margin = m.series("EBITDA % margin", ebitda / revenue)
ebit_margin = m.series("EBIT % margin", co.pl.operating_income / revenue)
net_margin = m.series("Net % margin", co.pl.net_income / revenue)

total_current_assets = m.series("Total current assets", co.bs.cash + ar + inventory)
total_debt = m.series("Total debt", tla + tlb)
net_debt = m.series("Net debt", total_debt - co.bs.cash)
total_leverage = m.series("Total debt / EBITDA", total_debt / ebitda)
net_leverage = m.series("Net debt / EBITDA", net_debt / ebitda)
interest_cov = m.series("EBITDA / Interest", ebitda / total_interest)
total_liab_equity = m.series("Total liabilities & equity", co.bs.total_liabilities + co.bs.total_equity)
bs_check = m.series("Balance check", co.bs.total_assets - total_liab_equity)

# CF display series
cf_capex = m.series("Capital expenditures (CF)", -capex)
cf_tla_repay = m.series("Term Loan A repayment", -tla.principal)
cf_tlb_repay = m.series("Term Loan B repayment", -tlb.principal)
net_cash_chg = m.series("Net change in cash", co.cf.operating + co.cf.investing + co.cf.financing)
beg_cash = m.series("Beginning cash", co.bs.cash.opening)
end_cash = m.series("Ending cash", beg_cash + net_cash_chg)
ppe_open_s = m.series("Beginning PP&E", ppe.opening)
tla_open_s = m.series("Beginning Term Loan A", tla.opening)
tlb_open_s = m.series("Beginning Term Loan B", tlb.opening)

# Exit Valuation & Sponsor Returns (FY2029E, 5-year hold)
exit_ebitda = m.series("Exit FY2029E EBITDA", ebitda.last())
exit_ev = m.series("Exit enterprise value", exit_ebitda * exit_mult)
exit_debt = m.series("Less: Ending total debt", total_debt.last())
exit_cash = m.series("Plus: Ending cash", co.bs.cash.last())
exit_equity = m.series("Exit sponsor equity", exit_ev - exit_debt + exit_cash)
sponsor_moic = m.series("Sponsor MoIC", exit_equity / sponsor_equity)
sponsor_irr = m.series("Sponsor IRR", sponsor_moic ** (1 / 5) - 1)

# 2D Sensitivity Axes (Entry Multiple × Exit Multiple — live Excel header cell references!)
ENTRY_MULTS = (8.0, 8.5, 9.0, 9.5, 10.0)
EXIT_MULTS = (7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5)


def _lbo_moic(e_m, x_m):
    eq_in = sponsor_equity + ltm_ebitda * (e_m - entry_mult) * (1 + fee_pct)
    eq_out = exit_ebitda * x_m - exit_debt + exit_cash
    return eq_out / eq_in


def _lbo_irr(e_m, x_m):
    return _lbo_moic(e_m, x_m) ** (1 / 5) - 1


def build_sheets():
    """Return the IB-grade LBO workbook layout (zero Model sheet)."""
    return [
        b.sheet("Transaction", [
            b.panel("Sources & Uses at Close (FY2024A)", ["$mm", "%", "x EBITDA"], [
                ("Term Loan A", [tla_init, tla_init / total_sources, tla_turns],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Term Loan B", [tlb_init, tlb_init / total_sources, tlb_turns],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Total Debt", [total_debt_init, total_debt_init / total_sources, total_debt_init / ltm_ebitda],
                 {"total": True, "fmt": ["money", "percent", "multiple"]}),
                ("Sponsor Common Equity", [sponsor_equity, sponsor_equity / total_sources, sponsor_equity / ltm_ebitda],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Total Sources", [total_sources, total_sources / total_sources, total_sources / ltm_ebitda],
                 {"total": "grand", "fmt": ["money", "percent", "multiple"]}),
            ]),
            b.panel("Uses of Funds", ["$mm", "%", "x EBITDA"], [
                ("Purchase Enterprise Value", [purchase_ev, purchase_ev / total_uses, entry_mult],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Cash to Balance Sheet", [min_cash, min_cash / total_uses, min_cash / ltm_ebitda],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Transaction & Financing Fees", [tx_fees, tx_fees / total_uses, tx_fees / ltm_ebitda],
                 {"fmt": ["money", "percent", "multiple"]}),
                ("Total Uses", [total_uses, total_uses / total_uses, total_uses / ltm_ebitda],
                 {"total": "grand", "fmt": ["money", "percent", "multiple"]}),
            ]),
            b.panel("Goodwill & Opening Pro Forma Balance Sheet", ["$mm"], [
                ("Purchase Enterprise Value + Fees", [purchase_ev + tx_fees], {"fmt": "money"}),
                ("Less: Identifiable Net Operating Assets", [-net_op_assets_close], {"fmt": "money"}),
                ("Goodwill & Intangibles Created", [goodwill_init], {"total": True, "fmt": "money"}),
                ("Opening Pro Forma Total Assets", [min_cash + open_ar + open_inv + open_ppe + goodwill_init],
                 {"fmt": "money"}),
                ("Opening Pro Forma Total Liab. & Equity", [open_ap + total_debt_init + sponsor_equity],
                 {"total": "grand", "fmt": "money"}),
            ]),
        ]),
        b.sheet("Returns", [
            b.section("Deleveraging & Credit Trajectory", [
                b.link(revenue, "Revenue"),
                b.link(ebitda, "EBITDA", total=True),
                b.link(ebitda_margin, "% margin", fmt="percent"),
                b.link(cfads, "CFADS (CFO - CapEx)"),
                b.link(total_debt, "Ending total debt", total=True),
                b.link(net_debt, "Net debt"),
                b.row(total_leverage, "Total debt / EBITDA", fmt="multiple"),
                b.row(net_leverage, "Net debt / EBITDA", fmt="multiple"),
                b.row(interest_cov, "EBITDA / Interest", fmt="multiple"),
            ]),
            b.panel("Exit Valuation & Sponsor Returns (FY2029E)", ["$mm", "Metric"], [
                ("FY2029E EBITDA", [exit_ebitda, ""], {"fmt": ["money", None]}),
                ("Exit EV / EBITDA Multiple", ["", exit_mult], {"fmt": [None, "multiple"]}),
                ("Implied Exit Enterprise Value", [exit_ev, exit_mult], {"total": True, "fmt": ["money", "multiple"]}),
                ("Less: FY2029E Ending Total Debt", [-exit_debt, -exit_debt / exit_ebitda],
                 {"fmt": ["money", "multiple"]}),
                ("Plus: FY2029E Ending Cash", [exit_cash, exit_cash / exit_ebitda],
                 {"fmt": ["money", "multiple"]}),
                ("Implied Exit Sponsor Equity", [exit_equity, ""], {"total": "grand", "fmt": ["money", None]}),
                ("Initial Sponsor Equity Invested", [sponsor_equity, ""], {"fmt": ["money", None]}),
                ("Sponsor MoIC", ["", sponsor_moic], {"bold": True, "fmt": [None, "multiple"]}),
                ("Sponsor IRR (5-Year Hold)", ["", sponsor_irr], {"total": "grand", "fmt": [None, "percent"]}),
            ]),
            b.sensitivity(
                "Sensitivity: Sponsor IRR (Entry Multiple vs. Exit Multiple)",
                ENTRY_MULTS,
                EXIT_MULTS,
                _lbo_irr,
                fmt="percent",
                row_fmt='"Entry "0.0"x"',
                col_fmt='"Exit "0.0"x"',
                highlight=(2, 3),
                corner="Entry \\ Exit",
            ),
            b.sensitivity(
                "Sensitivity: Sponsor MoIC (Entry Multiple vs. Exit Multiple)",
                ENTRY_MULTS,
                EXIT_MULTS,
                _lbo_moic,
                fmt="multiple",
                row_fmt='"Entry "0.0"x"',
                col_fmt='"Exit "0.0"x"',
                highlight=(2, 3),
                corner="Entry \\ Exit",
            ),
        ]),
        b.sheet("IS", [
            b.section("Income Statement", [
                b.row(revenue, "Revenue"),
                b.row(rev_growth_disp, "% growth", fmt="percent"),
                b.row(cogs, "Cost of goods sold", sign=-1),
                b.row(co.pl.gross_profit, "Gross profit", total=True),
                b.row(gp_margin, "% margin", fmt="percent"),
                b.row(sga, "Selling, general & administrative", sign=-1),
                b.row(da, "Depreciation & amortization", sign=-1),
                b.row(co.pl.operating_income, "Operating income (EBIT)", total=True),
                b.row(ebit_margin, "% margin", fmt="percent"),
                b.row(tla.interest, "Interest — Term Loan A", sign=-1),
                b.row(tlb.interest, "Interest — Term Loan B", sign=-1),
                b.row(total_interest, "Total interest expense", sign=-1, total=True),
                b.row(co.pl.pretax_income, "Pre-tax income (EBT)", total=True),
                b.row(taxes, "Income taxes", sign=-1),
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
                b.row(ppe, "PP&E, net", formula=ppe_open_s + capex - da),
                b.row(goodwill, "Goodwill & intangibles"),
                b.row(co.bs.total_assets, "Total assets", total="grand"),
            ]),
            b.section("Liabilities & Shareholders' Equity", [
                b.row(ap, "Accounts payable"),
                b.row(tla, "Term Loan A", formula=tla_open_s - tla.principal),
                b.row(tlb, "Term Loan B", formula=tlb_open_s - tlb.principal),
                b.row(co.bs.total_liabilities, "Total liabilities", total=True),
                b.row(sponsor_cap, "Sponsor common equity"),
                b.row(
                    co.bs.retained_earnings,
                    "Retained earnings",
                    formula=co.bs.retained_earnings.lag(1, fill=0 * USD) + co.pl.net_income,
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
                        b.link(co.pl.net_income, "Net income"),
                        b.link(da, "Depreciation & amortization", sign=-1),
                        d_ar,
                        d_inv,
                        d_ap,
                    ],
                    label="Cash flow from operations",
                ),
            ]),
            b.section("Investing Activities", [
                b.block(co.cf.investing, [b.row(cf_capex, "Capital expenditures")], label="Cash flow from investing"),
            ]),
            b.section("Financing Activities", [
                b.block(
                    co.cf.financing,
                    [cf_tla_repay, cf_tlb_repay],
                    label="Cash flow from financing",
                ),
            ]),
            b.section("Cash Reconciliation", [
                b.row(net_cash_chg, "Net change in cash", total=True),
                b.row(beg_cash, "Beginning cash"),
                b.row(end_cash, "Ending cash", total="grand"),
            ]),
            b.section("Memo: Debt Service Capacity", [
                b.row(cfads, "CFADS (CFO - CapEx)", total=True),
                b.row(ppe_open_s, "Beginning PP&E, net"),
                b.row(capex, "Capital expenditures"),
            ]),
        ]),
        b.sheet("Debt", [
            b.section("Cash Flow Sweep Waterfall", [
                b.link(cfads, "CFADS (CFO - CapEx)"),
                b.row(cash_before_debt, "Cash available for debt service"),
                b.row(total_mand, "Less: Total mandatory amortization", sign=-1),
                b.row(excess_for_sweep, "Excess cash available for sweep", total=True),
            ]),
            b.section("Term Loan A (Senior Bank — 1st Sweep Priority)", [
                b.row(tla_open_s, "Beginning balance"),
                b.row(tla_mand, "Less: Mandatory amortization", sign=-1),
                b.row(tla_sweep, "Less: Optional cash sweep", sign=-1),
                b.row(tla.principal, "Total Term Loan A repayment", sign=-1),
                b.link(tla, "Ending Term Loan A", total=True),
                b.link(tla.interest, "Interest expense"),
            ]),
            b.section("Term Loan B (Institutional — 2nd Sweep Priority)", [
                b.row(tlb_open_s, "Beginning balance"),
                b.row(tlb_mand, "Less: Mandatory amortization", sign=-1),
                b.row(excess_after_tla, "Remaining sweep capacity after TLA"),
                b.row(tlb_sweep, "Less: Optional cash sweep", sign=-1),
                b.row(tlb.principal, "Total Term Loan B repayment", sign=-1),
                b.link(tlb, "Ending Term Loan B", total=True),
                b.link(tlb.interest, "Interest expense"),
            ]),
            b.section("Total Debt Summary", [
                b.row(total_debt, "Total debt", total=True),
                b.link(co.bs.cash, "Less: Cash & cash equivalents", sign=-1),
                b.row(net_debt, "Net debt", total="grand"),
            ]),
        ]),
    ]


r = m.render()


def export_ib_workbook(out_path: Path):
    """Export the full IB-grade LBO workbook with live scenarios and zero Model sheet."""
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
    print(f"=== {m.name} (5-Year Hold, $mm) ===")
    for name in ("Base", "Bull", "Bear"):
        res = m.render(scenario=None if name == "Base" else name)
        eb29 = res.value(ebitda, "2029") / 1e6
        debt29 = res.value(total_debt, "2029") / 1e6
        moic = res[sponsor_moic]
        irr = res[sponsor_irr] * 100
        print(f"  {name:4s} | FY29E EBITDA ${eb29:5.1f}mm | End Debt ${debt29:5.1f}mm | "
              f"MoIC {moic:4.2f}x | IRR {irr:5.1f}%")
    if len(sys.argv) > 1:
        out_dir = Path(sys.argv[1])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "apex_lbo.xlsx"
        report = export_ib_workbook(out_file)
        print(f"\nExported: {out_file}")
        print(f"Report: {report}")
        print(f"Unplaced Model rows: {report.unplaced}")
