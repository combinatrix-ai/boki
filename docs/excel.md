# Excel output

2026-10-17. This document records the prototype and conclusions for the open requirement to export Excel tables while retaining as many formulas as possible with `r.to_excel("model.xlsx")` (`boki.excel`).

## What to write

- **Inputs sheet:** Lists `m.input` values by name, unit, and value. The model parameters become the input sheet.
- **Model sheet:** Each named series gets a row, and each period gets a column. Cells contain formulas that refer to other rows and input cells. Header rows separate the model, each entity's P&L/BS/CF, journal entries, and helper rows.
- **P&L, BS, and CF sheets for each entity:** Tables refer to rows on the Model sheet. BS totals use `SUM`.
- **Report return value:** Counts formula cells, data cells (blue), and cells written as values (yellow, with a reason).

## Generate formulas

boki series are expression trees, so Excel formulas can be generated directly from those trees.

| boki expression | Excel output |
|---|---|
| Named series, entity rows, and balances | Referenced rows |
| Unnamed subexpressions | Expanded in formulas. Expressions used at least twice get helper rows. |
| `x.lag(k, fill=)` | Cell `k` columns earlier, or `fill` outside the range. A series `k` becomes `INDEX` over the row. |
| `where` (on the calendar alone: only the branch taken; see below for branches that would be circular), `b.min`, `b.max`, `b.round`, `b.rounddown`, `b.roundup`, `b.floor`, `%`, `//`, `b.exp`, `b.log`, `b.sqrt`, comparisons, and logic | `IF`, `MIN`, `MAX`, `ROUND`, `ROUNDDOWN`, `ROUNDUP`, `INT`, `MOD`, `EXP`, `LN`, `SQRT`, `AND`, and related functions |
| Recurrences (`compound`, `cumsum`, `discount`, balances, loss carryforwards, depreciation, and series defined with their own lag) | Reference the same row in the previous column |
| `.sum()`, `.mean()`, `npv`, and `irr` | `SUM`, `AVERAGE`, `NPV`, and `IRR` over a row range; with `year=y`, over that year's cells |
| Ledger balances | Opening balance (or previous column) plus the sum of journal-entry rows posted to the account |
| `by_year`, `step`, `m.series(data=)`, dates, and period lengths | Data values (blue) |
| `lookup(x, table)` | The table as two rows on the Inputs sheet (`<row> table: from` with the keys, `<row> table` with the values) and `LOOKUP(x, keys, values)`; a table whose values are not constants is a value cell |
| Python functions decorated with `@m.series` and solutions from `m.solve` | Values (yellow) with a comment explaining why |

A reduction's formula is one operand: `a / npv(cf, r, at=0)` divides by the whole `((c0+NPV(r,cf))*(1+r)^(at+1))`.

Boolean rows use 1 or 0 because Excel `SUM` ignores `TRUE` and `FALSE` in a range. Dates use `DATE()`, month arithmetic uses `EDATE()`, days are added to a date cell as numbers, the days between two dates are their difference (`=C5-C4`), and `.year`/`.month` are `YEAR()`/`MONTH()`. `xirr` and `xnpv` are `XIRR` and `XNPV` over the rows.

## Circular references boki does not have

boki evaluates a cell from the cells it reads in that period: the branch of a `where` that is taken, the one period an `x[k]` or `x.lag(k)` with an input `k` picks. Excel's dependency graph counts every reference in a formula: both branches of `IF`, and every cell of the row `INDEX` picks from. A model can therefore be acyclic in boki and circular in Excel. A sculpted loan is the usual case: CFADS includes the equity and debt drawn in construction, the drawdown includes a fee on the debt commitment, and the commitment is sized on `(cfads * factor).where(debt_period, 0).sum()`. boki never reads the construction years' CFADS; Excel's `IF(debt_period, cfads*factor, 0)` refers to them, and fee -> commitment -> NPV -> CFADS closes a loop.

