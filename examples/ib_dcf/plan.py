"""Veridian MedTech Inc. — Investment-Banking DCF Valuation Model (2022A–2029E).

Benchmark #3 for IB-grade financial modeling in boki:
- 3 historical actual years (2022A–2024A) + 5 explicit forecast years (2025E–2029E), US GAAP, $mm.
- Full CAPM WACC build-up (Risk-free rate, ERP, Levered Beta, After-tax Cost of Debt, Target Capital Structure).
- Unlevered Free Cash Flow (UFCF) build via verified ``b.block`` with Mid-Year Discounting.
- Dual Terminal Value methodologies: Perpetuity Growth Method (Gordon Growth) & Exit EV / EBITDA Multiple Method,
  with cross-check metrics (Implied Exit Multiple & Implied Perpetual Growth Rate).
- Side-by-side Valuation Bridge + two live 2D Sensitivity Tables (WACC × Terminal Growth & WACC × Exit Multiple)
  computing Implied Share Price via live Excel formulas.
- Live Base / Bull / Bear scenario switch in Excel (Inputs!$C$3) with source citations and zero ``Model`` sheet.

Run:
    uv run python examples/ib_dcf/plan.py [out-dir]
    uv run python tools/excel_check.py examples/ib_dcf
"""
from __future__ import annotations

import sys
from pathlib import Path

import boki as b
from boki.units import USD, year

MM = 1_000_000 * USD

# ---- Model & Entity -----------------------------------------------------------------

m = b.Model("Veridian MedTech DCF", start="2022", periods=8, step=year, actual_until="2024")
co = m.entity("Veridian MedTech", standard=b.USGAAP, currency=USD)

# ---- Assumptions (Operating, WACC, Terminal Value & Market Data) --------------------

rev_growth = m.input(
    "Revenue growth", 0.09,
    scenarios={"Bull": 0.13, "Bear": 0.045},
    source="Wall Street consensus & FDA pipeline",
)
cogs_pct = m.input(
    "COGS % of revenue", 0.34,
    scenarios={"Bull": 0.325, "Bear": 0.365},
    source="FY2024 10-K gross margin trend",
)
sga_pct = m.input(
    "SG&A % of revenue", 0.25,
    scenarios={"Bull": 0.235, "Bear": 0.265},
    source="FY2024 10-K p.44",
)
rd_pct = m.input(
    "R&D % of revenue", 0.125,
    scenarios={"Bull": 0.13, "Bear": 0.12},
    source="MedTech peer median R&D intensity",
)
da_pct = m.input("D&A % of revenue", 0.05, source="3-yr historical average (5.0%)")
capex_pct = m.input(
    "CapEx % of revenue", 0.055,
    scenarios={"Bull": 0.06, "Bear": 0.045},
    source="Management long-term capex target",
)
nwc_pct = m.input("Operating NWC % of revenue", 0.14, source="3-yr historical NWC / Revenue")
tax_rate = m.input("Effective tax rate", 0.22, source="FY2024 10-K effective tax rate")
debt_rate = m.input("Debt interest rate", 0.0575, source="BBB+ senior notes coupon")

# WACC assumptions
rf_rate = m.input("Risk-free rate (10Y UST)", 0.0425, source="10-Year US Treasury yield")
erp = m.input("Equity risk premium (ERP)", 0.055, source="Kroll / Damodaran US ERP")
beta = m.input("Levered beta", 1.05, source="2-yr weekly Bloomberg beta")
pretax_kd = m.input("Pre-tax cost of debt", 0.0575, source="BBB+ corporate bond yield")
debt_weight = m.input("Target debt / total capital", 0.15, source="Target capital structure (15% D / 85% E)")

