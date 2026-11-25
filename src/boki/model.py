"""Model: the timeline, inputs, named series, unknowns and checks. render() evaluates."""
from __future__ import annotations

import calendar
import math
import warnings
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable

from .evaluator import Render, ensure_recursion_limit
from .series import DATE, MONTHS, Data, Fn, Named, Series, lift, written_unit
from .units import (_DIMENSIONLESS, Dims, Quantity, Unit, UnitError, _describe, _display_unit_of, _labeled, month,
                    _prefixed)


# ---- time ------------------------------------------------------------------------

def _months(step) -> int:
    """Length in months of a time unit (`month`, `year`) or quantity (`3 * month`)."""
    if isinstance(step, Unit) and step.dims == MONTHS:
        return int(round(step.scale))
    if isinstance(step, Quantity) and step.dims == MONTHS:
        return int(round(step.value))
    raise UnitError(f"a period length must be a time like month, year or 3 * month, got {step!r}")


def _dims(u):
    if u is None or isinstance(u, frozenset):
        return u
    if isinstance(u, Unit):
        return u.dims
    raise TypeError(f"expected a unit, got {u!r}")


def _check_display(node: Series, display) -> Unit | None:
    """display= for a series: a unit of the series' own dimension (a different time base is fine: 1 / year
    for a monthly rate). A series of unknown dimension takes the display unit's, as if unit= had been given."""
    if display is None:
        return None
    u = _display_unit_of(display)
    if node.unit is None:
        node.unit = u.dims
    elif node.unit != u.dims:
        raise UnitError(f"display={u.name} is in {_describe(u.dims)}, but {node.name!r} is in {_describe(node.unit)}")
    return u


