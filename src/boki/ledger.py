"""Entities, accounts and the double-entry ledger behind line items.

Users create line items from `entity.pl.<kind>(...)` and `entity.bs.<kind>(...)`. Each
item posts balanced entries (amount series, debit account, credit account). Balances,
the three statements and their consistency all derive from those postings.
"""
from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, NamedTuple

from . import evaluator
from ._maker_docs import maker_doc
from .layouts import IFRS, JGAAP, USGAAP, Kind, Layout, Standard  # noqa: F401  (re-exported)
from .shapes import Kernel, _check_kernel_distribution
from .series import Const, Data, Fn, Named, Series, lift, smax, smin
from .units import _DIMENSIONLESS, Dims, Unit, UnitError, _describe

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ._makers import GeneralBS, GeneralPL
    from .model import Model
    from .statements import Fiscal
    from .units import Quantity

MONTH_DIM = ("month", -1)


# ---- accounts not owned by a layout ----------------------------------------------

# Accounts that `settle=`, `recognize=`, `cash=` and `capitalize_during=` open on demand.
SHARED = {
    "receivable": ("asset", "operating", "Accounts receivable"),
    "payable": ("liability", "operating", "Accounts payable"),
    "deferred_revenue": ("liability", "operating", "Deferred revenue"),
    "prepaid": ("asset", "operating", "Prepaid expenses"),
    "construction": ("asset", "investing", "Construction in progress (capitalized interest)"),
    "vat": ("liability", "operating", "VAT payable (net)"),
}
CF_CLASSES = ("operating", "investing", "financing", "fx")
AUTOMATIC_NAMES = {"cash": "Cash", "retained_earnings": "Retained earnings"} | {k: v[2] for k, v in SHARED.items()}
SUBSIDIARY_INVESTMENT = "subsidiary_investment"
ACQUISITION_CLEARING = "acquisition_clearing"
# Tags on the PL account that holds an asset's depreciation: how Entity.depreciation and
# Entity.amortization find the expense wherever it is posted.
DEPRECIATION = "depreciation"
AMORTIZATION = "amortization"


# ---- accounts and postings -------------------------------------------------------

@dataclass(eq=False)
class Account:
    entity: "Entity"
    name: str
    side: str                    # asset / liability / equity / income / expense
    kind: str                    # a PL kind ("sga") or a BS kind ("loan")
    cf: str                      # operating / investing / financing / cash / pl
    category: str | None = None
    tags: frozenset = frozenset()
    opening: Series | None = None             # balance before the first period, on the normal side
    actuals: Series | None = None             # historical balances in periods <= model.actual_until
    mirror: "Account | None" = None           # opening balance recorded by the counterparty
    debits: list["Posting"] = field(default_factory=list)
    credits: list["Posting"] = field(default_factory=list)

    def __repr__(self):
        return f"<Account {self.entity.name}:{self.name}>"


@dataclass(eq=False)
class Posting:
    name: str
    amount: Series
    debit: Account
    credit: Account
    cf: str | None = None                     # overrides the cash-flow class of a cash posting
    counterparty: "Entity | None" = None      # the other entity of a trade booked with counterparty=
    asset_trade: _AssetTrade | None = None
    fx_remeasurement: bool = False
    net_investment: bool = False
    intercompany_trade: "_IntercompanyTrade | None" = None
    counterpart: "Posting | None" = None
    fx_rate: Series | None = None
    da: str | None = None                     # DEPRECIATION or AMORTIZATION when this posting alone is one


class _Flow(Series):
    """Net debit movement of an account in a period (debits minus credits)."""

    def __init__(self, account: Account):
        self.account = account
        self.name = f"{account.name} (movement)"

    def _eval(self, r, t):
        total = 0.0
        for p in self.account.debits:
            total += r.value(p.amount, None if p.amount.scalar else t) or 0
        for p in self.account.credits:
            total -= r.value(p.amount, None if p.amount.scalar else t) or 0
        return total


class _Balance(Series):
    """Closing balance, positive on the account's normal side."""

    def __init__(self, account: Account, sign: int, name: str | None = None):
        self.account, self.sign = account, sign
        self.flow = _Flow(account)
        self.name = name or account.name

    @property
    def unit(self):  # the books' currency is known once the first amount is posted
        return self.account.entity._currency

    @property
    def opening(self) -> Series:
        """The previous period's closing balance (the declared opening balance in the first period)."""
        if not hasattr(self, "_opening"):
            self._opening = _Opening(self)
        return self._opening

    @property
    def change(self) -> Series:
        return self - self.opening

    def start(self, r) -> float:
        o = self.account.opening
        return 0.0 if o is None else r.value(o, None if o.scalar else 0)

    def _eval(self, r, t):
        actual_until = self.account.entity.model.actual_until
        if actual_until is not None and t <= actual_until:
            if self.account.actuals is not None:
                return r.value(self.account.actuals, t) or 0.0
            return 0.0
        prev = r.value(self, t - 1) if t > 0 else self.start(r)
        return prev + self.sign * r.value(self.flow, t)


class _Opening(Series):
    """A balance at the start of each period. Reads the account's opening when evaluated, so an opening
    declared after this node was built still counts."""

    def __init__(self, balance: _Balance):
        self.balance = balance
        self.name = f"{balance.name} (opening)"

    @property
    def unit(self):
        return self.balance.unit

    def _eval(self, r, t):
        return r.value(self.balance, t - 1) if t > 0 else self.balance.start(r)


class _Total(Series):
    """Sum of a dynamic list of series (items added later are included)."""

    def __init__(self, items: Callable[[], list[Series]], name: str, entity: "Entity | None" = None):
        self.items, self.name, self._entity = items, name, entity

    @property
    def unit(self):
        units = {s.unit for s in self.items() if s.unit is not None}
        if len(units) > 1:
            raise UnitError(f"{self.name} mixes {', '.join(_describe(u) for u in units)}")
        if units:
            return units.pop()
        return self._entity._currency if self._entity is not None else None

    def _eval(self, r, t):
        return sum(r.value(s, None if s.scalar else t) or 0 for s in self.items())


def stock_kind(node) -> bool | str:
    """How a fiscal-year table groups a node: True for a closing balance (or a total of balances), "first"
    for an opening balance, False for a flow."""
    if isinstance(node, Named):
        return stock_kind(node.expr) if isinstance(node.expr, Series) else False
    if isinstance(node, _Opening):
        return "first"
    if isinstance(node, (_Balance, _SideTotal, _EquityTotal)):
        return True
    if isinstance(node, _Total):
        kinds = {stock_kind(item) for item in node.items()}
        return kinds.pop() if len(kinds) == 1 else False
    return False


# ---- line items ------------------------------------------------------------------

class LineItem(Named):
    """Series that is one line of an entity's statements: its name, kind, and the account that holds it.

    A line item is what ``co.pl.<kind>(...)`` and ``co.bs.<kind>(...)`` return. It is a `Series`, so it supports all
    the operations of one (arithmetic, ``lag``, ``sum``, ...), and it also knows which entity, accounting standard
    and kind it belongs to. Its value is a flow for a profit-and-loss kind (the amount recognized in each period) and
    a closing balance for a balance-sheet kind; the template of the kind says which. The line's amounts were posted
    to the entity's double-entry books when it was created, so a line cannot be changed afterwards.

    Parameters
    ----------
    name : str
        Name of the line, unique among the lines of its kind in the entity.
    expr : Series
        The values of the line: its flow, or the closing balance of its account.
    entity : Entity
        The entity whose books hold the line.
    kind : str
        Name of the layout kind, such as ``"revenue"`` or ``"loan"``.
    account : Account
        The ledger account the line reads. Internal.
    category : str | None
        Free-text label that groups lines in totals, such as ``"Products"``. ``None`` means no label.

    Attributes
    ----------
    name : str
        Name of the line, as it appears in statements.
    kind : str
        Name of the layout kind, as in ``co.pl.<kind>``.
    entity : Entity
        The entity whose books hold the line.
    standard : Standard
        The accounting standard of the entity.
    layout : Layout
        The layout of the entity's statements.
    category : str or None
        Label given at creation. ``LineMaker.total_of(category=...)`` totals the lines that share one.
    counterparty : LineItem or None
        For a trade with another entity (``counterparty=`` on the maker), the same trade in the other entity's books;
        otherwise ``None``. The link is symmetric.
    unit : frozenset or None
        Dimensions of the line's values, as for any series. ``None`` while the entity's currency is not yet known.
    balance : Series
        Closing balance of the line in each period, on most balance-sheet lines (``co.bs.<kind>``). For most kinds it
        has the same values as the line itself.
    depreciation : LineItem
        Depreciation expense of the asset, on fixed-asset lines, as a line of the layout's depreciation kind. On
        construction lines, only when ``complete_at=`` was given.
    draw : Series
        Amount drawn in each period, on loans: the ``draw=`` argument.
    interest : Series
        Interest accrued in each period, on loans: the rate times the opening balance. A rate per time is integrated
        by the period length. With a rate, it is the sum of ``interest_expense`` and ``capitalized_interest``; with
        ``rate=None`` it is 0 and no interest line is booked.
    principal : Series
        Principal repaid in each period, on loans: the ``repay=`` amount, never more than the opening balance.
    interest_expense : LineItem
        The part of the interest booked as expense, on loans: a line of the layout's interest kind (with
        ``rate=None``, the zero interest series).
    capitalized_interest : Series
        The part of the interest added to construction in progress instead of expense, on loans; 0 without
        ``capitalize_during=``.
    nol : NOL
        Loss carryforward of an income tax line computed from ``rate=`` and ``base=``: a named tuple with ``balance``,
        ``used`` and ``taxable`` series. Absent with ``nol=False`` or when the amount was given.

    See Also
    --------
    boki.LineMaker : Creates the lines of one kind and totals them.
    boki.series.Named : The series type that line items extend.

    Notes
    -----
    Only the line makers create line items, so user code never constructs one. A line also exists for the other side
    of a trade, such as the buyer's cost for a seller's revenue; read it from ``counterparty``. What each kind posts,
    and which attributes it has, is documented with the maker of the kind. The `double-entry bookkeeping
    <https://github.com/combinatrix-ai/boki/blob/master/docs/double-entry.md>`_ note explains the postings.

    Examples
    --------
    A loan drawn in the first month, repaid in the last two, with interest of 12% a year on the opening balance:

    >>> import boki as b
    >>> m = b.Model("Loan", start="2027-01", periods=4, step=b.month)
    >>> co = m.entity("Co", standard=b.IFRS)
    >>> co.bs.opening(cash=1000)
    >>> loan = co.bs.loan("Bank loan", draw={0: 600}, rate=0.12 / b.year, repay={2: 100, 3: 100})
    >>> r = m.render()
    >>> r[loan]
    [600.0, 600.0, 500.0, 400.0]
    >>> [round(v, 2) for v in r[loan.interest]]
    [0.0, 6.0, 6.0, 5.0]
    >>> r[loan.principal]
    [0, 0, 100, 100]
    >>> loan.kind, loan.entity is co, loan.layout.name
    ('loan', True, 'IFRS general')

    Revenue lines carry a category and are totalled by the maker:

    >>> m = b.Model("Sales", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("Co", standard=b.IFRS)
    >>> product = co.pl.revenue("Product", 100, category="Products")
    >>> service = co.pl.revenue("Service", 40, category="Services")
    >>> r = m.render()
    >>> r.value(co.pl.revenue.total_of(category="Services"), "2027-02")
    40
    """  # noqa: DOC602, DOC603

    def __init__(self, name: str, expr: Series, entity: "Entity", kind: str, account: Account,
                 category: str | None = None):
        super().__init__(name, expr)
        self.entity, self.standard, self.layout, self.kind = entity, entity.standard, entity.layout, kind
        self.account, self.category = account, category
        self.counterparty: "LineItem | None" = None   # the same trade in the other entity's books

    @property
    def opening(self) -> Series:
        """Value at the start of each period: the previous period's closing balance of a balance-sheet line.

        Returns
        -------
        Series
            For a balance-sheet line, the previous period's closing balance, which in the first period is the opening
            balance declared for the line (``opening=``, or 0). For a profit-and-loss line it is the previous period's
            value, 0 before the first period, as for any `Series`.

        See Also
        --------
        boki.Series.opening : The same for a plain series.
        boki.LineItem.change : This period's value minus the opening.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Deposit", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("Co", standard=b.IFRS)
        >>> co.bs.opening(cash=800, retained_earnings=1000)
        >>> deposit = co.bs.asset("Deposit", opening=200)
        >>> r = m.render()
        >>> [float(v) for v in r[deposit.opening]]
        [200.0, 200.0, 200.0]
        """
        return self.expr.opening if isinstance(self.expr, _Balance) else Series.opening.fget(self)

    @property
    def change(self) -> Series:
        """Change during each period: the closing value minus the opening.

        Returns
        -------
        Series
            This period's value minus ``opening``. For a balance-sheet line it is the movement of the balance in the
            period; for a flow it is the change from the previous period.

        See Also
        --------
        boki.LineItem.opening : The value at the start of each period.

        Examples
        --------
        The movement of a loan balance:

        >>> import boki as b
        >>> m = b.Model("Loan", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("Co", standard=b.IFRS)
        >>> co.bs.opening(cash=1000)
        >>> loan = co.bs.loan("Bank loan", draw={0: 600}, repay={2: 100})
        >>> r = m.render()
        >>> r[loan.change]
        [600.0, 0.0, -100.0]
        """
        return self - self.opening

    def __repr__(self):
        return f"<{self.kind} {self.entity.name}:{self.name}>"


@dataclass
class _OCIComponent:
    name: str
    account: Account
    recycle: bool
    taxed: bool
    amounts: list[Series] = field(default_factory=list)
    tax_basis: list[Series] = field(default_factory=list)
    line: LineItem | None = None
    tax_rate: Series | None = None
    tax_asset: Account | None = None
    tax_liability: Account | None = None


@dataclass(eq=False)
class _AssetTrade:
    seller: "Entity"
    buyer: "Entity"
    name: str
    asset_kind: str
    price: Series
    profit: Series
    buyer_item: LineItem
    used: Kernel | None = None
    depreciation: Series | None = None
    realization: Series | None = None
    life_months: int | None = None
    seller_asset: Account | None = None
    gain_account: Account | None = None
    loss_account: Account | None = None
    source: str = "product"
    _postings: tuple[Posting, ...] = ()
    buyer_price: Series | None = None


@dataclass(eq=False)
class _IntercompanyTrade:
    seller: "Entity"
    buyer: "Entity"
    name: str
    seller_amount: Series
    buyer_amount: Series
    _postings: tuple[Posting, ...]


class _AssetTradeFlow(Series):
    """A straight-line flow for each asset trade cohort, starting in its transfer period."""

    def __init__(self, model, basis: Series, life_months: int, name: str):
        self.model, self.basis, self.life_months, self.name = model, basis, life_months, name

    @property
    def unit(self):
        return self.basis.unit

    def _eval(self, r, t):
        total = 0
        for start in range(t + 1):
            elapsed = sum(self.model.timeline.periods[i].months for i in range(start, t))
            months = min(self.model.timeline.periods[t].months, self.life_months - elapsed)
            if months > 0:
                amount = r.value(self.basis, None if self.basis.scalar else start) or 0
                total += amount * months / self.life_months
        return total


class LineMaker:
    """Callable that adds line items of one kind to an entity and totals them.

    ``co.pl.<kind>`` and ``co.bs.<kind>`` are line makers, one for each kind in the entity's layout (``co.pl.revenue``,
    ``co.bs.loan``). Calling one books a line of its kind in the entity and returns the new `LineItem`. The maker
    keeps every line it created, so the lines of a kind are read back through `total`, `items`, `opening` and
    `total_of`. Subtotals such as ``co.pl.gross_profit`` are not line makers.

    The parameters of a call depend on the kind. Each maker carries the signature and documentation of its
    template, so ``inspect.signature(co.bs.loan)`` and ``help(co.bs.loan)`` show the loan parameters.

    Parameters
    ----------
    entity : Entity
        The entity whose books the lines are added to.
    kind : str
        Name of the layout kind the maker belongs to, such as ``"revenue"`` or ``"loan"``.
    create : Callable[..., LineItem]
        Function that books one line from the call's arguments and returns its `LineItem`.

    Attributes
    ----------
    entity : Entity
        The entity that owns the maker.
    kind : str
        Name of the layout kind, as in ``co.pl.<kind>``.
    total : Series
        Sum of the lines' values in each period, including lines added later. What a line's value is (a flow or
        a closing balance) depends on the kind; the template of the kind says which.

    Notes
    -----
    Only the entity creates line makers, when it builds ``co.pl`` and ``co.bs``; user code never constructs
    one. The layout decides which kinds exist: general layouts are in `boki.layouts`, and a custom `Layout` gets
    one maker per `Kind` it lists.

    Examples
    --------
    Book two revenue lines in a monthly model and read the kind back:

    >>> import boki as b
    >>> m = b.Model("Makers", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS)
    >>> product = co.pl.revenue("Product", 100, category="Products")
    >>> service = co.pl.revenue("Service", 40, category="Services")
    >>> r = m.render()
    >>> r.value(co.pl.revenue.total, "2027-02")
    140
    >>> r.value(co.pl.revenue.total_of(category="Services"), "2027-02")
    40
    >>> [item.name for item in co.pl.revenue.items]
    ['Product', 'Service']
    """

    entity: Entity
    kind: str
    total: Series
    _template: str

    def __init__(self, entity: Entity, kind: str, create: Callable[..., LineItem]):
        self.entity, self.kind, self._create = entity, kind, create
        self._items: list[LineItem] = []
        self.total = _Total(lambda: list(self._items), f"{kind} (total)", entity)

    def __call__(self, *args: object, **kwargs: object) -> LineItem:
        """Add a line of this kind to the entity's books and return it.

        The accepted parameters, and what the call posts, depend on the kind; the signature and documentation of
        this maker describe them. The call forwards its arguments unchanged to the kind's create function.

        Parameters
        ----------
        *args : object
            Positional arguments of the kind's create function, starting with the line name.
        **kwargs : object
            Keyword arguments of the kind's create function.

        Returns
        -------
        LineItem
            The new line. It is also appended to `items`.

        Raises
        ------
        TypeError
            At construction, if the arguments do not fit the kind; the template of the kind lists each case.
        ValueError
            At construction, if the arguments are valid in form but not in value, such as a duplicate line name.
        UnitError
            At construction, if an amount is not in the entity's currency.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Maker call", start="2027-01", periods=2, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS)
        >>> sales = co.pl.revenue("Product", 100)
        >>> sales.name, co.pl.revenue.items == [sales]
        ('Product', True)
        """  # noqa: DOC502
        item = self._create(*args, **kwargs)
        self._items.append(item)
        return item

    @property
    def items(self) -> list[LineItem]:
        """The lines created through this maker so far, in creation order.

        Returns
        -------
        list[LineItem]
            A new list on every access; changing it does not change the maker.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Maker items", start="2027-01", periods=2, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS)
        >>> product = co.pl.revenue("Product", 100)
        >>> service = co.pl.revenue("Service", 40)
        >>> [line.name for line in co.pl.revenue.items]
        ['Product', 'Service']
        """
        return list(self._items)

    @property
    def opening(self) -> Series:
        """Sum of the lines' opening balances, for balance-sheet kinds.

        Returns
        -------
        Series
            In each period, the previous period's closing balance of every line, added up; in the first period,
            the declared opening balances.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Maker opening", start="2027-01", periods=2, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS)
        >>> co.bs.opening(cash=100)
        >>> a = co.bs.receivable("Customer A", opening=50)
        >>> c = co.bs.receivable("Customer B", opening=30)
        >>> r = m.render()
        >>> r.value(co.bs.receivable.opening, "2027")
        80
        """
        return _Total(lambda: [i.opening for i in self._items], f"{self.kind} (opening)", self.entity)

    def total_of(self, **filters: object) -> Series:
        """Sum the lines whose attributes equal the given values.

        Parameters
        ----------
        **filters : object
            ``attribute=value`` pairs. A line is included when each named attribute of the `LineItem` equals the
            value, such as ``category="Services"`` or ``name="Product"``. With no filters, every line is included.

        Returns
        -------
        Series
            The sum of the matching lines in each period, including lines added later.

        Raises
        ------
        AttributeError
            At evaluation, if a filter names an attribute that a line does not have.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Maker filter", start="2027-01", periods=2, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS)
        >>> goods = co.pl.revenue("Product", 100, category="Goods")
        >>> services = co.pl.revenue("Support", 40, category="Services")
        >>> r = m.render()
        >>> r.value(co.pl.revenue.total_of(category="Services"), "2027")
        40
        """  # noqa: DOC502
        def pick():
            return [i for i in self._items if all(getattr(i, k) == v for k, v in filters.items())]
        return _Total(pick, f"{self.kind} ({', '.join(f'{k}={v}' for k, v in filters.items())})", self.entity)

    def __repr__(self):
        return f"<{self.entity.name}.{self.kind}: {len(self._items)} items>"


