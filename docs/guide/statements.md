# Entities, statements and the ledger

An entity is a company with its own books. You describe the business with lines (revenue, costs, assets, loans), and boki
posts balanced journal entries for each line into one ledger. The income statement, balance sheet and cash-flow statement
are views of that ledger, which is why they always agree. This page shows how to create an entity and choose its
accounting standard, what the common lines book, how timing arguments such as `settle=` change the entries, how tax,
opening balances and manual journal entries work, how the cash-flow statement is derived, and which of the four names
for other comprehensive income (OCI) to use.

One small bakery runs through the page. Each section adds lines to it.

## A first entity

{py:meth}`boki.Model.entity` creates an entity. Give it a name, an accounting standard and, to keep units honest, a
currency. Then add lines to its income statement (`co.pl`) and balance sheet (`co.bs`).

```{doctest}
>>> import boki as b
>>> from boki.units import USD, year
>>> m = b.Model("Bakery", start="2027-01", periods=4, step=year)
>>> co = m.entity("Bakery", standard=b.USGAAP, currency=USD)
>>> co.bs.opening(cash=150 * USD)
>>> sales = co.pl.revenue("Sales", {0: 60 * USD, 1: 120 * USD, 2: 150 * USD, 3: 150 * USD}, settle=b.delay(1))
>>> flour = co.pl.cogs("Flour", 0.5 * sales, settle=b.delay(1))
>>> wages = co.pl.sga("Wages", 40 * USD)
>>> oven = co.bs.fixed_asset("Oven", 60 * USD, at=0, life=3 * year)
>>> r = m.render()
>>> print(r.pl(co))
PL Bakery                2027  2028  2029  2030
Revenue                    60   120   150   150
  Sales                    60   120   150   150
Cost of revenue            30    60    75    75
  Flour                    30    60    75    75
Gross profit               30    60    75    75
Operating expenses         40    60    60    60
  Wages                    40    40    40    40
  Oven depreciation         0    20    20    20
Operating income (EBIT)   -10     0    15    15
Pre-tax income            -10     0    15    15
Net income                -10     0    15    15
>>> print(r.bs(co))
BS Bakery                   2027  2028  2029  2030
  Cash                        50    40    60    95
  Accounts receivable         60   120   150   150
  Oven                        60    40    20     0
Total assets                 170   200   230   245
  Accounts payable            30    60    75    75
Total liabilities             30    60    75    75
  Retained earnings          140   140   155   170
Total equity                 140   140   155   170
Total liabilities & equity   170   200   230   245
>>> print(r.cf(co))
CF Bakery                  2027  2028  2029  2030
  Accounts receivable         0    60   120   150
  Accounts payable            0   -30   -60   -75
  Wages                     -40   -40   -40   -40
Cash flow from operations   -40   -10    20    35
  Oven                      -60     0     0     0
Cash flow from investing    -60     0     0     0
Cash flow from financing      0     0     0     0
Net change in cash         -100   -10    20    35
```

You wrote four lines and an opening cash balance. boki added the rest:

- Customers pay a year after the sale and the flour is paid a year later too, so the balance sheet carries an Accounts
  receivable and an Accounts payable.
- The oven is bought with cash in 2027 and depreciated from the next period, so the income statement has an "Oven
  depreciation" line you did not write.
- The cash-flow statement lists the cash that moved, grouped into operating, investing and financing.

Every `co.pl.<kind>` and `co.bs.<kind>` is a {py:class}`boki.LineMaker`, and calling it returns a
{py:class}`boki.LineItem`. A line item is a series, so `0.5 * sales` above is an ordinary expression. Read values from the
result with `r.value(line, "2027")` or `r[line]`, or print a statement as a table with {py:meth}`boki.Result.pl`,
{py:meth}`boki.Result.bs` and {py:meth}`boki.Result.cf`.

Write amounts as quantities such as `60 * USD`. Most arguments also take a plain number as an amount in the entity's
currency, but some, such as a loan's `repay=`, reject one once the entity has a currency. See
[Units, currencies and rates](units.md).

