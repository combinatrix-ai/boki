# Models, time and series

A boki model is a timeline and a set of named series: expressions that have a value in every period. This page shows how
to set the timeline, build series from arithmetic, earlier periods and conditions, change values over time, add inputs
and scenarios, solve for a value on purpose, and read the results. The examples build on each other, so read the code
blocks as one session.

## The model and its timeline

A {py:class}`~boki.Model` has a name and a timeline of periods. Give it a start, a length for each period (`step`), and
either a number of periods or an end date:

```{doctest}
>>> import boki as b
>>> from boki.units import USD
>>> m = b.Model("Subscriptions", start="2027-01", periods=24, step=b.month)
>>> m.n
24
>>> [period.label for period in m.timeline.periods[:3]]
['2027-01', '2027-02', '2027-03']
```

`step` is `b.month` unless you say otherwise. Use `b.year`, or a multiple such as `3 * b.month` for quarters. With
`end=` instead of `periods=`, the model has every period that starts in or before the month of `end`. Annual periods that
start in January are labelled by year; every other dated period is labelled by its first month:

```{doctest}
>>> annual = b.Model("Annual", start="2027-01", end="2029-12", step=b.year)
>>> [period.label for period in annual.timeline.periods]
['2027', '2028', '2029']
>>> quarterly = b.Model("Quarterly", start="2027-04", periods=4, step=3 * b.month)
>>> [period.label for period in quarterly.timeline.periods]
['2027-04', '2027-07', '2027-10', '2028-01']
```

A label, a date inside the period and an index (from 0, or from the end when negative) all select a period. A model
started with an integer (`start=2027`) has undated periods labelled `"2027"`, `"2028"` and so on, and no dates.

Four built-in series describe the timeline:

| Series | Value in each period |
|---|---|
| `m.t` | The period's index, from 0 |
| `m.date` | The first day of the period ({py:attr}`boki.Model.date`) |
| `m.period_end` | The first day after the period ({py:attr}`boki.Model.period_end`) |
| `m.period_length` | The length of the period in months, so a quarter is 3 |

Periods need not have the same length. {py:func}`boki.timeline` builds a timeline from runs of equal periods, such as
monthly during construction and quarterly after:

```{doctest}
>>> phased = b.Model("Phased", timeline=b.timeline("2027-01", [(3, b.month), (2, 3 * b.month)]))
>>> phased.render()[phased.period_length]
[1, 1, 1, 3, 3]
```

### Counting years and periods

A model year is twelve months from the start of the model, counted from 0, whatever the period length. Keys of
{py:func}`boki.by_year` and the `year=` argument of the reductions below are model years. `m.t` is the zero-based period
index, so the number of the year in an annual model is `m.t + 1`. A kernel such as `b.delay(1)` and the `k` of `lag(k)`
count periods, not months.

## Series are expressions

A {py:class}`~boki.Series` is not a list of numbers. It is an expression that boki evaluates when you ask for results.
{py:meth}`boki.Model.series` names an expression:

```{doctest}
>>> visits = m.series("Visits", 1000 + 100 * m.t)
>>> r = m.render()
>>> r[visits][:3]
[1000, 1100, 1200]
```

`m.render()` evaluates the model and returns a {py:class}`~boki.Result`. `r[visits]` is the list of values, one for each
period. Arithmetic, comparisons and the methods of a series all build new series, and boki checks units as you write
them. A plain number is dimensionless, and `30 * USD` is a quantity with a unit (see
[Units, currencies and rates](units.md)).

## Inputs and scenarios

An input is a named assumption you can change without editing the model. {py:meth}`boki.Model.input` takes a default
and, if you like, values for named scenarios. A render picks a scenario with `scenario=`, and `inputs=` overrides single
inputs by object or by name:

```{doctest}
>>> conversion = m.input("Conversion", 0.04, scenarios={"bear": 0.03})
>>> signups = m.series("Signups", visits * conversion)
>>> m.render()[signups][:3]
[40.0, 44.0, 48.0]
>>> m.render(scenario="bear")[signups][:3]
[30.0, 33.0, 36.0]
>>> m.render(inputs={"Conversion": 0.05})[signups][:3]
[50.0, 55.0, 60.0]
```

