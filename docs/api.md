# boki API style (v0.0.2 proposal)

Proposal (2026-10-16), not yet implemented. The corpus `research/corpus/*/plan.py` files use this API style.

History: The shortened v0.0.1 proposal ([methods.md](methods.md)) had users create accounts and post moves. Based on the user's proposal that ``XXX special loss = parent.special_loss(data={"2022/7": 500})`` return a series with company, GAAP, and account type, the design changed so **entity methods create statement rows that carry their account kinds**. The user said `@m.series` was "brilliant" and `parent.pl.special_...` was "really good."

## Core data

```text
Series     Value per period. A lazily evaluated expression object with a unit.
LineItem   Series + entity + accounting standard + kind (a type such as Revenue or SpecialLoss).
           Creates double-entry journal entries with counter-accounts internally.
Entity     Company with an accounting standard and fiscal calendar. Creates LineItems in pl and bs namespaces.
Model      Outer container for the period axis, inputs, and evaluator. Entities belong to it.
```

## Model and periods

```python
import boki as b
from boki.units import JPY, USD, month, year

m = b.Model("Plan", start="2027-04", end="2032-03", step=b.month)
m.t        # Series of period indexes.
m.date     # Series of period start dates; m.period_end is the next period's start.
# m.period_end - 1 * b.day is the last day of each period, m.date + 14 * b.day a date two weeks in, and
# m.period_end - m.date the days in each period (a number in b.day). Months and days do not mix.
# m.date.year and m.date.month (1-12) are the calendar year and month of a date series.
```

Each period can have its own length, such as monthly periods during construction and quarterly periods after operations begin.

Name assumptions that need rows, including `b.by_year`, `b.step`, and period data: `m.input("Churn rate", b.by_year({...}))`. If an unnamed assumption is used directly in an expression, `to_excel` raises an error with its source (`file:line`) and the row that uses it. A single number can stay inline.

Express time points as dates or period labels ([api-principles.md](api-principles.md) §5). `b.by_year({"2028-04": 0.05})` applies to the model year containing that date; `b.step({"2028-06": 120})` starts that period; and `draw={"2027-07": 50 * JPY}` draws in that period. Annual models can use `"2028"`. Integers remain period indexes (model years for `by_year`), mainly for `at=0` and loops. Times outside the model raise errors.

```python
m = b.Model("Solar", timeline=b.timeline("2015-09", [(9, b.month), (100, 3 * b.month)]))
```

### Currency and FX

```python
m.fx(USD, JPY, closing=close_rate, average=average_rate, opening=150)
us = m.entity("US Inc.", currency=USD)   # Functional currency
```

The `m.fx(base, quote, ...)` rate is units of `quote` per unit of `base`. `closing` and `average` are series by period; `opening` is a single rate at the model start. Translate a consolidated subsidiary's balances and income to the parent's currency. Set `net_investment=True` on an intercompany loan in a different currency to post its FX gain or loss to the consolidated foreign-currency translation adjustment. Set `fx_rate=` to the transaction-date rate for intercompany capital transactions and dividends.

## Inputs

```python
price = m.input("Price", 3000 * JPY)                                       # Constant.
price = m.input("Price", b.step({"2027-04": 3000, "2028-04": 3500}) * JPY) # Changes on each date and remains until the next one.
season = m.input("Seasonality", b.by_month({12: 1.4, 1: 1.2}, default=1.0))      # By calendar month in a monthly model (or a list of twelve from January).
churn = m.input("Churn rate", 0.03, scenarios={"Bear": 0.05})
```

Resolve inputs during render. Use a Python `if` to choose which factory to build; this branches while assembling the model.

## Series

Define a series with expressions:

```python
revenue = m.series("Revenue", customers * price)
revenue.lag(1)              # Previous period; lag(-1) is the next period.
revenue.lag(k, fill=0)      # k can be a series: a different offset in each period.
revenue[t]                  # Value in a given period.
revenue.where(cash > 0, 0)  # Branch by period.
b.round(x, 2), b.rounddown(x, 1), b.roundup(x, -3)   # Excel's ROUND, ROUNDDOWN, ROUNDUP.
b.floor(x), b.ceil(x), x % 12, x // 12, b.mod(x, n)  # INT, ceiling, MOD, INT(x/n).
b.exp(x), b.log(x), b.sqrt(x)                        # Of plain numbers.
x.sum(), x.min(), x.max(), x.mean()                  # Over all periods; x.where(c).mean() averages where c holds.
x.sum(year=0), x.mean(year=1), x.last(year=2)        # Over model year 0 (the first 12 months, as b.by_year counts); last = year-end value.
```

**Define a function for each period with `@m.series`:** Use regular Python `if` statements.

```python
@m.series(unit=JPY)
def dividend(t):
    if cash[t - 1] < 1e8 * JPY:
        return 0 * JPY
    return net_income[t - 1] * 0.3
```

Write a recurrence that refers to its previous period the same way:

```python
@m.series
def customers(t):
    return 100 if t == 0 else customers[t - 1] * (1 - churn) + new_customers[t]
```

Declare a series before defining it when two series refer to each other. Python runs top to bottom, so declare the name first and use `define` to set the expression.