### Standards and layouts

`standard=` is `b.IFRS`, `b.USGAAP` or `b.JGAAP`; without it, an entity uses J-GAAP. The standard sets the entity's
**layout**: which kinds of income-statement and balance-sheet lines exist, which subtotals sit between them, and in what
order. It also sets the names the statements show and a few standard-specific treatments, such as how goodwill is handled
in a group.

The three general layouts share their balance-sheet kinds. The income statements differ:

- **IFRS**: `revenue`, `cogs`, `sga`, `other_income`, `other_expense`, `finance_income`, `finance_cost`, `income_tax`.
- **US GAAP**: `revenue`, `cogs`, `sga`, `other_income`, `other_expense`, `interest_expense`, `income_tax`.
- **J-GAAP**: `revenue`, `cogs`, `sga`, `non_operating_income`, `non_operating_expense`, `special_gain`, `special_loss`,
  `income_tax`, with an ordinary-income subtotal between operating income and the extraordinary items.

Reading a kind the layout does not have raises `AttributeError` and lists the kinds that exist. The same key also has a
different name under each standard:

```{doctest}
>>> labels = b.Model("Labels", start="2027-01", periods=1, step=year)
>>> [labels.entity(s.name, standard=s).label("net_income") for s in (b.IFRS, b.USGAAP, b.JGAAP)]
['Profit for the year', 'Net income', 'Net income']
>>> co.pl.special_loss
Traceback (most recent call last):
...
AttributeError: US GAAP has no PL kind 'special_loss'; available: revenue, cogs, sga, other_income, other_expense, interest_expense, income_tax
```

In the general layouts, loan interest goes to the standard's interest kind (IFRS finance cost, US GAAP interest expense,
J-GAAP non-operating expense), and depreciation to `sga`. A bank has its own layout, {py:data}`boki.layouts.bank`, and you can define your own.
The {doc}`layout pages <../reference/api/makers/index>` list the makers of each layout, and the
[layouts reference](../reference/api/layouts.md) explains how to define one.

### Fiscal years

Periods belong to the model; an entity reports them in its fiscal years. Give the entity {py:func}`boki.fiscal` and ask
for `by="fiscal_year"`. A model that starts in January with a March year-end begins with a short fiscal year:

```{doctest}
>>> from boki.units import JPY
>>> months = b.Model("Fiscal", start="2027-01", periods=15, step=b.month)
>>> shop = months.entity("Shop", standard=b.JGAAP, currency=JPY, fiscal=b.fiscal("03-31"))
>>> shop.bs.opening(cash=1000 * JPY)
>>> takings = shop.pl.revenue("Takings", 10 * JPY)
>>> table = months.render().pl(shop, by="fiscal_year")
>>> table.columns, table.row("Takings")
(['FY2027-03', 'FY2028-03'], [30.0, 120.0])
```

## What a line books

Behind each line is a set of journal entries: an amount, an account to debit and an account to credit. The lines used on
this page book:

| Line | When it is booked | Later |
|---|---|---|
| Revenue, no timing | debit cash, credit revenue | |
| Revenue with `settle=` | debit receivable, credit revenue | debit cash, credit receivable, by the kernel |
| Expense, no timing | debit expense, credit cash | |
| Fixed asset | debit the asset, credit cash | each period: debit depreciation expense, credit the asset |
| Loan | debit cash, credit the loan | each period: debit interest expense, credit cash; on repayment: debit the loan, credit cash |
| Capital | debit cash, credit capital | |
| Dividend | debit retained earnings, credit cash | |
| Income tax | debit tax expense, credit cash | |

The Notes of each line's reference page list its entries. The entries are real: you can write them out as Beancount text
(see [Excel output](excel.md)).

### Why the statements tie out

Every entry debits one account and credits another by the same amount, so the debits and credits of a ledger always sum
to zero. The statements are views of that ledger:

- The **income statement** adds up the income and expense accounts, period by period.
- The **balance sheet** shows the closing balance of every asset, liability and equity account. Profit is not posted to
  retained earnings; the statements add the profit to date to it.
- The **cash-flow statement** groups the entries that touch cash.

A balance sheet built this way balances whatever you write. `m.render()` still verifies it, and raises
{py:class}`boki.LedgerError` if the opening balance sheet does not balance, assets differ from liabilities plus equity in
any period, the cash-flow sections do not add up to the change in cash, or the indirect cash flow differs from the direct
one.

```{doctest}
>>> years = ["2027", "2028", "2029", "2030"]
>>> all(abs(r.value(co.bs.total_assets, y) - r.value(co.bs.total_liabilities, y) - r.value(co.bs.total_equity, y)) < 1e-9
...     for y in years)
True
>>> flows = [r.value(co.cf.operating, y) + r.value(co.cf.investing, y) + r.value(co.cf.financing, y) for y in years]
>>> changes = [r.value(co.bs.cash, y) - r.value(co.bs.cash.opening, y) for y in years]
>>> all(abs(flow - change) < 1e-9 for flow, change in zip(flows, changes))
True
```

A `LedgerError` means a bug in boki or an amount computed outside the ledger. The one input that can cause it is an
opening balance sheet that does not balance (see {ref}`opening balances <guide-opening-balances>`). A number you compute with
`m.series` and never book through a line is not in the statements, and nothing can check it.

Your own plan checks are separate: every entity checks that cash never goes negative, and `m.check` adds more. See
[Checks and expectations](checks.md).

## Income-statement lines and timing

The value of an income-statement line in a period is the amount recognized in that period's profit. When the cash moves is
a separate question, and a few arguments answer it. They work on revenue and expense lines alike; an expense mirrors a
revenue, with a payable for the receivable and prepaid expenses for deferred revenue.

| Argument | What it says | Entries |
|---|---|---|
| (none) | Cash moves when the line is booked | debit cash, credit revenue |
| `settle=` | Cash follows a kernel, such as {py:func}`boki.delay` or {py:func}`boki.even` | accrue in the shared receivable, then collect |
| `cash=` | Cash follows a schedule you give | accrue in the shared receivable, then collect by the schedule |
| `recognize=` | Profit follows a kernel, after the amount is billed | bill into deferred revenue, then recognize |
| `against=` | The other side is a balance of the entity, not cash | debit that balance, credit revenue |
| `vat=` | The line stays net of tax and the tax is held aside | collect or pay the tax with the line's cash; {py:meth}`boki.ledger.Entity.vat_settlement` pays the net |

Lines share the receivable, payable, deferred-revenue, prepaid and VAT accounts that these arguments open, so ten lines
with `settle=` make one Accounts receivable. The full list of arguments and the valid combinations is on the
{doc}`revenue and expense line <../reference/api/makers/template-pl_line>` page.

**`recognize=`.** A service plan is paid up front and earned over two years. The cash arrives in 2027, and half of the
revenue is recognized in each year:

```{doctest}
>>> plans = co.pl.revenue("Service plans", {0: 60 * USD}, recognize=b.even(2))
>>> r = m.render()
>>> [round(v) for v in r[plans]]
[30, 30, 0, 0]
>>> r.bs(co).row("Deferred revenue")
[30.0, 0.0, 0.0, 0.0]
```

**`cash=`.** A catering contract of 90 is booked in 2028 and paid in three instalments. What the schedule has not covered
stays in the shared receivable:

```{doctest}
>>> contract = co.pl.revenue("Catering contract", {1: 90 * USD}, cash={1: 30 * USD, 2: 30 * USD, 3: 30 * USD})
>>> r = m.render()
>>> [round(v) for v in r[contract]]
[0, 90, 0, 0]
>>> r.bs(co).row("Accounts receivable")
[60.0, 180.0, 180.0, 150.0]
```

**`against=`.** Gift cards are a liability the bakery already carries. Redeeming one earns revenue without any cash moving,
so the revenue line is booked against the liability:

```{doctest}
>>> cards = co.bs.deferred_revenue("Gift cards", opening=40 * USD)
>>> redeemed = co.pl.revenue("Redeemed gift cards", {0: 10 * USD, 1: 10 * USD}, against=cards)
>>> r = m.render()
>>> [round(v) for v in r[cards]]
[30, 20, 20, 20]
```

## Balance-sheet lines

A balance-sheet line's value is its closing balance. Most kinds share one call, a balance that moves by `amount=` against
cash or is held at `target=`. Fixed assets, construction, loans, capital and dividends have their own. Each call is
documented on its template page: {doc}`balance-sheet lines <../reference/api/makers/template-line>`,
{doc}`fixed assets <../reference/api/makers/template-fixed_asset>`,
{doc}`construction <../reference/api/makers/template-construction>`, {doc}`loans <../reference/api/makers/template-loan>`,
{doc}`capital <../reference/api/makers/template-capital>` and {doc}`dividends <../reference/api/makers/template-dividend>`.

**Receivables with `target=`.** Instead of payment terms on each line, state the balance you expect and let cash absorb the
difference. The bakery sells to shops for cash on booking, and assumes the shops owe a quarter of the year's sales at each
year-end:

```{doctest}
>>> wholesale = co.pl.revenue("Wholesale", {1: 40 * USD, 2: 60 * USD, 3: 60 * USD})
>>> owed = co.bs.receivable("Wholesale receivable", target=0.25 * wholesale)
>>> r = m.render()
>>> [round(v, 1) for v in r[owed]]
[0.0, 10.0, 15.0, 15.0]
```

**Loans.** A loan books its draws and repayments against cash and its interest as an expense. A rate without a time unit
is per period, so `0.08` is 8% of the opening balance in each period of this annual model. In a monthly model write
`0.08 / b.year`.

```{doctest}
>>> loan = co.bs.loan("Bank loan", draw={0: 50 * USD}, rate=0.08, repay={2: 25 * USD, 3: 25 * USD})
>>> r = m.render()
>>> [round(v, 1) for v in r[loan]]
[50.0, 50.0, 25.0, 0.0]
>>> [round(v, 1) for v in r[loan.interest]]
[0.0, 4.0, 4.0, 2.0]
```

**Capital and dividends.** Capital raises cash and equity. A dividend is paid out of retained earnings, and its value is the
amount paid in the period, not a balance.

```{doctest}
>>> shares = co.bs.capital("Share capital", 20 * USD, at=1)
>>> payout = co.bs.dividend("Dividend", {3: 10 * USD})
>>> r = m.render()
>>> [round(v) for v in r[shares]]
[0, 20, 20, 20]
>>> [round(v) for v in r[payout]]
[0, 0, 0, 10]
```

**Construction.** Construction in progress collects spend until the asset is complete, then depreciates it. A loan can
capitalize its interest into the asset while it is being built. This example is a separate small model:

```{doctest}
>>> build = b.Model("Second shop", start="2027-01", periods=5, step=year)
>>> second = build.entity("Bakery", standard=b.USGAAP, currency=USD)
>>> second.bs.opening(cash=40 * USD)
>>> takings = second.pl.revenue("Takings", 60 * USD)
>>> new_shop = second.bs.construction("New shop", {0: 60 * USD, 1: 40 * USD}, complete_at=2, life=5 * year)
>>> bridge = second.bs.loan("Construction loan", draw={0: 60 * USD, 1: 40 * USD}, rate=0.1,
...                         capitalize_during=build.t < 2, capitalize_into=new_shop)
>>> r2 = build.render()
>>> [round(v, 1) for v in r2[new_shop]]
[60.0, 106.0, 84.8, 63.6, 42.4]
>>> [round(v, 1) for v in r2[bridge.capitalized_interest]]
[0.0, 6.0, 0, 0, 0]
>>> [round(v, 1) for v in r2[new_shop.depreciation]]
[0, 0, 21.2, 21.2, 21.2]
```