def _line_maker(entity: "Entity", kind: Kind, create: Callable[..., LineItem], template: str) -> LineMaker:
    """The maker of `kind`, carrying the signature of `create` and the documentation of `template`.

    A template key without a template is an error: every maker must be documented.
    """
    maker = LineMaker(entity, kind.name, create)
    maker._template = template
    maker.__signature__ = inspect.signature(create)
    maker.__doc__ = maker_doc(template, entity.layout, kind)
    return maker


def _amount(entity: "Entity", x, what: str) -> Series:
    """An amount per period in currency. A rate per time (JPY/month) is integrated by period length.
    A dict gives amounts in selected periods ({"2027-06": 50 * JPY}), as loan draw= does."""
    s = Data(x) if isinstance(x, dict) else lift(x)
    if s.unit is not None and MONTH_DIM in s.unit:
        s = s * entity.model.period_length
    if s.unit is not None and s.unit != _DIMENSIONLESS:
        entity._check_currency(s.unit, what)
    return s


def _points(entity: "Entity", x, what: str) -> Series:
    return _amount(entity, x, what)


def _opening(entity: "Entity", x, what: str) -> Series | None:
    return None if x is None else _amount(entity, x, f"{what} (opening)")


def _parse_actuals(entity: "Entity", data, what: str) -> Data:
    """Validate and wrap a {period: amount} mapping of historical actuals for periods <= model.actual_until."""
    actual_until = entity.model.actual_until
    if actual_until is None:
        raise ValueError(f"{what}: actuals= requires Model(..., actual_until=...)")
    if not isinstance(data, Mapping):
        raise TypeError(f"{what}: actuals= must be a {{period: amount}} mapping")
    resolved = {}
    for key, value in data.items():
        index = entity.model.timeline.index(key)
        if index > actual_until:
            raise ValueError(f"{what}: actuals period {key!r} is after actual_until")
        _amount(entity, value, f"{what} actuals")
        resolved[index] = value
    out = Data(resolved, f"{what} (actuals)")
    out._actuals_inline = True
    return out


def _apply_pl_actuals(line: "LineItem", actuals_series: Series | None) -> None:
    """Replace the historical portion of a flow LineItem with actuals (or 0 when unset)."""
    model = line.entity.model
    if model.actual_until is None:
        return
    if not hasattr(line, "_forecast_expr"):
        line._forecast_expr = line.expr
    line._actuals = actuals_series
    hist = actuals_series if actuals_series is not None else Const(0, line.entity._currency, literal=True)
    line.expr = hist.where(model.is_actual, line._forecast_expr)
    line.scalar = line.expr.scalar


def _account_of(x) -> Account:
    """An account from an Account, a balance (co.bs.cash) or a line item."""
    if isinstance(x, Account):
        return x
    account = getattr(x, "account", None)
    if isinstance(account, Account):
        return account
    raise TypeError(f"{x!r} is not an account or a line item with one")


class PL:
    """The income statement of an entity: one line maker per PL kind and the layout's subtotals as series.

    ``co.pl`` is built from the entity's layout. Each PL kind of the layout is an attribute named after the kind,
    a `LineMaker` (``co.pl.revenue``, ``co.pl.sga``): calling it books a line, and its ``total`` adds up the lines
    of the kind. The layout's subtotals (its stages) are `Series` attributes such as ``co.pl.gross_profit``, in the
    entity's currency per period. Expenses are positive amounts, and a subtotal subtracts them. The kinds and
    subtotals that exist depend on the layout, and reading one the layout does not have raises ``AttributeError``.

    Parameters
    ----------
    entity : Entity
        The entity the statement belongs to. Created by the entity; user code does not construct it.

    Attributes
    ----------
    gross_profit : Series
        Revenue less cost of sales. Present in the IFRS, US GAAP and J-GAAP general layouts.
    operating_income : Series
        The operating subtotal. Present in the IFRS, US GAAP and J-GAAP general layouts, and absent in the bank
        layout. Shown as "Operating profit" under IFRS.
    ordinary_income : Series
        Operating income plus non-operating income less non-operating expenses. J-GAAP only.
    net_interest_income : Series
        Interest income less interest expense. Bank layout only.
    pretax_income : Series
        Profit before income tax. Present in every built-in layout.
    net_income : Series
        Profit after income tax, the entity's net income. Every layout needs it.

    See Also
    --------
    boki.LineMaker : The callable behind each PL kind.
    boki.ledger.BS : The balance sheet.

    Notes
    -----
    Reading a name that is not a PL kind or subtotal of the layout, such as ``co.pl.special_loss`` on an IFRS entity,
    raises ``AttributeError`` whose message lists the kinds available.

    The subtotals of each built-in layout, with expenses as positive amounts:

    * **IFRS**: ``gross_profit`` = revenue - cogs; ``operating_income`` = gross_profit - sga + other_income -
      other_expense; ``pretax_income`` = operating_income + finance_income - finance_cost; ``net_income`` =
      pretax_income - income_tax.
    * **US GAAP**: ``gross_profit`` = revenue - cogs; ``operating_income`` = gross_profit - sga; ``pretax_income`` =
      operating_income + other_income - other_expense - interest_expense; ``net_income`` = pretax_income - income_tax.
    * **J-GAAP**: ``gross_profit`` = revenue - cogs; ``operating_income`` = gross_profit - sga; ``ordinary_income`` =
      operating_income + non_operating_income - non_operating_expense; ``pretax_income`` = ordinary_income +
      special_gain - special_loss; ``net_income`` = pretax_income - income_tax.
    * **Bank layout**: ``net_interest_income`` = interest_income - interest_expense; ``pretax_income`` =
      net_interest_income - provision + non_interest_income - non_interest_expense; ``net_income`` = pretax_income -
      income_tax.

    Where the layouts differ, the standard also differs in what it calls the subtotal: ``co.label("operating_income")``
    returns the name a statement shows. Custom layouts define their own subtotals; see `boki.layouts`.

    Examples
    --------
    Revenue less cost of sales and operating costs in a monthly model:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Income", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> materials = co.pl.cogs("Materials", 30)
    >>> rent = co.pl.sga("Rent", 20)
    >>> r = m.render()
    >>> r.value(co.pl.gross_profit, "2027-01"), r.value(co.pl.operating_income, "2027-01")
    (70, 50)
    >>> r.value(co.pl.net_income, "2027-02")
    50
    >>> co.pl.special_loss
    Traceback (most recent call last):
    ...
    AttributeError: IFRS has no PL kind 'special_loss'; available: revenue, cogs, sga, other_income, other_expense, finance_income, finance_cost, income_tax
    """  # noqa: DOC602, DOC603

    def __init__(self, entity: Entity):
        self._entity = entity
        for k in entity.layout.pl:
            if isinstance(k, Kind):
                create, template = (self._make_income_tax, "income_tax") if k.name == "income_tax" \
                    else (self._maker(k.name), "pl_line")
                setattr(self, k.name, _line_maker(entity, k, create, template))
        for stage in entity.layout.stages:
            node = Named(f"{entity.name}: {stage.name}", stage.formula(self))
            setattr(self, stage.name, node)
            entity._late.append((node, lambda f=stage.formula: f(self)))

    def __getattr__(self, item: str) -> LineMaker:
        if item.startswith("_"):
            raise AttributeError(item)
        e = self._entity
        where = e.standard.name if e.layout is e.standard.general else f"the {e.layout.name} layout"
        raise AttributeError(f"{where} has no PL kind {item!r}; available: {', '.join(e.layout.pl_kinds)}")

    def _maker(self, kind: str):
        entity = self._entity
        income = kind in entity.layout.income_kinds

        def create(name: str, amount=None, *, data: dict | None = None, settle: Kernel | None = None,
                   recognize: Kernel | None = None, cash=None, category: str | None = None,
                   against=None, vat=None, counterparty=None, margin=None, used: Kernel | None = None,
                   life=None, opening=None, opening_collect: dict | None = None,
                   actuals: dict | None = None) -> LineItem:
            if (opening is not None or opening_collect is not None) and settle is None:
                raise TypeError(f"{name}: opening= and opening_collect= describe the balance that settle= collects; "
                                "give settle= too, or declare the balance with co.bs.receivable / co.bs.payable")
            if opening_collect is not None and opening is None:
                raise TypeError(f"{name}: opening_collect= splits the opening balance, so give opening= too")
            if (opening is not None) and (counterparty is not None or against is not None):
                raise TypeError(f"{name}: opening= does not combine with counterparty= or against=")
            if counterparty is not None:
                if isinstance(counterparty, LineMaker) and counterparty.kind in ("inventory", "fixed_asset"):
                    return _asset_trade(entity, kind, income, name, amount, data, settle, recognize, cash,
                                        category, against, vat, counterparty, margin, used, life)
                if margin is not None or used is not None or life is not None:
                    raise TypeError(f"{name}: margin=, used= and life= apply only when counterparty= is an asset")
                return _trade(entity, kind, income, name, amount, data, settle, recognize, cash, category,
                              against, vat, counterparty)
            if margin is not None or used is not None or life is not None:
                raise TypeError(f"{name}: margin=, used= and life= require counterparty=other.bs.inventory or "
                                "other.bs.fixed_asset")
            actuals_s = _parse_actuals(entity, actuals, name) if actuals is not None else None
            raw = data if data is not None else (0 if amount is None and actuals is not None else amount)
            amt = _points(entity, raw, name)
            if settle is not None:
                _check_kernel_distribution(settle, f"settle= of {name!r}")
            if recognize is not None:
                _check_kernel_distribution(recognize, f"recognize= of {name!r}")
            if against is not None and (settle is not None or cash is not None or recognize is not None):
                raise TypeError(f"{name}: against= does not combine with settle=, cash= or recognize=")
            paid = _amount(entity, cash, f"{name} cash") if cash is not None else \
                (amt.spread(settle) if settle is not None else None)
            if vat is not None:
                if against is not None:
                    raise TypeError(f"{name}: vat= does not apply to a line booked against another account")
                entity._vat_line(name, amt, vat, income, paid)
            acct = entity._account(name, "income" if income else "expense", kind, "pl", category)
            value = amt.spread(recognize) if recognize is not None else amt
            if recognize is not None:
                accrual = entity._shared("deferred_revenue" if income else "prepaid")
                if income:
                    counter = entity._shared("receivable") if paid is not None else entity._cash_account
                    entity._post(f"{name} (billed)", amt, debit=counter, credit=accrual)
                    if paid is not None:
                        entity._post(f"{name} (collected)", paid, debit=entity._cash_account, credit=counter)
                    entity._post(name, value, debit=accrual, credit=acct)
                else:
                    counter = entity._shared("payable") if paid is not None else entity._cash_account
                    entity._post(f"{name} (billed)", amt, debit=accrual, credit=counter)
                    if paid is not None:
                        entity._post(f"{name} (paid)", paid, debit=counter, credit=entity._cash_account)
                    entity._post(name, value, debit=acct, credit=accrual)
            elif paid is not None:
                # Cash on its own schedule; the difference sits in receivables (negative = deferred).
                accrual = entity._shared("receivable" if income else "payable")
                if income:
                    entity._post(name, amt, debit=accrual, credit=acct)
                    entity._post(f"{name} (collected)", paid, debit=entity._cash_account, credit=accrual)
                else:
                    entity._post(name, amt, debit=acct, credit=accrual)
                    entity._post(f"{name} (paid)", paid, debit=accrual, credit=entity._cash_account)
            elif against is not None:
                target = _account_of(against)
                entity._post(name, amt, debit=target, credit=acct) if income else \
                    entity._post(name, amt, debit=acct, credit=target)
            else:
                if income:
                    entity._post(name, amt, debit=entity._cash_account, credit=acct)
                else:
                    entity._post(name, amt, debit=acct, credit=entity._cash_account)
            if opening is not None:
                _open_settled_balance(entity, name, income, settle, opening, opening_collect)
            item = LineItem(name, value, entity, kind, acct, category)
            _apply_pl_actuals(item, actuals_s)
            return item
        return create

    def _make_income_tax(self, name: str, amount=None, *, rate=None, base=None,
                         nol: Series | Quantity | float | bool = True,
                         data: dict | None = None, settle: Kernel | None = None,
                         actuals: dict | None = None) -> LineItem:
        make = self._maker("income_tax")
        if amount is not None or data is not None:
            return make(name, amount, data=data, settle=settle, actuals=actuals)
        if rate is None or base is None:
            raise TypeError("income_tax needs rate= and base= (or data=)")
        base = lift(base)
        if self._entity.model.actual_until is not None:
            base = base.where(self._entity.model.is_forecast, 0)
        tax_on = rate if callable(rate) else (lambda taxable: rate * taxable)   # a callable rate: brackets
        if nol is False:
            return make(name, tax_on(base), settle=settle, actuals=actuals)
        carried = _nol(base, name, opening=None if nol is True else nol)
        used = Named(f"{name}: NOL used", carried.used)
        item = make(name, tax_on(_positive(base) - used), settle=settle, actuals=actuals)
        item.nol = NOL(carried.balance, used, carried.taxable)
        return item


class _OpeningCollected(Series):
    """The share of an opening receivable (payable) collected in each period, from steady pre-model sales."""

    scalar = False

    def __init__(self, balance: Series, fractions: tuple[float, ...], name: str):
        self.balance, self.fractions, self.name = balance, fractions, name
        self.unit = balance.unit

    def _eval(self, r, t):
        if t >= len(self.fractions):
            return 0.0
        return self.fractions[t] * (r.value(self.balance, None if self.balance.scalar else 0) or 0)


def _steady_collection(kernel: Kernel, name: str) -> tuple[float, ...]:
    """The share of an opening balance from steady pre-model sales that is settled in each period: T_j / sum(T)
    with T_j the weight of kernel steps beyond j (what is still open after j periods)."""
    w = kernel.weights
    tail = [sum(w[j + 1:]) for j in range(len(w))]
    total = sum(tail)
    if total <= 1e-12:
        raise ValueError(f"{name}: settle={kernel.name} leaves nothing outstanding, so there is no default "
                         "schedule for opening=; give opening_collect={period: amount}")
    return tuple(x / total for x in tail)


def _constant(x, what: str) -> float:
    s = lift(x)
    if not isinstance(s, Const):
        raise TypeError(f"{what}: give plain amounts (30 * JPY), not series, so the totals can be checked")
    return s.value


def _open_settled_balance(entity, name, income, settle, opening, opening_collect) -> None:
    """Open the receivable (payable) a settle= line uses with the line's pre-model balance and collect it."""
    shared = entity._shared("receivable" if income else "payable")
    balance = _opening(entity, opening, name)
    if isinstance(balance, Const) and balance.value < 0:
        raise ValueError(f"{name}: opening={balance.value:g} is negative; an opening balance is an amount outstanding")
    shared.opening = balance if shared.opening is None else shared.opening + balance
    if opening_collect is None:
        collected = _OpeningCollected(balance, _steady_collection(settle, name), f"{name} (opening collected)")
    else:
        if not isinstance(opening_collect, dict) or not opening_collect:
            raise TypeError(f"{name}: opening_collect= is a {{period: amount}} dict")
        what = f"{name}: opening_collect="
        for key in opening_collect:
            entity.model.timeline.index(key)
        amounts = [_constant(_amount(entity, v, what), what) for v in opening_collect.values()]
        total = sum(amounts)
        if any(a < 0 for a in amounts):
            raise ValueError(f"{name}: opening_collect= has a negative amount: {amounts}")
        have = _constant(balance, f"{name}: opening=")
        if abs(total - have) > 1e-9 * max(abs(total), abs(have), 1.0):
            raise ValueError(f"{name}: opening_collect= sums to {total:g} but opening= is {have:g}; "
                             "they must be equal")
        collected = _amount(entity, opening_collect, what)
    if income:
        entity._post(f"{name} (opening collected)", collected, debit=entity._cash_account, credit=shared)
    else:
        entity._post(f"{name} (opening paid)", collected, debit=shared, credit=entity._cash_account)


def _trade(entity, kind, income, name, amount, data, settle, recognize, cash, category, against, vat,
           counterparty) -> LineItem:
    """A PL line whose other side is another entity of the model (counterparty=other.pl.<kind>): the same
    amount, from the same expression and on the same timing, is booked in both books, so the two sides
    cannot differ. The postings of both carry the other entity, so a group's consolidation drops them."""
    other = counterparty
    if not isinstance(other, LineMaker) or other.kind not in other.entity.layout.pl_kinds:
        what = "a balance-sheet kind" if isinstance(other, LineMaker) else type(other).__name__
        raise TypeError(f"{name}: counterparty= takes the other entity's PL kind (other.pl.cogs); {what} on the "
                        "other side is not supported yet")
    _other_entity(name, entity, other.entity)
    if other.kind == "income_tax":
        raise TypeError(f"{name}: income tax is not a trade between entities")
    if (other.kind in other.entity.layout.income_kinds) == income:
        side = "income" if income else "an expense"
        raise TypeError(f"{name}: both sides would be {side}; the counterparty takes the opposite side "
                        "(revenue on one side, a cost on the other)")
    if against is not None or vat is not None:
        raise TypeError(f"{name}: counterparty= does not combine with against= or vat=")
    amt = _points(entity, data if data is not None else amount, name)
    other_amount = entity.model._convert_currency(
        amt, entity._currency, other.entity._currency or entity._currency)
    mine, theirs = len(entity._postings), len(other.entity._postings)
    line = getattr(entity.pl, kind)._create(name, amt, settle=settle, recognize=recognize, cash=cash,
                                            category=category)
    mirror = other(name, other_amount, settle=settle, recognize=recognize, cash=cash, category=category)
    _tag(entity, other.entity, mine, theirs)
    line.counterparty, mirror.counterparty = mirror, line
    seller, buyer = (entity, other.entity) if income else (other.entity, entity)
    seller_amount, buyer_amount = (amt, other_amount) if income else (other_amount, amt)
    trade = _IntercompanyTrade(seller, buyer, name, seller_amount, buyer_amount,
                               tuple(entity._postings[mine:] + other.entity._postings[theirs:]))
    for post in trade._postings:
        post.intercompany_trade = trade
    entity._intercompany_trades.append(trade)
    other.entity._intercompany_trades.append(trade)
    return line


