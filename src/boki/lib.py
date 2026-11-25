"""Standard library: shapes over time and valuation functions, built on series nodes."""
from __future__ import annotations

import math
from datetime import date
from typing import TYPE_CHECKING

from .series import At, Op, Reduce, Series, _site, _unify, lift
from .shapes import Kernel
from .units import _DIMENSIONLESS, Quantity, UnitError, _describe

if TYPE_CHECKING:
    from .ledger import NOL


def _dimensionless(node: Series, what: str) -> None:
    if node.unit not in (None, _DIMENSIONLESS):
        raise UnitError(f"{what} must be dimensionless (a per-period rate), got {_describe(node.unit)}; "
                        "convert an annual rate with rate * m.period_length")


class _Compound(Series):
    def __init__(self, x0, rate):
        self.x0, self.rate = lift(x0), lift(rate)
        self.name = "compound"
        _dimensionless(self.rate, "compound's rate")
        self.unit = self.x0.unit

    def _eval(self, r, t):
        if t == 0:
            return r.value(self.x0, None if self.x0.scalar else 0)
        prev = r.value(self, t - 1)
        g = r.value(self.rate, None if self.rate.scalar else t)
        return None if prev is None or g is None else prev * (1 + g)


def compound(x0, rate) -> Series:
    """Return a series that starts at ``x0`` and grows by ``rate`` in each period after the first.

    Parameters
    ----------
    x0 : scalar, Quantity, or Series
        Value in the first period, in any unit. The result has the unit of ``x0``. A `Series` is read in the first
        period only.
    rate : scalar or Series
        Growth rate, dimensionless and per period: ``0.05`` is 5% per period, whether the period is a month or a
        year. A `Series` gives a rate for each period. The rate of the first period is not used.

    Returns
    -------
    Series
        ``x0`` in the first period, then the previous value times ``1 + rate`` in each later period.

    Raises
    ------
    UnitError
        At construction, if ``rate`` has units, such as a rate per time like ``0.05 / b.year``. Convert it with
        ``rate * m.period_length``.

    See Also
    --------
    boki.lib.index : An index that starts at 1 and can grow only in some periods.
    boki.lib.discount : The cumulative discount factor.

    Notes
    -----
    The first period does not grow. For a series that already grows in the first period, write
    ``compound(1 + rate[0], rate)``. ``rate * m.period_length`` converts a rate per time into a rate per period
    by simple (non-compounding) scaling: ``0.12 / b.year`` is 1% in a monthly period.

    Examples
    --------
    A price of 100 that grows 10% in the second year and 20% in the third:

    >>> import boki as b
    >>> m = b.Model("Price", start="2027-01", periods=3, step=b.year)
    >>> growth = m.series("Growth", data={1: 0.1, 2: 0.2})
    >>> price = b.lib.compound(100, growth)
    >>> r = m.render()
    >>> [round(v, 2) for v in r[price]]
    [100, 110.0, 132.0]

    A rate per year converted for monthly periods grows 1% per month:

    >>> m = b.Model("Monthly price", start="2027-01", periods=3, step=b.month)
    >>> price = b.lib.compound(100, 0.12 / b.year * m.period_length)
    >>> r = m.render()
    >>> [round(v, 2) for v in r[price]]
    [100, 101.0, 102.01]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return _Compound(x0, rate)


class _Index(Series):
    def __init__(self, rate, when, start):
        self.site = _site()
        self.rate, self.when, self.start = lift(rate), None if when is None else lift(when), start
        self.name = "index"
        self.unit = _DIMENSIONLESS

    def _eval(self, r, t):
        if t == 0:
            return 1.0
        on = True
        if self.when is not None:
            on = r.value(self.when, None if self.when.scalar else t)
        if self.start is not None:
            on = on and r.model.timeline.periods[t].start >= _as_date(self.start)
        g = r.value(self.rate, None if self.rate.scalar else t)
        if self.rate.unit not in (None, _DIMENSIONLESS):
            # A rate per time, stored per month: compound the annual rate over the period's length.
            g = (1 + g * 12) ** (r.model.timeline.periods[t].months / 12) - 1
        return r.value(self, t - 1) * (1 + g * bool(on))


def index(rate, when=None, start=None) -> Series:
    """Return an index that is 1 in the first period and compounds by ``rate`` in the periods where it applies.

    Use it for a price or cost index that starts at 1 and grows only from a date or only while a condition holds.

    Parameters
    ----------
    rate : scalar, Quantity, or Series
        Growth rate. A plain number or a dimensionless series is per period: ``0.01`` is 1% in each period, whether
        a month or a year. A quantity or series per time, such as ``0.12 / b.year``, is an annual rate compounded
        over the length of each period, so it gives the same annual growth in a monthly and an annual model.
    when : Series, optional
        A condition. The index grows only in periods where it holds. If it is `None`, the index grows in every
        period. The default is `None`.
    start : date or str, optional
        The index grows only in periods that start on or after this date, such as ``"2028"``, ``"2028-04"``, or a
        `datetime.date`. It needs dated periods. If it is `None`, there is no start date. The default is `None`.

    Returns
    -------
    Series
        A dimensionless series: 1 in the first period, then the previous value times ``1 + growth`` in each period
        where the index grows, and unchanged in other periods.

    See Also
    --------
    boki.lib.compound : A series that starts at a value you choose and grows every period.

    Notes
    -----
    The first period is always 1, whatever ``when`` and ``start`` say. If both ``when`` and ``start`` are given, the
    index grows only where both hold. A rate per time is compounded as ``(1 + rate) ** (months / 12) - 1`` for a
    period of that many months.

    Examples
    --------
    A cost index with 12% a year, read after one year in a monthly model, and with 1% per period for comparison:

    >>> import boki as b
    >>> m = b.Model("Index", start="2027-01", periods=13, step=b.month)
    >>> r = m.render()
    >>> round(r.value(b.lib.index(0.12 / b.year), "2028-01"), 4)
    1.12
    >>> round(r.value(b.lib.index(0.01), "2028-01"), 4)
    1.1268

    Growth that starts in 2029 in an annual model:

    >>> m = b.Model("Escalation", start="2027-01", periods=5, step=b.year)
    >>> index = b.lib.index(0.1, start="2029")
    >>> r = m.render()
    >>> [round(v, 4) for v in r[index]]
    [1.0, 1.0, 1.1, 1.21, 1.331]
    """  # noqa: DOC105, DOC106, DOC107
    return _Index(rate, when, start)


def _as_date(x) -> date:
    from .model import parse_date
    return parse_date(x)


class _Fade(Series):
    def __init__(self, a, b, t0, t1):
        self.site = _site()
        self.a, self.b, self.t0, self.t1 = lift(a), lift(b), t0, t1
        self.name = "fade"
        self.unit = _unify([self.a, self.b], "fade between")

    def _eval(self, r, t):
        t0, t1 = r.period_index(self.t0), r.period_index(self.t1)
        a = r.value(self.a, None if self.a.scalar else t)
        b = r.value(self.b, None if self.b.scalar else t)
        if t <= t0:
            return a
        if t >= t1:
            return b
        return a + (b - a) * (t - t0) / (t1 - t0)


def fade(a, b, over: tuple) -> Series:
    """Return a series that is ``a`` until a period, ``b`` from a later period, and a straight line in between.

    Parameters
    ----------
    a : scalar, Quantity, or Series
        Value up to and including the first period of ``over``. A `Series` is read in each period.
    b : scalar, Quantity, or Series
        Value from the second period of ``over`` on, in the unit of ``a``.
    over : tuple
        Two periods ``(first, last)``, each a zero-based period index, a date, or a period label such as ``"2028"``.
        Between them, the value moves linearly with the period count.

    Returns
    -------
    Series
        ``a`` in periods up to ``first``, ``b`` from ``last``, and
        ``a + (b - a) * (t - first) / (last - first)`` in between, where ``t`` is the period index. The series has
        the common unit of ``a`` and ``b``.

    Raises
    ------
    UnitError
        At construction, if ``a`` and ``b`` have incompatible units.
    IndexError
        At evaluation, if a period of ``over`` is outside the model's timeline.

    See Also
    --------
    boki.step : Hold a value until the next key.

    Examples
    --------
    A margin that falls from 1 to 0 over the first three periods:

    >>> import boki as b
    >>> m = b.Model("Fade", start="2027-01", periods=5, step=b.year)
    >>> margin = b.lib.fade(1.0, 0.0, over=(0, 3))
    >>> r = m.render()
    >>> [round(v, 3) for v in r[margin]]
    [1.0, 0.667, 0.333, 0.0, 0.0]

    Period labels give the ends of the transition:

    >>> growth = b.lib.fade(10, 20, over=("2028", "2030"))
    >>> r[growth]
    [10, 10, 15.0, 20, 20]
    """  # noqa: DOC105, DOC107, DOC502
    return _Fade(a, b, *over)


class _Discount(Series):
    def __init__(self, rate):
        self.rate = lift(rate)
        self.name = "discount"
        _dimensionless(self.rate, "discount's rate")
        self.unit = _DIMENSIONLESS

    def _eval(self, r, t):
        prev = 1.0 if t == 0 else r.value(self, t - 1)
        return prev / (1 + r.value(self.rate, None if self.rate.scalar else t))


def discount(rate) -> Series:
    """Return the cumulative discount factor at the end of each period.

    Parameters
    ----------
    rate : scalar or Series
        Discount rate, dimensionless and per period: ``0.1`` is 10% per period, whether the period is a month or a
        year. A `Series` gives a rate for each period.

    Returns
    -------
    Series
        A dimensionless series: the product of ``1 / (1 + rate)`` over the periods up to and including each period.
        The first period is ``1 / (1 + rate)``, because flows occur at the end of each period.

    Raises
    ------
    UnitError
        At construction, if ``rate`` has units, such as a rate per time like ``0.1 / b.year``. Convert it with
        ``rate * m.period_length``.

    See Also
    --------
    boki.lib.npv : The present value of cash flows.

    Notes
    -----
    Calling ``discount`` again with the same rate series returns the same node, so `npv` at that rate and the
    plan's own discount row share one row in Excel. See the `time points and discounting conventions
    <https://github.com/combinatrix-ai/boki/blob/master/docs/conventions.md#time-points-and-discounting>`_.

    Examples
    --------
    Factors for a 10% annual rate:

    >>> import boki as b
    >>> m = b.Model("Discount", start="2027-01", periods=3, step=b.year)
    >>> factor = b.lib.discount(0.1)
    >>> r = m.render()
    >>> [round(v, 4) for v in r[factor]]
    [0.9091, 0.8264, 0.7513]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    rate = lift(rate)
    if rate.scalar:
        return _Discount(rate)
    if getattr(rate, "_discount", None) is None:
        rate._discount = _Discount(rate)
    return rate._discount


