"""Layouts and accounting standards as data.

A Layout says which kinds of lines a company's statements have and in what order: PL kinds
and the subtotals (stages) between them, and balance-sheet kinds with their defaults
(side, current or non-current, cash-flow class). A Standard holds the rules and its own
general layout (the master used when no layout is given). Industry layouts such as the
bank layout are shared across standards.

Adding a layout (insurance, REIT, regulated utility, non-profit) means adding data here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from ._dataclass_docs import document_init

if TYPE_CHECKING:
    from .ledger import PL
    from .series import Series


@document_init("Create a kind of line for a layout.")
@dataclass(frozen=True)
class Kind:
    """A kind of line in a layout: a named group of lines on one side of a statement, and how it behaves.

    Every kind of a layout becomes a `LineMaker` on the entity, named after the kind: a PL kind is ``co.pl.<name>``
    and a balance-sheet kind is ``co.bs.<name>``. The kind decides the side, the default cash-flow section,
    and, for the balance sheet, the mechanism that says what a call books (a plain balance, a loan, a fixed asset).
    A `Kind` is immutable.

    Parameters
    ----------
    name : str
        Name of the kind, which becomes the attribute ``co.pl.<name>`` or ``co.bs.<name>``. Required. It must be unique
        in the layout and must not be a name the statement already uses; see the custom-layout page.
    side : str
        Required. ``"asset"``, ``"liability"`` or ``"equity"`` for a balance-sheet kind, and ``"income"`` or
        ``"expense"`` for a PL kind. A PL kind whose side is not ``"income"`` is treated as an expense.
    section : str, optional
        ``"current"`` or ``"noncurrent"`` for a balance-sheet kind, which the Excel balance sheet uses to group its
        lines. The default is ``None``, for PL kinds and for kinds with no group.
    cf : str, default="operating"
        The cash-flow section of the cash that a line of this kind moves, unless the line gives its own: ``"operating"``,
        ``"investing"`` or ``"financing"`` for a balance-sheet kind, and ``"pl"`` for a PL kind.
    tags : frozenset, default=frozenset()
        Labels copied to every account of the kind, such as ``frozenset({"interest_bearing"})``. boki reads a few
        internal tags; others do not change values.
    contra : bool, default=False
        Marks an asset that is carried as a negative amount, such as an allowance. It is recorded on the kind and does not
        change values or statements today.
    mechanism : str, default="line"
        What a call of a balance-sheet kind books: ``"line"`` (a balance), ``"fixed_asset"``, ``"loan"``,
        ``"construction"``, ``"capital"`` or ``"dividend"``. Any other value makes ``Model.entity`` raise ``KeyError``
        when it builds the balance sheet. PL kinds use ``"pl"`` by convention; the income statement ignores it.

    Attributes
    ----------
    name : str
        The kind's name.
    side : str
        The side of the statement.
    section : str | None
        The balance-sheet section, or ``None``.
    cf : str
        The default cash-flow section.
    tags : frozenset
        The labels copied to the kind's accounts.
    contra : bool
        Whether the kind is a contra asset.
    mechanism : str
        The mechanism of the kind.

    See Also
    --------
    boki.layouts.Layout : A layout is a list of kinds and subtotals.
    boki.layouts.Stage : A subtotal between kinds.

    Notes
    -----
    A PL kind named ``income_tax`` gets the income tax maker, which takes ``rate=`` and ``base=``, whatever its mechanism. The
    built-in layouts list the general kinds; see `the balance-sheet rows
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#bs-rows>`_.

    Examples
    --------
    A royalty income kind for the income statement, and a loan kind for the balance sheet:

    >>> from boki.layouts import Kind
    >>> royalty = Kind("royalty", "income", cf="pl", mechanism="pl")
    >>> note = Kind("note", "liability", "noncurrent", "financing", mechanism="loan")
    >>> royalty.side, note.section, note.mechanism
    ('income', 'noncurrent', 'loan')
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    side: str                                 # asset / liability / equity / income / expense
    section: str | None = None                # current / noncurrent (balance sheet)
    cf: str = "operating"                     # operating / investing / financing / cash / pl
    tags: frozenset = frozenset()
    contra: bool = False                      # an asset carried as a negative (an allowance)
    mechanism: str = "line"                   # line / fixed_asset / loan / construction / capital / dividend / pl