def _asset_trade(entity, kind, income, name, amount, data, settle, recognize, cash, category, against, vat,
                 counterparty, margin, used, life) -> LineItem:
    other = counterparty
    if not isinstance(other, LineMaker) or other.kind not in ("inventory", "fixed_asset"):
        raise TypeError(f"{name}: counterparty= takes other.bs.inventory or other.bs.fixed_asset")
    if kind != "revenue" or not income:
        raise TypeError(f"{name}: an asset counterparty is supported only on pl.revenue products")
    _other_entity(name, entity, other.entity)
    if margin is None:
        raise TypeError(f"{name}: an asset counterparty requires margin=")
    if recognize is not None or against is not None or vat is not None:
        raise TypeError(f"{name}: an asset counterparty does not combine with recognize=, against= or vat=")
    if other.kind == "inventory":
        if used is None:
            raise TypeError(f"{name}: counterparty=other.bs.inventory requires used=")
        if life is not None:
            raise TypeError(f"{name}: life= applies only to counterparty=other.bs.fixed_asset")
        _check_kernel_distribution(used, f"used= of {name!r}")
        life_months = None
    else:
        if life is None:
            raise TypeError(f"{name}: counterparty=other.bs.fixed_asset requires life=")
        if used is not None:
            raise TypeError(f"{name}: used= applies only to counterparty=other.bs.inventory")
        from .model import _months
        life_months = _months(life)
        if life_months <= 0:
            raise ValueError(f"{name}: life must be positive, got {life_months} months")

    price = _points(entity, data if data is not None else amount, name)
    rate = lift(margin)
    if rate.unit not in (None, _DIMENSIONLESS):
        raise UnitError(f"{name}: margin= must be dimensionless")
    profit = Named(f"{name}: intercompany profit", price * rate)
    mine, theirs = len(entity._postings), len(other.entity._postings)
    line = entity.pl.__dict__[kind]._create(name, price, settle=settle, cash=cash, category=category)
    buyer_item, depreciation, realization, trade_end = _asset_purchase(
        other.entity, entity, name, price, other.kind, settle=settle, cash=cash, used=used, life=life,
        profit=profit)
    _tag(entity, other.entity, mine, theirs, theirs_end=trade_end)
    postings = tuple(entity._postings[mine:] + other.entity._postings[theirs:trade_end])
    buyer_price = entity.model._convert_currency(price, entity._currency,
                                                  other.entity._currency or entity._currency)
    trade = _AssetTrade(entity, other.entity, name, other.kind, price, profit, buyer_item, used,
                        depreciation, realization, life_months=life_months, _postings=postings,
                        buyer_price=buyer_price)
    for post in postings:
        post.asset_trade = trade
    entity._asset_trades.append(trade)
    other.entity._asset_trades.append(trade)
    line.counterparty, buyer_item.counterparty = buyer_item, line
    return line


def _asset_purchase(buyer, seller, name, price, asset_kind, *, settle, cash, used, life, profit):
    asset_name = f"{name} ({seller.name})"
    kind = buyer.layout.bs_kind(asset_kind)
    if kind is None:
        raise ValueError(f"{buyer.layout.name} has no balance-sheet kind {asset_kind!r}")
    price = buyer.model._convert_currency(price, seller._currency, buyer._currency or seller._currency)
    profit = buyer.model._convert_currency(profit, seller._currency, buyer._currency or seller._currency)
    price = _amount(buyer, price, asset_name)
    account = buyer._account(asset_name, "asset", asset_kind, kind.cf, tags=kind.tags)
    if settle is not None:
        _check_kernel_distribution(settle, f"settle= of {name!r}")
        due = buyer._shared("payable")
        buyer._post(f"{asset_name} (billed)", price, debit=account, credit=due)
        paid = price.spread(settle) if cash is None else _amount(buyer, cash, f"{asset_name} cash")
        buyer._post(f"{asset_name} (paid)", paid, debit=due, credit=buyer._cash_account)
    elif cash is not None:
        due = buyer._shared("payable")
        buyer._post(f"{asset_name} (billed)", price, debit=account, credit=due)
        buyer._post(f"{asset_name} (paid)", _amount(buyer, cash, f"{asset_name} cash"),
                    debit=due, credit=buyer._cash_account)
    else:
        buyer._post(asset_name, price, debit=account, credit=buyer._cash_account)
    trade_end = len(buyer._postings)

    balance = buyer._balance(account)
    item = LineItem(asset_name, balance, buyer, asset_kind, account)
    item.balance = item.book = balance
    getattr(buyer.bs, asset_kind)._items.append(item)

    if asset_kind == "inventory":
        consumption = price.spread(used)
        buyer.pl.cogs(f"{asset_name} used", consumption, against=account)
        item.used = used
        depreciation = None
        realization = profit.spread(used)
    else:
        from .model import _months
        life_months = _months(life)
        if life_months <= 0:
            raise ValueError(f"{asset_name}: life must be positive, got {life_months} months")
        depreciation = _AssetTradeFlow(buyer.model, price, life_months, f"{asset_name}: depreciation")
        item.depreciation = buyer.pl.__dict__[buyer.layout.depreciation_kind](
            f"{asset_name} depreciation", depreciation, against=account, category="Depreciation expense")
        item.depreciation.account.tags |= {DEPRECIATION}
        realization = _AssetTradeFlow(buyer.model, profit, life_months,
                                       f"{asset_name}: realized intercompany profit")
        item.life = life
    return item, depreciation, realization, trade_end


def _asset_disposal_account(entity, gain: bool) -> tuple[Account, str, str]:
    if entity.standard.name == "J-GAAP":
        kind, name = ("special_gain", "Gain on sale of fixed assets") if gain else ("special_loss", "Loss on sale of fixed assets")
    else:
        kind = "other_income" if gain else "other_expense"
        name = "Gain on disposal of fixed assets" if gain else "Loss on disposal of fixed assets"
    if kind not in entity.layout.pl_kinds:
        raise ValueError(f"{entity.layout.name} has no {kind} kind for fixed-asset disposals")
    account = next((a for a in entity._accounts if a.name == name and a.kind == kind), None)
    if account is None:
        account = entity._account(name, "income" if gain else "expense", kind, "pl", category=name)
    return account, kind, name


def _other_entity(name: str, entity, other) -> "Entity":
    if not isinstance(other, Entity):
        raise TypeError(f"{name}: counterparty= takes the other entity here (counterparty=parent)")
    if other is entity:
        raise ValueError(f"{name}: the counterparty is {entity.name} itself")
    if other.model is not entity.model:
        raise ValueError(f"{name}: the counterparty belongs to another model")
    return other


def _finance_income(entity) -> "LineMaker":
    """The PL kind for interest and dividends received."""
    kinds = entity.layout.pl_kinds
    options = ("finance_income", "non_operating_income", "other_income", "interest_income")
    kind = next((k for k in options if k in kinds), None)
    if kind is None:
        raise ValueError(f"{entity.layout.name} layout has no PL kind for interest income or dividends; "
                         f"expected one of {', '.join(options)}")
    return getattr(entity.pl, kind)


def _held_by(other, name: str, kind: str = "other_asset", *, tags=frozenset()) -> "tuple[Account, LineItem]":
    """An asset account in the other entity's books for a balance it holds in this trade (a loan made, shares)."""
    bs_kind = next(k for k in other.layout.bs if k.name == kind)
    acct = next((a for a in other._accounts if a.name == name and a.kind == kind), None)
    if acct is None:
        acct = other._account(name, "asset", kind, bs_kind.cf, tags=tags)
    else:
        acct.tags = acct.tags | frozenset(tags)
    items = getattr(other.bs, kind)._items
    item = next((i for i in items if i.account is acct), None)
    if item is None:
        item = LineItem(name, other._balance(acct), other, kind, acct)
        item.balance = item.expr
        items.append(item)
    return acct, item


def _tag(entity, other, mine: int, theirs: int, *, mine_end=None, theirs_end=None) -> None:
    """Mark the postings booked since (mine, theirs) as a trade between the two entities."""
    for p in entity._postings[mine:mine_end]:
        p.counterparty = other
    for p in other._postings[theirs:theirs_end]:
        p.counterparty = entity


def _positive(x: Series) -> Series:
    return smax(x, 0)


class _NOL(Series):
    """Loss carried forward: grows by losses, shrinks by the profit it shelters (at most cap × profit)."""

    def __init__(self, base: Series, name: str, opening=None, cap=None):
        self.base, self.name = base, f"{name}: NOL balance"
        self.carried_in = lift(opening) if opening is not None else None
        self.cap = lift(cap) if cap is not None else None

    @property
    def unit(self):
        return self.base.unit

    def _eval(self, r, t):
        if t > 0:
            prev = r.value(self, t - 1)
        else:
            prev = r.value(self.carried_in, None if self.carried_in.scalar else 0) if self.carried_in is not None else 0
        b = r.value(self.base, t)
        usable = max(b, 0) * (r.value(self.cap, None if self.cap.scalar else t) if self.cap is not None else 1)
        return prev + max(-b, 0) - min(usable, prev)


class NOL(NamedTuple):
    """A loss carryforward: b.nol(base) or an income tax's .nol."""
    balance: Series   # the losses still to use at the end of each period
    used: Series      # the losses used against this period's profit
    taxable: Series   # the profit left after them: max(base, 0) - used


def _nol(base: Series, name: str, opening=None, cap=None) -> NOL:
    balance = _NOL(base, name, opening, cap)
    profit = smax(base, 0)
    used = smin(profit if cap is None else profit * cap, balance.lag(1, fill=0 if opening is None else opening))
    return NOL(balance, used, profit - used)


class _Gap(Series):
    """The cash posting that makes an account close at `target`, after its other postings."""

    def __init__(self, balance: "_Balance", target: Series, name: str):
        self.balance, self.target, self.name = balance, target, name
        self.posting: Posting | None = None

    @property
    def unit(self):
        return self.target.unit

    def _eval(self, r, t):
        others = 0.0
        for sign, postings in ((1, self.balance.account.debits), (-1, self.balance.account.credits)):
            for p in postings:
                if p is not self.posting:
                    others += sign * (r.value(p.amount, None if p.amount.scalar else t) or 0)
        return r.value(self.target, None if self.target.scalar else t) - r.value(self.balance.opening, t) \
            - self.balance.sign * others