```python
need = m.series("Funding need")        # Forward declaration.
draw = (need - equity_first) * share
need.define(project_cost + idc + fees)
```

Set a value for one period with `data=`. Periods without a value default to 0.

```python
transfer_cost = m.series("Transfer costs", data={"2028-07": 5_000_000 * JPY})
```

## Entities and statement rows

```python
parent = m.entity("Parent", standard=b.JGAAP, fiscal=b.fiscal(year_end="03-31"))
```

Pass the default tax rate with `tax_rate=` for entities that use deferred taxes or taxable OCI. boki raises an error if a required tax rate is missing.

`parent.pl` and `parent.bs` expose only the kinds in that entity's **layout**. If you do not specify a layout, boki uses the general layout for the entity's accounting standard. A Japanese GAAP entity has `pl.special_loss`, but an IFRS entity does not. Accessing it on an IFRS entity raises `AttributeError`.

Select an industry layout with `layout=`. Layouts are shared across accounting standards, and a standards table (`labels`) supplies standard-specific names. Layouts are data, not code: `src/boki/layouts.py` lists each kind and profit-subtotal formula.

```python
bank = m.entity("VLY", standard=b.USGAAP, layout=b.layouts.bank)
bank.pl.interest_income(...); bank.pl.provision(...); bank.pl.net_interest_income
bank.bs.earning_asset(...); bank.bs.deposits(...); bank.bs.allowance(...)
```

### P&L rows (Japanese GAAP)

| Method | Kind | Counter-account (default) |
|---|---|---|
| `pl.revenue(name, amount, settle=)` | Revenue | Receivables when `settle` is set; otherwise, cash |
| `pl.cogs(name, amount, settle=)` | Cost of goods sold | Payables when `settle` is set; otherwise, cash |
| `pl.sga(name, amount, category=, settle=)` | Selling, general, and administrative expenses (`category` is a type such as personnel or rent) | Same as above |
| `pl.non_operating_income(...)` / `pl.non_operating_expense(...)` | Non-operating income or expense | Cash |
| `pl.special_gain(...)` / `pl.special_loss(name, amount, against=)` | Extraordinary gain or loss | Cash. If `against=` is an asset row, reduce that asset (impairment). |
| `pl.income_tax(name, rate=, base=, nol=True)` / `pl.income_tax(name, amount)` | Income taxes. `rate` is a rate or a taxable-income-to-tax function (for progressive rates, applied after NOLs). `nol=` is True (losses carried forward from zero), an amount carried in from before the model, or False; `tax.nol.balance` / `.used` / `.taxable` read the carryforward. | Cash, or income taxes payable with `settle` |

`bs.fixed_asset` and `bs.loan` create depreciation and interest expense automatically.

Every row is a Series and can be used directly in expressions. Common arguments are `data=` (values for selected periods), `settle=` (settlement delay), `recognize=` (recognition delay, such as prorating annual prepayments), `cash=` (direct cash-flow schedule), and `vat=` (consumption or value-added tax rate). boki uses net-of-tax accounting. Receipts and payments follow the row's cash timing, and remittances use `co.vat_settlement(settle=b.delay(1))`. Combine `recognize=` with `settle=` or `cash=` to set recognition and cash timing separately. If both `settle=` and `cash=` are set, `cash=` takes precedence.

#### Opening receivables and payables (`opening=`, `opening_collect=`)

An existing business starts with money owed to it. `opening=` on a row that has `settle=` is the balance outstanding at the model start from that row's pre-model sales (pre-model purchases for expense rows, which open a payable). It is added to the opening balance of the shared receivable (payable) that `settle=` uses, so it is on the opening balance sheet and `co.bs.opening(...)` balances retained earnings as for any other opening balance. `opening=` without `settle=` is a `TypeError`.

```python
# A food maker on 60-day terms: monthly model, 60 days = settle=b.delay(2).
co.bs.opening(cash=500 * JPY)                                    # Retained earnings balances the sheet.
co.pl.revenue("Sales", sales, settle=b.delay(2), opening=240 * JPY)   # 240 owed by customers at the start.
co.pl.cogs("Ingredients", cost, settle=b.delay(1), opening=80 * JPY)  # 80 owed to suppliers at the start.
```

