# Layouts

A layout says which kinds of lines an entity's statements have and in what order. `Model.entity(..., layout=...)` builds
the entity's `co.pl` and `co.bs` from it. Without `layout=`, an entity uses the general layout of its standard:
`b.IFRS.general`, `b.USGAAP.general` or `b.JGAAP.general`. `b.layouts` is the module that holds the custom-layout API
(`Layout`, `Kind`, `Stage`, `Standard`) and the presets (`IFRS`, `USGAAP`, `JGAAP`, `bank`).

## Built-in standards and layouts

```{eval-rst}
.. autodata:: boki.layouts.IFRS
   :no-value:

.. autodata:: boki.layouts.USGAAP
   :no-value:

.. autodata:: boki.layouts.JGAAP
   :no-value:

.. autodata:: boki.layouts.bank
   :no-value:
```

## Defining a custom layout

A layout is data: a tuple of `Kind` and `Stage` items for the income statement, a tuple of balance-sheet `Kind` items, and
the names of the two income-statement kinds that automatic entries use.

```{doctest}
>>> import boki as b
>>> from boki.layouts import Kind, Layout, Stage
>>> royalty = Kind("royalty", "income", cf="pl", mechanism="pl")
>>> cost = Kind("cost", "expense", cf="pl", mechanism="pl")
>>> layout = Layout(
...     "Licensing",
...     pl=(royalty, cost, Stage("net_income", lambda pl: pl.royalty.total - pl.cost.total)),
...     bs=(Kind("escrow", "asset", "current"),
...         Kind("note", "liability", "noncurrent", "financing", mechanism="loan")),
...     interest_kind="cost",
...     depreciation_kind="cost")
>>> m = b.Model("Licensing", start="2027-01", periods=2, step=b.year)
>>> co = m.entity("A", standard=b.IFRS, layout=layout)
>>> fee = co.pl.royalty("Fee", 100)
>>> m.render().value(co.net_income, "2027")
100
```

A layout is not checked when it is made. `Model.entity` builds the statements from it and raises when it cannot, and some
mistakes surface only when a line is booked. The rules below are what the code enforces.

### Mechanisms

A balance-sheet kind has a `mechanism` that decides what a call of its maker books and which template documents it. The
valid mechanisms are:

| Mechanism | What a call books | Template page |
|---|---|---|
| `"line"` | A balance, moved against cash or held at a target | {doc}`makers/template-line` |
| `"fixed_asset"` | A depreciating asset bought with cash | {doc}`makers/template-fixed_asset` |
| `"loan"` | Borrowing with repayment and interest | {doc}`makers/template-loan` |
| `"construction"` | Construction in progress | {doc}`makers/template-construction` |
| `"capital"` | Share capital and other equity | {doc}`makers/template-capital` |
| `"dividend"` | A dividend from retained earnings | {doc}`makers/template-dividend` |

Any other mechanism on a balance-sheet kind makes `Model.entity` raise `KeyError` when it builds the balance sheet. The
income statement does not read the mechanism of a PL kind: `"pl"` is the convention. Two things about PL kinds come from
other fields. A PL kind whose side is `"income"` is an income kind, and any other side is treated as an expense. A PL kind
named `income_tax` gets the income tax maker, which takes `rate=` and `base=`; the other PL kinds share one maker
({doc}`makers/template-pl_line`, {doc}`makers/template-income_tax`).

```{doctest}
>>> bad = Layout(
...     "Bad mechanism",
...     pl=(royalty, cost, Stage("net_income", lambda pl: pl.royalty.total - pl.cost.total)),
...     bs=(Kind("pool", "asset", "current", mechanism="pool"),),
...     interest_kind="cost", depreciation_kind="cost")
>>> try:
...     b.Model("Bad", start="2027-01", periods=1, step=b.year).entity("A", layout=bad)
... except KeyError as error:
...     print("KeyError", error)
KeyError 'pool'
```

### Required kinds and stages

- **`net_income`.** Every layout needs a stage named `net_income`, because the entity reads `co.pl.net_income` when it is
  created. Without it, `Model.entity` raises `AttributeError`.
- **`interest_kind` and `depreciation_kind`.** They name the PL kinds that take loan interest and depreciation. They are not
  looked up when the layout is made. A `KeyError` is raised when a line of a `loan` kind is booked and `interest_kind` is not
  a PL kind of the layout, and when a line of a `fixed_asset` or `construction` kind is booked and `depreciation_kind` is
  not.
