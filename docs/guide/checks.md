# Checks and expectations

A check is a condition you say must hold in the plan, such as "cash never falls below the minimum". boki evaluates it in
every period of every render and, at the default level, stops the render when it fails. This page covers how to declare
checks and read their results, the checks that every entity brings with it, and how to test a model against numbers from elsewhere with
`b.expect` and `b.compare`. The examples build on one small bakery, with a base case and a bear case.

## Checks in your model

{py:meth}`boki.Model.check` takes a condition and a name. The condition is usually a comparison, or a combination of
comparisons with `&`, `|` and `~`. It is checked in every period, and units are checked too: `cash >= 80 * USD`, not
`cash >= 80`. A period where the condition is missing is not checked.

```{doctest}
>>> import boki as b
>>> from boki.units import USD
>>> m = b.Model("Bakery", start="2027-01", periods=4, step=b.year)
>>> co = m.entity("Bakery", standard=b.IFRS, currency=USD)
>>> co.bs.opening(cash=200 * USD)
>>> sales_plan = m.input(
...     "Sales plan", b.by_year({0: 50 * USD, 1: 60 * USD, 2: 80 * USD, 3: 90 * USD}),
...     scenarios={"bear": b.by_year({0: 40 * USD, 1: 40 * USD, 2: 60 * USD, 3: 70 * USD})})
>>> rent_plan = m.input("Rent plan", b.by_year({0: 120 * USD, 1: 100 * USD, 2: 40 * USD, 3: 30 * USD}))
>>> sales = co.pl.revenue("Sales", sales_plan)
>>> rent = co.pl.sga("Rent", rent_plan)
>>> m.check(co.bs.cash >= 80 * USD, "Minimum cash")
>>> r = m.render()
>>> r[co.bs.cash]
[130.0, 90.0, 130.0, 190.0]
>>> [(check.name, check.passed) for check in r.checks]
[('Minimum cash', True), ('Bakery: cash is not negative', True)]
```