@document_init("Create a subtotal for a layout.")
@dataclass(frozen=True)
class Stage:
    """A subtotal of the income statement, such as gross profit, built from the totals of kinds and earlier subtotals.

    A layout lists stages between its kinds in presentation order. ``Model.entity`` builds each stage as a series
    named after it, ``co.pl.<name>``, by calling ``formula`` with the entity's `PL`. A `Stage` is immutable.

    Parameters
    ----------
    name : str
        Name of the subtotal, which becomes the attribute ``co.pl.<name>`` and the label key of the statement row.
        Required. A layout needs a stage called ``net_income``.
    formula : Callable[[PL], Series]
        Function that receives the entity's ``co.pl`` and returns the subtotal as a `Series`, such as
        ``lambda pl: pl.revenue.total - pl.cogs.total``. It may use the ``total`` of any kind of the layout and
        any stage listed before this one. Required.

    Attributes
    ----------
    name : str
        The subtotal's name.
    formula : Callable[["PL"], "Series"]
        The function that builds the subtotal.

    Raises
    ------
    AttributeError
        At construction through ``Model.entity``, if ``formula`` reads a kind or stage that the layout does not have, or a
        stage that is listed after this one.

    See Also
    --------
    boki.layouts.Layout : A layout lists its stages among its kinds.
    boki.layouts.Kind : A line kind that a stage adds up.

    Notes
    -----
    Expenses are positive amounts, so a subtotal subtracts them. ``Model.entity`` calls ``formula`` when it builds the
    statement, and may call it again when the first amount fixes the entity's currency, so write it as a function of
    ``pl`` only.

    Examples
    --------
    A subtotal from the total of two kinds, evaluated on an entity:

    >>> import boki as b
    >>> from boki.layouts import Kind, Layout, Stage
    >>> layout = Layout(
    ...     "Simple",
    ...     pl=(Kind("sales", "income", cf="pl", mechanism="pl"), Kind("costs", "expense", cf="pl", mechanism="pl"),
    ...         Stage("net_income", lambda pl: pl.sales.total - pl.costs.total)),
    ...     bs=(), interest_kind="costs", depreciation_kind="costs")
    >>> m = b.Model("Stage", start="2027-01", periods=1, step=b.year)
    >>> co = m.entity("A", layout=layout)
    >>> sales = co.pl.sales("Sales", 100)
    >>> costs = co.pl.costs("Costs", 30)
    >>> m.render().value(co.pl.net_income, "2027")
    70
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    formula: Callable[["PL"], "Series"]


def _pl(kind: str, side: str) -> Kind:
    return Kind(kind, side, cf="pl", mechanism="pl")


def _stage(name: str, formula: Callable[["PL"], "Series"]) -> Stage:
    """A subtotal of a built-in layout, with its formula documented so that ``help(stage.formula)`` says what it is."""
    formula.__doc__ = (
        f"Return the ``{name}`` subtotal of an entity's income statement.\n\n"
        f"Parameters\n----------\npl : PL\n    The entity's income statement.\n\n"
        f"Returns\n-------\nSeries\n    The subtotal in each period, in the entity's currency per period.\n")
    return Stage(name, formula)


@document_init("Create a layout of statement kinds and subtotals.")
@dataclass(frozen=True)
class Layout:
    """Which kinds of lines an entity's statements have, in what order, with the subtotals between them.

    A layout is data: the kinds of the income statement and their subtotals, the kinds of the balance sheet, and the two
    income-statement kinds that automatic entries use. ``Model.entity(..., layout=...)`` builds the entity's ``co.pl``
    and ``co.bs`` from it. Without ``layout=``, an entity uses the general layout of its standard. A `Layout` is
    immutable and shared by every entity that uses it. The custom-layout page explains how to define one.

    Parameters
    ----------
    name : str
        Name of the layout, shown in error messages and in ``repr(entity)``. Required.
    pl : tuple
        `Kind` and `Stage` items of the income statement in presentation order. Required. A layout needs a stage called
        ``net_income``.
    bs : tuple of Kind
        The balance-sheet kinds. Required; it may be empty. Cash, retained earnings and the shared accounts that
        ``settle=`` and ``vat=`` open are not kinds: every entity has them.
    interest_kind : str
        Name of the PL kind where interest on loans is expensed. Required; it must be a PL kind of the layout if the
        layout has a loan kind.
    depreciation_kind : str
        Name of the PL kind where depreciation is expensed. Required; it must be a PL kind of the layout if the layout
        has a fixed-asset or construction kind.

    Attributes
    ----------
    name : str
        The layout's name.
    pl : tuple
        The income-statement kinds and stages in presentation order.
    bs : tuple[Kind, ...]
        The balance-sheet kinds.
    interest_kind : str
        The PL kind that takes loan interest.
    depreciation_kind : str
        The PL kind that takes depreciation.

    See Also
    --------
    boki.layouts.Kind : One line kind of a layout.
    boki.layouts.Stage : One subtotal of a layout.
    boki.layouts.Standard : An accounting standard, which owns a general layout.

    Notes
    -----
    The properties ``pl_kinds``, ``income_kinds`` and ``stages`` list the names of the PL kinds, the names of the income
    kinds, and the subtotals.

    A layout is not checked when it is made. ``Model.entity`` builds the statements from it and raises when the layout
    cannot be built, and some mistakes surface only when a line is booked; the module page lists each rule and its error.
    The layouts of the built-in standards are ``b.IFRS.general``, ``b.USGAAP.general`` and ``b.JGAAP.general``,
    and ``b.layouts.bank`` is shared across standards.

    Examples
    --------
    A custom layout with one income kind, one expense kind and the required net income, then an entity that uses it:

    >>> import boki as b
    >>> from boki.layouts import Kind, Layout, Stage
    >>> layout = Layout(
    ...     "Licensing",
    ...     pl=(Kind("royalty", "income", cf="pl", mechanism="pl"), Kind("cost", "expense", cf="pl", mechanism="pl"),
    ...         Stage("net_income", lambda pl: pl.royalty.total - pl.cost.total)),
    ...     bs=(Kind("escrow", "asset", "current"),),
    ...     interest_kind="cost", depreciation_kind="cost")
    >>> layout.pl_kinds, layout.income_kinds
    (('royalty', 'cost'), ('royalty',))
    >>> m = b.Model("Layout", start="2027-01", periods=1, step=b.year)
    >>> co = m.entity("A", layout=layout)
    >>> royalty = co.pl.royalty("Royalty", 100)
    >>> m.render().value(co.net_income, "2027")
    100
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    pl: tuple                                  # Kind and Stage in presentation order
    bs: tuple[Kind, ...]
    interest_kind: str                         # where loan interest is expensed
    depreciation_kind: str                     # where depreciation is expensed

    @property
    def pl_kinds(self) -> tuple[str, ...]:
        """The names of the income-statement kinds, in presentation order.

        Returns
        -------
        tuple[str, ...]
            One name for each `Kind` in ``pl``; the stages are not included.

        Examples
        --------
        >>> import boki as b
        >>> b.layouts.bank.pl_kinds
        ('interest_income', 'interest_expense', 'provision', 'non_interest_income', 'non_interest_expense', 'income_tax')
        """
        return tuple(k.name for k in self.pl if isinstance(k, Kind))

    @property
    def income_kinds(self) -> tuple[str, ...]:
        """The names of the income-statement kinds that are income, in presentation order.

        Returns
        -------
        tuple[str, ...]
            The names of the PL kinds whose side is ``"income"``. The other PL kinds are expenses.

        Examples
        --------
        >>> import boki as b
        >>> b.IFRS.general.income_kinds
        ('revenue', 'other_income', 'finance_income')
        """
        return tuple(k.name for k in self.pl if isinstance(k, Kind) and k.side == "income")

    @property
    def stages(self) -> tuple[Stage, ...]:
        """The subtotals of the income statement, in presentation order.

        Returns
        -------
        tuple[Stage, ...]
            One `Stage` for each subtotal in ``pl``; the kinds are not included.

        Examples
        --------
        >>> import boki as b
        >>> [stage.name for stage in b.USGAAP.general.stages]
        ['gross_profit', 'operating_income', 'pretax_income', 'net_income']
        """
        return tuple(s for s in self.pl if isinstance(s, Stage))

    def bs_kind(self, name: str) -> Kind | None:
        """Return the balance-sheet kind with a name.

        Parameters
        ----------
        name : str
            The name of a balance-sheet kind, such as ``"loan"``.

        Returns
        -------
        Kind | None
            The kind, or ``None`` if the layout has no balance-sheet kind of that name.

        Examples
        --------
        >>> import boki as b
        >>> b.IFRS.general.bs_kind("loan").mechanism
        'loan'
        >>> b.layouts.bank.bs_kind("receivable") is None
        True
        """
        return next((k for k in self.bs if k.name == name), None)