def gordon(cash_flow, rate, growth) -> Series:
    """Return the value of a perpetuity whose cash flow grows at a constant rate: ``cash_flow / (rate - growth)``.

    Parameters
    ----------
    cash_flow : scalar, Quantity, or Series
        The first cash flow of the perpetuity, such as the terminal year's flow, in any unit. The result has its
        unit.
    rate : scalar or Series
        Discount rate, dimensionless and per period. A rate per time such as ``0.1 / b.year`` is not rejected here,
        so convert it with ``rate * m.period_length`` first.
    growth : scalar or Series
        Growth rate of the cash flow, dimensionless and on the same per-period basis as ``rate``.

    Returns
    -------
    Series
        The perpetuity value, a series that has the unit of ``cash_flow`` and is scalar when all arguments are.

    See Also
    --------
    boki.lib.npv : The present value of finite cash flows.

    Notes
    -----
    The formula needs ``rate`` above ``growth``. If they are equal the division fails at evaluation, and a
    ``growth`` above ``rate`` gives a negative value.

    Examples
    --------
    A terminal flow of 100 growing 2% a year at a 10% discount rate:

    >>> import boki as b
    >>> m = b.Model("Terminal value", start="2027-01", periods=3, step=b.year)
    >>> value = b.lib.gordon(100, 0.10, 0.02)
    >>> r = m.render()
    >>> round(r[value], 2)
    1250.0
    """  # noqa: DOC105, DOC106, DOC107
    return lift(cash_flow) / (lift(rate) - lift(growth))


