# boki DSL v0.0.1 (proposal)

Status (2026-10-16): Not implemented. The `research/corpus/*/plan.py` files are non-running examples written against this proposal. The proposal came from reading six public business plans and analyst models and trying to express them in boki. Version 0.0.1 is a draft for writing examples and collecting the cases that did not fit.

## Decisions to date

- An internal Python DSL. Use `import boki as b`. Define templates as functions and repeat generations with `for` loops.
- **Two stages: render, then evaluate.** Run Python to build the model during render, then evaluate it at the chosen time step. Rebuild the model when inputs such as scenarios or sliders change. Express time-dependent branches with expressions (`where`) or functions called once per month.
- Each model has one time step (`step=b.month` or `b.year`). Integrate rates with units over each time step.
- The source of truth is a set of timestamped journal entries. P&L, BS, and CF are aggregations of those entries.
- Users can define units with `b.unit("GPU")`. Quantities with different units cannot be combined.

## Patterns found in the corpus

These patterns recurred in six models: DCF, capital budgeting, LBO, SaaS, a solar project finance model, and a Japan Finance Corporation startup plan. The last column lists examples.

| # | Pattern | Excel representation | Examples |
|---|---|---|---|
| 1 | **Corkscrew** (opening + additions - reductions = closing) | Four rows: Opening, Add, Less, and Closing | Loans, NOL, customer counts, MRR, paid-in capital, defaults, undrawn amounts, book value, and invested capital across all models |
| 2 | **Phases and milestones** | Multiply each formula by a period-specific 0/1 flag row | Solar (development, construction, operations); Japan Finance Corporation (startup and steady state) |
| 3 | **Compounding** (growth from an initial value of 1) | `K=J*(1+rate*flag)` | Degradation, inflation, interest, cumulative discounting, and ARPA |
| 4 | **Fade and segment definitions** | `G2-((G2-M2)/5)*k` | Ginzu (growth, margins, tax rates, and cost of capital); LBO and capbudg (growth that changes over time) |
| 5 | **Table lookup** | `LOOKUP(YEAR(date), table)` | Solar (calendar-year prices and monthly factors); Ginzu (industry averages and rating-to-spread mapping) |
| 6 | **Backsolving** | Circular references and iteration, macros, manually solved formulas, or searching with `IF` | Solar (sculpting); SaaS (target MRR to new customers, target ARR to AE hiring); Ginzu (share price and cost of capital) |
| 7 | **Cycles** | The source uses `Iterationを有効に` ("Enable iteration") and copy-paste macros | Solar (uses, debt, and IDC; taxes and interest); Ginzu |
| 8 | **Waterfalls** | Chains of `MIN` and `MAX` | Solar (interest, principal, default, sweep, and equity holders) |
| 9 | **States and transitions** | Manually keep corresponding rows in sync | SaaS (Basic, Pro, and Enterprise; unconverted signups) |
| 10 | **Cohorts and ramps** | Months since start per row multiplied by a factor | SaaS (AE quota ramp and renewal month for Enterprise contracts) |
| 11 | **Headcount and ratios** | Role, start month, and salary; `ROUNDUP(customer_count/200)` | SaaS and Japan Finance Corporation (employees, owner-operators, and part-time staff) |
| 12 | **Valuation functions** | NPV, IRR, XIRR, Gordon growth, cumulative discounting, and probability weighting | Ginzu, LBO, capbudg, and solar |
| 13 | **Tax and NOL** | NOL corkscrew and changing tax rates | Ginzu, solar, capbudg, and LBO |
| 14 | **Calendar-based quantities** | Source labels `26日` ("26 days") and `月〜木18日` ("18 days, Monday through Thursday") | Japan Finance Corporation |
| 15 | **Ramp-up and steady state** | Two monthly averages (startup and steady state), with a 1.3x factor | Japan Finance Corporation |
| 16 | **Collection and payment terms, and prepayments** | Terms are recorded but not used in the calculation; a separate cash-receipt row | Japan Finance Corporation (close at month-end, collect on the 20th of the next month); SaaS (annual prepayment) |
| 17 | **Rounding** | `ROUND` and `ROUNDUP` | SaaS |
| 18 | **Period length changes over time** | Months in Period changes from 1 to 3 | Solar |

