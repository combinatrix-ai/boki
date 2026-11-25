"""The three statements as views of an entity's ledger, grouping by fiscal year, and checks."""
from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from .ledger import ACQUISITION_CLEARING
from .layouts import Stage
from .series import Series
from .units import Unit

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .ledger import Entity
    from .model import Model, Result


# ---- fiscal calendars ------------------------------------------------------------

class Fiscal:
    """A fiscal calendar: the day each fiscal year ends, with optional changes of year end.

    Statements grouped ``by="fiscal_year"`` and the Excel statement columns use it to sum monthly or quarterly
    model periods into fiscal years. The model's periods do not change: a fiscal calendar is a reporting view of
    them. Make one with ``b.fiscal(...)`` and pass it as ``fiscal=`` to ``Model.entity``.

    Parameters
    ----------
    year_end : str
        The day each fiscal year ends, as ``"MM-DD"``: ``"03-31"`` for a year ending on March 31 and ``"12-31"`` for a
        calendar year. A day beyond the end of the month is moved to the last day of the month, so ``"02-30"`` ends on
        February 28 (or 29). Required. It is not checked when the calendar is made; a malformed value raises when a
        label is needed.
    change : dict | None
        Changes of year end as ``{date: "MM-DD"}``. A key is the last day of a fiscal year, as a date or a
        ``"YYYY-MM-DD"`` string, and the value is the year-end rule that applies to the years after it. The default
        is ``None``, which means no change. The year that ends on a key is shorter or longer than twelve months when
        the old and new year ends differ.

    Attributes
    ----------
    year_end : str
        The year-end rule as given.
    change : dict
        The changes of year end, keyed by `datetime.date`.

    See Also
    --------
    boki.fiscal : Make a fiscal calendar.
    boki.statements.Fiscal.label : The label of the fiscal year a period belongs to.

    Notes
    -----
    ``b.fiscal`` raises ``ValueError`` if a key of ``change`` is not a date or a date string. A year-end rule that is not a
    valid ``"MM-DD"`` is not checked there: it raises ``ValueError`` when a label is needed, at evaluation.

    Examples
    --------
    A March year end, and a December year end that moves to March after the year ending 2029-03-31 (a three-month
    transition year):

    >>> import boki as b
    >>> from datetime import date
    >>> fy = b.fiscal("03-31")
    >>> fy.label(date(2027, 4, 1))
    'FY2028-03'
    >>> moved = b.fiscal("12-31", change={"2029-03-31": "03-31"})
    >>> [moved.label(date(*start)) for start in ((2028, 6, 1), (2029, 1, 1), (2029, 4, 1))]
    ['FY2028-12', 'FY2029-03', 'FY2030-03']
    """

    year_end: str
    change: dict

    def __init__(self, year_end: str, change: dict | None = None):
        self.year_end = year_end
        self.change = {_parse(k): v for k, v in (change or {}).items()}

    def _end_for(self, d: date) -> date:
        """The fiscal year end on or after d, honoring changes of year end."""
        rule = self.year_end
        for switch, new_rule in sorted(self.change.items()):
            end = _next_end(d, rule)
            if end < switch:
                return end
            if d <= switch:
                return switch
            rule = new_rule
        return _next_end(d, rule)

    def label(self, period_start: date) -> str:
        """Return the label of the fiscal year that contains a date.

        Parameters
        ----------
        period_start : datetime.date
            The first day of a model period, or any date. It must be a ``date``, not a string.

        Returns
        -------
        str
            ``"FY<year>-<month>"`` for the fiscal year whose last day is on or after the date, such as
            ``"FY2028-03"`` for the year ending 2028-03-31.

        Raises
        ------
        ValueError
            At evaluation, if the year-end rule is not a valid ``"MM-DD"``.

        See Also
        --------
        boki.fiscal : Make a fiscal calendar.

        Examples
        --------
        The last day of a fiscal year belongs to that year, and the next day to the following one:

        >>> import boki as b
        >>> from datetime import date
        >>> fy = b.fiscal("03-31")
        >>> fy.label(date(2028, 3, 31)), fy.label(date(2028, 4, 1))
        ('FY2028-03', 'FY2029-03')
        """  # noqa: DOC105, DOC502
        end = self._end_for(period_start)
        return f"FY{end.year}-{end.month:02d}"