A scenario applies only to the inputs that declare it, and the others keep their defaults. An input whose default is a
table has a value in each period, as `price` below does. `choices=` limits an input to a list of allowed values, or maps
names to values. Inputs are the parameters of the model: in Excel they are the cells on the Inputs sheet, and the
formulas that read them recalculate when you change them.

## Functions of the period

When a rule is easier to write as Python than as an expression, decorate a function of the period index `t` with
`@m.series`. Inside the function, `x[t]` is the value of another series as a plain number, so ordinary `if` works:

```{doctest}
>>> @m.series
... def customers(t):
...     if t == 0:
...         return signups[t]
...     return customers[t - 1] * 0.95 + signups[t]
>>> @m.series
... def promo(t):
...     return 0.1 if customers[t] < 150 else 0.0
>>> r = m.render()
>>> [round(v, 1) for v in r[customers][:3]]
[40.0, 82.0, 125.9]
>>> r[promo][:5]
[0.1, 0.1, 0.1, 0.0, 0.0]
```

The `t == 0` case is not optional. A negative index counts from the last period, so `customers[t - 1]` in the first
period reads the last one, which depends on the first, and the render stops with a {py:class}`~boki.CycleError`.

A function series runs Python, so the Excel output cannot turn it into a formula. `to_excel` writes its values instead,
highlighted. Prefer an expression when the result should stay live in Excel.

## Earlier periods, running totals and conditions

{py:meth}`~boki.Series.lag` reads a series `k` periods earlier. Periods that fall before the start are missing (`None`)
unless you give `fill=`. Missing values propagate through arithmetic, and the reductions skip them.
{py:attr}`~boki.Series.opening` is `lag(1, fill=0)`, and {py:attr}`~boki.Series.change` is the series minus its opening.
{py:meth}`~boki.Series.cumsum` is the running total:

```{doctest}
>>> r[signups.lag(1)][:3]
[None, 40.0, 44.0]
>>> r[signups.lag(1, fill=0)][:3]
[0, 40.0, 44.0]
>>> r[signups.change][:3]
[40.0, 4.0, 4.0]
>>> r[signups.cumsum()][:3]
[40.0, 84.0, 132.0]
```

Python's `if`, `and`, `or` and `not` cannot branch per period, because a series holds no numbers while you write the
model. They raise `TypeError`. Use {py:meth}`~boki.Series.where` to choose a value for each period, and `&`, `|` and `~`
to combine conditions:

```{doctest}
>>> r[signups.where(signups > 45)][:3]
[None, None, 48.0]
>>> r[signups.where(signups > 45, 0)][:3]
[0, 0, 48.0]
>>> try:
...     if signups > 45:
...         pass
... except TypeError:
...     print("use where() instead")
use where() instead
```

{py:func}`boki.min` and {py:func}`boki.max` compare series period by period, for caps and floors. A series reduces over
its periods to one number with {py:meth}`~boki.Series.sum`, {py:meth}`~boki.Series.min`, {py:meth}`~boki.Series.max`,
{py:meth}`~boki.Series.mean` and {py:meth}`~boki.Series.last`. Pass `year=` to reduce over one model year:

```{doctest}
>>> [round(v) for v in r[b.min(customers, 300)][4:8]]
[219, 268, 300, 300]
>>> r[signups.sum()], r[signups.sum(year=0)], r[signups.sum(year=1)]
(2064.0, 744.0, 1320.0)
>>> r[signups.mean()], r[signups.last()], r[signups.last(year=0)]
(86.0, 132.0, 84.0)
```

## Values that change over time

Three functions make a series from a table of values:

- {py:func}`boki.by_year` takes model years (`0` is the first twelve months). A period label or a date selects the model
  year that contains it.
- {py:func}`boki.step` takes periods, dates or labels. A value holds until the next key, and periods before the first
  key have no value.
- {py:func}`boki.by_month` takes calendar months, for seasonality. It needs dated periods of one month.

Integer keys mean different things: `b.by_year({1: x})` starts in the second twelve months, and `b.step({1: x})` starts
in the second period, whatever its length. When a table feeds an expression, name it with
{py:meth}`~boki.Model.input`. It then has a row on the Inputs sheet in Excel, and `to_excel` raises
{py:exc}`~boki.excel.UnnamedAssumption` for a table without a name.