def npv(cash_flows, rate, at: int = -1, initial=None) -> Series:
    """Return the present value of cash flows at a per-period discount rate.

    Each period's flow arrives at the end of the period, as in `discount` and Excel's ``NPV``. The value is as of
    the end of period ``at``; the default, ``-1``, is the start of the model.

    Parameters
    ----------
    cash_flows : Series, Quantity, or scalar
        Cash flow in each period, in any unit. The result has its unit. A scalar counts as the same flow in every
        period.
    rate : scalar or Series
        Discount rate, dimensionless and per period: ``0.01`` is 1% per period, whether the period is a month or a
        year. A `Series` is a rate that changes by period (for example a WACC set year by year): each flow is
        discounted by the product of ``1 + rate`` over the periods up to and including its own, as `discount` does.
    at : int, optional
        Period whose end the value is taken at. ``-1`` is the start of the model, ``0`` the end of the first
        period. With a constant rate it can be any period, including one after the end of the model; with a
        `Series` rate that varies by period it must be ``-1`` or a period of the model. The default is ``-1``.
    initial : scalar, Quantity, or Series, optional
        A flow at the start of the model, such as an investment at closing, valued as of that date. If it is `None`,
        there is none. The default is `None`.

    Returns
    -------
    Series
        The value, a scalar series (the same in every period) with the unit of ``cash_flows``.

    Raises
    ------
    UnitError
        At construction, if ``rate`` has units, such as a rate per time like ``0.1 / b.year``. Convert it with
        ``rate * m.period_length``.
    ValueError
        At construction, if ``rate`` is a `Series` that varies by period and ``at`` is below ``-1``.
    IndexError
        At evaluation, if ``rate`` is a `Series` that varies by period and ``at`` is after the last period.

    See Also
    --------
    boki.lib.discount : The cumulative discount factor.
    boki.lib.irr : The rate at which the present value is zero.
    boki.lib.xnpv : The present value of flows on given dates.

    Notes
    -----
    Excel gets ``NPV()`` for a constant rate, and ``SUMPRODUCT`` of the flows and the ``discount(rate)`` row for a
    series. See the `time points and discounting conventions
    <https://github.com/combinatrix-ai/boki/blob/master/docs/conventions.md#time-points-and-discounting>`_.

    Examples
    --------
    Flows of 10, 10, and 110 at 10% per year, valued at the start of the model, at the end of the first year, and
    with an investment of 90 at the start:

    >>> import boki as b
    >>> m = b.Model("Valuation", start="2027-01", periods=3, step=b.year)
    >>> flows = m.series("Flows", data={0: 10, 1: 10, 2: 110})
    >>> r = m.render()
    >>> round(r[b.lib.npv(flows, 0.1)], 2)
    100.0
    >>> round(r[b.lib.npv(flows, 0.1, at=0)], 2)
    110.0
    >>> round(r[b.lib.npv(flows, 0.1, initial=-90)], 2)
    10.0

    In a monthly model the rate is per month, so a 12% annual rate is written as 1% per period:

    >>> m = b.Model("Rent", start="2027-01", periods=3, step=b.month)
    >>> rent = m.series("Rent", data={0: 100, 1: 100, 2: 100})
    >>> r = m.render()
    >>> round(r[b.lib.npv(rent, 0.12 / 12)], 2)
    294.1
    """  # noqa: DOC105, DOC107, DOC502
    rate = lift(rate)
    _dimensionless(rate, "npv's rate")
    first = lift(initial if initial is not None else 0)
    unit = lift(cash_flows).unit
    if not rate.scalar:
        return _npv_by_period(cash_flows, rate, at, first, unit)

    def value(cf, rr, c0):
        r = rr[0]
        return c0[0] * (1 + r) ** (at + 1) + sum((c or 0) / (1 + r) ** (t - at) for t, c in enumerate(cf))
    return Reduce(value, cash_flows, rate, first, unit=unit,
                  excel=lambda cf, r, c0: f"({c0}+NPV({r},{cf}))*(1+{r})^({at}+1)", excel_first=(1, 2))


def _npv_by_period(cash_flows, rate, at, first, unit) -> Series:
    """npv at a rate per period: (initial + Σ flow × discount factor) / the discount factor at the end of `at`."""
    if at < -1:
        raise ValueError(f"npv(at={at}): with a rate per period, at= is a period of the model (-1 for its start)")
    factor = discount(rate)

    def total(cf, d, c0):
        return c0[0] + sum((c or 0) * k for c, k in zip(cf, d))
    if at == -1:
        return Reduce(total, cash_flows, factor, first, unit=unit,
                      excel=lambda cf, d, c0: f"(SUMPRODUCT({cf},{d})+{c0})", excel_first=(2,))
    return Reduce(lambda cf, d, c0, end: total(cf, d, c0) / end[0], cash_flows, factor, first, At(factor, at),
                  unit=unit, excel=lambda cf, d, c0, end: f"(SUMPRODUCT({cf},{d})+{c0})/{end}", excel_first=(2, 3))


class NoRateOfReturn(ArithmeticError):
    """Error raised when cash flows have no internal rate of return.

    `irr` and `xirr` raise it at evaluation when the flows have no sign change within the search range, from -99% to
    1000% per period, and no ``default=`` was given. It is an `ArithmeticError`.

    See Also
    --------
    boki.lib.irr : The internal rate of return per period.
    boki.lib.xirr : The annual internal rate of return for flows on given dates.

    Notes
    -----
    Flows that are all positive or all negative have no rate of return. ``irr(..., default=0)`` returns the default
    instead of raising, which is how a running IRR starts before the first sign change.

    Examples
    --------
    Flows without an outflow have no rate of return:

    >>> import boki as b
    >>> m = b.Model("Receipts", start="2027-01", periods=2, step=b.year)
    >>> flows = m.series("Flows", data={0: 10, 1: 10})
    >>> r = m.render()
    >>> try:
    ...     r[b.lib.irr(flows)]
    ... except b.lib.NoRateOfReturn as error:
    ...     print(error)
    no sign change: the cash flows have no internal rate of return in range
    >>> r[b.lib.irr(flows, default=0)]
    0
    """


def _finite(f):
    """f, or None where it overflows: near a rate of -99% a long series discounts by 100^t."""
    def g(x):
        try:
            v = f(x)
        except (OverflowError, ZeroDivisionError):
            return None
        return v if math.isfinite(v) else None
    return g


def _bisect(f, lo=-0.99, hi=10.0, iters=200, guess=0.10):
    """A root of f in [lo, hi]. With several roots (cash flows that change sign more than once, such as a
    decommissioning cost at the end), a root where the value falls as the rate rises (invest first, then
    earn: the usual IRR), and among those the one nearest `guess`, as Excel's IRR does from its default guess."""
    f = _finite(f)
    grid = [lo + (hi - lo) * (k / 2_000) ** 3 for k in range(2_001)]       # dense near lo, where returns usually are
    values = [f(x) for x in grid]
    brackets = [(a, b) for a, b, fa, fb in zip(grid, grid[1:], values, values[1:])
                if fa is not None and fb is not None and (fa == 0 or fa * fb < 0)]
    if not brackets:
        raise NoRateOfReturn("no sign change: the cash flows have no internal rate of return in range")
    falling = [(a, b) for a, b in brackets if f(a) > 0 > f(b)]
    brackets = falling or brackets
    lo, hi = min(brackets, key=lambda ab: abs((ab[0] + ab[1]) / 2 - guess))
    flo = f(lo)
    if flo == 0:
        return lo
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def _root_or(default, solve):
    """solve(), or `default` when the cash flows have no rate of return (Excel's IFERROR(IRR(...), default))."""
    try:
        return solve()
    except NoRateOfReturn:
        if default is None:
            raise
        return default


def _check_default(default, what: str):
    if default is not None and (isinstance(default, bool) or not isinstance(default, (int, float))):
        raise TypeError(f"{what}: default= takes a number (the value where no rate of return exists)")


def _excel_default(formula: str, default) -> str:
    return formula if default is None else f"IFERROR({formula},{float(default)!r})"