def fiscal(year_end: str, change: dict | None = None) -> Fiscal:
    """Make a fiscal calendar for an entity.

    Parameters
    ----------
    year_end : str
        The day each fiscal year ends, as ``"MM-DD"``, such as ``"03-31"`` or ``"12-31"``. Required. A day beyond
        the end of the month is moved to the last day of that month.
    change : dict, optional
        Changes of year end as ``{date: "MM-DD"}``. A key is the last day of a fiscal year, as a date or a
        ``"YYYY-MM-DD"`` string, and the value is the year-end rule for the years after it. The default is ``None``,
        which means no change.

    Returns
    -------
    Fiscal
        The fiscal calendar, to pass as ``fiscal=`` to ``Model.entity``.

    Raises
    ------
    ValueError
        At construction, if a key of ``change`` is not a date or a date string.

    See Also
    --------
    boki.calendar : Business-day counts, which are a different calendar.

    Examples
    --------
    Group a monthly model into March fiscal years:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Fiscal", start="2027-01", periods=18, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY, fiscal=b.fiscal("03-31"))
    >>> sales = co.pl.revenue("Sales", 10)
    >>> r = m.render()
    >>> table = r.pl(co, by="fiscal_year")
    >>> table.columns
    ['FY2027-03', 'FY2028-03', 'FY2029-03']
    """  # noqa: DOC105, DOC502
    return Fiscal(year_end, change)


def _parse(x) -> date:
    from .model import parse_date
    return parse_date(x)


def _next_end(d: date, rule: str) -> date:
    m, day = (int(p) for p in rule.split("-"))
    for year in (d.year, d.year + 1):
        last = min(day, _cal.monthrange(year, m)[1])
        end = date(year, m, last)
        if end >= d:
            return end
    raise AssertionError("unreachable")


# ---- business-day calendars ------------------------------------------------------

_DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


class _Days(Series):
    def __init__(self, cal: "Calendar", weekdays: set[int], name: str):
        from .units import day
        self.cal, self.weekdays, self.name, self.unit = cal, weekdays, name, day.dims

    def _eval(self, r, t):
        p = r.model.timeline.periods[t]
        d, n = p.start, 0
        while d < p.end:
            if d.weekday() in self.weekdays and d.weekday() not in self.cal.closed and d not in self.cal.holidays:
                n += 1
            d += timedelta(days=1)
        return n