# Terminal value & market data
term_growth = m.input(
    "Terminal growth rate (g)", 0.03,
    scenarios={"Bull": 0.035, "Bear": 0.025},
    source="Long-term US GDP + healthcare inflation",
)
exit_mult = m.input(
    "Terminal EV / EBITDA multiple", 13.5,
    scenarios={"Bull": 15.0, "Bear": 11.5},
    source="MedTech peer group NTM median",
)
current_price = m.input("Current share price ($)", 68.0, source="NYSE closing price")
diluted_shares = m.input("Diluted shares (millions)", 50.0, source="FY2024 10-K treasury stock method")

# ---- Operating Model (3 Actual Years 2022A–2024A + 5 Forecast Years 2025E–2029E) ----

rev_fcst = m.series("Revenue forecast", unit=USD)
revenue = co.pl.revenue(
    "Revenue",
    rev_fcst,
    actuals={"2022": 1000.0 * MM, "2023": 1095.0 * MM, "2024": 1200.0 * MM},
)
rev_fcst.define(revenue.lag(1) * (1 + rev_growth))

cogs = co.pl.cogs(
    "Cost of goods sold",
    revenue * cogs_pct,
    actuals={"2022": 350.0 * MM, "2023": 378.0 * MM, "2024": 408.0 * MM},
)
sga = co.pl.sga(
    "Selling, general & administrative",
    revenue * sga_pct,
    actuals={"2022": 260.0 * MM, "2023": 279.0 * MM, "2024": 300.0 * MM},
)
rd = co.pl.sga(
    "Research & development",
    revenue * rd_pct,
    actuals={"2022": 125.0 * MM, "2023": 137.0 * MM, "2024": 150.0 * MM},
)

# PP&E & D&A
ppe = co.bs.other_asset(
    "PP&E, net",
    cf="investing",
    actuals={"2022": 360.0 * MM, "2023": 370.0 * MM, "2024": 385.0 * MM},
)
capex = m.series("Capital expenditures", (revenue * capex_pct).where(m.is_forecast, 0 * USD))
co.journal("Capital expenditures", debit=ppe, credit=co.bs.cash, amount=capex, cf="investing")

da = co.pl.sga(
    "Depreciation & amortization",
    revenue * da_pct,
    against=ppe,
    actuals={"2022": 50.0 * MM, "2023": 55.0 * MM, "2024": 60.0 * MM},
)

# Operating Net Working Capital (modeled cleanly as net operating working capital asset)
nwc_bs = co.bs.other_asset(
    "Net working capital",
    target=revenue * nwc_pct,
    cf="operating",
    actuals={"2022": 140.0 * MM, "2023": 153.0 * MM, "2024": 168.0 * MM},
)

# Existing Debt (held constant at $420mm through forecast for clean capital structure)
notes = co.bs.loan(
    "Senior notes",
    rate=None,
    repay=0 * USD,
    actuals={"2022": 420.0 * MM, "2023": 420.0 * MM, "2024": 420.0 * MM},
)
interest = co.pl.interest_expense(
    "Interest expense",
    notes.lag(1, fill=0 * USD) * debt_rate,
    actuals={"2022": 24.2 * MM, "2023": 24.2 * MM, "2024": 24.2 * MM},
)
taxes = co.pl.income_tax(
    "Income taxes",
    rate=tax_rate,
    base=co.pl.pretax_income,
    nol=False,
    actuals={"2022": 42.0 * MM, "2023": 48.8 * MM, "2024": 56.7 * MM},
)

# Historical BS balances (exact tie-out across 2022A–2024A)
common_stock = co.bs.capital(
    "Common stock & APIC",
    actuals={"2022": 150.0 * MM, "2023": 150.0 * MM, "2024": 150.0 * MM},
)
co.load_actuals({
    co.bs.cash: {"2022": 135.0 * MM, "2023": 185.0 * MM, "2024": 240.0 * MM},
    # 2022A Assets = 135+140+360 = 635 -> Debt 420 + Common 150 + RE 65 = 635
    # 2023A Assets = 185+153+370 = 708 -> Debt 420 + Common 150 + RE 138 = 708
    # 2024A Assets = 240+168+385 = 793 -> Debt 420 + Common 150 + RE 223 = 793
    co.bs.retained_earnings: {"2022": 65.0 * MM, "2023": 138.0 * MM, "2024": 223.0 * MM},
})

