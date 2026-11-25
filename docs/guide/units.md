# Units, currencies and rates

In boki a number can carry a unit, and the model refuses to combine units that do not fit. This page covers how quantities
and units work, how a model and an entity use them, how currencies are kept apart, the difference between a rate per
period and a rate per time, and how values are displayed. The rate rule is the one most worth learning: it decides
whether `0.12` means 12% a year or 12% a month.

## Quantities and units

Multiply a number by a unit to make a quantity: `3 * kW`, `100 * USD`, `12 * month`. The built-in units are listed on the
{doc}`units reference page <../reference/api/units>`. A quantity stores its value in the base unit of its dimension:
each currency in itself, power in W, energy in W×h, and time in months. A year is 12 months, so `2 * year` holds 24.

Quantities of the same dimension add, subtract and compare. Multiplying and dividing makes new dimensions, so
`50 * USD / MWh` is a price per energy. {py:func}`boki.unit` makes a countable unit of your own, such as customers or
GPUs, and a unit defined from another:

```{doctest}
>>> import boki as b
>>> from boki.units import JPY, MWh, USD, kW, kWh, month, year
>>> (3 * kW + 2 * kW).value
5000.0
>>> (2 * year).value
24.0
>>> gpu = b.unit("GPU")
>>> node = b.unit("node", 8 * gpu)
>>> (2 * node + 4 * gpu).value
20.0
```

Quantities of different dimensions do not mix. The error names both sides:

```{doctest}
>>> try:
...     2 * kW + 3 * USD
... except b.UnitError as error:
...     print(error)
cannot add W and USD
```

## Units in a model

Series carry units too. A series takes the unit of its expression, and `unit=` states the unit it must have. The model
below sells the output of a solar plant. The plant's hours in each month come from the number of days in it, which is
`m.period_end - m.date`:

```{doctest}
>>> m = b.Model("Solar", start="2027-01", periods=3, step=b.month)
>>> capacity = m.input("Capacity", 1000 * kW)
>>> load_factor = m.input("Load factor", 0.2)
>>> hours = m.series("Hours", (m.period_end - m.date) / b.day * 24 * b.h)
>>> generation = m.series("Generation", capacity * load_factor * hours)
>>> tariff = m.input("Tariff", 50 * USD / MWh)
>>> revenue = m.series("Revenue", generation * tariff, unit=USD)
>>> r = m.render()
>>> r[hours]
[744.0, 672.0, 744.0]
>>> r[generation]
[148800000.0, 134400000.0, 148800000.0]
>>> r[revenue]
[7440.0, 6720.0, 7440.0]
```

Results are in base units, so `generation` reads in watt-hours, not megawatt-hours. Days and hours are dimensions of
their own: a month is 28 to 31 days, so `month` and `day` never convert silently. Dividing the days of a period by
`b.day` gives a plain number. Inside an `@m.series` function the same expressions are plain floats in base units, so
ordinary Python arithmetic works there.

A plain number is dimensionless. The one exception is a literal `0`, which fits any unit, so `b.max(profit, 0)` works
for a profit in dollars.

## Unit errors

A unit error is raised when the expression is written, with the names of the series involved:

```{doctest}
>>> def show(build):
...     try:
...         build()
...     except b.UnitError as error:
...         print(error)
>>> show(lambda: generation + capacity)
cannot add Generation (W×h) and Capacity (kW)
>>> show(lambda: revenue + 5)
cannot add Revenue (USD) and 5 dimensionless
>>> show(lambda: revenue > 5000)
cannot compare Revenue (USD) and 5,000 dimensionless
>>> show(lambda: m.series("Wrong revenue", capacity * tariff, unit=USD))
'Wrong revenue' is declared in USD but defined in USD/h
```

The last one is the classic slip: a price per energy applied to power, without the hours. The declared unit catches it
where it is made, and the message shows what is missing (a rate per hour where money was expected). Without `unit=`, the
series would carry `USD/h` and the error would surface only where it meets a money series.

Every unit error stops the model before any value is computed, and a spreadsheet would add the same two columns without
a word. Declare `unit=` on the series whose unit you know, such as money rows and the totals you compare with a source.

## Currencies

Each currency is a dimension of its own, so `USD` and `JPY` do not convert. An entity books in one currency. Declare it
with `m.entity(..., currency=JPY)`, or let the first quantity posted to its books set it. Plain numbers on its lines are
then in that currency, and the currency fixes the unit of its subtotals. An amount in another currency is an error:

```{doctest}
>>> yen = b.Model("Shop", start="2027-01", periods=2, step=b.month)
>>> shop = yen.entity("Shop", standard=b.IFRS, currency=JPY)
>>> sales = shop.pl.revenue("Sales", 100)
>>> sorted(shop.pl.net_income.unit)
[('JPY', 1)]
>>> show(lambda: shop.pl.sga("Rent", 10 * USD))
Shop: 'Rent' is in USD, but the books are in JPY
```

An entity that never gets a currency, because every amount is a plain number, has no unit checks on its books. Declare the
currency whenever the entity has one.

Convert between currencies with an exchange-rate series. {py:meth}`boki.Model.fx` registers the closing, average and
opening rates of a pair, quoted as units of the second currency per unit of the first. The rate is a quantity in
`JPY/USD`, so multiplying a dollar series by it gives yen. Groups use the same rates to translate foreign subsidiaries
(see [Groups and consolidation](consolidation.md)).

