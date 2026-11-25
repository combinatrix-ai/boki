# Groups and consolidation

A group consolidates entities under a parent. You record how the parent came to own each entity (its acquisition, later
purchases, sales) with `own()`, and boki derives the consolidated income statement, balance sheet and cash-flow statement
from the members' own books. That covers non-controlling interests, goodwill, the equity method, the elimination of trades
between members, unrealized profit, and the translation of foreign subsidiaries. This page walks through each with a small
parent and subsidiary. It assumes you have read [Entities, statements and the ledger](statements.md).

## A group and its first acquisition

{py:meth}`boki.Model.group` creates a group around a parent entity, and {py:meth}`boki.group.core.Group.own` records that
the parent owns another entity. The examples on this page start from the same two companies, built by a small function:

```{doctest}
>>> import boki as b
>>> from boki.units import JPY, USD, year
>>> def company_pair(periods=3):
...     m = b.Model("Group plan", start="2027-01", periods=periods, step=year)
...     parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
...     sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
...     parent.bs.opening(cash=1000 * JPY)
...     sub.bs.opening(cash=500 * JPY)
...     sub.pl.revenue("Sales", 100 * JPY)
...     return m, parent, sub, m.group("Group", parent=parent)
```

The parent buys 80% of the subsidiary for 400 at the start of the first year. The subsidiary has net assets of 500, so the
price is exactly the parent's 80% share:

```{doctest}
>>> m, parent, sub, g = company_pair()
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
>>> r = m.render()
>>> print(r.pl(g))
PL Group                     2027  2028  2029
Revenue                       100   100   100
  Sales                       100   100   100
Gross profit                  100   100   100
Other income                    0     0     0
  Gain on bargain purchase      0     0     0
Operating profit              100   100   100
Profit before tax             100   100   100
Profit for the year           100   100   100
Attributable to:                -     -     -
  Non-controlling interests    20    20    20
  Owners of the parent         80    80    80
>>> print(r.bs(g))
BS Group                       2027   2028   2029
  Cash and cash equivalents   1,200  1,300  1,400
  Goodwill                        0      0      0
Total assets                  1,200  1,300  1,400
Total liabilities                 0      0      0
  Retained earnings           1,080  1,160  1,240
  Non-controlling interests     120    140    160
Total equity                  1,200  1,300  1,400
Total equity and liabilities  1,200  1,300  1,400
>>> [round(v) for v in r[g.books.cf.investing]]
[100, 0, 0]
```

Read the consolidated statements with `r.pl(g)`, `r.bs(g)` and `r.cf(g)`, as you would those of an entity.

- The group holds both companies' cash: the parent's 600 left after paying 400, plus the subsidiary's 600.
- The subsidiary earns 100 a year, all of it in the consolidated income statement. 80 belongs to the parent's owners and
  20 to the **non-controlling interests** (NCI), the 20% the parent does not own.
- The NCI on the balance sheet start at 20% of the subsidiary's net assets, 100, and grow by their share of profit.
- Investing cash flow is +100: the 400 paid, net of the 500 of cash that came with the subsidiary. The statement lists
  the price (`Sub shares`) and the cash acquired (`Acquisition clearing`) as two rows.

The parent's own books are unchanged. They carry the investment as an asset at its price:

```{doctest}
>>> [round(v) for v in r.bs(parent).row("Sub shares")]
[400, 400, 400]
```

## How the consolidated books are built

Separate books stay entity-specific, and consolidation is derived from them in three steps when the model renders:

1. **Replay.** Each member's entries are replayed into the group's ledger for the periods in which it is in the group.
   Income before an acquisition, or after control is lost, is left out.
2. **Eliminate.** The entries of trades between members (booked with `counterparty=`) are removed, so that the group shows
   only dealings with outsiders. See {ref}`trades between members <guide-consolidation-trades>`.
3. **Consolidate.** Entries for the ownership events are added: the acquisition, goodwill, NCI, unrealized profit,
   equity-method accounting and translation.