Findings:

- Most rows in Excel models manually expand patterns 1 through 5 above: corkscrews, flags, compounding, fades, and table lookups. Providing these as reusable components would greatly reduce row counts.
- **Patterns 6 through 8 are the hardest: backsolving, cycles, and waterfalls.** Excel models handle them with iteration, macros, or manually solved formulas. These parts are the hardest to read and most likely to break. boki has the most to gain by giving them explicit syntax.
- Some models use little or no accounting (Ginzu and LBO). boki needs a layer for series and valuation formulas that is separate from the journal-entry engine.
- Models that retain calculated values in the source file (capbudg and LBO) can use those values directly in `expect` regression checks.

## v0.0.1 components

> 2026-10-16: [methods.md](methods.md) replaced this section with a shorter list (nine core methods, the standard library, and a future single-entity model). The original full proposal remains below.

### Model and time

```python
m = b.Model(name, start="2027-04" | 2025 | 0, step=b.month | b.year, periods=N,
            currency=JPY, terminal=False)
m.phase(name, start=, length= | end= | after=)   # .flag, .start, .end
m.milestone(name, date)                          # Date arithmetic: cod + 10 * year
cal = m.calendar(holidays="jp", closed=["Sun"]); cal.days(weekdays="Mon-Thu")
m.base_year(revenue=, ebit=, ...)                # Actual years for an annual valuation model
```

### Inputs (resolved during render)

```python
m.input(name, default, scenarios={...}, choices={...})   # default can be an expression that uses other inputs
b.by_year({1: x, range(2, 6): y, "terminal": z})          # Inputs split by year
b.table(by="year" | ("year", "month"), values="file.csv#column")
b.seasonal({1: ..., 12: ...})                             # Calendar-month factors
b.step({date: value, ...})                                # Values that change on given dates
```

### Series

```python
m.series(name, expr)
s.prev / s.lag(k) / s.lead(k) / s.at(t) / s.terminal / s.cumsum() / s.where(cond)
b.compound(start, rate)          # Previous period * (1 + rate)
b.index(rate, when=phase | start=date)
b.fade(a, b, over=(t0, t1))      # Linear fade
b.piecewise({...})
b.ramp(start, end, over=)
b.once({date: amount})
b.min / b.max / clip
```

### Stocks and flows (corkscrew)

```python
st = m.stock(name, unit=, opening=, rounding="round" | "ceil" | None)
st.inflow(name, expr) / st.outflow(name, expr)   # .opening, .closing, .inflows, .outflows
m.transfer(src, dst, expr)                       # Transfer between states; appears on both sides
m.convert(pool, dst, expr)                       # Convert from an unconverted pool to a state
c = m.cohort(name, unit=, productivity=b.ramp_curve([...], every=))
c.hire_to_meet(capacity=, demand=, rounding="ceil")
```

### Accounting (creates journal entries)

```python
m.revenue(name, amount, settle=b.immediate | b.terms(close="eom", pay=b.next_month(day=20)) | b.mix({...}),
          recognize=b.as_incurred | b.ratably, active_from=)
m.expense(name, amount, account=, settle=, when=phase, start=)
m.asset(name, amount, at=, depreciate=b.straight_line(n) | b.ddb(n) | b.macrs(n) | b.none,
        salvage=, tax_credit=)
m.asset_group(name, spend=b.even(over=) | b.s_curve(over=), depreciate=)
m.deposit(name, amount, at=)
m.capex(name, amount, depreciation=)             # For annual models that do not track individual assets
m.working_capital(name, target= | initial=, recover_at_end=)
m.roster(name, loading=)                         # .add(role, salary, start=), .table(csv), .ratio(...), .per_head(...)
m.cohort_contracts(name, stock=, term=, acv=, bill=b.upfront, recognize=b.ratably, renewal=)
m.loan(name, principal | size=, draw=, rate=, interest="opening_balance",
       repay=b.equal_principal(...) | b.bullet(at=) | b.percent_of_original({...}) | b.sculpted(...),
       fees=[...], capitalize_interest_during=phase)
m.equity(name, amount, at= | plug="funding_gap")
m.tax(rate=, nol=True)
```

