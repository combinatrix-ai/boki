# Investment-Banking DCF Valuation Model (Veridian MedTech Inc.)

Benchmark #3 for Investment Banking-grade financial modeling in `boki`: a public-equity Discounted Cash Flow valuation spanning **3 historical actual years (`2022A–2024A`)** and **5 explicit forecast years (`2025E–2029E`)**, US GAAP, `$mm`.

```
uv run python examples/ib_dcf/plan.py out/         # Print Base/Bull/Bear implied share prices and write veridian_dcf.xlsx
uv run python tools/excel_check.py examples/ib_dcf # Verify recalculation against boki (zero mismatches)
```

## Model architecture

- **CAPM WACC Build-Up (`DCF` sheet)**: Risk-free rate, ERP, Levered Beta, After-Tax Cost of Debt, and target capital structure weights combining into live WACC.
- **Unlevered Free Cash Flow & Mid-Year Discounting (`DCF` sheet)**: Explicit NOPAT → +D&A → -CapEx → -ΔNWC build verified via `b.block`, discounted on a mid-year convention (`0.5, 1.5, 2.5, 3.5, 4.5` years).
- **Dual Terminal Value & Cross-Checks (`Summary` sheet)**: Side-by-side comparison of **Perpetuity Growth Method (PGM)** and **Exit EV / EBITDA Multiple Method** with EV-to-Equity bridge, Implied Share Price, Upside/(Downside), and cross-check implied exit multiple / implied growth rate.
- **Live 2D Sensitivity Tables (`Summary` sheet)**: `WACC × Terminal Growth Rate` and `WACC × Terminal EV / EBITDA Multiple` matrices computing Implied Share Price via live closed-form Excel formulas with Base-case cell highlighting.
- **Integrated 3-Statement Operating Support (`Operating` sheet) & Zero `Model` Sheet**: Full historical-to-forecast IS, BS, and indirect CF tie-out verified inline on `Checks`, with `omit_unused_model=True` (`report.unplaced == []`).
