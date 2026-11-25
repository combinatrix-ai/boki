# API principles and boki as a compiler

Discussion summary (2026-10-28). Before implementing intercompany transactions, the user asked to start with the ideal API and review its overall consistency.

This document separates decisions approved by the user from agent proposals. The user resolved open questions on 2026-10-28; see "Decisions and next steps" at the end.

## 1. Current API layers

| Receiver | What belongs here | Examples |
|---|---|---|
| `b.` | Constructors and pure functions | `b.Model`, `b.fiscal`, `b.delay`, `b.by_year`, `b.round`, `b.expect` |
| `b.lib.` | Financial functions | `npv`, `irr`, `pmt`, `wacc`, `black_scholes` |
| `m.` | Model-wide objects | `input`, `series`, `unknown`, `solve`, `check`, `render`, `entity`, `quantity`, `move` |
| `co.` | Entity books | `pl.<kind>(...)`, `bs.<kind>(...)`, `bs.opening(...)`, `journal`, `vat_settlement`, and read-only `cf` |
| `r.` | Results | `pl`, `bs`, `cf`, `table`, `to_excel` |

The overall structure is consistent: entity books own accounting items, the Model owns model-wide items, and `b` holds functions. Constructors use nouns (`m.input`, `co.pl.revenue`), while operations use verbs (`solve`, `check`, `render`).

Inconsistencies:

1. Only quantities (`m.quantity`) use an unowned verb, `m.move(src=, dst=)`. `src`, `dst`, and `b.outside` remain from the initial proposal to put accounts on the Model and express everything as moves ([methods.md](methods.md)). Only one corpus plan, janz-saas-plan, and tests use them.
2. Four arguments change the counter-account for P&L rows: `settle=`, `cash=`, `recognize=`, and `against=`. Their names do not explain which combinations are valid.
3. Time points use period indexes (`at=0`, `draw={0: ...}`), model years (`b.by_year({0: ...})`), and dates (`b.fiscal(change={"2029-03-31": ...})`).
4. Both `b.delay` and `lib.delay`, and both `b.mix` and `lib.mix`, exist and are used in the corpus.
5. Opening balances can be set with either `co.bs.opening(...)` or `opening=` on each row.

## 2. Book entries have an amount, time, and counterparty (decided)

The user approved this model.

Each book entry has an amount, time, and counterparty. By default, it occurs in the recognition period, with the outside world, and against cash. Each argument changes one of those defaults.

| Dimension | Default | Argument |
|---|---|---|
| When the P&L records it | Recognition period | `recognize=` |
| When cash moves | Same period | `settle=` (timing delay) or `cash=` (cash-flow series) |
| Which account in the same entity is paired with it | Cash | `against=` (a transfer that does not use cash) |
| Who the entity trades with | Outside world | `counterparty=` (another entity in the same model) |

`counterparty=` is not a fifth exception; it defines the "who" dimension. It can be combined with `settle=`, but it is mutually exclusive with `against=`.

## 3. Inter-entity transactions use `counterparty=` (decided; v1 scope follows)

On the name `intercompany`, the user asked what it meant and confirmed that intercompany transactions are a real concept.

- Accounting standards use different terms. IFRS 10 uses "intragroup". US GAAP uses "intercompany" (the codified source uses "intra-entity"). Japanese GAAP refers to transactions between consolidated companies, or related companies in separate-company disclosures. Because boki uses standard-specific presentation labels, the API should not lock users into one standard's term.
- This feature handles transactions between two entities in the same model. Group ownership determines later whether they are in the same group. A 30% associate is not an intragroup entity, and consolidation eliminates only the investor's share of unrealized profit.
- The public API is `counterparty=`. Keep `intercompany` as an internal name for pair tags and `Posting` attributes. Do not abbreviate it to `counter=` because "counter" can also mean a counting device.

Proposal: Keep the current style, where the entity owns each book entry, and add the counterparty to existing methods.

