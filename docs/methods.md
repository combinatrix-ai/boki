# boki methods (v0.0.1, condensed)

> 2026-10-16: The API style moved to [api.md](api.md) (v0.0.2). Entity methods now create statement rows with account kinds. User-created accounts and `move` remain low-level tools for quantity rows and unusual journal entries. This file preserves the v0.0.1 record.

Status: 2026-10-16. Rewrote all six `plan.py` files using this condensed API (22 core names and 31 standard-library names). User's direction: "Keep the basics minimal, then later make a simple one-company model feel obvious." The core does not prescribe P&L kinds such as revenue, gross profit, or net income, or a tax base. Since group companies are also in scope, users compose models primarily from series.

The six `research/corpus/*/plan.py` files used about 136 names in total (`b.` 63, `m.` 37, `r.` 17, and 19 object methods). Condense these to **nine core names plus series operators**. Put the rest in a standard library that can be implemented with the core, or remove them and write the logic as model series.

Inventory method: use `python3`'s `ast` module to collect every `b.*`, `m.*`, and `r.*` attribute and object-method call from the plans (see the [full inventory](#full-inventory) at the end).

## Summary

```text
Layer 1: Core (9 names)
  b.Model   b.unit   m.input   m.series   m.account   m.move   m.solve   m.check   m.render
  Series operators: + - * /  comparisons  s[t]  s.lag(k)  s.where(c, else_)  s.spread(kernel)  s.sum()
               b.min  b.max  b.round  b.ceil
Layer 2: Standard library (`boki.lib`; functions expressible with the core and no fixed account kinds)
  About 30 names for time, shapes, delay kernels, accounting combinations (`flow`, `asset`, `loan`, `tax(base)`, etc.), allocation, and valuation.
Layer 3: One-company model (planned as `boki.company`)
  Standard account kinds, P&L/BS/CF, and named series such as `revenue`, `gross_profit`, `operating_profit`, and `net_profit`.
Remove (write as model series or accounts)
  About 60 names, such as SaaS-specific transitions, cohorts, staffing tables, and attributes copied directly from Excel row labels.
```

Three principles guided the reduction:

1. **Everything with opening and closing balances is an account.** This includes borrowings, NOLs, working capital, and default accounts, as well as **customer counts, plan-level subscriptions, and AE headcount as unit-based accounts**. Move all changes with `move`, which transfers an amount between accounts. This absorbs `stock`, `transfer`, `convert`, and the four-line corkscrew.
2. **Represent recognition or payment delays with a kernel (a distribution over time).** "Cash collected the following month" is a one-period delay; straight-line depreciation over five years spreads evenly across 60 periods; an AE ramp is a coefficient series from the hire month; annual prepayment allocated monthly spreads evenly over 12 periods. All use `s.spread(kernel)` (convolution). This unifies delays for `settle`, `recognize`, `depreciate`, `cohort`, and `renewal`.
3. **Use one `solve` for back-solving and cycles.** Solving for new customers from target MRR (one variable per period) and solving a debt-size ↔ construction-interest cycle (fixed point) both solve `unknown == expression`. Sculpting is a recurrence that works backward from the future (`lag(-1)`), so it does not need `solve`.

## Core

```python
m = b.Model(name, start, step=b.month | b.year, periods=N, currency=JPY)
GPU = b.unit("GPU")                          # A countable unit. b.unit("node", 8 * GPU) defines a conversion.

x = m.input(name, default, scenarios={...})  # Value resolved at render time. default can be a constant, series, or expression using other inputs.
s = m.series(name, expr)                     # Named series (for display and tracing); unnamed expressions work anywhere.
s = m.series(name, lambda self: self.lag(1, fill=x0) * (1 + g))   # Recurrence that refers to itself.

@m.series(unit=JPY / month)                  # Time-dependent series, called once for each t.
def dividend(t): ...

a = m.account(name, unit=JPY, opening=0)     # Has no kind (asset, revenue, etc.); classification belongs to Layer 3.
m.move(name, amount, src=a1, dst=a2)        # For journal entries, dst is debit and src is credit. amount is a series (integrate rates by period).
a.balance  a.opening  a.inflow  a.outflow   # Account series; opening = balance.lag(1).

u = m.unknown(name, init=...)                # Unknown to solve (scalar or series); can declare a name before defining it.
m.solve(u, lhs == rhs)                       # Solve each period in order for a series, or use fixed-point iteration for a scalar.
m.solve(u, lhs >= rhs, integer=True, min=0)  # Smallest value satisfying the condition when lhs is monotonic in u; e.g. hires or new customers.
m.solve([u1, u2], [eq1, eq2])                # System of equations; fixed-point iteration (debt size ↔ uses ↔ construction interest).

m.t  m.date                                  # Series of period indexes and dates. Use b.date("2027-07-01") for dates and date + 12 * month for date arithmetic.

m.check(cond, msg)                           # Evaluated at render time. expect (reconciliation with a source file) is syntactic sugar for check.
r = m.render(scenario=..., inputs={...})
r[name]  r.table([series...], freq=)          # P&L/BS/CF formatting belongs to Layer 3.
```