class Calendar:
    """A business-day calendar that counts the days of each model period.

    ``b.calendar(m, ...)`` makes one for a model. ``days`` then counts, in every period, the days that match a
    weekday pattern and are neither a closed weekday nor a holiday. Use the counts to scale amounts that depend on
    trading days.

    Parameters
    ----------
    model : Model
        The model whose periods are counted. It needs a dated timeline.
    holidays : Iterable[date | str] | None
        Dates that never count, as dates or ``"YYYY-MM-DD"`` strings. The default is ``None``, which means no
        holidays. ``"jp"`` is not available and raises `NotImplementedError`.
    closed : Iterable[str]
        Weekdays that never count, from ``"Mon"``, ``"Tue"``, ``"Wed"``, ``"Thu"``, ``"Fri"``, ``"Sat"`` and ``"Sun"``.
        The default is an empty tuple. An entry that is not a weekday abbreviation raises ``KeyError`` through
        ``b.calendar``.

    Attributes
    ----------
    holidays : set[date]
        The holidays.
    closed : set[int]
        The closed weekdays as numbers, Monday is 0 and Sunday is 6.

    Raises
    ------
    NotImplementedError
        At construction through ``b.calendar``, if ``holidays`` is ``"jp"``.

    See Also
    --------
    boki.calendar : Make a calendar.
    boki.statements.Calendar.days : Count the matching days of each period.

    Examples
    --------
    July 2027 has 27 days that are not Sundays, and 26 after one holiday:

    >>> import boki as b
    >>> m = b.Model("Days", start="2027-07", periods=1, step=b.month)
    >>> cal = b.calendar(m, holidays=["2027-07-19"], closed=["Sun"])
    >>> r = m.render()
    >>> r.value(cal.days("Mon-Sat"), "2027-07")
    26
    """

    holidays: set[date]
    closed: set[int]

    def __init__(self, model: Model, holidays: Iterable[date | str] | None = None, closed: Iterable[str] = ()):
        if holidays == "jp":
            raise NotImplementedError("built-in Japanese holidays are not bundled yet; pass holidays=[dates]")
        self.model = model
        self.holidays = {_parse(h) for h in (holidays or [])}
        self.closed = {_DAYS[c] for c in closed}

    def days(self, spec: str) -> Series:
        """Count the days of each period that match a weekday pattern.

        A day counts when its weekday is in ``spec``, it is not a closed weekday of the calendar, and it is not a
        holiday.

        Parameters
        ----------
        spec : str
            Weekdays as names joined by commas, where a name can be a range: ``"Mon-Sat"``, ``"Fri-Sat"``,
            ``"Mon,Wed"``. A range whose end is before its start wraps around the week, so ``"Sat-Mon"`` is Saturday,
            Sunday and Monday. Names are ``Mon`` to ``Sun``. Required.

        Returns
        -------
        Series
            The number of matching days in each period, a quantity in days (``b.day``).

        Raises
        ------
        KeyError
            At construction, if a weekday name in ``spec`` is not ``Mon`` to ``Sun``.

        See Also
        --------
        boki.calendar : Make a calendar.

        Examples
        --------
        Days open Monday to Friday and on Saturday and Sunday in July 2027:

        >>> import boki as b
        >>> m = b.Model("Days", start="2027-07", periods=2, step=b.month)
        >>> cal = b.calendar(m, holidays=["2027-07-19"], closed=["Sun"])
        >>> r = m.render()
        >>> r.value(cal.days("Mon-Fri"), "2027-07"), r.value(cal.days("Sat-Mon"), "2027-07")
        (21, 8)
        >>> r.value(cal.days("Mon,Wed"), "2027-08")
        9
        """  # noqa: DOC502
        wanted: set[int] = set()
        for part in spec.split(","):
            if "-" in part:
                a, b = (_DAYS[x.strip()] for x in part.split("-"))
                wanted |= set(range(a, b + 1)) if a <= b else set(range(a, 7)) | set(range(0, b + 1))
            else:
                wanted.add(_DAYS[part.strip()])
        return _Days(self, wanted, f"days({spec})")


