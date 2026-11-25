# boki goals and development plan

Decision (2026-10-16): The user said, "Let's build on boki. Starting from scratch is fine." Build the evaluator rather than using modelx. See [modelx.md](modelx.md) for the modelx survey and design references.

## Goals in the order the user gave them

1. **Model without errors.** Add sanity checks, including unit checks, double-entry invariants, cash and accrual checks, cycle detection, and comparisons with the source Excel file (`expect`).
2. **Support object-based modeling.** Let users define products and components as classes, as in the example below.
3. **Resolve circular references.** Provide `solve` for fixed-point iteration and solving for one variable in each period.
4. **Provide useful formulas and functions.** Cover common methods such as WACC, with their definitions and conventions. This area can attract open-source contributions.
5. Uncertain: **Can boki calculate balance-sheet-based KPIs**, such as average unit price, from accounts?
6. Uncertain: **Can boki produce clean Excel output with a minimal set of flags?**

```python
@m.revenue_item
class ProductA(m.series):
    ...
```

## Design proposals from the agent

- **Represent double-entry bookkeeping with accounts and moves** ([double-entry.md](double-entry.md)). Following Beancount, infer the account type from its name prefix, such as `Assets:`. Users describe business activity with terms such as `flow` instead of writing journal entries.
- **Represent series as expression objects.** Excel export (goal 6) depends on translating series expressions directly into Excel formulas. `lag(1)` refers to the previous column, and operations between series become operations between rows. A series defined with a Python `if` for each period (a function decorated with `@m.series`) cannot become a formula, so export its values and mark them.
- **Build object-based modeling on top of expression objects.** Classes only create namespaces that group series and accounts; the evaluator does not know about them. Use Python classes and `__init__` arguments for the equivalents of modelx inheritance (`bases`) and parameterized Spaces.
- **Represent entities and fiscal periods explicitly** ([entities-and-timeline.md](entities-and-timeline.md)), based on the user's request. The Model holds the period axis and evaluator, and entities sit inside it. Each entity has a sequence of fiscal year ends, including irregular fiscal periods. A Group handles consolidation, including full consolidation, one-line equity-method consolidation, and intercompany eliminations.
- **Allow each period to have its own length.** A modelx experiment showed that changing from one-month to three-month periods required only one `months(i)` call. The plan to use a single time step is being reconsidered and will be checked in v0.1.

## Development stages

At the end of each stage, verify that the corpus comparisons (`expect`) pass.

| Stage | Scope | Completion check |
|---|---|---|
| v0.1 Evaluator (implemented 2026-10-16: series, `@m.series`, memoization, cycle detection, `solve`, and units. Ginzu matches the spreadsheet.) | Series as expression objects, `lag`/lead, pull-based memoized evaluation, cycle detection, `solve`, dimensional unit checks, `check`, and `expect` | `expect` passes for capbudg, LBO, and Ginzu without accounting support. |
| v0.2 Accounts (implemented 2026-10-16: entities, P&L and BS rows, ledger, three statements with direct and indirect cash flow, consistency checks, fiscal periods, business days, and Beancount export. capbudg, LBO, and the Japan Finance Corporation model match their source values.) | Accounts and moves, balances, P&L/BS/CF views, closing entries to retained earnings, cash and accrual checks, and Beancount export | The izakaya model from the Japan Finance Corporation shows a mismatch between earnings and cash flow. Fava displays the P&L and BS. |
| v0.3 Hard cases (implemented 2026-10-16: quantity rows, construction in progress, capitalized construction interest, and `cash=`. SaaS revenue and the solar model match their source values and the modelx experiment.) | Period-specific lengths, sculpting, and solving construction-interest cycles within the model | The solar project matches the modelx experiment, both for spreadsheet values and convergence. |
| v0.3.5 Entities and consolidation | Entities, fiscal periods (including irregular periods), intercompany pairs, full consolidation, equity method, and non-controlling interests | A small example with a parent, an 80% subsidiary, and a 30% associate has a balanced consolidated BS and eliminates intercompany transactions. |
| v0.4 Objects | A class layer for products and components, bills of materials, and inventory as paired quantities and amounts | Small examples for SaaS and manufacturing with a bill of materials |
| v0.5 Function library | WACC, IRR/XIRR, depreciation (straight-line, declining-balance, and Japan's 200% declining-balance method), repayment methods, and taxes, with sources for each convention | A test for each function uses a numeric example from its source. |
| v0.6 Export | Excel export with formulas and minimal flags, plus a UI for tracing dependencies | Export the solar project, open it in Excel, and get the same values. |

## Open questions

- Unit implementation. The leading option is custom dimensional analysis that keeps values as floats and checks units when building expressions.
- How much inventory valuation support (moving average and FIFO) to include in v0.4.