```python
# Sales and services: pass the counterparty's account kind. P&L account kinds are not unique, so this is required.
sub.pl.revenue("Parts sale", qty * price, settle=b.delay(1), counterparty=parent.pl.cogs)
parent.pl.revenue("Management fee", 0.03 * sub.pl.revenue.total, counterparty=sub.pl.sga)

# If the counterparty account kind is determined, pass the entity.
sub.bs.loan("Parent loan", draw={"2027-04": 50 * JPY}, rate=0.02, repay=10 * JPY, counterparty=parent)
sub.bs.capital("Capital increase", 100 * JPY, at=0, counterparty=parent)     # Creates an investment in the parent.
sub.bs.dividend("Dividend", 0.3 * sub.net_income.lag(1), counterparty=parent) # Creates dividend income in the parent.

line = sub.pl.revenue(...)
line.counterparty      # The counterparty LineItem
```

Principles:

1. **Create both sides from one expression.** A planning model has no reason for the amounts to differ, so the API should make mismatches impossible to write.
2. **The entity that sets the terms writes the entry, and boki creates the mirror entry.** The borrower writes a loan; the seller writes a sale.
3. **Let the counterparty choose only its account kind.** The same part may be cost of revenue, operating expense, or a fixed asset for the buyer. Pass the counterparty entity when its account kind is unambiguous; otherwise pass the account kind.
4. **Do not make users write elimination entries.** Consolidation eliminates the recorded pair.

Alternatives considered: a neutral verb `b.intercompany(seller=, buyer=, amount=)` cannot express both account kinds and would require separate methods for loans, dividends, and capital contributions, as well as duplicating arguments such as `settle=`. A model-wide two-entity method like `m.move` is also weak because §4 proposes removing `m.move` itself.

v1 scope (decided on 2026-10-28, as proposed):

- A fallback that lets users write both sides separately and pair them later (`b.pair(a, b)`) could check for consolidation mismatches and may be needed to reproduce mismatches in source models. Exclude it from v1 and add it if the corpus requires it.
- Transactions where the buyer records an asset (inventory or fixed assets) need unrealized-profit elimination and depreciation adjustments. In v1, support expenses only and raise an error if the buyer's account kind is an asset.
- Whether to include consolidation: v1 combines and eliminates 100% subsidiaries. Add non-controlling interests, the equity method, and goodwill later.
- Transactions between entities with different currencies or fiscal periods: v1 supports only a shared currency and Timeline.

## 4. Use series for quantities instead of a separate mechanism (decided)

The user asked whether `move` and `transfer` are needed, and suggested that ordinary series could support their own operations, like pandas.

This can be written with series alone; `define` and `lag` already exist:

```python
basic = m.series("Basic", unit=account)
pro = m.series("Pro", unit=account)
b0, p0 = basic.lag(1, fill=100 * account), pro.lag(1, fill=30 * account)
up = m.series("Basic to Pro", b.round(b0 * 0.005))
basic.define(b0 + conv_basic - up - b.round(b0 * 0.03))
pro.define(p0 + conv_pro + up - b.round(p0 * 0.02))
```

The quantity mechanism checked units for inflows and outflows, matched amounts leaving and entering, and displayed a change table. Series unit checks, reusing a named flow at both ends, and presentation logic can provide the same behavior.

Boundary:

- **Entity books enforce structure.** Accounting invariants require balanced books, CF to equal the change in cash, and profit to equal the change in retained earnings. The §2 principles and `counterparty=` apply only to books.
- **Everything else is a regular series that users can define freely.** Unit checks and cycle detection provide safeguards.

Proposal: Remove `m.quantity`, `m.move`, and `b.outside`.

Model-wide values such as USD/JPY rates and market size are already series on the Model (`m.series(data=)`, `b.table`, and `m.input`) and appear as rows on the Excel Model sheet. Keep this design. Use these series to convert transactions between entities with different currencies.

## 5. Express time points as dates (decided)

The user asked whether period indexes are awkward to write.

`Timeline.index` already accepts date strings, so `at="2028-04"` works. The issue is that the API has three time conventions:

| Syntax | Meaning |
|---|---|
| `at=0`, `draw={0: ...}` | Zero-based period index |
| `b.by_year({0: ...})` | Zero-based model year. In a monthly model, 0 covers the first 12 months. |
| `"2028-04"` | Date |

This is error-prone: `at=12` and `by_year({1: ...})` refer to the same time in a monthly model, but use different numbers. A model with `start=1` labels its periods `1, 2, 3, ...`, while `at=1` still means the second period.

Proposal:

- Use dates (period labels) in documentation and examples. Allow `"2027"` in annual models.
- Keep integers as period indexes, mainly for the initial period with `at=0` (used 33 times in the corpus) and inside loops and library code.
- Let `by_year` accept dates and year labels as keys.