The only built-in accounts are `b.cash` and `b.outside` (outside the model, for inflows and outflows of non-monetary accounts such as customer counts). Accounts have no kinds, so the core does not know about revenue, expenses, or assets. It only knows which account transfers how much to another, and when.

### Series operators

| Operator | Meaning | Replaces |
|---|---|---|
| `s.lag(k, fill=)` | k periods earlier (`k<0` means k periods later) | `prev`, `lead`, `at(t-1)` |
| `s[t]` / `s.at(date)` | Value in a period (scalar) | `terminal`, `at` |
| `s.where(cond, else_)` | Branch by period. If `else_` is omitted, the result is missing and ignored in aggregation. | Phase flags multiplied into expressions, `when=` |
| `s.spread(kernel)` | Convolution using a coefficient series | Recognition and payment delays, depreciation, ramps, allocation, renewals |
| `s.sum(over=)` | Sum, with an optional interval | `cumsum` as `lambda self: self.lag(1, fill=0) + s` |
| `b.min` / `b.max` | Per-period minimum or maximum | `clip` |

Evaluation is pull-based: calculate and cache each (series, period) pair when needed. Forward references with `lag(-1)` work unless they create a cycle. Raise an error on same-period cycles and require `solve`.

## Standard library (`boki.lib`)

Everything can be expressed in the core, often in a few lines, so users can replace an implementation if needed.

### Time and shapes

| Function | Core definition |
|---|---|
| `phase(start, end)` | Boolean series `(m.date >= start) & (m.date < end)` |
| `calendar(holidays, closed).days(weekdays=)` | Data series of matching days in each period |
| `step({date: v})` / `by_year({...})` / `piecewise({...})` / `table(csv)` / `seasonal({...})` | Series keyed by date, year, or calendar month; can supply an input default. |
| `once({date: amount})` | Series with a value only in the specified period |
| `compound(x0, rate)` | `lambda self: self.lag(1, fill=x0) * (1 + rate)` |
| `index(rate, when=)` | `compound(1, rate.where(when, 0))` |
| `fade(a, b, over=(t0, t1))` | Linearly interpolated series |
| `ramp(start, end, over=)` | Alias for `fade`, used for multipliers |

### Delay kernels

| Function | Kernel |
|---|---|
| `delay(n)` | Delay by n periods (`[0]*n + [1]`). Month-end billing, paid the following month: `delay(1)` for monthly periods. |
| `even(n)` | Even allocation across n periods (`[1/n]*n`). Straight-line depreciation, monthly allocation of annual prepayments, construction spending. |
| `mix({kernel: w})` | Weighted combination, such as "70% cash, 30% next month." |
| `curve([...])` | Arbitrary coefficient series, such as an AE ramp or S-shaped spending curve. |

### Accounting (accounts and moves)

```python
def flow(m, name, amount, pl, recognize=delay(0), settle=delay(0), via=None, inflow=True):
    """A transaction with separate recognition and settlement timing. The difference accumulates in via (receivables, payables, prepayments, or customer advances).
    pl is a user-created account. If inflow=True, funds flow through pl→via→cash; otherwise, cash→via→pl."""
    via = via or m.account(f"{name}:accrual")
    booked, paid = amount.spread(recognize), amount.spread(settle)
    if inflow:
        m.move(f"{name}:recognize", booked, src=pl, dst=via)
        m.move(f"{name}:settle", paid, src=via, dst=b.cash)
    else:
        m.move(f"{name}:recognize", booked, src=via, dst=pl)
        m.move(f"{name}:settle", paid, src=b.cash, dst=via)
```