`g.books` is the result as an entity, with `books.pl`, `books.bs`, `books.cf` and `books.net_income`. It builds the books
again on every read, so read it once and keep the result. The group uses the parent's accounting standard, layout and
currency, and every member must have the same layout as the parent.

As for any entity, `m.render()` verifies the consolidated books. The balance sheet balances, the cash-flow statement agrees
with the change in cash, and the profit attributed to the owners and to the NCI adds up to net income.
{py:class}`boki.LedgerError` reports a failure.

## Events: acquisition, purchase, sale

Every `own()` call is one dated event for one entity. The event takes effect at the **start** of the `since` period, so the
balances it uses are the opening balances of that period, and the group's cash flow shows the acquisition in that period.
The kind of event follows from the previous one:

| Call | Event | What it needs |
|---|---|---|
| The first `own()` of an entity | Acquisition, or the start of an equity or cost holding | `method=`, and `consideration=` unless the parent already holds the shares |
| A higher `share` with the same method | Purchase | `consideration=` |
| A lower `share` | Sale | `proceeds=`, and `retained_value=` when control is lost and a stake remains (IFRS, US GAAP) |
| `method="consolidate"` after `"equity"` or `"cost"` | Step acquisition | `previously_held_value=` and `consideration=` |
| `since="before"` | A holding from before the model | `opening=`; see {ref}`holdings from before the model <guide-consolidation-before>` |

`method=` is `"consolidate"` (a subsidiary), `"equity"` (an associate) or `"cost"` (an investment held as a financial
asset). boki does not infer it from the percentage: you say which one applies. `consideration=` is the price the parent
pays to outsiders. If the parent already paid for the shares through a capital contribution made with `counterparty=` on the
subsidiary's `bs.capital`, leave it out, so the investment is not recorded twice.

### Goodwill and fair values

Goodwill is the price plus the NCI, less the net assets acquired. Pay 450 for the same 80% and the difference is booked as
goodwill. Pay less than the share of net assets and it is a gain on a bargain purchase in the acquisition period:

```{doctest}
>>> m, parent, sub, g = company_pair()
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=450 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.bs(g).row("Goodwill")]
[50, 50, 50]
>>> m, parent, sub, g = company_pair()
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=350 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.pl(g).row("Gain on bargain purchase")]
[50, 0, 0]
```

The standards disagree on how goodwill and the NCI are measured, and boki raises an error for terms the parent's standard
does not allow:

| | J-GAAP | US GAAP | IFRS |
|---|---|---|---|
| Goodwill | Amortized straight-line over `goodwill_life=` (required, at most 20 years) | Not amortized; `private_company=True` allows `goodwill_life=` (at most 10 years) | Not amortized; `goodwill_life=` is an error |
| NCI at acquisition | Proportionate share of net assets | Fair value for a partial acquisition: `nci="fair_value"` and `nci_value=` (full goodwill) | Proportionate share (the default), or `nci="fair_value"` with `nci_value=` |
| Losses of a subsidiary | The parent bears losses beyond the NCI, and later profits recover them first | NCI can go negative | NCI can go negative |

You supply the amount of any impairment with `impairment=`; boki does not test for it.

Fair-value adjustments and assets that exist only at acquisition live in the consolidated books, not in the subsidiary's.
Pass `fair_value={line: amount}` for adjustments to the subsidiary's lines, with a remaining life for a depreciating asset,
and `acquired={name: amount}` for items that were never on its balance sheet. The adjustments carry deferred tax at the
subsidiary's `tax_rate`, unless you say `tax_basis="stepped_up"`:

```{doctest}
>>> m = b.Model("Fair values", start="2027-01", periods=2, step=year)
>>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
>>> target = m.entity("Target", standard=b.IFRS, currency=JPY, tax_rate=0.3)
>>> parent.bs.opening(cash=1000 * JPY)
>>> land = target.bs.other_asset("Land", opening=200 * JPY)
>>> plant = target.bs.other_asset("Plant", opening=300 * JPY)
>>> g = m.group("Group", parent=parent)
>>> g.own(target, 0.8, since=0, method="consolidate", consideration=600 * JPY,
...       fair_value={land: 100 * JPY, plant: (50 * JPY, 5 * year)})
>>> r = m.render()
>>> print(r.bs(g))
BS Group                                  2027   2028
  Cash and cash equivalents                400    400
  Land                                     300    300
  Plant                                    340    330
  Goodwill                                 116    116
Total assets                             1,156  1,146
  Deferred tax liability: Target: Land      30     30
  Deferred tax liability: Target: Plant     12      9
Total liabilities                           42     39
  Retained earnings                        994    989
  Non-controlling interests                120    118
Total equity                             1,114  1,107
Total equity and liabilities             1,156  1,146
```

Net assets are 500, plus 150 of fair-value adjustments, less 45 of deferred tax: 605. Goodwill is 600 less 80% of that,
which is 116. The plant adjustment is depreciated over its five years, and the deferred tax is released with it.

### Later purchases and sales

Buying more shares while control continues is a transaction between owners, not an acquisition. The NCI shrink by the share
bought times the subsidiary's net assets, the difference from the price goes to capital, goodwill does not change, and the
cash is financing:

```{doctest}
>>> m, parent, sub, g = company_pair()
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
>>> g.own(sub, 0.9, since=1, consideration=70 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.bs(g).row("Non-controlling interests")]
[120, 70, 80]
>>> [round(v) for v in r.bs(g).row("Share premium")]
[0, -10, -10]
>>> [round(v) for v in r[g.books.cf.financing]]
[0, -70, 0]
```

Selling shares works the other way, and needs `proceeds=`. A sale that keeps control is again between owners. A sale that
loses control removes the subsidiary from the group from the start of that period, with its assets, liabilities and NCI,
and books a gain or loss. Under IFRS and US GAAP the stake that remains is remeasured to its fair value, `retained_value=`:

```{doctest}
>>> m, parent, sub, g = company_pair(periods=4)
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
>>> g.own(sub, 0.4, since=2, method="equity", proceeds=300 * JPY, retained_value=250 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.pl(g).row("Gain (loss) on disposal of subsidiary")]
[0, 0, -10, 0]
>>> [round(v) for v in r.bs(g).row("Investments in associates: Sub")]
[0, 0, 290, 330]
```

From the third year the 40% that remains is an associate under the equity method. Under J-GAAP, `retained_value=` is an
error: a stake that stays an associate keeps its consolidated carrying amount. The gain or loss, the treatment of OCI and the
cash flow of each kind of event are in the {py:meth}`boki.group.core.Group.own` reference.

## Associates and the equity method

An associate is not combined line by line. With `method="equity"` its entries are not replayed. The group carries one
investment that starts at the price and grows with the parent's share of the associate's profit and OCI, less the dividends
the parent receives and, under J-GAAP, the amortization of goodwill inside the price. The share of profit appears in the
income statement under the standard's name for it (IFRS: "Share of profit of associates"). Losses are recognized only until
the investment reaches zero, and later profits recover the excess first (`loss_limit=True`, the default).

`method="cost"` is for an investment held as a financial asset: it stays at its price, and dividends are income. Here is
the same 30% holding under both methods, with an associate that earns 50 and pays the parent 6 a year:

```{doctest}
>>> def associate_group(method):
...     m = b.Model("Associate", start="2027-01", periods=3, step=year)
...     parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
...     assoc = m.entity("Associate", standard=b.IFRS, currency=JPY)
...     parent.bs.opening(cash=1000 * JPY)
...     plant = assoc.bs.other_asset("Plant", opening=600 * JPY)
...     profit = assoc.pl.revenue("Profit", 50 * JPY)
...     payout = assoc.bs.dividend("Dividend", 6 * JPY, counterparty=parent)
...     g = m.group("Group", parent=parent)
...     g.own(assoc, 0.3, since=0, method=method, consideration=200 * JPY)
...     return m.render(), g
>>> for method in ("equity", "cost"):
...     r, g = associate_group(method)
...     print(method, [round(r.value(g.books.net_income, y)) for y in ("2027", "2028", "2029")],
...           [round(r.value(g.books.bs.total_assets, y)) for y in ("2027", "2028", "2029")])
equity [15, 15, 15] [1015, 1030, 1045]
cost [6, 6, 6] [1006, 1012, 1018]
```

Under the equity method the group's profit is the 15 share of the associate's profit, and the investment is 200 plus 15, less
the 6 received: 209 after the first year. Under the cost method the profit is only the 6 dividend and the investment stays at
200. Buying or selling part of an associate, or moving between methods, are further `own()` events. Dividends received
from an associate are operating cash flow, and buying and selling the holding is investing.

(guide-consolidation-trades)=
## Trades between members

When members trade with each other, book the trade once with `counterparty=`. The other entity gets the matching line, and
the group removes the trade from its statements, since a company cannot sell to itself. Here the subsidiary sells flour to
the parent, who pays a year later:

```{doctest}
>>> m, parent, sub, g = company_pair()
>>> bread = parent.pl.revenue("Bread", 300 * JPY)
>>> flour = sub.pl.revenue("Flour to Parent", 80 * JPY, settle=b.delay(1), counterparty=parent.pl.cogs)
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.pl(sub).row("Revenue")]
[180, 180, 180]
>>> [round(v) for v in r.pl(parent).row("Cost of sales")]
[80, 80, 80]
>>> [round(v) for v in r.pl(g).row("Revenue")]
[400, 400, 400]
>>> [round(v) for v in r.bs(sub).row("Trade receivables")]
[80, 80, 80]
>>> [round(v) for v in r.bs(parent).row("Trade payables")]
[80, 80, 80]
>>> print(r.bs(g))
BS Group                       2027   2028   2029
  Cash and cash equivalents   1,500  1,900  2,300
  Goodwill                        0      0      0
Total assets                  1,500  1,900  2,300
Total liabilities                 0      0      0
  Retained earnings           1,364  1,728  2,092
  Non-controlling interests     136    172    208
Total equity                  1,500  1,900  2,300
Total equity and liabilities  1,500  1,900  2,300
>>> [round(v) for v in r.pl(g).row("Owners of the parent")]
[364, 364, 364]
>>> [round(v) for v in r.pl(g).row("Non-controlling interests")]
[36, 36, 36]
```

The subsidiary's own revenue is 180 and the parent's own cost of sales is 80, both including the trade. The group's revenue
is the 300 of bread and 100 of outside sales, it has no cost of sales, and the receivable and the payable cancel.
`flour.counterparty` is the parent's matching line.

The elimination does not change who owns the profit. The NCI take 20% of the subsidiary's own profit, 180 including the
sale to the parent, so they grow by 36 a year, and the parent's owners bear the 80 of cost: of the group's 400 of profit, 364 belongs
to the owners of the parent and 36 to the NCI. Only the profit still held inside the group, on goods or equipment
the buyer has not yet used, is taken out first; see {ref}`unrealized profit <guide-consolidation-unrealized>`.