def parse_date(x) -> date:
    """Return a date from a date, a string such as ``"2027-04"``, or a year.

    This is the parser behind every date argument of boki (``start=``, ``end=``, period keys, ``by_year`` keys), so
    ``b.date("2027-04")`` shows what a date string means. A missing month or day is January or the 1st.

    Parameters
    ----------
    x : date, str, or int
        A `datetime.date` (returned as is), or text of year, month and day separated by ``-`` or ``/``: ``"2028"``,
        ``"2027-04"``, ``"2027/04/15"``. An integer year such as ``2028`` is read as ``"2028"``.

    Returns
    -------
    date
        The `datetime.date`: January 1 of the year, or the 1st of the month, when the text has fewer parts.

    Raises
    ------
    ValueError
        At construction, if the text is not made of integer year, month and day, or the date does not exist (for
        example month 13).

    See Also
    --------
    boki.timeline : Build periods of varying length from a start date.

    Examples
    --------
    >>> import boki as b
    >>> b.date("2027-04")
    datetime.date(2027, 4, 1)
    >>> b.date("2027/04/15")
    datetime.date(2027, 4, 15)
    >>> b.date(2028)
    datetime.date(2028, 1, 1)
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    if isinstance(x, date):
        return x
    parts = [int(p) for p in str(x).replace("/", "-").split("-")]
    return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)   # "2028": Jan 1


def add_months(d: date, k: int) -> date:
    y, m = divmod(d.month - 1 + k, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


@dataclass(frozen=True)
class Period:
    """One period of a model's timeline: when it starts, how long it is, and what it is called.

    Periods come from `Timeline`; read them from ``m.timeline.periods``. Periods of one model need not have the same
    length (see `boki.timeline`).

    Parameters
    ----------
    start : date | None
        First day of the period, or ``None`` for an undated model (one built with an integer ``start``).
    months : int
        Length of the period in months.
    label : str
        Name of the period, used to select it (``r.value(x, "2028")``) and as the column heading.
    end_date : date | None
        First day after the period. ``None``, the default, computes it from ``start`` and ``months``.

    Attributes
    ----------
    start : date | None
        First day of the period, or ``None`` for an undated model.
    months : int
        Length of the period in months.
    label : str
        Name of the period: ``"2027"`` for a 12-month period starting in January, ``"2027-04"`` for other dated
        periods, and the integer text for an undated model.
    end_date : date | None
        First day after the period, as given at construction; ``None`` when it is computed. Use `Period.end`.

    See Also
    --------
    boki.model.Timeline : The periods of a model, in order.
    boki.Model.period_end : The end of each period as a series.

    Examples
    --------
    The second quarter of a quarterly model:

    >>> import boki as b
    >>> m = b.Model("Quarters", start="2027-01", periods=4, step=3 * b.month)
    >>> p = m.timeline.periods[1]
    >>> p.label, p.start, p.end, p.months
    ('2027-04', datetime.date(2027, 4, 1), datetime.date(2027, 7, 1), 3)
    """
    start: date | None
    months: int
    label: str
    end_date: date | None = None

    @property
    def end(self) -> date | None:
        """First day after the period, which is the start of the next period.

        Returns
        -------
        date or None
            The explicit ``end_date`` if one was given, else ``start`` plus ``months`` (a day past the month's end
            is clamped). ``None`` for an undated period. The last day of the period is one day earlier.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Months", start="2027-01", periods=2, step=b.month)
        >>> [p.end for p in m.timeline.periods]
        [datetime.date(2027, 2, 1), datetime.date(2027, 3, 1)]
        """  # noqa: DOC203
        return None if self.start is None else self.end_date or add_months(self.start, self.months)


class Timeline:
    """Ordered periods of a model, each with its own length in months.

    A model's timeline is ``m.timeline``. Build one by giving `Model` a ``start``, a step and a count, or pass your own
    with ``Model(timeline=...)``: `Timeline.regular` for equal periods and `boki.timeline` for periods of varying
    length.

    Parameters
    ----------
    periods : list[Period]
        The periods in time order. At least one is needed.

    Attributes
    ----------
    periods : list[Period]
        The periods in time order.
    n : int
        Number of periods.

    Raises
    ------
    ValueError
        At construction, if ``periods`` is empty.

    See Also
    --------
    boki.timeline : Periods of varying length.
    boki.Model : A model, which holds its timeline.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Plan", start="2027-04", periods=3, step=b.year)
    >>> m.timeline.n
    3
    >>> [period.label for period in m.timeline.periods]
    ['2027-04', '2028-04', '2029-04']
    """  # noqa: DOC602, DOC603

    def __init__(self, periods: list[Period]):
        if not periods:
            raise ValueError("a timeline needs at least one period")
        self.periods = periods
        self.n = len(periods)

    @classmethod
    def regular(cls, start, step, n: int | None = None, end=None) -> "Timeline":
        """Return a timeline of equal periods.

        Parameters
        ----------
        start : date, str, or int
            First period. A date or date text (``"2027-04"``) makes dated periods. An integer such as ``2027`` makes
            undated periods labelled ``"2027"``, ``"2028"``, ... and needs ``n``.
        step : Unit or Quantity
            Length of each period: ``b.month``, ``b.year``, or a multiple such as ``3 * b.month``. It must be a time.
        n : int, optional
            Number of periods. When given, ``end`` is ignored.
        end : date or str, optional
            Date text such as ``"2029-03"``. Without ``n``, the timeline has every period that starts in or before
            the month of ``end``.

        Returns
        -------
        Timeline
            The periods. Annual periods that start in January are labelled by calendar year (``"2027"``); other dated
            periods by their first month (``"2027-04"``).

        Raises
        ------
        ValueError
            At construction, if ``start`` is an integer and ``n`` is missing; if ``start`` is a date and neither ``n``
            nor ``end`` is given or a date cannot be parsed; or if the timeline would have no period.
        UnitError
            At construction, if ``step`` is not a time.

        See Also
        --------
        boki.timeline : Periods of varying length.

        Examples
        --------
        Four quarters, from a start and from an end:

        >>> import boki as b
        >>> from boki.model import Timeline
        >>> [p.label for p in Timeline.regular("2027-01", 3 * b.month, 4).periods]
        ['2027-01', '2027-04', '2027-07', '2027-10']
        >>> Timeline.regular("2027-01", 3 * b.month, end="2027-12").n
        4
        """  # noqa: DOC105, DOC107, DOC503
        k = _months(step)
        if isinstance(start, int):
            if n is None:
                raise ValueError("an integer start needs periods=")
            return cls([Period(None, k, str(start + i)) for i in range(n)])
        d = parse_date(start)
        if n is None:
            last = parse_date(end)
            n = ((last.year - d.year) * 12 + last.month - d.month) // k + 1
        periods = []
        calendar_years = k == 12 and d.month == 1        # annual periods on calendar years read "2027"
        for i in range(n):
            s = add_months(d, i * k)
            end = add_months(d, (i + 1) * k)
            periods.append(Period(s, k, s.strftime("%Y" if calendar_years else "%Y-%m"), end))
        return cls(periods)

    def index(self, key) -> int:
        if isinstance(key, bool):
            raise TypeError("a period key cannot be a bool")
        if isinstance(key, int):
            i = key if key >= 0 else self.n + key
            if not 0 <= i < self.n:
                raise IndexError(f"period {key} is outside the model (0..{self.n - 1})")
            return i
        for i, p in enumerate(self.periods):              # a period's own label ("2028", "FY2028")
            if isinstance(key, str) and p.label == key:
                return i
        d = parse_date(key)
        for i, p in enumerate(self.periods):
            if p.start is not None and p.start <= d < p.end:
                return i
        raise IndexError(f"{key} is outside the model's timeline")


def timeline(start, segments: list[tuple]) -> Timeline:
    """Return a timeline whose periods change length, such as monthly during construction and quarterly after.

    Pass the result to ``Model(timeline=...)``. Each segment adds a run of equal periods that follows the previous
    one. Periods are labelled by their first month (``"2027-04"``).

    Parameters
    ----------
    start : date or str
        First day of the first period, for example ``"2015-09"``.
    segments : list of tuple
        ``(count, step)`` pairs in time order: ``count`` periods of length ``step``, a time such as ``b.month``,
        ``b.year`` or ``3 * b.month``.

    Returns
    -------
    Timeline
        The periods of all segments in order.

    Raises
    ------
    UnitError
        At construction, if a step is not a time.
    ValueError
        At construction, if the date cannot be parsed or no segment has a period.

    See Also
    --------
    boki.model.Timeline.regular : Equal periods.
    boki.Model : Takes the timeline with ``timeline=``.

    Examples
    --------
    Three monthly periods and then two quarterly ones; ``m.period_length`` gives each period's months:

    >>> import boki as b
    >>> t = b.timeline("2027-01", [(3, b.month), (2, 3 * b.month)])
    >>> m = b.Model("Mixed", timeline=t)
    >>> [p.label for p in m.timeline.periods]
    ['2027-01', '2027-02', '2027-03', '2027-04', '2027-07']
    >>> m.render()[m.period_length]
    [1, 1, 1, 3, 3]
    """  # noqa: DOC105, DOC107, DOC502
    d = parse_date(start)
    periods = []
    for count, step in segments:
        k = _months(step)
        for _ in range(count):
            end = add_months(d, k)
            periods.append(Period(d, k, d.strftime("%Y-%m"), end))
            d = end
    return Timeline(periods)


class _Time(Series):
    def __init__(self, fn: Callable[[Period, int], Any], name: str, unit):
        self._fn, self.name, self.unit = fn, name, unit

    def _eval(self, r, t):
        return self._fn(r.model.timeline.periods[t], t)


# ---- inputs and unknowns ---------------------------------------------------------

class Input(Series):
    """Named assumption of the model, with a default, optional scenarios and optional allowed values.

    `Model.input` creates inputs. An input is a `Series` that is scalar when its default is a single value and has a
    value per period when the default is a series (such as ``b.by_year({...})``). Its value is chosen at render time,
    in this order: ``render(inputs={...})``, then the scenario named by ``render(scenario=...)``, then the default.
    The input shows in the unit its default was written in (``400 * MWh`` shows in MWh), or in ``display``.

    Parameters
    ----------
    name : str
        Name of the input, unique among the model's inputs and series.
    default : Series | Quantity | float | str
        The value used when no override applies. A string is a choice; see ``choices``.
    scenarios : dict | None
        Values by scenario name, in any form ``default`` takes. ``None`` means no scenarios.
    choices : list | tuple | dict | None
        The allowed values: a list or tuple of them, or a dict that maps a choice name to its value. ``None`` allows
        any value.
    display : Unit | None
        Unit to show the input in. It must have the dimensions of the value.
    source : str | None
        Citation or provenance for the assumption, such as ``"FY2024 10-K p.42"``. Shown in the Excel Inputs sheet.
    note : str | None
        Free-text rationale or comment for the assumption.

    Attributes
    ----------
    name : str
        Name of the input.
    default : Series | Quantity | float | str
        The default value, as given.
    scenarios : dict
        Values by scenario name; empty when there are none.
    choices : list, tuple, dict, or None
        The allowed values, as given; ``None`` when any value is allowed.
    source : str or None
        Citation or provenance string, or ``None``.
    note : str or None
        Free-text note, or ``None``.

    See Also
    --------
    boki.Model.input : Create an input.
    boki.Model.render : Choose the scenario and override inputs for one render.
    boki.model.Unknown : A value found by solving instead of chosen.

    Notes
    -----
    ``Result.to_excel`` writes the inputs on an Inputs sheet, and the formulas refer to their cells, so changing an
    assumption in Excel changes the result. See the `inputs guide
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#inputs>`_.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Plan", start="2027-01", periods=2, step=b.month)
    >>> churn = m.input("Churn rate", 0.03, scenarios={"Bear": 0.05})
    >>> m.render()[churn], m.render(scenario="Bear")[churn], m.render(inputs={churn: 0.01})[churn]
    (0.03, 0.05, 0.01)
    """  # noqa: DOC602, DOC603

    def __init__(self, name: str, default: Series | Quantity | float | str, scenarios: dict | None,
                 choices: list | tuple | dict | None, display: Unit | None = None,
                 source: str | None = None, note: str | None = None):
        self.name, self.default = name, default
        self.scenarios = scenarios or {}
        self.choices = choices
        self.source = source
        self.note = note
        self.scalar = not isinstance(default, Series) or default.scalar
        self.unit = None if isinstance(default, str) else lift(default).unit
        self.shown = getattr(default, "shown", None)
        if isinstance(choices, dict):
            units = {lift(v).unit for v in choices.values() if not isinstance(v, str)}
            self.unit = units.pop() if len(units) == 1 else None
        self.display = _check_display(self, display)

    def resolve(self, r: Render):
        if self.name in r.inputs:
            v = r.inputs[self.name]
        elif r.scenario in self.scenarios:
            v = self.scenarios[r.scenario]
        else:
            v = self.default
        if isinstance(self.choices, dict) and isinstance(v, str):
            if v not in self.choices:
                raise ValueError(f"input {self.name!r}: {v!r} is not one of {list(self.choices)}")
            v = self.choices[v]
        elif isinstance(self.choices, (list, tuple)) and v not in self.choices:
            raise ValueError(f"input {self.name!r}: {v!r} is not one of {list(self.choices)}")
        return v

    def _eval(self, r, t):
        v = self.resolve(r)
        if isinstance(v, Series):
            return r.value(v, None if v.scalar else t)
        if isinstance(v, Quantity):
            if self.unit is not None and v.dims != self.unit:
                raise UnitError(f"input {self.name!r} is in {_describe(self.unit)}, got {_describe(v.dims)}")
            return v.value
        return v


class Unknown(Series):
    """Value that `Model.solve` finds, instead of one you choose.

    `Model.unknown` creates unknowns. An unknown is scalar (one value for the whole model) unless it was declared with
    ``per_period=True``, which gives one value per period. Before solving, and in a render without a solve, it has its
    initial value. Use it in expressions like any other series; the equation passed to `Model.solve` fixes it.

    Parameters
    ----------
    name : str
        Name of the unknown, unique among the model's series.
    init : Series | Quantity | float
        Starting value of the search, a number or a `Quantity` (a constant, not a series).
    per_period : bool
        Whether the unknown has a value in each period (``True``) or one value (``False``).
    unit : Unit | Dims | None
        Unit of the value. ``None`` takes the unit of ``init``.

    Attributes
    ----------
    name : str
        Name of the unknown.
    init : float
        Starting value in base units, as a plain number.

    See Also
    --------
    boki.Model.unknown : Create an unknown.
    boki.Model.solve : Solve for unknowns.
    boki.model.Input : A value you choose.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Solve", start="2027-01", periods=2, step=b.year)
    >>> debt = m.unknown("Debt", init=100)
    >>> m.solve(debt, debt == 0.5 * debt + 10)
    >>> round(m.render()[debt], 6)
    20.0
    """  # noqa: DOC602, DOC603

    def __init__(self, name: str, init: Series | Quantity | float, per_period: bool, unit: Unit | Dims | None):
        init = lift(init)
        self.name, self.scalar = name, not per_period
        self.init = init.value
        self.unit = _dims(unit) if unit is not None else init.unit

    def _eval(self, r, t):
        return r.unknowns.get((id(self), t), self.init)


@dataclass
class _Solve:
    unknowns: list[Unknown]
    equations: list[Series]
    integer: bool
    lower: float | None
    tol: float
    max_iter: int


LEVELS = ("error", "warn", "off")


def check_level(level: str) -> str:
    if level not in LEVELS:
        raise ValueError(f"check level must be one of {', '.join(map(repr, LEVELS))}, not {level!r}")
    return level


@dataclass
class _Check:
    cond: Series
    message: str
    level: str = "error"


@dataclass
class CheckResult:
    """Outcome of one check in one render: whether it held, where it failed, and how to report it.

    Read the results of a render from ``r.checks``. A check at level ``"off"`` is not evaluated and has no result.

    Parameters
    ----------
    name : str
        The check's message, such as ``"Minimum cash"``.
    level : str
        ``"error"`` or ``"warn"``. With ``render(checks="warn")`` an ``"error"`` check reports as ``"warn"``.
    passed : bool
        Whether the check held in every period it was evaluated.
    periods : list[str]
        Labels of the periods in which it failed; empty when it passed.
    detail : str
        The sentence that reports the outcome: the name, and for a failure the periods and, for a comparison, the
        worst period with both sides.

    Attributes
    ----------
    name : str
        The check's message.
    level : str
        ``"error"`` or ``"warn"``.
    passed : bool
        Whether the check held in every evaluated period.
    periods : list[str]
        Labels of the periods in which it failed.
    detail : str
        The sentence that reports the outcome.

    See Also
    --------
    boki.Model.check : Declare a check.
    boki.Result.checks : The results of a render.
    boki.CheckFailed : Raised when an ``"error"`` check fails.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Checks", start="2027-01", periods=3, step=b.month)
    >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
    >>> m.check(cash >= 0, "Cash is not negative", level="off")
    >>> m.check(cash >= -50, "Overdraft limit")
    >>> check = m.render().checks[0]
    >>> check.name, check.level, check.passed, check.periods
    ('Overdraft limit', 'error', True, [])
    """
    name: str
    level: str
    passed: bool
    periods: list[str]
    detail: str


def _number(x: float) -> str:
    x = float(f"{x:.6g}")
    return f"{x:,.0f}" if abs(x) >= 1000 or x == int(x) else f"{x:,.6g}"


def _expression(node: Series, v: float) -> str:
    """'Cash -12,400', '5,000,000' for a constant, 'expression -3' for an unnamed formula."""
    if node.name:
        return f"{node.name} {_number(v)}"
    return _number(v) if node.scalar else f"expression {_number(v)}"


def _evaluate(name: str, level: str, labels: list[str], holds: list, sides=None) -> CheckResult:
    """holds[t] is True/False (None: not evaluated). sides = (lhs values, lhs label fn, rhs values, rhs label fn)
    names the two sides of a comparison, so the worst period can report both."""
    bad = [t for t, h in enumerate(holds) if h is not None and not h]
    when = ", ".join(labels[t] for t in bad[:5]) + (", ..." if len(bad) > 5 else "")
    detail = name
    if bad:
        detail = f"{name} (fails in {when}"
        if sides is not None:
            lhs, lname, rhs, rname = sides
            try:
                t = max(bad, key=lambda t: abs(lhs[t] - rhs[t]))
                detail += f"; worst {labels[t]}: {lname(lhs[t])} vs {rname(rhs[t])}"
            except TypeError:
                pass
        detail += ")"
    return CheckResult(name, level, not bad, [labels[t] for t in bad], detail)


@dataclass(frozen=True)
class FxPair:
    """Read-only exchange-rate record returned by `Model.fx`.

    Rates are quoted as units of `quote` currency for one unit of `base` currency. Use `Model.fx` to validate and
    register a pair with a model; it normalizes each rate input to a `Series`.

    Parameters
    ----------
    base : Unit
        Unit represented by one unit in each rate. Use a currency unit for a currency pair. Required; no default.
    quote : Unit
        Unit measured by each rate. Use a currency unit for a currency pair. Required; no default.
    closing : Series
        Closing exchange rate in quote units per base unit. `Model.fx` accepts a scalar, `Quantity`, `Series`, a
        `dict` keyed by period, or a `list` or `tuple` with one value per model period. Required; no default.
    average : Series
        Average exchange rate in quote units per base unit. It accepts the same forms as `closing` through
        `Model.fx`. Required; no default.
    opening : Series
        Single opening exchange rate in quote units per base unit. `Model.fx` accepts a scalar, `Quantity`, or
        scalar `Series`. Required; no default.

    Attributes
    ----------
    base : Unit
        Base currency unit.
    quote : Unit
        Quote currency unit.
    closing : Series
        Closing exchange-rate series.
    average : Series
        Average exchange-rate series.
    opening : Series
        Scalar opening exchange rate.

    Raises
    ------
    TypeError
        At construction through `Model.fx`, if `base` or `quote` is not a `Unit`, or if `opening` is not scalar.
    ValueError
        At construction through `Model.fx`, if `base` and `quote` have the same dimensions or the pair already
        exists in the model.
    UnitError
        At construction through `Model.fx`, if a rate uses units other than quote currency per base currency.
    CheckFailed
        At evaluation by `Model.render`, if any exchange rate is not positive.

    See Also
    --------
    boki.Model.fx : Add and register an exchange-rate pair with a model.

    Notes
    -----
    Use distinct currency units for `base` and `quote`. Numeric rate inputs are dimensionless and receive quote-per-
    base units from `Model.fx`. `opening` applies before the first model period. `closing` and `average` provide
    period-specific rates.

    Examples
    --------
    Register a pair with monthly closing and average rates:

    >>> import boki as b
    >>> from boki.units import JPY, USD
    >>> m = b.Model("FX", start="2027-01", periods=2, step=b.month)
    >>> pair = m.fx(JPY, USD, closing=[0.0067, 0.0068], average=[0.0066, 0.0067], opening=0.0065)
    >>> r = m.render()
    >>> r.value(pair.closing, "2027-02")
    0.0068
    """
    base: Unit
    quote: Unit
    closing: Series
    average: Series
    opening: Series


class CheckFailed(AssertionError):
    """Error raised by `Model.render` when a check at level ``"error"`` fails.

    `Model.render` computes everything first, so the exception carries the complete `Result` for inspection. It
    subclasses `AssertionError`, so a test runner reports it as a failed assertion.

    Parameters
    ----------
    message : str
        The text of the error: ``"checks failed:"`` followed by one line for each failed check.
    result : Result
        The complete result of the render that failed its checks.
    failures : list[CheckResult]
        The failed checks at level ``"error"``.

    Attributes
    ----------
    result : Result
        The complete result: ``e.result[cash]``, ``e.result.pl(co)``.
    failures : list[CheckResult]
        The failed checks at level ``"error"``, each with its name, failing periods and detail.

    See Also
    --------
    boki.Model.check : Declare a check and its level.
    boki.model.CheckResult : One check's outcome.

    Examples
    --------
    Read the failure and the values behind it:

    >>> import boki as b
    >>> m = b.Model("Cash", start="2027-01", periods=3, step=b.month)
    >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
    >>> m.check(cash >= 0, "Cash is not negative")
    >>> try:
    ...     m.render()
    ... except b.CheckFailed as error:
    ...     print(error.failures[0].periods)
    ...     print(error.result[cash])
    ['2027-02']
    [50, -20, 30]
    """  # noqa: DOC602, DOC603

    def __init__(self, message: str, result: "Result", failures: list[CheckResult]):
        super().__init__(message)
        self.result, self.failures = result, failures


# ---- model -----------------------------------------------------------------------

class Model:
    """Business-plan model: a timeline, assumptions, named series, entities with books, and checks.

    A model is built by declaring things on it and nothing is computed until `Model.render`. Declaring (`Model.input`,
    `Model.series`, `Model.entity`, `Model.check`, ...) builds expressions and checks units; `Model.render` evaluates
    them and returns a `Result` to read values, statements and the Excel workbook from. A model can be rendered again
    with other inputs or scenarios.

    Parameters
    ----------
    name : str
        Name of the model. It appears in error messages.
    start : date | str | int | None
        First period. A date or date text (``"2027-04"``) makes dated periods; an integer such as ``2027`` makes
        undated periods labelled ``"2027"``, ``"2028"``, ..., which needs ``periods``. Required unless ``timeline`` is
        given.
    end : date | str | None
        Date text such as ``"2029-03"``. Without ``periods``, the model has every period that starts in or before the
        month of ``end``. Ignored when ``periods`` or ``timeline`` is given.
    periods : int | None
        Number of periods. Required unless ``end`` or ``timeline`` is given.
    step : Unit | Quantity
        Length of each period: ``b.month`` (the default), ``b.year``, or a multiple such as ``3 * b.month``. It
        must be a time. Ignored when ``timeline`` is given.
    timeline : Timeline | None
        A ready-made timeline, for periods of different lengths (`boki.timeline`). It replaces ``start``, ``end``,
        ``periods`` and ``step``.
    actual_until : date | str | int | None
        Last historical (actual) period, as a period index, label (``"2024"``), or date. Periods up to and including
        ``actual_until`` are historical actuals; periods after it are forecast periods whose opening balances carry
        forward from the last actual period. ``None`` (the default) treats every period as a forecast period.

    Attributes
    ----------
    name : str
        Name of the model.
    timeline : Timeline
        The model's periods.
    actual_until : int or None
        Zero-based period index of the last historical period, or ``None`` when the model has no historical periods.
    is_actual : Series
        Boolean series that is ``True`` in periods up to and including ``actual_until``, and ``False`` otherwise.
    is_forecast : Series
        Boolean series that is ``True`` in forecast periods (after ``actual_until``, or every period when
        ``actual_until`` is ``None``).
    t : Series
        Zero-based index of each period (0, 1, 2, ...), dimensionless.
    date : Series
        First day of each period, a date series. It is missing for undated periods.
    period_end : Series
        First day after each period, which is the start of the next one. ``m.period_end - 1 * b.day`` is the last day.
    period_length : Series
        Length of each period in months, so a quarterly period is 3. Multiply a rate per month by it to get the amount
        in the period.
    entities : list
        The entities of the model, in the order `Model.entity` created them.
    groups : list
        The groups of the model, in the order `Model.group` created them.

    See Also
    --------
    boki.timeline : Periods of varying length.
    boki.Result : What `Model.render` returns.

    Notes
    -----
    Construction raises `ValueError` if ``start`` is an integer and ``periods`` is missing, if ``start`` is a date and
    neither ``periods`` nor ``end`` is given, if a date cannot be parsed, or if the model would have no period. It
    raises `UnitError` if ``step`` is not a time.

    A plain number used as a rate is per period: ``0.03`` is 3% per period, whether the period is a month or a year.
    A rate per time (``0.12 / b.year``) is converted by the length of each period; see ``period_length``.

    Models hold closures, so they cannot be pickled. See the `model and periods guide
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#model-and-periods>`_.

    Examples
    --------
    A three-month model with an assumption and two series, read from a render:

    >>> import boki as b
    >>> m = b.Model("Coffee", start="2027-01", periods=3, step=b.month)
    >>> cups = m.input("Cups", 100)
    >>> price = m.series("Price", data={0: 3, 1: 3, 2: 4})
    >>> revenue = m.series("Revenue", cups * price)
    >>> r = m.render()
    >>> r[revenue]
    [300, 300, 400]
    >>> r.value(revenue, "2027-03")
    400

    Annual periods starting in January are labelled by year, and ``end`` includes the last period that starts in its
    month:

    >>> m = b.Model("Annual", start="2027-01", end="2029-06", step=b.year)
    >>> [p.label for p in m.timeline.periods]
    ['2027', '2028', '2029']
    >>> m.n
    3
    """  # noqa: DOC602, DOC603

    def __init__(self, name: str, start: date | str | int | None = None, end: date | str | None = None,
                 periods: int | None = None, step: Unit | Quantity = month, timeline: Timeline | None = None,
                 *, actual_until: date | str | int | None = None):
        self.name = name
        self.timeline = timeline or Timeline.regular(start, step, periods, end)
        self.actual_until: int | None = None if actual_until is None else self.timeline.index(actual_until)
        self.t = _Time(lambda p, t: t, "t", _DIMENSIONLESS)
        self.date = _Time(lambda p, t: p.start, "date", DATE)
        self.period_end = _Time(lambda p, t: p.end, "period_end", DATE)
        self.period_length = _Time(lambda p, t: p.months, "period_length", MONTHS)
        self.is_actual = _Time(
            lambda p, t: self.actual_until is not None and t <= self.actual_until,
            "is_actual", _DIMENSIONLESS,
        )
        self.is_forecast = _Time(
            lambda p, t: self.actual_until is None or t > self.actual_until,
            "is_forecast", _DIMENSIONLESS,
        )
        self._named: dict[str, Series] = {}
        self._inputs: dict[str, Input] = {}
        self._solves: list[_Solve] = []
        self._checks: list[_Check] = []
        self.entities: list = []
        self.groups: list = []
        self._fx: dict[tuple, FxPair] = {}
        ensure_recursion_limit(self.timeline.n)

    @property
    def n(self) -> int:
        """Number of periods in the model.

        Returns
        -------
        int
            The length of the timeline.

        Examples
        --------
        >>> import boki as b
        >>> b.Model("Plan", start="2027-01", periods=36, step=b.month).n
        36
        """
        return self.timeline.n

    def _register(self, node: Series) -> Series:
        if node.name:
            if node.name in self._named:
                raise ValueError(f"a series named {node.name!r} already exists in {self.name!r}")
            self._named[node.name] = node
        return node

    def group(self, name: str, parent):
        """Create a group of entities under a parent, whose consolidated books the statements read.

        Add subsidiaries to the group with ``g.own(sub, method="consolidate")``. ``r.pl(g)``, ``r.bs(g)`` and
        ``r.cf(g)`` then show the consolidated statements.

        Parameters
        ----------
        name : str
            Name of the group, unique among the model's entities and groups.
        parent : Entity
            The entity that owns the group, normally the parent company of the subsidiaries. It must be an entity of
            this model.

        Returns
        -------
        Group
            The new group. It is also appended to ``m.groups``.

        Raises
        ------
        ValueError
            At construction, if an entity or a group with this name already exists in the model, or ``parent`` is not
            an entity of this model.

        See Also
        --------
        boki.Model.entity : Create an entity with its own books.

        Notes
        -----
        See `consolidation <https://github.com/combinatrix-ai/boki/blob/master/docs/consolidation.md>`_ for how
        groups combine subsidiaries.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Group", start="2027-01", periods=2, step=b.year)
        >>> parent = m.entity("Parent", standard=b.IFRS)
        >>> sub = m.entity("Sub", standard=b.IFRS)
        >>> g = m.group("Holdings", parent=parent)
        >>> g.own(sub, method="consolidate")
        >>> g.name, [group.name for group in m.groups]
        ('Holdings', ['Holdings'])
        """  # noqa: DOC105, DOC107, DOC203
        from .group import Group
        if any(g.name == name for g in self.groups) or any(e.name == name for e in self.entities):
            raise ValueError(f"an entity or group named {name!r} already exists")
        g = Group(self, name, parent)
        self.groups.append(g)
        return g

    def entity(self, name: str, standard=None, fiscal=None, layout=None, currency=None, tax_rate=None):
        """Create an entity: a company with its own double-entry books.

        The entity holds the ``pl``, ``bs`` and ``cf`` makers of its layout, from which the line items of the
        statements are created (``co.pl.revenue("Sales", 100)``).

        Parameters
        ----------
        name : str
            Name of the entity, unique among the model's entities and groups. It titles the entity's statements.
        standard : Standard, optional
            Accounting standard: ``b.JGAAP`` (the default), ``b.IFRS`` or ``b.USGAAP``. It sets the account names,
            their order and the standard-specific treatments.
        fiscal : Fiscal, optional
            Fiscal calendar from ``b.fiscal(year_end)``, such as ``b.fiscal("03-31")``. Statements and tables read with
            ``by="fiscal_year"`` need it. The default has no fiscal calendar.
        layout : Layout, optional
            Industry layout such as ``b.layouts.bank``. The default is the standard's general layout.
        currency : Unit, optional
            Functional currency, such as ``JPY``. The default lets the first amount booked decide it.
        tax_rate : scalar or Series, optional
            Default tax rate for deferred taxes, a dimensionless ratio such as ``0.3`` for 30%.

        Returns
        -------
        Entity
            The new entity. It is also appended to ``m.entities``.

        Raises
        ------
        ValueError
            At construction, if an entity or a group with this name already exists in the model.

        See Also
        --------
        boki.Model.group : Combine entities into consolidated books.

        Notes
        -----
        The entity's postings balance by construction. ``Model.render`` verifies that the balance sheet balances and
        that the direct and indirect cash flows agree with each other and with the change in cash, and raises
        `LedgerError` otherwise. See `double-entry bookkeeping
        <https://github.com/combinatrix-ai/boki/blob/master/docs/double-entry.md>`_.

        Examples
        --------
        A company with an opening balance, a revenue line and a cost, in a monthly model:

        >>> import boki as b
        >>> m = b.Model("Cafe", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("Cafe", standard=b.IFRS)
        >>> co.bs.opening(cash=1000)
        >>> sales = co.pl.revenue("Sales", 100)
        >>> rent = co.pl.sga("Rent", 40)
        >>> r = m.render()
        >>> r[co.pl.net_income]
        [60, 60, 60]
        >>> r.value(co.bs.cash, "2027-03")
        1180.0
        """  # noqa: DOC105, DOC107, DOC203
        from .ledger import Entity, JGAAP
        if any(e.name == name for e in self.entities) or any(g.name == name for g in self.groups):
            raise ValueError(f"an entity or group named {name!r} already exists")
        e = Entity(self, name, standard or JGAAP, fiscal, layout, currency, tax_rate)
        self.entities.append(e)
        return e

    def fx(self, base: Unit, quote: Unit, *, closing, average, opening) -> FxPair:
        """Register the exchange rates of one currency pair and return them.

        Rates are quoted as units of ``quote`` per one unit of ``base``. Entities with different functional currencies
        use the rates to translate amounts between them (consolidation, intercompany trades).

        Parameters
        ----------
        base : Unit
            The currency of one unit, such as ``b.units.USD``.
        quote : Unit
            The currency the rates are measured in, such as ``b.units.JPY``. It must differ from ``base``.
        closing : scalar, Quantity, Series, dict, list, or tuple
            Rate at the end of each period, in ``quote`` per ``base``. A plain number is the same rate every period. A
            dict maps periods to rates; a list or tuple has one rate for each period of the model.
        average : scalar, Quantity, Series, dict, list, or tuple
            Average rate over each period, in ``quote`` per ``base``, in the same forms as ``closing``.
        opening : scalar, Quantity, or Series
            One rate at the model start, in ``quote`` per ``base``. It must be a single value.

        Returns
        -------
        FxPair
            The registered rates, as series named ``<base>/<quote> closing`` and so on.

        Raises
        ------
        TypeError
            At construction, if ``base`` or ``quote`` is not a `Unit`, or ``opening`` is not a single value.
        ValueError
            At construction, if ``base`` and ``quote`` are the same currency, the pair is already registered, or a list
            has the wrong number of rates.
        UnitError
            At construction, if a rate has units other than ``quote`` per ``base``.
        CheckFailed
            At evaluation, if a rate is not positive in some period.

        See Also
        --------
        boki.model.FxPair : The registered rates.

        Examples
        --------
        >>> import boki as b
        >>> from boki.units import JPY, USD
        >>> m = b.Model("FX", start="2027-01", periods=2, step=b.month)
        >>> pair = m.fx(USD, JPY, closing=[150, 152], average=151, opening=149)
        >>> r = m.render()
        >>> r[pair.closing]
        [150.0, 152.0]
        """  # noqa: DOC105, DOC107, DOC503
        if not isinstance(base, Unit) or not isinstance(quote, Unit):
            raise TypeError("m.fx base and quote must be currency units")
        if base.dims == quote.dims:
            raise ValueError("m.fx base and quote must be different currencies")
        key = (base.dims, quote.dims)
        if key in self._fx:
            raise ValueError(f"m.fx already has a rate for {base.name}/{quote.name}")
        ratio = quote / base

        def rate_series(value, name, *, scalar=False):
            if isinstance(value, dict):
                source = Data(value, name)
            elif isinstance(value, (list, tuple)):
                if len(value) != self.n:
                    raise ValueError(f"m.fx {name} needs {self.n} rates, got {len(value)}")
                source = Data(dict(enumerate(value)), name)
            else:
                source = lift(value)
            if scalar and not source.scalar:
                raise TypeError(f"m.fx {name} must be one opening rate")
            if source.unit not in (None, _DIMENSIONLESS, ratio.dims):
                raise UnitError(f"m.fx {name} must be in {ratio.name}, got {_describe(source.unit)}")
            result = source if source.unit == ratio.dims else source * ratio
            result = Named(f"{base.name}/{quote.name} {name}", result)
            self.check(result > 0, f"m.fx {base.name}/{quote.name} {name} rates must be positive")
            return result

        pair = FxPair(base, quote,
                      rate_series(closing, "closing"),
                      rate_series(average, "average"),
                      rate_series(opening, "opening", scalar=True))
        self._fx[key] = pair
        return pair

    def _fx_rate(self, base, quote, method: str) -> tuple[Series, bool]:
        base, quote = getattr(base, "dims", base), getattr(quote, "dims", quote)
        for pair in self._fx.values():
            direct = pair.base.dims == base and pair.quote.dims == quote
            reverse = pair.base.dims == quote and pair.quote.dims == base
            if direct or reverse:
                if method == "acquisition":
                    rate = pair.closing.lag(1, fill=pair.opening)
                elif method == "opening":
                    rate = pair.opening
                else:
                    rate = getattr(pair, method)
                return rate, direct
        raise ValueError(f"the model needs m.fx rates from {_describe(base)} to {_describe(quote)}")

    def _convert_currency(self, amount: Series, base, quote, method: str = "average", *, rate=None) -> Series:
        base = getattr(base, "dims", base) or amount.unit
        quote = getattr(quote, "dims", quote)
        if base is None or quote is None or base == quote:
            return amount
        if amount.unit in (None, _DIMENSIONLESS):
            amount = amount * Unit("functional currency", base)
        elif amount.unit != base:
            raise UnitError(f"cannot translate an amount in {_describe(amount.unit)} as {_describe(base)}")
        if rate is not None:
            rate = lift(rate)
            ratio = Unit("quote currency", quote) / Unit("base currency", base)
            if rate.unit in (None, _DIMENSIONLESS):
                rate = rate * ratio
            elif rate.unit != ratio.dims:
                raise UnitError(f"fx_rate must be quoted in {ratio.name}, got {_describe(rate.unit)}")
            self.check(rate > 0, "fx_rate must be positive")
            return amount * rate
        rate, direct = self._fx_rate(base, quote, method)
        return amount * rate if direct else amount / rate

    def input(self, name: str, default, scenarios: dict | None = None, choices=None, *, display=None,
              source: str | None = None, note: str | None = None) -> Input:
        """Declare a named assumption with a default value.

        An input is a series you can change without editing the model: per render with ``render(inputs=...)`` or
        ``render(scenario=...)``, and in the Inputs sheet of the Excel output. It shows in the unit its default was
        written in (``400 * MWh`` shows in MWh), or in ``display``.

        Parameters
        ----------
        name : str
            Name of the input, unique among the model's inputs and series.
        default : scalar, Quantity, Series, or str
            Value used unless a scenario or ``render(inputs=...)`` replaces it. A plain number is dimensionless; as a
            rate it is per period (``0.03`` is 3% per period, whether the period is a month or a year). A
            `Quantity` carries a unit (``3000 * JPY``). A rate per time (``0.12 / b.year``) is stored per month and
            becomes per period when multiplied by ``m.period_length``. A series such as ``b.by_year({...})`` gives
            a value in each period. A string is one of ``choices``.
        scenarios : dict, optional
            Maps a scenario name to its value, in any form ``default`` takes. ``render(scenario=name)`` uses it.
        choices : list, tuple, or dict, optional
            The allowed values. A list or tuple restricts the value to its members. A dict maps a choice name to its
            value: the input's value is a name, and the input reads as the mapped value.
        display : Unit or Quantity, optional
            Unit to show the input in, of the same dimension as its value. A different time base is allowed, such as
            ``1 / b.year`` for a monthly rate.
        source : str, optional
            Citation or provenance for the assumption, such as ``"FY2024 10-K p.42"``. Written to the Excel Inputs
            sheet when any input carries a source or note.
        note : str, optional
            Free-text rationale or note for the assumption.

        Returns
        -------
        Input
            The new input, a series that is scalar when ``default`` is a single value.

        Raises
        ------
        ValueError
            At construction, if an input or a series with this name already exists. At evaluation, if the chosen value
            is not among ``choices``.
        TypeError
            At construction, if ``default`` has a type a series expression cannot use, such as a list, or ``display``
            is not a unit.
        UnitError
            At construction, if ``display`` has other dimensions than the value. At evaluation, if a `Quantity`
            override has other dimensions than the input.

        See Also
        --------
        boki.Model.series : A named series computed from an expression.
        boki.Model.render : Choose a scenario or override inputs for one render.

        Examples
        --------
        An assumption with a scenario, and an override for one render:

        >>> import boki as b
        >>> m = b.Model("Plan", start="2027-01", periods=3, step=b.month)
        >>> churn = m.input("Churn rate", 0.03, scenarios={"Bear": 0.05})
        >>> m.render()[churn]
        0.03
        >>> m.render(scenario="Bear")[churn]
        0.05
        >>> m.render(inputs={"Churn rate": 0.01})[churn]
        0.01

        A rate per year is per month internally; multiplying by the period length gives the rate for each period:

        >>> m = b.Model("Rates", start="2027-01", periods=2, step=3 * b.month)
        >>> rate = m.input("Interest rate", 0.12 / b.year)
        >>> [round(v, 6) for v in m.render()[rate * m.period_length]]
        [0.03, 0.03]
        """  # noqa: DOC105, DOC107, DOC503
        if name in self._inputs:
            raise ValueError(f"input {name!r} already exists")
        node = Input(name, default, scenarios, choices, display, source=source, note=note)
        self._inputs[name] = node
        return self._register(node)

    def series(self, name=None, expr=None, *, data: dict | None = None, unit=None, display=None):
        """Create a named series from an expression, from period data, or from a function of the period.

        There are four forms. ``m.series("x", expr)`` names an expression. ``m.series("x")`` declares a series to
        define later with `Named.define`. ``m.series("x", data={...})`` holds values at chosen periods and 0
        elsewhere. ``@m.series`` (or ``@m.series(unit=...)``) turns a Python function of the period index into a
        series; inside it, ``x[t]`` reads other series as numbers and ordinary ``if`` works.

        Parameters
        ----------
        name : str or callable, optional
            Name of the series, unique in the model. A function, when ``@m.series`` is applied to it, becomes the
            series and is named after itself. May be omitted with ``data=`` (an unnamed series) or when returning a
            decorator.
        expr : Series, Quantity, or number, optional
            The expression. Leave it out to declare the series and define it later.
        data : dict, optional
            Values at selected periods, as ``{period: value}``: the period is an index, a label (``"2028"``) or a
            date, and the value a number or `Quantity`. Other periods are 0. A series made with ``data=`` is fixed
            and cannot be defined later.
        unit : Unit, optional
            The unit the series must have, such as ``JPY``. It is checked against the expression or the function's
            return values; without it the series takes the expression's unit. Ignored with ``data=``.
        display : Unit or Quantity, optional
            Unit to show the series in, of the same dimension as its values (``MWh``, or ``1 / b.year`` for a monthly
            rate). Without it a series defined as a quantity shows in the unit it was written in, and a computed
            physical quantity (W, Wh, g, m) gets an SI prefix chosen from its values.

        Returns
        -------
        Series or callable
            The `Named` series for the first two forms. For ``data=`` a series of the fixed values, and for
            ``@m.series`` the series that the function computes; both read like any other series. Called with only
            ``unit=`` or ``display=``, it returns the decorator to apply to a function.

        Raises
        ------
        ValueError
            At construction, if a series with this name already exists in the model.
        UnitError
            At construction, if ``expr`` has other units than ``unit``, if ``display`` has other dimensions than the
            series, or if the values of ``data`` mix units.
        TypeError
            At construction, if ``expr`` or a data value has a type a series expression cannot use, such as a list, or
            ``unit`` or ``display`` is not a unit.

        See Also
        --------
        boki.Model.input : A named assumption that scenarios and renders can change.
        boki.series.Named.define : Define a declared series later.

        Examples
        --------
        The four forms in a monthly model:

        >>> import boki as b
        >>> m = b.Model("Forms", start="2027-01", periods=3, step=b.month)
        >>> units = m.series("Units", data={0: 10, 1: 12})
        >>> revenue = m.series("Revenue", units * 30)
        >>> margin = m.series("Margin")
        >>> _ = margin.define(revenue * 0.2)
        >>> @m.series
        ... def doubled(t):
        ...     return units[t] * 2
        >>> r = m.render()
        >>> r[revenue], r[margin], r[doubled]
        ([300, 360, 0], [60.0, 72.0, 0.0], [20, 24, 0])
        """  # noqa: DOC105, DOC107, DOC203, DOC502
        if callable(name) and not isinstance(name, Series):
            return self._register(Fn(name))
        if name is None and expr is None and data is None:
            def decorate(fn):
                node = Fn(fn, unit=_dims(unit))
                node.display = _check_display(node, display)
                return self._register(node)
            return decorate
        if data is not None:
            node = Data(data, name)
        else:
            node = Named(name, expr, unit=_dims(unit))
        node.display = _check_display(node, display)
        return self._register(node)

    def unknown(self, name: str, init=0.0, per_period: bool | None = None, unit=None) -> Unknown:
        """Declare a value that `Model.solve` will find.

        Use an unknown for a number the model must determine, such as the debt amount that meets a covenant, or the
        headcount that covers demand. Declaring it does not solve it: pass it to `Model.solve` with an equation.

        Parameters
        ----------
        name : str
            Name of the unknown, unique among the model's series.
        init : scalar or Quantity, default=0.0
            Starting value of the search, in the unit of the unknown. A `Quantity` such as ``100 * USD`` also fixes the
            unit. When there is no solve (or ``fix=`` replaces it), the unknown keeps this value. It selects among
            solutions when an equation has several.
        per_period : bool, optional
            ``True`` gives one value for each period; ``False`` or ``None`` (the default) gives one value for the whole
            model.
        unit : Unit, optional
            Unit of the value, such as ``USD``. The default is the unit of ``init``.

        Returns
        -------
        Unknown
            The new unknown, a series that is scalar unless ``per_period`` is true.

        Raises
        ------
        ValueError
            At construction, if a series with this name already exists in the model.
        TypeError
            At construction, if ``unit`` is not a unit, or ``init`` has a type a series expression cannot use.

        See Also
        --------
        boki.Model.solve : Find the value of an unknown.
        boki.Model.input : A value you choose instead.

        Examples
        --------
        A scalar unknown with a starting value, and a per-period unknown in a unit:

        >>> import boki as b
        >>> from boki.units import USD
        >>> m = b.Model("Unknowns", start="2027-01", periods=2, step=b.month)
        >>> debt = m.unknown("Debt", init=100 * USD)
        >>> hires = m.unknown("Hires", per_period=True)
        >>> m.render()[debt], m.render()[hires]
        (100.0, [0.0, 0.0])
        """  # noqa: DOC105, DOC107, DOC502
        node = Unknown(name, init, bool(per_period), unit)
        return self._register(node)

    def solve(self, unknowns, equations, *, integer: bool = False, min: float | None = None,
              tol: float = 1e-9, max_iter: int = 500) -> None:
        """Declare the equation that determines one or more unknowns; render solves it.

        The equation's form selects the method. ``u == expression``, with the unknown alone on the left, iterates a
        fixed point (use it for circular references such as interest on an average balance). Any other ``==`` for
        a scalar unknown, such as ``npv == 0`` or ``value == price``, is a goal seek by the secant method, as in
        Excel. A per-period unknown solves each period: ``==`` by secant, and ``>=``/``<=`` with ``integer=True`` for
        the smallest integer that satisfies the condition.

        Parameters
        ----------
        unknowns : Unknown, or list or tuple of Unknown
            The unknowns to solve for, from `Model.unknown`.
        equations : Series, or list or tuple of Series
            One equation for each unknown, in the same order, built by comparing series with ``==``, ``>=`` or ``<=``.
        integer : bool, default=False
            Search whole numbers for per-period ``>=``/``<=`` conditions.
        min : float, optional
            Lowest value tried in the integer search of each period. The default is 0.
        tol : float, default=1e-9
            Convergence tolerance. Fixed-point iteration stops when no unknown moves by more than ``tol`` (relative to
            its size, for values above 1). A goal seek stops when the equation's two sides differ by at most ``tol``
            times the larger of 1 and the right side. A per-period secant needs the sides to differ by less than
            ``tol``.
        max_iter : int, default=500
            Maximum iterations for each solve.

        Raises
        ------
        ValueError
            At construction, if the number of equations differs from the number of unknowns.
        TypeError
            At construction, if an unknown is not made by `Model.unknown`, if an equation is not a comparison, or if a
            scalar unknown's equation is not written with ``==``. At evaluation, if several scalar unknowns are solved
            and an equation is not written ``u == expression``.
        ArithmeticError
            At evaluation, if the solve does not converge within ``max_iter`` iterations, the secant stalls, or no
            integer satisfies a per-period condition.
        NotImplementedError
            At evaluation, if a per-period unknown has an equation other than ``==`` or an integer ``>=``/``<=``.

        See Also
        --------
        boki.Model.unknown : Declare an unknown.
        boki.Model.render : Solve and evaluate; ``fix=`` skips the solve for chosen unknowns.

        Notes
        -----
        Cycles are detected before evaluation. Only values passed to `solve` are solved; a cycle that is not
        wrapped in `solve` raises `CycleError`. When a cycle has several solutions, the ``init`` of the unknown picks
        one. See `Solving <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#solving>`_.

        Examples
        --------
        A fixed point and a goal seek on scalar unknowns:

        >>> import boki as b
        >>> m = b.Model("Solve", start="2027-01", periods=2, step=b.year)
        >>> debt = m.unknown("Debt", init=100)
        >>> m.solve(debt, debt == 0.5 * debt + 10)
        >>> rate = m.unknown("Rate", init=1)
        >>> m.solve(rate, 3 * rate == 12)
        >>> r = m.render()
        >>> round(r[debt], 6), round(r[rate], 6)
        (20.0, 4.0)

        The smallest whole headcount that covers demand in each period:

        >>> m = b.Model("Hiring", start="2027-01", periods=2, step=b.month)
        >>> hires = m.unknown("Hires", per_period=True)
        >>> demand = m.series("Demand", data={0: 25, 1: 40})
        >>> m.solve(hires, hires * 10 >= demand, integer=True, min=0)
        >>> m.render()[hires]
        [3, 4]
        """  # noqa: DOC105, DOC107, DOC503
        us = list(unknowns) if isinstance(unknowns, (list, tuple)) else [unknowns]
        es = list(equations) if isinstance(equations, (list, tuple)) else [equations]
        if len(us) != len(es):
            raise ValueError("m.solve needs one equation per unknown")
        for u, e in zip(us, es):
            if not isinstance(u, Unknown):
                raise TypeError(f"m.solve solves for an m.unknown(...), not {type(u).__name__} {u.name!r}; declare it "
                                f"with m.unknown({u.name!r}, unit=...) (add per_period=True for a value in each period)")
            if not isinstance(e, Series) or not hasattr(e, "fn"):
                raise TypeError(f"the equation for {u.name!r} must compare two series (==, >=, <=)")
            if integer or not u.scalar:
                continue
            if e.fn.__name__ != "eq":
                raise TypeError(f"a scalar unknown ({u.name!r}) needs an equation written with ==")
        self._solves.append(_Solve(us, es, integer, min, tol, max_iter))

    def check(self, cond, message: str, level: str = "error") -> None:
        """Declare a condition that must hold in every period, such as ``cash >= 0``.

        A check is a statement the modeler makes about the plan. A failure at the default level stops `Model.render`
        with `CheckFailed`, which still carries the complete result. The result of every check is listed in
        ``r.checks``, and the Excel output has a Checks sheet.

        Parameters
        ----------
        cond : Series
            The condition, usually a comparison (``cash >= 5 * USD``) or a combination with ``&``, ``|`` and ``~``. It
            fails in a period where it is false. A period where it is missing is not evaluated.
        message : str
            Name of the check, shown in the failure report and in ``r.checks``.
        level : str, default="error"
            ``"error"``: a failure raises `CheckFailed`. ``"warn"``: a failure only warns, for a benchmark the plan may
            miss. ``"off"``: not evaluated and not reported.

        Raises
        ------
        ValueError
            At construction, if ``level`` is not ``"error"``, ``"warn"`` or ``"off"``.
        TypeError
            At construction, if ``cond`` has a type a series expression cannot use.

        See Also
        --------
        boki.Model.render : Evaluates the checks; ``checks="warn"`` downgrades the errors while exploring.
        boki.CheckFailed : Raised for a failed ``"error"`` check.

        Notes
        -----
        The failure message names the failing periods and, for a comparison of two series, both sides in the period of
        the largest violation. See `checks stop the render
        <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#checks-stop-the-render>`_.

        Examples
        --------
        A failing check stops the render and reports the worst period:

        >>> import boki as b
        >>> m = b.Model("Cash", start="2027-01", periods=3, step=b.month)
        >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
        >>> m.check(cash >= 0, "Cash is not negative")
        >>> try:
        ...     m.render()
        ... except b.CheckFailed as error:
        ...     print(error)
        checks failed:
        Cash is not negative (fails in 2027-02; worst 2027-02: Cash -20 vs 0)
        """  # noqa: DOC105, DOC107, DOC502
        self._checks.append(_Check(lift(cond), message, check_level(level)))

    def _input_values(self, inputs: dict) -> dict:
        """inputs= keyed by the input node or its name; an unknown key is an error, not ignored."""
        out = {}
        for k, v in inputs.items():
            name = k.name if isinstance(k, Input) else k
            if name not in self._inputs:
                raise KeyError(f"render(inputs=): no input named {name!r}")
            out[name] = v
        return out

    def render(self, scenario: str | None = None, inputs: dict | None = None,
               fix: dict | None = None, checks: str | None = None) -> "Result":
        """Evaluate the model and return its result.

        Everything is computed first: the solves, the ledger tie-outs, and the checks. Then failed ``"warn"`` checks
        issue warnings and failed ``"error"`` checks raise `CheckFailed`, whose ``result`` is the complete `Result`.
        A model can be rendered any number of times with different arguments.

        Parameters
        ----------
        scenario : str, optional
            Name of a scenario. Inputs declared with ``scenarios=`` take the value of this scenario; the others keep
            their default.
        inputs : dict, optional
            Overrides as ``{input or name: value}``, which take precedence over scenarios and defaults. A value is a
            number, a `Quantity` in the input's unit, a series, or a choice name.
        fix : dict, optional
            ``{unknown: value}``: use this value for the unknown and skip solving for it, for example a pasted result
            of the source spreadsheet.
        checks : str, optional
            ``"warn"`` downgrades every ``"error"`` check, yours and the built-in ones, to a warning for this render,
            while exploring a plan that does not hold together yet. Checks at level ``"off"`` stay off. The default
            ``None`` keeps the levels.

        Returns
        -------
        Result
            The values, statements and Excel output of this render.

        Raises
        ------
        ValueError
            At call, if ``checks`` is neither ``None`` nor ``"warn"``.
        KeyError
            At call, if ``inputs`` names an input that does not exist.
        CheckFailed
            At evaluation, if a check at level ``"error"`` fails, including the built-in check that cash is not
            negative.
        LedgerError
            At evaluation, if an entity's books do not tie out: the opening or a closing balance sheet does not balance,
            or the direct and indirect cash flows disagree with each other or with the change in cash.
        UnitError
            At evaluation, if a `Quantity` in ``fix`` has other dimensions than its unknown.

        See Also
        --------
        boki.Model.check : Declare a check.
        boki.Model.solve : Declare the equations solved during a render.
        boki.Result : The object returned.

        Notes
        -----
        Evaluation errors of the series the render reads, such as a division by zero, a value outside a ``choices``
        list, or `CycleError`, are raised here or when the result is read.

        Examples
        --------
        Render a scenario, and downgrade a failing check to a warning:

        >>> import boki as b
        >>> m = b.Model("Plan", start="2027-01", periods=3, step=b.month)
        >>> growth = m.input("Growth", 0.0, scenarios={"Bull": 0.1})
        >>> sales = m.series("Sales", 100 * (1 + growth) ** m.t)
        >>> m.render()[sales]
        [100.0, 100.0, 100.0]
        >>> [round(v, 2) for v in m.render(scenario="Bull")[sales]]
        [100.0, 110.0, 121.0]
        >>> cash = m.series("Cash", data={1: -5})
        >>> m.check(cash >= 0, "Cash is not negative")
        >>> import warnings
        >>> with warnings.catch_warnings(record=True) as caught:
        ...     warnings.simplefilter("always")
        ...     r = m.render(checks="warn")
        >>> r.checks[0].level, r.checks[0].passed, len(caught)
        ('warn', False, 1)
        """  # noqa: DOC105, DOC503
        if checks not in (None, "warn"):
            raise ValueError(f"render(checks=) must be None or 'warn', not {checks!r}")
        r = Render(self, self._input_values(inputs or {}))
        r.scenario = scenario
        r.unknowns = {}
        for s in self._solves:
            _run_solve(r, s, fix or {})
        result = Result(self, r)
        from .statements import verify
        for e in self.entities + [g.books for g in self.groups]:
            verify(result, e)
        labels = [p.label for p in self.timeline.periods]
        found = []
        for c in self._checks:
            if c.level != "off":
                found.append(self._run_check(r, c, labels))
        for e in self.entities:
            if e.checks.cash_level != "off":
                found.append(_cash_check(result, e, labels))
        if checks == "warn":
            for f in found:
                f.level = "warn"
        result.checks = found
        for f in found:
            if not f.passed and f.level == "warn":
                warnings.warn(f"check failed: {f.detail}", stacklevel=2)
        failures = [f for f in found if not f.passed and f.level == "error"]
        if failures:
            raise CheckFailed("checks failed:\n" + "\n".join(f.detail for f in failures), result, failures)
        return result

    @staticmethod
    def _run_check(r: Render, c: _Check, labels: list[str]) -> CheckResult:
        import operator
        holds = [None if v is None else bool(v) for v in r.values(c.cond)]
        sides = None
        fn = getattr(c.cond, "fn", None)
        if fn in (operator.ge, operator.le, operator.eq, operator.gt, operator.lt) and len(c.cond.args) == 2:
            a, b = c.cond.args
            lhs, rhs = r.values(a), r.values(b)
            sides = (lhs, lambda v: _expression(a, v), rhs, lambda v: _expression(b, v))
        return _evaluate(c.message, c.level, labels, holds, sides)


Model.__init__.__doc__ = Model.__doc__      # the class docstring documents the constructor, as numpydoc does


def _cash_check(result: "Result", entity, labels: list[str]) -> CheckResult:
    cash = result[entity.bs.cash]
    holds = [v >= -1e-9 for v in cash]
    sides = (cash, lambda v: f"cash {_number(v)}", [0.0] * len(cash), _number)
    return _evaluate(f"{entity.name}: cash is not negative", entity.checks.cash_level, labels, holds, sides)


# ---- solving ---------------------------------------------------------------------

def _split(eq: Series):
    lhs, rhs = eq.args
    return eq.fn.__name__, lhs, rhs


def _run_solve(r: Render, s: _Solve, fix: dict) -> None:
    for u in s.unknowns:
        if u in fix:
            v = fix[u]
            if isinstance(v, Quantity):
                if u.unit is not None and v.dims != u.unit:
                    raise UnitError(f"fix for {u.name!r} is in {_describe(v.dims)}, not {_describe(u.unit)}")
                v = v.value
            for t in ([None] if u.scalar else range(r.n)):
                r.unknowns[(id(u), t)] = v
            r.invalidate()
    todo = [(u, e) for u, e in zip(s.unknowns, s.equations) if u not in fix]
    if not todo:
        return
    if all(u.scalar for u, _ in todo):
        _solve_fixed_point(r, todo, s)
    else:
        for u, e in todo:
            _solve_per_period(r, u, e, s)


def _solve_fixed_point(r: Render, todo, s: _Solve) -> None:
    """Gauss-Seidel on u = rhs(u) when each equation is written `u == expr`; a single equation of
    any other form (npv == 0) is a goal seek on its residual."""
    if len(todo) == 1 and _split(todo[0][1])[1] is not todo[0][0]:
        return _goal_seek(r, *todo[0], s)
    for u, e in todo:
        op, lhs, _ = _split(e)
        if op != "eq" or lhs is not u:
            raise TypeError(f"write the equation for {u.name!r} as `{u.name} == expression`")
    for _ in range(s.max_iter):
        delta = 0.0
        for u, e in todo:
            _, _, rhs = _split(e)
            key = (id(u), None)
            old = r.unknowns.get(key, u.init)
            new = r.value(rhs, None if rhs.scalar else 0)
            r.unknowns[key] = new
            r.invalidate()
            delta = max(delta, abs(new - old) / max(1.0, abs(new)))
        if delta < s.tol:
            return
    raise ArithmeticError(f"m.solve did not converge for {[u.name for u, _ in todo]} in {s.max_iter} iterations")


def _at_float_limit(x0: float, x1: float, f0: float, f1: float, scale: float) -> bool:
    """The secant has run out of floating-point room: the unknown can no longer move
    (its last two values are within a few ulps), and the residual has fallen far below
    where it started. With large terms (a project NPV in the hundreds of billions) the
    rounding left in lhs - rhs can exceed an absolute tolerance that no float of the
    unknown can meet. The residual drop rules out a step or a pole, where the unknown
    also stops moving but the residual stays large."""
    return abs(x1 - x0) <= 4 * math.ulp(x1) and min(abs(f0), abs(f1)) <= 1e-12 * scale


def _secant_iterate(residual: Callable[[float], float], x0: float, x1: float, *, tol: float,
                    max_iter: int, inclusive: bool, scale: Callable[[], float] | None,
                    stalled: Callable[[float], str], exhausted: str) -> float:
    f0, f1 = residual(x0), residual(x1)
    initial_scale = max(abs(f0), abs(f1))
    for _ in range(max_iter):
        threshold = tol if scale is None else tol * max(1.0, abs(scale()))
        converged = abs(f1) <= threshold if inclusive else abs(f1) < threshold
        if converged:
            return x1
        if _at_float_limit(x0, x1, f0, f1, initial_scale):
            return x0 if abs(f0) < abs(f1) else x1
        if f1 == f0:
            raise ArithmeticError(stalled(f1))
        x0, x1, f0 = x1, x1 - f1 * (x1 - x0) / (f1 - f0), f1
        f1 = residual(x1)
    raise ArithmeticError(exhausted)


def _goal_seek(r: Render, u: Unknown, e: Series, s: _Solve) -> None:
    """Secant iterations on lhs - rhs = 0 over a scalar unknown (Excel's Goal Seek)."""
    _, lhs, rhs = _split(e)
    key = (id(u), None)

    def residual(x):
        r.unknowns[key] = x
        r.invalidate()
        return r.value(lhs, None if lhs.scalar else 0) - r.value(rhs, None if rhs.scalar else 0)

    x0 = u.init
    x1 = x0 * 1.01 + 1e-6 if x0 else 1e-3
    root = _secant_iterate(
        residual, x0, x1, tol=s.tol, max_iter=s.max_iter, inclusive=True,
        scale=lambda: r.value(rhs, None if rhs.scalar else 0),
        stalled=lambda f1: f"m.solve could not find {u.name!r} with {e!r}: "
                           f"the residual is {f1:g} at two different values of {u.name!r}",
        exhausted=f"m.solve could not find {u.name!r} with {e!r} in {s.max_iter} iterations")
    residual(root)


def _solve_per_period(r: Render, u: Unknown, e: Series, s: _Solve) -> None:
    op, lhs, rhs = _split(e)

    def holds(t, x):
        r.unknowns[(id(u), t)] = x
        r.invalidate()
        a = r.value(lhs, None if lhs.scalar else t)
        b = r.value(rhs, None if rhs.scalar else t)
        if a is None or b is None:
            return True
        return {"ge": a >= b, "gt": a > b, "le": a <= b, "lt": a < b, "eq": math.isclose(a, b)}[op]

    lo = s.lower if s.lower is not None else 0
    for t in range(r.n):
        if op in ("ge", "gt", "le", "lt") and s.integer:
            if holds(t, lo):
                continue
            step = 1
            while not holds(t, lo + step):
                step *= 2
                if step > 2 ** 40:
                    raise ArithmeticError(f"m.solve: no value of {u.name!r} satisfies the condition at period {t}")
            a, b = lo + step // 2, lo + step
            while b - a > 1:
                mid = (a + b) // 2
                a, b = (a, mid) if holds(t, mid) else (mid, b)
            holds(t, b)
        elif op == "eq":
            _secant(t, u, lhs, rhs, r, s)
        else:
            raise NotImplementedError("per-period solve supports == and integer >= / <= conditions")


def _secant(t, u, lhs, rhs, r, s):
    def f(x):
        r.unknowns[(id(u), t)] = x
        r.invalidate()
        return r.value(lhs, None if lhs.scalar else t) - r.value(rhs, None if rhs.scalar else t)

    root = _secant_iterate(
        f, u.init, u.init + 1.0, tol=s.tol, max_iter=s.max_iter, inclusive=False, scale=None,
        stalled=lambda f1: f"m.solve did not converge for {u.name!r} at period {t}: "
                           f"the residual is {f1:g} at two different values of {u.name!r}",
        exhausted=f"m.solve did not converge for {u.name!r} at period {t}")
    f(root)


# ---- result ----------------------------------------------------------------------

class Result:
    """Values, statements and Excel output of one render of a model.

    `Model.render` returns a result. It holds the evaluated model: read any series from it with ``r[x]`` (all periods)
    or ``r.value(x, period)`` (one period), statements with `Result.pl`, `Result.bs` and `Result.cf`, arbitrary series
    as a table with `Result.table`, and write the workbook with `Result.to_excel`. Rendering again with other inputs
    gives a new, independent result.

    Parameters
    ----------
    model : Model
        The model that was rendered.
    render : Render
        The evaluation of the model, which holds the computed values. Internal.

    Attributes
    ----------
    checks : list[CheckResult]
        The outcome of every check of the model that was evaluated: yours and the built-in checks, such as that cash is
        never negative. Checks at level ``"off"`` are absent.

    See Also
    --------
    boki.Model.render : Creates a result.
    boki.CheckFailed : Carries the result of a render whose checks failed.

    Notes
    -----
    Only `Model.render` creates a result. Values are in base units (currency, Wh, months); tables and statements divide
    by a display unit or a money scale when they are shown.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Cafe", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("Cafe", standard=b.IFRS)
    >>> co.bs.opening(cash=1000, retained_earnings=1000)
    >>> sales = co.pl.revenue("Sales", 100)
    >>> rent = co.pl.sga("Rent", 40)
    >>> r = m.render()
    >>> r.value(co.pl.net_income, "2027-02")
    60
    >>> r[co.bs.cash]
    [1060.0, 1120.0, 1180.0]
    >>> [check.name for check in r.checks]
    ['Cafe: cash is not negative']
    """  # noqa: DOC602, DOC603

    def __init__(self, model: Model, render: Render):
        self.model, self._r = model, render
        self.checks: list[CheckResult] = []

    def __getitem__(self, key):
        """Return the values of a series: a list with one value per period, or one number for a scalar series.

        Parameters
        ----------
        key : Series or str
            The series. A string is the name of a series, input or unknown of the model (``r["Revenue"]``). Any other
            value is turned into a series, so ``r[x * 2]`` evaluates an expression that has no name.

        Returns
        -------
        list or float
            For a series with a value in each period, the list of values in period order, in base units (``None`` for a
            missing value). For a scalar series, its single value.

        Raises
        ------
        KeyError
            At call, if a string names no series of the model.
        TypeError
            At call, if ``key`` has a type a series expression cannot use.

        See Also
        --------
        boki.Result.value : The value in one period.
        boki.Result.table : Several series side by side.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Plan", start="2027-01", periods=3, step=b.month)
        >>> units = m.series("Units", data={0: 10, 1: 12, 2: 9})
        >>> total = m.series("Total", units.sum())
        >>> r = m.render()
        >>> r[units]
        [10, 12, 9]
        >>> r["Units"] == r[units]
        True
        >>> r[total]
        31
        >>> r[units * 2]
        [20, 24, 18]
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        node = self.model._named[key] if isinstance(key, str) else lift(key)
        if node.scalar:
            return self._r.value(node, None)
        return self._r.values(node)

    def to_excel(self, path, style=None, sheets=None, *, scenarios=None, omit_unused_model: bool = False,
                 checks: bool | None = None, **overrides):
        """Write the model to an Excel workbook that keeps live formulas.

        The workbook has an Inputs sheet, a Model sheet with one formula for each series and period, a sheet for each
        entity's statements, and a Checks sheet. Cells hold formulas that refer to the inputs, so changing an input in
        Excel recalculates the model.

        Parameters
        ----------
        path : str or path-like
            The ``.xlsx`` file to write. An existing file is replaced.
        style : Style, optional
            How numbers and headings look: a preset from ``b.styles`` (``b.styles.banker``, the default, ``japanese``,
            ``plain`` or ``sec``) or a modified copy. A style changes only how values are shown, never the model sheet's
            formulas.
        sheets : list, optional
            Where rows go, in reading order: a list of ``b.sheet(name, [...])`` whose entries are sections, series,
            ``b.row(...)``, ``b.block(...)``, ``b.panel(...)``, and ``b.link(...)``. The default writes every row to
            the Model sheet.
        scenarios : sequence of str, optional
            Scenario names to expose as a live Excel selector on the Inputs sheet (for example
            ``["Base", "Bull", "Bear"]``). Changing the active case cell recalculates the workbook in Excel.
        omit_unused_model : bool, default=False
            Drop unreachable Model-sheet rows and omit the Model sheet entirely when every placed sheet and check
            formula resolves without it. Remaining Model rows are listed in ``Report.unplaced``.
        checks : bool, optional
            Whether to write the Checks sheet. ``None`` (the default) follows ``style.statements``.
        **overrides
            Settings of the style applied for this call, such as ``money="$mm"`` (scale and label of money amounts),
            ``units={series: MWh}`` (display units), ``hide=[series, ...]``, ``columns="fiscal"`` or ``"periods"`` and
            ``helpers="group"`` or ``"show"``. They are the fields of `Style`.

        Returns
        -------
        Report
            What was written: counts of formula cells (``formulas``), cells written as values (``values``) and data
            cells (``data``), the cells guarded against a circular reference (``guarded``), why cells fell back to
            values (``reasons``), and any Model rows left unplaced (``unplaced``).

        Raises
        ------
        UnnamedAssumption
            At call, if a data table (``b.by_year``, ``b.step``, ...) used in an expression has no name; name it with
            ``m.input``.
        EquivalenceError
            At call, if a ``b.row(..., formula=...)`` or ``b.block(...)`` rewrite disagrees with boki across scenarios
            or perturbed inputs.
        ValueError
            At call, if ``sheets`` places a series twice with ``b.row``, links a row that is not placed, names two
            sheets alike, or gives an unnamed series no ``label=``; if ``units`` names a unit of another dimension; or
            if ``columns``, ``helpers`` or ``money`` has a value outside its choices.
        TypeError
            At call, if a keyword argument is not a setting of the style.

        See Also
        --------
        boki.Result.table : The same numbers as a table in Python.

        Notes
        -----
        A cell that Excel cannot compute from boki's expression is written as a value (highlighted) and counted in
        ``reasons``. Where Excel would see a circular reference that boki does not have, the cell is guarded with
        ``NA()`` and a ``CircularReferenceWarning`` is issued. See the `Excel output
        <https://github.com/combinatrix-ai/boki/blob/master/docs/excel.md>`_ and `row placement
        <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#excel-row-placement>`_ notes.

        Examples
        --------
        Write a model with a money scale in millions, and read how many cells are formulas:

        >>> import tempfile
        >>> import boki as b
        >>> m = b.Model("Cafe", start="2027-01", periods=3, step=b.month)
        >>> co = m.entity("Cafe", standard=b.IFRS)
        >>> co.bs.opening(cash=1000000, retained_earnings=1000000)
        >>> sales = co.pl.revenue("Sales", 100000)
        >>> r = m.render()
        >>> with tempfile.TemporaryDirectory() as folder:
        ...     report = r.to_excel(f"{folder}/cafe.xlsx", money="$mm")
        >>> report.formulas > 0
        True
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .excel import to_excel
        return to_excel(self, path, style, sheets, scenarios=scenarios,
                        omit_unused_model=omit_unused_model, checks=checks, **overrides)

    def value(self, node: Series, t=None):
        """Return the value of a series in one period.

        Parameters
        ----------
        node : Series
            The series to read; any value is turned into a series. A name string is not looked up: use ``r["name"]``.
        t : int, str, or date, optional
            The period: an index from 0 (negative counts from the end), a label (``"2028"``, ``"2027-04"``) or a date
            inside the period. Required for a series with a value in each period; a scalar series ignores it.

        Returns
        -------
        float
            The value in base units, or ``None`` when the series has no value in that period.

        Raises
        ------
        IndexError
            At call, if the period is outside the model's timeline.
        ValueError
            At call, if ``t`` is missing for a series with a value in each period, or cannot be read as a period.
        TypeError
            At call, if ``t`` is a bool.

        See Also
        --------
        boki.Result.__getitem__ : All the periods at once.

        Notes
        -----
        A bare ``r.value(x)`` is for scalar series (totals, inputs). Name the period for every other series, as in the
        examples.

        Examples
        --------
        Read one period by label, by index, and a scalar series:

        >>> import boki as b
        >>> m = b.Model("Plan", start="2027-01", periods=3, step=b.month)
        >>> units = m.series("Units", data={0: 10, 1: 12, 2: 9})
        >>> r = m.render()
        >>> r.value(units, "2027-02"), r.value(units, 2), r.value(units, -1)
        (12, 9, 9)
        >>> r.value(units.sum())
        31
        """  # noqa: DOC105, DOC107, DOC203, DOC502
        node = lift(node)
        return self._r.value(node, None if node.scalar else self.model.timeline.index(t))

    def display_unit(self, node: Series) -> Unit | None:
        """Return the unit that tables and Excel show a series in.

        The unit is chosen in this order: the ``display=`` of the series; the unit a quantity literal was written in
        (``m.input("x", 400 * MWh)`` shows in MWh); for a computed physical quantity (W, Wh, g, m and their per-month
        forms), the SI prefix that puts the row's largest absolute value over all periods in the range 1 to 1000. The
        unit is the same for every period of a row.

        Parameters
        ----------
        node : Series or str
            The series, or the name of a series, input or unknown of the model.

        Returns
        -------
        Unit or None
            The unit to show the values in, or ``None`` to show base units (a dimensionless series, or one whose unit
            is unknown).

        Raises
        ------
        KeyError
            At call, if a string names no series of the model.

        See Also
        --------
        boki.Model.series : Set a series' ``display=`` unit.
        boki.Result.table : Shows each row in its display unit.

        Notes
        -----
        Values stay in base units everywhere (W, Wh, per month); this only chooses how they are shown, so arithmetic,
        unit checks and Excel formulas are unaffected. Money is never prefixed (the style's ``money=`` scaling shows it)
        and dimensionless numbers have no unit to prefix.

        Examples
        --------
        >>> import boki as b
        >>> from boki.units import MWh, W
        >>> m = b.Model("Power", start="2027-01", periods=2, step=b.month)
        >>> capacity = m.input("Capacity", 400 * MWh)
        >>> load = m.series("Load", data={0: 3500 * W, 1: 1200 * W})
        >>> r = m.render()
        >>> r.display_unit(capacity).name, r.display_unit("Load").name, r.display_unit(m.t)
        ('MWh', 'kW', None)
        """  # noqa: DOC105, DOC203, DOC502
        node = self.model._named[node] if isinstance(node, str) else lift(node)
        chosen = written_unit(node)
        if chosen is not None:
            return chosen
        if node.unit is None or node.unit == _DIMENSIONLESS:
            return None
        vals = self[node]
        return _prefixed(node.unit, vals if isinstance(vals, list) else [vals])

    def table(self, nodes: Iterable[Series], *, where=None, unit=None, title: str = "", by=None,
              entity=None, stock: Iterable[Series] = ()):
        """Return chosen series side by side as a table, one row for each series and one column for each period.

        Each series is shown in its display unit (`Result.display_unit`), and its row is labelled with the unit when
        that is not the base unit, such as ``Generation (MWh)``. Printing the table, or showing it in a notebook, draws
        it as text.

        Parameters
        ----------
        nodes : iterable of Series
            The series to show, in row order. A scalar series repeats its value in every period. A row is labelled
            with the series' name, or ``?`` for an unnamed series.
        where : Series, optional
            A condition: only the periods where it holds are shown.
        unit : Unit or Quantity, optional
            Divide every row by this scale instead of using display units, and show no unit labels:
            ``unit=1000 * USD`` shows thousands of dollars. The default uses each series' display unit.
        title : str, default=""
            The table's title, shown above the first column.
        by : str, optional
            ``"fiscal_year"`` groups the periods into the fiscal years of ``entity``'s fiscal calendar: flows are summed
            over the year, and balances are kept at the year's last period. The default shows one column for each
            period.
        entity : Entity, optional
            The entity whose ``fiscal`` calendar groups the periods. Required with ``by="fiscal_year"``.
        stock : iterable of Series, default=()
            Series that are balances, such as headcount or customers, which ``by="fiscal_year"`` keeps at the year's
            last period instead of summing. Ledger balances and their totals are balances already.

        Returns
        -------
        Table
            The rows and column labels, in base units divided by each row's display unit or by ``unit``.

        Raises
        ------
        ValueError
            At call, if ``by`` is neither ``None`` nor ``"fiscal_year"``, or ``by="fiscal_year"`` has no entity with a
            fiscal calendar, or the periods are undated.

        See Also
        --------
        boki.Result.pl : A profit-and-loss statement as a table.
        boki.Result.__getitem__ : The values of one series as a list.

        Examples
        --------
        A series in a physical unit is labelled with its display unit:

        >>> import boki as b
        >>> from boki.units import MWh, USD
        >>> m = b.Model("Plant", start="2027-01", periods=3, step=b.month)
        >>> generation = m.series("Generation", data={0: 400 * MWh, 1: 500 * MWh, 2: 300 * MWh})
        >>> revenue = m.series("Revenue", generation / MWh * 30 * USD)
        >>> r = m.render()
        >>> table = r.table([generation, revenue], title="Plant")
        >>> table.columns
        ['2027-01', '2027-02', '2027-03']
        >>> [(row.label, row.unit, row.values) for row in table.rows]
        [('Generation', 'MWh', [400.0, 500.0, 300.0]), ('Revenue', '', [12000.0, 15000.0, 9000.0])]

        Group a monthly model by fiscal year; flows are summed and the headcount is kept at the year end:

        >>> m = b.Model("Years", start="2027-01", periods=24, step=b.month)
        >>> co = m.entity("Co", standard=b.IFRS, fiscal=b.fiscal("12-31"))
        >>> sales = m.series("Sales", 10)
        >>> headcount = m.series("Headcount", m.t + 1)
        >>> table = m.render().table([sales, headcount], by="fiscal_year", entity=co, stock=[headcount])
        >>> table.columns, table.row("Sales"), table.row("Headcount")
        (['FY2027-12', 'FY2028-12'], [120.0, 120.0], [12.0, 24.0])
        """  # noqa: DOC105, DOC107, DOC203, DOC502
        from .ledger import stock_kind
        from .statements import Row, Table, group, scale_of
        k = scale_of(unit)
        marked = {id(node) for node in stock}
        rows = []
        for node in nodes:
            vals = self[node]
            vals = vals if isinstance(vals, list) else [vals] * self.model.n
            kind = True if id(node) in marked else stock_kind(node)
            shown = self.display_unit(node) if unit is None else None
            label = shown.name if shown is not None and _labeled(shown) else ""
            div = shown.scale if shown is not None else k
            rows.append(Row(node.name or "?", [None if v is None else v / div for v in vals], kind, unit=label))
        cols, rows = group(self, rows, by, entity)
        if where is not None:
            keep = [i for i, v in enumerate(self[where]) if v]
            cols = [cols[i] for i in keep]
            rows = [Row(r.label, [r.values[i] for i in keep], r.stock, r.level, r.unit) for r in rows]
        return Table(title, cols, rows)

    def pl(self, entity, by=None, detail: bool = True):
        """Return an entity's profit and loss statement as a table.

        Rows follow the entity's layout: each kind with revenue or expense lines shows its total, and with
        ``detail=True`` the lines below it, followed by the subtotals (gross profit, operating profit, profit for the
        year). Labels follow the entity's accounting standard and language.

        Parameters
        ----------
        entity : Entity or Group
            The entity, or a group, whose consolidated books are shown.
        by : str, optional
            ``"fiscal_year"`` groups the periods into the fiscal years of the entity's calendar, summing flows. The
            default shows one column for each period.
        detail : bool, default=True
            Show the lines of each kind below its total; ``False`` shows only totals and subtotals.

        Returns
        -------
        Table
            The statement, titled ``PL <entity name>``.

        Raises
        ------
        ValueError
            At call, if ``by`` is neither ``None`` nor ``"fiscal_year"``, or ``by="fiscal_year"`` has an entity without
            a fiscal calendar, or the periods are undated.

        See Also
        --------
        boki.Result.bs : The balance sheet.
        boki.Result.cf : The cash flow statement.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Cafe", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("Cafe", standard=b.IFRS)
        >>> co.bs.opening(cash=1000, retained_earnings=1000)
        >>> sales = co.pl.revenue("Sales", 100)
        >>> rent = co.pl.sga("Rent", 40)
        >>> table = m.render().pl(co)
        >>> table.title, table.row("Profit for the year")
        ('PL Cafe', [60, 60])
        """  # noqa: DOC105, DOC107, DOC203, DOC502
        from .statements import Table, group, pl_rows
        entity = getattr(entity, "books", entity)          # a group: its consolidated books
        cols, rows = group(self, pl_rows(self, entity, detail), by, entity)
        return Table(f"PL {entity.name}", cols, rows)

    def bs(self, entity, by=None):
        """Return an entity's balance sheet as a table.

        Assets, liabilities and equity follow the entity's layout, with totals. Each row is a closing balance.

        Parameters
        ----------
        entity : Entity or Group
            The entity, or a group, whose consolidated books are shown.
        by : str, optional
            ``"fiscal_year"`` groups the periods into the fiscal years of the entity's calendar, keeping each balance at
            the year's last period. The default shows one column for each period.

        Returns
        -------
        Table
            The statement, titled ``BS <entity name>``.

        Raises
        ------
        ValueError
            At call, if ``by`` is neither ``None`` nor ``"fiscal_year"``, or ``by="fiscal_year"`` has an entity without
            a fiscal calendar, or the periods are undated.

        See Also
        --------
        boki.Result.pl : The profit and loss statement.
        boki.Result.cf : The cash flow statement.

        Notes
        -----
        The balance sheet balances by construction, and `Model.render` verifies it. See `double-entry
        bookkeeping <https://github.com/combinatrix-ai/boki/blob/master/docs/double-entry.md>`_.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Cafe", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("Cafe", standard=b.IFRS)
        >>> co.bs.opening(cash=1000, retained_earnings=1000)
        >>> sales = co.pl.revenue("Sales", 100)
        >>> table = m.render().bs(co)
        >>> table.title, table.row("Total assets")
        ('BS Cafe', [1100.0, 1200.0])
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .statements import Table, bs_rows, group
        entity = getattr(entity, "books", entity)
        cols, rows = group(self, bs_rows(self, entity), by, entity)
        return Table(f"BS {entity.name}", cols, rows)

    def cf(self, entity, by=None, method: str = "direct"):
        """Return an entity's cash flow statement as a table.

        Rows are operating, investing and financing cash flows and the net change in cash. The direct method lists the
        cash received and paid by line; the indirect method starts from the profit for the year.

        Parameters
        ----------
        entity : Entity or Group
            The entity, or a group, whose consolidated books are shown.
        by : str, optional
            ``"fiscal_year"`` groups the periods into the fiscal years of the entity's calendar, summing flows. The
            default shows one column for each period.
        method : str, default="direct"
            ``"direct"`` or ``"indirect"``. Both give the same totals; `Model.render` verifies it.

        Returns
        -------
        Table
            The statement, titled ``CF <entity name>``.

        Raises
        ------
        KeyError
            At call, if ``method`` is not ``"direct"`` or ``"indirect"``.
        ValueError
            At call, if ``by`` is neither ``None`` nor ``"fiscal_year"``, or ``by="fiscal_year"`` has an entity without
            a fiscal calendar, or the periods are undated.

        See Also
        --------
        boki.Result.pl : The profit and loss statement.
        boki.Result.bs : The balance sheet.

        Examples
        --------
        The two methods reach the same net change in cash:

        >>> import boki as b
        >>> m = b.Model("Cafe", start="2027-01", periods=2, step=b.month)
        >>> co = m.entity("Cafe", standard=b.IFRS)
        >>> co.bs.opening(cash=1000, retained_earnings=1000)
        >>> sales = co.pl.revenue("Sales", 100)
        >>> rent = co.pl.sga("Rent", 40)
        >>> r = m.render()
        >>> r.cf(co).row("Net change in cash")
        [60.0, 60.0]
        >>> r.cf(co).row("Net change in cash") == r.cf(co, method="indirect").row("Net change in cash")
        True
        """  # noqa: DOC105, DOC107, DOC203, DOC502
        from .statements import Table, cf_indirect_rows, cf_rows, group
        build = {"direct": cf_rows, "indirect": cf_indirect_rows}[method]
        entity = getattr(entity, "books", entity)
        cols, rows = group(self, build(self, entity), by, entity)
        return Table(f"CF {entity.name}", cols, rows)
