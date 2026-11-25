# Excel presentation

## Decisions and implementation status (2026-10-18)

- The user asked, "Could we handle Excel's appearance with `to_excel`?" Put all presentation options in `to_excel` arguments. Drop `m.series(..., show=)` from the proposal below and use `to_excel(units={series: unit}, hide=[series])`. Keep `actual_until` on the model because it describes which periods are actuals. If boki adds other export formats, move shared presentation options into a separate value such as `b.view(...)`.
- The user said, "Let's use banking style for all presets. Go ahead; parentheses are fine, and the rest can follow your proposal." Use `banker` by default for every accounting standard. Show expenses as negative values in parentheses.
- Implemented in `boki.styles` and `boki.excel`:
- Implemented in `boki.styles` and `boki.excel`:
  - `r.to_excel(path, style=b.styles.banker, **overrides)`. Presets are `banker` (default), `japanese`, and `plain` (the output through 2026-10-17). `b.styles.banker(money="$mm")` is equivalent to `.replace(...)`. Unknown settings and unsupported `money=` values raise errors.
  - Display units use `money=` with values such as `$mm`, `$000`, `millions JPY`, `thousands JPY`, `hundred millions JPY`, or a number. Statement sheets convert values with formulas such as `=Model!C12/1000000` and show captions such as `(in millions)` and `(in millions of yen)`. The Model sheet keeps values unchanged and uses number formats such as `#,##0,,` to show the same scale. `units={generation: MWh}` also uses number formats. Units must use powers of 1000.
  - Helper rows and series listed in `hide=` are grouped on the Model sheet (`helpers="group"`). Set `helpers="show"` to expand them.
  - The banker statements (IS, BS, and CF for each entity) link values to the Model sheet (green) and calculate totals and subtotals from other rows on the statement sheet (black). Expenses appear in parentheses. The statements show % growth under revenue, % margin under each profit subtotal, and the effective tax rate under income taxes. The BS has subtotals for current assets and liabilities, total assets, total liabilities, total equity, a double-ruled total liabilities and equity, and a balance check. The CF has three sections, exchange rates if present, net change, and beginning and ending cash. Period headings are numbers shown as `FY2027E` by number format (`"FY"0"E"_)`), or `Jan-27` for periods shorter than 12 months. The sheets have no gridlines, and input cells are blue.
  - Subtotals and account types use a table by language. English uses US GAAP terms; the Japanese-accounting preset uses translated English labels for Japanese GAAP classifications. boki also selects translated English names for automatic accounts such as cash, retained earnings, and receivables. User-defined names remain unchanged.
  - The `japanese` preset uses English labels, triangle negatives, positive expenses with subtotals subtracting, headings such as `Year ended December 2027`, and no ratio rows.
  - `tools/excel_check.py` also recalculates the three banker statements. It verifies that profit subtotals and ending cash match boki and that the balance check is 0 in every period. Across 38 plans, there were no mismatches in 30,543 formula cells.
- Not implemented: custom statements through `b.statement`, `b.schedule`, and `b.sheet`; Cover, Assumptions, and Checks sheets; actual-period columns (`actual_until`); sensitivity tables; and moving helpers to a separate sheet with `helpers="sheet"`.

---

The following is the 2026-10-17 proposal. The decision above replaces `show=`.

On 2026-10-17, the user said, "Display units are needed. Hiding helper rows makes sense. Presentation settings would be useful, such as investment-banking-style output and overrides. The output does not have to match the original Excel file. Think it through and make a proposal."

Example: `research/mock/banker_mock.py` contains Otis's three statements, with investment-banking-style IS and BS sheets and a Japanese-format income statement. The Model sheet keeps the current formula output, and the presentation sheets use formulas that refer to it. This mock checks the appearance; it is not a library API.

## Separate calculation from presentation

- **Calculation** stays on the current Model sheet in base units and formulas. Verify it by recalculating the workbook and comparing the results with boki.
- **Presentation** uses separate sheets that refer to calculation cells. These sheets handle unit conversion, signs, order, subtotals, ratio rows, colors, and number formats. Presentation changes do not affect calculations.
- Apply presentation settings in this order: **preset data, workbook-wide overrides, sheet settings, then row settings**. The preset alone should produce a usable table without extra flags.

## 1. Display units

```python
r.to_excel("plan.xlsx", style=b.styles.banker(money="$mm"))     # Show amounts in millions of dollars.
m.series("generation", capacity * cf * hours, show=MWh)          # Show this row in MWh; calculations remain in Wh.
```

- Use one money scale for the entire workbook with `money=`, such as `JPY`, `thousands JPY`, `millions JPY`, `$`, `$000`, or `$mm`. Add a heading such as `(in millions of yen)` or `(in millions of dollars)`.
- Specify display units for other quantities per row with `show=unit`. If you omit the setting, the preset supplies a default for each dimension, such as kWh for energy and months for time.
- In Excel, presentation sheets convert values with formulas such as `=Model!C12/1000000`. Calculation sheets keep base units. Number formats such as `#,##0,,` can also display powers of 1000, including on the Model sheet.
- Do not convert per-share values, ratios, or multiples. Use `%` and `x` number formats.