class BS:
    """The balance sheet of an entity: cash, one line maker per balance-sheet kind, the totals, and generic lines.

    ``co.bs`` is built from the entity's layout. Each balance-sheet kind of the layout is an attribute named after the
    kind, a `LineMaker` (``co.bs.loan``, ``co.bs.fixed_asset``, ``co.bs.receivable``): calling it books a line,
    and its ``total`` adds up the lines of the kind. ``asset`` and ``liability`` book generic lines that are
    outside the layout. Balances are in the entity's currency, positive on the account's normal side. Reading a
    kind the layout does not have raises ``AttributeError``.

    Parameters
    ----------
    entity : Entity
        The entity the balance sheet belongs to. Created by the entity; user code does not construct it.

    Attributes
    ----------
    cash : Series
        The cash balance at the end of each period. Its ``opening`` is the balance at the start of the period, and its
        ``change`` the movement.
    retained_earnings : Series
        Closing retained earnings in each period, including cumulative forecast profit to date.
    equity : Equity
        The equity namespace. ``equity.total`` is the same series as ``total_equity``.
    total_assets : Series
        Every asset balance at the end of each period, cash included.
    total_liabilities : Series
        Every liability balance at the end of each period.
    total_equity : Series
        Capital, retained earnings, and other equity accounts, including the profit to date of the model. Total assets equal
        total liabilities plus total equity in every period; the render checks this.

    See Also
    --------
    boki.ledger.PL : The income statement.
    boki.ledger.CF : The cash-flow statement.
    boki.LineMaker : The callable behind each balance-sheet kind.

    Notes
    -----
    Reading a name that is not a balance-sheet kind of the layout raises ``AttributeError`` whose message lists the kinds
    available and points to ``asset`` and ``liability``.

    A line item's value is its closing balance in each period, and its ``opening`` is the previous period's
    closing balance (the declared opening balance in the first period). Two kinds are the exception because they
    are flows: a ``dividend`` line is the dividend declared in the period, and an ``oci`` line is the period's OCI
    after tax (its ``balance`` is the accumulated reserve), so ``co.bs.oci.total`` is the period's OCI rather than a
    balance. The equity total adds the profit to date to the equity accounts: profit is not posted to the retained
    earnings account, and the statements add the cumulative profit to it.

    The kinds of the general layouts are listed in `the balance-sheet rows
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#bs-rows>`_, and ``working_capital`` is a line you declare,
    like the other kinds: it is not a total computed from the statements.

    Examples
    --------
    A balance sheet with an opening cash balance and a loan drawn in the first month:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Balance", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=100)
    >>> loan = co.bs.loan("Loan", draw={0: 400 * JPY})
    >>> r = m.render()
    >>> round(r.value(co.bs.total_assets, "2027-01")), round(r.value(co.bs.total_liabilities, "2027-01"))
    (500, 400)
    >>> round(r.value(co.bs.total_equity, "2027-01"))
    100
    >>> co.bs.special
    Traceback (most recent call last):
    ...
    AttributeError: the IFRS general layout has no balance-sheet kind 'special'; available: receivable, inventory, prepaid, working_capital, other_current_asset, fixed_asset, intangible, construction, deposit, other_asset, deferred_tax_asset, payable, accrued, deferred_revenue, other_current_liability, lease_liability, other_liability, deferred_tax_liability, loan, capital, nci, dividend, oci, or use bs.asset / bs.liability
    """  # noqa: DOC602, DOC603

    def __init__(self, entity: Entity):
        self._entity = entity
        self.cash = entity._balance(entity._cash_account)
        self.retained_earnings = Named(
            f"{entity.name}: retained earnings",
            entity._balance(entity.retained_earnings) + entity._cum_profit,
        )
        entity._late.append(
            (self.retained_earnings, lambda: entity._balance(entity.retained_earnings) + entity._cum_profit)
        )
        makers = {"line": self._line_kind, "fixed_asset": self._fixed_asset, "loan": self._loan,
                  "construction": self._construction, "capital": self._capital, "dividend": self._dividend}
        for k in entity.layout.bs:
            setattr(self, k.name, _line_maker(entity, k, makers[k.mechanism](k), k.mechanism))
        self.equity = _Equity(entity)
        self.total_assets = _SideTotal(entity, "asset")
        self.total_liabilities = _SideTotal(entity, "liability")
        self.total_equity = entity._equity_total

    def __getattr__(self, item: str) -> LineMaker:
        if item.startswith("_"):
            raise AttributeError(item)
        e = self._entity
        raise AttributeError(f"the {e.layout.name} layout has no balance-sheet kind {item!r}; available: "
                             f"{', '.join(k.name for k in e.layout.bs)}, or use bs.asset / bs.liability")

    def opening(self, *, cash=None, retained_earnings=None) -> None:
        """Declare the opening cash and retained earnings of the balance sheet at the model start.

        The opening balance sheet is made of the opening balances declared on each account: ``cash`` here and
        ``opening=`` on lines. Retained earnings take whatever balances the sheet unless you give them.

        Parameters
        ----------
        cash : scalar or Quantity, optional
            Cash at the start of the first period, in the entity's currency. The default is ``None``, which leaves
            the opening cash unchanged (0 when never given).
        retained_earnings : scalar or Quantity, optional
            Retained earnings at the start of the first period, in the entity's currency. The default is ``None``,
            which leaves the opening retained earnings as the amount that balances the sheet: assets less
            liabilities and the other equity accounts. If you give it, the opening balance sheet must balance on its
            own.

        Raises
        ------
        UnitError
            At construction, if an amount is in a unit other than the entity's currency.

        See Also
        --------
        boki.LineMaker : ``opening=`` on a line declares that line's own opening balance.
        boki.ledger.Entity.journal : Post changes between accounts instead of declaring opening balances.

        Notes
        -----
        ``bs.opening`` declares the opening balance of the cash account and of retained earnings. The opening balance of any
        other account is declared with ``opening=`` on its line, such as ``co.bs.receivable("Receivable", opening=200)``.
        Retained earnings are the balancing figure unless given. When ``retained_earnings`` is given and the opening
        balance sheet does not balance, ``m.render()`` raises `LedgerError` and names the difference. Each call
        replaces only the amounts it names. See `the opening balance sheet
        <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#bs-rows>`_.

        Examples
        --------
        Retained earnings balance the sheet unless you give them:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> m = b.Model("Opening", start="2027-01", periods=2, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> co.bs.opening(cash=1000)
        >>> receivable = co.bs.receivable("Receivable", opening=200)
        >>> r = m.render()
        >>> round(r.value(co.bs.total_equity, "2027"))
        1200
        >>> co.bs.opening(cash=1000, retained_earnings=500)
        >>> try:
        ...     m.render()
        ... except b.LedgerError:
        ...     print("opening balance sheet does not balance")
        opening balance sheet does not balance
        """  # noqa: DOC105, DOC106, DOC107, DOC502
        e = self._entity
        if cash is not None:
            e._cash_account.opening = _opening(e, cash, "cash")
        if retained_earnings is not None:
            e.retained_earnings.opening = _opening(e, retained_earnings, "retained earnings")

    def deferred_tax(self, name: str, difference, rate=None, recognized=1.0) -> None:
        """Book deferred tax from the temporary difference at the end of each period.

        A positive difference creates a deferred tax liability and a negative one a deferred tax asset. The balances
        follow the difference, and each period's change is charged to income tax without moving cash.

        Parameters
        ----------
        name : str
            Name of the deferred tax item; required. It must be unique among the entity's deferred tax items.
        difference : scalar, Quantity, Series, or dict
            The temporary difference between book and tax amounts at the end of each period, a balance in the
            entity's currency (not a change). Positive is taxable and negative is deductible. A plain number is in the
            entity's currency. A dict maps period labels, indices, or dates to differences and uses 0 in the other
            periods.
        rate : scalar or Series, optional
            Tax rate on the difference, a dimensionless ratio such as ``0.3`` for 30%. The default is ``None``, which
            uses the entity's ``tax_rate``.
        recognized : scalar or Series, default=1.0
            Share of a deductible difference that is recognized as an asset, a dimensionless ratio from 0 to 1. It
            does not apply to taxable differences. boki does not assess recoverability, so this is your judgement.

        Raises
        ------
        ValueError
            At construction, if a deferred tax item with this name already exists, or if neither ``rate`` nor the
            entity's ``tax_rate`` is given.
        UnitError
            At construction, if ``rate`` or ``recognized`` is not dimensionless, or ``difference`` is in a unit other
            than the entity's currency.
        TypeError
            At construction, if an argument has a type boki cannot use in an expression.

        See Also
        --------
        boki.ledger.Entity.oci : Taxed OCI recognizes deferred tax through its own reserve.

        Notes
        -----
        The deferred tax liability is ``rate`` times the positive part of ``difference``, and the deferred tax asset is
        ``rate * recognized`` times the negative part. The balances are in ``co.bs.deferred_tax_liability`` and
        ``co.bs.deferred_tax_asset`` (the kinds are non-current and non-cash), and the movements are in the
        income tax line "Deferred tax" ("Deferred income tax" under US GAAP). An increase of the liability is
        ``Dr deferred tax expense, Cr deferred tax liability``, and an increase of the asset is ``Dr deferred tax
        asset, Cr deferred tax expense``. Cash does not change. See `S1: deferred taxes
        <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md#deferred-taxes>`_.

        Examples
        --------
        At a 30% tax rate, temporary differences of 100, 150 and 50 at the year ends give liabilities of 30, 45 and 15
        and tax expenses of 30, 15 and -30:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> years = ["2027", "2028", "2029"]
        >>> m = b.Model("Deferred", start="2027-01", periods=3, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY, tax_rate=0.3)
        >>> co.bs.deferred_tax("Depreciation difference", {0: 100, 1: 150, 2: 50})
        >>> r = m.render()
        >>> [round(r.value(co.bs.deferred_tax_liability.total, year)) for year in years]
        [30, 45, 15]
        >>> [round(r.value(co.pl.income_tax.total, year)) for year in years]
        [30, 15, -30]
        >>> [round(r.value(co.bs.cash, year)) for year in years]
        [0, 0, 0]
        """  # noqa: DOC105, DOC107, DOC502
        self._entity._deferred_tax(name, difference, rate, recognized)

    def sell(self, asset_line: LineItem, price, *, at, counterparty, life) -> LineItem:
        """Sell an existing fixed asset to another entity of the model.

        The seller stops depreciating the asset from the period of sale, derecognizes its carrying amount at the start
        of that period, and books the difference from the price as a gain or loss. The buyer books the asset at the price
        and depreciates it straight-line over ``life``.

        Parameters
        ----------
        asset_line : LineItem
            A depreciating fixed-asset line of this entity, made by ``co.bs.fixed_asset``. Required.
        price : Quantity
            The sale price, in the entity's currency, such as ``150 * JPY``. A plain number is dimensionless and
            raises `UnitError` when the books have a currency.
        at : int, str, or date
            The period of the sale, as an index, a period label, or a date. The price is received in that period.
        counterparty : LineMaker
            The buyer's ``bs.fixed_asset``, ``other.bs.fixed_asset``, where ``other`` is another entity of the same model.
        life : Quantity or Unit
            The buyer's useful life as a time, such as ``5 * b.year``. It must be positive.

        Returns
        -------
        LineItem
            ``asset_line``, whose ``counterparty`` attribute is now the buyer's asset line, named
            ``<asset name> (<seller name>)``.

        Raises
        ------
        TypeError
            At construction, if ``asset_line`` is not a fixed-asset line of this entity with depreciation, or
            ``counterparty`` is not a ``bs.fixed_asset`` maker.
        ValueError
            At construction, if the counterparty is this entity or belongs to another model, if ``life`` is not
            positive, or if the layout of the seller has no gain or loss kind for fixed-asset disposals, or the
            buyer's layout has no ``fixed_asset`` kind.
        IndexError
            At construction, if ``at`` is outside the model timeline.
        UnitError
            At construction, if ``price`` or ``life`` has the wrong unit.

        See Also
        --------
        boki.LineMaker : ``counterparty=`` on a revenue line sells new goods or equipment instead.

        Notes
        -----
        The seller books ``Dr cash, Cr asset`` for the price and ``Dr asset, Cr gain`` (or ``Dr loss, Cr asset``) for the
        difference between the price and the carrying amount. The gain or loss is "Gain on sale of fixed assets" in
        ``special_gain`` under J-GAAP, and "Gain on disposal of fixed assets" in ``other_income`` (or
        ``other_expense`` for a loss) under IFRS and US GAAP. The buyer books ``Dr asset, Cr cash``. Consolidation removes the
        entries of the sale and the unrealized gain; see `S6: intercompany asset sales
        <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md#s6-intercompany-asset-sales-and-unrealized-profits>`_.

        Examples
        --------
        A machine with a carrying amount of 90 at the start of the second month is sold for 150, a gain of 60. The
        buyer depreciates it over five years, 2.5 a month:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> months = ["2027-01", "2027-02", "2027-03"]
        >>> m = b.Model("Sale", start="2027-01", periods=3, step=b.month)
        >>> seller = m.entity("Seller", standard=b.IFRS, currency=JPY)
        >>> buyer = m.entity("Buyer", standard=b.IFRS, currency=JPY)
        >>> buyer.bs.opening(cash=500 * JPY)
        >>> machine = seller.bs.fixed_asset("Machine", opening=100 * JPY, depreciation=10 * JPY)
        >>> sold = seller.bs.sell(machine, 150 * JPY, at="2027-02", counterparty=buyer.bs.fixed_asset, life=5 * b.year)
        >>> r = m.render()
        >>> [round(r.value(seller.pl.other_income.total, month)) for month in months]
        [0, 60, 0]
        >>> [round(r.value(machine.counterparty.balance, month), 1) for month in months]
        [0.0, 147.5, 145.0]
        """  # noqa: DOC105, DOC107, DOC503
        e = self._entity
        if not isinstance(asset_line, LineItem) or asset_line.entity is not e or asset_line.kind != "fixed_asset":
            raise TypeError("bs.sell takes a fixed-asset LineItem from the seller's books")
        if not hasattr(asset_line, "book") or not hasattr(asset_line, "depreciation"):
            raise TypeError(f"{asset_line.name}: bs.sell needs a depreciating fixed asset")
        if not isinstance(counterparty, LineMaker) or counterparty.kind != "fixed_asset":
            raise TypeError("bs.sell counterparty= takes other.bs.fixed_asset")
        _other_entity(asset_line.name, e, counterparty.entity)
        period = e.model.timeline.index(at)
        name = asset_line.name
        price_s = _points(e, {period: price}, f"{name} sale price")
        carrying = asset_line.book.lag(1, fill=asset_line.book.opening) * (e.model.t == period)

        dep_line = asset_line.depreciation
        before_sale = e.model.t < period
        dep_line.expr = dep_line.expr.where(before_sale, 0)
        dep_line.scalar = dep_line.expr.scalar
        for post in set(dep_line.account.debits + dep_line.account.credits):
            post.amount = post.amount.where(before_sale, 0)

        profit = Named(f"{name}: disposal gain or loss", price_s - carrying)
        gain, loss = smax(profit, 0), smax(-profit, 0)
        gain_account, gain_kind, gain_name = _asset_disposal_account(e, True)
        loss_account, loss_kind, loss_name = _asset_disposal_account(e, False)
        e.pl.__dict__[gain_kind]._items.append(LineItem(gain_name, gain, e, gain_kind, gain_account, gain_name))
        e.pl.__dict__[loss_kind]._items.append(LineItem(loss_name, loss, e, loss_kind, loss_account, loss_name))

        mine, theirs = len(e._postings), len(counterparty.entity._postings)
        e._post(f"{name} sale proceeds", price_s, debit=e._cash_account, credit=asset_line.account)
        e._post(gain_name, gain, debit=asset_line.account, credit=gain_account)
        e._post(loss_name, loss, debit=loss_account, credit=asset_line.account)
        buyer_item, depreciation, realization, trade_end = _asset_purchase(
            counterparty.entity, e, name, price_s, "fixed_asset", settle=None, cash=None, used=None,
            life=life, profit=profit)
        _tag(e, counterparty.entity, mine, theirs, theirs_end=trade_end)
        postings = tuple(e._postings[mine:] + counterparty.entity._postings[theirs:trade_end])
        from .model import _months
        buyer_price = e.model._convert_currency(price_s, e._currency,
                                                counterparty.entity._currency or e._currency)
        trade = _AssetTrade(e, counterparty.entity, name, "fixed_asset", price_s, profit, buyer_item,
                            depreciation=depreciation, realization=realization, life_months=_months(life),
                            seller_asset=asset_line.account,
                            gain_account=gain_account, loss_account=loss_account, source="disposal",
                            _postings=postings, buyer_price=buyer_price)
        for post in postings:
            post.asset_trade = trade
        e._asset_trades.append(trade)
        counterparty.entity._asset_trades.append(trade)
        asset_line.counterparty, buyer_item.counterparty = buyer_item, asset_line
        return asset_line

    # -- generic lines ----------------------------------------------------------------

    def asset(self, name: str, amount=None, at=None, *, target=None, opening=None, section: str = "current",
              cf: str | None = None, tags=(), kind: str = "asset", counterparty=None,
              actuals: dict | None = None) -> LineItem:
        """Add a generic balance-sheet asset that is not one of the layout's kinds.

        Use it for an asset the layout has no kind for. Give ``amount`` to change the balance each period against cash,
        or ``target`` to hold the balance at a level and let cash absorb the change. Without either, the line only
        has its opening balance.

        Parameters
        ----------
        name : str
            Line name; required. It must be unique among the entity's accounts of the same ``kind``.
        amount : scalar, Quantity, Series, or dict, optional
            Change of the balance in each period, paid in cash: a positive amount increases the asset and reduces cash.
            In the entity's currency per period. A plain number is in the entity's currency. A quantity per time is
            integrated by period length. A dict maps period labels, indices, or dates to amounts and uses 0 in the
            other periods. Give ``amount`` or ``target``, not both.
        at : int, str, or date, optional
            With ``amount``, books the amount in this period only, and 0 in every other period. The default is ``None``,
            which means the amount applies to every period.
        target : scalar, Quantity, or Series, optional
            The closing balance to hold in each period, in the entity's currency. Cash absorbs the difference from
            the balance before. Give ``amount`` or ``target``, not both.
        opening : scalar or Quantity, optional
            Balance at the start of the first period, in the entity's currency. The default is ``None``, meaning 0.
        section : str, default="current"
            ``"current"`` or ``"noncurrent"``. It only sets the default cash-flow section: ``"current"`` gives
            ``"operating"`` and anything else ``"investing"``.
        cf : str, optional
            Cash-flow section of the cash that moves: ``"operating"``, ``"investing"``, ``"financing"``, or ``"fx"``. The
            default is ``None``, which uses the section from ``section``.
        tags : iterable of str, default=()
            Labels stored on the account and copied into consolidated books. boki reads a few internal tags; others
            have no effect on values.
        kind : str, default="asset"
            The account kind recorded as ``LineItem.kind``. The Excel balance sheet places the line in the
            current or non-current group by the layout kind of this name, if the layout has one.
        counterparty : Entity, optional
            The other entity of the same model that holds the matching liability. It needs ``opening`` and does
            not take ``amount``, ``at``, or ``target``: only an opening intercompany balance is booked, and the
            other entity gets a mirrored line.
        actuals : dict, optional
            Historical closing balances for periods up to ``actual_until``, as ``{period: amount}``. Requires
            ``Model(..., actual_until=...)``.

        Returns
        -------
        LineItem
            The new line, whose value in each period is its closing balance. ``line.balance`` is the same series.

        Raises
        ------
        TypeError
            At construction, if both ``amount`` and ``target`` are given, or if ``counterparty`` is not an entity,
            is given without ``opening``, or is combined with ``amount``, ``target`` or ``at``.
        ValueError
            At construction, if a line of this kind with this name already exists, if ``cf`` is not a valid
            section, or if ``counterparty`` is this entity or belongs to another model.
        UnitError
            At construction, if an amount is in a unit other than the entity's currency.

        See Also
        --------
        boki.ledger.BS.liability : The generic liability.
        boki.ledger.BS.opening : Opening cash and retained earnings.

        Notes
        -----
        ``amount`` books ``Dr asset, Cr cash``, and ``target`` books the cash entry that makes the closing balance equal the
        target. The cash flow is classified by ``cf``. Layout kinds such as ``co.bs.other_asset`` take the same arguments
        and have a default section of their own; use ``asset`` for something the layout does not offer.

        Examples
        --------
        A deposit that grows by 20 a month and a stock held at 50, paid from cash:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> months = ["2027-01", "2027-02", "2027-03"]
        >>> m = b.Model("Assets", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> co.bs.opening(cash=1000)
        >>> deposit = co.bs.asset("Deposit", 20, opening=100)
        >>> stock = co.bs.asset("Stock", target=50, opening=10)
        >>> r = m.render()
        >>> [round(r.value(deposit, month)) for month in months]
        [120, 140, 160]
        >>> [round(r.value(stock, month)) for month in months]
        [50, 50, 50]
        >>> [round(r.value(co.bs.cash, month)) for month in months]
        [940, 920, 900]
        """  # noqa: DOC105, DOC107, DOC502
        return self._line(name, kind, "asset", amount, at, target, opening,
                          cf or ("operating" if section == "current" else "investing"), frozenset(tags),
                          counterparty=counterparty, actuals=actuals)

    def liability(self, name: str, amount=None, at=None, *, target=None, opening=None,
                  cf: str | None = None, tags=(), kind: str = "liability", counterparty=None,
                  actuals: dict | None = None) -> LineItem:
        """Add a generic balance-sheet liability that is not one of the layout's kinds.

        It works like ``asset`` on the other side of the balance sheet: ``amount`` changes the balance each period and
        brings cash in, and ``target`` holds the balance at a level.

        Parameters
        ----------
        name : str
            Line name; required. It must be unique among the entity's accounts of the same ``kind``.
        amount : scalar, Quantity, Series, or dict, optional
            Change of the balance in each period, received in cash: a positive amount increases the liability and
            increases cash. In the entity's currency per period, with the forms of the ``amount`` of ``asset``. Give
            ``amount`` or ``target``, not both.
        at : int, str, or date, optional
            With ``amount``, books the amount in this period only. The default is ``None``, which means every period.
        target : scalar, Quantity, or Series, optional
            The closing balance to hold in each period, in the entity's currency. Cash absorbs the change.
        opening : scalar or Quantity, optional
            Balance at the start of the first period, in the entity's currency. The default is ``None``, meaning 0.
        cf : str, optional
            Cash-flow section of the cash that moves: ``"operating"``, ``"investing"``, ``"financing"``, or ``"fx"``. The
            default is ``None``, which means ``"operating"``.
        tags : iterable of str, default=()
            Labels stored on the account and copied into consolidated books.
        kind : str, default="liability"
            The account kind recorded as ``LineItem.kind``.
        counterparty : Entity, optional
            The other entity of the same model that holds the matching asset. It needs ``opening`` and does not take
            ``amount``, ``at``, or ``target``.
        actuals : dict, optional
            Historical closing balances for periods up to ``actual_until``, as ``{period: amount}``. Requires
            ``Model(..., actual_until=...)``.

        Returns
        -------
        LineItem
            The new line, whose value in each period is its closing balance. ``line.balance`` is the same series.

        Raises
        ------
        TypeError
            At construction, if both ``amount`` and ``target`` are given, or if ``counterparty`` is not an entity,
            is given without ``opening``, or is combined with ``amount``, ``target`` or ``at``.
        ValueError
            At construction, if a line of this kind with this name already exists, if ``cf`` is not a valid
            section, or if ``counterparty`` is this entity or belongs to another model.
        UnitError
            At construction, if an amount is in a unit other than the entity's currency.

        See Also
        --------
        boki.ledger.BS.asset : The generic asset.

        Notes
        -----
        ``amount`` books ``Dr cash, Cr liability``, and ``target`` books the cash entry that makes the closing balance
        equal the target. The default cash-flow section is operating.

        Examples
        --------
        An accrual held at 5, starting from 3, and a deposit received once in the second month:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> months = ["2027-01", "2027-02", "2027-03"]
        >>> m = b.Model("Liabilities", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> co.bs.opening(cash=100)
        >>> accrued = co.bs.liability("Accrued", target=5, opening=3)
        >>> deposit = co.bs.liability("Deposit", 30, at="2027-02")
        >>> r = m.render()
        >>> [round(r.value(accrued, month)) for month in months]
        [5, 5, 5]
        >>> [round(r.value(deposit, month)) for month in months]
        [0, 30, 30]
        >>> [round(r.value(co.bs.cash, month)) for month in months]
        [102, 132, 132]
        """  # noqa: DOC105, DOC107, DOC502
        return self._line(name, kind, "liability", amount, at, target, opening, cf or "operating", frozenset(tags),
                          counterparty=counterparty, actuals=actuals)

    def _line_kind(self, k: Kind):
        def create(name: str, amount=None, at=None, *, data: dict | None = None, target=None, opening=None,
                   cf: str | None = None, tags: Iterable[str] = (), counterparty=None,
                   actuals: dict | None = None) -> LineItem:
            if data is not None:
                if amount is not None:
                    raise TypeError(f"{name}: give an amount or data=, not both")
                amount = data
            return self._line(name, k.name, k.side, amount, at, target, opening, cf or k.cf,
                              k.tags | frozenset(tags), counterparty=counterparty, actuals=actuals)
        return create

    def _line(self, name, kind, side, amount, at, target, opening, cf, tags, *, counterparty=None,
              actuals: dict | None = None) -> LineItem:
        e = self._entity
        if amount is not None and target is not None:
            raise TypeError(f"{name}: give an amount or target=, not both")
        actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
        other = None
        counterpart_kind = counterpart_spec = opposite = None
        if counterparty is not None:
            other = _other_entity(name, e, counterparty)
            if opening is None or amount is not None or target is not None or at is not None:
                raise TypeError(f"{name}: a balance-sheet counterparty requires opening= and does not take amount= or target=")
            opposite = "liability" if side == "asset" else "asset"
            paired = {"receivable": "payable", "payable": "receivable",
                      "other_current_asset": "other_current_liability",
                      "other_current_liability": "other_current_asset"}.get(kind)
            candidates = [paired] if paired is not None else []
            candidates.append("other_liability" if side == "asset" else "other_asset")
            counterpart_kind = next((candidate for candidate in candidates
                                     if other.layout.bs_kind(candidate) is not None), opposite)
            counterpart_spec = other.layout.bs_kind(counterpart_kind)
        acct = e._account(name, side, kind, cf, tags=tags, opening=_opening(e, opening, name))
        acct.actuals = actuals_s
        balance = e._balance(acct)
        if target is not None:
            self._hold(acct, _amount(e, target, name), name)
        elif amount is not None:
            amt = _points(e, {at: amount}, name) if at is not None else _amount(e, amount, name)
            e._cash(name, amt, acct)
        item = LineItem(name, balance, e, kind, acct)
        item.balance = balance
        if other is not None:
            counterpart_cf = counterpart_spec.cf if counterpart_spec is not None else cf
            counterpart_tags = counterpart_spec.tags if counterpart_spec is not None else frozenset()
            other_name = f"{name} ({e.name})"
            other_account = other._account(other_name, opposite, counterpart_kind, counterpart_cf,
                                           tags=counterpart_tags,
                                           opening=_opening(other, opening, other_name))
            acct.mirror, other_account.mirror = other_account, acct
            other_item = LineItem(other_name, other._balance(other_account), other, counterpart_kind, other_account)
            other_item.balance = other_item.expr
            item.counterparty, other_item.counterparty = other_item, item
            counterpart_namespace = getattr(other.bs, counterpart_kind, None)
            if isinstance(counterpart_namespace, LineMaker):
                counterpart_namespace._items.append(other_item)
        return item

    def _hold(self, acct: Account, target: Series, name: str) -> Posting:
        e = self._entity
        gap = _Gap(e._balance(acct), target, f"{name} (change)")
        gap.posting = e._cash(gap.name, gap, acct)
        return gap.posting

    # -- mechanisms -------------------------------------------------------------------

    def _fixed_asset(self, k: Kind):
        def create(name: str, cost=None, at=None, *, life=None, method="straight",
                   salvage: Series | Quantity | float = 0, sell_at=None,
                   depreciation=None, opening=None, category: str = "Depreciation expense",
                   actuals: dict | None = None) -> LineItem:
            e = self._entity
            actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
            acct = e._account(name, "asset", k.name, k.cf, opening=_opening(e, opening, name))
            acct.actuals = actuals_s
            if cost is not None:
                spend = _points(e, {at: cost}, name) if at is not None else _amount(e, cost, name)
                e._post(f"{name} (acquired)", spend, debit=acct, credit=e._cash_account)
            book = e._balance(acct)
            if depreciation is not None:
                dep = _amount(e, depreciation, f"{name} depreciation")
            elif at is None and cost is not None and life is not None:
                dep = _program_depreciation(e.model, name, spend, life, method, salvage)
            else:
                if at is None or life is None:
                    raise TypeError(f"{k.name} needs at= and life= to compute depreciation (or pass depreciation=)")
                dep = _depreciation(e.model, name, book, at, life, method, lift(salvage))
            dep_line = e.pl.__dict__[e.layout.depreciation_kind](f"{name} depreciation", dep, against=acct,
                                                                 category=category)
            dep_line.account.tags |= {AMORTIZATION if k.name == "intangible" else DEPRECIATION}
            if sell_at is not None:
                if isinstance(sell_at, int):           # an expression, so the Excel export keeps a formula
                    proceeds = Named(f"{name} proceeds", (book.opening - dep_line).where(e.model.t == sell_at, 0))
                else:
                    def sold(t, _i=sell_at):
                        if t != evaluator.current().period_index(_i):
                            return 0
                        return book[t - 1] - dep_line[t]
                    proceeds = Fn(sold, name=f"{name} proceeds", unit=book.unit)
                e._post(f"{name} (sold)", proceeds, debit=e._cash_account, credit=acct)
            item = LineItem(name, book, e, k.name, acct)
            item.depreciation, item.book, item.balance = dep_line, book, book
            return item
        return create

    def _loan(self, k: Kind):
        def create(name: str, draw=None, rate: Series | Quantity | float | None = 0, repay=None, *,
                   opening=None, target=None,
                   capitalize_during=None, capitalize_into=None, counterparty=None,
                   net_investment: bool = False, actuals: dict | None = None) -> LineItem:
            e = self._entity
            actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
            if not isinstance(net_investment, bool):
                raise TypeError(f"{name}: net_investment= must be a boolean")
            if target is not None and (draw is not None or repay is not None):
                raise TypeError(f"{name}: target= sets the balance; leave out draw= and repay=")
            lender = None
            if counterparty is not None:
                lender = _other_entity(name, e, counterparty)
                if target is not None or capitalize_during is not None:
                    raise TypeError(f"{name}: a loan from another entity takes draw=, rate= and repay= "
                                    "(not target= or capitalize_during=) for now")
            elif net_investment:
                raise TypeError(f"{name}: net_investment= requires counterparty=")
            if capitalize_into is not None:
                if capitalize_during is None:
                    raise TypeError(f"{name}: capitalize_into= needs capitalize_during= (the periods to capitalize)")
                if not isinstance(capitalize_into, LineItem) or capitalize_into.kind != "construction" \
                        or capitalize_into.entity is not e:
                    raise TypeError(f"{name}: capitalize_into= takes a bs.construction line of {e.name}")
            lender_income = _finance_income(lender) if lender is not None and rate is not None else None
            acct = e._account(name, "liability", k.name, k.cf, opening=_opening(e, opening, name))
            acct.actuals = actuals_s
            balance = e._balance(acct)
            item = LineItem(name, balance, e, k.name, acct)
            item.balance = balance
            item.net_investment = net_investment
            prev = balance.opening
            if rate is None:
                interest = Named(f"{name}: interest", Const(0, literal=True))
            else:
                rate_s = lift(rate)
                per_period = rate_s * e.model.period_length if rate_s.unit is not None and MONTH_DIM in rate_s.unit \
                    else rate_s
                interest = Named(f"{name}: interest", per_period * prev)
            item.interest = interest
            repay_s = repay(item) if callable(repay) and not isinstance(repay, Series) else (0 if repay is None else repay)
            repay_s = _amount(e, repay_s, f"{name} repayment")
            item.principal = Named(f"{name}: principal", smin(repay_s, prev))
            item.draw = _points(e, draw, f"{name} draw") if draw is not None else Const(0, e._currency)
            mine, theirs = len(e._postings), len(lender._postings) if lender else 0
            if draw is not None:
                e._post(f"{name} (drawn)", item.draw, debit=e._cash_account, credit=acct)
            e._post(f"{name} (repaid)", item.principal, debit=acct, credit=e._cash_account)
            if lender is not None:
                made, made_item = _held_by(lender, f"{name} ({e.name})")
                made_item.net_investment = net_investment
                if opening is not None:
                    borrower_opening = _opening(e, opening, f"{name} ({e.name}) opening")
                    made.opening = e.model._convert_currency(
                        borrower_opening, e._currency, lender._currency, "opening")
                    acct.mirror, made.mirror = made, acct
                lender_draw = e.model._convert_currency(item.draw, e._currency, lender._currency)
                lender_principal = e.model._convert_currency(item.principal, e._currency, lender._currency)
                lender._post(f"{name} (lent)", lender_draw, debit=made, credit=lender._cash_account)
                lender._post(f"{name} (collected)", lender_principal, debit=lender._cash_account, credit=made)
                _tag(e, lender, mine, theirs)
                item.counterparty, made_item.counterparty = made_item, item
                if e._currency is not None and lender._currency is not None and e._currency != lender._currency:
                    translated_balance = e.model._convert_currency(
                        balance, e._currency, lender._currency, "closing")
                    opening_parent = made.opening if made.opening is not None else lift(0)
                    previous = translated_balance.lag(1, fill=opening_parent)
                    translated_movement = lender_draw - lender_principal
                    fx_change = translated_balance - previous - translated_movement
                    income_kind = next((candidate for candidate in
                                        ("other_income", "non_operating_income", "finance_income", "interest_income")
                                        if candidate in lender.layout.pl_kinds), None)
                    if income_kind is None:
                        raise ValueError(f"{lender.layout.name} has no income kind for loan FX differences")
                    fx_line = getattr(lender.pl, income_kind)(
                        f"Foreign exchange difference: {name} ({e.name})", fx_change,
                        against=made, category=f"Foreign exchange: {name}")
                    fx_post = lender._postings[-1]
                    fx_post.counterparty = e
                    fx_post.fx_remeasurement = True
                    fx_post.net_investment = net_investment
                    fx_line.counterparty = item

            def draw_or_repay(amount) -> LineItem:
                """Borrow or repay an amount in every period, with cash moving by the same amount.

                Use it when the borrowing follows from the cash position, such as a revolving facility. It posts in
                addition to ``draw=`` and ``repay=``; those are unchanged.

                Parameters
                ----------
                amount : scalar, Quantity, Series, or dict
                    Amount borrowed in each period, in the entity's currency per period: positive to draw, negative to
                    repay. A dict maps period labels or indices to amounts and books 0 in the other periods. A rate per
                    time, such as ``100 * JPY / b.month``, is integrated by period length.

                Returns
                -------
                LineItem
                    This loan line, so calls can be chained.

                Raises
                ------
                TypeError
                    At construction, if the loan is from another entity (created with ``counterparty=``).
                UnitError
                    At construction, if ``amount`` is in a unit other than the entity's currency.

                Notes
                -----
                Each period debits cash and credits the loan by ``amount`` (a negative amount reverses the entry), under
                the posting name ``<loan name> (net borrowing)``. The loan's balance includes it, so interest of later
                periods accrues on it, but the loan's ``draw`` and ``principal`` do not.

                Examples
                --------
                Draw 100 and 50, then repay 80, on a loan with no interest:

                >>> import boki as b
                >>> m = b.Model("Revolver", start="2027-01", periods=3, step=b.month)
                >>> co = m.entity("Co", standard=b.IFRS)
                >>> co.bs.opening(cash=1000)
                >>> loan = co.bs.loan("Revolver", rate=0)
                >>> _ = loan.draw_or_repay(m.series("Net", data={0: 100, 1: 50, 2: -80}))
                >>> r = m.render()
                >>> r[loan]
                [100.0, 150.0, 70.0]
                >>> r[co.bs.cash]
                [1100.0, 1150.0, 1070.0]
                """
                if lender is not None:
                    raise TypeError(f"{name}: draw_or_repay on a loan from another entity is not supported yet")
                e._cash(f"{name} (net borrowing)", _amount(e, amount, f"{name} net borrowing"), acct)
                return item
            item.draw_or_repay = draw_or_repay
            if target is not None:
                self._hold(acct, _amount(e, target, name), name)

            if rate is None:
                item.capitalized_interest = item.interest_expense = interest
                return item
            if capitalize_during is not None:
                capitalized = Named(f"{name}: capitalized interest", interest.where(capitalize_during, 0))
                into = capitalize_into.account if capitalize_into is not None else e._shared("construction")
                e._post(f"{name} interest (capitalized)", capitalized, debit=into,
                        credit=e._cash_account)
                expensed = interest - capitalized
            else:
                capitalized, expensed = Named(f"{name}: capitalized interest", interest * 0), interest
            item.capitalized_interest = capitalized
            paid_to = {"counterparty": lender_income} if lender_income is not None else {}
            item.interest_expense = e.pl.__dict__[e.layout.interest_kind](f"{name} interest", expensed,
                                                                          category="Interest expense", **paid_to)
            if lender is not None:
                item.interest_expense.counterparty.category = "Interest income"
            return item
        return create

    def _construction(self, k: Kind):
        def create(name: str, spend, complete_at=None, life=None, *, opening=None,
                   category: str = "Depreciation expense", actuals: dict | None = None) -> LineItem:
            e = self._entity
            actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
            acct = e._account(name, "asset", k.name, k.cf, opening=_opening(e, opening, name))
            acct.actuals = actuals_s
            spend_s = _amount(e, spend, name)
            e._post(f"{name} (spent)", spend_s, debit=acct, credit=e._cash_account)
            book = e._balance(acct)
            item = LineItem(name, book, e, k.name, acct)
            item.spend, item.balance = spend_s, book
            if complete_at is not None:
                if life is None:
                    raise TypeError("construction with complete_at= needs life=")
                from .model import _months
                from .units import month
                life_months = _months(life)
                if life_months <= 0:
                    raise ValueError(f"{name}: life must be positive, got {life_months} months")

                if isinstance(complete_at, int) and complete_at > 0:
                    cost = book[complete_at - 1]
                    dep_s = smin(cost * e.model.period_length / (life_months * month), book.opening).where(
                        e.model.t >= complete_at, 0)
                else:
                    def dep(t):
                        start = evaluator.current().period_index(complete_at)
                        if t < start:
                            return 0
                        cost = book[start - 1] if start > 0 else book.opening[0]
                        return min(cost * e.model.timeline.periods[t].months / life_months, book[t - 1])
                    dep_s = Fn(dep, name=f"{name}: depreciation", unit=book.unit)
                item.depreciation = e.pl.__dict__[e.layout.depreciation_kind](
                    f"{name} depreciation", dep_s, against=acct, category=category)
                item.depreciation.account.tags |= {DEPRECIATION}
            return item
        return create

    def _capital(self, k: Kind):
        def create(name: str, amount=None, at=None, *, opening=None, cf: str | None = None,
                   counterparty=None, fx_rate=None, actuals: dict | None = None) -> LineItem:
            e = self._entity
            actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
            if counterparty is not None:
                if actuals is not None:
                    raise TypeError(f"{name}: actuals= does not combine with counterparty=")
                owner = _other_entity(name, e, counterparty)
                if opening is not None:
                    if amount is not None or at is not None:
                        raise TypeError(f"{name}: opening capital cannot also take amount= or at=")
                    if fx_rate is not None:
                        raise TypeError(f"{name}: fx_rate= applies only to an in-period capital transaction")
                    item = create(name, opening=opening, cf=cf)
                    held, held_item = _held_by(owner, f"{e.name} shares", tags={SUBSIDIARY_INVESTMENT})
                    borrower_opening = _opening(e, opening, f"{e.name} shares")
                    held.opening = e.model._convert_currency(
                        borrower_opening, e._currency, owner._currency, "opening")
                    held.mirror = item.account
                    item.account.mirror = held
                    item.counterparty, held_item.counterparty = held_item, item
                    return item
                if amount is None:
                    raise TypeError(f"{name}: capital from another entity needs amount= or opening=")
                mine, theirs = len(e._postings), len(owner._postings)
                item = create(name, amount, at, cf=cf)
                child_post = e._postings[-1]
                paid = child_post.amount
                parent_amount = e.model._convert_currency(
                    paid, e._currency, owner._currency, rate=fx_rate)
                held, held_item = _held_by(owner, f"{e.name} shares", tags={SUBSIDIARY_INVESTMENT})
                owner._post(f"{name} ({e.name} shares)", parent_amount,
                            debit=held, credit=owner._cash_account)
                _tag(e, owner, mine, theirs)
                parent_post = owner._postings[-1]
                child_post.fx_rate = fx_rate
                child_post.counterpart, parent_post.counterpart = parent_post, child_post
                item.counterparty, held_item.counterparty = held_item, item
                item.account.mirror = held
                held.mirror = item.account
                return item
            acct = e._account(name, "equity", k.name, cf or k.cf, opening=_opening(e, opening, name))
            acct.actuals = actuals_s
            if fx_rate is not None:
                raise TypeError(f"{name}: fx_rate= requires counterparty=")
            if amount is not None:
                e._cash(name, _points(e, {at: amount}, name) if at is not None else _amount(e, amount, name), acct)
            item = LineItem(name, e._balance(acct), e, k.name, acct)
            item.balance = item.expr
            return item
        return create

    def _dividend(self, k: Kind):
        def create(name: str, amount, *, counterparty=None, fx_rate=None,
                   actuals: dict | None = None) -> LineItem:
            e = self._entity
            actuals_s = _parse_actuals(e, actuals, name) if actuals is not None else None
            amt = _amount(e, amount, name)
            if counterparty is not None:
                if actuals is not None:
                    raise TypeError(f"{name}: actuals= does not combine with counterparty=")
                owner = _other_entity(name, e, counterparty)
                income = _finance_income(owner)
                mine, theirs = len(e._postings), len(owner._postings)
                e._post(name, amt, debit=e.retained_earnings, credit=e._cash_account)
                paid = e._postings[-1]
                received_amount = e.model._convert_currency(
                    amt, e._currency, owner._currency, rate=fx_rate)
                received = income(f"{name} ({e.name})", received_amount)
                owner._associate_dividend_receipts.add(owner._postings[-1])
                _tag(e, owner, mine, theirs)
                received_post = owner._postings[-1]
                paid.fx_rate = fx_rate
                paid.counterpart, received_post.counterpart = received_post, paid
                item = LineItem(name, amt, e, k.name, e.retained_earnings)
                item.counterparty, received.counterparty = received, item
                return item
            if fx_rate is not None:
                raise TypeError(f"{name}: fx_rate= requires counterparty=")
            post = e._post(name, amt, debit=e.retained_earnings, credit=e._cash_account)
            e._external_dividends.add(post)
            item = LineItem(name, amt, e, k.name, e.retained_earnings)
            _apply_pl_actuals(item, actuals_s)
            return item
        return create