# ---- balance-sheet kinds shared by the general layouts ---------------------------

_GENERAL_BS: tuple[Kind, ...] = (
    Kind("receivable", "asset", "current"),
    Kind("inventory", "asset", "current"),
    Kind("prepaid", "asset", "current"),
    Kind("working_capital", "asset", "current"),
    Kind("other_current_asset", "asset", "current"),
    Kind("fixed_asset", "asset", "noncurrent", "investing", mechanism="fixed_asset"),
    Kind("intangible", "asset", "noncurrent", "investing", mechanism="fixed_asset"),
    Kind("construction", "asset", "noncurrent", "investing", mechanism="construction"),
    Kind("deposit", "asset", "noncurrent", "investing"),
    Kind("other_asset", "asset", "noncurrent", "investing"),
    Kind("deferred_tax_asset", "asset", "noncurrent", "operating"),
    Kind("payable", "liability", "current"),
    Kind("accrued", "liability", "current"),
    Kind("deferred_revenue", "liability", "current"),
    Kind("other_current_liability", "liability", "current"),
    Kind("lease_liability", "liability", "noncurrent"),
    Kind("other_liability", "liability", "noncurrent"),
    Kind("deferred_tax_liability", "liability", "noncurrent", "operating"),
    Kind("loan", "liability", "noncurrent", "financing", mechanism="loan"),
    Kind("capital", "equity", cf="financing", mechanism="capital"),
    Kind("nci", "equity", cf="financing", mechanism="capital"),
    Kind("dividend", "equity", cf="financing", mechanism="dividend"),
    Kind("oci", "equity", cf="financing", mechanism="capital"),
)


