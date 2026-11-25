# Excel output

`r.to_excel(path)` writes a workbook in which the model's numbers are live formulas, so changing an input in Excel
recalculates the model. This page covers what the workbook contains, how series become formulas and which cannot, why the
export guards a few cells against circular references that boki does not have, how to change the look with a style, a money
scale and display units, how to place rows on sheets of your own, and how to write an entity's ledger as Beancount text.

## Writing a workbook

Render the model, then call {py:meth}`boki.Result.to_excel`. It writes an `.xlsx` file, replacing one that is there, and
returns a {py:class}`boki.excel.Report` that counts what was written. The examples write to a temporary folder:

```{doctest}
>>> import pathlib, tempfile
>>> import boki as b
>>> from boki.lib import compound
>>> from boki.units import USD, year
>>> m = b.Model("Widget Co", start="2027-01", periods=5, step=year)
>>> co = m.entity("Widget Co", standard=b.USGAAP, currency=USD)
>>> co.bs.opening(cash=20e6 * USD)
>>> growth = m.input("Revenue growth", 0.25)
>>> sales = co.pl.revenue("Product sales", compound(40e6 * USD, growth))
>>> cost_of_sales = co.pl.cogs("Cost of sales", 0.45 * sales)
>>> opex = co.pl.sga("Operating expenses", 6e6 * USD + 0.15 * sales)
>>> receivable = co.bs.receivable("Accounts receivable", target=0.12 * sales)
>>> plant = co.bs.fixed_asset("Plant", 30e6 * USD, at=0, life=10 * year)
>>> loan = co.bs.loan("Term loan", draw={0: 25e6 * USD}, rate=0.07, repay=5e6 * USD)
>>> tax = co.pl.income_tax("Income taxes", rate=0.21, base=co.pl.pretax_income)
>>> solvent = m.check(co.bs.cash >= 0, "never runs out of cash")
>>> r = m.render()
>>> folder = tempfile.TemporaryDirectory()
>>> path = pathlib.Path(folder.name) / "widget.xlsx"
>>> report = r.to_excel(path, money="$mm")
>>> print(report)
155 formula cells, 10 data cells, 0 value cells
```

To look inside the file without Excel, this page uses a few lines of standard-library code. You do not need them in your
own work; open the workbook in Excel instead.

```{doctest}
>>> import re, zipfile
>>> from xml.etree import ElementTree
>>> NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
>>> def read_workbook(path):
...     """Return {sheet name: {row label: {column: text}}}, where a formula's text starts with =."""
...     book = zipfile.ZipFile(path)
...     names = [s.get("name") for s in ElementTree.fromstring(book.read("xl/workbook.xml")).iter(NS + "sheet")]
...     def text(cell):
...         formula, value = cell.find(NS + "f"), cell.find(NS + "v")
...         words = "".join(t.text or "" for t in cell.iter(NS + "t"))
...         return "=" + formula.text if formula is not None else words or (value.text if value is not None else "")
...     sheets = {}
...     for number, name in enumerate(names, start=1):
...         rows = {}
...         for row in ElementTree.fromstring(book.read(f"xl/worksheets/sheet{number}.xml")).iter(NS + "row"):
...             cells = {re.match("[A-Z]+", c.get("r")).group(): text(c) for c in row.iter(NS + "c")}
...             rows[cells.get("A", "")] = cells
...         sheets[name] = rows
...     return sheets
>>> book = read_workbook(path)
>>> list(book)
['Inputs', 'Widget Co IS', 'Widget Co BS', 'Widget Co CF', 'Widget Co Schedules', 'Checks', 'Model']
```

### What each sheet holds

| Sheet | What you see |
|---|---|
| `Inputs` | Every `m.input` with its unit and value, in blue. A table such as `b.by_year` has one value for each period. The sheet exists when the model has inputs. |
| `<entity> IS`, `BS`, `CF` | The income statement, balance sheet and cash-flow statement of each entity and group, in the line order and names of its standard. Every number links to the Model sheet. |
| `<entity> Schedules` | Roll-forwards of the entity's loans, fixed assets and working-capital lines: opening balance, each movement, closing balance. |
| `Checks` | The checks, one row each, `OK` or `FAIL`: for every entity that assets equal liabilities plus equity and that cash flow equals the change in cash, and each `m.check` you declared. |
| `Model` | One row per series and one column per period, all formulas. Helper rows are folded. |

The statements keep the structure of the layout: expenses in parentheses under the default style, subtotals as sums of the
lines above, percentage rows for growth, margin and the effective tax rate, and a balance check on the balance sheet. The
statement sheets contain formulas that refer to the Model sheet, and the Model sheet holds the arithmetic:

```{doctest}
>>> income = book["Widget Co IS"]
>>> list(income)[:2]
['Widget Co – Income Statement', '($ in millions)']
>>> income["Cost of revenue"]["C"]
'=-Model!C6/1000000'
>>> book["Model"]["Product sales"]["D"]
'=C4*(1+Inputs!$C$3)'
>>> [book["Checks"][row]["C"] for row in ("Widget Co: assets = liabilities + equity", "never runs out of cash")]
['=Model!C41', '=Model!C43']
```

The file stores formulas without results and asks Excel to recalculate when it opens, so open it in Excel or LibreOffice;
a viewer that does not calculate shows empty cells. boki's own tests recalculate exported workbooks with an independent
engine and compare every formula cell with the model.

## How series become formulas

boki series are expression trees, so each one is written as a formula that refers to the cells it reads. Named series and
lines are referenced by their rows, and an unnamed expression is written into the formula that uses it. The common
translations:

| In boki | In the workbook |
|---|---|
| `x.lag(k, fill=)` | The cell `k` columns to the left, or `fill` before the first period |
| `x.where(cond, y)`, `b.min`, `b.max` | `IF`, `MIN`, `MAX`. A condition on the calendar alone is settled first, and only the branch taken is written |
| A series defined on its own past, `compound`, `cumsum`, loan and fixed-asset balances, loss carryforwards | A reference to the previous column of the same row |
| `x.sum()`, `x.mean()`, `npv`, `irr` | `SUM`, `AVERAGE`, `NPV`, `IRR` over the row |
| `m.date`, `.year`, `.month`, date plus months | `YEAR`, `MONTH`, `EDATE` on the period-start cells |
| `b.by_year` or `b.step` in an `m.input` | Typed values on the Inputs sheet, in blue |
| `m.series(data=)`, a dict of amounts on a line | Typed values on the Model sheet, in blue |

Here are some of them, in a small extension of the model above:

```{doctest}
>>> last_year = m.series("Sales last year", sales.lag(1, fill=0 * USD))
>>> big_years = m.series("Sales above 60m", sales.where(sales > 60e6 * USD, 0 * USD))
>>> to_date = m.series("Sales to date", sales.cumsum())
>>> total_sales = m.series("Total sales", sales.sum())
>>> r = m.render()
>>> report = r.to_excel(path, money="$mm")
>>> model = read_workbook(path)["Model"]
>>> [model[label]["D"] for label in ("Sales last year", "Sales above 60m", "Sales to date")]
['=C10', '=IF((D10>60000000),D10,0)', '=SUM($C10:D10)']
>>> model["Total sales"]["C"]
'=SUM($C$10:$G$10)'
```

(Prefer `m.input` for a number that is an assumption: it gets a row on the Inputs sheet, so you can change it in Excel.)

### What cannot be a formula

Some series have no Excel formula: a Python function used as a series (`@m.series`), the value found by `m.solve`, a period
chosen by another series, and a reduction with no row to refer to. {py:meth}`boki.Result.to_excel` writes the value boki
computed instead, shades the cell and adds a note with the reason. Such a cell does not follow a changed input in the
workbook, so export again after changing inputs that feed it. The report counts them, and `Report.reasons` says why:

```{doctest}
>>> solved = b.Model("Solved", start="2027-01", periods=3, step=year)
>>> size = solved.unknown("Size", init=1)
>>> demand = solved.input("Demand", 10)
>>> solved.solve(size, size == b.min(demand * 2, 15))
>>> @solved.series
... def seasonal(t):
...     return 1.0 + 0.1 * (t % 2)
>>> total = solved.series("Total", size * seasonal)
>>> report = solved.render().to_excel(path)
>>> print(report)
3 formula cells, 0 data cells, 4 value cells (Fn ×3, Unknown ×1)
>>> report.reasons
{'Unknown': 1, 'Fn': 3}
```

Each reason is the message of an {py:exc}`boki.excel.Untranslatable` exception, which the export catches and does not show
you. Write a series so that Excel can compute it where you can: define a recurrence with `x.define(x.lag(1, fill=...) *
...)` instead of a Python function.

A table of numbers that has no name (`b.by_year` or `b.step` used inside an expression) cannot be a row either, because a row
needs a name.
{py:meth}`boki.Result.to_excel` raises {py:exc}`boki.excel.UnnamedAssumption`, and the fix is to give the table a name with
`m.input`:

```{doctest}
>>> def cost_plan(named):
...     plan = b.Model("Plan", start="2027-01", periods=3, step=year)
...     firm = plan.entity("Firm", standard=b.IFRS, currency=USD)
...     firm.bs.opening(cash=1000 * USD)
...     ratio = b.by_year({0: 0.4, 1: 0.38, 2: 0.36})
...     if named:
...         ratio = plan.input("Cost ratio", ratio)
...     revenue = firm.pl.revenue("Sales", plan.input("Sales plan", b.by_year({0: 100, 1: 120, 2: 150}) * USD))
...     cost = firm.pl.cogs("Cost", ratio * revenue)
...     return plan.render()
>>> from boki.excel import UnnamedAssumption
>>> try:
...     cost_plan(named=False).to_excel(path)
... except UnnamedAssumption as error:
...     print(str(error).splitlines()[0])
1 assumption tables have no name; a table needs a row, and a row a name. Name each with m.input("…", …):
>>> print(cost_plan(named=True).to_excel(path))
51 formula cells, 0 data cells, 0 value cells
```

A single number such as `0.45 * sales` stays inline and needs no name.

## Circular references that boki does not have

boki evaluates a cell from the cells it reads in that period: only the branch of a `where` that is taken, only the one
period that `x[k]` or `x.lag(k)` picks when `k` is an input. Excel's dependency graph counts every reference in a formula,
both branches of an `IF` and every cell of the row an `INDEX` picks from. A model can therefore be acyclic in boki and
circular in Excel. A sculpted loan is the usual case: the debt is sized on the cash flow of the operating years only, and
Excel's `IF` still refers to the construction years, whose cash flow includes the debt.

The export never writes a workbook with such a loop. It writes each Model cell once, recording what the formula refers to
and what boki does not read in that period, and where those unread references close a loop in the cell graph it replaces
the fewest of them with `NA()`. The guarded cells are shaded with a note, keep their live condition and the formula for what
boki reads, and recalculate to boki's value for the exported inputs. If you change an input in Excel so that a guarded cell
would read the part that was cut off, the cell shows `#N/A`, and so do the cells that use it, rather than a wrong number.
Export again from boki for those inputs.

The export warns with {py:class}`boki.excel.CircularReferenceWarning` and counts the guarded cells in `Report.guarded`:

```{doctest}
>>> import warnings
>>> from boki.units import USD, year
>>> toll = b.Model("Toll road", start="2020", periods=8, step=year)
>>> calendar = toll.date.year
>>> start = toll.input("construction start", 2020)
>>> opening = toll.input("opening year", 2022)
>>> building = (calendar >= start) & (calendar < opening)
>>> operating = calendar >= opening
>>> debt_period = operating & (calendar < opening + 4)
>>> rate = toll.input("debt rate", 0.05)
>>> capex = toll.series("capex", (60 * USD).where(building, 0 * USD))
>>> revenue = toll.series("net revenue", (40 * USD).where(operating, 0 * USD))
>>> commitment = toll.series("debt commitment")
>>> fee = toll.series("arrangement fee", (0.02 * commitment).where(calendar == start, 0 * USD))
>>> drawdown = toll.series("drawdown", (0.7 * (capex + fee)).where(building, 0 * USD))
>>> equity = toll.series("equity", (0.3 * (capex + fee)).where(building, 0 * USD))
>>> cfads = toll.series("CFADS", revenue - capex + equity + drawdown - fee)
>>> factor = toll.series("debt discount factor", (1 + rate) ** -(calendar - opening + 1))
>>> pv = toll.series("NPV of CFADS", (cfads * factor).where(debt_period, 0 * USD).sum())
>>> sized = commitment.define(pv / 1.3)
>>> with warnings.catch_warnings(record=True) as caught:
...     warnings.simplefilter("always")
...     report = toll.render().to_excel(path)
>>> [warning.category.__name__ for warning in caught]
['CircularReferenceWarning']
>>> report.guarded
8
```

A loop that is left after every unread reference is guarded is boki's own, and boki reports it as a `CycleError` when the
cell is evaluated. Cycles you mean, such as debt sized on its own interest, are solved with `m.solve`; see
[Models, time and series](models.md).

## Styles

A {py:class}`boki.Style` decides how the workbook looks and never changes what the model computes. Choose one with
`style=`; the default is `b.styles.banker`.