| Function | Implementation |
|---|---|
| `asset(name, amount, at=, depreciate=kernel or fn, salvage=)` | Acquisition: cash → asset. Depreciation: `amount.spread(kernel)` from asset to depreciation expense. For declining balance, use `fn(book)`, a recurrence over the book-value series. |
| `loan(name, draw, rate, repay)` | Borrowing account. Draw: debt → cash. Interest: `rate * balance.opening` from cash to interest expense. Repayment: cash → debt. `repay` is a series. |
| `equity(name, amount, at=)` | Capital → cash |
| `tax(rate, base, expense=, nol=True)` | User supplies the taxable-base series and tax account. NOL is a unit-based account. See example below. |
| `working_capital(name, target)` | See example below. |

Repayment methods (equal principal, bullet, percentage of original principal, and level payment) are one- or two-line functions that return a series for `repay`.

### Allocation and back-solving

```python
def waterfall(available, dues):
    """Allocate in priority order. Payment at each tier = min(amount due, remaining funds)."""
    paid, rest = [], available
    for due in dues:
        p = b.min(due, b.max(rest, 0))
        paid.append(p)
        rest = rest - p
    return paid, rest

def sculpt(debt_service, rate):
    """Debt balance whose principal and interest payment equals debt_service each period. Work backward from the future."""
    return m.series("sculpted balance", lambda bal:
        (bal.lag(-1, fill=0) + debt_service.lag(-1, fill=0)) / (1 + rate.lag(-1, fill=0)))
```

### Valuation

`npv(cf, rate)` (`rate` can be a series for varying annual discount rates), `irr`, `xirr`, `gordon(cf, rate, growth)`, `discount(rate)` (cumulative discount factors), `capm`, `hamada`, and `wacc`. These are ordinary functions that take series and return a scalar or series without changing model state.

## Example: implementing `working_capital`