The interest of 2028 (10% of the 60 borrowed in 2027) is added to the asset's cost instead of the income statement, and
depreciation starts in the completion period on the balance at the end of the period before.

Anything the layout has no kind for goes through `co.bs.asset` and `co.bs.liability`. The balance sheet also has
{py:meth}`boki.ledger.BS.deferred_tax` for temporary differences and {py:meth}`boki.ledger.BS.sell` for selling a fixed
asset to another entity.

## Income tax and losses carried forward

`co.pl.income_tax` takes a rate and the profit to tax. Name the base yourself, because the tax law's base is a modeling
decision: usually `co.pl.pretax_income`. A loss adds to a carryforward that shelters later profits, and `nol=` starts the
carryforward with losses from before the model. The bakery spends 80 on a launch campaign in the first year, so it starts
with a loss:

```{doctest}
>>> launch = co.pl.sga("Launch campaign", {0: 80 * USD})
>>> tax = co.pl.income_tax("Income tax", rate=0.2, base=co.pl.pretax_income)
>>> r = m.render()
>>> [round(v) for v in r[co.pl.pretax_income]]
[-50, 166, 71, 73]
>>> [round(v) for v in r[tax.nol.balance]]
[50, 0, 0, 0]
>>> [round(v, 1) for v in r[tax]]
[0.0, 23.2, 14.2, 14.6]
```

The line's `nol` attribute holds the carryforward: `balance` (losses left at the end of the period), `used` (losses set
against that period's profit) and `taxable` (the profit left after them). `nol=30 * USD` starts the carryforward with
losses from before the model, and `nol=False` turns it off, so a loss gives a negative tax. The tax is a cash expense
unless you give `settle=`. Pass `amount=` instead of `rate=` and `base=` for a tax computed elsewhere, such as a minimum tax, or a function
as `rate=` for progressive bands. See the {doc}`income tax <../reference/api/makers/template-income_tax>` page.

(guide-opening-balances)=
## Opening balances

An entity starts from an opening balance sheet. `co.bs.opening(cash=...)` declares the cash, and `opening=` on a line
declares that line's balance. Retained earnings are the figure that balances the sheet, unless you give them:

```{doctest}
>>> start = b.Model("Opening", start="2027-01", periods=2, step=year)
>>> corner = start.entity("Corner shop", standard=b.USGAAP, currency=USD)
>>> corner.bs.opening(cash=150 * USD)
>>> vouchers = corner.bs.deferred_revenue("Gift cards", opening=40 * USD)
>>> round(start.render().value(corner.bs.total_equity, "2027"))
110
>>> corner.bs.opening(cash=150 * USD, retained_earnings=100 * USD)
>>> try:
...     start.render()
... except b.LedgerError as error:
...     print(error)
Corner shop: the opening balance sheet does not balance: assets 150 != liabilities 40 + equity 100; difference 10
```

If you give retained earnings, you take responsibility for the balance, and a sheet that does not balance fails at
render. {py:meth}`boki.ledger.BS.opening` documents both arguments.

An amount you are owed, or owe, from before the model uses `opening=` on the line that has `settle=`. The default assumes
the earlier sales were steady, so with `settle=b.delay(2)` half of the opening balance is collected in each of the first two
periods. `opening_collect=` replaces that schedule:

```{doctest}
>>> carried = b.Model("Carried", start="2027-01", periods=3, step=year)
>>> cafe = carried.entity("Cafe", standard=b.USGAAP, currency=USD)
>>> dinners = cafe.pl.revenue("Dinners", 100 * USD, settle=b.delay(2), opening=240 * USD)
>>> [round(v) for v in carried.render()[cafe.bs.cash]]
[120, 240, 340]
>>> before = carried.render()[cafe.bs.cash]
>>> lunches = cafe.pl.revenue("Lunches", 50 * USD, settle=b.delay(1), opening=60 * USD, opening_collect={2: 60 * USD})
>>> after = carried.render()[cafe.bs.cash]
>>> [round(new - old) for new, old in zip(after, before)]
[0, 50, 160]
```

