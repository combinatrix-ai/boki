# boki

boki is a Python library for financial models. You write the business as code (revenue, costs, payment terms, assets,
loans), and boki writes the journal entries, depreciation and interest, then builds the income statement, balance sheet
and cash-flow statement in the line order and names of your accounting standard: US GAAP, IFRS or J-GAAP. The model
stays in code, where it can be diffed, reviewed and tested, and Excel is its output: a workbook whose statements link to
a Model sheet of live formulas. Units, a double-entry ledger and checks stop mistakes, such as adding dollars to
kilowatts or a balance sheet that does not balance, before they reach a number.

## Installation

boki needs Python 3.11 or later. Core boki has no required dependencies; install the `excel` extra to write `.xlsx` workbooks with `openpyxl`:

```sh
uv add "boki[excel]"   # or: pip install "boki[excel]"
```

For modeling in Python without Excel export, `uv add boki` (or `pip install boki`) is enough.

## Quickstart

A five-year plan for a company that sells a product, collects from customers a little late, buys a plant and borrows to
pay for it. A model has a timeline, and an entity is a company with its own books under an accounting standard. The
growth rate is an input, so it can change without editing the model:

```{doctest}
>>> import boki as b
>>> from boki.lib import compound
>>> from boki.units import USD, year
>>> m = b.Model("Widget Co", start="2027-01", periods=5, step=year)
>>> co = m.entity("Widget Co", standard=b.USGAAP, currency=USD)
>>> co.bs.opening(cash=20e6 * USD)
>>> growth = m.input("Revenue growth", 0.25)
```

You describe the business with lines. A line says what happens, and boki posts the double entries behind it:

```{doctest}
>>> sales = co.pl.revenue("Product sales", compound(40e6 * USD, growth))
>>> cogs = co.pl.cogs("Cost of sales", 0.45 * sales)
>>> opex = co.pl.sga("Operating expenses", 6e6 * USD + 0.15 * sales)
>>> receivable = co.bs.receivable("Accounts receivable", target=0.12 * sales)
>>> plant = co.bs.fixed_asset("Plant", 30e6 * USD, at=0, life=10 * year)
>>> loan = co.bs.loan("Term loan", draw={0: 25e6 * USD}, rate=0.07, repay=5e6 * USD)
>>> tax = co.pl.income_tax("Income taxes", rate=0.21, base=co.pl.pretax_income)
```

Nothing is computed yet. `m.render()` evaluates the model, checks the books, and returns a result to read values and
statements from. You never wrote a journal entry, a depreciation schedule or a cash-flow statement, but they exist:

```{doctest}
>>> r = m.render()
>>> r[sales]
[40000000.0, 50000000.0, 62500000.0, 78125000.0, 97656250.0]
>>> r[co.pl.net_income]
[7900000.0, 7307500.0, 11534000.0, 16748000.0, 23196375.0]
>>> r.value(co.bs.cash, "2031")
61967125.0
>>> [(check.name, check.passed) for check in r.checks]
[('Widget Co: cash is not negative', True)]
>>> print(r.pl(co, detail=False))  # doctest: +NORMALIZE_WHITESPACE
PL Widget Co                   2027        2028        2029        2030        2031
Revenue                  40,000,000  50,000,000  62,500,000  78,125,000  97,656,250
Cost of revenue          18,000,000  22,500,000  28,125,000  35,156,250  43,945,312
Gross profit             22,000,000  27,500,000  34,375,000  42,968,750  53,710,938
Operating expenses       12,000,000  16,500,000  18,375,000  20,718,750  23,648,438
Operating income (EBIT)  10,000,000  11,000,000  16,000,000  22,250,000  30,062,500
Interest expense                  0   1,750,000   1,400,000   1,050,000     700,000
Pre-tax income           10,000,000   9,250,000  14,600,000  21,200,000  29,362,500
Income taxes              2,100,000   1,942,500   3,066,000   4,452,000   6,166,125
Net income                7,900,000   7,307,500  11,534,000  16,748,000  23,196,375
```

`r.bs(co)` and `r.cf(co)` draw the balance sheet and the cash-flow statement the same way, and the render has verified that
the balance sheet balances and that the cash flow matches the change in cash.

To get the workbook, call `r.to_excel("widget.xlsx", money="$mm")`. Here it goes to a temporary folder, and the example
lists what it wrote. The statement sheets link their lines to the Model sheet, which has one row for each series and one
column for each period. No cell had to be written as a value:

```{doctest}
>>> import os
>>> import tempfile
>>> import openpyxl
>>> with tempfile.TemporaryDirectory() as folder:
...     path = os.path.join(folder, "widget.xlsx")
...     report = r.to_excel(path, money="$mm")
...     sheets = openpyxl.load_workbook(path).sheetnames
>>> sheets
['Inputs', 'Widget Co IS', 'Widget Co BS', 'Widget Co CF', 'Widget Co Schedules', 'Checks', 'Model']
>>> report.formulas > 0, report.values
(True, 0)
```

## Where to go next

The user guide explains the ideas in the order you meet them:

- {doc}`guide/models` covers the timeline, series, inputs and scenarios, and solving.
- {doc}`guide/units` covers units, currencies, and the difference between a rate per period and a rate per time.
- {doc}`guide/statements` covers entities, the lines that make the statements, and the ledger.
- {doc}`guide/consolidation` covers groups of entities.
- {doc}`guide/checks` covers checks in the model and tests against known numbers.
- {doc}`guide/excel` covers the Excel output.

The API reference documents every public name, starting with {py:class}`~boki.Model`, {py:class}`~boki.Series` and
{py:class}`~boki.Result`. {doc}`reference/api/makers/index` lists the lines you can add to each statement.

```{toctree}
:maxdepth: 2
:caption: User guide

guide/index
```

```{toctree}
:maxdepth: 2
:caption: API reference

reference/api/model
reference/api/series
reference/api/line-item
reference/api/result
reference/api/testing
reference/api/shapes
reference/api/units
reference/api/lib
reference/api/fx
reference/api/line-maker
reference/api/makers/index
reference/api/entity
reference/api/group
reference/api/layouts
reference/api/output
```