| Preset | Look |
|---|---|
| `banker` (the default) | Expenses negative in parentheses, blue inputs, black formulas and green links, growth and margin rows, a dark title band, shaded totals, Arial |
| `sec` | A filing: Times New Roman, no colors or ratio rows, dollar signs on the first line and the totals, plain year headings under a "Year Ended" line, "Consolidated" statement titles |
| `japanese` | Triangle marks for negatives, expenses shown positive and subtracted in subtotals, no ratio rows, and the sheet names and titles of Japanese statements |
| `plain` | Minus signs, no styled statements (plain `PL`, `BS` and `CF` sheets that link to the Model sheet), gridlines on, the model's own period labels, helper rows shown |

```{doctest}
>>> for preset in ("banker", "sec", "japanese", "plain"):
...     report = r.to_excel(path, style=getattr(b.styles, preset))
...     book = read_workbook(path)
...     sheet = next(name for name in book if name.startswith("Widget Co"))
...     print(preset, sheet, "|", next(iter(book[sheet])))
banker Widget Co IS | Widget Co – Income Statement
sec Widget Co IS | WIDGET CO
japanese Widget Co PL | Widget Co Income Statement
plain Widget Co PL | Widget Co PL
```

A style is a frozen value. Change settings by calling it, or with `replace`, and the original is untouched. The same
settings can be passed straight to `to_excel` as keyword arguments, which apply to that call:

```{doctest}
>>> house = b.styles.banker(money="$000", font="Calibri", negatives="minus")
>>> house.money, house.font, house.negatives, b.styles.banker.negatives
('$000', 'Calibri', 'minus', 'parens')
>>> report = r.to_excel(path, style=house, band="006400")
>>> list(read_workbook(path)["Widget Co IS"])[:2]
['Widget Co – Income Statement', '($ in thousands)']
>>> b.styles.banker(colour=False)
Traceback (most recent call last):
...
TypeError: unknown style setting(s): colour
```

The settings you are likely to want are `money`, `units`, `hide`, `helpers`, `columns` and `periods`; the rest
(`negatives`, `zero`, `expenses`, `colors`, `ratios`, `gridlines`, `font`, `decimals`, `band`, `shade`, `dollars`, `titles`,
`header`, `language`) are on the {py:class}`boki.Style` page. A mistake in a setting fails when the style is made, not when
the file is written.

### Money scale and display units

Values are in base units: a currency in itself, power in W, energy in W×h, time in months. `money=` sets one scale for the
whole workbook: `"$mm"`, `"$000"`, `"millions JPY"`, `"thousands JPY"`, `"hundred millions JPY"` or a number such as
`1000`. The statement sheets divide by the scale and caption it, and the Model sheet keeps base units and shows the scale
through number formats, so every formula still recalculates to the model's value. The currency mark is ignored, because the
books have one currency: the caption names the entity's own.

```{doctest}
>>> for scale in ("$000", "$mm"):
...     report = r.to_excel(path, money=scale)
...     income = read_workbook(path)["Widget Co IS"]
...     print(scale, list(income)[1], income["Revenue"]["C"])
$000 ($ in thousands) =Model!C10/1000
$mm ($ in millions) =Model!C10/1000000
>>> b.styles.banker(money="lots")
Traceback (most recent call last):
...
ValueError: money='lots': use a scale such as '$mm', '$000', 'millions JPY', 'thousands JPY' or a number
```

`units={series: unit}` shows a series that is not money in a unit of the same dimension, such as kWh for energy; the
conversion is part of the formulas. It works for inputs too.

```{doctest}
>>> from boki.units import MWh, kWh
>>> energy = b.Model("Energy", start="2027-01", periods=3, step=year)
>>> generation = energy.input("Generation", b.by_year({0: 400 * MWh, 1: 500 * MWh, 2: 300 * MWh}))
>>> tariff = energy.input("Tariff", 80 * USD / MWh)
>>> turnover = energy.series("Turnover", generation / MWh * tariff * MWh)
>>> result = energy.render()
>>> report = result.to_excel(path)
>>> read_workbook(path)["Inputs"]["Generation"]["B"]
'W×h'
>>> report = result.to_excel(path, units={generation: kWh})
>>> read_workbook(path)["Inputs"]["Generation"]["B"], read_workbook(path)["Inputs"]["Generation"]["C"]
('kWh', '400000')
```

### Columns and helper rows

For a model with periods shorter than a year, the statements sum them into fiscal years (`columns="fiscal"`, the default),
using the entity's {py:func}`boki.fiscal` calendar. `columns="periods"` keeps a column for each model period.
`periods="fy"`, `"year"` or `"raw"` chooses how the columns are headed.

On the Model sheet, rows that exist only to compute other rows are helper rows. They are grouped and folded under
`helpers="group"`, and open with `helpers="show"`. `hide=[series, ...]` folds named series the same way.

## Placing rows on sheets of your own