By default boki assumes the pre-model sales were steady, so the opening balance is collected on the same terms as new sales. With kernel weights `w[k]` (the share of a period's amount settled `k` periods later), period `j` collects `opening * T_j / sum(T)` where `T_j` is the sum of `w[k]` for `k > j`. `settle=b.delay(2)` collects half in the first period and half in the second; `b.delay(1)` collects all of it in the first. Collections are cash in and credit the receivable (cash out and debit the payable for expense rows). `b.delay(0)` leaves nothing outstanding, so it needs `opening_collect=`.

`opening_collect={period: amount}` replaces that schedule (keys as elsewhere: period index, date or label). The amounts must sum to `opening=` (otherwise `ValueError` naming both totals), none may be negative, and they must be plain amounts, not series.

```python
co.pl.revenue("Sales", sales, settle=b.delay(2), opening=240 * JPY,
              opening_collect={"2027-01": 90 * JPY, "2027-02": 150 * JPY})   # Known invoices and due months.
```

Several lines share one receivable, and their openings add up. Do not declare `co.bs.receivable("Accounts receivable", opening=...)` next to a `settle=` row: it collides with the shared account and raises an error that points to `opening=`. `opening=` does not combine with `counterparty=` or `against=`. In Excel the default collections are live formulas of the opening amount; `opening_collect=` is written as data cells.

### P&L totals (Japanese GAAP subtotals)

```python
parent.pl.revenue.total                 # Sum of revenue rows; each kind namespace also exposes its total.
parent.pl.sga.total_of(category="Personnel expense")  # Subtotal by category.
parent.pl.gross_profit                  # Gross profit.
parent.pl.operating_income              # Operating income.
parent.pl.ordinary_income               # Ordinary income (Japanese GAAP only).
parent.pl.pretax_income                 # Income before taxes.
parent.pl.net_income                    # Net income.
```

### EBITDA and its relatives

boki provides the parts of EBITDA and never a default EBITDA: `co.ebitda`, `co.adjusted_ebitda`, `co.ebitdar`, `co.ebit` and `co.noi` (on entities and groups) raise an `AttributeError` that shows how to build the measure. EBITDA is non-GAAP under J-GAAP, IFRS and US GAAP, and the definitions differ by company and by covenant, so the choice stays visible in your plan.

```python
ebitda = m.series("EBITDA", co.operating_income + co.depreciation + co.amortization)
covenant = m.series("Covenant EBITDA", co.operating_income + co.depreciation + co.amortization + restructuring)
```

| Part | Meaning |
|---|---|
| `co.operating_income` | The layout's operating income subtotal. A layout without one (the bank layout) raises `AttributeError`. |
| `co.depreciation` | Depreciation of tangible assets: every `fixed_asset` line and completed `construction` line, wherever the expense is posted (any PL kind, any `category=`, `depreciation=`, capex programs). Impairment is not included. |
| `co.amortization` | The same for `intangible` lines. On a group (`g.amortization`) it also holds goodwill amortization (`goodwill_life=`) and the amortization of acquired intangibles. Impairment is not included. |

The three names work the same on a group (`g.operating_income`, `g.depreciation`, `g.amortization`), from the consolidated books: intercompany profit in depreciated assets is eliminated, and the unwind of an acquisition fair-value step-up counts as depreciation for a fixed asset and as amortization for an intangible. The unwind of a liability, inventory or any other item is not D&A and stays out of both. The Excel export keeps these series as live formulas.

Where the standards differ (EBITDA is built from the same parts under each; the inputs differ):

| Topic | J-GAAP | IFRS | US GAAP |
|---|---|---|---|
| Goodwill | Amortized (up to 20 years, in SG&A), so J-GAAP EBITDA conventionally adds it back | Not amortized (impairment only) | Not amortized; private companies may elect amortization |
| Impairment | Extraordinary loss, below operating income | Within operating results; adding it back is your choice | Within operating results; adding it back is your choice |
| Leases | boki has no lease accounting yet. A new standard modeled on IFRS 16 | IFRS 16: most leases on the balance sheet (depreciation plus interest) | ASC 842: operating leases stay a straight-line operating cost |
| Operating income | Defined | IFRS 18 (effective 2027-01-01) defines operating profit | No required subtotal |
| Development costs | Expensed | Capitalized when criteria are met (amortization is in `amortization`) | Expensed |

### BS rows

Kinds in the general balance-sheet layouts:

| Kind | Behavior | Default CF section |
|---|---|---|
| `receivable`, `inventory`, `prepaid`, `working_capital`, `other_current_asset` | Generic row | Operating |
| `payable`, `accrued`, `deferred_revenue`, `other_current_liability`, `lease_liability`, `other_liability` | Generic row | Operating |
| `deposit`, `other_asset` | Generic row | Investing |
| `fixed_asset`, `intangible` | Acquisition and depreciation | Investing |
| `construction` | Construction in progress; depreciated after completion | Investing |
| `loan` | Borrowing | Financing |
| `capital`, `nci` | Equity (share capital, non-controlling interests, and more) | Financing |
| `dividend` | Dividend from retained earnings | Financing |
| `deferred_tax_asset`, `deferred_tax_liability` | Deferred tax asset or liability (non-current and non-cash) | Operating |
| `oci` | Accumulated other comprehensive income | Financing |

All generic rows use the same arguments. The kind determines the row's position in the layout and its default CF section. Wherever a row takes an amount (`amount`, `spend=`, `cost=`, `draw=`, `repay=`), a dict gives amounts in selected periods, as in `draw={"2027-07": 50 * JPY}`; generic rows also take it as `data=`.

```python
co.bs.receivable("Accounts receivable", target=revenue * 0.12, opening=3_232 * USD) # Match a target balance; cash changes by the difference.
co.bs.other_asset("FDIC", -20_000 * USD, opening=89_359 * USD)                      # Periodic changes offset cash.
co.bs.other_liability("Other", opening=1_431 * USD)                                # Opening balance only; use journal entries for changes.
co.bs.asset("Name", ..., section="current", cf=, tags=)                            # Generic asset or liability outside the layout.
co.bs.liability("Name", ...)
```

| Method | Behavior |
|---|---|
| `bs.cash` | Cash (one balance series per entity) |
| `bs.opening(cash=, retained_earnings=)` | Opening BS. If retained earnings are omitted, boki calculates the balancing value. If both values are set, boki checks that the BS balances. |
| `bs.fixed_asset(name, cost, at=, life=, method=, salvage=, depreciation=, opening=)` | Acquires a fixed asset with cash and creates depreciation expense. With `cost=` a series and no `at=` (a capex program, such as one fit-out per store opening), each period's spend is depreciated straight-line over `life=` from the next period. |
| `bs.construction(name, spend, complete_at=, life=, opening=)` | Construction in progress. |
| `bs.loan(name, draw=, rate=, repay=, opening=, target=, capitalize_during=, capitalize_into=, counterparty=, net_investment=False)` | Borrowing with `.balance`, `.interest`, `.principal`, and `.draw_or_repay(series)` for net changes in a period, such as a revolver or adjustment. `rate=None` means no interest expense. `capitalize_during=` capitalizes interest in those periods; `capitalize_into=` a `bs.construction` row adds it to that asset's cost so it is depreciated after completion (without it, the interest sits in a shared construction-in-progress account that is never depreciated). `net_investment=True` posts FX gains or losses on a loan to a counterparty with another currency to consolidated OCI. |
| `bs.capital(name, amount, at=, opening=, cf=, counterparty=, fx_rate=)` | Share capital, treasury shares, and other equity items. Set `counterparty=` for intercompany capital transactions and `fx_rate=` for the transaction-date exchange rate. |
| `bs.dividend(name, amount, counterparty=, fx_rate=)` | Dividend from retained earnings. Set `counterparty=` for intercompany dividends and `fx_rate=` for the transaction-date exchange rate. |
| `bs.total_assets` / `bs.total_liabilities` / `bs.total_equity` / `bs.equity.total` | Series for BS totals. |
| `co.journal(name, amount, debit=, credit=, cf=)` | Transfers between two accounts, such as lease assets and liabilities, profit attributable to non-controlling interests, and pensions. Override the CF section for a journal entry against cash. |

BS rows expose `.balance` (ending balance), `.opening` (opening balance; the declared opening balance in the first period), and `.change`. Kind namespaces also expose `.total` and `.opening`, as in `bank.bs.earning_asset.opening`.

### Deferred taxes and OCI

```python
co = m.entity("Co", tax_rate=0.3)
co.bs.deferred_tax("Depreciation difference", temporary_difference, recognized=0.8)
co.oci("Fair value change", fair_value_change, against=security, recycle=True, tax=True)
co.oci_release("Fair value change", amount)
co.comprehensive_income
```

`difference` in `deferred_tax` is the temporary difference at each period-end. A positive value creates a deferred tax liability; a negative value creates a deferred tax asset. `recognized=` is the share of deductible temporary differences to recognize. If `rate=` is omitted, boki uses the entity's `tax_rate`. Tax changes appear in the income tax expense adjustment row and do not affect cash.

`amount` in `oci` is OCI generated in each period. boki transfers it against the account in `against=`. Set `tax=True` to recognize tax effects at the entity's rate and show OCI net of tax. OCI with the same name shares one account and keeps the first `recycle=` value. `amount` in `oci_release` is pre-tax. With `tax=True`, boki also reverses deferred taxes for the released amount, and the OCI balance decreases by the after-tax amount. With `recycle=True`, transfer the pre-tax amount to the P&L, and have the caller record the realized tax in the income-tax row. Otherwise, transfer the pre-tax amount directly to retained earnings. Neither treatment moves cash. `comprehensive_income` is net income plus after-tax OCI. If OCI exists, `r.pl(co)` and the Excel income statement show OCI and comprehensive income.

### Cash-flow rows

Cash flow is a ledger view, so its sections are available as series: `co.cf.operating`, `co.cf.investing`, `co.cf.financing`, `co.cf.fx`, and `co.cf.financing_excluding(revolver)`.

```python
before = co.bs.cash.opening + co.cf.operating + co.cf.investing + co.cf.financing_excluding(revolver)
revolver.draw_or_repay(-b.min(before, revolver.opening))     # Borrow the shortfall or repay the excess.
```

### Quantities

Non-monetary quantities such as customer counts, account executives, and inventory units are ordinary series. They do not appear in the income statement or balance sheet. Unit and cycle checks provide guardrails ([api-principles.md](api-principles.md) §4).

```python
basic = m.series("Basic", unit=account)
pro = m.series("Pro", unit=account)
b0, p0 = basic.lag(1, fill=100 * account), pro.lag(1, fill=30 * account)
up = m.series("Basic to Pro", b.round(b0 * 0.005))                 # Reuse a named flow in two places.
basic.define(b0 + new_basic - up - b.round(b0 * 0.03))
pro.define(p0 + up)
```

### Display units

Values are always stored and computed in base units (W, Wh, per month); a series also has a display unit that decides how `r.table(...)` and the Excel Model sheet show it. The unit is chosen in this order:

1. `display=`: `m.series("generation", expr, display=MWh)`, `m.input("churn", 0.01 / month, display=1 / year)`. It must have the series' dimension (`UnitError` otherwise) but may use another time base, so a monthly rate can be shown per year.
2. The unit a quantity literal was written in: `m.input("sold", 400 * MWh)` and `m.series("capacity", 6000 * kW)` show in MWh and kW.
3. A computed physical quantity (W, Wh, g, m, and their per-month forms) takes the power-of-1000 SI prefix that puts the row's largest absolute value over all periods in [1, 1000): Wh, kWh, MWh, GWh. The whole row uses one unit.

Money is never prefixed (the style's `money=` shows it), and counts and dimensionless numbers have no prefix. Tables name the unit after the label (`generation (GWh)`) when it is not a base unit; `Result.display_unit(series)` returns it. `r.table(..., unit=kWh)` and `to_excel(units={series: kWh})` override the choice.

In Excel the Unit column shows the display unit. A power of 1000 above the base unit (kW, MWh) is shown by number format alone, so formula cells keep base units and ranges are unaffected. Any other factor (a rate per year, a milli prefix) is applied like `b.row(scale=)`: the cell holds the display value and every formula that refers to it converts back; a range over such a row is written as values. A row placed with its own `sign=` or `scale=` keeps that and shows no display unit. Editable cells never rely on a number format: on the Inputs sheet an input written as `400 * MWh` holds 400 (unit column MWh) and formulas convert it back, so typing 500 means 500 MWh. The same holds for data tables (`b.by_year`) on the Model sheet. A range over such a row is written as values.

## Solving

```python
size = m.unknown("Debt amount")
m.solve(size, size == b.min(sculpted_balance[cod], 0.8 * uses))   # Fixed point.
m.solve(hires, capacity >= demand, integer=True, min=0)            # Smallest integer that satisfies the condition in each period.
```

Cycles are detected before evaluation, and errors identify the series in the cycle. Only values passed to `solve` are solved.

The form `u == expression` uses fixed-point iteration. Other forms, such as `npv(cf, r) == 0` and `value == price`, use scalar goal seeking with the secant method. When a cycle has multiple solutions, the initial value in `m.unknown(init=)` selects one.

`m.render(fix={unknown: value})` skips the solve for that unknown and uses the given value, for example a source sheet's pasted or unconverged result.

## Output and checks

```python
r = m.render(scenario="Bear")
r.pl(parent, by="fiscal_year")     # By fiscal year, including irregular fiscal years.
r.bs(parent)
r.cf(parent, method="indirect")
r.table([revenue, parent.bs.cash])
r.table([revenue, customers], by="fiscal_year", entity=parent, stock=[customers])  # Flows sum over the year; balances and stock= rows keep the year-end value.
m.check(parent.bs.cash >= 5e6 * USD, "Minimum cash")   # level="error" by default
r.to_excel("model.xlsx")           # Keep formulas in Excel (docs/excel.md); cells written as values are yellow.
b.compare(r, {co.bs.cash: [..value for each period..], npv(...): 1234})   # Show each number with its difference.
b.expect(r, {...}, tol=0.01)       # Compare with the original Excel results; fail on a mismatch.
b.expect(r, {bcr: b.approx(1.34, tol=0.005), irr(net): b.above(0.5), x: b.between(lo, hi), y: b.below(0)})   # A range or a tolerance for one key.
b.expect(m.render(inputs={...}, fix={unknown: value}), {...})   # Compare with changed inputs and a fixed unknown, such as when the source sheet does not converge.
```

### Checks stop the render

A check is a condition the modeler says must hold, so a failing check stops `render()`. Every check has a level:

```python
m.check(cond, "message")                       # level="error" (default): a failure raises CheckFailed
m.check(dscr >= 1.2, "DSCR covenant", level="warn")   # a benchmark the plan may miss: warns and goes on
m.check(cond, "message", level="off")          # not evaluated, not reported
co.checks.cash()                               # built-in on every entity, level="error": cash is not negative in any period
co.checks.cash(level="warn")                   # a plan that shows a funding gap on purpose (or "off")
r = m.render(checks="warn")                    # exploring: every "error" check, yours and built-in, warns instead
```

`render()` computes everything first (solves, every check, the result, the ledger tie-outs), then warns for failed `"warn"` checks and raises `CheckFailed` if an `"error"` check failed. The exception lists each failed check on its own line, names the failing periods and, for a comparison of two series, both sides with their values in the period of the largest violation (`Minimum cash (fails in 2028-03, 2028-04, ...; worst 2028-06: Cash -12,400,000 vs 5,000,000)`). It carries `e.result` (the complete result: `e.result[cash]`, `e.result.pl(co)`) and `e.failures`. A passed or failed check of every level except `"off"` is in `r.checks`, each with `name`, `level`, `passed`, `periods` and `detail`. `checks=` accepts only `"warn"`; other values raise `ValueError`, as does a `level=` other than `"error"`, `"warn"` or `"off"`. `co.checks` is the place where further built-in checks will be added. Group books have no cash check. The Excel `Checks` sheet lists your checks (not `"off"` ones), and a check that fails in a period is shown in red.

The engine checks the consistency of the three statements on every run: the balance sheet balances, total cash flow equals the change in cash, net income equals the change in retained earnings, and direct cash flow equals indirect cash flow.

### Excel row placement

Use `sheets=` to specify, in reading order, which sheet contains each row ([api-principles.md](api-principles.md) §8).

```python
revenue_row = b.row(revenue, label="Revenue")
r.to_excel("plan.xlsx", sheets=[
    b.sheet("Business plan", [
        b.section("Contracts", [new, churned, customers]),
        b.section("Revenue", [price, revenue_row]),       # Placing an input adds a reference to its Inputs row.
    ]),
    b.sheet("Summary", [b.link(revenue_row), cost, margin]),    # b.link repeats a placed row; its formula lives in one place.
])
```

- A placed series writes its formula in that row. Placing the same series twice with `b.row` raises an error; use `b.link` to repeat it.
- Named series that are not placed expand inline in formulas that use them. Series that need their own rows (balances, recurrences, and data) and ledger statements (P&L, BS, and CF) stay on the Model sheet.
- Use `label=` when placing an unnamed series.
- `b.row(cost, sign=-1)` displays expenses as negative values. `b.row(revenue, scale=1000)` displays values in thousands (cell value = value × sign ÷ scale). Formulas and statements that reference this row use the original value, so display settings do not change results. `b.link` uses the same display settings as the source row. Range functions such as MIN and IRR that reference this row use its value cell, which appears in the report.

## Standard library (`boki.lib`)

For conventions about timing, year zero, signs, units, cycles, and reconciliation, see `docs/conventions.md`.

Accounting-independent functions include `compound`, `fade`, `index`, `by_year` (keyed by date, display year, or zero-based model year), `step`, `delay`, `even`, `mix`, `curve`, `npv(cf, r, at=, initial=)` (moves period-end cash flows to the model start, or to the end of period `at`; `r` may be a series, and each flow is then discounted by the product of `1 + r` up to its period, as `discount(r)` does), `irr(cf, initial=, running=, default=)`, `xirr(cf, dates)`, `xnpv(cf, rate, dates)` (actual/365 from the first date), `gordon`, `discount`, `capm`, `hamada`, `wacc`, `pmt`, `levelized`, `macrs(years)` and `straight_line(years)` (tax depreciation kernels), `lookup(x, {lower_bound: value})` (range lookup), `b.nol(base, opening=, cap=)` (a tax loss carryforward outside the ledger: `balance`, `used`, `taxable`; `cap=0.8` limits use to 80% of a period's profit), and `black_scholes` (real options). Expand this list with sources for each definition and convention.

`irr(cf, running=True)` is the IRR of the flows up to each period (Excel's `IRR($C5:C5)` filled right); it reads only the periods so far, so later flows can depend on it, as in a partnership flip once the investor's IRR to date reaches its target. `default=` on `irr` and `xirr` is the value where the flows have no rate of return yet (Excel's `IFERROR(IRR(...), 0)`); without it that stays an error.

Excel's `IFERROR` has no general counterpart, so a mistake is not silently turned into 0. Write the guard as a condition instead: `IFERROR(a/b, 0)` is `(a / b).where(b != 0, 0)`, and a lookup outside its table is guarded on its input the same way. Only `irr` and `xirr` take `default=`, because only a root search cannot tell in advance whether it will fail. A negative number to a non-integer power is an error, as Excel's `#NUM!` is.

Sensitivity tables rerender the model with changed inputs: `for v in grid: m.render(inputs={pe: v})`. Keys in `inputs=` must be input nodes or names; unknown keys raise an error.

## Groups

```python
sub = m.entity("Subsidiary A", standard=b.JGAAP, fiscal=b.fiscal(year_end="12-31"))
sub.pl.revenue("Parts sale", qty * price, settle=b.delay(1), counterparty=parent.pl.cogs)   # Record the same amount in the parent's COGS.
parent.pl.revenue("Management fee", 10 * JPY, counterparty=sub.pl.sga)
g = m.group("Group", parent=parent)
g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY, goodwill_life=10 * year)
g.own(sub, 1.0, since=1, consideration=70 * JPY)   # Additional purchase while retaining control.
r.pl(g); r.bs(g); r.cf(g)                         # Consolidated statements eliminate intercompany transactions.
```

- The first `own` requires one of `method="consolidate"`, `method="equity"`, or `method="cost"`. Later increases in ownership retain the previous method.
- `method="consolidate"` consolidates the entity's journal entries from `since=` onward. It excludes pre-acquisition income and includes assets and liabilities on the acquisition date. Partial ownership records non-controlling interests and shows the allocation of profit to non-controlling and parent shareholders on the P&L.
- `method="equity"` does not combine the associate's journal entries. It reclassifies the shares on the parent's separate books as the group's investment in associates. The group recognizes its share of post-acquisition net income and OCI. Equity-method earnings are shown in J-GAAP non-operating income, US GAAP "Equity in earnings of affiliates," or IFRS "Share of profit of associates." `loss_limit=True` recognizes losses until the investment reaches zero, then recovers any excess from later profits first. If embedded goodwill exists, J-GAAP requires `goodwill_life=` for each acquisition. US GAAP amortizes it only with `private_company=True`; IFRS does not specify it. `impairment=` reduces the total investment.
- Use `since="before", method="equity"` with `opening={"investment": ..., "embedded_goodwill": ..., "fair_value": ..., "suspended_losses": ..., "oci": ...}` to resume an equity-method investment at the start of the model. Match `opening["investment"]` to the opening investment recorded by the parent. Move opening cumulative OCI to the OCI account and reduce opening retained earnings by the same amount.
- Split `opening["oci"]` for `since="before", method="consolidate"` into `(parent_part, nci_part)`, and include `nci_part` in `opening["nci"]`. When ownership changes without losing control, reallocate opening OCI according to the acquisition or sale percentage.
- To increase ownership while retaining the equity method, pass the new percentage and `consideration=`. Each purchase creates a separate basis lot based on net assets at that acquisition; measure it using that call's `fair_value=`, `acquired=`, `tax_basis=`, and `goodwill_life=`. To sell part of an equity-method investment, pass the reduced percentage and `proceeds=`. Reduce the consolidated carrying amount by the share sold and show the gain or loss separately from equity-method earnings. Eliminate the parent's separate-book gain or loss on consolidation.
- For a step acquisition that gains control from the equity or cost method, pass `previously_held_value=`. Remeasure the existing interest at fair value and recognize the difference in earnings. Under IFRS, if the existing interest is an FVOCI equity instrument, reclassify OCI to retained earnings.
- Pass `proceeds=` when reducing ownership. On the parent's separate books, reduce shares at average cost and record the separate-book gain or loss. A sale that retains control is consolidated as a change in non-controlling interests and additional paid-in capital; classify its cash flow as financing.
- When control is lost, remove the subsidiary from the consolidation scope at the start of the period. Under US GAAP or IFRS, pass `retained_value=` if an interest remains, and include the fair-value remeasurement difference in consolidated earnings. Under J-GAAP, do not use `retained_value=`; measure an interest that continues under the equity method at its share of net assets plus remaining goodwill. Under the cost method or with no retained interest, use the parent's separate-book carrying amount for the remaining investment and transfer the remaining consolidation adjustment to retained earnings. Follow each OCI component's `recycle=` setting. Classify disposal cash flow as investing and subtract the subsidiary's cash from the proceeds.
- `method="cost"` records the investment at cost on the parent's separate books and recognizes dividends as income. Reducing ownership to 0 removes the investment. When changing methods without changing the ownership percentage, treat consideration and proceeds as 0.
- `consideration=` records on the parent's books the price paid for shares bought from outside the group. If omitted, it refers to the existing "<subsidiary> shares" account on the parent. Do not record one acquisition using both `consideration=` and the existing investment.
- Additional purchases and partial sales that retain control are recorded as equity transactions. A US GAAP partial acquisition requires `nci="fair_value"` and `nci_value=`.
- Specify acquisition-date fair-value adjustments with `fair_value={bs_line: amount}` and unrecorded assets or liabilities with `acquired={name: amount}` (negative amounts are liabilities). `acquired` amounts can also be model inputs or series; the sign determines whether they are recognized as assets or liabilities. For either argument, pass `(amount, remaining_life)` to specify an amortization period. With `tax_basis="carryover"`, record deferred taxes at the subsidiary's rate and reverse them as the item is amortized. With `"stepped_up"`, do not record deferred taxes. J-GAAP requires proportionate non-controlling interests and goodwill amortization (within 20 years). US GAAP requires fair-value non-controlling interests and permits goodwill amortization (within 10 years) only with `private_company=True`. IFRS supports `nci="proportionate"` or `"fair_value"` and does not use `goodwill_life=`. `impairment=` is a series of goodwill impairment amounts.
- Pass `counterparty=` the relevant P&L kind on the other entity. Both sides are generated from one expression, and `settle=`, `cash=`, and `recognize=` apply at the same times to each side. `line.counterparty` refers to the row on the other side.
- Record intercompany product sales with `pl.revenue(..., counterparty=buyer.bs.inventory, margin=, used=)` or `counterparty=buyer.bs.fixed_asset, margin=, life=`. For a sale of an existing fixed asset, use `seller.bs.sell(asset_line, price, at=, counterparty=buyer.bs.fixed_asset, life=)`. The seller's gain or loss is extraordinary under J-GAAP and other income or expense under US GAAP and IFRS.
- Combine the books of consolidated subsidiaries and eliminate intercompany counterpart entries. Eliminate only entries for the transaction, receivable or payable, and settlement; retain subsequent consumption, depreciation, and FX gains or losses. Do not combine the books of equity-method associates or eliminate the other side in full. Dividends the parent receives from an associate reduce the investment. Classify dividends received as operating cash flow and acquisitions of equity-method investments as investing cash flow.
- Pass the other entity as `counterparty=` for loans, capital contributions, and dividends too. `sub.bs.loan("Parent loan", draw=…, rate=0.02, repay=…, counterparty=parent)` creates a loan receivable, matching lending and repayment, and interest income for the parent. `sub.bs.capital("Capital increase", 100 * JPY, at=0, counterparty=parent)` creates the parent's subsidiary shares and payment. `sub.bs.dividend("Dividend", …, counterparty=parent)` creates dividend income for the parent. Consolidation eliminates subsidiary shares and capital, loans receivable and payable, interest, and dividends.
- `to_excel` writes consolidated statements for the group (IS, BS, CF, and detail) and recalculates profit attribution to non-controlling interests, non-controlling interests, equity-method investment balances, and loss limits with formulas. Checks also validate the consolidated balance sheet, cash flow against the change in cash, direct against indirect cash flow, and profit attribution.
- For loans, capital, receivables, and payables with `counterparty=`, `opening=` can create the same opening balance for the other entity. If both entities are in the consolidation scope from the start of the model, eliminate both opening balances from the consolidated opening balance.
- Not yet supported: `target=`, `draw_or_repay`, and `capitalize_during=` for intercompany loans ([api-principles.md](api-principles.md) §3).

For details, see [entities-and-timeline.md](entities-and-timeline.md).

## Other names used in the rewrite

| Name | Meaning |
|---|---|
| `s.change` | Change during a period (`s - s.lag(1)`). `co.bs.cash.change` is the change in cash, or free cash flow. |
| `m.period_length` / `m.period_end` | Series for period length and period-end date. Use them to allocate annual amounts across periods when period lengths vary. |
| `b.table(file#column, by=)` | Read an assumptions table (such as annual prices or monthly factors) as an input. `.over_period()` sums the monthly values within each period. |
| `b.by_year({...})` / `b.step({...})` | Values keyed by model year or switched by date. |
| `bs.fixed_asset(..., depreciation=series)` | Set depreciation directly without tracking the asset individually (for annual valuation models). |
| `bs.fixed_asset(..., sell_at=period)` | Sell at book value in the specified period. |
| `bs.construction(name, spend=, complete_at=, life=)` | Construction in progress; transfer to fixed assets on completion and depreciate thereafter. |
| `loan.capitalized_interest` | Interest added to construction in progress during `capitalize_during=` (to the `capitalize_into=` asset if given). |
| `bs.equity.total` | Total equity, including share capital and retained earnings. |
| `m.render(inputs=, fix=)` | Render with changed inputs, and with an unknown fixed to a given value instead of solved. |

## Lessons from rewriting six models (2026-10-16)

- **Removing account declarations made models read more like prose.** The izakaya example from the public lender now maps almost one-to-one to the formulas and rows in its calculation-basis column (`shop.pl.revenue(...)`, `shop.pl.sga(..., category="Personnel expense")`, `shop.bs.loan(...)`).
- **The tax base needed to be passed in by the user.** For the solar project's CFADS, tax uses an operating base before interest (EBITDA minus tax depreciation), which differs from P&L pretax income. `income_tax(base=...)` supports this.
- **`bs.cash.change` removed the need to assemble free cash flow by hand** (capbudg, LBO). In v0.0.1, cash movements were added up in an expression.
- **`@m.series` works for both recurrences and branches.** NOLs, invested capital, enterprise value updates, and growth-rate cases can use regular Python `if` statements and `x[t - 1]`. This is clearer than v0.0.1's `lambda self: self.lag(1, fill=...)`.
- **Forward declarations (`define`) were needed.** The solar project's funding need includes construction-period interest; that interest depends on draws, and draws depend on funding need. This is not a same-period cycle. Python executes top to bottom, so declare the name first.
- **Unit checks need an explicit escape hatch.** Reproducing a bug in the source sheet (adding kW to euros) required `unchecked_units=True`. Require users to state the escape hatch explicitly and include it in the sanity-check list.
- **Put quantity rows on the Model.** The user decided on 2026-10-16 that this seemed reasonable because common assumptions, such as external factors, may apply across entities. Quantities such as market size and exchange rates can be shared across companies. Filter by name or attribute when aggregating for one company.
- **Remaining rough edges:** Writing a cumulative sum such as `sum(x[s] for s in range(t))` inside `@m.series` is slow; a cumulative function is needed. The capbudg and LBO source models have no accounting standard, so US GAAP was assumed.

## Open questions

- **Customer advances:** If recognition and receipt timing differ through `cash=`, the difference appears as negative receivables. Show a negative amount as customer advances.

- **How to keep formulas in Excel output.** On 2026-10-16, the user noted that retaining formulas in a spreadsheet may require a more complex DSL than `@m.series`, and left this as an open question. An `@m.series` function is Python code and cannot become an Excel formula, so it must be written as a value. Expression objects (`a * b`, `.lag`, `.where`) can become formulas. Preserving recurrences and branches as formulas may require a more expressive DSL whose contents can also be expressed as formulas, such as `b.recur(...)` or `b.if_(...)`.
- **How to declare parameters and pass them to `m.series`.** On 2026-10-16, the user said it would be useful to declare persistent parameters, perhaps with a parameter list in Excel, and that passing parameters into `m.series` raised questions. Currently, `m.input` declares them and expressions or `@m.series` functions reference them as Python variables. The Model holds an input list (`m._inputs`), which could supply an Excel parameter sheet. Open questions include whether to declare function-referenced inputs as dependencies, or record them at runtime, so Excel output can show which parameters each row uses; and how to store input groups (market, price, sourcing, etc.), units, sources, and descriptions.

- Cover all statement kinds, including J-GAAP SGA categories and the kinds and levels used by IFRS and US GAAP.
- Decide how to record dependencies when an `@m.series` function reads another series as `x[t]` (one option is runtime recording).
- Implement units.