- **`income_tax`.** `bs.deferred_tax` books its expense into a PL kind named `income_tax`, and raises `AttributeError` when
  the layout has none.
- **A non-revenue income kind.** `oci_release` of a recycled OCI component books into the first of `other_income`,
  `non_operating_income`, `non_interest_income`, `special_gain` and `finance_income` that the layout has, and raises
  `ValueError` when it has none.
- **Optional kinds.** Cash, retained earnings and the shared accounts that `settle=`, `recognize=` and `vat=` open need no
  kind. Kinds named `deferred_tax_asset`, `deferred_tax_liability` and `oci` are filled when the layout has them.

```{doctest}
>>> def build(layout, body=None):
...     m = b.Model("Rules", start="2027-01", periods=1, step=b.year)
...     try:
...         co = m.entity("A", standard=b.IFRS, currency=b.units.JPY, layout=layout)
...         if body is not None:
...             body(co)
...     except (AttributeError, KeyError, ValueError) as error:
...         return type(error).__name__
...     return "ok"
>>> no_net_income = Layout("No net income", pl=(royalty, cost), bs=(), interest_kind="cost", depreciation_kind="cost")
>>> build(no_net_income)
'AttributeError'
>>> loans = Layout(
...     "Loans",
...     pl=(royalty, cost, Stage("net_income", lambda pl: pl.royalty.total - pl.cost.total)),
...     bs=(Kind("note", "liability", "noncurrent", "financing", mechanism="loan"),),
...     interest_kind="missing", depreciation_kind="cost")
>>> build(loans)
'ok'
>>> build(loans, lambda co: co.bs.note("Note", draw={0: 100 * b.units.JPY}))
'KeyError'
>>> build(layout, lambda co: co.bs.deferred_tax("Difference", 100, rate=0.3))
'AttributeError'
```

### Stage dependencies

`Model.entity` builds every kind first and then the stages in the order of the layout. A stage's formula receives `co.pl`
and may read the `total` of any kind of the layout, wherever the kind is listed, and any stage listed before it. A
formula that reads a stage listed after it, or a name the layout does not have, raises `AttributeError`. The formula may
be called again when the first amount fixes the entity's currency, so it should depend on `pl` only.

```{doctest}
>>> def stages(*items):
...     return Layout("Stages", pl=(royalty, cost, *items), bs=(), interest_kind="cost", depreciation_kind="cost")
>>> net = Stage("net_income", lambda pl: pl.profit)
>>> profit = Stage("profit", lambda pl: pl.royalty.total - pl.cost.total)
>>> build(stages(profit, net))
'ok'
>>> build(stages(net, profit))
'AttributeError'
```

### Names

Kind and stage names become attributes of `co.pl` and `co.bs`, and nothing checks them against the names the statement
already uses. Choose names that are unique and that the statement does not use:

- In `co.pl`, kinds are set first and stages after them, so a stage with the name of a kind replaces the kind's maker. A
  repeated name keeps the last one.
- In `co.bs`, `cash` is set first, then the kinds, then `equity`, `total_assets`, `total_liabilities` and `total_equity`. A
  kind named `cash` replaces the cash balance in `co.bs.cash`. A kind named `equity` or `total_*` is replaced by the total.
  A kind named like a method, `opening`, `asset`, `liability`, `deferred_tax` or `sell`, shadows that method on that
  balance sheet, so `co.bs.opening(cash=...)` would call the maker instead.
- `boki.layouts` is the module, not a class: `b.layouts.bank` is the bank layout, and `b.layouts.Layout` is the layout
  class.

```{doctest}
>>> clash = Layout("Clash", pl=(royalty, cost, Stage("net_income", lambda pl: pl.royalty.total - pl.cost.total)),
...                bs=(Kind("opening", "asset", "current"), Kind("equity", "equity", cf="financing")),
...                interest_kind="cost", depreciation_kind="cost")
>>> m = b.Model("Clash", start="2027-01", periods=1, step=b.year)
>>> co = m.entity("A", layout=clash)
>>> type(co.bs.opening).__name__, type(co.bs.equity).__name__
('LineMaker', '_Equity')
```

## Classes

```{eval-rst}
.. autoclass:: boki.layouts.Layout
   :members: bs_kind, pl_kinds, income_kinds, stages

.. autoclass:: boki.layouts.Kind

.. autoclass:: boki.layouts.Stage

.. autoclass:: boki.layouts.Standard
```
