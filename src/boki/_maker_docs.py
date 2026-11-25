"""Numpydoc templates for the line makers: one template per create signature.

``PL`` and ``BS`` build every maker from one of eight create functions and look its documentation up here by an
explicit template key: ``"pl_line"`` and ``"income_tax"`` for the PL makers, and the BS mechanism name (``"line"``,
``"fixed_asset"``, ``"loan"``, ``"construction"``, ``"capital"``, ``"dividend"``) for the BS makers. A maker whose
key has no template is an error. The parameters a template documents must be exactly the parameters of its create
function, in order; ``tests/test_docstrings.py`` validates every maker against that.

The ``$metadata`` placeholder in each template is replaced by one sentence about the maker's kind: its name, side,
section, and cash-flow class.
"""
from __future__ import annotations

from string import Template

from .layouts import Kind, Layout

_DOCS = "https://github.com/combinatrix-ai/boki/blob/master/docs"

PL_LINE = Template(f"""\
Add a line to this revenue or expense kind and book its amount in every period.

The line's value in a period is the amount recognized in that period's profit. The amount is booked against cash
unless ``settle``, ``cash``, ``recognize``, ``against`` or ``counterparty`` say otherwise; Notes lists the valid
combinations. The line is also counted in the kind's ``total``. Lines share the receivable, payable, deferred
revenue, prepaid, and VAT accounts that ``settle``, ``recognize`` and ``vat`` open.

Parameters
----------
name : str
    Line name; required. It must be unique among the lines of this kind in the entity.
amount : scalar, Quantity, Series, or dict, optional
    Amount booked in each period, in the entity's currency per period. A plain number is in the entity's currency.
    A quantity per time, such as ``100 * JPY / b.month``, is integrated by period length. A dict maps period
    labels, indices, or dates to amounts and books 0 in the other periods. Give ``amount`` or ``data``; when both
    are given, ``data`` is used.
data : dict, optional
    Amounts for selected periods as ``{{period: amount}}``, with the units of ``amount``. Other periods book 0.
    It replaces ``amount`` when both are given.
settle : Kernel, optional
    How the cash moves after the booking period. The line accrues in the shared receivable (revenue kinds) or
    payable (expense kinds), and cash follows the kernel weights: ``b.delay(2)`` settles two periods later and
    ``b.even(3)`` settles one third in each of three periods. The weights must sum to 1, and a ``b.curve``
    must end in 0.
recognize : Kernel, optional
    When the profit is recognized. The amount is billed in the booking period into deferred revenue (revenue kinds)
    or prepaid expenses (expense kinds), and the line's value follows the kernel: ``b.even(12)`` recognizes an
    annual prepayment over twelve monthly periods. The kernel has the same limits as ``settle``.
cash : scalar, Quantity, Series, or dict, optional
    Cash received (revenue kinds) or paid (expense kinds) in each period, in the entity's currency per period, with
    the forms of ``amount``. It replaces the cash schedule of ``settle``. What the cash does not cover stays in the
    shared receivable or payable, which can turn negative to show a deferral.
category : str, optional
    Free-text label stored on the line as ``LineItem.category``. ``total_of(category=...)`` of the maker totals the
    lines with the same label.
against : LineItem or balance, optional
    A line item or balance in this entity's books, such as a ``co.bs`` line or ``co.bs.cash``, that takes the other
    side of the entry instead of cash: a revenue line debits it and an expense line credits it. No cash moves.
    It does not combine with ``settle``, ``cash``, ``recognize``, ``vat``, ``opening`` or ``counterparty``.
vat : scalar or Series, optional
    Tax rate on the amount, a dimensionless ratio such as ``0.1`` for 10%. The line stays net of tax, and the tax is
    booked in the shared VAT account: collected on a revenue line and paid on an expense line, with the cash timing
    of the line. ``Entity.vat_settlement`` pays the net balance. It does not combine with ``against`` or
    ``counterparty``.
counterparty : LineMaker, optional
    The other side of a trade with another entity of the same model. ``other.pl.<kind>`` of the opposite side
    (a cost for a revenue line, a revenue for a cost line) books the same amount in both entities.
    ``other.bs.inventory`` or ``other.bs.fixed_asset`` books a sale of goods or equipment by a revenue line and needs
    ``margin`` and ``used`` or ``life``. The returned line's ``counterparty`` attribute is the other entity's line.
margin : scalar or Series, optional
    Seller's profit as a dimensionless share of the price: ``0.3`` on a price of 100 is an intercompany profit of
    30. Required with an asset ``counterparty``. It does not change either entity's separate books; consolidation
    uses it to eliminate the unrealized profit.
used : Kernel, optional
    With ``counterparty=other.bs.inventory``, required: how the buyer uses up the purchased inventory. The weights
    give the share used each period after the purchase, and the use becomes the buyer's cost of sales.
life : Quantity or Unit, optional
    With ``counterparty=other.bs.fixed_asset``, required: the buyer's useful life as a time such as ``5 * b.year``.
    The buyer depreciates each purchase straight-line over it, from the purchase period. It must be positive.
opening : scalar or Quantity, optional
    Amount outstanding at the model start from this line's earlier sales (earlier purchases, for an expense kind), in
    the entity's currency. It is added to the opening balance of the shared receivable (payable) that ``settle``
    uses and is collected (paid) in the first periods. Requires ``settle``. It does not combine with ``counterparty``
    or ``against``.
opening_collect : dict, optional
    ``{{period: amount}}`` replacing the default collection schedule of ``opening``: the amounts collected (paid) in
    the listed periods. Periods are indices, dates, or labels. Amounts are plain numbers or quantities, not
    negative, and add up to ``opening``. Requires ``opening``.
actuals : dict, optional
    Historical amounts for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The new line. Its value in each period is the amount recognized in profit. With ``counterparty``, its
    ``counterparty`` attribute is the matching line of the other entity.

Raises
------
TypeError
    At construction, if an argument combination is not valid:

    - ``opening`` or ``opening_collect`` is given without ``settle``, or ``opening_collect`` without ``opening``;
    - ``opening`` is combined with ``counterparty`` or ``against``, or ``opening_collect`` is not a non-empty dict
      of plain amounts;
    - ``against`` is combined with ``settle``, ``cash``, ``recognize`` or ``vat``, or is not a line item or balance;
    - ``margin``, ``used`` or ``life`` is given without an asset ``counterparty``;
    - ``counterparty`` is not a PL kind of another entity or its ``inventory`` or ``fixed_asset``, is ``income_tax``,
      takes the same side as this line, or is combined with ``against`` or ``vat``;
    - an asset ``counterparty`` is used on a kind other than ``revenue``, is combined with ``recognize``, or lacks
      ``margin``, ``used`` (inventory) or ``life`` (fixed asset), or is given the other kind's argument;
    - an amount has a type boki cannot use in an expression.
ValueError
    At construction, if a value is not valid:

    - ``settle``, ``recognize`` or ``used`` is not a distribution: weights that do not sum to 1, or a ``b.curve``
      that does not end in 0;
    - a line with this name already exists for this kind;
    - ``counterparty`` belongs to this entity or to another model;
    - ``against`` is an account of another entity;
    - ``life`` is not positive;
    - ``opening`` is negative, ``opening_collect`` has a negative amount or does not add up to ``opening``, or
      ``settle=b.delay(0)`` leaves nothing outstanding and ``opening_collect`` is missing.
UnitError
    At construction, if an amount is in a unit other than the entity's currency, ``margin`` is not dimensionless, or
    ``life`` is not a time.
IndexError
    At construction, if a period of ``opening_collect`` is outside the model timeline. At evaluation, if a period
    of ``amount``, ``data`` or ``cash`` is outside it.

Notes
-----
$metadata

A revenue line is described first; an expense line mirrors it, with the expense in place of the revenue, the payable
in place of the receivable, and prepaid expenses in place of deferred revenue.

* **Cash on booking** (``amount`` only): debit cash, credit revenue.
* **Settled later** (``settle``): debit the shared receivable and credit revenue when booked; the cash arrives by
  the kernel (debit cash, credit receivable).
* **Own cash schedule** (``cash``, with or without ``settle``): the same entries with the cash given by ``cash``.
  ``cash`` wins when both are given; ``settle`` is still checked, and ``opening`` still uses it.
* **Deferred recognition** (``recognize``, optionally with ``settle`` or ``cash``): when booked, debit cash (or the
  receivable, when ``settle`` or ``cash`` is given) and credit deferred revenue; the revenue is recognized by the
  kernel (debit deferred revenue, credit revenue).
* **Against an account** (``against``): debit that account and credit revenue; no cash moves.
* **VAT** (``vat``, with any of the first four): the tax follows the cash timing of the line.
* **Opening balance** (``opening``, with ``settle``): see below.
* **Trade with another entity** (``counterparty``, optionally with ``settle``, ``cash``, ``recognize``): the same
  expression and timing are booked in both entities, converted to the other entity's currency, so the two sides
  cannot differ. Consolidation removes the entries of the trade itself.
* **Asset sale to another entity** (``counterparty=other.bs.inventory`` or ``other.bs.fixed_asset``, with
  ``margin``, and ``used`` or ``life``; optionally ``settle`` or ``cash``): the seller books revenue and the buyer
  books the asset at the price. Only the ``revenue`` kind may do this, and ``recognize``, ``against`` and ``vat``
  are not allowed. The buyer's asset is named ``<name> (<seller>)``; the buyer's use of inventory becomes its ``cogs``,
  and the buyer's depreciation goes to the layout's depreciation expense.

With ``opening``, the default schedule assumes the earlier sales were steady: each earlier period sold the same
amount on the same terms. With kernel weights ``w[k]``, the share of a period's amount settled ``k`` periods later,
the balance outstanding after period ``j`` is ``T[j]``, the sum of ``w[k]`` for ``k > j``, and period ``j`` collects
``opening * T[j] / sum(T)``. ``settle=b.delay(2)`` collects half of ``opening`` in each of the first two periods.
``settle=b.delay(0)`` leaves nothing outstanding, so ``opening_collect`` is required. Opening balances of lines
with ``settle`` add up in the shared receivable (payable); do not declare ``co.bs.receivable("Accounts receivable",
opening=...)`` next to them.

See the `account and settlement table <{_DOCS}/api.md#pl-rows-japanese-gaap>`_, the `opening receivables guide
<{_DOCS}/api.md#opening-receivables-and-payables-opening-opening_collect>`_, `intercompany transactions
<{_DOCS}/entities-and-timeline.md#intercompany-transactions>`_, and `intercompany asset sales
<{_DOCS}/consolidation.md#s6-intercompany-asset-sales-and-unrealized-profits>`_.

Examples
--------
Revenue collected one month later, in a monthly model:

>>> import boki as b
>>> months = ["2027-01", "2027-02", "2027-03"]
>>> m = b.Model("Sales", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> sales = co.pl.revenue("Sales", 100, settle=b.delay(1))
>>> r = m.render()
>>> [round(r.value(sales, month)) for month in months]
[100, 100, 100]
>>> [round(r.value(co.bs.cash, month)) for month in months]
[0, 100, 200]

An amount per time is integrated by the length of each period, so a quarterly model books three months at once:

>>> from boki.units import JPY
>>> m = b.Model("Fees", start="2027-01", periods=2, step=3 * b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> fee = co.pl.revenue("Fee", 100 * JPY / b.month)
>>> r = m.render()
>>> [round(r.value(fee, quarter)) for quarter in ("2027-01", "2027-04")]
[300, 300]

An annual prepayment paid up front and recognized over three months:

>>> m = b.Model("Insurance", start="2027-01", periods=4, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> premium = co.pl.sga("Premium", {{0: 300}}, recognize=b.even(3))
>>> r = m.render()
>>> [round(r.value(premium, month)) for month in months + ["2027-04"]]
[100, 100, 100, 0]
>>> [round(r.value(co.bs.cash, month)) for month in months + ["2027-04"]]
[700, 700, 700, 700]

An opening receivable of 240 on terms of two months is collected half in each of the first two periods:

>>> m = b.Model("Opening", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> sales = co.pl.revenue("Sales", 100, settle=b.delay(2), opening=240)
>>> r = m.render()
>>> [round(r.value(co.bs.cash, month)) for month in months]
[120, 240, 340]

A subsidiary's sale to its parent is booked once and appears in both entities' books:

>>> m = b.Model("Group", start="2027-01", periods=2, step=b.month)
>>> parent = m.entity("Parent", standard=b.IFRS)
>>> sub = m.entity("Sub", standard=b.IFRS)
>>> parent.bs.opening(cash=1000)
>>> parts = sub.pl.revenue("Parts", 100, counterparty=parent.pl.cogs)
>>> r = m.render()
>>> round(r.value(parts, "2027-01")), round(r.value(parts.counterparty, "2027-01"))
(100, 100)
>>> parts.counterparty.kind
'cogs'
""")