**Exported workbooks have no circular reference that boki does not have.** `to_excel` writes every Model cell once while recording what its formula refers to, and, separately, what each part that boki does not read in that period refers to (an `IF` branch not taken, the rest of a row an `INDEX` picks from). In each loop of the resulting cell graph (a strongly connected set of cells), every unread part that refers back into the loop is guarded; then each guard is lifted again, in a fixed order (rows with the most guarded parts first, then row, period and position in the formula), unless lifting it would close a loop. The guards that remain are a minimal set (removing any one makes Excel circular), usually the masked periods of the reduction the loops pass through. The result is the same for the same model.

A guarded part is written as `NA()`, and its cell is shaded orange with a note:

```
=IF(AND((YEAR(C4)>=Inputs!$C$4),...),NA(),0)                        a masked period of the NPV of CFADS
=IF((F4>Inputs!$C$3),(IF(IF(Inputs!$C$3<0,6+Inputs!$C$3,Inputs!$C$3)+1=3,E7,NA())/3),0)
                     balance[cod] / 3, where INDEX over the balance row would be circular: the one cell, if cod still points at it
```

The cell keeps its live condition and the formula for what boki reads, so with the exported inputs every cell recalculates to boki's value. If a changed input in the workbook makes a guarded cell read the guarded part (the opening year moves the debt period), the cell shows `#N/A` and so do the cells that use it, instead of a wrong number; export again from boki for those inputs. `to_excel` warns (`boki.excel.CircularReferenceWarning`) with the guarded cells, and the report counts them (`report.guarded`).

Why not the other designs: writing a value where a loop closes (as for `@m.series`) freezes the cell for every input, not only for the inputs that would read the guarded part, and goes stale silently. Writing only the branch boki takes for every condition on inputs (as for conditions on the calendar alone, which never change) would also go stale silently when an input moves a period across the condition, and in every cell, not only where a loop needs it. Limiting a reduction's range to the periods it reads fails the same way when the periods depend on an input. Guarding only the parts that close a loop keeps every other formula whole, and makes the one way the workbook can go wrong visible.

A loop that remains after every unread part is guarded is boki's own: boki would report it as a `CycleError` if that cell were evaluated. The warning names it and the workbook keeps it.

## Verification

`tools/excel_check.py` recalculates the exported workbook with `formulas`, a development dependency that evaluates Excel formulas in Python, then compares every formula cell on the Model sheet with boki's value. It compares the P&L sheet with boki's P&L and checks `assets = liabilities + equity` for every period on the BS sheet. Run all plans with `research/tools/excel_all.py`.

Results for 38 plans: 30,538 formula cells, 6,258 data cells, and 578 cells written as values (1.8%). There were no mismatches.

Issues found and fixed: division applied before a sum was parenthesized (operator precedence); `SUM` ignored booleans; `SUM` over empty ranges; sheet names containing apostrophes in entity names; and internal Python functions for loan principal, depreciation, loss carryforwards, sale proceeds, and construction-in-progress depreciation were replaced with nodes that can be translated to formulas.

## Do we need a more complex DSL?

The user asked on 2026-10-16, "To export to Excel and retain as many formulas as possible, it seems we may need a more complex DSL than `@m.series`."

**Most expressions can be exported as formulas as written.** The main remaining use for `@m.series` was recurrences that refer to their previous period. Define those by declaring the series and then using its own `lag`.

```python
nol = m.series("NOL")
prev = nol.lag(1, fill=0 * JPY)
nol.define(prev + b.max(-ebit, 0) - b.min(b.max(ebit, 0), prev))
```

The recurrences in Ginzu, Janz, and Bodmer were rewritten this way. Their values still match, and Excel formulas now refer to the previous column.

**The remaining value cells** come mostly from `@m.series` functions on dates in plans written before `lookup`, `m.date.year`/`.month` and day counts were written as formulas. Keep `@m.series` as an escape hatch for calculations that cannot become formulas, and mark their cells as values.

## Open questions for the next Excel export work

1. **Display units:** Values use base units (dollars and Wh). Add a display unit per row to show amounts in millions of yen or kWh.
2. **Choose which rows to show:** Export every named series now. Decide how to add minimal options, such as hiding helper rows and setting row order and headings.
3. **Sensitivity tables:** Choose between Excel data tables and scenario columns for repeated renders with different inputs.
4. **Accounting presentation:** P&L, BS, and CF sheets follow the order from boki's `r.pl()`. There is no option to match the source Excel layout, such as account names and subtotal positions.