class _RunningIrr(Series):
    """The IRR of the cash flows up to and including each period. It reads only the periods so far, so a later
    flow can depend on it (a partnership flip once the investor's IRR to date reaches its target)."""

    def __init__(self, cash_flows, default):
        self.src = lift(cash_flows)
        if self.src.scalar:
            raise TypeError("irr(running=True) needs a series of cash flows")
        self.default, self.name, self.unit = default, "irr to date", _DIMENSIONLESS

    def _eval(self, r, t):
        cf = [r.value(self.src, s) for s in range(t + 1)]
        return _root_or(self.default, lambda: _bisect(lambda x: sum((c or 0) / (1 + x) ** k for k, c in enumerate(cf))))


def irr(cash_flows, initial=None, *, running: bool = False, default=None) -> Series:
    """Return the internal rate of return per period of a series of cash flows.

    Parameters
    ----------
    cash_flows : Series
        Cash flow in each period, arriving at the end of the period, in any unit. The flows must change sign.
    initial : scalar, Quantity, or Series, optional
        A flow one period before the first, such as the investment at closing when the model starts with the first
        operating year. If it is `None`, there is none. It cannot be combined with ``running=True``. The default is
        `None`.
    running : bool, optional
        If `True`, return a series of the rate of return of the flows up to and including each period, as Excel's
        ``IRR($C5:C5)`` filled right. It reads only the periods so far, so a later flow can depend on it (a
        partnership flip once the investor's rate to date reaches its target). The default is `False`.
    default : int or float, optional
        The value where the flows have no rate of return, as ``IFERROR(IRR(...), 0)`` does. If it is `None`, that is
        an error. The default is `None`.

    Returns
    -------
    Series
        A dimensionless rate per period. A scalar series (the same in every period) when ``running`` is `False`, and
        one value for each period when it is `True`.

    Raises
    ------
    TypeError
        At construction, if ``default`` is not a number (a `bool` is not accepted), if ``running`` is `True` and
        ``initial`` is given, or if ``running`` is `True` and ``cash_flows`` is a scalar.
    NoRateOfReturn
        At evaluation, if the flows have no sign change within -99% to 1000% per period and ``default`` is `None`.

    See Also
    --------
    boki.lib.xirr : The annual rate for flows on given dates.
    boki.lib.npv : The present value at a given rate.
    boki.lib.NoRateOfReturn : The error for flows without a rate of return.

    Notes
    -----
    The rate is per period, so monthly flows give a monthly rate: annualize it as ``(1 + irr) ** 12 - 1``. If the
    flows change sign more than once, such as a decommissioning cost at the end, the rate chosen is a root where the
    value falls as the rate rises (invest first, then earn, the usual IRR) and, among those, the one nearest 10%, as
    Excel's ``IRR`` does from its default guess. Only ``irr`` and ``xirr`` take ``default=``; guard other divisions
    with ``x.where(denominator != 0, 0)``. See the `time points and discounting conventions
    <https://github.com/combinatrix-ai/boki/blob/master/docs/conventions.md#time-points-and-discounting>`_.

    Examples
    --------
    An investment of 100 followed by flows of 40, 50, and 60:

    >>> import boki as b
    >>> m = b.Model("Project", start="2027-01", periods=4, step=b.year)
    >>> flows = m.series("Flows", data={0: -100, 1: 40, 2: 50, 3: 60})
    >>> r = m.render()
    >>> round(r[b.lib.irr(flows)], 4)
    0.2165

    The same project with the investment passed as ``initial``, one period before the first flow:

    >>> m = b.Model("Operating years", start="2027-01", periods=3, step=b.year)
    >>> flows = m.series("Flows", data={0: 10, 1: 10, 2: 110})
    >>> r = m.render()
    >>> round(r[b.lib.irr(flows, initial=-100)], 4)
    0.1

    The rate is per period: 100 invested grows to 112.68 in twelve months, a 1% monthly rate and 12.68% a year:

    >>> m = b.Model("Monthly", start="2027-01", periods=13, step=b.month)
    >>> flows = m.series("Flows", data={0: -100, 12: 112.6825})
    >>> r = m.render()
    >>> monthly = r[b.lib.irr(flows)]
    >>> round(monthly, 4)
    0.01
    >>> round((1 + monthly) ** 12 - 1, 4)
    0.1268

    The rate to date, with ``default=0`` before the flows change sign:

    >>> m = b.Model("To date", start="2027-01", periods=4, step=b.year)
    >>> flows = m.series("Flows", data={0: -100, 1: 40, 2: 50, 3: 60})
    >>> r = m.render()
    >>> [round(v, 4) for v in r[b.lib.irr(flows, running=True, default=0.0)]]
    [0.0, -0.6, -0.0652, 0.2165]
    """  # noqa: DOC105, DOC107, DOC503
    _check_default(default, "irr")
    if running:
        if initial is not None:
            raise TypeError("irr(running=True) does not take initial=; put that flow in the first period")
        return _RunningIrr(cash_flows, default)
    if initial is None:
        return Reduce(lambda cf: _root_or(default, lambda: _bisect(
                          lambda x: sum((c or 0) / (1 + x) ** t for t, c in enumerate(cf)))),
                      cash_flows, unit=_DIMENSIONLESS, excel_guess=True,
                      excel=lambda cf, guess: _excel_default(f"IRR({cf},{guess})", default))
    return Reduce(lambda cf, c0: _root_or(default, lambda: _bisect(
                      lambda x: c0[0] + sum((c or 0) / (1 + x) ** (t + 1) for t, c in enumerate(cf)))),
                  cash_flows, lift(initial), unit=_DIMENSIONLESS)