## 2. Hide helper rows

- By default, group and collapse helper rows (rows added for unnamed intermediate expressions) on the Model sheet. Expand them with Excel's plus sign. Formula references remain visible.
- Choose to move helpers to a separate Calc sheet or omit them and inline their formulas with `helpers="group" | "sheet" | "inline"`.
- Hide named series with `m.series(..., show=False)`.

## 3. Presentation presets

Store presets as data, like accounting layouts. Start with three presets.

| | `b.styles.banker` (investment banking) | `b.styles.japanese` (Japanese accounting) | `b.styles.plain` (current output) |
|---|---|---|---|
| Text colors | Inputs blue, formulas black, references to other sheets green | Inputs blue, formulas black | None |
| Negative values | (1,234) | △1,234 | -1234 |
| Zero | – | － | 0 |
| Expense sign | Show as negative in parentheses; add subtotals | Show as positive; subtract in subtotals | As in boki |
| Unit heading | ($ in millions, except per-share data) | (in millions of yen) | None |
| Period headings | FY2025A / FY2026E | Year ended March 2025 | 2025-04 |
| Ratio rows | Italic % growth under revenue and % margin under each profit subtotal | None by default | None |
| Totals | Top border and bold; double rule for the final total | Same | None |
| Account names | English (US GAAP terms) | Translated English labels for Japanese accounting classifications | Row names |
| Other | Hide gridlines, freeze headings and columns, add a BS check row | Same | Freeze panes only |

Override settings:

```python
style = b.styles.banker.replace(money="millions JPY", negatives="△", font="Meiryo", growth_rows=False)
r.to_excel("plan.xlsx", style=style)
```

## 4. Configure sheets and rows

**By default**, create P&L, BS, and CF sheets from each entity's accounting layout. Account types and profit subtotals become rows and totals. Presets add ratio rows.

**Specify only the changes you need:**

```python
r.to_excel("plan.xlsx", style=b.styles.banker(money="$mm"), sheets=[
    b.statement(co, "Income Statement", labels={"sga": "Operating expenses", "cogs": "Cost of sales"},
                hide=["other_expense"], detail=["revenue"]),      # Show revenue details only.
    b.schedule(co, "Debt Schedule", [debt]),                        # Opening balance, borrowing, repayment, interest, and closing balance.
    b.sheet("KPIs", [b.line(units, "Service units", show=unit_),
                     b.line(per_unit, "Revenue per unit"), b.ratio(margin, "EBIT margin")]),
])
```

- Row types are `line` (account), `total` (subtotal or total), `ratio` (% growth, % margin, or multiple), `header`, `gap`, and `check` (a comparison row that turns red when nonzero).
- Build custom sheets for KPIs, valuation, and assumption lists with the same components.
- `b.schedule` creates rows from the ledger, such as opening balance, borrowing, repayment, interest, and closing balance for debt. These are the "Debt Schedule," "PP&E Schedule," and "Working Capital" tables in investment-banking models.

## 5. Workbook layout (banker default)

Cover (entity name, date, notes, and input-color legend) → Assumptions (inputs by category, with units and sources) → IS → BS → CF → Schedules → Valuation (if present) → Checks (BS reconciliation and `m.check` results) → Model (calculations, with helper rows collapsed).

## 6. Actual and forecast columns

Set actual periods with `m.entity(..., actual_until="2025-03")`. Headings then use A/E for actual and estimate, and actual-period cells appear as inputs (blue). For models that forecast from the final actual year, such as Otis and ecommerce, show the opening BS in the final actual-year column.

## 7. Sensitivity tables

Excel data tables (`TABLE()`) can be exported, but the verification library cannot recalculate them. Start with a table of values calculated by boki and label it "Calculated by boki." Consider formula-based scenario columns later.

## Findings from the mock

- The generated statement showed Japanese names for automatic accounts such as cash and retained earnings, even for an English-language US GAAP company. Select account names by accounting standard and display language through the preset's account-name table.
- Comparing the mock with the source sheet exposed an error in my Otis plan: the lease-liability remeasurement counted the opening balance twice in year 1. I fixed it and added total assets to the reconciliation. A consistent presentation made the error easier to spot.

## Proposed implementation order

1. Add display units with `money=`, `show=`, and headings. Group helper rows.
2. Add `banker`, `japanese`, and `plain` presets and overrides with `replace`. Set colors, negative and zero formats, total borders, and period headings.
3. Add ratio rows and account names by standard and language to P&L, BS, and CF sheets generated from accounting layouts. Translate names for automatic accounts.
4. Add custom sheets with `b.statement`, `b.schedule`, and `b.sheet`.
5. Add Cover, Assumptions, and Checks sheets and actual-period columns.
6. Add sensitivity tables.

## Decisions requested

- Should the default preset be `banker` (investment banking) or depend on the entity's accounting standard (use `japanese` for Japanese GAAP)? Proposal: choose by accounting standard.
- Should the banker income statement show expenses as negative values in parentheses, as investment banks commonly do? Proposal: show them as negative.