INCOME_TAX = Template(f"""\
Add income tax on a base you choose, or a tax amount computed elsewhere.

The tax law's base is a modeling decision, so the base is an argument: give ``rate`` and ``base`` to compute the
tax with a loss carryforward, or give ``amount`` or ``data`` for a tax computed outside boki (brackets, minimum
taxes). The tax is booked as an expense paid in cash, or accrued and paid later with ``settle``.

Parameters
----------
name : str
    Line name; required. It must be unique among the lines of this kind in the entity.
amount : scalar, Quantity, Series, or dict, optional
    Tax amount in each period, in the entity's currency per period. When ``amount`` or ``data`` is given, ``rate``,
    ``base`` and ``nol`` are ignored. A dict maps period labels, indices, or dates to amounts and books 0 in the
    other periods.
rate : scalar, Series, or callable, optional
    Tax rate on the taxable profit, a dimensionless ratio such as ``0.3`` for 30%. A callable receives the taxable
    profit as a `Series` and returns the tax as a `Series`; use it for progressive brackets. Required with ``base``
    unless ``amount`` or ``data`` is given.
base : scalar or Series, optional
    Profit before tax and before loss carryforwards, in the entity's currency per period, such as
    ``co.pl.pretax_income``. A loss in a period adds to the carryforward unless ``nol`` is ``False``. Required with
    ``rate`` unless ``amount`` or ``data`` is given.
nol : bool or amount, default=True
    Loss carryforward. ``True`` starts the carryforward at zero, an amount in the entity's currency starts it with
    losses carried in from before the model, and ``False`` has no carryforward: the tax is ``rate`` times the base
    as it is, which is negative in a period of loss.
data : dict, optional
    Tax amounts for selected periods as ``{{period: amount}}``. Other periods book 0. It replaces ``amount`` when
    both are given.
settle : Kernel, optional
    How the tax is paid after the booking period. The tax accrues in the shared payable and is paid by the kernel
    weights, which must sum to 1.
actuals : dict, optional
    Historical tax amounts for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The tax expense line. When it was computed from ``rate`` and ``base`` with ``nol`` not ``False``, its ``nol``
    attribute holds the carryforward as ``balance`` (losses left at the end of each period), ``used`` (losses used
    against this period's profit), and ``taxable`` (the profit left after them).

Raises
------
TypeError
    At construction, if neither ``amount`` nor ``data`` is given and ``rate`` or ``base`` is missing, or an amount
    has a type boki cannot use in an expression.
ValueError
    At construction, if ``settle`` is not a distribution (weights that do not sum to 1, or a ``b.curve`` that
    does not end in 0), or an income tax line with this name already exists.
UnitError
    At construction, if an amount is in a unit other than the entity's currency.
IndexError
    At evaluation, if a period of ``amount`` or ``data`` is outside the model timeline.

Notes
-----
$metadata

With ``rate`` and ``base``, the tax in each period is ``rate`` times the taxable profit. The taxable profit is the
base if positive, less the losses carried forward, which are used up to the whole profit. A loss adds to the
carryforward and bears no tax. A callable ``rate`` is applied to this taxable profit, after the losses are used.

The tax is booked as an expense; to pay it later, ``settle`` accrues it in the shared payable (``Accounts payable``
before the standard renames it). Deferred taxes are separate: see ``co.bs.deferred_tax``.

See the `P&L rows table <{_DOCS}/api.md#pl-rows-japanese-gaap>`_ for the arguments in context.

Examples
--------
Tax at 30% of the profit before tax in a monthly model:

>>> import boki as b
>>> months = ["2027-01", "2027-02", "2027-03"]
>>> m = b.Model("Tax", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> sales = co.pl.revenue("Sales", 100)
>>> costs = co.pl.sga("Costs", 40)
>>> tax = co.pl.income_tax("Income tax", rate=0.3, base=co.pl.pretax_income)
>>> r = m.render()
>>> [round(r.value(tax, month)) for month in months]
[18, 18, 18]

A first-period loss shelters the profits that follow, and ``tax.nol`` reads the carryforward:

>>> m = b.Model("Losses", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> profit = m.series("Profit", data={{0: -100, 1: 60, 2: 80}})
>>> tax = co.pl.income_tax("Income tax", rate=0.25, base=profit)
>>> r = m.render()
>>> [round(r.value(tax, month)) for month in months]
[0, 0, 10]
>>> [round(r.value(tax.nol.balance, month)) for month in months]
[100, 40, 0]
""")