def calendar(model, holidays=None, closed=()) -> Calendar:
    """Make a business-day calendar for a model.

    Parameters
    ----------
    model : Model
        The model whose periods are counted. Required; it needs a dated timeline.
    holidays : iterable of date or str, optional
        Dates that never count, as dates or ``"YYYY-MM-DD"`` strings. The default is ``None``, which means no
        holidays. ``"jp"`` is not available.
    closed : iterable of str, default=()
        Weekdays that never count, as ``"Mon"`` to ``"Sun"``.

    Returns
    -------
    Calendar
        The calendar. Call ``days`` on it to get a series.

    Raises
    ------
    NotImplementedError
        At construction, if ``holidays`` is ``"jp"``: built-in Japanese holidays are not bundled.
    KeyError
        At construction, if ``closed`` has an entry that is not a weekday abbreviation.
    ValueError
        At construction, if a holiday is not a date or a date string.

    See Also
    --------
    boki.fiscal : Fiscal years, which are a different calendar.

    Examples
    --------
    Count the days open in each month when the business is closed on Sundays:

    >>> import boki as b
    >>> m = b.Model("Open days", start="2027-07", periods=2, step=b.month)
    >>> cal = b.calendar(m, closed=["Sun"])
    >>> days_open = cal.days("Mon-Sat")
    >>> r = m.render()
    >>> r.value(days_open, "2027-07"), r.value(days_open, "2027-08")
    (27, 26)
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Calendar(model, holidays, closed)


# ---- statements ------------------------------------------------------------------

@dataclass
class Row:
    """One row of a `Table`: a label and a value for each column.

    Parameters
    ----------
    label : str
        Name shown at the start of the row.
    values : list[Any]
        One value for each column of the table, in column order. ``None`` is a missing value.
    stock : bool | str
        How the row groups by fiscal year: ``False`` for a flow (summed), ``True`` for a balance (the value at the
        year's last period), ``"first"`` for an opening balance (the value at the year's first period).
    level : int
        Indentation: 0 for totals and subtotals, 1 for the lines below a total.
    unit : str
        The display unit named after the label, when the values are not in base units; ``""`` otherwise.

    Attributes
    ----------
    label : str
        Name shown at the start of the row.
    values : list[Any]
        One value for each column of the table.
    stock : bool | str
        How the row groups by fiscal year.
    level : int
        Indentation of the row.
    unit : str
        The display unit named after the label, or ``""``.

    See Also
    --------
    boki.statements.Table : The rows of a statement or of ``Result.table``.

    Examples
    --------
    >>> import boki as b
    >>> from boki.units import MWh
    >>> m = b.Model("Plant", start="2027-01", periods=2, step=b.month)
    >>> generation = m.series("Generation", data={0: 400 * MWh, 1: 500 * MWh})
    >>> row = m.render().table([generation]).rows[0]
    >>> row.label, row.unit, row.values, row.level
    ('Generation', 'MWh', [400.0, 500.0], 0)
    """
    label: str
    values: list[Any]
    stock: bool | str = False  # balances keep the last value when grouped ("first": opening balances); flows are summed
    level: int = 0
    unit: str = ""             # the display unit named after the label, when the values are not in base units


class Table:
    """Rows of values by period: what `Result.table`, `Result.pl`, `Result.bs` and `Result.cf` return.

    A table has a title, a label for each column (the periods, or fiscal years), and rows. Printing it, or showing it in
    a notebook, draws it as aligned text, with nested lines indented and numbers in thousands separators. Statement
    rows follow the entity's layout and language; the rows of ``Result.table`` follow the series you passed.

    Parameters
    ----------
    title : str
        Title shown above the first column.
    columns : list[str]
        Column labels: period labels, or fiscal-year labels such as ``"FY2027-12"``.
    rows : list[Row]
        The rows, in display order. Each row has one value for each column.

    Attributes
    ----------
    title : str
        Title of the table, such as ``"PL Cafe"``.
    columns : list[str]
        Column labels.
    rows : list[Row]
        The rows, each with a ``label``, ``values``, ``level`` (1 for a line below a total), ``stock`` and ``unit``.

    See Also
    --------
    boki.Result.table : A table of chosen series.
    boki.Result.pl : A profit and loss statement as a table.

    Notes
    -----
    Values are in base units divided by the row's display unit or by the ``unit`` given to ``Result.table``.
    Only `Result` methods create a table.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Cafe", start="2027-01", periods=2, step=b.month)
    >>> co = m.entity("Cafe", standard=b.IFRS)
    >>> co.bs.opening(cash=1000, retained_earnings=1000)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> table = m.render().pl(co)
    >>> table.title, table.columns
    ('PL Cafe', ['2027-01', '2027-02'])
    >>> [(row.label, row.level, row.values) for row in table.rows[:2]]
    [('Revenue', 0, [100, 100]), ('Sales', 1, [100, 100])]
    """  # noqa: DOC602, DOC603

    def __init__(self, title: str, columns: list[str], rows: list[Row]):
        self.title, self.columns, self.rows = title, columns, rows

    def row(self, label: str) -> list[Any]:
        for r in self.rows:
            if r.label == label:
                return r.values
        raise KeyError(label)

    def __str__(self) -> str:
        head = [self.title, *self.columns]
        body = [["  " * r.level + r.label + (f" ({r.unit})" if r.unit else ""), *[_fmt(v) for v in r.values]] for r in self.rows]
        widths = [max(_width(x[i]) for x in [head, *body]) for i in range(len(head))]
        pad = lambda c, w, right: (" " * (w - _width(c)) + c) if right else (c + " " * (w - _width(c)))
        lines = ["  ".join(pad(c, w, i > 0) for i, (c, w) in enumerate(zip(row, widths))).rstrip()
                 for row in [head, *body]]
        return "\n".join(lines)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))


def _width(text: str) -> int:
    """Columns a string takes in a terminal: CJK characters take two."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        v = v + 0.0                       # -0.0 prints as 0
        if abs(v) < 1e-9:
            return "0"
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.4g}"
    return str(v)