# ---- WACC Build-Up ------------------------------------------------------------------

cost_of_equity = m.series("Cost of equity (CAPM)", rf_rate + beta * erp)
aftertax_kd = m.series("After-tax cost of debt", pretax_kd * (1 - tax_rate))
equity_weight = m.series("Target equity weight", 1 - debt_weight)
wacc = m.series("Weighted average cost of capital (WACC)", equity_weight * cost_of_equity + debt_weight * aftertax_kd)

# ---- Unlevered Free Cash Flow (UFCF) & Mid-Year Discounting -------------------------

ebitda = m.series("EBITDA", co.pl.operating_income + da)
rev_growth_disp = m.series("Revenue % growth", (revenue / revenue.lag(1) - 1).where(m.t > 0, 0))
gp_margin = m.series("Gross % margin", co.pl.gross_profit / revenue)
ebitda_margin = m.series("EBITDA % margin", ebitda / revenue)
ebit_margin = m.series("EBIT % margin", co.pl.operating_income / revenue)

ebit_fcst = m.series("EBIT (UFCF)", co.pl.operating_income.where(m.is_forecast, 0 * USD))
unlevered_tax = m.series("Less: Taxes on EBIT", (-(co.pl.operating_income * tax_rate)).where(m.is_forecast, 0 * USD))
nopat = m.series("NOPAT", (co.pl.operating_income * (1 - tax_rate)).where(m.is_forecast, 0 * USD))
ufcf_da = m.series("Plus: Depreciation & amortization", da.where(m.is_forecast, 0 * USD))
ufcf_capex = m.series("Less: Capital expenditures", (-capex).where(m.is_forecast, 0 * USD))
change_nwc = m.series("Less: Change in NWC", (-(nwc_bs - nwc_bs.lag(1, fill=0 * USD))).where(m.is_forecast, 0 * USD))
ufcf = m.series("Unlevered free cash flow (UFCF)", nopat + ufcf_da + ufcf_capex + change_nwc)

# Mid-year discount periods (0.5, 1.5, 2.5, 3.5, 4.5) written as live Excel formulas without m.t row!
disc_period = m.series("Discount period (mid-year)")
disc_period.define(
    b.Series.where(
        b.series.Const(0.5),
        m.t == 3,
        (disc_period.lag(1, fill=0) + 1).where(m.is_forecast, 0),
    )
)
disc_factor = m.series("Discount factor", (1 / (1 + wacc) ** disc_period).where(m.is_forecast, 0))
pv_ufcf = m.series("Present value of UFCF", (ufcf * disc_factor).where(m.is_forecast, 0 * USD))

# Sum of explicit PV of UFCFs (years 2025E–2029E; 0 in actual years -> clean SUM formula!)
sum_pv_ufcf = m.series("PV of explicit UFCF (FY25E–FY29E)", pv_ufcf.sum())

# Valuation Date (FY2024A Close, index 2) Balance Sheet Bridge items
val_debt = m.series("Valuation date total debt", notes[2])
val_cash = m.series("Valuation date cash", co.bs.cash[2])
val_net_debt = m.series("Valuation date net debt", val_debt - val_cash)
terminal_ufcf = m.series("Terminal year UFCF (FY2029E)", ufcf[7])
terminal_ebitda = m.series("Terminal year EBITDA (FY2029E)", ebitda[7])
tv_disc_factor = m.series("Terminal value discount factor (Yr 5)", 1 / (1 + wacc) ** 5)