LINE = Template(f"""\
Add a balance-sheet line of this kind: an opening balance, a movement against cash, or a target balance.

The line's value is its closing balance in each period. Give ``amount`` to move the balance by a fixed amount in
each period (or once, with ``at``), ``target`` to hold the balance at a level and let cash absorb the difference,
or only ``opening`` to declare a balance that other entries move later.

Parameters
----------
name : str
    Line name; required. It must be unique among the lines of this kind in the entity.
amount : scalar, Quantity, Series, or dict, optional
    Change of the balance in each period, in the entity's currency per period; cash takes the other side. A
    positive amount raises an asset and lowers cash, and raises a liability or equity line and raises cash. A dict
    maps period labels, indices, or dates to amounts and books 0 in the other periods. A quantity per time is
    integrated by period length. It does not combine with ``target`` or ``data``.
at : int, str, or date, optional
    Period in which ``amount`` is booked, once. Without ``at``, ``amount`` is booked in every period.
data : dict, optional
    Changes of the balance for selected periods as ``{{period: amount}}``. It does not combine with ``amount`` or
    ``target``.
target : scalar, Quantity, Series, or dict, optional
    Closing balance to hold in each period, in the entity's currency. Cash absorbs the difference between the
    target and what other entries leave. It does not combine with ``amount`` or ``data``.
opening : scalar, Quantity, Series, or dict, optional
    Opening balance before the first period, in the entity's currency. Retained earnings balance it unless
    ``co.bs.opening`` states them.
cf : str, optional
    Cash-flow class of the line's cash movements: ``"operating"``, ``"investing"``, ``"financing"`` or ``"fx"``.
    The default is the cash-flow class of the kind.
tags : iterable of str, default=()
    Labels added to the account's tags, besides the tags of the kind. boki reads tags to recognize special accounts;
    most models do not need them.
counterparty : Entity, optional
    The other entity of the model that holds the opposite balance. It books a matching line named
    ``<name> (<this entity>)`` with the same opening balance, on the opposite side. It requires ``opening`` and does
    not take ``amount``, ``at``, ``data`` or ``target``.
actuals : dict, optional
    Historical closing balances for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The new line, valued at its closing balance. Its ``balance`` attribute is the same series, ``opening`` is the
    balance at the start of each period, and ``change`` is the movement.

Raises
------
TypeError
    At construction, if ``amount``, ``data`` and ``target`` are combined (any two of them); if ``counterparty`` is
    not an entity, lacks ``opening``, or is combined with ``amount``, ``at``, ``data`` or ``target``; or if an amount
    has a type boki cannot use in an expression.
ValueError
    At construction, if a line with this name already exists for this kind, ``cf`` is not a cash-flow class, or
    ``counterparty`` is this entity or belongs to another model.
UnitError
    At construction, if an amount is in a unit other than the entity's currency.
IndexError
    At evaluation, if ``at`` or a period of ``amount``, ``data``, ``target`` or ``opening`` is outside the model
    timeline.

Notes
-----
$metadata

An asset moves with a debit to the line and a credit to cash, and a liability or equity line moves with a debit to
cash and a credit to the line; a negative amount reverses the entry. ``target`` posts whatever cash movement makes
the line close at the target after the line's other entries. The opposite balance of a ``counterparty`` has the
paired kind where the layout has one: ``receivable`` and ``payable``, and ``other_current_asset`` and
``other_current_liability`` pair with each other; any other kind pairs with ``other_liability`` or ``other_asset``.

Kinds whose mechanism is not a plain line use another template: fixed assets, construction in progress, loans,
capital, and dividends.

See the `balance-sheet rows <{_DOCS}/api.md#bs-rows>`_ and `opening balances with a counterparty
<{_DOCS}/consolidation.md#s7-opening-balances-at-model-start-all-supplied-by-the-user>`_.

Examples
--------
Hold receivables at half of each month's sales, starting from an opening balance of 30:

>>> import boki as b
>>> months = ["2027-01", "2027-02", "2027-03"]
>>> m = b.Model("Receivables", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> sales = co.pl.revenue("Sales", 100)
>>> receivable = co.bs.receivable("Receivable", target=sales * 0.5, opening=30)
>>> r = m.render()
>>> [round(r.value(receivable, month)) for month in months]
[50, 50, 50]
>>> [round(r.value(co.bs.cash, month)) for month in months]
[1080, 1180, 1280]

Book a deposit once, in the second month, with ``at``:

>>> m = b.Model("Deposit", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> deposit = co.bs.deposit("Deposit", 20, at="2027-02")
>>> r = m.render()
>>> [round(r.value(deposit, month)) for month in months]
[0, 20, 20]
""")