def group(result: "Result", rows: list[Row], by: str | None, entity: "Entity | None") -> tuple[list[str], list[Row]]:
    periods = result.model.timeline.periods
    if by is None:
        return [p.label for p in periods], rows
    if by != "fiscal_year":
        raise ValueError("by= must be None or 'fiscal_year'")
    fiscal = entity.fiscal if entity is not None else None
    if fiscal is None or periods[0].start is None:
        raise ValueError("grouping by fiscal year needs dated periods and an entity with fiscal=")
    labels: list[str] = []
    for p in periods:
        lab = fiscal.label(p.start)
        if not labels or labels[-1] != lab:
            labels.append(lab)
    idx = [labels.index(fiscal.label(p.start)) for p in periods]
    out = []
    for row in rows:
        vals: list[Any] = [None] * len(labels)
        for t, i in enumerate(idx):
            v = row.values[t]
            if row.stock == "first":
                if t == 0 or idx[t - 1] != i:
                    vals[i] = v
            elif row.stock:
                vals[i] = v
            else:
                vals[i] = (vals[i] or 0) + (v or 0)
        out.append(Row(row.label, vals, row.stock, row.level, row.unit))
    return labels, out


def _vec(result: "Result", node) -> list:
    """A node's values as one per period (a scalar node repeats)."""
    v = result[node]
    return v if isinstance(v, list) else [v] * result.model.n


def pl_rows(result: "Result", entity: "Entity", detail: bool = True) -> list[Row]:
    rows = []
    for k in entity.layout.pl:
        if isinstance(k, Stage):
            rows.append(Row(entity.label(k.name), _vec(result, getattr(entity.pl, k.name))))
            continue
        kind = getattr(entity.pl, k.name)
        if not kind.items:
            continue
        rows.append(Row(entity.label(k.name), _vec(result, kind.total)))
        if detail:
            for item in kind.items:
                rows.append(Row(item.name, _vec(result, item), level=1))
    if entity._oci_components:
        rows.append(Row(entity.label("other_comprehensive_income"),
                        _vec(result, entity.other_comprehensive_income)))
        if detail:
            for component in entity._oci_components.values():
                rows.append(Row(component.name, _vec(result, component.line), level=1))
        rows.append(Row(entity.label("comprehensive_income"), _vec(result, entity.comprehensive_income)))
    attribution = getattr(entity, "_group_profit_attribution", None)
    if attribution is not None:
        if attribution["section"]:
            rows.append(Row(attribution["section"], [None] * result.model.n))
        rows.append(Row(attribution["nci_label"], _vec(result, attribution["nci"]), level=1))
        rows.append(Row(attribution["parent_label"], _vec(result, attribution["parent"]), level=1))
    return rows


_NETTED = {"receivable": "deferred_from_receivable", "prepaid": "accrued_from_prepaid"}