def _general(standard_name: str, income: tuple, expense: tuple, stages: tuple, interest: str) -> Layout:
    kinds = {k: _pl(k, "income") for k in income} | {k: _pl(k, "expense") for k in expense}
    order: list = []
    placed: set[str] = set()
    for stage_name, uses, fn in stages:
        for k in uses:
            if k not in placed:
                order.append(kinds[k])
                placed.add(k)
        order.append(_stage(stage_name, fn))
    return Layout(f"{standard_name} general", tuple(order), _GENERAL_BS, interest, "sga")


_JGAAP_GENERAL = _general(
    "J-GAAP",
    income=("revenue", "non_operating_income", "special_gain"),
    expense=("cogs", "sga", "non_operating_expense", "special_loss", "income_tax"),
    stages=(
        ("gross_profit", ("revenue", "cogs"), lambda pl: pl.revenue.total - pl.cogs.total),
        ("operating_income", ("sga",), lambda pl: pl.gross_profit - pl.sga.total),
        ("ordinary_income", ("non_operating_income", "non_operating_expense"),
         lambda pl: pl.operating_income + pl.non_operating_income.total - pl.non_operating_expense.total),
        ("pretax_income", ("special_gain", "special_loss"),
         lambda pl: pl.ordinary_income + pl.special_gain.total - pl.special_loss.total),
        ("net_income", ("income_tax",), lambda pl: pl.pretax_income - pl.income_tax.total),
    ),
    interest="non_operating_expense",
)

_IFRS_GENERAL = _general(
    "IFRS",
    income=("revenue", "other_income", "finance_income"),
    expense=("cogs", "sga", "other_expense", "finance_cost", "income_tax"),
    stages=(
        ("gross_profit", ("revenue", "cogs"), lambda pl: pl.revenue.total - pl.cogs.total),
        ("operating_income", ("sga", "other_income", "other_expense"),
         lambda pl: pl.gross_profit - pl.sga.total + pl.other_income.total - pl.other_expense.total),
        ("pretax_income", ("finance_income", "finance_cost"),
         lambda pl: pl.operating_income + pl.finance_income.total - pl.finance_cost.total),
        ("net_income", ("income_tax",), lambda pl: pl.pretax_income - pl.income_tax.total),
    ),
    interest="finance_cost",
)