FIXED_ASSET = Template(f"""\
Add a fixed asset bought with cash and depreciated, optionally sold at its carrying amount.

The line's value is the asset's carrying amount (book value) at the end of each period. The depreciation expense is
booked as a separate PL line named ``<name> depreciation``, and its credit reduces the asset.

Parameters
----------
name : str
    Asset name; required. It must be unique among the lines of this kind in the entity.
cost : scalar, Quantity, Series, or dict, optional
    Purchase price in the entity's currency per period. With ``at``, a single purchase in that period. Without ``at``,
    the spend of each period, which is a capex program when it is a `Series` or a dict: each period's spend is
    depreciated on its own, from the next period.
at : int, str, or date, optional
    Period of the purchase. Depreciation starts in the period after it.
life : Quantity or Unit, optional
    Useful life as a time such as ``5 * b.year``. It is required unless ``depreciation`` is given, and must be
    positive.
method : str, default="straight"
    ``"straight"`` for straight-line depreciation of the cost less ``salvage`` over ``life``, or ``"ddb"`` for
    double-declining balance on the opening carrying amount. Depreciation never takes the carrying amount below
    ``salvage``. A capex program accepts only ``"straight"``.
salvage : scalar, Quantity, or Series, default=0
    Residual value in the entity's currency that depreciation does not go below. A capex program needs 0.
sell_at : int, str, or date, optional
    Period in which the asset is sold at its carrying amount after that period's depreciation: the cash received
    equals the carrying amount, so there is no gain or loss.
depreciation : scalar, Quantity, Series, or dict, optional
    Depreciation expense in each period, in the entity's currency per period. It replaces the computed schedule, so
    ``at`` and ``life`` are not needed.
opening : scalar, Quantity, Series, or dict, optional
    Opening carrying amount before the first period, in the entity's currency. To depreciate an asset that only has
    an opening balance, give ``depreciation``, or ``at`` and ``life``.
category : str, default="Depreciation expense"
    Label stored as ``LineItem.category`` on the depreciation expense line.
actuals : dict, optional
    Historical carrying amounts for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The asset line, valued at its carrying amount. Its ``balance`` attribute is the same series, and its
    ``depreciation`` attribute is the depreciation expense line.

Raises
------
TypeError
    At construction, if ``depreciation`` is not given and ``life`` is missing, or ``at`` and ``cost`` are both
    missing; if a capex program has a constant ``cost``, a ``method`` other than ``"straight"``, a nonzero
    ``salvage``, or periods of different lengths; or if an amount has a type boki cannot use in an expression.
ValueError
    At construction, if a line with this name already exists for this kind, or ``life`` is not positive, or a capex
    program's ``life`` is not a whole number of periods. At evaluation, if ``method`` is not ``"straight"`` or
    ``"ddb"``.
UnitError
    At construction, if an amount is in a unit other than the entity's currency, or ``life`` is not a time.
IndexError
    At evaluation, if ``at``, a period of ``cost``, or ``sell_at`` given as a label or date is outside the model
    timeline.

Notes
-----
$metadata

The purchase debits the asset and credits cash. The expense goes to the layout's depreciation kind (selling, general
and administrative expenses in the general layouts) and is counted by ``co.depreciation``, or by ``co.amortization``
for the ``intangible`` kind. Straight-line depreciation takes the carrying amount at ``at`` less ``salvage``, times
the period length over ``life``; double-declining balance takes twice that rate of the opening carrying amount.

See the `fixed asset row <{_DOCS}/api.md#bs-rows>`_ and the `depreciation measures
<{_DOCS}/api.md#ebitda-and-its-relatives>`_.

Examples
--------
A machine bought in the first year and depreciated over five years in an annual model:

>>> import boki as b
>>> m = b.Model("Machine", start="2027-01", periods=3, step=b.year)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> machine = co.bs.fixed_asset("Machine", cost=500, at=0, life=5 * b.year)
>>> r = m.render()
>>> [round(r.value(machine, year)) for year in ("2027", "2028", "2029")]
[500, 400, 300]
>>> [round(r.value(machine.depreciation, year)) for year in ("2027", "2028", "2029")]
[0, 100, 100]

In a monthly model the same life is twelve times as many periods; depreciation is a twelfth of a year each month:

>>> m = b.Model("Machine", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> machine = co.bs.fixed_asset("Machine", cost=600, at=0, life=1 * b.year)
>>> r = m.render()
>>> [round(r.value(machine.depreciation, month)) for month in ("2027-01", "2027-02", "2027-03")]
[0, 50, 50]
""")