## 6. `b` and `b.lib` correspond to numpy and scipy (decided)

The user asked whether the namespaces correspond to `np` and `sp`.

- `b` (numpy): Items needed by every model, including `Model`, units, series operations (`round`, `max`), time shapes (`by_year`, `step`), kernels for `settle=` (`delay`, `even`, `mix`), and comparisons (`expect`).
- `b.lib` (scipy): Published formulas with sources, including `npv`, `irr`, `pmt`, `wacc`, `capm`, `black_scholes`, `macrs`, and `ssfa`.
- Keep `delay` and `mix` in `b` only, and stop re-exporting them from `lib`. SciPy has also stopped re-exporting NumPy functions. Add domain-specific subpackages when the function library grows.

## 7. Time granularity (recorded for later discussion)

The user noted that it may be useful to express computations that run hourly.

Each Model currently has one Timeline, so hourly calculations such as generation, battery charge and discharge, and time-of-use rates must be computed externally and read with `b.table(...).over_period()`. Proposal: treat time granularity as a type, like a unit.

```python
hourly = m.timeline("Hourly", step=b.h)
gen = m.series("Generation", capacity * irradiance, on=hourly)
revenue = (b.min(gen, grid_limit) * price_by_hour).over(m, how="sum")
```

- Raise an error when users combine series with different granularities. Require explicit aggregation (`.over`) and allocation, with `how=` set to `sum`, `closing`, or `average`.
- An entity's fiscal calendar groups Timeline periods into larger reporting periods. Finer timelines work in the opposite direction.
- In Excel, put hourly calculations on a separate sheet or write aggregated values as data.

Defer this work because it is separate from inter-entity transactions and requires an Excel presentation design.

## 8. Make Excel output resemble human-authored models

The user asked how to prevent many intermediate rows and make Excel output look more like a person wrote it.

### Rows on the current Model sheet (counted on 2026-10-28)

| Plan | Rows | User-named series | P&L | BS | CF | Postings | Helpers | Checks |
|---|---|---|---|---|---|---|---|---|
| quickstart | 40 | 0 | 15 | 7 | 3 | 10 | 3 | 2 |
| neocloud | 106 | 20 | 26 | 11 | 3 | 24 | 19 | 3 |

Sources of intermediate rows:

1. Journal-entry rows duplicate P&L rows. In quickstart, "Product sales" appears twice with the same value, once in P&L and once in postings. Internal book rows such as "Term loan (drawn)" and "AR (change)" also appear.
2. Unnamed helper rows. Twelve of neocloud's 19 helper rows have the `(op)` label for a subexpression used twice.
3. User-named series. Users want to see these, so they are not intermediate rows.

### Differences from human-authored models

| | Human-authored model | Current boki |
|---|---|---|
| Sections | By business topic (revenue, expenses, capital spending, and debt) | By internal category (model / P&L / BS / CF / postings / helpers / checks) |
| Order within a block | Assumptions → calculations → results | Creation order |
| P&L rows | Calculated with the revenue model | Shown in a separate P&L section |
| Intermediate values | Rows with meaningful names | `(op)` labels and journal-entry rows |
| Numbers in formulas | Refer to assumption cells | Hard-coded, such as `=0.45*C12` |

### Policy (decided; see "Decisions and next steps" for layout)

**Only named values become rows.** Inline intermediate calculations written as Python variables in formulas. Use `m.series("name", ...)` only when you want a row.

**boki should know how to remove unnecessary rows; agents should not rewrite formulas to do it.** The user asked whether agents should have a way to remove boki-generated intermediate rows and noted that `cumsum` does not need its own row. If agents write alternate formulas, the same value has two definitions that can diverge. Teach boki once that `cumsum` can use `SUM`, and every model benefits.

| Intermediate row created by boki | Current translation | Translation without a row |
|---|---|---|
| `(cumsum)` | Previous column plus current period | `SUM($C$5:F5)` (range from the source-series row) |
| `compound` (constant rate) | Previous column times (1 + rate) | `C5*(1+$C$9)^(column_index)` |
| `discount` (constant rate) | Previous column divided by (1 + rate) | `1/(1+$C$9)^(column_index)` |
| Opening loan balance | Helper row | Previous column in the balance row |
| Journal-entry row | Helper row | Inline in the balance formula (receivables = previous column + revenue - cash collected) |
| `(op)` | Helper row | Inline at each use |
| NOL balance | Previous column | No shortcut. It is a real recurrence with `max` and `min`, and human-authored models also have an "NOL balance" row. |