class _Depreciation(Series):
    """Depreciation of a fixed asset from its book value: straight-line on cost or double-declining, never
    below salvage. Starts the period after `at`."""

    def __init__(self, model, name, book: Series, at, life, method, salvage: Series):
        from .model import _months
        self.model, self.book, self.at, self.method, self.salvage = model, book, at, method, salvage
        self.life_months = _months(life)
        if self.life_months <= 0:
            raise ValueError(f"{name}: life must be positive, got {self.life_months} months")
        self.name = f"{name}: depreciation"

    @property
    def unit(self):
        return self.book.unit

    def method_at(self, r, t) -> str:
        m = r.value(self.method, None if self.method.scalar else t) if isinstance(self.method, Series) else self.method
        if m not in ("straight", "ddb"):
            raise ValueError(f"unknown depreciation method {m!r} (straight, ddb)")
        return m

    def _eval(self, r, t):
        start = r.period_index(self.at)
        if t <= start:
            return 0
        k = self.model.timeline.periods[t].months / self.life_months
        opening = r.value(self.book, t - 1)
        salvage = r.value(self.salvage, None if self.salvage.scalar else t)
        room = max(opening - salvage, 0)
        if self.method_at(r, t) == "straight":
            return min((r.value(self.book, start) - salvage) * k, room)
        return min(opening * 2 * k, room)


def _program_depreciation(model, name, spend: Series, life, method, salvage) -> Series:
    """A capex program (cost= a series, no at=): each period's spend is depreciated straight-line over
    life, starting the period after it is spent, as a single asset bought at= would be."""
    from .model import _months
    from .shapes import Kernel
    if spend.scalar:
        raise TypeError(f"{name}: a constant cost needs at= (one purchase); for a capex program give cost= a series "
                        "of spend per period")
    if method != "straight" or isinstance(salvage, Series) or getattr(salvage, "value", salvage) != 0:
        raise TypeError(f"{name}: a capex program (cost= a series without at=) depreciates straight-line to zero; "
                        "use one fixed_asset per purchase for other methods or salvage=")
    life_months = _months(life)
    if life_months <= 0:
        raise ValueError(f"{name}: life must be positive, got {life_months} months")
    lengths = {p.months for p in model.timeline.periods}
    if len(lengths) != 1:
        raise TypeError(f"{name}: a capex program needs periods of one length; with mixed lengths use one "
                        "fixed_asset per purchase, or pass depreciation=")
    n = life_months / lengths.pop()
    if abs(n - round(n)) > 1e-9:
        raise ValueError(f"{name}: life ({life_months} months) is not a whole number of periods")
    n = round(n)
    if model.actual_until is not None:
        spend = spend.where(model.is_forecast, 0)
    return spend.spread(Kernel([0.0] + [1.0 / n] * n, f"straight({n})"))


def _depreciation(model, name, book: Series, at, life, method, salvage: Series) -> Series:
    return _Depreciation(model, name, book, at, life, method, salvage)


class _Equity:
    """The equity namespace of a balance sheet, ``co.bs.equity``, which holds the equity total.

    Parameters
    ----------
    entity : Entity
        The entity whose equity it totals. Created by the balance sheet; user code does not construct it.

    Attributes
    ----------
    total : Series
        Equity at the end of each period, in the entity's currency: capital, retained earnings, other equity accounts,
        and the profit to date. It is the same value as ``co.bs.total_equity``.

    See Also
    --------
    boki.ledger.BS : The balance sheet, whose ``total_equity`` is the same total.

    Examples
    --------
    Equity grows by the profit of each period:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Equity", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=1000)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> r = m.render()
    >>> [round(r.value(co.bs.equity.total, month)) for month in ("2027-01", "2027-02")]
    [1100, 1200]
    """

    total: Series

    def __init__(self, entity: Entity):
        self._entity = entity
        self.total = _Total(lambda: [entity._equity_total], f"{entity.name}: equity", entity)


class _SideTotal(Series):
    """All balances on one side of the balance sheet (entity.bs.total_assets)."""

    def __init__(self, entity: "Entity", side: str):
        self.entity, self.side = entity, side
        self.name = f"{entity.name}: total {side}s"

    @property
    def unit(self):
        return self.entity._currency

    def _eval(self, r, t):
        e = self.entity
        return sum(r.value(e._balance(a), t) for a in e._accounts if a.side == self.side)


