# Investment-Banking 3-Statement Operating Model (Acme Industrial Corp.)

Benchmark #1 for Investment Banking-grade financial modeling in `boki`: an integrated 3-statement operating model spanning **3 historical actual years (`2022A–2024A`)** and **5 forecast years (`2025E–2029E`)**, US GAAP, `$mm`.

```
uv run python examples/ib_3statement/plan.py out/         # Print Base/Bull/Bear summary and write acme_ib_3statement.xlsx
uv run python tools/excel_check.py examples/ib_3statement # Verify recalculation against boki (zero mismatches)
```

## Model architecture

- **Historical Actuals → Forecast handoff (`actual_until="2024"`)**: Historical IS and BS actuals are validated for balance sheet identity (`Assets == Liabilities + Equity`), rendered as blue hardcoded inputs with `FY2022A–FY2024A | FY2025E–FY2029E` headings and a vertical boundary border, and closing `2024A` balances automatically seed `2025E` opening balances.
- **Live Excel Scenario Switch (`scenarios=["Base", "Bull", "Bear"]`)**: Changing `Inputs!$C$3` (`1 = Base, 2 = Bull, 3 = Bear`) dynamically recalculates every sheet in Excel via `=INDEX(...)`, with source citations in the `Source` column.
- **Proof-Carrying Excel Rewrites**:
  - `CF` renders a full **Indirect Cash Flow Statement** via `b.block(co.cf.operating, [...])`, `b.block(co.cf.investing, [...])`, and `b.block(co.cf.financing, [...])`, each writing `=SUM(...)` after boki verifies equivalence across Base, Bull, Bear, and perturbed inputs.
  - `BS` Cash (`=CF!Ending cash`), PP&E (`=Beginning + CapEx - D&A`), Term Loan (`=Beginning - Amortization`), and Retained Earnings (`=Prior + Net Income - Dividends`) use perturbation-verified `b.row(..., formula=...)`.
- **Executive Summary & 2D Panel**: `Summary` combines key financial/credit KPIs with a live `b.panel` FY2029E Valuation & Credit Bridge.
- **Zero `Model` Sheet**: Exported with `omit_unused_model=True, statements=False, checks=True` (`report.unplaced == []`), leaving only `Inputs`, `Summary`, `IS`, `BS`, `CF`, `Schedules`, and `Checks`.