def xirr(cash_flows, dates, *, default=None) -> Series:
    """Return the annual internal rate of return of cash flows on given dates, on an actual/365 basis.

    Parameters
    ----------
    cash_flows : Series
        Cash flow in each period, in any unit. The flows must change sign.
    dates : Series
        The date of each period's flow, such as ``m.date`` or ``m.period_end``. It must have a date in every
        period; the first date is the date the rate is measured from.
    default : int or float, optional
        The value where the flows have no rate of return, as for `irr`. If it is `None`, that is an error. The
        default is `None`.

    Returns
    -------
    Series
        A dimensionless annual rate, a scalar series (the same in every period).

    Raises
    ------
    TypeError
        At construction, if ``default`` is not a number (a `bool` is not accepted).
    NoRateOfReturn
        At evaluation, if the flows have no sign change within -99% to 1000% and ``default`` is `None`.

    See Also
    --------
    boki.lib.irr : The rate per period, without dates.
    boki.lib.xnpv : The present value of flows on given dates.
    boki.lib.NoRateOfReturn : The error for flows without a rate of return.

    Notes
    -----
    Time between flows is the number of days divided by 365, like Excel's ``XIRR``, so the rate is annual whatever
    the period length. The search range is -99% to 1000% a year.

    Examples
    --------
    Annual flows on the first day of each year:

    >>> import boki as b
    >>> m = b.Model("Project", start="2027-01", periods=4, step=b.year)
    >>> flows = m.series("Flows", data={0: -100, 1: 40, 2: 50, 3: 60})
    >>> r = m.render()
    >>> round(r[b.lib.xirr(flows, m.date)], 4)
    0.2163
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    _check_default(default, "xirr")

    def f(cf, ds):
        return _root_or(default, lambda: _bisect(lambda x: _xnpv(x, cf, ds)))
    return Reduce(f, cash_flows, dates, unit=_DIMENSIONLESS, excel_guess=True,
                  excel=lambda cf, ds, guess: _excel_default(f"XIRR({cf},{ds},{guess})", default))


def _xnpv(rate, cf, ds):
    d0 = ds[0]
    return sum((c or 0) / (1 + rate) ** ((d - d0).days / 365) for c, d in zip(cf, ds))


def xnpv(cash_flows, rate, dates) -> Series:
    """Return the value at the first date of cash flows on given dates at an annual rate, on an actual/365 basis.

    Parameters
    ----------
    cash_flows : Series
        Cash flow in each period, in any unit. The result has its unit.
    rate : scalar or Series
        Annual discount rate, dimensionless: ``0.1`` is 10% a year. The dates set the timing, so it is a rate for a
        year whatever the period length, and a rate per time such as ``0.1 / b.year`` is rejected.
    dates : Series
        The date of each period's flow, such as ``m.date``. The first date is the date the value is taken at.

    Returns
    -------
    Series
        The value, a scalar series (the same in every period) with the unit of ``cash_flows``.

    Raises
    ------
    UnitError
        At construction, if ``rate`` has units.

    See Also
    --------
    boki.lib.npv : The present value of flows by period.
    boki.lib.xirr : The annual rate at which the value is zero.

    Notes
    -----
    Each flow is discounted by ``(1 + rate) ** (days / 365)`` from the first date, like Excel's ``XNPV``. Unlike
    `npv`, the first flow is not discounted, because it is on the first date.

    Examples
    --------
    Annual flows on the first day of each year, discounted at 10% a year to the first date:

    >>> import boki as b
    >>> m = b.Model("Project", start="2027-01", periods=4, step=b.year)
    >>> flows = m.series("Flows", data={0: -100, 1: 40, 2: 50, 3: 60})
    >>> r = m.render()
    >>> round(r[b.lib.xnpv(flows, 0.1, m.date)], 2)
    22.74
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    rate = lift(rate)
    _dimensionless(rate, "xnpv's rate")
    return Reduce(lambda cf, rr, ds: _xnpv(rr[0], cf, ds), cash_flows, rate, dates, unit=lift(cash_flows).unit,
                  excel=lambda cf, r, ds: f"XNPV({r},{cf},{ds})", excel_first=(1,))


def _pmt(rate, n, pv):
    if rate == 0:
        return pv / n
    return pv * rate / (1 - (1 + rate) ** -n)


def pmt(rate, n, pv) -> Series | Quantity | float:
    """Return the level payment per period that repays ``pv`` over ``n`` periods at a per-period rate.

    The payment is made at the end of each period (an ordinary annuity). It is positive for a positive ``pv``;
    Excel's ``PMT`` has the opposite sign.

    Parameters
    ----------
    rate : scalar or Series
        Interest rate, dimensionless and per period: ``0.01`` is 1% per period, whether the period is a month or a
        year. Divide an annual rate by 12 for monthly periods. A rate per time such as ``0.1 / b.year`` raises
        `UnitError` when it is a scalar quantity; a series with units is not checked.
    n : int or Series
        Number of periods over which the amount is repaid. It must not be zero.
    pv : scalar, Quantity, or Series
        Amount to repay, in any unit. The result has its unit.

    Returns
    -------
    Series | Quantity | float
        The payment per period: a `Series` if any argument is a series (with the unit of ``pv``), a `Quantity` if
        ``pv`` is a quantity, and otherwise a number.

    Raises
    ------
    UnitError
        At construction, if ``rate`` is a scalar quantity with units.

    See Also
    --------
    boki.lib.npv : The present value of a series of payments.

    Notes
    -----
    With a rate of 0 the payment is ``pv / n``. Otherwise it is ``pv * rate / (1 - (1 + rate) ** -n)``.

    Examples
    --------
    Repay 1000 over twelve months at 12% a year, which is 1% a month:

    >>> import boki as b
    >>> payment = b.lib.pmt(0.12 / 12, 12, 1000)
    >>> round(payment, 2)
    88.85

    With a series for the amount the payment is a series:

    >>> m = b.Model("Loan", start="2027-01", periods=12, step=b.month)
    >>> loan = m.series("Loan", 1000)
    >>> r = m.render()
    >>> round(r[b.lib.pmt(0.01, 12, loan)], 2)
    88.85
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    if any(isinstance(x, Series) for x in (rate, n, pv)):
        return Op(_pmt, rate, n, pv, unit=lift(pv).unit)
    return _pmt(rate, n, pv)


def levelized(cost, quantity, rate) -> Series:
    """Return the levelized cost: the present value of costs divided by the present value of quantities.

    Use it for the levelized cost of energy (LCOE) and similar unit costs.

    Parameters
    ----------
    cost : Series
        Cost in each period, in a currency unit.
    quantity : Series
        Quantity delivered in each period, such as energy produced.
    rate : scalar or Series
        Discount rate, dimensionless and per period, as for `npv`.

    Returns
    -------
    Series
        A scalar series (the same in every period): ``npv(cost, rate) / npv(quantity, rate)``, in the unit of
        ``cost`` per unit of ``quantity``.

    Raises
    ------
    UnitError
        At construction, if ``rate`` has units, such as a rate per time like ``0.1 / b.year``.

    See Also
    --------
    boki.lib.npv : The present value used for both sides.

    Notes
    -----
    Quantities are held in base units, so a quantity in MWh is stored in Wh and the result is in currency per Wh;
    multiply by 1,000,000 for currency per MWh.

    Examples
    --------
    A cost of 100 a year for 50 units a year, at 8%:

    >>> import boki as b
    >>> m = b.Model("Unit cost", start="2027-01", periods=3, step=b.year)
    >>> cost = m.series("Cost", data={0: 100, 1: 100, 2: 100})
    >>> units = m.series("Units", data={0: 50, 1: 50, 2: 50})
    >>> r = m.render()
    >>> round(r[b.lib.levelized(cost, units, 0.08)], 4)
    2.0
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return npv(cost, rate) / npv(quantity, rate)