# ---- cash flow as series -----------------------------------------------------------

def cash_class(entity: "Entity", p: Posting) -> str | None:
    """The cash-flow class of a posting that moves cash (None if it does not)."""
    cash = entity._cash_account
    if cash not in (p.debit, p.credit) or p.debit is p.credit:
        return None
    if p.cf is not None:
        return p.cf
    other = p.credit if p.debit is cash else p.debit
    return "operating" if other.cf in ("pl", "operating") else other.cf


class _CashFlow(Series):
    def __init__(self, entity: "Entity", cls: str, exclude: frozenset = frozenset()):
        self.entity, self.cls, self.exclude = entity, cls, exclude
        self.name = f"{entity.name}: {cls} cash flow"

    @property
    def unit(self):
        return self.entity._currency

    def _eval(self, r, t):
        e = self.entity
        total = 0.0
        for p in e._postings:
            if cash_class(e, p) != self.cls or p.debit in self.exclude or p.credit in self.exclude:
                continue
            v = r.value(p.amount, None if p.amount.scalar else t) or 0
            total += v if p.debit is e._cash_account else -v
        return total


class CF:
    """The cash-flow statement of an entity as series, one for each section (direct method, from the ledger).

    Each section adds up the cash postings of the entity's ledger that the entity classified into it. The four
    sections together equal the change in cash in every period, which the render checks, along with the indirect
    method.

    Parameters
    ----------
    entity : Entity
        The entity the statement belongs to. Created by the entity; user code does not construct it.

    Attributes
    ----------
    operating : Series
        Cash received or paid for operations, in the entity's currency per period.
    investing : Series
        Cash received or paid for investments, such as fixed assets and subsidiary shares, in the entity's currency
        per period.
    financing : Series
        Cash received or paid for borrowing, equity, and dividends, in the entity's currency per period.
    fx : Series
        The effect of exchange rates on cash, in the entity's currency per period. It is 0 unless a journal entry is
        booked with ``cf="fx"``.

    See Also
    --------
    boki.ledger.CF.financing_excluding : Financing cash flow without some lines.

    Notes
    -----
    A posting that moves cash is classified by its ``cf`` if one was given (``Entity.journal(..., cf=...)`` or a line's
    ``cf=``). Otherwise it takes the class of the account on the other side: operating for profit-and-loss accounts and
    operating balance-sheet accounts, and the account's own class for the others (fixed assets investing, loans and
    capital financing). Receipts are positive and payments negative. See `the cash-flow rows
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#cash-flow-rows>`_.

    Examples
    --------
    A loan drawn in the first month and a machine bought in the same month, with sales of 50 a month:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Cash flow", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=100)
    >>> sales = co.pl.revenue("Sales", 50)
    >>> loan = co.bs.loan("Loan", draw={0: 500 * JPY})
    >>> machine = co.bs.fixed_asset("Machine", cost=200, at=0, life=4 * b.year)
    >>> r = m.render()
    >>> [round(r.value(co.cf.operating, month)) for month in ("2027-01", "2027-02")]
    [50, 50]
    >>> round(r.value(co.cf.investing, "2027-01")), round(r.value(co.cf.financing, "2027-01"))
    (-200, 500)
    >>> round(r.value(co.bs.cash, "2027-01"))
    450
    """

    operating: Series
    investing: Series
    financing: Series
    fx: Series

    def __init__(self, entity: Entity):
        self._entity = entity
        self.operating = _CashFlow(entity, "operating")
        self.investing = _CashFlow(entity, "investing")
        self.financing = _CashFlow(entity, "financing")
        self.fx = _CashFlow(entity, "fx")

    def financing_excluding(self, *items) -> Series:
        """Return the financing cash flow without the cash postings of some lines.

        Use it to size a line from the rest of financing, such as a revolver that borrows the shortfall.

        Parameters
        ----------
        *items : LineItem, balance, or Account
            The lines to leave out: line items, balances, or accounts of this entity's books, such as a revolver.
            Without any, the result equals ``cf.financing``.

        Returns
        -------
        Series
            Financing cash flow in each period, in the entity's currency per period, without the postings between
            cash and the given accounts.

        Raises
        ------
        TypeError
            At construction, if an item is not an account, a balance, or a line item.

        See Also
        --------
        boki.ledger.CF : The sections of the cash-flow statement.

        Examples
        --------
        Financing before the loan, in a model where the loan is drawn once and capital is paid in the second month:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> months = ["2027-01", "2027-02", "2027-03"]
        >>> m = b.Model("Financing", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> loan = co.bs.loan("Loan", draw={0: 500 * JPY}, repay={2: 100 * JPY})
        >>> shares = co.bs.capital("Shares", 20, at=1)
        >>> co.checks.cash(level="off")
        >>> r = m.render()
        >>> [round(r.value(co.cf.financing, month)) for month in months]
        [500, 20, -100]
        >>> [round(r.value(co.cf.financing_excluding(loan), month)) for month in months]
        [0, 20, 0]
        """  # noqa: DOC105, DOC106, DOC502
        return _CashFlow(self._entity, "financing", frozenset(_account_of(i) for i in items))


# ---- entity ----------------------------------------------------------------------

class _OpeningPlug(Series):
    """Opening retained earnings when none is given: whatever balances the opening sheet."""

    scalar = True

    def __init__(self, entity: "Entity"):
        self.entity = entity
        self.name = f"{entity.name}: opening retained earnings"

    @property
    def unit(self):
        return self.entity._currency

    def _eval(self, r, t):
        total = 0.0
        for a in self.entity._accounts:
            if a is self.entity.retained_earnings or a.opening is None:
                continue
            v = r.value(a.opening, None if a.opening.scalar else 0)
            total += v if a.side == "asset" else -v
        return total


class EntityChecks:
    """The checks an entity brings with it, configured through ``co.checks``.

    Every entity has one built-in check: cash must not be negative in any period. ``co.checks.cash(level=...)``
    sets how it is enforced. The check runs when the model renders, together with the checks you declare with
    ``Model.check``. Later built-in checks will join this object and are configured the same way.

    See Also
    --------
    boki.ledger.EntityChecks.cash : Set the level of the cash check.

    Notes
    -----
    A failed check at level ``"error"`` makes ``m.render()`` raise ``CheckFailed``, whose ``result`` attribute holds the
    complete `Result`. A failed check at level ``"warn"`` issues a warning and lets the render finish. A check at level
    ``"off"`` is not run.

    Examples
    --------
    An entity that pays rent from zero cash fails the default check:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Funding", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> rent = co.pl.sga("Rent", 100)
    >>> try:
    ...     m.render()
    ... except b.CheckFailed:
    ...     print("cash is negative")
    cash is negative
    >>> co.checks.cash(level="off")
    >>> r = m.render()
    """

    def __init__(self):
        self.cash_level = "error"

    def cash(self, level: str = "error") -> None:
        """Set how the check that cash does not go below zero is enforced.

        Every entity has this check at level ``"error"``, because a plan that spends money it does not have is not a
        plan. Declare ``"warn"`` when the plan is meant to show a funding gap (a source model with negative cash, or
        a gap the plan will finance later) and ``"off"`` to drop the check.

        Parameters
        ----------
        level : str, default="error"
            ``"error"`` makes ``m.render()`` raise ``CheckFailed`` when cash is below zero in any period,
            ``"warn"`` warns instead, and ``"off"`` does not run the check.

        Raises
        ------
        ValueError
            At construction, if ``level`` is not ``"error"``, ``"warn"`` or ``"off"``.

        Notes
        -----
        The check compares the closing cash balance of every period with zero, with a tolerance of 1e-9. It is
        reported in ``Result.checks`` as ``"<entity name>: cash is not negative"``. ``m.render(checks="warn")``
        turns every ``"error"`` check into a warning for that render without changing the level set here.

        Examples
        --------
        Turn the check off for a plan that is meant to show a funding gap; an invalid level is an error:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> m = b.Model("Funding", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> rent = co.pl.sga("Rent", 100)
        >>> co.checks.cash(level="off")
        >>> r = m.render()
        >>> r.checks
        []
        >>> co.checks.cash("loud")
        Traceback (most recent call last):
        ...
        ValueError: check level must be one of 'error', 'warn', 'off', not 'loud'
        """  # noqa: DOC105, DOC502
        from .model import check_level
        self.cash_level = check_level(level)


# ---- the parts of EBITDA -----------------------------------------------------------

_EBITDA_NOTES = """\
    EBITDA is a non-GAAP measure under J-GAAP, IFRS and US GAAP, so boki provides its parts and
    leaves the definition to the modeler. The standards differ in what goes into the parts:

    * **Goodwill.** J-GAAP amortizes it (up to 20 years, in SG&A), so J-GAAP EBITDA conventionally
      adds it back. IFRS and US GAAP do not amortize it (impairment only; US private companies may
      elect amortization).
    * **Impairment.** J-GAAP books it as an extraordinary loss, below operating income. IFRS and
      US GAAP book it within operating results, so adding it back is the modeler's choice. Neither
      ``depreciation`` nor ``amortization`` includes it.
    * **Leases.** boki has no lease accounting yet. IFRS 16 puts most leases on the balance sheet
      (depreciation plus interest), ASC 842 operating leases stay a straight-line operating cost,
      and J-GAAP's new lease standard is modeled on IFRS 16.
    * **Operating income.** Defined under J-GAAP. IFRS 18 (effective 2027-01-01) defines operating
      profit. US GAAP has no required subtotal.
    * **Development costs.** Capitalized under IFRS when the criteria are met (their amortization is
      in ``amortization``). Expensed under US GAAP and J-GAAP.
"""


def _parts_doc(summary: str, returns: str, raises: str = "", examples: str = ""):
    """Give a property of Entity or Group a docstring made of its summary, Returns, Raises, Examples and the shared notes.

    Parameters
    ----------
    summary : str
        The summary line, optionally followed by a blank line and an indented extended summary.
    returns : str
        Description of the returned Series, as one line.
    raises : str
        An indented Raises section, without the heading; empty for none.
    examples : str
        Indented doctest text, without the heading; empty for none.

    Returns
    -------
    Callable[[Callable], Callable]
        A decorator that sets the docstring of the property getter it wraps.
    """
    def apply(fn):
        parts = [summary, f"    Returns\n    -------\n    Series\n        {returns}"]
        if raises:
            parts.append(f"    Raises\n    ------\n{raises}")
        parts.append(f"    Notes\n    -----\n{_EBITDA_NOTES.rstrip()}")
        if examples:
            parts.append(f"    Examples\n    --------\n{examples}")
        fn.__doc__ = "\n\n".join(parts) + "\n    "
        return fn
    return apply


_NO_DEFINITION = {
    "ebitda": "EBITDA", "adjusted_ebitda": "Adjusted EBITDA", "ebitdar": "EBITDAR",
    "ebit": "EBIT", "noi": "NOI",
}


def no_default_measure(name: str, var: str) -> AttributeError:
    """The error for a measure boki refuses to define (`co.ebitda`, `co.noi`, ...), with how to build it.

    Parameters
    ----------
    name : str
        The attribute asked for; one of the keys of `_NO_DEFINITION`.
    var : str
        The name to use for the object in the example (``co`` for an entity, ``group`` for a group).

    Returns
    -------
    AttributeError
        The error to raise, whose message shows how to build the measure from the parts.

    Notes
    -----
    These measures have no standard definition (EBITDA is non-GAAP under all three standards), and
    a default would hide a choice that changes the number: goodwill, impairment, leases, one-offs.
    The message shows the parts instead (`depreciation`, `amortization`, `operating_income`).
    """
    label = _NO_DEFINITION[name]
    if name == "ebit":
        build = (f"EBIT has no standard definition (which non-operating items belong in it is a choice), so "
                 f"boki does not pick one. Build it from {var}.operating_income and the lines to adjust:\n"
                 f'  ebit = m.series("EBIT", {var}.operating_income + <other income you count> - <expenses you count>)')
    elif name == "noi":
        build = (f"NOI has no standard definition (it is a real-estate measure, and which costs count as "
                 f"operating is a choice), so boki does not pick one. Build it from revenue and operating "
                 f"expense lines:\n"
                 f'  noi = m.series("NOI", {var}.pl.revenue.total - <operating expense lines>)')
    else:
        build = (f"{label} has no standard definition, so boki does not pick one. Build it from parts:\n"
                 f'  ebitda = m.series("EBITDA", {var}.operating_income + {var}.depreciation + {var}.amortization)\n'
                 f"{var}.amortization includes goodwill amortization where goodwill is amortized (J-GAAP); "
                 f"impairment is not included.\n"
                 f"For covenant or adjusted EBITDA, add or subtract lines the same way.")
        if name == "ebitdar":
            build += "\nFor EBITDAR, also add the rent expense line."
    return AttributeError(build)


def _refusal(name: str, var: str):
    """The getter of a refused measure: it raises `no_default_measure`, with a docstring that says so."""
    label = _NO_DEFINITION[name]
    parts = {"ebit": "``operating_income`` and the lines you decide belong in EBIT",
             "noi": "revenue and operating expense lines",
             "ebitda": "``operating_income``, ``depreciation`` and ``amortization``",
             "adjusted_ebitda": "``operating_income``, ``depreciation``, ``amortization`` and the adjustments you choose",
             "ebitdar": "``operating_income``, ``depreciation``, ``amortization`` and the rent expense line"}[name]

    setup = "" if var == "co" else '    >>> group = m.group("Group", parent=co)\n'

    def refuse(self):
        raise no_default_measure(name, var)
    refuse.__name__ = name
    refuse.__doc__ = (
        f"{label}, which boki refuses to define.\n\n"
        f"    Reading this property always raises ``AttributeError``. {label} has no standard definition, and a default\n"
        f"    would hide choices that change the number (goodwill, impairment, leases, one-off items). Build it\n"
        f"    yourself as a named series from {parts}.\n\n"
        f"    Raises\n    ------\n    AttributeError\n"
        f"        Always, when the property is read. The message shows how to build the measure from the parts.\n\n"
        f"    See Also\n    --------\n"
        f"    {_parts_owner(var)}.operating_income : The operating income subtotal.\n"
        f"    {_parts_owner(var)}.depreciation : Depreciation of tangible assets.\n"
        f"    {_parts_owner(var)}.amortization : Amortization of intangible assets.\n\n"
        f"    Notes\n    -----\n{_EBITDA_NOTES}\n"
        f"    Examples\n    --------\n"
        f"    Reading the property raises ``AttributeError``:\n\n"
        f"    >>> import boki as b\n"
        f"    >>> from boki.units import JPY\n"
        f'    >>> m = b.Model("Parts", start="2027-01", periods=2, step=b.year)\n'
        f'    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)\n'
        f"{setup}"
        f"    >>> try:\n"
        f"    ...     {var}.{name}\n"
        f"    ... except AttributeError as error:\n"
        f'    ...     print(str(error).startswith("{label} has no standard definition"))\n'
        f"    True\n    ")
    return refuse


def _parts_owner(var: str) -> str:
    """The documented path of the class a measure belongs to: the entity or the group."""
    return "boki.ledger.Entity" if var == "co" else "boki.group.core.Group"


def refuse_default_measures(cls: type, var: str) -> None:
    """Make `cls.ebitda`, `.adjusted_ebitda`, `.ebitdar`, `.ebit` and `.noi` raise `no_default_measure`.

    Defined as properties rather than through ``__getattr__`` so that a property of the class that
    raises AttributeError (`operating_income` on a layout without one) keeps its own message.

    Parameters
    ----------
    cls : type
        The class to add the properties to.
    var : str
        The name to use for the object in the error message and the examples (``co`` or ``group``).
    """
    for name in _NO_DEFINITION:
        setattr(cls, name, property(_refusal(name, var)))