Lines with `settle=` share one receivable, and their openings add up in it. Declaring `co.bs.receivable("Accounts
receivable", opening=...)` next to them collides with that account and raises `ValueError`; give the balance with `opening=`
on the line instead:

```{doctest}
>>> try:
...     cafe.bs.receivable("Accounts receivable", opening=30 * USD)
... except ValueError as error:
...     print(str(error).split(";")[0])
Cafe already has a receivable named 'Accounts receivable'
```

## How the cash-flow statement is derived

The cash-flow statement is the entries that touch cash, grouped by the class of the account on the other side. Cash against
a profit-and-loss line or an operating balance is **operating**: rent, wages, interest and tax paid, receivables collected.
Fixed assets, deposits and other long-term assets are **investing**. Loans, capital and dividends are **financing**. A
line's `cf=` or a journal entry's `cf=` overrides the class, and `"fx"` is the effect of exchange rates on cash.
{py:class}`boki.ledger.CF` has the four sections as series (`co.cf.operating` and so on), and
{py:meth}`boki.ledger.CF.financing_excluding` leaves some lines out of financing, for instance to size a revolver.

The direct method lists the cash by the account on the other side:

```{doctest}
>>> print(r.cf(co))
CF Bakery                  2027   2028   2029   2030
  Accounts receivable         0     90    150    180
  Accounts payable            0    -30    -60    -75
  Wages                     -40    -40    -40    -40
  Deferred revenue           60      0      0      0
  Wholesale                   0     40     60     60
  Wholesale receivable        0    -10     -5      0
  Bank loan interest          0     -4     -4     -2
  Launch campaign           -80      0      0      0
  Income tax                  0  -23.2  -14.2  -14.6
Cash flow from operations   -60   22.8   86.8    108
  Oven                      -60      0      0      0
Cash flow from investing    -60      0      0      0
  Bank loan                  50      0    -25    -25
  Share capital               0     20      0      0
  Retained earnings           0      0      0    -10
Cash flow from financing     50     20    -25    -35
Net change in cash          -70   42.8   61.8   73.4
```

The indirect method starts from net income, adds back the non-cash charges such as depreciation, and then adjusts for the
change in each operating balance:

```{doctest}
>>> print(r.cf(co, method="indirect"))
CF Bakery                                  2027  2028  2029  2030
  Net income                                -50   143  56.8  58.4
  Depreciation and other non-cash charges     0    20    20    20
  Change in Accounts receivable             -60  -120     0    30
  Change in Accounts payable                 30    30    15     0
  Change in Deferred revenue                 30   -30     0     0
  Change in Gift cards                      -10   -10     0     0
  Change in Wholesale receivable              0   -10    -5     0
Cash flow from operations                   -60  22.8  86.8   108
Cash flow from investing                    -60     0     0     0
Cash flow from financing                     50    20   -25   -35
Net change in cash                          -70  42.8  61.8  73.4
```

Both end at the same net change in cash, and `m.render()` verifies it. The direct statement is where you see that the
dividend is a financing outflow (labelled by the retained earnings it reduces) and that a loan's interest sits in operating,
because interest is an expense. To classify a line differently, give it `cf=`; both statements follow.

## Journal entries by hand

When no line books what you need, {py:meth}`boki.ledger.Entity.journal` posts an amount from one account of the entity to
another. There are two common reasons: a transfer between two balance-sheet accounts that no line books, and a cash entry
that needs its own cash-flow section. The bakery gets a grant of 20 towards the oven. It is a liability until the bakery
earns it, and the cash is investing, not operating:

```{doctest}
>>> grant = co.bs.other_liability("Oven grant", opening=0 * USD)
>>> entry = co.journal("Oven grant received", {0: 20 * USD}, debit=co.bs.cash, credit=grant, cf="investing")
>>> r = m.render()
>>> [round(v) for v in r[grant]]
[20, 20, 20, 20]
>>> [round(v) for v in r[co.cf.investing]]
[-40, 0, 0, 0]
>>> [round(v) for v in r[co.net_income]]
[-50, 143, 57, 58]
```