# Method 1: Perpetuity Growth Method (PGM)
tv_pgm = m.series("Terminal value (PGM)", terminal_ufcf * (1 + term_growth) / (wacc - term_growth))
pv_tv_pgm = m.series("PV of terminal value (PGM)", tv_pgm * tv_disc_factor)
ev_pgm = m.series("Implied enterprise value (PGM)", sum_pv_ufcf + pv_tv_pgm)
eq_pgm = m.series("Implied equity value (PGM)", ev_pgm - val_debt + val_cash)
price_pgm = m.series("Implied share price (PGM)", (eq_pgm / MM) / diluted_shares)
upside_pgm = m.series("Implied upside (PGM)", price_pgm / current_price - 1)
tv_pct_pgm = m.series("TV % of EV (PGM)", pv_tv_pgm / ev_pgm)
implied_mult_pgm = m.series("Implied exit EV / EBITDA (PGM)", tv_pgm / terminal_ebitda)

# Method 2: Exit EV / EBITDA Multiple Method (EMM)
tv_emm = m.series("Terminal value (EMM)", terminal_ebitda * exit_mult)
pv_tv_emm = m.series("PV of terminal value (EMM)", tv_emm * tv_disc_factor)
ev_emm = m.series("Implied enterprise value (EMM)", sum_pv_ufcf + pv_tv_emm)
eq_emm = m.series("Implied equity value (EMM)", ev_emm - val_debt + val_cash)
price_emm = m.series("Implied share price (EMM)", (eq_emm / MM) / diluted_shares)
upside_emm = m.series("Implied upside (EMM)", price_emm / current_price - 1)
tv_pct_emm = m.series("TV % of EV (EMM)", pv_tv_emm / ev_emm)
implied_g_emm = m.series("Implied perpetual growth (EMM)", (tv_emm * wacc - terminal_ufcf) / (tv_emm + terminal_ufcf))

# Checks
m.check(wacc > term_growth + 0.01, "WACC > Terminal growth rate")
m.check(ufcf.where(m.is_forecast, 1 * MM) > 0 * USD, "Forecast UFCF > 0")

# Indirect CF rows (for complete 3-statement check tie-out with zero Model sheet)
cf_ni = m.series("Net income (CF)", co.pl.net_income.where(m.is_forecast, 0 * USD))
cf_da = m.series("D&A (CF)", da.where(m.is_forecast, 0 * USD))
cf_nwc = m.series("Change in NWC (CF)", change_nwc)
cf_capex = m.series("CapEx (CF)", ufcf_capex)
net_cash_chg = m.series("Net change in cash", co.cf.operating + co.cf.investing + co.cf.financing)
beg_cash = m.series("Beginning cash", co.bs.cash.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))
end_cash = m.series("Ending cash", (beg_cash + net_cash_chg).where(m.is_forecast, co.bs.cash))
total_liab_equity = m.series("Total liabilities & equity", co.bs.total_liabilities + co.bs.total_equity)
bs_check = m.series("Balance check", co.bs.total_assets - total_liab_equity)
ppe_open_s = m.series("Beginning PP&E", ppe.lag(1, fill=0 * USD).where(m.is_forecast, 0 * USD))

# ---- Live 2D Sensitivity Axes (Implied Share Price) ---------------------------------
# Row headers are live WACC formulas centered on active WACC; col headers are numeric g / Exit Multiple!
WACC_ROWS = (wacc - 0.010, wacc - 0.005, wacc, wacc + 0.005, wacc + 0.010)
G_STEPS = (0.020, 0.025, 0.030, 0.035, 0.040)
MULT_STEPS = (11.5, 12.5, 13.5, 14.5, 15.5)


def _pv_ufcf_at(w_expr):
    return (
        ufcf[3] / (1 + w_expr) ** 0.5
        + ufcf[4] / (1 + w_expr) ** 1.5
        + ufcf[5] / (1 + w_expr) ** 2.5
        + ufcf[6] / (1 + w_expr) ** 3.5
        + ufcf[7] / (1 + w_expr) ** 4.5
    )


def _dcf_pgm_price(w_s, g_val):
    tv_cell = terminal_ufcf * (1 + g_val) / (w_s - g_val)
    ev_cell = _pv_ufcf_at(w_s) + tv_cell / (1 + w_s) ** 5
    return ((ev_cell - val_debt + val_cash) / MM) / diluted_shares