**Rows that are necessary:** Recurrences (balances, NOL, and user-defined recurrences); aggregations over ranges (`.sum()`, and the source series for `npv` and `irr`); data (`by_year`, `step`, and `data=`); and values that cannot become formulas (functions decorated with `@m.series` and solutions from `m.solve`).

**Expressions that can be inlined but cause problems:** Repeating shared subexpressions makes formulas longer, potentially exponentially so. Excel's limit is 8,192 characters. Expanding `settle=` grows with the number of periods. Set a length limit. Above it, create a row or raise an error that asks users to name an intermediate value. Formulas may differ in the first column when `lag` is out of range or a `where` depends only on time. Allow this, but report it.

The user asked whether inlining formulas would be difficult. `excel.py` already expands formulas column by column in `f` and `expand`; `promote()` adds helper rows afterward. The change is deciding where to stop inlining. `research/tools/excel_check.py` recalculates and compares every formula cell in every plan, so it will catch incorrect translations.

**Agents specify only what to show and where to show it.** The user suggested asking agents to specify how to group or collapse rows. Specify the calculation order with topic-based blocks:

```python
r.to_excel("plan.xlsx", calc=[
    b.block("Revenue", [users, churn, arpu, co.pl.revenue]),
    b.block("Expenses", [headcount, salary, co.pl.sga]),
    b.block("Debt", b.schedule(loan)),
])
```

- Make each listed series a row and inline the others. Raise an error, with the name and reason, if a required row is missing from all blocks. Like unit and cycle errors, this stops the agent.
- Report signs of machine-generated output: formulas that are too long, hard-coded numbers inside formulas, rows whose formulas vary by column, and series with no location. Make each finding a warning or an error.
- Improve the default even without explicit settings: show only named values, use LineItems rather than journal entries as rows, and preserve the order of blocks in the code.
- Set `detail="full"` to include helper rows as now, for audits.

Questions initially left open (decided on 2026-10-28; see "Decisions and next steps"):

- Should users specify calculation order by topic-based blocks, or keep the current decision ([excel-presentation.md](excel-presentation.md)) to put calculations on the Model sheet and create human-oriented layouts on presentation sheets? Proposal: use topic-based blocks.
- Where should users specify order? Use `to_excel(calc=...)`, consistent with the 2026-10-18 decision to put all presentation options in `to_excel` (this repeats series names), or use `with m.section("Revenue"):` in the model code, treating order as part of the calculation structure?

## 9. boki is a compiler

The user noted that this work is close to building a compiler.

| Compiler concept | boki |
|---|---|
| Source language | Python DSL |
| Intermediate representation (IR) | DAG of series expressions |
| Lowering to a simpler IR | Books: LineItem → Posting → balance |
| Type checking | Units |
| Dependency analysis | Cycle detection. `m.solve` handles explicit fixed points. |
| Interpreter | Evaluator (`m.render()`) |
| Code generation | Excel formulas |
| Instruction selection | Excel translation by operation, such as a previous-column recurrence or `SUM(range)` for `cumsum` |
| Keep or inline a variable | Make a subexpression a row or inline it |
| Strength reduction | Replace a recurrence with a closed formula, such as constant-rate `compound` with `(1+g)^t` |
| Debug information | Series names |
| Translation verification | `excel_check.py` |

Unlike a typical compiler, boki targets a language that people read, like a transpiler that emits readable JavaScript. Optimize for reader effort, not runtime: reduce row count, formula length, and variation between columns. Always keep user-named series, like variables at `-O0`; remove only rows created by boki. `detail="full"` selects a different optimization level.

Design implications:

1. **Do not generate code from an IR that is too low-level.** Journal-entry rows appear in Excel because the current export starts from the lowered posting IR. Generate from the units people think in: rows, balances, and subtotals.
2. **Separate compiler passes.** `collect()` and `promote()` currently handle row selection, instruction selection, and layout together. Use distinct passes for collection, translation selection, row selection, layout (blocks and order), output, and verification. `calc=` and `m.section` feed the layout pass.
3. **Treat translation verification as an invariant.** More translation options create more chances for errors, so compare every output.
4. **Treat consolidation as a pass.** Combine the book IRs for each entity and eliminate pairs recorded with `counterparty=`. The inter-entity API must record the pair, counterparty, and account kind at the source level because consolidation needs them.

