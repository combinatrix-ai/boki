# Neocloud (GPU cloud) business plan

2026-10-19. First plan written from scratch in boki (`plan.py`), rather than ported from an existing Excel workbook. **All figures are placeholders and have not been researched.**

```
uv run python examples/neocloud/plan.py [out-dir]     # Print results and write neocloud.xlsx if out-dir is provided.
uv run python tools/excel_check.py examples/neocloud   # Recalculate Excel and compare with boki (zero mismatches).
```

## Model scope

- 120 monthly periods (2026-10 to 2036-09), one entity (US GAAP, USD, December year-end).
- Data center: lease 10 MW for 10 years ($140/kW/month, payable whether used or not). Corporate overhead: $0.3mm/month.
- Clusters: create one Python `Cluster` object per generation. Order → delivery in 5 months → operation 1 month later. Pay 20% of hardware cost at order and 80% at delivery; depreciate over 6 years from operation (construction in progress before then).
  - Customer contracts: 3-year take-or-pay. Receive a 15% advance against total contract value at order and deduct it from monthly invoices. Cash arrives the following month.
  - After the contract: market price (scenarios: base $2.35, bear $1.40/GPU-h) × utilization (70%).
  - Power: 1.4 kW/GPU × PUE 1.25 × $0.08/kWh. Operating cost: $60/GPU/month.
  - Debt: the lower of the present value of contract CFADS ÷ DSCR 1.3 (sculpted) and 90% of hardware cost. Draw at delivery. Interest is SOFR + 5.5%; undrawn fee is 0.5%. Repay in line with contract cash flow, with a bullet at maturity (5 years).
- Cash flow: DSRA (next 6 months of principal and interest); contribute equity as needed to maintain minimum cash ($2mm); distribute cash above the minimum after all clusters are online when DSCR ≥ 1.2.
- Outputs: required equity, debt and LTV, DSCR, sponsor IRR, cost per GPU-hour, annual commitment ladder, sensitivity (market price × utilization), and banker-style Excel with $mm and fiscal-year columns.

## Results (placeholder assumptions)

| | |
|---|---|
| Required equity | $64.3mm |
| Debt | batch1 $35.9mm (LTV 70%), batch2 $87.4mm (LTV 71%) |
| Minimum company-wide DSCR (after all clusters are online) | 0.91 |
| Sponsor IRR (annualized) | 15.4% |
| batch2 cost per GPU-hour (at $3.50 price) | $1.94 (depreciation 1.14, DC rent 0.34, interest 0.24, power 0.14, operations 0.08) |

Sensitivity (post-contract market price × utilization):

| | 50% | 70% | 90% |
|---|---|---|---|
| base: required equity / IRR | 64.3 / 2.3% | 64.3 / 15.4% | 64.3 / 23.3% |
| bear: required equity / IRR | 96.9 / −96% (most equity is lost) | 64.3 / −12.3% | 64.3 / 3.5% |

Observations from the model (under placeholder assumptions):

**Customer advances reduce debt.** A 15% advance leaves 85% of monthly invoices for collection, reducing debt sized from contract CFADS (LTV falls from about 86% to 70%). This became clear when sizing debt against all revenue failed to match the concept note's estimate that prepayment would reduce LTV to about 65%.
- **Even with each cluster sized at 1.3 DSCR, company-wide DSCR falls below 1.3 (to 0.91).** The company leases 10 MW but GPUs use only about 5.4 MW, so unused capacity rent (about $0.64mm/month) and corporate overhead are excluded from cluster debt sizing. A lender underwriting company-wide CFADS would size less debt.
- **Required equity is determined by the cash trough during construction and barely changes with post-contract market price or utilization.** Only the bear × 50% case needs more equity to cover post-contract losses.
- **Operations remain loss-making after the contract until depreciation ends.** Under the base case, EBIT is negative in FY2031–FY2033. The contract lasts 3 years versus 6 years of depreciation, so the depreciation-life question flows directly into P&L.

## Findings about boki

Fixed issues:

1. **Bug:** Passing a period index to `complete_at=` for construction in progress caused depreciation units to become USD × month and fail; passing a date worked. Fixed.
2. **Excel-output bug:** Before operation, the depreciation formula referenced the pre-operation book value in an unused branch. Excel counts references in unused branches as dependencies, creating a circular reference that prevented all downstream calculations (boki does not evaluate unused branches). When a condition depends only on a period index and a constant, output now includes only the active branch. Also made one value cell with variable lag a formula in the 38-plan corpus.
3. **Monthly three-statement output was unreadable:** fitting 120 columns to a page made the text illegible. Statements now use fiscal-year columns (sum flows over the year and show ending balances). Keep the previous layout with `columns="periods"`.

Works, but these may merit reduction:

- **Forward-declaration pattern:** dividends and equity contributions depend on cash before distributions, so declare series with `m.series` and define them later. `before = cash.opening + cf.operating + cf.investing + cf.financing_excluding(...)` is a third example after Bodmer and ecommerce. Could become a waterfall (priority allocation) function.
- **Manual debt sculpting:** `(target_ds * df).sum() / df[delivery]`. This is the second example after Bodmer, so `lib.sculpt` may be useful.
- **Goal seeking silently returned a non-unique solution:** initially solved equity with `m.solve(equity, cash.min() == min_cash)`, but because all cash above the minimum is distributed, the equation holds for any equity amount and iteration stopped near the initial value. Consider a warning when the equation is insensitive to an unknown near the solution.
- **Customer advances appear as negative receivables in the Excel BS.** `r.bs()` presents them as customer advances, but Excel output does not.
- **DSCR when there is no debt:** used `.where(debt_service > 0, 99)` as a sentinel value. A better ratio API could leave periods with a zero denominator blank.
- Python classes were enough for templates and instances; no new syntax was needed. Milestones (order → delivery → operation) used period-index arithmetic.

Not yet modeled: leasing instead of owning hardware (replace the asset/debt combination with a lease), renewal contracts that lock in the market price at contract end, tax depreciation separate from book depreciation, and a web interface.