### Backsolving, cycles, and allocation

```python
m.solve(name, unit=, so_that=lhs == rhs, each_period=True, rounding=, min=)  # Solve for one variable in each period
b.sculpt(cfads / dscr, rate=, over=phase)       # PV(CFADS/DSCR), including forward references
m.iterate([vars...], tol=, max_iter=)           # Explicit fixed-point iteration; implicit cycles are errors
m.waterfall(source, [step, ...])                # Priority allocation: b.default_account / b.reserve / b.sweep / b.to_equity
```

### Valuation and output

```python
r = m.render()
r.pl() / r.bs() / r.cf(freq="month" | "year") / r.table(rows, months=, unit=)
r.monthly_average(phase=, after=)
r.metric(name, expr) / r.decision(name, accept_if=) / r.sensitivity([inputs], on=metric)
b.npv(cf, rate= | discount=) / b.irr / b.xirr / b.gordon(cf, rate=, growth=)
b.cumulative(1 + rate)                          # Discount rates that vary by year
b.capm / b.hamada / b.wacc / b.expect({value: prob}) / b.option_value(...)
r.check(cond, msg) / r.expect({key: value}, tol=)   # Compare against calculated values in the source file
```

## Open questions and unsupported patterns

1. **Forward references (sculpting) and evaluation order.** `b.sculpt` needs CFADS for the entire repayment window. A pull-based evaluator can request the full CFADS series while evaluating the loan amount, but a cycle occurs when CFADS depends on taxes, which depend on interest, which depends on the loan amount. Should `iterate` be required, or should the first estimate use CFADS before taxes?
2. **Period length changes over time**, such as monthly to quarterly. The current plan is to calculate monthly and aggregate, but quarterly repayments and interest need a payment frequency on the loan (such as `every=3*month`).
3. **Rounding and expected values.** `ROUND` can greatly change the result when customer counts are small. Should users choose between deterministic mode (no rounding) and rounded mode?
4. **Representing terminal state.** A terminal state is a steady state used as input to a Gordon formula, not an 11th-year column. The draft uses `terminal=True` and `.terminal` as placeholders.
5. **Relationship between the non-accounting layer** (Ginzu and LBO) and the journal-entry engine. If `m.series` and `m.revenue` refer to the same series, should the P&L come from journal entries or expressions?
6. **Where to store headcount and assumption data**, such as role tables, price tables, and industry averages. The draft uses CSV references (`file.csv#column`).
7. **Tax.** How much support should be built in for sole proprietorships (Japan Finance Corporation), corporate tax and NOL, transitions to marginal tax rates, and consumption tax?
8. **Probability.** The models use probability-weighted default (Ginzu), P50/P90 (solar), and renewal probability (SaaS). Version 0.0.1 avoids this with `b.expect` and scenarios.

## Next steps

- Build the smallest evaluator that passes `expect` for capbudg and LBO, with series, stocks, annual periods, NPV/IRR, and Hamada. It should work without the accounting engine.
- Use the Japan Finance Corporation izakaya model to check journal entries through P&L, BS, and CF, including how collection terms shift cash flow.
- Try sculpting and `iterate` on the solar model.
- Candidate corpus additions: neocloud, the Macabacus LBO (download requires login), and analyst models for public companies.