The entry debits `debit` and credits `credit`. If one side is an income or expense line, the entry changes that line's value,
and so the profit; an entry between balance-sheet accounts, as here, does not. If one side is cash, `cf=` sets the
cash-flow section, and without it the section is that of the other account (operating for a profit-and-loss line).
The indirect statement shows the moved cash on an "Other non-cash items" row, which cancels the grant's change in the
operating balances.

## Other comprehensive income

Other comprehensive income (OCI) is a change in equity that does not pass through profit: a fair-value change on a
security, a hedge, a pension remeasurement. Four names concern it, and they are four different things:

| Name | What it is |
|---|---|
| `co.oci(name, amount, against=...)` | The call that books one OCI item. It returns the component's line. |
| `co.bs.oci` | The equity line maker of kind `oci`. The reserve of each component is its line's `balance`. |
| `co.other_comprehensive_income` | The series of the period's OCI, after tax. |
| `co.oci_release(name, amount)` | The call that reclassifies accumulated OCI to profit or to retained earnings. |

The easy mistake is `co.bs.oci.total`. Every other balance-sheet kind totals to a balance, except dividends, but the lines of
kind `oci` have the period's OCI as their value, so `co.bs.oci.total` is a flow: the same series as
`co.other_comprehensive_income`. The accumulated reserve is `balance` on the line that `co.oci` returned.

```{doctest}
>>> funds = b.Model("Securities", start="2027-01", periods=3, step=year)
>>> fund = funds.entity("Fund", standard=b.IFRS, currency=USD, tax_rate=0.3)
>>> shares_held = fund.bs.other_asset("Shares held", opening=0 * USD)
>>> reserve = fund.oci("Fair value reserve", {0: 100 * USD, 2: -40 * USD}, against=shares_held, tax=True)
>>> r3 = funds.render()
>>> [round(v) for v in r3[reserve]]
[70, 0, -28]
>>> [round(v) for v in r3[reserve.balance]]
[70, 70, 42]
>>> [round(v) for v in r3[fund.bs.oci.total]]
[70, 0, -28]
>>> [round(v) for v in r3[fund.other_comprehensive_income]]
[70, 0, -28]
>>> [round(v) for v in r3[fund.net_income]]
[0, 0, 0]
>>> [round(v) for v in r3[fund.comprehensive_income]]
[70, 0, -28]
```

With `tax=True`, boki recognizes deferred tax on the item at the entity's `tax_rate` and shows the OCI net of it. The profit
is untouched, and comprehensive income is net income plus OCI. Once an entity has OCI, its income statement shows OCI and
comprehensive income below net income.

`co.oci_release` reclassifies a component when the item behind it is sold. A component with `recycle=True` (the default)
moves into profit, and one with `recycle=False` moves to retained earnings, which is how IFRS treats equity instruments held at
fair value through OCI. boki leaves the choice to you. A recycled release adds a profit line and removes the same amount from the period's OCI, so
comprehensive income does not change:

```{doctest}
>>> hedge = fund.oci("Hedge reserve", {0: 50 * USD}, against=shares_held)
>>> released = fund.oci_release("Hedge reserve", {1: 50 * USD})
>>> r3 = funds.render()
>>> [round(v) for v in r3[fund.net_income]]
[0, 50, 0]
>>> [round(v) for v in r3[fund.other_comprehensive_income]]
[120, -50, -28]
>>> [round(v) for v in r3[fund.comprehensive_income]]
[120, 0, -28]
```

A recycled release does not book the tax realized on the gain. Record it in an income tax line.

## Where to go next

- Statements for a group of entities, with ownership, goodwill and eliminations: [Groups and consolidation](consolidation.md).
- Writing the statements to Excel with live formulas: [Excel output](excel.md).
- Sanity checks on a plan, and comparing it with a source model: [Checks and expectations](checks.md).
- The signature and notes of every line maker: {doc}`the line makers <../reference/api/makers/index>`.