class _Lookup(Series):
    """Excel writes the table as two rows on the Inputs sheet (keys, values) and the cell as LOOKUP."""

    def __init__(self, x, table: dict):
        self.site = _site()
        self.x = lift(x)
        self.keys = sorted(table)
        self.values = [lift(table[k]) for k in self.keys]
        self.scalar = self.x.scalar
        self.name = "lookup"
        units = {v.unit for v in self.values}
        self.unit = units.pop() if len(units) == 1 else None

    def _eval(self, r, t):
        v = r.value(self.x, None if self.scalar else t)
        found = None
        for k, value in zip(self.keys, self.values):
            if k <= v:
                found = value
        if found is None:
            raise ValueError(f"lookup: {v} is below the first band {self.keys[0]}")
        return r.value(found, None)


def lookup(x, table: dict) -> Series:
    """Return the value for the largest key that is not above ``x``, from a banded table.

    Use it for tax brackets, synthetic ratings, or a rate by calendar year with date keys. It is like Excel's
    approximate ``LOOKUP``.

    Parameters
    ----------
    x : Series, number, or date
        The value to look up, in each period: a number, or a date for date keys. A scalar is looked up once.
    table : dict
        Map the lower bound of each band to its value, a number or `Quantity`. Keys are sorted, so the order does not
        matter. Use a very low key such as ``-1e9`` for a band with no lower bound. A key and ``x`` must be
        comparable: both numbers or both dates.

    Returns
    -------
    Series
        The value of the band that ``x`` falls in, in each period. It has the unit of the table values when they
        all share one unit, and an unknown unit otherwise.

    Raises
    ------
    ValueError
        At evaluation, if ``x`` is below the first key of the table.

    See Also
    --------
    boki.step : Hold a value until the next period key.
    boki.by_year : Select values by model year.

    Notes
    -----
    Excel writes the table as two rows on the Inputs sheet (keys and values) and the cell as ``LOOKUP``. A key is the
    lower bound of its band, so a value equal to a key falls in that key's band.

    Examples
    --------
    A tax rate of 10% below 1000, 20% from 1000, and 30% from 5000:

    >>> import boki as b
    >>> m = b.Model("Brackets", start="2027-01", periods=3, step=b.year)
    >>> income = m.series("Income", data={0: 500, 1: 1500, 2: 6000})
    >>> rate = b.lib.lookup(income, {0: 0.1, 1000: 0.2, 5000: 0.3})
    >>> r = m.render()
    >>> r[rate]
    [0.1, 0.2, 0.3]

    A rate by calendar year, with date keys and the model's dates:

    >>> import datetime
    >>> rate = b.lib.lookup(m.date, {datetime.date(2027, 1, 1): 0.1, datetime.date(2029, 1, 1): 0.2})
    >>> r[rate]
    [0.1, 0.1, 0.2]
    """  # noqa: DOC105, DOC107, DOC502
    return _Lookup(x, table)