def _dcf_emm_price(w_s, m_val):
    tv_cell = terminal_ebitda * m_val
    ev_cell = _pv_ufcf_at(w_s) + tv_cell / (1 + w_s) ** 5
    return ((ev_cell - val_debt + val_cash) / MM) / diluted_shares


def build_sheets():
    """Return the IB-grade DCF valuation workbook layout (zero Model sheet)."""
    return [
        b.sheet("Summary", [
            b.panel("DCF Valuation Summary (FY2024A Valuation Date)", ["Perpetuity Growth", "Exit Multiple"], [
                ("PV of Explicit UFCF (FY25E–FY29E)", [sum_pv_ufcf, sum_pv_ufcf], {"fmt": ["money", "money"]}),
                ("PV of Terminal Value", [pv_tv_pgm, pv_tv_emm], {"fmt": ["money", "money"]}),
                ("Implied Enterprise Value ($mm)", [ev_pgm, ev_emm], {"total": True, "fmt": ["money", "money"]}),
                ("Terminal Value % of EV", [tv_pct_pgm, tv_pct_emm], {"fmt": ["percent", "percent"]}),
                ("Less: Valuation Date Total Debt", [-val_debt, -val_debt], {"fmt": ["money", "money"]}),
                ("Plus: Valuation Date Cash", [val_cash, val_cash], {"fmt": ["money", "money"]}),
                ("Implied Equity Value ($mm)", [eq_pgm, eq_emm], {"total": True, "fmt": ["money", "money"]}),
                ("Diluted Shares (millions)", [diluted_shares, diluted_shares], {"fmt": ["days", "days"]}),
                ("Implied Share Price ($)", [price_pgm, price_emm], {"total": "grand", "fmt": ["price", "price"]}),
                ("Current Share Price ($)", [current_price, current_price], {"fmt": ["price", "price"]}),
                ("Implied Upside / (Downside)", [upside_pgm, upside_emm], {"bold": True, "fmt": ["percent", "percent"]}),
                ("Cross-Check: Implied Exit Multiple / g", [implied_mult_pgm, implied_g_emm],
                 {"fmt": ["multiple", "percent"]}),
            ]),
            b.sensitivity(
                "Sensitivity: Implied Share Price — WACC vs. Terminal Growth Rate (PGM)",
                WACC_ROWS,
                G_STEPS,
                _dcf_pgm_price,
                fmt="price",
                row_fmt='"WACC "0.0%',
                col_fmt='"g = "0.0%',
                highlight=(2, 2),
                corner="WACC \\ g",
            ),
            b.sensitivity(
                "Sensitivity: Implied Share Price — WACC vs. Terminal EV / EBITDA (Exit Multiple)",
                WACC_ROWS,
                MULT_STEPS,
                _dcf_emm_price,
                fmt="price",
                row_fmt='"WACC "0.0%',
                col_fmt='"Exit "0.0"x"',
                highlight=(2, 2),
                corner="WACC \\ Exit",
            ),
        ]),
        b.sheet("DCF", [
            b.section("Unlevered Free Cash Flow (UFCF) Schedule", [
                b.link(revenue, "Revenue"),
                b.link(rev_growth_disp, "% growth", fmt="percent"),
                b.link(ebitda, "EBITDA", total=True),
                b.link(ebitda_margin, "% margin", fmt="percent"),
                b.row(ebit_fcst, "Operating income (EBIT)"),
                b.row(unlevered_tax, "Less: Taxes on EBIT"),
                b.block(
                    ufcf,
                    [
                        b.row(nopat, "NOPAT", total=True),
                        b.row(ufcf_da, "Plus: Depreciation & amortization"),
                        b.row(ufcf_capex, "Less: Capital expenditures"),
                        b.row(change_nwc, "Less: Change in NWC"),
                    ],
                    label="Unlevered free cash flow (UFCF)",
                    total="grand",
                ),
            ]),
            b.section("Discounting (Mid-Year Convention)", [
                b.row(disc_period, "Discount period (years)", fmt="days"),
                b.row(disc_factor, "Discount factor", fmt="percent"),
                b.row(pv_ufcf, "Present value of UFCF", total=True),
            ]),
            b.panel("WACC Build-Up (CAPM)", ["Value"], [
                ("Risk-Free Rate (10Y UST)", [rf_rate], {"fmt": "percent"}),
                ("Equity Risk Premium (ERP)", [erp], {"fmt": "percent"}),
                ("Levered Beta", [beta], {"fmt": "days"}),
                ("Cost of Equity (Ke)", [cost_of_equity], {"total": True, "fmt": "percent"}),
                ("Pre-Tax Cost of Debt (Kd)", [pretax_kd], {"fmt": "percent"}),
                ("After-Tax Cost of Debt", [aftertax_kd], {"fmt": "percent"}),
                ("Target Debt Weight", [debt_weight], {"fmt": "percent"}),
                ("Target Equity Weight", [equity_weight], {"fmt": "percent"}),
                ("Weighted Average Cost of Capital (WACC)", [wacc], {"total": "grand", "fmt": "percent"}),
            ]),
        ]),
        b.sheet("Operating", [
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
                b.row(co.pl.net_income, "Net income", total="grand"),
                b.row(ebitda, "EBITDA (memo)", total=True),
                b.row(ebitda_margin, "% EBITDA margin", fmt="percent"),
            ]),
            b.section("Balance Sheet", [
                b.row(co.bs.cash, "Cash & cash equivalents", formula=end_cash),
                b.row(nwc_bs, "Operating net working capital"),
                b.row(ppe, "PP&E, net", formula=ppe_open_s + capex - da),
                b.row(co.bs.total_assets, "Total assets", total="grand"),
                b.row(notes, "Senior notes"),
                b.row(co.bs.total_liabilities, "Total liabilities", total=True),
                b.row(common_stock, "Common stock & APIC"),
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
            b.section("Cash Flow Statement", [
                b.block(
                    co.cf.operating,
                    [b.row(cf_ni, "Net income"), b.row(cf_da, "Depreciation & amortization"), b.row(cf_nwc, "Change in NWC")],
                    label="Cash flow from operations",
                ),
                b.block(co.cf.investing, [b.row(cf_capex, "Capital expenditures")], label="Cash flow from investing"),
                b.row(co.cf.financing, "Cash flow from financing"),
                b.row(net_cash_chg, "Net change in cash", total=True),
                b.row(beg_cash, "Beginning cash"),
                b.row(end_cash, "Ending cash", total="grand"),
            ]),
            b.section("PP&E Schedule", [
                b.row(ppe_open_s, "Beginning PP&E, net"),
                b.row(capex, "Capital expenditures"),
                b.link(da, "Less: Depreciation & amortization"),
                b.link(ppe, "Ending PP&E, net", total=True),
            ]),
        ]),
    ]


r = m.render()


def export_ib_workbook(out_path: Path):
    """Export the full IB-grade DCF valuation workbook with live scenarios and zero Model sheet."""
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
    print(f"=== {m.name} (WACC {r[wacc]*100:.2f}%, Current ${r[current_price]:.2f}) ===")
    for name in ("Base", "Bull", "Bear"):
        res = m.render(scenario=None if name == "Base" else name)
        p_pgm = res[price_pgm]
        p_emm = res[price_emm]
        u_pgm = res[upside_pgm] * 100
        u_emm = res[upside_emm] * 100
        print(f"  {name:4s} | PGM ${p_pgm:6.2f} ({u_pgm:+5.1f}%) | Exit Mult ${p_emm:6.2f} ({u_emm:+5.1f}%)")
    if len(sys.argv) > 1:
        out_dir = Path(sys.argv[1])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "veridian_dcf.xlsx"
        report = export_ib_workbook(out_file)
        print(f"\nExported: {out_file}")
        print(f"Report: {report}")
        print(f"Unplaced Model rows: {report.unplaced}")