def bs_rows(result: "Result", entity: "Entity") -> list[Row]:
    rows = []
    balances = {a: result[entity._balance(a)] for a in entity._accounts if a.side in ("asset", "liability")}
    shown: dict[str, list[tuple[str, list]]] = {"asset": [], "liability": []}
    for a, v in balances.items():
        if a.side == "asset" and a.kind in _NETTED and any(x < 0 for x in v):
            # A receivable that went negative is money received in advance: show it as a liability.
            shown["asset"].append((entity._account_name(a), [max(x, 0) for x in v]))
            shown["liability"].append((entity.label(_NETTED[a.kind]), [max(-x, 0) for x in v]))
        else:
            shown[a.side].append((entity._account_name(a), v))
    for side, title in (("asset", "total_assets"), ("liability", "total_liabilities")):
        items = [(name, v) for name, v in shown[side] if any(x for x in v)]
        for name, v in items:
            rows.append(Row(name, v, stock=True, level=1))
        rows.append(Row(entity.label(title), _sum_cols([v for _, v in items], result.model.n), stock=True))
    eq, nci = [], []
    group_nci = getattr(entity, "_group_profit_attribution", None) is not None
    for a in entity._accounts:
        if a.side == "equity":
            if ACQUISITION_CLEARING in a.tags:
                continue
            v = result[entity._balance(a)]
            if a.kind == "nci" and group_nci:
                nci.append(v)
                continue
            if a.kind == "retained_earnings":
                v = [x + (y or 0) for x, y in zip(v, _vec(result, entity._cum_profit))]
            if any(v):
                eq.append(v)
                rows.append(Row(entity._account_name(a), v, stock=True, level=1))
    if nci:
        nci_total = _sum_cols(nci, result.model.n)
        if any(nci_total):
            eq.append(nci_total)
            rows.append(Row(entity.label("nci"), nci_total, stock=True, level=1))
    rows.append(Row(entity.label("total_equity"), _sum_cols(eq, result.model.n), stock=True))
    rows.append(Row(entity.label("total_liabilities_equity"),
                    [a + b for a, b in zip(rows[-1].values, _find(rows, entity.label("total_liabilities")))], stock=True))
    return rows


def _operating_effect(account, credit: int) -> int:
    """How a posting side moves profit plus operating working capital (credit = +1, debit = -1)."""
    if account.side in ("income", "expense") or (account.side in ("asset", "liability") and account.cf == "operating"):
        return credit
    return 0


def cf_indirect_rows(result: "Result", entity: "Entity") -> list[Row]:
    """Indirect method: profit, plus non-cash charges, minus increases in operating assets."""
    from .ledger import cash_class
    n = result.model.n
    cash = entity._cash_account
    L = entity.label
    rows = [Row(L("net_income"), _vec(result, entity.net_income), level=1)]
    charges, other = [0.0] * n, [0.0] * n
    for p in entity._postings:
        vals = result[p.amount]
        vals = vals if isinstance(vals, list) else [vals] * n
        cls = cash_class(entity, p)
        if cls is not None:
            # A cash posting whose class differs from what the balance changes below imply.
            acct = p.credit if p.debit is cash else p.debit
            implied = acct.cf in ("pl", "operating")
            if (cls == "operating") != implied:
                sign = (1 if p.debit is cash else -1) * (1 if cls == "operating" else -1)
                for t, v in enumerate(vals):
                    other[t] += sign * (v or 0)
            continue
        effect = _operating_effect(p.debit, -1) + _operating_effect(p.credit, 1)
        if not effect:
            continue
        bucket = charges if any(x.side in ("income", "expense") for x in (p.debit, p.credit)) else other
        for t, v in enumerate(vals):
            bucket[t] -= effect * (v or 0)
    rows.append(Row(L("noncash"), charges, level=1))
    if any(other):
        rows.append(Row(L("other_noncash"), other, level=1))
    for a in entity._accounts:
        if a.side in ("asset", "liability") and a.cf == "operating":
            bal = result[entity._balance(a)]
            prev = result[entity._balance(a).opening]
            change = [bal[t] - prev[t] for t in range(n)]
            sign = -1 if a.side == "asset" else 1
            if any(change):
                rows.append(Row(L("change_in").format(entity._account_name(a)), [sign * c for c in change], level=1))
    rows.append(Row(L("operating"), _sum_cols([r.values for r in rows], n)))
    direct = cf_rows(result, entity)
    for key in ("investing", "financing"):
        rows.append(Row(L(key), _find(direct, L(key))))
    if any(cash_class(entity, p) == "fx" for p in entity._postings):
        rows.append(Row(L("fx"), _find(direct, L("fx"))))
    rows.append(Row(L("net_change"), _sum_cols([r.values for r in rows if r.level == 0], n)))
    return rows