class Entity:
    """A company with its own books: one double-entry ledger, three statements, and the lines that fill them.

    ``m.entity(...)`` creates an entity and returns it, and ``co`` stands for one in these docs. The entity
    owns an account for cash and one for retained earnings; ``co.pl`` and ``co.bs`` hold one `LineMaker` for each kind
    in the entity's layout. Every line item posts balanced entries (an amount, a debit account, a credit account)
    to the ledger, and the balance sheet, the cash-flow statement, and their checks are derived from those
    entries. The entity's values are `Series` that you read from the result of ``m.render()``.

    Parameters
    ----------
    model : Model
        The model the entity belongs to. Created through ``Model.entity``, which also registers the entity there.
    name : str
        Entity name; required. It must be unique among the entities and groups of the model.
    standard : Standard
        Accounting standard, ``b.JGAAP``, ``b.IFRS`` or ``b.USGAAP``. It sets the general layout, the labels,
        and the standard-specific accounting. ``Model.entity`` uses ``b.JGAAP`` when it is not given.
    fiscal : Fiscal | None
        Fiscal calendar made by ``b.fiscal(...)``. Statements grouped ``by="fiscal_year"`` and the Excel statement
        columns use it. The default is ``None``, which means no fiscal calendar.
    layout : Layout | None
        Kinds and subtotals of the statements, such as ``b.layouts.bank``. The default is ``None``, the general layout
        of the standard.
    currency : Unit | None
        The functional currency, such as ``JPY``. The default is ``None``: the unit of the first amount booked sets
        it, and every later amount must be in the same unit.
    tax_rate : float | Series | Quantity | None
        Default tax rate for deferred tax (``bs.deferred_tax``) and taxed OCI (``oci(..., tax=True)``), a
        dimensionless ratio such as ``0.3`` for 30%. The default is ``None``, which makes those calls need their
        own ``rate=``.

    Attributes
    ----------
    model : Model
        The model the entity belongs to.
    name : str
        The entity's name.
    standard : Standard
        The accounting standard.
    fiscal : Fiscal or None
        The fiscal calendar, or ``None`` when the entity has none.
    layout : Layout
        The layout of kinds and subtotals in use.
    tax_rate : float, Series, Quantity, or None
        The default tax rate given at creation, or ``None``.
    pl : PL
        The income statement: one `LineMaker` for each PL kind of the layout, and the layout's subtotals as
        series.
    bs : BS
        The balance sheet: cash, one `LineMaker` for each BS kind of the layout, the totals, and the generic
        ``asset`` and ``liability`` makers.
    cf : CF
        The cash-flow statement as series, by section.
    checks : EntityChecks
        The entity's built-in check, for configuration.
    net_income : Series
        The period's net income, the same series as ``co.pl.net_income``. The unit is the entity's currency per
        period. Every layout needs a ``net_income`` subtotal, so ``Model.entity`` raises ``AttributeError``
        for a layout without one.
    other_comprehensive_income : Series
        The period's other comprehensive income (OCI) after tax: the sum of the lines that ``oci`` created, in the
        entity's currency per period. It is 0 when the entity has booked no OCI. This is the period total, not the
        balance (``bs.oci``) and not the booking call (``oci``).
    comprehensive_income : Series
        ``net_income`` plus ``other_comprehensive_income`` in each period.

    See Also
    --------
    boki.LineMaker : The callable behind every ``co.pl.<kind>`` and ``co.bs.<kind>``.

    Notes
    -----
    Creating an entity through ``Model.entity`` raises ``ValueError`` if the name is already used by an entity or group
    of the model, and ``AttributeError`` if the layout has no ``net_income`` subtotal.

    The ledger is double-entry, and the entity verifies it when the model renders: assets equal liabilities plus
    equity in every period, the opening balance sheet balances, cash-flow sections add up to the change in cash,
    and the indirect cash flow equals the direct one. A failure raises `LedgerError`. See the
    `double-entry notes <https://github.com/combinatrix-ai/boki/blob/master/docs/double-entry.md>`_ for the design and
    `consolidation <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md>`_ for how groups combine
    entity ledgers.

    Four names concern other comprehensive income, and they are four different things:

    * ``co.oci(name, amount, against=...)`` is a call that books one OCI item and returns its line;
    * ``co.bs.oci`` is the equity line maker of kind ``oci``, whose lines keep the accumulated OCI that is part of
      equity in their ``balance``;
    * ``co.other_comprehensive_income`` is the series of the period's total OCI, after tax;
    * ``co.oci_release(name, amount)`` is a call that reclassifies accumulated OCI to profit or retained earnings.

    Examples
    --------
    A monthly entity that earns 100 a month with 40 of costs, and its three statements:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Cafe", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("Cafe", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=1000)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> costs = co.pl.sga("Costs", 40)
    >>> r = m.render()
    >>> [r.value(co.net_income, month) for month in ("2027-01", "2027-02", "2027-03")]
    [60, 60, 60]
    >>> round(r.value(co.bs.cash, "2027-03"))
    1180
    >>> round(r.value(co.cf.operating, "2027-03"))
    60
    """  # noqa: DOC602, DOC603

    if TYPE_CHECKING:
        # The general layouts' makers are typed (see _makers.py); other layouts fall back to LineMaker.
        pl: GeneralPL
        bs: GeneralBS

    def __init__(self, model: Model, name: str, standard: Standard, fiscal: Fiscal | None = None,
                 layout: Layout | None = None, currency: Unit | None = None,
                 tax_rate: float | Series | Quantity | None = None):
        self.model, self.name, self.standard, self.fiscal = model, name, standard, fiscal
        self.tax_rate = tax_rate
        self.layout = layout or standard.general
        self._accounts: list[Account] = []
        self._postings: list[Posting] = []
        self._asset_trades: list[_AssetTrade] = []
        self._intercompany_trades: list[_IntercompanyTrade] = []
        self._external_dividends: set[Posting] = set()
        self._associate_dividend_receipts: set[Posting] = set()
        self._shared_accounts: dict[str, Account] = {}
        self._balances: dict[int, _Balance] = {}
        self._currency: Dims | None = getattr(currency, "dims", currency)
        self._currency_unit = currency if isinstance(currency, Unit) else None
        self._late: list[tuple[Named, Callable[[], Series]]] = []   # rebuilt once the currency is known
        self._vat_items: list[Series] = []
        self._deferred_tax_names: set[str] = set()
        self._deferred_tax_movements: list[Series] = []
        self._deferred_tax_expense: Account | None = None
        self._oci_components: dict[str, _OCIComponent] = {}
        self._cash_account = self._account("Cash", "asset", "cash", "cash")
        self.retained_earnings = self._account("Retained earnings", "equity", "retained_earnings", "financing")
        self.retained_earnings.opening = _OpeningPlug(self)
        self.pl = PL(self)  # type: ignore[assignment]
        self.net_income = self.pl.net_income
        self.other_comprehensive_income = _Total(
            lambda: [component.line for component in self._oci_components.values() if component.line is not None],
            f"{name}: other comprehensive income", self)
        self.comprehensive_income = Named(f"{name}: comprehensive income",
                                          self.net_income + self.other_comprehensive_income)
        self._late.append((self.comprehensive_income,
                           lambda: self.net_income + self.other_comprehensive_income))
        cum_source = self.net_income.where(model.is_forecast, 0) if model.actual_until is not None else self.net_income
        self._cum_profit = Named(f"{name}: cumulative profit", cum_source.cumsum())
        self._late.append((
            self._cum_profit,
            lambda: (self.net_income.where(model.is_forecast, 0) if model.actual_until is not None
                     else self.net_income).cumsum(),
        ))
        self._equity_total = _EquityTotal(self)
        self.bs = BS(self)  # type: ignore[assignment]
        self.cf = CF(self)
        self.checks = EntityChecks()

    def __repr__(self):
        return f"<Entity {self.name} ({self.standard.name}, {self.layout.name})>"

    @property
    def currency(self) -> Unit | frozenset | None:
        """The entity's functional currency.

        Returns
        -------
        Unit | frozenset | None
            The `Unit` given as ``currency=`` when the entity was created. Otherwise the dimensions of the unit
            of the first amount booked, as an opaque ``frozenset``, or ``None`` while no amount has been booked.
            Every later amount must be in the same currency.

        Examples
        --------
        The unit of the first amount sets the currency when none was declared:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> m = b.Model("Currency", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS)
        >>> co.currency is None
        True
        >>> sales = co.pl.revenue("Sales", 100 * JPY)
        >>> co.currency == JPY.dims
        True
        >>> m.entity("B", standard=b.IFRS, currency=JPY).currency is JPY
        True
        """
        return self._currency_unit if self._currency_unit is not None else self._currency

    @property
    def language(self) -> str:
        """The language of the entity's statement labels.

        Returns
        -------
        str
            ``"en"`` for every standard: all labels are English.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Language", start="2027-01", periods=2, step=b.year)
        >>> m.entity("A", standard=b.JGAAP).language
        'en'
        """
        return "en"

    def label(self, key: str) -> str:
        """Return the presentation name of a kind, subtotal, or statement line.

        The standard's own term comes first (IFRS says "Profit for the year"), then the common English name. A
        key that has no name is returned unchanged.

        Parameters
        ----------
        key : str
            The internal name, such as ``"gross_profit"``, ``"net_income"``, ``"receivable"``, or ``"total_assets"``.

        Returns
        -------
        str
            The name the statements show for ``key`` under this entity's standard, or ``key`` when it has none.

        See Also
        --------
        boki.Style : Statement titles and labels in the Excel output come from the style.

        Examples
        --------
        The same key has a different name under each standard:

        >>> import boki as b
        >>> m = b.Model("Labels", start="2027-01", periods=1, step=b.year)
        >>> m.entity("A", standard=b.IFRS).label("net_income")
        'Profit for the year'
        >>> m.entity("B", standard=b.USGAAP).label("net_income")
        'Net income'
        >>> m.entity("C", standard=b.IFRS).label("not_a_line")
        'not_a_line'
        """
        from .styles import Style
        return Style("text", language=self.language).label(key, self.standard)

    @property
    @_parts_doc("The layout's operating income subtotal, the same series as ``co.pl.operating_income``.",
                "Operating income in each period, in the entity's currency per period.",
                raises="    AttributeError\n        At construction, when the property is read on a layout without an operating income\n"
                       "        subtotal, such as the bank layout.",
                examples="    Operating income is the subtotal before finance items and tax, here sales less costs:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Operating", start="2027-01", periods=2, step=b.month)\n'
                         '    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)\n'
                         '    >>> sales = co.pl.revenue("Sales", 100)\n'
                         '    >>> costs = co.pl.sga("Costs", 30)\n'
                         "    >>> r = m.render()\n"
                         '    >>> r.value(co.operating_income, "2027-01")\n'
                         "    70")
    def operating_income(self) -> Series:
        stage = next((s for s in self.layout.stages if s.name == "operating_income"), None)
        if stage is None:
            raise AttributeError(f"the {self.layout.name} layout has no operating income subtotal")
        return self.pl.operating_income

    def _depreciation_of(self, tag: str, name: str) -> Series:
        def lines():
            found = []
            for kind in self.layout.pl_kinds:
                for line in getattr(self.pl, kind).items:
                    account = getattr(line, "account", None)
                    if account is None:
                        continue
                    if tag in account.tags:
                        found.append(line)                     # the whole account is depreciation
                    else:                                      # a statement line shared with other items
                        found.extend(p.amount for p in account.debits if p.da == tag)
                        found.extend(-p.amount for p in account.credits if p.da == tag)
            return found
        return _Total(lines, f"{self.name}: {name}", self)

    @property
    @_parts_doc("Depreciation of tangible assets, as a Series of positive expense.\n\n"
                "    Every ``fixed_asset`` line that is not ``intangible`` and every completed ``construction``\n"
                "    line, wherever the expense is posted in the PL (any PL kind, any ``category=``,\n"
                "    ``depreciation=`` given directly, a capex program, an intercompany asset purchase).\n"
                "    The assets decide, not the PL line: use this instead of summing a category.\n"
                "    Impairment and losses on sale are not included.",
                "Depreciation expense in each period, positive, in the entity's currency per period.",
                examples="    A machine bought in the first month for 600 and depreciated over six months starts\n"
                         "    to depreciate in the next month, 100 a month:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Depreciation", start="2027-01", periods=4, step=b.month)\n'
                         '    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)\n'
                         "    >>> co.bs.opening(cash=1000)\n"
                         '    >>> machine = co.bs.fixed_asset("Machine", cost=600, at=0, life=6 * b.month)\n'
                         "    >>> r = m.render()\n"
                         '    >>> [round(r.value(co.depreciation, month)) for month in ("2027-01", "2027-02", "2027-03")]\n'
                         "    [0, 100, 100]")
    def depreciation(self) -> Series:
        return self._depreciation_of(DEPRECIATION, "depreciation")

    @property
    @_parts_doc("Amortization of intangible assets, as a Series of positive expense.\n\n"
                "    The same as ``depreciation`` for ``intangible`` lines. Impairment is not included. On a\n"
                "    consolidated group (``Group.amortization``) it also holds goodwill amortization.",
                "Amortization expense in each period, positive, in the entity's currency per period.",
                examples="    Software bought in the first month for 300 and amortized over three months:\n\n"
                         "    >>> import boki as b\n"
                         "    >>> from boki.units import JPY\n"
                         '    >>> m = b.Model("Amortization", start="2027-01", periods=4, step=b.month)\n'
                         '    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)\n'
                         "    >>> co.bs.opening(cash=1000)\n"
                         '    >>> software = co.bs.intangible("Software", cost=300, at=0, life=3 * b.month)\n'
                         "    >>> r = m.render()\n"
                         '    >>> [round(r.value(co.amortization, month)) for month in ("2027-01", "2027-02", "2027-03")]\n'
                         "    [0, 100, 100]\n"
                         "    >>> round(r.value(co.depreciation, \"2027-02\"))\n"
                         "    0")
    def amortization(self) -> Series:
        return self._depreciation_of(AMORTIZATION, "amortization")

    def _account_name(self, account: "Account") -> str:
        """An account as shown: accounts boki opens itself take the standard's term ('Cash'), others keep theirs."""
        if account.kind in ("deferred_tax_asset", "deferred_tax_liability"):
            return f"{self.label(account.kind)}: {account.category or account.name}"
        if account.kind == "oci":
            return f"{self.label('oci')}: {account.name}"
        from .styles import AUTOMATIC
        if account.kind in AUTOMATIC and account.name == AUTOMATIC_NAMES.get(account.kind):
            return self.label(account.kind)
        return account.name

    def journal(self, name: str, amount, *, debit, credit, cf: str | None = None) -> Series:
        """Post an amount from one account of the entity to another.

        Use it for entries no line maker books: a transfer between two balance-sheet accounts (a deposit turned into
        income, a lease asset and liability), or a cash posting that needs its own cash-flow class. The entry
        debits ``debit`` and credits ``credit`` by ``amount`` in every period.

        Parameters
        ----------
        name : str
            Name of the entry. It names the returned series and the posting (the narration of the Beancount
            transaction). Required.
        amount : scalar, Quantity, Series, or dict
            Amount posted in each period, in the entity's currency per period. A plain number is in the entity's
            currency. A quantity per time, such as ``100 * JPY / b.month``, is integrated by period length. A dict
            maps period labels, indices, or dates to amounts and posts 0 in the other periods.
        debit : LineItem, balance, or Account
            The account to debit, from this entity's books: a line item, a balance such as ``co.bs.cash``, or an
            account.
        credit : LineItem, balance, or Account
            The account to credit, with the same forms as ``debit``.
        cf : str, optional
            Cash-flow section of the entry when it moves cash: ``"operating"``, ``"investing"``, ``"financing"``, or
            ``"fx"``. It is ignored when the entry does not touch cash. When it is omitted, a cash entry takes the
            section of the other account (operating for a PL account).

        Returns
        -------
        Series
            The amount posted in each period, named ``name``.

        Raises
        ------
        ValueError
            At construction, if ``cf`` is not one of the four sections, or if ``debit`` or ``credit`` is an account
            of another entity (a trade with another entity is booked with ``counterparty=`` on a line instead).
        TypeError
            At construction, if ``debit`` or ``credit`` is not an account, a balance, or a line item, or if
            ``amount`` has a type boki cannot use in an expression.
        UnitError
            At construction, if ``amount`` is in a unit other than the entity's currency.

        See Also
        --------
        boki.ledger.BS.opening : Declare opening balances instead of posting changes.

        Notes
        -----
        The entry is ``Dr debit, Cr credit``, with no cash involved unless one of the accounts is cash. When an
        account is a PL line, the entry changes that line's value, and so the profit: crediting an income line
        or debiting an expense line adds to it, and the opposite entries reduce it. Journal entries on the
        balance sheet alone do not change profit. A cash entry is classified by ``cf``; see
        `the cash-flow rows <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#cash-flow-rows>`_.

        Examples
        --------
        A customer forfeits a deposit of 10 in the first month, which moves it from the liability into income:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> m = b.Model("Journal", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> co.bs.opening(cash=100)
        >>> deposit = co.bs.liability("Deposit", opening=100)
        >>> fees = co.pl.revenue("Fees", 5)
        >>> entry = co.journal("Forfeited deposit", {0: 10}, debit=deposit, credit=fees)
        >>> r = m.render()
        >>> round(r.value(deposit, "2027-01")), round(r.value(deposit, "2027-02"))
        (90, 90)
        >>> r.value(fees, "2027-01"), r.value(fees, "2027-02")
        (15, 5)
        >>> r.value(co.net_income, "2027-01")
        15
        """  # noqa: DOC105, DOC107, DOC503
        if cf is not None and cf not in CF_CLASSES:
            raise ValueError(f"cf= must be one of {', '.join(CF_CLASSES)}")
        amt = Named(name, _amount(self, amount, name))
        debit, credit = _account_of(debit), _account_of(credit)
        self._post(name, amt, debit, credit, cf=cf)
        # A PL line's value is its own amount; a journal into its account changes the profit too.
        for account, debited in ((debit, True), (credit, False)):
            if account.cf == "pl":
                line = next(i for kind in self.layout.pl_kinds for i in getattr(self.pl, kind).items if i.account is account)
                expr = line.expr + amt if debited == (account.side == "expense") else line.expr - amt
                line.expr = None
                line.define(expr)
        return amt

    def _vat_line(self, name: str, amount: Series, rate, income: bool, paid: Series | None) -> None:
        """VAT on a line (tax-exclusive bookkeeping): collected on sales, paid on purchases, held in one account
        until co.vat_settlement pays the net amount. The VAT cash follows the line's own cash timing."""
        vat = self._shared("vat")
        tax = Named(f"{name} (VAT)", amount * rate)
        deferred = paid is not None
        counter = self._shared("receivable" if income else "payable") if deferred else self._cash_account
        if income:
            self._post(f"{name} (VAT collected)", tax, debit=counter, credit=vat)
        else:
            self._post(f"{name} (VAT paid)", tax, debit=vat, credit=counter)
        if deferred:
            settled = paid * rate
            if income:
                self._post(f"{name} (VAT collected, cash)", settled, debit=self._cash_account, credit=counter)
            else:
                self._post(f"{name} (VAT paid, cash)", settled, debit=counter, credit=self._cash_account)
        self._vat_items.append(tax if income else -tax)

    def vat_settlement(self, settle: Kernel, name: str = "VAT settlement") -> Series:
        """Pay the net value-added tax of each period to the tax authority on a schedule.

        Lines declared with ``vat=`` collect or pay tax and hold it in one shared VAT account. This call pays that
        account out in cash: each period's net VAT (collected minus paid) is paid according to ``settle``. Lines
        declared after this call are included.

        Parameters
        ----------
        settle : Kernel
            When the net VAT of a period is paid, as the share paid in each period from that period on:
            ``b.delay(1)`` pays it in the next period and ``b.even(2)`` pays half in the period itself and half in the
            next. The weights must sum to 1, and a ``b.curve`` must end in 0.
        name : str, default="VAT settlement"
            Name of the payment series and of the posting.

        Returns
        -------
        Series
            The cash paid to the tax authority in each period, in the entity's currency per period, named ``name``.
            It is negative in a period when more VAT was paid than collected earlier, which is a refund.

        Raises
        ------
        ValueError
            At construction, if ``settle`` is not a distribution: weights that are not finite, weights that do not
            sum to 1, or a ``b.curve`` that does not end in 0.

        See Also
        --------
        boki.LineMaker : ``vat=`` on a line books the tax that this call pays.

        Notes
        -----
        boki uses tax-exclusive accounting: a line stays net of tax, and ``vat=`` books the tax beside it in the
        shared ``VAT payable (net)`` account, with the cash timing of the line. Tax collected on a revenue line is
        ``Dr cash (or receivable), Cr VAT payable``, and tax paid on an expense line is ``Dr VAT payable, Cr cash
        (or payable)``. This call posts ``Dr VAT payable, Cr cash`` for the payment, an operating cash flow. The
        VAT account is a liability that is negative while a refund is due. See `net-of-tax accounting
        <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#p-l-rows-japanese-gaap>`_.

        Examples
        --------
        Sales of 1,000 and purchases of 400 each month, both with 10% VAT. The net VAT of 60 a month is paid one month
        later, so the first payment is in the second month:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> months = ["2027-01", "2027-02", "2027-03"]
        >>> m = b.Model("VAT", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> co.bs.opening(cash=1000)
        >>> sales = co.pl.revenue("Sales", 1000, vat=0.1)
        >>> purchases = co.pl.cogs("Purchases", 400, vat=0.1)
        >>> payment = co.vat_settlement(settle=b.delay(1))
        >>> r = m.render()
        >>> [round(r.value(payment, month)) for month in months]
        [0, 60, 60]
        >>> [round(r.value(co.bs.cash, month)) for month in months]
        [1660, 2260, 2860]
        """  # noqa: DOC105, DOC502
        _check_kernel_distribution(settle, "settle= of the VAT settlement")
        net = _Total(lambda: list(self._vat_items), "net VAT", self)
        payment = Named(name, net.spread(settle))
        self._post(name, payment, debit=self._shared("vat"), credit=self._cash_account)
        return payment

    def _tax_rate(self, rate, what: str) -> Series:
        rate = self.tax_rate if rate is None else rate
        if rate is None:
            raise ValueError(f"{self.name}: {what} needs rate= or tax_rate= on the entity")
        rate = lift(rate)
        if rate.unit not in (None, _DIMENSIONLESS):
            raise UnitError(f"{self.name}: {what} rate must be dimensionless")
        return rate

    def _tax_accounts(self, name: str, difference: Series, rate: Series, recognized: Series, cf: str):
        taxable = Named(f"{name}: taxable temporary difference", rate * smax(difference, 0))
        deductible = Named(f"{name}: deductible temporary difference",
                           rate * recognized * smax(-difference, 0))
        liability_change, asset_change = taxable.change, deductible.change
        liability = self._tax_account(name, "deferred_tax_liability", "liability", cf)
        asset = self._tax_account(name, "deferred_tax_asset", "asset", cf)
        return asset, liability, asset_change, liability_change

    def _tax_account(self, name: str, kind: str, side: str, cf: str) -> Account:
        account = self._account(f"{name} ({kind.replace('_', ' ')})", side, kind, cf, category=name)
        namespace = getattr(self.bs, kind, None)
        if isinstance(namespace, LineMaker):
            balance = self._balance(account)
            item = LineItem(name, balance, self, kind, account)
            item.balance = balance
            namespace._items.append(item)
        return account

    def _deferred_tax_line(self) -> Account:
        if self._deferred_tax_expense is None:
            self._deferred_tax_expense = self._account("deferred tax adjustments", "expense", "income_tax", "pl")
            amount = _Total(lambda: self._deferred_tax_movements, self.label("deferred_tax"), self)
            line = LineItem(self.label("deferred_tax"), amount, self, "income_tax", self._deferred_tax_expense)
            self.pl.income_tax._items.append(line)
        return self._deferred_tax_expense

    def _deferred_tax(self, name: str, difference, rate=None, recognized=1.0) -> None:
        if name in self._deferred_tax_names:
            raise ValueError(f"{self.name} already has deferred tax named {name!r}")
        rate = self._tax_rate(rate, f"deferred tax {name!r}")
        recognized = lift(recognized)
        if recognized.unit not in (None, _DIMENSIONLESS):
            raise UnitError(f"{self.name}: deferred tax {name!r} recognized= must be dimensionless")
        difference = _points(self, difference, name)
        asset, liability, asset_change, liability_change = self._tax_accounts(
            name, difference, rate, recognized, "operating")
        tax_expense = self._deferred_tax_line()
        self._deferred_tax_names.add(name)
        self._deferred_tax_movements.append(liability_change - asset_change)
        self._post(f"{name} deferred tax liability", liability_change, debit=tax_expense, credit=liability)
        self._post(f"{name} deferred tax asset", -asset_change, debit=tax_expense, credit=asset)

    def oci(self, name: str, amount, *, against, recycle: bool = True, tax: bool = False) -> LineItem:
        """Book an item of other comprehensive income (OCI) and return its line.

        The item moves ``amount`` in every period between the account ``against`` (a security, a hedge, a pension
        asset) and a reserve in equity named ``name``, and the profit is untouched. Several calls with one name
        add to the same reserve.

        Parameters
        ----------
        name : str
            Name of the OCI component, which names the equity reserve. Required. A name used before adds to that
            component, and it must be given the same ``recycle`` and ``tax``.
        amount : scalar, Quantity, Series, or dict
            OCI arising in each period before tax, in the entity's currency per period; a loss is negative. A
            plain number is in the entity's currency. A quantity per time is integrated by period length. A dict
            maps period labels, indices, or dates to amounts and books 0 in the other periods.
        against : LineItem, balance, or Account
            The account of this entity's books that takes the other side of the entry, such as a ``co.bs`` line for a
            security. It is debited by ``amount``. A PL line is allowed: its value falls by ``amount``, which moves the
            amount from net income into OCI.
        recycle : bool, default=True
            Whether the reserve is later reclassified to profit (``True``) or transferred to retained earnings
            (``False``) by ``oci_release``. It only takes effect there.
        tax : bool, default=False
            Whether to recognize deferred tax on the OCI at the entity's ``tax_rate`` and show the OCI net of tax.

        Returns
        -------
        LineItem
            The component's line, of kind ``oci``. Its value in a period is the OCI after tax, and its ``balance``
            is the accumulated reserve after tax. Another call with the same ``name`` returns the same line.

        Raises
        ------
        ValueError
            At construction, if ``against`` is an account of another entity, if ``tax`` is true and the entity has
            no ``tax_rate``, or if ``name`` was used before with a different ``recycle`` or ``tax``.
        TypeError
            At construction, if ``against`` is not an account, a balance, or a line item, or if ``amount`` has a
            type boki cannot use in an expression.
        UnitError
            At construction, if ``amount`` is in a unit other than the entity's currency, or the tax rate is not
            dimensionless.

        See Also
        --------
        boki.ledger.Entity.oci_release : Reclassify accumulated OCI to profit or retained earnings.
        boki.LineMaker : ``co.bs.oci`` is the line maker of kind ``oci``, whose lines are the ones this call returns.

        Notes
        -----
        The entry is ``Dr against, Cr reserve``. The reserve is an equity account of kind ``oci``, shown as
        "Other components of equity" under IFRS and "Accumulated other comprehensive income" under US GAAP and
        J-GAAP. With ``tax=True``, deferred tax is recognized on the cumulative pre-tax OCI at the entity's
        ``tax_rate``: a deferred tax liability while the cumulative amount is positive (``Dr reserve, Cr deferred tax
        liability``) and a deferred tax asset while it is negative. The tax is charged to equity, so profit and cash do
        not change.

        The period's OCI after tax is also in ``co.other_comprehensive_income``, and ``co.comprehensive_income`` adds
        it to net income. Statements show OCI and comprehensive income below net income once the entity has OCI.
        Whether an item is recycled is a matter of the accounting standard; for example IFRS FVOCI equity
        instruments and defined-benefit remeasurements are not recycled. See
        `S1: tax effects and OCI <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md#other-comprehensive-income-oci>`_.

        Examples
        --------
        A gain of 100 on a security in the first year and a loss of 40 in the third, taxed at 30%:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> years = ["2027", "2028", "2029"]
        >>> m = b.Model("OCI", start="2027-01", periods=3, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY, tax_rate=0.3)
        >>> security = co.bs.other_asset("Security", opening=0)
        >>> reserve = co.oci("Fair value reserve", {0: 100, 2: -40}, against=security, tax=True)
        >>> r = m.render()
        >>> [round(r.value(reserve, year)) for year in years]
        [70, 0, -28]
        >>> [round(r.value(reserve.balance, year)) for year in years]
        [70, 70, 42]
        >>> [round(r.value(co.net_income, year)) for year in years]
        [0, 0, 0]
        >>> [round(r.value(co.comprehensive_income, year)) for year in years]
        [70, 0, -28]
        """  # noqa: DOC105, DOC107, DOC503
        target = _account_of(against)
        if target.entity is not self:
            raise ValueError(f"{name}: against= must be an account in {self.name}'s books")
        rate = self._tax_rate(None, f"OCI {name!r}") if tax else None
        amount = _amount(self, amount, name)
        component = self._oci_components.get(name)
        if component is None:
            account = self._account(name, "equity", "oci", "financing")
            component = _OCIComponent(name, account, recycle, tax)
            self._oci_components[name] = component
        elif component.recycle != recycle or component.taxed != tax:
            raise ValueError(f"OCI {name!r} already has recycle={component.recycle} and tax={component.taxed}")

        component.amounts.append(amount)
        self.journal(name, amount, debit=target, credit=component.account)
        total = _Total(lambda c=component: c.amounts, name, self)
        if tax:
            component.tax_basis.append(amount)
        if tax and component.tax_liability is None:
            tax_basis = _Total(lambda c=component: c.tax_basis, f"{name} OCI tax basis", self)
            cumulative = Named(f"{name}: cumulative OCI tax basis", tax_basis.cumsum())
            asset, liability, asset_change, liability_change = self._tax_accounts(
                f"{name} OCI", cumulative, rate, lift(1.0), "financing")
            component.tax_asset, component.tax_liability = asset, liability
            component.tax_rate = rate
            self._post(f"{name} OCI deferred tax liability", liability_change,
                       debit=component.account, credit=liability)
            self._post(f"{name} OCI deferred tax asset", asset_change,
                       debit=asset, credit=component.account)

        if component.line is None:
            after_tax = total
            if component.taxed:
                cumulative = Named(f"{name}: cumulative reported OCI before tax", total.cumsum())
                taxable = Named(f"{name}: reported OCI taxable difference",
                                component.tax_rate * smax(cumulative, 0))
                deductible = Named(f"{name}: reported OCI deductible difference",
                                   component.tax_rate * smax(-cumulative, 0))
                after_tax = total - taxable.change + deductible.change
            component.line = LineItem(name, after_tax, self, "oci", component.account)
            component.line.balance = self._balance(component.account)
            namespace = getattr(self.bs, "oci", None)
            if isinstance(namespace, LineMaker):
                namespace._items.append(component.line)
        return component.line

    def oci_release(self, name: str, amount) -> Series:
        """Reclassify accumulated OCI of a component to profit or to retained earnings.

        Call it when the item behind an OCI component is sold or settled. A component booked with
        ``recycle=True`` moves the amount into profit, and one booked with ``recycle=False`` moves it to retained
        earnings. Neither moves cash.

        Parameters
        ----------
        name : str
            Name of an OCI component created by ``oci``. Required.
        amount : scalar, Quantity, Series, or dict
            Amount released in each period, before tax, in the entity's currency per period, with the forms of the
            ``amount`` of ``oci``. A dict books 0 in the other periods.

        Returns
        -------
        Series
            For a recycled component, the new profit line named ``OCI release: <name>``, a `LineItem` whose value
            is the amount released into profit. For a component that is not recycled, the released amount.

        Raises
        ------
        ValueError
            At construction, if the entity has no OCI component called ``name``, if a recycled component was
            released before (the profit line ``OCI release: <name>`` already exists), or if a recycled component
            is released on a layout without a non-revenue income kind.
        TypeError
            At construction, if ``amount`` has a type boki cannot use in an expression.
        UnitError
            At construction, if ``amount`` is in a unit other than the entity's currency.

        See Also
        --------
        boki.ledger.Entity.oci : Book the OCI that this call releases.

        Notes
        -----
        A recycled release is booked as a profit line against the reserve, ``Dr reserve, Cr income``. The line goes to
        the first of ``other_income``, ``non_operating_income``, ``non_interest_income``, ``special_gain`` and
        ``finance_income`` that the layout has (``other_income`` for IFRS and US GAAP, ``non_operating_income`` for
        J-GAAP, ``non_interest_income`` for the bank layout). The period's OCI falls by the amount, so
        before tax the transfer leaves comprehensive income unchanged. A release that is not recycled is ``Dr reserve, Cr
        retained earnings`` and is a transfer inside equity.

        The amount is before tax. With ``tax=True`` on the component, the deferred tax on the released amount is
        reversed and the reserve falls by the after-tax amount. A recycled release does not book the realized tax
        for you: record it in an income tax line. See the OCI tax rules in `S1
        <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md#other-comprehensive-income-oci>`_.

        Examples
        --------
        A gain of 100 is booked in the first year and released into profit in the second:

        >>> import boki as b
        >>> from boki.units import JPY
        >>> years = ["2027", "2028", "2029"]
        >>> m = b.Model("Release", start="2027-01", periods=3, step=b.year)
        >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
        >>> security = co.bs.other_asset("Security", opening=0)
        >>> reserve = co.oci("Fair value reserve", {0: 100}, against=security)
        >>> released = co.oci_release("Fair value reserve", {1: 100})
        >>> r = m.render()
        >>> [round(r.value(co.net_income, year)) for year in years]
        [0, 100, 0]
        >>> [round(r.value(co.other_comprehensive_income, year)) for year in years]
        [100, -100, 0]
        >>> [round(r.value(co.comprehensive_income, year)) for year in years]
        [100, 0, 0]
        """  # noqa: DOC105, DOC107, DOC503
        component = self._oci_components.get(name)
        if component is None:
            raise ValueError(f"{self.name} has no OCI component named {name!r}")

        amount = _amount(self, amount, f"{name} OCI release")
        if component.taxed:
            component.tax_basis.append(-amount)
        if component.recycle:
            preferred = ("other_income", "non_operating_income", "non_interest_income", "special_gain",
                         "finance_income")
            kind = next((k for k in preferred if k in self.layout.income_kinds), None)
            if kind is None:
                raise ValueError(f"{self.layout.name} has no non-revenue income kind for OCI recycling")
            component.amounts.append(-amount)
            item = getattr(self.pl, kind)(f"OCI release: {name}", amount, against=component.account)
            return item

        self._post(f"OCI release: {name}", amount, debit=component.account, credit=self.retained_earnings)
        return amount

    def _check_currency(self, unit: Dims, what: str) -> None:
        if self._currency is None:
            self._currency = unit
            # Subtotals built before the currency was known had no unit; rebuild them so unit checks apply.
            for node, build in self._late:
                if node.unit is None:
                    node.expr, node.unit = None, None
                    node.define(build())
        elif unit != self._currency:
            raise UnitError(f"{self.name}: {what!r} is in {_describe(unit)}, but the books are in "
                            f"{_describe(self._currency)}")

    def _account(self, name, side, kind, cf, category=None, *, tags=frozenset(), opening=None) -> Account:
        if cf not in CF_CLASSES + ("pl", "cash"):
            raise ValueError(f"{name}: cf= must be one of {', '.join(CF_CLASSES)}")
        if any(a.name == name and a.kind == kind for a in self._accounts):
            hint = ""
            if kind in ("receivable", "payable") and name == SHARED[kind][2]:
                hint = (f"; settle= on a PL row opens this {kind} for every line that uses it, so give the opening "
                        f"balance with opening= on the PL row (co.pl.revenue(..., settle=..., opening=...)) "
                        f"instead of declaring co.bs.{kind}({name!r}, opening=...)")
            raise ValueError(f"{self.name} already has a {kind} named {name!r}{hint}")
        a = Account(self, name, side, kind, cf, category, frozenset(tags), opening)
        self._accounts.append(a)
        return a

    def _shared(self, kind: str) -> Account:
        if kind not in self._shared_accounts:
            side, cf, label = SHARED[kind]
            self._shared_accounts[kind] = self._account(label, side, kind, cf)
        return self._shared_accounts[kind]

    def load_actuals(self, actuals: Mapping) -> None:
        """Load historical actuals for multiple lines or accounts at once.

        Historical periods (up to and including ``Model.actual_until``) take the supplied values instead of running
        the double-entry posting engine. Forecast periods carry forward from the last actual period's closing
        balances.

        Parameters
        ----------
        actuals : Mapping
            Mapping from a target line or account to ``{period: amount}``. Each key may be a `LineItem`,
            ``co.bs.cash``, ``co.bs.retained_earnings``, an `Account`, or the unique name of a line or account
            in this entity.

        Raises
        ------
        ValueError
            At construction, if the model has no ``actual_until``, if a target belongs to another entity, if a
            period is after ``actual_until``, or if a string name matches multiple items.
        TypeError
            At construction, if ``actuals`` or any entry is not a mapping, or if a key is not a supported target.
        KeyError
            At construction, if a string key matches no line or account of this entity.
        UnitError
            At construction, if an amount is in a unit other than the entity's currency.
        IndexError
            At construction, if a period key is outside the model timeline.

        Examples
        --------
        Load historical cash, retained earnings, and revenue for two actual years:

        >>> import boki as b
        >>> from boki.units import USD
        >>> m = b.Model("Co", start="2023", periods=3, step=b.year, actual_until="2024")
        >>> co = m.entity("Co", standard=b.USGAAP, currency=USD)
        >>> sales = co.pl.revenue("Sales", 150 * USD)
        >>> co.load_actuals({
        ...     sales: {"2023": 100 * USD, "2024": 120 * USD},
        ...     co.bs.cash: {"2023": 50 * USD, "2024": 70 * USD},
        ...     co.bs.retained_earnings: {"2023": 50 * USD, "2024": 70 * USD},
        ... })
        >>> r = m.render()
        >>> r[sales]
        [100.0, 120.0, 150.0]
        >>> r[co.bs.cash]
        [50.0, 70.0, 220.0]
        """  # noqa: DOC105, DOC107, DOC502, DOC503
        if self.model.actual_until is None:
            raise ValueError(f"{self.name}: load_actuals requires Model(..., actual_until=...)")
        if not isinstance(actuals, Mapping):
            raise TypeError("load_actuals expects a mapping of {line_or_account: {period: amount}}")
        for target, data in actuals.items():
            resolved = self._resolve_actuals_target(target)
            if isinstance(resolved, Account):
                resolved.actuals = _parse_actuals(self, data, resolved.name)
            else:
                _apply_pl_actuals(resolved, _parse_actuals(self, data, resolved.name))

    def _resolve_actuals_target(self, target):
        if target is self.bs.retained_earnings or target is self.retained_earnings:
            return self.retained_earnings
        if target is self.bs.cash or target is self._cash_account:
            return self._cash_account
        if isinstance(target, Account):
            if target.entity is not self:
                raise ValueError(f"load_actuals: {target.name!r} belongs to another entity")
            return target
        if isinstance(target, _Balance):
            if target.account.entity is not self:
                raise ValueError(f"load_actuals: {target.account.name!r} belongs to another entity")
            return target.account
        if isinstance(target, LineItem):
            if target.entity is not self:
                raise ValueError(f"load_actuals: {target.name!r} belongs to another entity")
            if isinstance(target.expr, _Balance):
                return target.account
            return target
        if isinstance(target, str):
            matches = []
            if target.casefold() == "cash":
                matches.append(self._cash_account)
            elif target.casefold() == "retained earnings":
                matches.append(self.retained_earnings)
            for kind in self.layout.pl_kinds:
                for line in getattr(self.pl, kind).items:
                    if line.name == target:
                        matches.append(line)
            for kind in self.layout.bs:
                for line in getattr(self.bs, kind.name).items:
                    if line.name == target:
                        matches.append(line.account if isinstance(line.expr, _Balance) else line)
            for acct in self._accounts:
                if acct.name == target and acct not in matches and not any(
                    isinstance(m, LineItem) and m.account is acct for m in matches
                ):
                    matches.append(acct)
            if not matches:
                raise KeyError(f"load_actuals: no line or account named {target!r} in {self.name!r}")
            if len(matches) > 1:
                raise ValueError(f"load_actuals: {target!r} matches multiple lines or accounts in {self.name!r}")
            return matches[0]
        raise TypeError(f"load_actuals: unsupported target {target!r}")

    def _post(self, name, amount: Series, debit: Account, credit: Account, cf: str | None = None) -> Posting:
        if debit.entity is not self or credit.entity is not self:
            raise ValueError("a posting must stay inside one entity; book a trade with another entity with counterparty=")
        amount = lift(amount)
        if self.model.actual_until is not None:
            amount = amount.where(self.model.is_forecast, 0)
        p = Posting(name, amount, debit, credit, cf)
        debit.debits.append(p)
        credit.credits.append(p)
        self._postings.append(p)
        return p

    def _cash(self, name, amount: Series, account: Account) -> Posting:
        """Move a balance-sheet account by `amount` on its normal side, against cash."""
        if account.side == "asset":
            return self._post(name, amount, debit=account, credit=self._cash_account)
        return self._post(name, amount, debit=self._cash_account, credit=account)

    def _balance(self, account: Account) -> _Balance:
        if id(account) not in self._balances:
            sign = 1 if account.side in ("asset", "expense") else -1
            self._balances[id(account)] = _Balance(account, sign)
        return self._balances[id(account)]

refuse_default_measures(Entity, "co")


class _EquityTotal(Series):
    """Capital accounts plus retained earnings, with profit to date closed into them."""

    def __init__(self, entity: Entity):
        self.entity = entity
        self.name = f"{entity.name}: equity"

    @property
    def unit(self):
        return self.entity._currency

    def _eval(self, r, t):
        e = self.entity
        total = sum(r.value(e._balance(a), t) for a in e._accounts if a.side == "equity")
        return total + (r.value(e._cum_profit, t) or 0)