LOAN = Template(f"""\
Add a borrowing with interest and repayment entries.

The line's value is the loan balance at the end of each period. Interest is the rate times the opening balance and is
expensed in the layout's interest kind unless it is capitalized. Draws and repayments move cash.

Parameters
----------
name : str
    Loan name; required. It must be unique among the lines of this kind in the entity.
draw : scalar, Quantity, Series, or dict, optional
    Amount drawn, in the entity's currency per period. A dict maps period labels or indices to amounts and draws 0
    in the other periods.
rate : scalar, Quantity, or Series, default=0
    Interest rate, dimensionless per period: ``0.01`` is 1% of the opening balance in each period, whether the
    period is a month or a year. A rate per time, such as ``0.12 / b.year``, is integrated by period length.
    ``None`` books no interest.
repay : scalar, Quantity, Series, dict, or callable, optional
    Amount repaid, in the entity's currency per period, never more than the opening balance. A dict maps period
    labels or indices to amounts; a callable receives this loan and returns the repayment.
opening : scalar, Quantity, Series, or dict, optional
    Opening loan balance before the first period, in the entity's currency.
target : scalar, Quantity, Series, or dict, optional
    Closing balance to hold in each period, in the entity's currency. Leave ``draw`` and ``repay`` unset when giving
    it.
capitalize_during : bool or Series, optional
    Periods in which interest is capitalized instead of expensed: a condition that is true in those periods. It does
    not combine with ``counterparty``.
capitalize_into : LineItem, optional
    The ``construction`` line of this entity that receives the capitalized interest. Requires ``capitalize_during``.
    Without it, capitalized interest goes to a shared construction-in-progress account that is never depreciated.
counterparty : Entity, optional
    The lender, another entity of the same model. It books the matching loan receivable, the draws and repayments,
    and the interest as income. It does not combine with ``target`` or ``capitalize_during``.
net_investment : bool, default=False
    Treat a loan to a lender with another functional currency as part of the net investment, which sends the
    exchange difference to other comprehensive income in consolidation. Requires ``counterparty``.
actuals : dict, optional
    Historical closing balances for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The loan line, valued at its closing balance. Its ``interest``, ``principal`` and ``draw`` attributes are the
    interest on the opening balance, the repayment actually made, and the draw; ``interest_expense`` is the interest
    expensed and ``capitalized_interest`` the interest capitalized. ``draw_or_repay(amount)`` borrows (positive) or
    repays (negative) an extra amount in each period.

Raises
------
TypeError
    At construction, if ``net_investment`` is not a bool or is given without ``counterparty``; if ``target`` is
    combined with ``draw`` or ``repay``; if ``counterparty`` is not an entity or is combined with ``target`` or
    ``capitalize_during``; if ``capitalize_into`` lacks ``capitalize_during`` or is not a ``construction`` line of
    this entity; or if an amount has a type boki cannot use in an expression.
ValueError
    At construction, if a loan with this name already exists, ``counterparty`` is this entity or belongs to another
    model, or the lender's layout has no income kind for interest or foreign-exchange differences.
UnitError
    At construction, if an amount is in a unit other than the entity's currency.
IndexError
    At evaluation, if a period of ``draw``, ``repay``, ``opening`` or ``target`` is outside the model timeline.

Notes
-----
$metadata

A draw debits cash and credits the loan; a repayment debits the loan and credits cash. Interest is calculated on the
opening balance. Without ``capitalize_during`` it is expensed. With it, interest in the selected periods is capitalized
into a shared construction-in-progress account, which is never depreciated, or with ``capitalize_into`` into the cost
of that construction line, which depreciates it after completion. See the `loans section
<{_DOCS}/double-entry.md#loans>`_ and the `consolidation guide for loans between entities
<{_DOCS}/consolidation.md#s8-entities-with-different-currencies>`_.

Examples
--------
Use a monthly model to see a per-time rate integrated over each month:

>>> import boki as b
>>> m = b.Model("Loan", start="2027-01", periods=2, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> loan = co.bs.loan("Term loan", draw={{0: 100}}, rate=0.12 / b.year)
>>> r = m.render()
>>> round(r.value(loan.interest, "2027-02"), 8)
1.0
""")