def cf_rows(result: "Result", entity: "Entity") -> list[Row]:
    """Direct method: cash postings grouped by the class of the account on the other side."""
    n = result.model.n
    from .ledger import cash_class
    groups: dict[str, dict[str, list[float]]] = {"operating": {}, "investing": {}, "financing": {}, "fx": {}}
    cash = entity._cash_account
    for p in entity._postings:
        cls = cash_class(entity, p)
        if cls is None:
            continue
        other = p.credit if p.debit is cash else p.debit
        sign = 1 if p.debit is cash else -1
        vals = result[p.amount]
        vals = vals if isinstance(vals, list) else [vals] * n
        bucket = groups[cls].setdefault(entity._account_name(other), [0.0] * n)
        for t, v in enumerate(vals):
            bucket[t] += sign * (v or 0)
    rows = []
    for cls, items in groups.items():
        if cls == "fx" and not items:
            continue
        for name, v in items.items():
            rows.append(Row(name, v, level=1))
        rows.append(Row(entity.label(cls), _sum_cols(list(items.values()), n)))
    rows.append(Row(entity.label("net_change"), _sum_cols([r.values for r in rows if r.level == 0], n)))
    return rows


def _sum_cols(vectors: list[list], n: int) -> list[float]:
    return [sum((v[t] or 0) for v in vectors) for t in range(n)]


def _find(rows: list[Row], label: str) -> list[float]:
    return next(r.values for r in rows if r.label == label)


def scale_of(unit) -> float:
    if unit is None:
        return 1.0
    if isinstance(unit, Unit):
        return unit.scale
    return unit.value    # a Quantity such as 10_000 * JPY


# ---- invariants ------------------------------------------------------------------

class LedgerError(AssertionError):
    """Error raised when an entity's books fail a consistency check.

    ``m.render()`` verifies every entity and group before it evaluates your own checks. It raises `LedgerError` when
    an opening balance sheet does not balance, when assets differ from liabilities plus equity in any period, when
    cash-flow sections do not add up to the change in cash, or when the indirect cash flow differs from the
    direct one. A group's consolidated books are checked too, including the profit attributed to owners and to
    non-controlling interests. The message names the entity, the check, and the period.

    See Also
    --------
    boki.ledger.EntityChecks : Checks about your plan, such as cash not being negative.

    Notes
    -----
    A difference larger than a relative tolerance of 1e-6 fails. Postings made through boki's own lines always
    balance, so a ledger error usually means a bug in boki, or an amount computed outside the ledger. You can also cause it
    by declaring an opening balance sheet that does not balance: giving both ``cash`` and ``retained_earnings`` to
    ``co.bs.opening`` (or an opening balance on a line) without matching amounts. ``LedgerError`` is an
    `AssertionError`, so it is not caught by handlers for ``ValueError``, and it differs from the check failures that
    ``Model.render`` raises as ``CheckFailed`` for conditions of your plan.

    Examples
    --------
    An opening balance sheet that declares cash of 1,000 and retained earnings of 500 does not balance:

    >>> import boki as b
    >>> from boki.units import JPY
    >>> m = b.Model("Unbalanced", start="2027-01", periods=1, step=b.year)
    >>> co = m.entity("A", standard=b.IFRS, currency=JPY)
    >>> co.bs.opening(cash=1000, retained_earnings=500)
    >>> try:
    ...     m.render()
    ... except b.LedgerError as error:
    ...     print(error)
    A: the opening balance sheet does not balance: assets 1,000 != liabilities 0 + equity 500; difference 500
    """