```{doctest}
>>> price = m.input("Price", b.by_year({0: 30 * USD, 1: 33 * USD}))
>>> season = m.input("Seasonality", b.by_month({11: 1.2, 12: 1.4}, default=1.0))
>>> revenue = m.series("Revenue", customers * price * season)
>>> r = m.render()
>>> [r.value(price, label) for label in ("2027-12", "2028-01")]
[30.0, 33.0]
>>> [r.value(season, label) for label in ("2027-10", "2027-11", "2027-12", "2028-01")]
[1.0, 1.2, 1.4, 1.0]
>>> round(r.value(revenue, "2027-12"), 2)
24876.1
```

## Spreading amounts over time

A kernel says how one amount falls over its own and later periods. {py:func}`boki.delay` moves it later,
{py:func}`boki.even` spreads it evenly, {py:func}`boki.curve` takes your own weights, and {py:func}`boki.mix` blends
kernels. {py:meth}`~boki.Series.spread` applies a kernel to a series. Here, 70% of each month's revenue is collected in
the month and 30% a month later:

```{doctest}
>>> collected = m.series("Cash collected", revenue.spread(b.mix({b.delay(0): 0.7, b.delay(1): 0.3})))
>>> r = m.render()
>>> [round(r.value(collected, label)) for label in ("2027-01", "2027-02", "2027-03")]
[840, 2082, 3382]
```

The same kernels set payment terms and recognition on the lines of an entity (`settle=`, `recognize=`); see
[Entities, statements and the ledger](statements.md).

## Declaring a series before defining it

Python runs from top to bottom, so a series cannot use a name that does not exist yet. When a series depends on its own
past, or two series depend on each other through earlier periods, declare one with {py:meth}`~boki.Model.series` and no
expression, and give it its expression with {py:meth}`~boki.series.Named.define` once the others exist. This is the
expression form of `customers`. It gives the same numbers, and it stays a formula in Excel:

```{doctest}
>>> active = m.series("Active customers")
>>> _ = active.define(active.lag(1, fill=0) * 0.95 + signups)
>>> all(abs(a - c) < 1e-9 for a, c in zip(m.render()[active], m.render()[customers]))
True
```

Interest on the cash balance is another case. The interest of a month depends on the balance at the start of it, and the
balance depends on the interest. Declare the balance with the unit it must have, then define it:

```{doctest}
>>> costs = m.series("Costs", 3000 * USD + 5 * USD * active)
>>> cash = m.series("Cash", unit=USD)
>>> opening = cash.lag(1, fill=20_000 * USD)
>>> interest = m.series("Interest income", opening * 0.002)
>>> _ = cash.define(opening + collected - costs + interest)
>>> [round(v, 2) for v in m.render()[cash][:3]]
[17680.0, 16387.36, 16172.53]
```

A series that is declared but never defined raises `ValueError` when it is evaluated. A series made with `data=` holds
fixed values and cannot be defined later.

## Circular references, unknowns and solve

A cycle in the same period is an error, because boki cannot say which value comes first. The message names the loop:

```{doctest}
>>> loan = b.Model("Loan", start="2027-01", periods=3, step=b.year)
>>> debt = loan.series("Debt")
>>> idc = loan.series("Interest during construction", debt * 0.08)
>>> _ = debt.define(1000 * USD + idc)
>>> try:
...     loan.render()[debt]
... except b.CycleError as error:
...     print(error)
circular reference: Debt -> Interest during construction -> Debt (in 2027)
Break it by reading an earlier period (x.lag(1)), or wrap the loop in m.solve(...).
```

Some loops are real: the debt you need depends on the interest you pay while building, which depends on the debt. Make
that circularity explicit. Declare the value as an {py:meth}`~boki.Model.unknown` and state the equation it must satisfy
with {py:meth}`~boki.Model.solve`. The equation `u == expression`, with the unknown alone on the left, iterates to a
fixed point:

```{doctest}
>>> loan = b.Model("Loan", start="2027-01", periods=3, step=b.year)
>>> debt = loan.unknown("Debt", init=1000 * USD)
>>> idc = loan.series("Interest during construction", debt * 0.08)
>>> loan.solve(debt, debt == 1000 * USD + idc)
>>> r_loan = loan.render()
>>> round(r_loan[debt], 2), round(r_loan[idc], 2)
(1086.96, 86.96)
```