```{doctest}
>>> pair = m.fx(USD, JPY, closing=150, average=[150, 152, 151], opening=149)
>>> revenue_yen = m.series("Revenue in yen", revenue * pair.average)
>>> m.render()[revenue_yen]
[1116000.0, 1021440.0, 1123440.0]
```

## Rates per period and per time

A plain number used as a rate is per period. `0.12` is 12% per period, whether the period is a month or a year. A rate per
time, written with a unit of time such as `0.12 / b.year`, is stored per month and integrated by the length of each
period. Twelve percent a year is 1% in a month and 3% in a quarter.

The line makers of an entity do this for you. This function books a loan of 1,000 and returns the interest in the second
and third periods:

```{doctest}
>>> def interest(step, rate):
...     model = b.Model("Loan", start="2027-01", periods=3, step=step)
...     co = model.entity("Bakery", standard=b.IFRS, currency=USD)
...     co.bs.opening(cash=2000 * USD)
...     loan = co.bs.loan("Term loan", draw={0: 1000 * USD}, rate=rate)
...     return [round(v, 2) for v in model.render()[loan.interest]][1:]
>>> interest(b.month, 0.12 / b.year)
[10.0, 10.0]
>>> interest(3 * b.month, 0.12 / b.year)
[30.0, 30.0]
>>> interest(b.month, 0.12)
[120.0, 120.0]
>>> interest(3 * b.month, 0.12)
[120.0, 120.0]
```

The same loan costs 10 a month or 30 a quarter at 12% a year. A plain `0.12` costs 120 in every period, which is 12% a
month in the monthly model. Write the rate the way the source states it. An annual rate in a monthly model is
`0.12 / b.year`, and a rate per month is `0.01` or `0.01 / b.month`.

Amounts work the same way. `100 * USD / b.month` on a revenue line books 100 in a monthly model and 300 in a quarterly
one, while a plain `100 * USD` books 100 in every period:

```{doctest}
>>> def fee(step, amount):
...     model = b.Model("Fees", start="2027-01", periods=2, step=step)
...     co = model.entity("A", standard=b.IFRS, currency=USD)
...     return model.render().value(co.pl.revenue("Fee", amount), "2027-01")
>>> fee(b.month, 100 * USD / b.month), fee(3 * b.month, 100 * USD / b.month), fee(3 * b.month, 100 * USD)
(100.0, 300.0, 100.0)
```

Outside the ledger, a rate per time is a series in `1/month`, and you integrate it yourself with `m.period_length`. The
functions of `boki.lib` that take a rate, such as {py:func}`boki.lib.npv` and {py:func}`boki.lib.compound`, want a
rate per period and say so:

```{doctest}
>>> annual = 0.12 / b.year
>>> [round(v, 4) for v in m.render()[annual * m.period_length]]
[0.01, 0.01, 0.01]
>>> flows = m.series("Flows", data={0: 100, 1: 100, 2: 100})
>>> show(lambda: b.lib.npv(flows, annual))
npv's rate must be dimensionless (a per-period rate), got 1/month; convert an annual rate with rate * m.period_length
>>> round(m.render()[b.lib.npv(flows, annual * m.period_length)], 2)
294.1
```

## Display units

Values are stored and computed in base units. A display unit only decides how a series is shown in tables and in Excel,
so arithmetic and unit checks never change. {py:meth}`boki.Result.display_unit` tells you which unit a series is shown
in. It is chosen in this order:

1. `display=` on the series or input, such as `display=kWh` or `display=1 / year` for a monthly rate. It must have the
   dimension of the series.
2. The unit a quantity was written in: `1000 * kW` shows in kW.
3. For a computed physical quantity (W, W×h and their per-month forms), the prefix that puts the row's largest value
   between 1 and 1,000. One unit is used for the whole row.

Money is never prefixed, and counts and plain numbers have no unit to prefix. In Excel, the style's `money=` setting
scales money (`money="$mm"` shows millions). In a table, a row with a display unit other than the base is labelled with it:

```{doctest}
>>> r = m.render()
>>> r.display_unit(capacity).name, r.display_unit(generation).name, r.display_unit(revenue)
('kW', 'MWh', None)
>>> print(r.table([capacity, generation, revenue]))
                  2027-01  2027-02  2027-03
Capacity (kW)       1,000    1,000    1,000
Generation (MWh)      149      134      149
Revenue             7,440    6,720    7,440
```

Choose a unit for one series with `display=`, or for one table with `unit=`:

```{doctest}
>>> output = m.series("Output", generation, display=kWh)
>>> churn = m.input("Churn", 0.01 / month, display=1 / year)
>>> print(m.render().table([output, churn]))
                2027-01  2027-02  2027-03
Output (kWh)    148,800  134,400  148,800
Churn (1/year)     0.12     0.12     0.12
>>> print(r.table([generation], unit=kWh))
            2027-01  2027-02  2027-03
Generation  148,800  134,400  148,800
```

The Excel output keeps the same rule. The Unit column shows the display unit, a power of 1000 above the base unit (kW,
MWh) changes only the number format, and a cell you edit on the Inputs sheet is in the displayed unit. See
[Excel output](excel.md).