_USGAAP_GENERAL = _general(
    "US GAAP",
    income=("revenue", "other_income"),
    expense=("cogs", "sga", "other_expense", "interest_expense", "income_tax"),
    stages=(
        ("gross_profit", ("revenue", "cogs"), lambda pl: pl.revenue.total - pl.cogs.total),
        ("operating_income", ("sga",), lambda pl: pl.gross_profit - pl.sga.total),
        ("pretax_income", ("other_income", "other_expense", "interest_expense"),
         lambda pl: pl.operating_income + pl.other_income.total - pl.other_expense.total
         - pl.interest_expense.total),
        ("net_income", ("income_tax",), lambda pl: pl.pretax_income - pl.income_tax.total),
    ),
    interest="interest_expense",
)

# ---- industry layouts (shared across standards) ----------------------------------

#: The bank layout: net interest income, provisions and non-interest items on the income statement, and earning assets,
#: deposits and allowances on the balance sheet. It is shared across standards: pass ``layout=b.layouts.bank`` to
#: ``Model.entity`` with any standard. It has no operating income or gross profit subtotal.
bank = Layout(
    "bank",
    pl=(
        _pl("interest_income", "income"),
        _pl("interest_expense", "expense"),
        _stage("net_interest_income", lambda pl: pl.interest_income.total - pl.interest_expense.total),
        _pl("provision", "expense"),
        _pl("non_interest_income", "income"),
        _pl("non_interest_expense", "expense"),
        _stage("pretax_income", lambda pl: pl.net_interest_income - pl.provision.total
               + pl.non_interest_income.total - pl.non_interest_expense.total),
        _pl("income_tax", "expense"),
        _stage("net_income", lambda pl: pl.pretax_income - pl.income_tax.total),
    ),
    bs=(
        Kind("earning_asset", "asset", cf="investing", tags=frozenset({"interest_earning"})),
        Kind("allowance", "asset", contra=True),
        Kind("other_asset", "asset", "noncurrent", "investing"),
        Kind("deferred_tax_asset", "asset", "noncurrent", "operating"),
        Kind("fixed_asset", "asset", "noncurrent", "investing", mechanism="fixed_asset"),
        Kind("intangible", "asset", "noncurrent", "investing", mechanism="fixed_asset"),
        Kind("deposits", "liability", cf="financing", tags=frozenset({"interest_bearing"})),
        Kind("other_liability", "liability"),
        Kind("deferred_tax_liability", "liability", "noncurrent", "operating"),
        Kind("loan", "liability", cf="financing", mechanism="loan"),
        Kind("capital", "equity", cf="financing", mechanism="capital"),
        Kind("nci", "equity", cf="financing", mechanism="capital"),
        Kind("dividend", "equity", cf="financing", mechanism="dividend"),
        Kind("oci", "equity", cf="financing", mechanism="capital"),
    ),
    interest_kind="interest_expense",
    depreciation_kind="non_interest_expense",
)


# ---- standards -------------------------------------------------------------------

