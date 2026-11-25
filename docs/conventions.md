# Conventions

2026-10-17. These conventions standardize patterns that varied across 38 plans in three sweeps. New plans and library code follow them.

## Time points and discounting

- **Flows occur at the end of each period.** `discount(r)` returns the end-of-period discount factor. The first period uses `1 / (1 + r)`.
- **`npv(cf, r)` returns the value at the model start**, as Excel's `NPV()` does. `npv(cf, r, at=0)` returns the value at the end of period 0. Pass a one-time flow at the model start, such as an investment, with `initial=`. `irr(cf, initial=)` works the same way.
- **A discount rate that changes by period is a series:** `npv(cf, wacc)` discounts each flow by the product of `1 + wacc` up to its period, the factor `discount(wacc)` gives. Do not build the cumulative factor by hand. Excel gets `SUMPRODUCT` of the flows and the `discount(wacc)` row; a constant rate keeps `NPV()`.
- If the source sheet passes the year-0 investment to `NPV()` and discounts the entire result by one extra period, note that behavior and divide by `(1 + r)` to match it.

## Handle year 0

**Create a period only when something happens during it.** A point-in-time event is not a period.

| Source model | boki representation | Examples |
|---|---|---|
| A balance sheet exists at acquisition or founding, and operations start in year 1 | Start periods in year 1. Record the transaction at `bs.opening(...)`. | LBO test, hotel |
| Year 0 contains only an investment in a cash-flow-only model | Start periods in year 1. Pass the investment to `npv(..., initial=)` or `irr(..., initial=)`. | Sponsor IRR in LBO, CREST |
| Something happens during year 0, such as construction | Include year 0 as a period. | SAM (construction year) |
| An analysis values year 0 as a decision point and includes multiple year-0 flows | Include year 0 as a period and use `npv(..., at=0)`. | capbudg |

## Count years and periods

- Keys in `b.by_year({0: ...})` are **zero-based model years**, independent of period length. `m.t` is also the zero-based period index.
- The source label `1年目` ("Year 1") maps to `m.t == 0`. Write `years = m.t + 1` when a formula needs the year number.

## Signs

- Write amounts as positive numbers. Record expenses as positive values on expense rows such as `pl.cogs`. If the source sheet stores expenses as negative values, compare against `-x` during verification, as in `{-capex: s.row(92, "H", "Q")}`.
- For borrowing, `draw_or_repay` is positive when drawing and negative when repaying.

## Units

- Declare an entity's currency with `m.entity(..., currency=JPY)`, or let the first posted amount set it. Once set, the currency also determines the units of subtotal rows such as `pl.operating_income`. boki checks formulas derived from those rows.
- If an expected value in a comparison includes a unit, boki compares values in that unit, as in `28_032_000 * kWh`. Bare numbers use base units (dollars, Wh, and months).

## Cycles and goal seek

- `m.solve(u, u == expression)` runs fixed-point iteration. An equation whose left side is not an unknown, such as `m.solve(u, npv(...) == 0)`, performs scalar goal seek.
- **Excel counts both branches of a `where`.** A model that is acyclic in boki can be circular in Excel; `to_excel` guards the fewest cells with `NA()` and warns ([excel.md](excel.md#circular-references-boki-does-not-have)). Do not rewrite a correct model to avoid the warning.
- **Cycles with multiple solutions**, such as a cycle between ratings and interest rates, use the initial value from `m.unknown(init=)`. Start from the conservative case (the interest rate for the worst rating) and note that choice in the plan (APV).

## Sensitivity tables and scenario columns

- Render the model repeatedly with different inputs: `for v in grid: m.render(inputs={pe: v})`. Keys in `inputs=` must be input nodes or names. Unknown keys raise an error.

## Compare results with the source

- `b.compare(r, {...})` lists every number with its difference. `b.expect(r, {...})` fails when values differ. Pass a list of period values for a series, as in `{co.bs.cash: s.row(23, "C", "G")}`: one value per period, or `ValueError`; `None` skips a period the source has no value for. Dates (`m.date`) compare as dates; a cell read as a datetime at midnight counts as that date. A constant series compares with a list of period values as it is: do not pad it with `m.t * 0`.
- Compare the model with `b.expect`, not a plain `assert`, so a mismatch lists every number. When the source gives a rounded figure or a range, use `b.approx(1.34, tol=0.005)`, `b.above(0.5)`, `b.below(x)` or `b.between(lo, hi)` for that key. A plain `assert` is for checks on the source itself (its own totals add up), not on the model.
- **Write the model correctly and document source errors or mismatches in the plan.** Post a balancing amount as a journal entry named after the source's own note, add the difference to an expected value, or add a note. Do not write an incorrect formula to match the source.