def verify(result: "Result", entity: "Entity") -> None:
    n = result.model.n
    actual_until = result.model.actual_until
    if actual_until is None:
        opening = {side: sum(result[entity._balance(a).opening][0] for a in entity._accounts if a.side == side)
                   for side in ("asset", "liability", "equity")}
        opening_difference = opening["asset"] - opening["liability"] - opening["equity"]
        if abs(opening_difference) > 1e-6 * max(1.0, abs(opening["asset"])):
            raise LedgerError(f"{entity.name}: the opening balance sheet does not balance: assets {opening['asset']:,.6g} "
                              f"!= liabilities {opening['liability']:,.6g} + equity {opening['equity']:,.6g}; "
                              f"difference {opening_difference:,.6g}")
    clearing = getattr(entity, "_consolidation_clearing_account", None)
    if clearing is not None:
        balances = _vec(result, entity._balance(clearing))
        assets_total = _vec(result, entity.bs.total_assets)
        for t, balance in enumerate(balances):
            if abs(balance) > 1e-6 * max(1.0, abs(assets_total[t])):
                period = result.model.timeline.periods[t].label
                raise LedgerError(f"{entity.name}: acquisition clearing balance {balance:,.6g} is not zero "
                                  f"in period {period}")
    bs = bs_rows(result, entity)
    L = entity.label
    assets, le = _find(bs, L("total_assets")), _find(bs, L("total_liabilities_equity"))
    for t in range(n):
        if abs(assets[t] - le[t]) > 1e-6 * max(1.0, abs(assets[t])):
            raise LedgerError(f"{entity.name}: assets {assets[t]} != liabilities + equity {le[t]} "
                              f"in period {result.model.timeline.periods[t].label}")
    attribution = getattr(entity, "_group_profit_attribution", None)
    if attribution is not None:
        net = _vec(result, entity.net_income)
        nci = _vec(result, attribution["nci"])
        parent = _vec(result, attribution["parent"])
        for t in range(n):
            if abs(net[t] - nci[t] - parent[t]) > 1e-6 * max(1.0, abs(net[t])):
                raise LedgerError(f"{entity.name}: profit attribution {nci[t] + parent[t]} != net income {net[t]} "
                                  f"in period {result.model.timeline.periods[t].label}")
    cash = result[entity.bs.cash]
    cash_prev = result[entity.bs.cash.opening]
    direct_rows = cf_rows(result, entity)
    flows = _find(direct_rows, L("net_change"))
    for t in range(n):
        if actual_until is not None and t <= actual_until:
            continue
        change = cash[t] - cash_prev[t]
        if abs(change - flows[t]) > 1e-6 * max(1.0, abs(change)):
            raise LedgerError(f"{entity.name}: cash flow {flows[t]} != change in cash {change} in period {t}")
    indirect_rows = cf_indirect_rows(result, entity)
    indirect = _find(indirect_rows, L("operating"))
    direct = _find(direct_rows, L("operating"))
    for t in range(n):
        if actual_until is not None and t <= actual_until:
            continue
        if abs(indirect[t] - direct[t]) > 1e-6 * max(1.0, abs(direct[t])):
            raise LedgerError(f"{entity.name}: indirect operating cash flow {indirect[t]} != direct {direct[t]} "
                              f"in period {t}")
    indirect = _find(indirect_rows, L("net_change"))
    direct = flows
    for t in range(n):
        if actual_until is not None and t <= actual_until:
            continue
        if abs(indirect[t] - direct[t]) > 1e-6 * max(1.0, abs(direct[t])):
            raise LedgerError(f"{entity.name}: indirect cash flow {indirect[t]} != direct {direct[t]} "
                              f"in period {t}")