By default every row is on the Model sheet. {py:func}`boki.sheet`, {py:func}`boki.section`, {py:func}`boki.row` and
{py:func}`boki.link` place chosen series where you want them, in reading order, and the rest of the model stays where boki
puts it. `b.row(series, label=, sign=, scale=)` shows `value * sign / scale`, such as a cost as a negative number in
thousands; it changes only how the row shows the value, never the value that other formulas read. A series can be placed
once, and `b.link(row)` shows a placed row again on another sheet, with the same sign and scale:

```{doctest}
>>> cafe = b.Model("Cafe", start="2027-01", periods=3, step=year)
>>> customers = cafe.series("Customers")
>>> growing = customers.define(customers.lag(1, fill=100) * 1.1)
>>> price = cafe.input("Price", 20 * USD)
>>> takings = cafe.series("Takings", customers * price)
>>> costs = cafe.series("Costs", takings * 0.6)
>>> takings_row = b.row(takings)
>>> costs_row = b.row(costs, "Operating costs", sign=-1, scale=1000)
>>> sales_sheet = b.sheet("Sales", [b.section("Drivers", [customers, price]), b.section("Results", [takings_row, costs_row])])
>>> summary_sheet = b.sheet("Summary", [b.link(takings_row), b.link(costs_row, "Costs (thousands)")])
>>> report = cafe.render().to_excel(path, sheets=[sales_sheet, summary_sheet])
>>> placed = read_workbook(path)
>>> list(placed)
['Inputs', 'Sales', 'Summary', 'Model']
>>> placed["Sales"]["Operating costs"]["D"]
'=-((D10*0.6))/1000'
>>> placed["Summary"]["Costs (thousands)"]["D"]
'=Sales!D11'
```

The names `Inputs`, `Model` and `Checks` belong to the workbook. An input placed on a sheet is written as a link to its row
on the Inputs sheet.

### Banker-grade workbooks: actuals, panels, sensitivities and live scenarios

For investment-banking and presentation-ready workbooks, you can combine custom sheet placement with:

- **Historical actuals and forecast divider**: set `actual_until=` on `b.Model(...)` and pass `actuals=` on line makers (or `co.load_actuals(...)`). Actual columns are formatted as blue inputs with `FY2024A` / `FY2025E` headings and a vertical border between actuals and forecast.
- **Proof-carrying formula rewrites**: pass `formula=` to {py:func}`boki.row` or group summary lines with {py:func}`boki.block` (`verify="perturb"`) to emit concise banker-style Excel formulas while proving equivalence against boki across scenarios and perturbations.
- **2D summary panels and live sensitivity tables**: use {py:func}`boki.panel` for non-time-series tables (Sources & Uses, Exit Bridge, Valuation Summary) and {py:func}`boki.sensitivity` for 2D sensitivity matrices whose row and column headers are live cells (`$A<row>`, `<col>$<hdr>`) that recalculate directly in Excel.
- **Live scenario switcher and no `Model` sheet**: pass `scenarios=["Base", "Bull", "Bear"]` to emit an `Inputs!$C$3` case selector backed by `=INDEX(...)`, and `omit_unused_model=True` to omit the `Model` sheet when every needed line is placed on presentation sheets.

See `examples/ib_3statement`, `examples/ib_lbo` and `examples/ib_dcf` in the repository for complete end-to-end workbooks.

## Beancount

{py:func}`boki.export.to_beancount` writes an entity's ledger as text for plain-text accounting tools such as Beancount: an
`open` line for every account, one dated transaction for the opening balances, and one for each posting of each period,
dated the last day of the period. Pass `group.books` for a group's consolidated books. Amounts have two decimals, and
account names are ASCII (`Assets:Cash:Cash`), with the original name kept as metadata.

```{doctest}
>>> from boki.export import to_beancount
>>> text = to_beancount(r, co)
>>> print("\n".join(text.splitlines()[:5]))
option "title" "Widget Co"
option "operating_currency" "USD"
<BLANKLINE>
2026-12-31 open Assets:Cash:Cash USD
  boki-name: "Cash"
>>> [line for line in text.splitlines() if line.startswith("2027-12-31 * ")][:3]
['2027-12-31 * "Product sales"', '2027-12-31 * "Cost of sales"', '2027-12-31 * "Operating expenses"']
>>> folder.cleanup()
```

Beancount derives retained earnings from the income and expense accounts, so profit is not closed into the retained earnings
account in the export.

## What the workbook does not have

The workbook has no cover sheet yet. A cell is a value rather than a formula only for the reasons above, and each one is
counted in the report.