CONSTRUCTION = Template(f"""\
Add construction in progress, depreciated straight-line once it is complete.

The line's value is the balance at the end of each period: the opening balance, the spend, and any capitalized
interest, less depreciation after completion. Without ``complete_at`` the balance stays in construction in progress.

Parameters
----------
name : str
    Asset name; required. It must be unique among the lines of this kind in the entity.
spend : scalar, Quantity, Series, or dict
    Spend in each period, in the entity's currency per period; cash pays it. A dict maps period labels, indices, or
    dates to amounts and spends 0 in the other periods.
complete_at : int, str, or date, optional
    Period in which construction completes. Depreciation starts in this period, on the balance at the end of the
    period before it.
life : Quantity or Unit, optional
    Useful life from completion as a time such as ``5 * b.year``; required with ``complete_at``, and must be
    positive.
opening : scalar, Quantity, Series, or dict, optional
    Opening balance before the first period, in the entity's currency.
category : str, default="Depreciation expense"
    Label stored as ``LineItem.category`` on the depreciation expense line.
actuals : dict, optional
    Historical carrying amounts for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The construction line, valued at its balance. Its ``balance`` attribute is the same series; with ``complete_at``,
    its ``depreciation`` attribute is the depreciation expense line.

Raises
------
TypeError
    At construction, if ``complete_at`` is given without ``life``, or an amount has a type boki cannot use in an
    expression.
ValueError
    At construction, if a line with this name already exists for this kind or ``life`` is not positive.
UnitError
    At construction, if an amount is in a unit other than the entity's currency, or ``life`` is not a time.
IndexError
    At evaluation, if ``complete_at`` given as a label or date, or a period of ``spend``, is outside the model
    timeline.

Notes
-----
$metadata

Spending debits the line and credits cash. Depreciation after completion is the balance at the end of the period
before ``complete_at``, times the period length over ``life``, never more than the balance, and is booked in the
layout's depreciation kind, which ``co.depreciation`` counts. Interest from ``co.bs.loan`` can be added to the
cost with ``capitalize_into``. See the `construction row <{_DOCS}/api.md#bs-rows>`_.

Examples
--------
Spend 100 in each of the first two months, complete the asset in the third, and depreciate it over a year:

>>> import boki as b
>>> m = b.Model("Plant", start="2027-01", periods=4, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> plant = co.bs.construction("Plant", {{0: 100, 1: 100}}, complete_at=2, life=1 * b.year)
>>> r = m.render()
>>> [round(r.value(plant, month), 2) for month in ("2027-01", "2027-02", "2027-03", "2027-04")]
[100.0, 200.0, 183.33, 166.67]
""")