The base case holds. `r.checks` lists the outcome of every check as a {py:class}`~boki.model.CheckResult`: yours, and
the one the entity brings (see the books' own checks below). A check runs in every scenario you render, so a scenario is
a test of the plan:

```{doctest}
>>> try:
...     m.render(scenario="bear")
... except b.CheckFailed as error:
...     print(error)
...     failure = error.failures[0]
...     print(failure.name, failure.periods)
...     print(error.result[co.bs.cash])
checks failed:
Minimum cash (fails in 2028; worst 2028: Cash 60 vs 80)
Minimum cash ['2028']
[120.0, 60.0, 80.0, 120.0]
```

A failed check stops {py:meth}`~boki.Model.render` with {py:class}`~boki.CheckFailed`, because a check is a condition you
said must hold. The message gives one line for each failed check, with the failing periods and, for a comparison of two
series, both sides in the period of the largest violation. `CheckFailed` is an
`AssertionError`, so a test runner reports it as a failed assertion.

`render` computes everything before it raises, so the exception carries the complete result as `error.result`. Read the
values behind the failure there: `error.result[cash]`, `error.result.pl(co)`.

## Levels and exploring

A check has a level. `"error"`, the default, raises `CheckFailed`. `"warn"` only warns, for a benchmark that the plan may
miss, such as a covenant ratio. `"off"` is not evaluated and not reported. A warning is a Python `UserWarning`, and the
result still lists the failed check:

```{doctest}
>>> import warnings
>>> bench = b.Model("Benchmark", start="2027-01", periods=3, step=b.year)
>>> dscr = bench.series("DSCR", data={0: 1.1, 1: 1.3, 2: 1.4})
>>> bench.check(dscr >= 1.2, "DSCR covenant", level="warn")
>>> with warnings.catch_warnings(record=True) as caught:
...     warnings.simplefilter("always")
...     result = bench.render()
>>> [str(warning.message) for warning in caught]
['check failed: DSCR covenant (fails in 2027; worst 2027: DSCR 1.1 vs 1.2)']
>>> [(check.name, check.level, check.passed) for check in result.checks]
[('DSCR covenant', 'warn', False)]
```

While you are still building a plan that does not hold together yet, `m.render(checks="warn")` downgrades every error
check, yours and the built-in ones, to a warning for that render. The levels you declared do not change:

```{doctest}
>>> with warnings.catch_warnings(record=True) as caught:
...     warnings.simplefilter("always")
...     bear = m.render(scenario="bear", checks="warn")
>>> [(check.name, check.level, check.passed, check.periods) for check in bear.checks]
[('Minimum cash', 'warn', False, ['2028']), ('Bakery: cash is not negative', 'warn', True, [])]
>>> len(caught)
1
```

## The books' own checks

Every entity checks that its cash is never negative, at level `"error"`. The check is named `"<entity>: cash is not
negative"`. Set its level with {py:meth}`co.checks.cash(level=...) <boki.ledger.EntityChecks.cash>`: `"warn"` for a plan
that is meant to show a funding gap, `"off"` to drop it.

```{doctest}
>>> funding = b.Model("Funding", start="2027-01", periods=2, step=b.month)
>>> cafe = funding.entity("Cafe", standard=b.IFRS, currency=USD)
>>> rent_line = cafe.pl.sga("Rent", 100 * USD)
>>> try:
...     funding.render()
... except b.CheckFailed as error:
...     print(error)
checks failed:
Cafe: cash is not negative (fails in 2027-01, 2027-02; worst 2027-02: cash -200 vs 0)
>>> cafe.checks.cash(level="off")
>>> funding.render().checks
[]
```

Every render also verifies the ledger of each entity and group before it evaluates your checks. The opening balance sheet
must balance, assets must equal liabilities plus equity in every period, the cash-flow sections must add up to the change
in cash, and the indirect cash flow must equal the direct one. A failure raises {py:exc}`~boki.LedgerError`, which names
the entity, the check and the period. It is not a check of your plan, so it has no level. Entries made by boki's own
lines always balance, so a ledger error points to an opening balance sheet that you declared out of balance, an amount
computed outside the ledger, or a bug in boki:

```{doctest}
>>> broken = b.Model("Unbalanced", start="2027-01", periods=1, step=b.year)
>>> shop = broken.entity("Shop", standard=b.IFRS, currency=USD)
>>> shop.bs.opening(cash=1000 * USD, retained_earnings=500 * USD)
>>> try:
...     broken.render()
... except b.LedgerError as error:
...     print(error)
Shop: the opening balance sheet does not balance: assets 1,000 != liabilities 0 + equity 500; difference 500
```

The Excel output has a Checks sheet. For each entity that has a currency it lists the balance sheet and cash flow
tie-outs, then every check you declared except those at level `"off"`. Each cell reads OK or FAIL by period. See
[Excel output](excel.md).

## Testing a model against known numbers

A check says what must be true of the plan. A test says what the plan must equal: the figures in the source workbook you
are rewriting, the numbers the board signed off, or last quarter's run. {py:func}`boki.expect` takes a render and a dict
from series to reference values. It stays silent when they agree and raises `AssertionError` with every disagreement
when they do not:

```{doctest}
>>> b.expect(r, {co.pl.net_income: [-70, -40, 40, 60]})
>>> try:
...     b.expect(r, {co.pl.net_income: [-70, -40, 40, 65]})
... except AssertionError as error:
...     print(error)
values differ from the source:
  Bakery: net_income [2030]: expected 65, got 60
```

Put it in a test function, and the numbers someone signed off cannot drift without notice:

```{doctest}
>>> def test_plan_matches_the_board_deck():
...     b.expect(m.render(), {co.pl.net_income: [-70, -40, 40, 60]})
>>> test_plan_matches_the_board_deck()
```

Use `b.expect` instead of a plain `assert` for the model, because a mismatch lists every number that differs. A plain
`assert` fits checks on the source itself, such as that its own totals add up.

A reference can take these forms:

- A list with one value per period for a series. `None` skips a period that the source has no value for. A wrong
  length raises `ValueError`.
- One number for a scalar series, such as `npv(...)`, `x.sum()` or `x[3]`. A single number given for a whole series is
  compared in every period.
- A quantity such as `28_032_000 * kWh`, compared in its own unit. Bare numbers are in base units (currency units, Wh
  and months). A date series compares as dates.
- A range: {py:func}`boki.approx`, {py:func}`boki.above`, {py:func}`boki.below` and {py:func}`boki.between`.

Two numbers agree when they are within `tol` (absolute, in base units, `0.01` by default) or within `rel` (a fraction of
the larger value, `1e-4` by default), whichever is wider. A source that rounds its figures needs a wider tolerance, or a
range for that key:

```{doctest}
>>> b.expect(r, {co.pl.net_income: [-70.4, -40.4, 40.4, 60.4]}, tol=0.5)
>>> b.expect(r, {co.pl.net_income: [-70, -40, 40, 61]}, rel=0.02)
>>> b.expect(r, {co.bs.cash.last(): b.between(180, 200), co.pl.net_income.sum(): b.approx(-10, tol=0.5)})
```

{py:func}`boki.compare` makes the same comparison and returns it instead of raising. Printing the
{py:class}`~boki.testing.Comparison` draws a table with every number beside its reference and marks each disagreement
with `≠`. It is the tool for finding where a rewritten model drifts from its source. `mismatches` lists the entries that
disagree:

```{doctest}
>>> comparison = b.compare(r, {co.pl.net_income: [-70, -40, 40, 65], co.bs.cash.last(): b.between(180, 200)})
>>> print(comparison)  # doctest: +NORMALIZE_WHITESPACE
                    period  model     source  diff
Bakery: net_income  2027      -70        -70     0
Bakery: net_income  2028      -40        -40     0
Bakery: net_income  2029       40         40     0
Bakery: net_income  2030       60         65    -5  ≠
Cash[-1]                      190  180 to 200     -
>>> [(entry.label, entry.period, entry.got, entry.want) for entry in comparison.mismatches]
[('Bakery: net_income', '2030', 60.0, 65)]
```

Keep the model correct. If the source has an error, do not write a wrong formula to match it: add the known difference to
the expected value, with a note that says why. Signs follow the model, where amounts are positive and an expense is a
positive value on an expense line. If a source stores expenses as negative numbers, compare `-rent` with them.

To compare a render with other inputs or a pasted solution, pass the render you want: `b.expect(m.render(inputs={...},
fix={unknown: value}), {...})`. This is how to test a source whose own solve did not converge.