## Decisions and next steps (2026-10-28)

In another thread, an agent proposed an order and decisions, and the user agreed ("Yes, this order"). The open questions in §§3–6 and §8 were resolved as follows.

- §3: Keep the proposed v1 scope. Exclude `b.pair`; support expenses only on the buyer side and raise an error for asset account kinds; consolidate and eliminate 100% subsidiaries; require a shared currency and Timeline.
- §4: Remove `m.quantity`, `m.move`, and `b.outside`.
- §5: Express time points as dates. Let `by_year` accept dates and year labels as keys.
  - Implemented on 2026-10-29: `Timeline.index` accepts period labels ("2028") and date strings that include only a year. `by_year` maps date and label keys to the model year containing that date. Previously, string keys were silently ignored and defaults were used, so times outside the model now raise an error.
- §6: Keep `delay` and `mix` only in `b` (`boki/shapes.py`). `lib` contains only sourced formulas.
- §1 inconsistency 5 (opening balances): Inspection showed no duplication. `co.bs.opening(...)` accepts only cash and retained earnings. These are entity-level accounts without row constructors. All other rows use their own `opening=`. The rule is to set opening balances on the rows that hold them, and use `co.bs.opening` only for cash and retained earnings, which have no rows. Each balance has one place to be set. No change is needed.
- §8 layout settings: Build on the PR #1 experiment with `b.section`, `b.row`, and `b.link` inside `to_excel(sheets=[b.sheet(...)])`. This follows the 2026-10-18 decision to separate calculation and presentation and lets users repeat a value with `link`. Do not merge PR #1 as is. Rebuild it as the layout pass in §9.
- §7: Defer.
- §3 implementation, first v1 stage (2026-10-29): Add `counterparty=other.pl.<kind>` to P&L rows, plus consolidation with `m.group(name, parent=)`, `g.own(sub)`, and `r.pl/bs/cf(g)`. Consolidation combines each entity's books and removes paired journal entries (`boki/group/`). The second stage (2026-10-29) added `counterparty=` to loans, capital contributions, and dividends, plus Excel output for consolidated statements. Remaining work includes asset transactions and unrealized profit, ownership below 100%, goodwill, opening intercompany balances, and currencies.
- §8 layout pass, implemented on 2026-10-29: `to_excel(sheets=[b.sheet(name, [b.section(title, [series | b.row(series, label=) | b.link(row)])])])`. Place specified rows on their sheets. Inline named series that are not placed. Keep required rows and books on the Model sheet. References to other sheets include the sheet name. Display transforms with `sign=` and `scale=` were also implemented on 2026-10-29: cell values are `value × sign ÷ scale`, while references restore the original value.
- §8 assumption rows, implemented on 2026-10-29: A number that is not a formula result is an assumption. Put it on the Inputs sheet as a named input (`m.input`). The user agreed that a working-capital change that is not a formula is an assumption. Many unnamed `by_year` rows in the corpus came from plan helpers (`drv = lambda row: b.by_year(...)`) that dropped row labels from the source sheet. `Sheet.inputs` in `research/tools/xlsx.py` creates time-series inputs named from source row labels. boki does not guess names. It reports unnamed assumption rows through `Report.unnamed`. On 2026-10-29, the user decided to make this an error after all unnamed corpus assumptions were named. `to_excel` raises `UnnamedAssumption` with the source `file:line` and the row that uses it. A single value such as `0.45 * sales` stays inline because it does not need a row.

Order:

1. **Reduce the API surface** (§§4 and 6) before larger changes.
2. **Split Excel export into passes** (§9) without changing output, then verify zero differences with `excel_check.py`. Add row-free translations one at a time, such as generating from LineItems, inlining `(op)`, and translating `cumsum` to `SUM`. Count intermediate rows across all plans after each change. By default, only named values become rows.
3. **Add layout settings** (§8) as input to the layout pass.
4. **Add `counterparty=`** (§3) as input to the consolidation elimination pass.
5. Align date handling from §5 during one of the steps above.