CAPITAL = Template(f"""\
Add an equity line such as share capital, paid in against cash or by another entity.

The line's value is its balance at the end of each period. ``amount`` raises it and cash, and a negative amount
reduces it. With ``counterparty``, another entity of the model pays the capital and books the shares it holds.

Parameters
----------
name : str
    Line name; required. It must be unique among the lines of this kind in the entity.
amount : scalar, Quantity, Series, or dict, optional
    Capital paid in each period, in the entity's currency per period. A dict maps period labels, indices, or dates
    to amounts and books 0 in the other periods. With ``counterparty`` it is required unless ``opening`` is given.
at : int, str, or date, optional
    Period in which ``amount`` is booked, once. Without ``at``, ``amount`` is booked in every period.
opening : scalar, Quantity, Series, or dict, optional
    Opening balance before the first period, in the entity's currency. With ``counterparty`` it also opens the
    owner's shares at the same amount and does not combine with ``amount``, ``at`` or ``fx_rate``.
cf : str, optional
    Cash-flow class of the cash movements: ``"operating"``, ``"investing"``, ``"financing"`` or ``"fx"``. The default
    is the cash-flow class of the kind.
counterparty : Entity, optional
    The owner that pays the capital, another entity of the same model. It books the shares it holds
    (``<this entity> shares``, an asset) against the cash it pays, and consolidation eliminates both.
fx_rate : scalar, Quantity, or Series, optional
    Exchange rate on the transaction date, used to translate the amount into the owner's currency: owner currency per
    unit of this entity's currency. Without it, the period average is used. Requires ``counterparty``, and has no
    effect when both entities have the same currency.
actuals : dict, optional
    Historical closing balances for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The capital line, valued at its balance. With ``counterparty``, its ``counterparty`` attribute is the owner's
    shares line.

Raises
------
TypeError
    At construction, if ``fx_rate`` is given without ``counterparty``; if ``counterparty`` is not an entity, is given
    without ``amount`` or ``opening``, or ``opening`` is combined with ``amount``, ``at`` or ``fx_rate``; or if an
    amount has a type boki cannot use in an expression.
ValueError
    At construction, if a line with this name already exists for this kind, ``cf`` is not a cash-flow class, or
    ``counterparty`` is this entity or belongs to another model.
UnitError
    At construction, if an amount is in a unit other than the entity's currency, or ``fx_rate`` is not quoted in owner
    currency per unit of this entity's currency.
IndexError
    At evaluation, if ``at`` or a period of ``amount`` is outside the model timeline.
CheckFailed
    At evaluation, if ``fx_rate`` is not positive and the entities have different currencies; ``render(checks="warn")``
    only warns.

Notes
-----
$metadata

The line is paid in by a debit to cash and a credit to the line. With ``counterparty``, the owner debits its shares
and credits cash for the translated amount. The shares line is created on the first use and reused. See the
`equity section <{_DOCS}/double-entry.md#equity>`_ and the `intercompany capital transactions
<{_DOCS}/consolidation.md#s8-entities-with-different-currencies>`_.

Examples
--------
Capital of 1,000 paid in the first month of a monthly model:

>>> import boki as b
>>> m = b.Model("Capital", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> capital = co.bs.capital("Share capital", 1000, at=0)
>>> r = m.render()
>>> [round(r.value(capital, month)) for month in ("2027-01", "2027-02", "2027-03")]
[1000, 1000, 1000]
>>> round(r.value(co.bs.cash, "2027-03"))
1000

A subsidiary's capital paid in by its parent appears as shares in the parent's books:

>>> m = b.Model("Group", start="2027-01", periods=2, step=b.month)
>>> parent = m.entity("Parent", standard=b.IFRS)
>>> sub = m.entity("Sub", standard=b.IFRS)
>>> parent.bs.opening(cash=500)
>>> paid = sub.bs.capital("Capital", 200, at=0, counterparty=parent)
>>> r = m.render()
>>> round(r.value(parent.bs.cash, "2027-01")), round(r.value(paid.counterparty, "2027-01"))
(300, 200)
""")