**Top-down (Damodaran's annual model):** set working-capital balances to 25% of revenue and transfer the change from cash.

```python
def working_capital(m, name, target):
    wc = m.account(name)
    m.move(f"Change in {name}", target - wc.opening, src=b.cash, dst=wc)   # Ending balance equals target.
    return wc
```

`wc.opening` is the prior period's balance (`lag(1)`), so this is not circular. To recover it at the end of the model, set `target` to 0 in the final period (`target.where(m.t < N - 1, 0)`).

**Bottom-up (public-lender izakaya example):** do not create a working-capital account. Recording revenue with `settle=delay(1)` automatically accumulates receivables; setting `settle=delay(1)` for purchases accumulates payables. Working capital appears in the BS as receivables + inventory − payables.

Using both approaches in one model double-counts working capital, so document `working_capital` for models that do not specify transaction terms.

## Example: tax with NOLs

```python
def tax(m, rate, base, expense):
    nol = m.account("NOL")
    m.move("NOL created", b.max(-base, 0), src=b.outside, dst=nol)
    used = b.min(b.max(base, 0), nol.opening)
    m.move("NOL used", used, src=nol, dst=b.outside)
    return m.move("tax", rate * (b.max(base, 0) - used), src=b.cash, dst=expense)
```

The user decides which series to use as the taxable base (which accounts make up pretax income, and which items are added or deducted) and passes it as `base`. Since `tax` performs no aggregation, it is less likely to create a cycle by including tax in its own base. In models that still have a tax → interest → debt-size cycle (such as the solar project), use `solve` to solve debt size as a fixed point.

## Example: modeling SaaS plan transitions with accounts

```python
basic = m.account("Basic", unit=account, opening=100)
pro = m.account("Pro", unit=account, opening=30)
m.move("Signup to Basic", new_signups.lag(1) * 0.10, src=b.outside, dst=basic)
m.move("upgrade", basic.opening * 0.005, src=basic, dst=pro)
m.move("downgrade", pro.opening * 0.05, src=pro, dst=basic)
m.move("churn", basic.opening * 0.03, src=basic, dst=b.outside)
```

Even without dedicated `transfer`, `convert`, or `stock`, one `move` updates both accounts. The engine generates each account's opening balance, increases, decreases, and closing balance (corkscrew) automatically.

## Layer 3: One-company model (planned)

With only the core and standard library, every model must repeatedly create revenue accounts and define gross profit as a series, as happened when rewriting the SaaS model. Collect common one-company patterns in Layer 3 later.

- Standard account kinds (revenue, COGS, SGA, depreciation, interest expense, income tax, cash, receivables, payables, fixed assets, borrowings, share capital, etc.) and CF classifications (operating, investing, financing).
- Named series: `revenue`, `gross_profit`, `operating_profit`, `ebitda`, `pretax_profit`, and `net_profit`. Providing at least `net_profit` may be useful.
- Keep metrics such as adjusted EBITDA as commonly named series in Layer 3. Decide later how many aliases to provide.
- Put formatted P&L/BS/CF output (`pl()`, `bs()`, `cf()`) in Layer 3. The core only knows account balances and movements.
- Group companies: build a Layer 3 one-company model for each entity, then express consolidation as sums of series and intercompany eliminations. Whether companies belong in the core remains undecided.

## Tradeoffs and open questions

- **Readability:** keep accounting vocabulary such as `m.loan(..., repay=b.equal_principal(...))` in the standard library. Remove only vocabulary specific to a single industry.
- **Rounding:** when moving a `ROUND`ed customer count, should rounding be an account attribute or part of the expression (`b.round(x)`)? Keeping it in the expression means accounts do not need to know about rounding.
- **Kernels and declining-balance methods:** declining-balance depreciation and churn proportional to a balance are not convolutions because they depend on the balance. Allow functions as well, as in `asset(depreciate=fn)`.
- **Period lengths change mid-model** (monthly to quarterly): `spread` kernels operate in periods, so calculations still assume monthly granularity.
- **Name for `move`:** accountants may prefer `dr=` / `cr=`, while `src=` / `dst=` better describe moving quantities such as customer counts. Use the latter, and document that dst is the debit side.
- **Account direction:** revenue is the `src` side (credit) of a `move`, so revenue appears as `rev.outflow`. Expenses are on the `dst` side, so expenses appear as `cost.inflow`. Decide whether to expose accounting sign conventions directly or hide them in Layer 3.
- **Non-monetary accounts** (customer counts and AE headcount) should not be included in P&L or BS totals. Since core accounts have no kinds, Layer 3 should aggregate only accounts denominated in currency.

## Full inventory

Columns: examples using each name (CB = capbudg, DCF = Ginzu, LBO, SaaS, PF = solar project, JFC = public lender) and destination (**core**, **lib** = standard library, **remove** = write in the model).

### `b.*`

| Name | Examples | Destination |
|---|---|---|
| `Model` | All six | core |
| `unit` | JFC, SaaS | core |
| `currency` | CB, DCF, LBO | core (integrated as a kind of `unit`) |
| `month` / `year` | Five examples | core (units) |
| `min` / `max` | DCF, PF | core (series operators) |
| `compound` | CB, DCF, LBO, SaaS | lib |
| `index` | PF | lib (alias for `compound`) |
| `fade` | DCF | lib |
| `ramp` | JFC | lib (`fade`) |
| `linear` | SaaS | lib (`fade` or an expression) |
| `piecewise` / `by_year` / `step` / `table` / `seasonal` | DCF, CB, LBO, SaaS, PF | lib (series keyed by date, year, or calendar month) |
| `once` | CB, PF | lib |
| `geometric_path` | SaaS | remove: calculate the monthly rate with `compound` |
| `immediate` / `next_month` / `terms` | JFC, SaaS | lib: unify as `delay(n)` |
| `mix` | JFC | lib |
| `upfront` / `ratably` | SaaS | lib: `delay(0)` / `even(12)` |
| `even` | PF | lib |
| `ramp_curve` | SaaS | lib: `curve` |
| `straight_line` | CB, JFC, PF | lib: `even(n)` |
| `ddb` | CB | lib: `asset(depreciate=fn)` |
| `equal_principal` / `bullet` / `percent_of_original` | JFC, LBO | lib (functions that create a `repay` series) |
| `sculpted` / `sculpt` | PF | lib: unify as `sculpt`, a backward recurrence |
| `pro_rata` | PF | remove: express capital contributions and debt draws as series |
| `upfront_fee` / `commitment_fee` | PF | remove: an `expense` series (undrawn amount × rate) |
| `default_account` / `reserve` / `sweep` / `to_equity` | PF | remove: `waterfall` tiers (ordinary series) and accounts |
| `npv` / `irr` / `xirr` / `gordon` | CB, LBO, PF, DCF | lib (valuation) |
| `cumulative` / `cumulative_discount` | LBO, DCF | lib: unify as `discount(rate)` |
| `capm` / `hamada` / `wacc` | CB, LBO | lib (valuation) |
| `expect` | DCF | lib (weighted sum of probabilities; use `weighted` to distinguish it from check-related `expect`) |
| `normal` / `quantile` | PF | defer (probability handling is undecided) |
| `option_value` | DCF | remove: call an external function (Black-Scholes) |
| `renewal` / `spread` | SaaS | remove: use `lag(12)` times a rate or `spread(kernel)` |
| `ref` | DCF | remove: use a Python import |

### `m.*`

| Name | Examples | Destination |
|---|---|---|
| `input` / `series` / `render` / `check` | All six / four / six / two | core |
| `solve` / `iterate` | SaaS, PF | core: unify as `solve` |
| `stock` | DCF, LBO, SaaS | core: unify as `account` (unit-based account) |
| `transfer` / `convert` | SaaS | core: unify as `move` |
| `revenue` / `expense` | Five examples | remove: users create accounts and use `move` or `flow` (restore as standard kinds in Layer 3) |
| `asset` / `asset_group` / `capex` / `deposit` / `disposal` | CB, JFC, PF, LBO | lib: one `asset` function (use a for loop for groups, asset without depreciation for deposits, and `move` for disposal) |
| `loan` / `equity` / `tax` / `working_capital` | 3 / 3 / 3 / 2 examples | lib |
| `waterfall` | PF | lib |
| `phase` / `milestone` / `calendar` | PF, JFC | lib (`milestone` is a date input) |
| `base_year` | DCF | remove: define a sequence of `input` values |
| `roster` | JFC, SaaS | remove: sum series by job title (read CSV and use a for loop) |
| `cohort` / `cohort_contracts` | SaaS | remove: use `spread(curve)` and accounts |
| `cfads` / `uses` / `net_income` / `cf` | PF, LBO | remove: write as series from account movements (`net_income` becomes Layer 3 `net_profit`) |

### `r.*`

| Name | Examples | Destination |
|---|---|---|
| `pl` / `bs` / `cf` | CB, SaaS | Layer 3 (formatted output for a one-company model) |
| `check` / `expect` | JFC, CB, LBO | core: `m.check` (`expect` is syntactic sugar) |
| `table` / `monthly_average` | CB, DCF, JFC | lib (presentation) |
| `sensitivity` | PF | lib: rerender with changed inputs |
| `metric` / `decision` | Five examples | remove: use ordinary variables and `check` |
| `cash` / `equity_cashflow` / `expense` / `gross_margin` / `mrr` | JFC, PF, SaaS | remove: write as series (`gross_margin` and similar names can be named series in Layer 3) |

### Object methods

| Name | Examples | Destination |
|---|---|---|
| `lag` / `lead` / `at` / `where` / `sum` / `min` / `clip` / `mean` | All examples | core: unify as `lag(k)`, `s[t]`, `where`, `sum`, and `b.min` / `b.max` |
| `forward_avg` | PF | remove: sum `lag(-k)` values |
| `inflow` / `outflow` | DCF, LBO, SaaS | core: account properties updated by `move` |
| `days` | JFC | lib (`calendar`) |
| `add` | JFC, PF | remove: use Python lists and for loops |
| `book_value` | CB | core: `asset.balance` |
| `add_new` / `hire_to_meet` / `per_head` / `ratio` / `headcount` / `table` | SaaS | remove |
