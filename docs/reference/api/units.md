# Units and quantities

Units catch mistakes at build time and keep amounts consistent. A number times a unit is a quantity (`3 * kW`), and
quantities of different dimensions do not add, subtract, or compare. Values are stored in base units: each currency
in itself, power in W, energy in W×h, and time in months, so `0.05 / b.year` is a rate per month that the ledger
integrates by the length of each period. Days and hours are separate dimensions, because their length in months
depends on the calendar: `month` and `day` never convert silently, and the days in a period come from
`m.period_end - m.date`.

Inside a render the same expressions give plain floats in base units, so `@m.series` functions work on ordinary
numbers.

## Making units

```{eval-rst}
.. autofunction:: boki.unit

.. autoclass:: boki.units.Unit
   :special-members: __mul__, __rmul__, __truediv__, __rtruediv__, __pow__

.. autoclass:: boki.units.Quantity
   :special-members: __add__, __radd__, __sub__, __rsub__, __mul__, __rmul__, __truediv__, __rtruediv__, __neg__, __abs__, __pow__, __lt__, __le__, __gt__, __ge__

.. autoexception:: boki.UnitError
```

## Unit constants

`boki.units` defines these units. `day`, `h`, `month`, `quarter`, and `year` are also available as `b.day`, `b.h`,
`b.month`, `b.quarter`, and `b.year`. The scale is the size of one unit in the base unit of its dimension. Each
currency is a dimension of its own: `USD` and `JPY` do not convert, so use an exchange-rate series
(`Model.fx`) to move between them. Define other units with `boki.unit`.

| Name | Dimension | Scale | Meaning |
|---|---|---|---|
| `USD` | USD | 1 | US dollar |
| `JPY` | JPY | 1 | Japanese yen |
| `EUR` | EUR | 1 | euro |
| `GBP` | GBP | 1 | pound sterling |
| `CNY` | CNY | 1 | Chinese yuan |
| `W` | W | 1 | watt, the base unit of power |
| `kW` | W | 1,000 | kilowatt |
| `MW` | W | 1,000,000 | megawatt |
| `Wh` | W×h | 1 | watt-hour, the base unit of energy |
| `kWh` | W×h | 1,000 | kilowatt-hour |
| `MWh` | W×h | 1,000,000 | megawatt-hour |
| `day` | day | 1 | a day, a dimension of its own |
| `h` | h | 1 | an hour, a dimension of its own |
| `month` | month | 1 | a month, the base unit of time |
| `quarter` | month | 3 | three months |
| `year` | month | 12 | twelve months |