Any other equation for a single unknown is a goal seek, as in Excel. The `init` of an unknown is the starting guess, and
it picks one solution when there are several. Back in the subscription model, this finds the price at which the first
year just covers its costs:

```{doctest}
>>> break_even = m.unknown("Break-even price", init=30 * USD)
>>> m.solve(break_even, (customers * break_even * season).sum(year=0) == costs.sum(year=0))
>>> round(m.render()[break_even], 2)
13.63
```

An unknown made with `per_period=True` has a value in each period. With `integer=True`, `>=` and `<=` conditions find the
smallest whole number that satisfies them in each period, starting the search at `min`. Here it is the support staff
needed at 60 customers each:

```{doctest}
>>> staff = m.unknown("Support staff", per_period=True)
>>> m.solve(staff, staff * 60 >= customers, integer=True, min=1)
>>> m.render()[staff][:6]
[1, 2, 3, 3, 4, 5]
```

Only values passed to `solve` are solved, and every other cycle stops with a `CycleError`. A solve that does not
converge raises `ArithmeticError`. `m.render(fix={unknown: value})` skips the solve for an unknown and uses the value you
give, for example a number pasted from a source workbook.

## Time points and discounting

Flows occur at the end of each period. {py:func}`boki.lib.discount` is the end-of-period discount factor, so the first
period is discounted by one period. {py:func}`boki.lib.npv` returns the value at the start of the model, as Excel's
`NPV` does. Pass `at=0` for the value at the end of the first period, and pass a one-off flow at the start of the model,
such as an investment, with `initial=`. {py:func}`boki.lib.irr` takes `initial=` the same way. Rates are per period:

```{doctest}
>>> project = b.Model("Project", start="2027-01", periods=3, step=b.year)
>>> flows = project.series("Net cash flow", data={0: 40, 1: 50, 2: 60})
>>> r_project = project.render()
>>> [round(v, 4) for v in r_project[b.lib.discount(0.1)]]
[0.9091, 0.8264, 0.7513]
>>> round(r_project[b.lib.npv(flows, 0.1)], 2), round(r_project[b.lib.npv(flows, 0.1, at=0)], 2)
(122.76, 135.04)
>>> round(r_project[b.lib.npv(flows, 0.1, initial=-100)], 2), round(r_project[b.lib.irr(flows, initial=-100)], 4)
(22.76, 0.2165)
```

A rate that changes by period is a series, such as `m.input("WACC", b.by_year({...}))`. `npv` then discounts each flow by
the product of `1 + rate` up to its period, so do not build the cumulative factor yourself.

Add a period only when something happens during it. A balance sheet at founding or acquisition is not a period: start
the timeline in the first year of operations and record the opening balances with `co.bs.opening(...)`. An investment on
the first day of a cash-flow model goes into `initial=`. A year of construction, or a decision point with several flows
on day zero, is a period, and `at=0` values it at the end of that year.

## Reading results

`r[x]` gives all the values of a series, one for each period, or one number for a scalar series such as an input or
`x.sum()`. It also takes a name (`r["Revenue"]`) and any expression (`r[revenue * 2]`). {py:meth}`~boki.Result.value`
reads one period by label, date or index, and a negative index counts from the end:

```{doctest}
>>> r = m.render()
>>> [round(r.value(revenue, period), 2) for period in ("2027-03", "2027-03-15", 2)]
[3777.0, 3777.0, 3777.0]
>>> r.value(revenue, -1) == r["Revenue"][-1]
True
>>> r.value(price, "2028-06")
33.0
```

Values are plain numbers in base units: currency units, watts, watt-hours and months. A value is `None` where the series is
missing. Each `m.render()` is independent, so you can render the same model with other scenarios and compare. For several
series side by side, {py:meth}`~boki.Result.table` returns a table that prints as text, and `where=` limits the periods
shown:

```{doctest}
>>> print(r.table([visits, signups, revenue], where=m.t < 3))
         2027-01  2027-02  2027-03
Visits     1,000    1,100    1,200
Signups       40       44       48
Revenue    1,200    2,460    3,777
```

Statements for an entity (`r.pl(co)`, `r.bs(co)`, `r.cf(co)`) and the Excel workbook (`r.to_excel(...)`) also come from
the result. To make the model state what must hold, and to compare it with another source, see
[Checks and expectations](checks.md).
