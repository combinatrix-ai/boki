# Investment-Banking LBO Model (Apex Precision Manufacturing)

Benchmark #2 for Investment Banking-grade financial modeling in `boki`: a 5-year middle-market Leveraged Buyout (`FY2025E–FY2029E`, US GAAP, `$mm`) featuring full transaction structuring, multi-tranche debt with excess cash flow sweep, indirect cash flow statement, sponsor IRR/MoIC returns, and live 2D sensitivity tables.

```
uv run python examples/ib_lbo/plan.py out/         # Print Base/Bull/Bear returns and write apex_lbo.xlsx
uv run python tools/excel_check.py examples/ib_lbo # Verify recalculation against boki (zero mismatches)
```

## Model architecture

- **Transaction Structuring (`Transaction` sheet)**: Live `b.panel` tables for Sources & Uses (Term Loan A 3.0x, Term Loan B 2.5x, Sponsor Common Equity), Goodwill creation, and Opening Pro Forma Balance Sheet — all updating dynamically from `Inputs`.
- **Multi-Tranche Debt Waterfall (`Debt` sheet)**: Scheduled mandatory amortization (TLA 5%/yr, TLB 1%/yr) plus a 100% Excess Cash Flow Sweep that pays down Term Loan A first and then Term Loan B, with interest on opening balances (zero circularity).
- **Verified 3-Statement Integration (`IS`, `BS`, `CF`)**: Full indirect Cash Flow Statement via verified `b.block`, direct BS links (`Cash = CF!Ending cash`, `TLA`/`TLB` from `Debt`, `Retained earnings = Prior + NI`), and zero `Model` sheet (`omit_unused_model=True`).
- **Sponsor Returns & 2D Sensitivities (`Returns` sheet)**: Exit Valuation Bridge, Sponsor IRR / MoIC, and live Excel-formula 2D sensitivity matrices (Entry Multiple × Exit Multiple) with Base-case cell highlighting.
- **Live Scenario Switch (`Inputs!$C$3`)**: Switching `1 = Base`, `2 = Bull`, `3 = Bear` dynamically recalculates all 7 sheets including debt sweep, returns, and sensitivity tables.