DIVIDEND = Template(f"""\
Add a dividend paid out of retained earnings, optionally to another entity of the model.

The line's value is the amount paid in each period, not a balance. The dividend debits retained earnings and credits
cash. With ``counterparty``, the owner books the dividend as income.

Parameters
----------
name : str
    Line name; required.
amount : scalar, Quantity, Series, or dict
    Dividend paid in each period, in the entity's currency per period. A dict maps period labels, indices, or dates
    to amounts and pays 0 in the other periods.
counterparty : Entity, optional
    The owner that receives the dividend, another entity of the same model. It books the dividend, translated into
    its currency, as finance or other income, and consolidation eliminates both sides.
fx_rate : scalar, Quantity, or Series, optional
    Exchange rate on the transaction date, used to translate the dividend into the owner's currency: owner currency per
    unit of this entity's currency. Without it, the period average is used. Requires ``counterparty``, and has no
    effect when both entities have the same currency.
actuals : dict, optional
    Historical dividend payments for periods up to ``Model.actual_until``, as ``{{period: amount}}``. Requires
    ``Model(..., actual_until=...)``.

Returns
-------
LineItem
    The dividend line, valued at the amount paid in each period. With ``counterparty``, its ``counterparty``
    attribute is the owner's income line.

Raises
------
TypeError
    At construction, if ``fx_rate`` is given without ``counterparty``, ``counterparty`` is not an entity, or an
    amount has a type boki cannot use in an expression.
ValueError
    At construction, if ``counterparty`` is this entity or belongs to another model, the owner's layout has no
    income kind for dividends, or the owner already has an income line named ``<name> (<this entity>)``.
UnitError
    At construction, if an amount is in a unit other than the entity's currency, or ``fx_rate`` is not quoted in owner
    currency per unit of this entity's currency.
IndexError
    At evaluation, if a period of ``amount`` is outside the model timeline.
CheckFailed
    At evaluation, if ``fx_rate`` is not positive and the entities have different currencies; ``render(checks="warn")``
    only warns.

Notes
-----
$metadata

The dividend reduces retained earnings, not the line, so the line is a flow and has no balance. The owner's income
is booked in the first of ``finance_income``, ``non_operating_income``, ``other_income`` and ``interest_income``
that its layout has. See the `equity section <{_DOCS}/double-entry.md#equity>`_ and the `intercompany dividends
<{_DOCS}/consolidation.md#s8-entities-with-different-currencies>`_.

Examples
--------
Pay a dividend of 30 in each month of a monthly model:

>>> import boki as b
>>> m = b.Model("Dividend", start="2027-01", periods=3, step=b.month)
>>> co = m.entity("A", standard=b.IFRS)
>>> co.bs.opening(cash=1000)
>>> dividend = co.bs.dividend("Dividend", 30)
>>> r = m.render()
>>> [round(r.value(co.bs.cash, month)) for month in ("2027-01", "2027-02", "2027-03")]
[970, 940, 910]

A subsidiary's dividend is income of its parent:

>>> m = b.Model("Group", start="2027-01", periods=2, step=b.month)
>>> parent = m.entity("Parent", standard=b.IFRS)
>>> sub = m.entity("Sub", standard=b.IFRS)
>>> sub.bs.opening(cash=100)
>>> paid = sub.bs.dividend("Dividend", 40, counterparty=parent)
>>> r = m.render()
>>> round(r.value(parent.pl.finance_income.total, "2027-01"))
40
""")

TEMPLATES: dict[str, Template] = {
    "pl_line": PL_LINE,
    "income_tax": INCOME_TAX,
    "line": LINE,
    "fixed_asset": FIXED_ASSET,
    "loan": LOAN,
    "construction": CONSTRUCTION,
    "capital": CAPITAL,
    "dividend": DIVIDEND,
}

_GENERIC_METADATA = (
    "The documentation of each maker starts this section with the maker's kind, its side, and the section and "
    "cash-flow class of the kind; the layout pages list them."
)


def _article(word: str) -> str:
    return "an" if word[0] in "aeiou" else "a"


def kind_metadata(layout: Layout, kind: Kind) -> str:
    """One sentence about a kind: its side, its place in the layout, and its cash-flow class."""
    subject = f"``{kind.name}`` is {_article(kind.side)} {kind.side} kind of the {layout.name} layout"
    if kind.mechanism == "pl":
        later = layout.pl[layout.pl.index(kind) + 1:]
        subtotal = next((item.name for item in later if not isinstance(item, Kind)), None)
        return subject + (f", listed before the ``{subtotal}`` subtotal." if subtotal else ".")
    section = f", in the ``{kind.section}`` section" if kind.section else ""
    return f"{subject}{section}. Its cash-flow class is ``{kind.cf}``."


def maker_doc(key: str, layout: Layout | None = None, kind: Kind | None = None) -> str:
    """The numpydoc text of the template ``key``; with a layout and kind, the sentence about that kind is filled in."""
    if key not in TEMPLATES:
        raise KeyError(f"no maker doc template {key!r}; templates: {', '.join(TEMPLATES)}")
    if (layout is None) != (kind is None):
        raise TypeError("give both layout and kind, or neither")
    metadata = _GENERIC_METADATA if kind is None else kind_metadata(layout, kind)
    return TEMPLATES[key].substitute(metadata=metadata)