@document_init("Create an accounting standard.")
@dataclass(frozen=True)
class Standard:
    """An accounting standard: its name, its general layout, and how its statements are named and ordered.

    ``b.IFRS``, ``b.USGAAP`` and ``b.JGAAP`` are the built-in standards, and ``Model.entity(standard=...)`` takes
    one. The standard decides which general layout an entity gets when it names none, the names its statements
    show (IFRS says "Profit for the year", US GAAP "Net income"), the order of the Excel balance sheet, and the
    standard-specific accounting that the rest of boki applies by ``standard.name`` (goodwill, deferred tax, OCI).
    A `Standard` is immutable.

    Parameters
    ----------
    name : str
        The standard's name, such as ``"IFRS"``, ``"US GAAP"`` or ``"J-GAAP"``. Required. boki's standard-specific
        rules branch on these three names.
    general : Layout
        The layout an entity uses when it names none. Required.
    labels : dict, optional
        Display names by kind, as ``{kind: name}``. The default is an empty dict. The current statements do not read
        it; they take names from ``display`` and the style.
    display : dict, optional
        Statement names by language, as ``{"en": {key: name}}``. The standard's name for a key comes before the style's
        and the common table's, such as ``{"en": {"net_income": "Profit for the year"}}``. The default is an empty dict.
    bs_order : str, default="current_first"
        Order of the Excel balance sheet: ``"current_first"`` (US GAAP and J-GAAP: current assets first, liabilities before
        equity) or ``"noncurrent_first"`` (IFRS: non-current assets first, equity before liabilities).

    Attributes
    ----------
    name : str
        The standard's name.
    general : Layout
        The general layout.
    labels : dict
        Display names by kind.
    display : dict
        Statement names by language.
    bs_order : str
        The balance-sheet order.

    See Also
    --------
    boki.layouts.Layout : The layout a standard owns.

    Notes
    -----
    The built-in standards differ in more than names. For example, goodwill is amortized under J-GAAP and not under
    IFRS, and the standards disagree on what belongs in operating income and EBITDA; see the notes of the line makers and
    of `Group.own`. ``repr`` of a standard is ``<Standard NAME>``.

    Examples
    --------
    The built-in standards and what each gives an entity:

    >>> import boki as b
    >>> b.IFRS.name, b.IFRS.general.name, b.IFRS.bs_order
    ('IFRS', 'IFRS general', 'noncurrent_first')
    >>> m = b.Model("Standard", start="2027-01", periods=1, step=b.year)
    >>> m.entity("A", standard=b.USGAAP).layout.name
    'US GAAP general'
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    general: Layout                            # the layout used when an entity names none
    labels: dict = field(default_factory=dict) # display names for kinds, e.g. {"interest_income": "資金運用収益"}
    display: dict = field(default_factory=dict)  # statement names by language: {"en": {"net_income": "Profit for the year"}}
    bs_order: str = "current_first"            # current_first (US GAAP, J-GAAP) / noncurrent_first (IFRS, equity first)

    def __repr__(self):
        return f"<Standard {self.name}>"


#: The Japanese GAAP standard. Its general layout has gross profit, operating income, ordinary income, pretax income
#: and net income; it amortizes goodwill and shows current assets first.
JGAAP = Standard("J-GAAP", _JGAAP_GENERAL, labels={
    "interest_income": "資金運用収益", "interest_expense": "資金調達費用", "deferred_tax": "法人税等調整額",
})
#: The IFRS standard. Its general layout has gross profit, operating income, pretax income and net income ("Profit for
#: the year"); goodwill is not amortized, and the Excel balance sheet shows non-current assets first.
IFRS = Standard("IFRS", _IFRS_GENERAL, bs_order="noncurrent_first", display={"en": {
    "cogs": "Cost of sales", "sga": "Selling, general and administrative expenses", "operating_income": "Operating profit",
    "other_income": "Other income", "other_expense": "Other expenses", "finance_income": "Finance income",
    "equity_method_income": "Share of profit of associates",
    "finance_cost": "Finance costs", "pretax_income": "Profit before tax", "income_tax": "Income tax expense",
    "net_income": "Profit for the year", "deferred_tax": "Deferred tax", "oci": "Other components of equity",
    "IS": "Statement of Profit or Loss", "BS": "Statement of Financial Position",
    "CF": "Statement of Cash Flows", "cash": "Cash and cash equivalents", "liabilities_equity": "Equity and liabilities",
    "total_liabilities_equity": "Total equity and liabilities", "receivable": "Trade receivables",
    "payable": "Trade payables", "goodwill": "Goodwill", "nci": "Non-controlling interests",
    "capital_surplus": "Share premium"}})
#: The US GAAP standard. Its general layout has gross profit, operating income, pretax income and net income; goodwill is
#: not amortized except under the private-company alternative, and current assets are shown first.
USGAAP = Standard("US GAAP", _USGAAP_GENERAL, display={"en": {
    "deferred_tax": "Deferred income tax", "oci": "Accumulated other comprehensive income",
    "goodwill": "Goodwill", "nci": "Noncontrolling interests",
    "capital_surplus": "Additional paid-in capital", "equity_method_income": "Equity in earnings of affiliates",
}})


__all__ = ["Layout", "Kind", "Stage", "Standard", "IFRS", "USGAAP", "JGAAP", "bank"]