`counterparty=` is not limited to revenue and expense lines. A loan takes the lender (`counterparty=parent` books the loan
receivable, the draws and the interest income on the parent's side), `bs.capital` takes the owner, and `bs.dividend` takes
the receiving owner, so that the dividend is income there. All of these are eliminated in the group. A subsidiary's
dividend written without `counterparty=` goes to outside shareholders, so it reduces the NCI and is a financing cash flow.
The {doc}`line pages <../reference/api/makers/index>` list each.

Only the entries of the trade itself are eliminated. What the buyer does afterwards, such as consuming inventory or
depreciating an asset, stays in the group.

(guide-consolidation-unrealized)=
### Unrealized profit

A sale of goods or equipment within the group makes a profit the group has not earned until the buyer uses the asset or
sells it on. Book it as a revenue line whose `counterparty=` is the buyer's `inventory` or `fixed_asset`. Give the seller's
profit as a share of the price with `margin=`, and how the buyer uses the asset with `used=` (a kernel, for inventory) or
`life=` (a time, for a fixed asset). boki cannot derive the seller's cost from one trade, so you book the cost on the
seller's own lines. Here the subsidiary sells parts at 100 that cost it 70, and the parent uses each year's parts the year
after:

```{doctest}
>>> m = b.Model("Group plan", start="2027-01", periods=3, step=year)
>>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY, tax_rate=0.3)
>>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY, tax_rate=0.3)
>>> parent.bs.opening(cash=1000 * JPY)
>>> sub.bs.opening(cash=500 * JPY)
>>> bread = parent.pl.revenue("Bread", 200 * JPY)
>>> parts = sub.pl.revenue("Parts", 100 * JPY, counterparty=parent.bs.inventory, margin=0.3, used=b.delay(1))
>>> parts_cost = sub.pl.cogs("Parts cost", 70 * JPY)
>>> g = m.group("Group", parent=parent)
>>> g.own(sub, 0.8, since=0, method="consolidate", consideration=400 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.bs(parent).row("Parts (Sub)")]
[100, 100, 100]
>>> [round(v) for v in r.bs(g).row("Parts (Sub)")]
[70, 70, 70]
>>> [round(v) for v in r.bs(g).row("Deferred tax asset: Unrealized profit: Sub to Parent: Parts")]
[9, 9, 9]
>>> [round(r.value(parent.net_income, y) + r.value(sub.net_income, y)) for y in ("2027", "2028", "2029")]
[230, 130, 130]
>>> [round(v) for v in r.pl(g).row("Profit for the year")]
[209, 130, 130]
```

In the parent's books the parts are worth 100. In the group they are worth the subsidiary's cost, 70. The 30 of profit is
eliminated until the parts are used, with a deferred tax asset of 9 at the tax rate. The tax rate is required, so give the
entity `tax_rate=`; which entity's rate applies depends on the standard. In the first year the group's profit is 21 lower than
the two companies' separate profits added together. From the second year, the profit released from last year's parts equals
the profit eliminated on this year's, and the adjustment is zero. A profit on an upstream sale (subsidiary to parent) is
shared between the parent and the NCI by ownership, and a downstream one belongs to the parent.

To sell an existing fixed asset between members, use {py:meth}`boki.ledger.BS.sell`. The group eliminates the gain and
realizes it through the buyer's depreciation.

(guide-consolidation-before)=
## Holdings from before the model

A model rarely starts on the day of the acquisition. With `since="before"` you say the holding began earlier, and you supply
the consolidated balances at the start: boki does not calculate them from an acquisition date it never sees. `opening=`
takes `"nci"` (required, including the NCI's share of OCI), and optionally `"goodwill"`, `"fair_value"`, `"acquired"`,
`"deferred_tax"`, `"unrealized"`, `"oci"` and `"capital_surplus"`. An equity-method holding takes `"investment"` and its
own optional keys. Goodwill and fair-value adjustments are given with their remaining life, and the group amortizes them
from there.

The parent's investment has to be in its opening balance sheet. Either use the subsidiary's `bs.capital(..., opening=,
counterparty=parent)`, which mirrors the shares on the parent's side, or give the parent an `other_asset` line with an
opening balance and pass it as `investment=`. Use one, not both. The earlier acquisition becomes a set of opening balances,
with no acquisition cash flow:

```{doctest}
>>> m = b.Model("Opening holdings", start="2027-01", periods=3, step=year)
>>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
>>> sub = m.entity("Sub", standard=b.IFRS, currency=JPY)
>>> parent.bs.opening(cash=600 * JPY)
>>> shares = parent.bs.other_asset("Sub shares", opening=400 * JPY)
>>> sub.bs.opening(cash=500 * JPY)
>>> sales = sub.pl.revenue("Sales", 100 * JPY)
>>> g = m.group("Group", parent=parent)
>>> g.own(sub, 0.8, since="before", method="consolidate", investment=shares,
...       opening={"goodwill": 0 * JPY, "nci": 100 * JPY})
>>> r = m.render()
>>> [round(v) for v in r.bs(g).row("Non-controlling interests")]
[120, 140, 160]
>>> [round(v) for v in r[g.books.cf.investing]]
[0, 0, 0]
```

The opening consolidated balance sheet has to balance. If your `opening` figures leave a difference, `render` raises
{py:class}`boki.LedgerError` with the amount, and does not plug it into retained earnings. Opening intercompany balances
(`opening=` with `counterparty=` on loans, capital and receivables) create the matching balance on the other side, and both
are eliminated.

## Entities in other currencies

An entity keeps its books in its functional currency. Give the model the exchange rates with {py:meth}`boki.Model.fx`,
quoted as the second currency per one of the first, and the group translates the subsidiary into the parent's currency:
assets and liabilities at the closing rate, income and changes at the period average, and the equity acquired at the rate
on the acquisition date. Capital and dividends between members are translated at the rate you give with `fx_rate=` on
`bs.capital` and `bs.dividend`, and at the period average without it. The difference is a foreign currency translation
adjustment in OCI, and the NCI take their share of it. Without rates between the two currencies,
rendering the group raises an error.

A US subsidiary with net assets of 100 dollars earns 10 dollars a year. The rate was 150 yen to the dollar when the parent
paid 15,000 yen for it:

```{doctest}
>>> m = b.Model("Overseas", start="2027-01", periods=2, step=year)
>>> rates = m.fx(USD, JPY, closing=[150, 160], average=[145, 155], opening=150)
>>> parent = m.entity("Parent", standard=b.IFRS, currency=JPY)
>>> us = m.entity("US Inc.", standard=b.IFRS, currency=USD)
>>> parent.bs.opening(cash=15_000 * JPY)
>>> us.bs.opening(cash=100 * USD)
>>> profit = us.pl.revenue("Profit", 10 * USD)
>>> g = m.group("Group", parent=parent)
>>> g.own(us, 1, since=0, method="consolidate", consideration=15_000 * JPY)
>>> r = m.render()
>>> [round(v) for v in r.pl(g).row("Profit for the year")]
[1450, 1550]
>>> [round(v) for v in r.bs(g).row("Total assets")]
[16500, 19200]
>>> [round(v) for v in r.bs(g).row("Other components of equity: Foreign currency translation (US Inc.)")]
[50, 1200]
```

Income is 10 dollars at the average rates: 1,450 and 1,550 yen. Net assets are 100 + 10 = 110 dollars at the first closing
rate, 16,500 yen, so the translation adjustment is 16,500 less the price of 15,000 and the profit of 1,450, which is 50. The
balance accumulates to 1,200 by the second year.

When control is lost, the accumulated adjustment is reclassified to profit: all of the parent's share under IFRS and US GAAP,
and the part relating to the interest sold under J-GAAP. An exchange difference on a loan between members stays in profit,
unless the loan is declared part of the net investment (`net_investment=True`), which moves the difference to the translation
adjustment.

## Reading a group

`r.pl(g)`, `r.bs(g)` and `r.cf(g)` give the statements as tables, and `g.books` gives an entity to read series from, such as
`books.net_income`, `books.bs.cash` or `books.cf.investing`. The group's depreciation, amortization and operating income are
`g.depreciation`, `g.amortization` and `g.operating_income`. Like an entity, a group refuses to define EBITDA or EBIT,
because the standards disagree on what they include; build them from the parts. The consolidated statements go to Excel like
those of an entity ([Excel output](excel.md)).