def _norm_cdf(x):
    import math
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bs(s, k, t, sigma, r, q, call):
    import math
    d1 = (math.log(s / k) + (r - q + sigma ** 2 / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if call:
        return s * math.exp(-q * t) * _norm_cdf(d1) - k * math.exp(-r * t) * _norm_cdf(d2)
    return k * math.exp(-r * t) * _norm_cdf(-d2) - s * math.exp(-q * t) * _norm_cdf(-d1)


def black_scholes(underlying, strike, years, volatility, rate, yield_=0.0,
                  call: bool = True) -> Series | Quantity | float:
    """Return the Black-Scholes value of a European option.

    Use it for real options such as expanding, delaying, or abandoning a project, or a natural-resource option. The
    value is as of today for an option that expires in ``years`` years.

    Parameters
    ----------
    underlying : scalar, Quantity, or Series
        Current value of the underlying asset, such as the present value of a project's cash flows, in any unit. The
        result has its unit.
    strike : scalar, Quantity, or Series
        Exercise price, in the same unit as ``underlying``.
    years : scalar or Series
        Time to expiry in years, a plain number: ``0.5`` is six months. It must be positive.
    volatility : scalar or Series
        Annualized volatility of the underlying, dimensionless: ``0.2`` is 20% a year. It must be positive.
    rate : scalar or Series
        Continuously compounded risk-free rate per year, dimensionless: ``0.05`` is 5% a year.
    yield_ : scalar or Series, optional
        Continuous payout rate of the underlying per year, dimensionless, such as dividends or the annual cost of
        delay. The default is ``0.0``.
    call : bool, optional
        `True` for a call (the right to buy at ``strike``), `False` for a put. The default is `True`.

    Returns
    -------
    Series | Quantity | float
        The option value: a `Series` if any argument is a series, a `Quantity` if the underlying and strike are
        quantities, and otherwise a number. It has the unit of ``underlying``.

    See Also
    --------
    boki.lib.npv : The present value that often serves as the underlying.

    Notes
    -----
    ``years``, ``volatility``, ``rate``, and ``yield_`` are per year, not per period, so they do not depend on the
    model's period length. A zero ``years`` or ``volatility`` divides by zero, and a non-positive ``underlying`` or
    ``strike`` has no logarithm; both fail at evaluation.

    Examples
    --------
    An at-the-money call and put on an underlying worth 100, one year to expiry, 20% volatility, and a 5% rate:

    >>> import boki as b
    >>> round(b.lib.black_scholes(100, 100, 1, 0.2, 0.05), 4)
    10.4506
    >>> round(b.lib.black_scholes(100, 100, 1, 0.2, 0.05, call=False), 4)
    5.5735

    A continuous payout of 2% lowers the call value:

    >>> round(b.lib.black_scholes(100, 100, 1, 0.2, 0.05, yield_=0.02), 4)
    9.227

    With a series for the underlying, the value is a series:

    >>> m = b.Model("Option", start="2027-01", periods=2, step=b.year)
    >>> worth = m.series("Worth", data={0: 100, 1: 120})
    >>> r = m.render()
    >>> [round(v, 2) for v in r[b.lib.black_scholes(worth, 100, 1, 0.2, 0.05)]]
    [10.45, 26.17]
    """  # noqa: DOC105, DOC107
    args = (underlying, strike, years, volatility, rate, yield_)
    if any(isinstance(x, Series) for x in args):
        return Op(lambda *v: _bs(*v, call), *args, unit=lift(underlying).unit)
    return _bs(*args, call)


def ssfa(kg: float, w: float, attachment: float, detachment: float, p: float = 0.5, floor: float = 0.20) -> float:
    """Return the risk weight of a securitization tranche under the Simplified Supervisory Formula Approach.

    The formula is the US capital rule's SSFA (12 CFR 217.144). The part of the tranche below ``KA`` takes a
    1,250% risk weight, and above it the weight follows ``K_SSFA``.

    Parameters
    ----------
    kg : float
        ``KG`` of the rule: the weighted-average capital requirement of the underlying exposures, as a dimensionless
        fraction of exposure (``0.08`` is 8%).
    w : float
        ``W`` of the rule: the share of the underlying exposures that are delinquent or in default, as a
        dimensionless fraction of exposure.
    attachment : float
        Attachment point ``A`` of the tranche: the share of the pool that absorbs losses first, as a fraction of the
        pool.
    detachment : float
        Detachment point ``D`` of the tranche, as a fraction of the pool. It must be above ``attachment``.
    p : float, optional
        Supervisory parameter: ``0.5`` for a securitization, ``1.5`` for a resecuritization. The default is ``0.5``.
    floor : float, optional
        Lowest risk weight as a ratio (``0.20`` is 20%). The default is ``0.20``.

    Returns
    -------
    float
        The risk weight as a ratio of exposure: ``12.5`` is 1,250% and ``floor`` is the lowest value.

    Notes
    -----
    ``KA = (1 - w) * kg + 0.5 * w``. If ``detachment`` is at or below ``KA`` the whole tranche takes 1,250%. Otherwise
    the capital per unit above ``KA`` is ``K_SSFA = (e^(a*u) - e^(a*l)) / (a * (u - l))`` with ``a = -1 / (p * KA)``,
    ``u = D - KA`` and ``l = max(A - KA, 0)``. The share of the tranche below ``KA`` takes 1,250% and the rest takes
    ``12.5 * K_SSFA``. The result is never below ``floor``. A zero ``KA`` (``kg`` and ``w`` both 0) or a tranche with
    no thickness divides by zero.

    Examples
    --------
    A thin first-loss tranche takes a weight near 1,250%, and a senior tranche takes the 20% floor:

    >>> import boki as b
    >>> round(b.lib.ssfa(0.05, 0.1, 0.0, 0.1), 4)
    12.4682
    >>> round(b.lib.ssfa(0.05, 0.1, 0.3, 1.0), 4)
    0.2
    """  # noqa: DOC105
    import math
    ka = (1 - w) * kg + 0.5 * w
    a = -1 / (p * ka)
    thickness = detachment - attachment
    if detachment <= ka:
        return 12.5
    l, u = max(attachment - ka, 0.0), detachment - ka
    k_ssfa = (math.exp(a * u) - math.exp(a * l)) / (a * (u - l))
    below = max(ka - attachment, 0.0) / thickness
    weight = below * 12.5 + (1 - below) * 12.5 * k_ssfa
    return max(weight, floor)


def capm(beta, rf, erp) -> Series | float:
    """Return the cost of equity from the capital asset pricing model: ``rf + beta * erp``.

    Parameters
    ----------
    beta : scalar or Series
        Equity beta, dimensionless.
    rf : scalar or Series
        Risk-free rate, dimensionless and per period (``0.03`` is 3% a period).
    erp : scalar or Series
        Equity risk premium, dimensionless and on the same per-period basis as ``rf``.

    Returns
    -------
    Series | float
        The cost of equity on the per-period basis of ``rf`` and ``erp``: a `Series` if any argument is a series,
        otherwise a number.

    Raises
    ------
    UnitError
        At construction, if an argument has units, such as a rate per time like ``0.03 / b.year``: the sum with a
        plain number then has incompatible units.

    See Also
    --------
    boki.lib.wacc : The weighted average cost of capital.
    boki.lib.hamada : The levered beta used in the cost of equity.

    Examples
    --------
    A beta of 1.2, a 3% risk-free rate, and a 5% equity risk premium:

    >>> import boki as b
    >>> round(b.lib.capm(1.2, 0.03, 0.05), 4)
    0.09
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return rf + beta * erp


def hamada(unlevered, de, tax) -> Series | float:
    """Return the levered equity beta from an unlevered beta and a debt-to-equity ratio, by the Hamada equation.

    The levered beta is ``unlevered * (1 + (1 - tax) * de)``.

    Parameters
    ----------
    unlevered : scalar or Series
        Unlevered (asset) beta, dimensionless.
    de : scalar or Series
        Debt-to-equity ratio at market values, dimensionless (``0.5`` is 50 of debt per 100 of equity).
    tax : scalar or Series
        Tax rate on the interest shield, a dimensionless fraction (``0.25`` is 25%).

    Returns
    -------
    Series | float
        The levered beta: a `Series` if any argument is a series, otherwise a number.

    Raises
    ------
    UnitError
        At construction, if ``tax`` or ``de`` has units, because the sum with a plain number then has incompatible
        units.

    See Also
    --------
    boki.lib.capm : The cost of equity from a beta.
    boki.lib.wacc : The weighted average cost of capital.

    Examples
    --------
    An unlevered beta of 1.0 with 50% debt to equity and a 25% tax rate:

    >>> import boki as b
    >>> round(b.lib.hamada(1.0, 0.5, 0.25), 4)
    1.375
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return unlevered * (1 + (1 - tax) * de)


def wacc(cost_of_equity, cost_of_debt, debt_ratio, tax) -> Series | float:
    """Return the weighted average cost of capital with an after-tax cost of debt.

    The result is ``cost_of_equity * (1 - debt_ratio) + cost_of_debt * (1 - tax) * debt_ratio``.

    Parameters
    ----------
    cost_of_equity : scalar or Series
        Cost of equity, dimensionless and per period (``0.1`` is 10% a period), such as the result of `capm`.
    cost_of_debt : scalar or Series
        Pre-tax cost of debt, dimensionless and on the same per-period basis as ``cost_of_equity``.
    debt_ratio : scalar or Series
        Debt as a dimensionless share of total capital, debt over debt plus equity (``0.4`` is 40%).
    tax : scalar or Series
        Tax rate on the interest shield, a dimensionless fraction (``0.25`` is 25%).

    Returns
    -------
    Series | float
        The cost of capital on the per-period basis of the two costs: a `Series` if any argument is a series,
        otherwise a number.

    Raises
    ------
    UnitError
        At construction, if an argument has units, such as a rate per time like ``0.04 / b.year``: the sum with a
        plain number then has incompatible units.

    See Also
    --------
    boki.lib.capm : The cost of equity.
    boki.lib.npv : Discount cash flows at the result.

    Examples
    --------
    10% cost of equity, 4% cost of debt, 40% debt, and a 25% tax rate:

    >>> import boki as b
    >>> round(b.lib.wacc(0.1, 0.04, 0.4, 0.25), 4)
    0.072
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return cost_of_equity * (1 - debt_ratio) + cost_of_debt * (1 - tax) * debt_ratio


# IRS Publication 946, Table A-1: GDS, half-year convention (200% declining balance for 3 to 10
# years, 150% for 15 and 20), switching to straight line.
_MACRS = {
    3: (0.3333, 0.4445, 0.1481, 0.0741),
    5: (0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576),
    7: (0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446),
    10: (0.10, 0.18, 0.144, 0.1152, 0.0922, 0.0737, 0.0655, 0.0655, 0.0656, 0.0655, 0.0328),
    15: (0.05, 0.095, 0.0855, 0.077, 0.0693, 0.0623, 0.059, 0.059, 0.0591, 0.059, 0.0591, 0.059, 0.0591,
         0.059, 0.0591, 0.0295),
    20: (0.0375, 0.07219, 0.06677, 0.06177, 0.05713, 0.05285, 0.04888, 0.04522, 0.04462, 0.04461, 0.04462,
         0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.04462, 0.04461, 0.02231),
}


def macrs(years: int) -> Kernel:
    """Return the US MACRS tax depreciation schedule as a kernel over annual periods.

    The schedule is the General Depreciation System with the half-year convention, in IRS Publication 946, Table A-1:
    200% declining balance for 3 to 10 years and 150% for 15 and 20 years, switching to straight line.

    Parameters
    ----------
    years : int
        MACRS recovery period in years. It must be one of 3, 5, 7, 10, 15, or 20.

    Returns
    -------
    Kernel
        A kernel named ``"macrs(<years>)"`` whose weight ``k`` is the share of the cost deducted ``k`` years after
        the year placed in service. The table has ``years + 1`` weights, rounded as published, so they sum to 1
        within rounding.

    Raises
    ------
    ValueError
        At construction, if ``years`` is not 3, 5, 7, 10, 15, or 20.

    See Also
    --------
    boki.lib.straight_line : Straight-line tax depreciation.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    The kernel counts periods, so use it with annual periods: ``capex.spread(macrs(5))`` is the deduction each year.
    In a model with shorter periods each weight would apply to one period, not to one year.

    Examples
    --------
    A five-year asset bought for 100 in the first year:

    >>> import boki as b
    >>> m = b.Model("Tax depreciation", start="2027-01", periods=6, step=b.year)
    >>> capex = m.series("Capex", data={0: 100})
    >>> deduction = capex.spread(b.lib.macrs(5))
    >>> r = m.render()
    >>> [round(v, 2) for v in r[deduction]]
    [20.0, 32.0, 19.2, 11.52, 11.52, 5.76]
    """
    if years not in _MACRS:
        raise ValueError(f"MACRS recovery periods: {', '.join(map(str, _MACRS))}")
    return Kernel(_MACRS[years], f"macrs({years})")


def straight_line(years: int, half_year: bool = True) -> Kernel:
    """Return a straight-line depreciation schedule as a kernel over annual periods.

    Parameters
    ----------
    years : int
        Recovery period in years. It must be at least 1.
    half_year : bool, optional
        If `True`, deduct half a year's share in the first year and the other half in the year after the last, so
        the schedule covers ``years + 1`` years, as tax schedules such as the 20-year straight line do. If `False`,
        deduct ``1 / years`` in each of ``years`` years. The default is `True`.

    Returns
    -------
    Kernel
        A kernel named ``"straight_line(<years>)"`` whose weight ``k`` is the share of the cost deducted ``k`` years
        after the year placed in service. The weights sum to 1.

    Raises
    ------
    ValueError
        At construction, if ``years`` is less than 1.

    See Also
    --------
    boki.lib.macrs : US MACRS tax depreciation.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    The kernel counts periods, so use it with annual periods. ``b.even(years)`` gives the same weights as
    ``half_year=False`` for any period length.

    Examples
    --------
    A four-year asset bought for 100 in the first year, with the half-year convention:

    >>> import boki as b
    >>> m = b.Model("Tax depreciation", start="2027-01", periods=6, step=b.year)
    >>> capex = m.series("Capex", data={0: 100})
    >>> deduction = capex.spread(b.lib.straight_line(4))
    >>> r = m.render()
    >>> [round(v, 2) for v in r[deduction]]
    [12.5, 25.0, 25.0, 25.0, 12.5, 0.0]
    >>> b.lib.straight_line(2, half_year=False).weights
    (0.5, 0.5)
    """  # noqa: DOC105
    if years < 1:
        raise ValueError(f"straight_line() needs a positive number of years, got {years}")
    if not half_year:
        return Kernel([1 / years] * years, f"straight_line({years})")
    return Kernel([0.5 / years] + [1 / years] * (years - 1) + [0.5 / years], f"straight_line({years})")


def nol(base, opening=0, cap=None) -> NOL:
    """Return a tax loss carryforward on a tax base: the balance, the losses used, and the taxable income left.

    Losses add to the balance, and later profits use it up, at most ``cap`` times the profit of a period when a law
    limits it. The carryforward is computed outside the ledger; ``pl.income_tax(nol=True)`` keeps the same
    carryforward inside the tax line, as its ``.nol``. ``boki.nol`` is the same function.

    Parameters
    ----------
    base : Series
        Pretax income or another tax base in each period. A negative value is a loss that adds to the balance; a
        positive value is profit that the balance can offset.
    opening : scalar or Quantity, optional
        Losses carried in from before the model starts, in the unit of ``base``. The default is ``0``.
    cap : scalar or Series, optional
        The most of a period's profit that the carryforward can offset, a dimensionless fraction of the profit
        (``0.8`` is 80%). If it is `None`, there is no limit. The default is `None`.

    Returns
    -------
    NOL
        A named tuple ``(balance, used, taxable)`` of series in the unit of ``base``. ``balance`` is the losses still
        to use at the end of each period. ``used`` is the losses used against the period's profit: the smaller of
        ``cap`` times the profit and the balance carried from the previous period. ``taxable`` is the profit left
        after them, ``max(base, 0) - used``.

    Notes
    -----
    Multiply ``taxable`` by the tax rate for the tax of each period. A loss in a period adds to the balance at the
    end of that period; it is first available in the next one.

    Examples
    --------
    A loss of 50, then profits of 30, 100, and 10, taxed at 25%:

    >>> import boki as b
    >>> m = b.Model("Tax losses", start="2027-01", periods=4, step=b.year)
    >>> income = m.series("Pretax income", data={0: -50, 1: 30, 2: 100, 3: 10})
    >>> carry = b.lib.nol(income)
    >>> r = m.render()
    >>> r[carry.balance]
    [50, 20, 0, 0]
    >>> r[carry.used]
    [0, 30, 20, 0]
    >>> r[carry.taxable]
    [0, 0, 80, 10]
    >>> r[carry.taxable * 0.25]
    [0.0, 0.0, 20.0, 2.5]

    Losses of 20 carried in from before the model, with the carryforward limited to 80% of each profit:

    >>> carry = b.lib.nol(income, opening=20, cap=0.8)
    >>> [round(v, 2) for v in r[carry.used]]
    [0.0, 24.0, 46.0, 0.0]
    """  # noqa: DOC105, DOC106, DOC107
    from .ledger import _nol
    return _nol(lift(base), "NOL", opening=opening, cap=cap)


__all__ = [
    "black_scholes", "capm", "compound", "discount", "fade", "gordon", "hamada", "index", "irr",
    "levelized", "lookup", "macrs", "nol", "npv", "pmt", "ssfa", "straight_line", "wacc", "xirr", "xnpv",
    "NoRateOfReturn",
]
