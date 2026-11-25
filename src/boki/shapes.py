"""Time shapes and delay kernels: values by year or from a date, and how an amount spreads over later
periods (settle=, recognize=, x.spread). These are b.by_year, b.step, b.delay, b.even, b.curve and b.mix;
boki.lib keeps the sourced financial formulas."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .series import Series, _site, _unify, lift

if TYPE_CHECKING:
    from collections.abc import Iterable


class _ByYear(Series):
    def __init__(self, mapping: dict, default):
        self.site = _site()
        self.mapping, self.default = mapping, default
        self.name = "by_year"
        self.unit = _unify([lift(v) for v in [*mapping.values(), default]], "mix")

    def pick(self, r, t):
        """The value period t takes (the default when no key matches); evaluation and the Excel writer share it."""
        key = _model_year(r, t)
        self._check_keys(r)
        for k, v in self.mapping.items():
            if isinstance(k, str) and k != "terminal" or hasattr(k, "year"):
                k = _model_year(r, r.period_index(k))          # a date or period label: the year it falls in
            if (k == "terminal" and t == r.n - 1) or (isinstance(k, range) and key in k) or k == key:
                return v
        return self.default

    def _check_keys(self, r):
        """An int key is a model year: one past the model's years would silently never apply."""
        last = _model_year(r, r.n - 1)
        for k in self.mapping:
            if isinstance(k, int) and not isinstance(k, bool) and not 0 <= k <= last:
                hint = f"; for the calendar year write the key as {str(k)!r}" if k >= 1900 else ""
                raise ValueError(f"by_year key {k} is outside the model years 0-{last} (int keys count model "
                                 f"years from 0){hint}")

    def _eval(self, r, t):
        v = self.pick(r, t)
        return None if v is None else r.value(lift(v), None if lift(v).scalar else t)


class _Year(Series):
    """A reduction over one model year: x.sum(year=), mean, min, max, or the year's last value (x.last(year=))."""
    scalar = True
    FNS = {"sum": sum, "mean": lambda vs: sum(vs) / len(vs), "min": min, "max": max}

    def __init__(self, src, y: int, kind: str):
        self.src, self.y, self.kind = lift(src), y, kind
        self.unit = self.src.unit
        self.name = f"{self.src.name or 'series'} {kind} in year {y}"

    def periods(self, r) -> list[int]:
        ts = [t for t in range(r.n) if _model_year(r, t) == self.y]
        if not ts:
            raise ValueError(f"year={self.y} is outside the model years 0-{_model_year(r, r.n - 1)}")
        return ts

    def _eval(self, r, _):
        ts = self.periods(r)
        if self.src.scalar:
            v = r.value(self.src, None)
            return v * len(ts) if self.kind == "sum" and v is not None else v
        if self.kind == "last":
            return r.value(self.src, ts[-1])
        vals = [v for v in (r.value(self.src, t) for t in ts) if v is not None]
        return self.FNS[self.kind](vals) if vals or self.kind == "sum" else None


def _model_year(r, t: int) -> int:
    """The model year (0 = the first twelve months) period t falls in."""
    periods = r.model.timeline.periods
    if all(p.months == 12 for p in periods):
        return t
    return sum(p.months for p in periods[:t]) // 12


def by_year(mapping: dict, default=None) -> Series:
    """Return values for model years counted from zero.

    Integer keys count model years from the model start, with each model year spanning twelve months. Date and
    period-label keys select the model year containing that date or period. A `range` selects model years with
    Python's stop-exclusive semantics, and ``"terminal"`` selects the last period. A selected value is used in
    every period of that model year. Periods without a matching key use `default`.

    Parameters
    ----------
    mapping : dict
        Map a model-year index (`int`), `range`, date, period label (`str`), or ``"terminal"`` to a numeric scalar,
        `Quantity`, or `Series`. Date and period-label keys select the model year that contains them. Values and
        `default` must have compatible units.
    default : scalar, Quantity, or Series, optional
        A scalar, `Quantity`, `Series`, or `None`. Use a value with units compatible with `mapping`; the default is
        `None`.

    Returns
    -------
    Series
        A value for each model period. The series has the common unit of the mapping values and `default`.

    Raises
    ------
    UnitError
        At construction, if mapping values and `default` have incompatible units.
    ValueError
        At evaluation, if an integer key is outside the model's year range. Integer keys count from zero, not from
        the calendar year.

    See Also
    --------
    boki.step : Select values by model-period index.
    boki.by_month : Select values by calendar month.

    Examples
    --------
    Use a calendar-year label or a zero-based model-year index in an annual model:

    >>> import boki as b
    >>> m = b.Model("Revenue", start="2027-01", periods=3, step=b.year)
    >>> value = b.by_year({"2027": 10, 1: 20}, default=0)
    >>> r = m.render()
    >>> [r.value(value, period) for period in ("2027", "2028", "2029")]
    [10, 20, 0]

    Model years count twelve months from the model start, even with monthly periods:

    >>> m = b.Model("Monthly revenue", start="2027-01", periods=24, step=b.month)
    >>> value = b.by_year({0: 5, 1: 7})
    >>> r = m.render()
    >>> [r.value(value, period) for period in ("2027-01", "2028-01")]
    [5, 7]
    """  # noqa: DOC105, DOC107, DOC502
    return _ByYear(mapping, default)


class _Step(Series):
    def __init__(self, mapping: dict):
        self.site = _site()
        self.mapping = mapping
        self.name = "step"
        self.unit = _unify([lift(v) for v in mapping.values()], "mix")

    def pick(self, r, t):
        """The value in effect in period t (None before the first key); evaluation and the Excel writer share it."""
        current = None
        for k in sorted(self.mapping, key=r.period_index):
            if r.period_index(k) <= t:
                current = self.mapping[k]
        return current

    def _eval(self, r, t):
        v = self.pick(r, t)
        return None if v is None else r.value(lift(v), None if lift(v).scalar else t)


def step(mapping: dict) -> Series:
    """Return a value that takes effect at each key and holds until the next key.

    Each key is a period of the model. A key's value applies from that period up to the period before the next key,
    so a price list or a rate that changes on given dates is one `step`. The order of the keys does not matter.
    Periods before the first key have no value (``None``), and a series computed from a missing value is missing
    too.

    Parameters
    ----------
    mapping : dict
        Map a period key to a numeric scalar, `Quantity`, or `Series`. A key is a zero-based period index (`int`;
        a negative index counts from the last period), a date, or a period label such as ``"2027-04"`` or
        ``"2028"`` (annual periods). A date selects the period that contains it. A `Series` value is evaluated in
        each period in which its key is in effect. Values must have compatible units; a literal 0 fits any unit.

    Returns
    -------
    Series
        The value in effect in each period. The series has the common unit of the values.

    Raises
    ------
    UnitError
        At construction, if the values have incompatible units.
    IndexError
        At evaluation, if a key is outside the model's timeline.

    See Also
    --------
    boki.by_year : Select values by model year.
    boki.by_month : Select values by calendar month.

    Notes
    -----
    Integer keys are period indexes, not model years: ``b.step({1: x})`` starts in the second period whatever the
    period length, while ``b.by_year({1: x})`` starts in the second twelve months.

    Examples
    --------
    A price that changes on given months of a monthly model:

    >>> import boki as b
    >>> m = b.Model("Price list", start="2027-01", periods=6, step=b.month)
    >>> price = b.step({"2027-01": 100, "2027-04": 120})
    >>> r = m.render()
    >>> r[price]
    [100, 100, 100, 120, 120, 120]

    Periods before the first key have no value:

    >>> late = b.step({"2027-03": 5})
    >>> r[late]
    [None, None, 5, 5, 5, 5]

    Integer keys count periods, so with quarterly periods ``2`` is the third quarter:

    >>> m = b.Model("Quarterly", start="2027-01", periods=4, step=3 * b.month)
    >>> level = b.step({0: 1, 2: 2})
    >>> r = m.render()
    >>> [r.value(level, quarter) for quarter in ("2027-01", "2027-04", "2027-07", "2027-10")]
    [1, 1, 2, 2]
    """  # noqa: DOC502
    return _Step(mapping)


class _ByMonth(_Step):
    """A value by calendar month. A _Step for the Excel writer: each period's value is picked the same way."""

    def __init__(self, mapping: dict, default):
        super().__init__({**mapping, **({"default": default} if default is not None else {})})
        self.name = "by_month"
        self.months, self.default = mapping, default

    def pick(self, r, t):
        p = r.model.timeline.periods[t]
        if p.start is None or p.months != 1:
            raise ValueError("b.by_month needs dated monthly periods; for longer periods use b.by_year or b.step")
        return self.months.get(p.start.month, self.default)


def by_month(values, default=None) -> Series:
    """Return a value that depends on the calendar month of each period, for seasonality in a monthly model.

    The model must have dated periods of one month each. A month's value applies in every period that starts in
    that month, in every year.

    Parameters
    ----------
    values : dict, list, or tuple
        Either a `dict` that maps a calendar month (`int`, 1 for January to 12 for December) to a numeric scalar,
        `Quantity`, or `Series`, or a `list` or `tuple` of exactly twelve such values from January. Values must have
        compatible units with each other and with `default`.
    default : scalar, Quantity, or Series, optional
        Value of the months that `values` does not list. If it is `None`, `values` must give all twelve months. The
        default is `None`.

    Returns
    -------
    Series
        The value for the calendar month of each period. The series has the common unit of `values` and `default`.

    Raises
    ------
    TypeError
        At construction, if `values` is not a `dict`, `list`, or `tuple`.
    ValueError
        At construction, if a list does not have twelve values, a key is not an `int` from 1 to 12, or `default` is
        `None` and a month has no value. At evaluation, if a period is not a dated period of one month, as in a
        quarterly model or a model that starts with an integer.
    UnitError
        At construction, if the values and `default` have incompatible units.

    See Also
    --------
    boki.by_year : Select values by model year.
    boki.step : Select values by period.

    Notes
    -----
    The month is the month in which a period starts, so ``by_month`` needs monthly periods; use `by_year` or
    `step` for longer ones.

    Examples
    --------
    A seasonal factor that is 1.2 in November, 1.4 in December, and 1.0 in other months:

    >>> import boki as b
    >>> m = b.Model("Season", start="2027-11", periods=4, step=b.month)
    >>> season = b.by_month({11: 1.2, 12: 1.4}, default=1.0)
    >>> r = m.render()
    >>> r[season]
    [1.2, 1.4, 1.0, 1.0]

    Twelve values from January give every month a value, so no default is needed:

    >>> sales = b.by_month([10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 20, 30])
    >>> r[sales]
    [20, 30, 10, 10]
    """  # noqa: DOC105, DOC106, DOC107, DOC503
    if isinstance(values, (list, tuple)):
        if len(values) != 12:
            raise ValueError(f"b.by_month takes twelve values from January, got {len(values)}")
        values = dict(zip(range(1, 13), values))
    if not isinstance(values, dict):
        raise TypeError("b.by_month takes a dict keyed by month (1-12) or a list of twelve values")
    bad = [k for k in values if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 12]
    if bad:
        raise ValueError(f"b.by_month keys are calendar months 1-12, got {bad}")
    if default is None and len(values) < 12:
        missing = sorted(set(range(1, 13)) - set(values))
        raise ValueError(f"b.by_month has no value for months {missing}; add them or pass default=")
    return _ByMonth(dict(values), default)


class Kernel:
    """A kernel: the shares of one amount that fall in the same period and in later periods.

    ``weights[k]`` is the share that falls ``k`` periods after the period of the amount, so ``delay(2)`` has the
    weights ``(0, 0, 1)``. The unit of ``k`` is the model's period, not a month. A kernel sets when cash moves
    (``settle=``), when profit is recognized (``recognize=``), when bought inventory is used (``used=``), and how a
    series spreads over later periods (``Series.spread``). Build kernels with `delay`, `even`, `curve`, `mix`, and
    the tax schedules of `boki.lib` (`macrs`, `straight_line`) rather than by calling the class.

    Parameters
    ----------
    weights : Iterable[float]
        Share of the amount that falls ``k`` periods later, for ``k = 0, 1, ...``. The shares are dimensionless
        fractions of the amount. At least one weight is required, and every weight must be finite. The weights
        are stored as a `tuple`.
    name : str
        Label for messages and for the name of series built with the kernel. The label ``"curve"`` also makes
        `boki.shapes.spread` keep applying the last weight in all later periods.

    Attributes
    ----------
    weights : tuple[float, ...]
        Share of the amount that falls ``k`` periods after the amount, for ``k = 0, 1, ...``.
    name : str
        The kernel's label, such as ``"delay(2)"``.

    Raises
    ------
    ValueError
        At construction, if there are no weights or a weight is not finite.

    See Also
    --------
    boki.delay : A kernel that moves an amount a number of periods later.
    boki.even : A kernel that spreads an amount evenly.
    boki.curve : A kernel from arbitrary weights.
    boki.mix : A weighted mix of kernels.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    Two kernels are equal when their weights are equal, whatever their names, and a kernel hashes by its weights.
    ``settle=``, ``recognize=``, and ``used=`` accept only kernels whose weights sum to 1 (a distribution), and
    reject a `curve`, which keeps applying its last weight, unless it ends in 0.

    Examples
    --------
    Read the weights of a kernel:

    >>> import boki as b
    >>> kernel = b.delay(2)
    >>> kernel.weights
    (0.0, 0.0, 1.0)
    >>> kernel.name
    'delay(2)'
    >>> b.delay(1) == b.curve([0, 1])
    True
    """

    weights: tuple[float, ...]
    name: str

    def __init__(self, weights: Iterable[float], name: str):
        import math
        weights = tuple(weights)
        if not weights:
            raise ValueError(f"a kernel needs at least one weight ({name})")
        if not all(math.isfinite(x) for x in weights):
            raise ValueError(f"kernel weights must be finite, got {list(weights)} ({name})")
        self.weights, self.name = weights, name

    def __repr__(self):
        return f"<Kernel {self.name}>"

    def __hash__(self):
        return hash(self.weights)

    def __eq__(self, other):
        return isinstance(other, Kernel) and other.weights == self.weights


def delay(n: int) -> Kernel:
    """Return a kernel that moves the whole amount ``n`` periods later.

    Use it for ``settle=`` to collect or pay cash after a fixed lag, such as ``b.delay(2)`` for 60-day terms in a
    monthly model.

    Parameters
    ----------
    n : int
        Number of periods later, counted in the model's periods, not in months. ``0`` keeps the amount in the same
        period. It must not be negative.

    Returns
    -------
    Kernel
        A kernel whose weights are 0 for the first ``n`` periods and 1 in period ``n``.

    Raises
    ------
    ValueError
        At construction, if ``n`` is negative.

    See Also
    --------
    boki.even : Spread an amount evenly instead of moving it all at once.
    boki.mix : Split an amount between kernels.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    A period is whatever length the model uses. ``b.delay(1)`` is one month in a monthly model and three months in
    a quarterly one. With ``settle=``, a revenue line is booked into the shared receivable (an expense line into the
    payable) and the cash follows the kernel; see the `account and settlement table
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#pl-rows-japanese-gaap>`_.

    Examples
    --------
    Revenue booked in each month of a monthly model and collected one month later:

    >>> import boki as b
    >>> months = ["2027-01", "2027-02", "2027-03"]
    >>> m = b.Model("Collections", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS)
    >>> sales = co.pl.revenue("Sales", 100, settle=b.delay(1))
    >>> r = m.render()
    >>> [round(r.value(sales, month)) for month in months]
    [100, 100, 100]
    >>> [round(r.value(co.bs.cash, month)) for month in months]
    [0, 100, 200]

    The lag counts periods: one period is one quarter in a quarterly model.

    >>> m = b.Model("Quarterly", start="2027-01", periods=3, step=3 * b.month)
    >>> co = m.entity("A", standard=b.IFRS)
    >>> sales = co.pl.revenue("Sales", 100, settle=b.delay(1))
    >>> r = m.render()
    >>> [round(r.value(co.bs.cash, quarter)) for quarter in ("2027-01", "2027-04", "2027-07")]
    [0, 100, 200]
    """
    if n < 0:
        raise ValueError(f"delay() needs a non-negative period count, got {n}")
    return Kernel([0.0] * n + [1.0], f"delay({n})")


def even(n: int) -> Kernel:
    """Return a kernel that spreads an amount evenly over ``n`` periods, starting with the period of the amount.

    Use it for ``recognize=`` to recognize a prepayment over the months it covers, for ``settle=`` to pay in equal
    instalments, or with ``Series.spread`` to smear an amount over time.

    Parameters
    ----------
    n : int
        Number of periods, counted in the model's periods, not in months. It must be at least 1; ``1`` keeps the
        amount in its own period.

    Returns
    -------
    Kernel
        A kernel with ``n`` equal weights of ``1 / n``, so the shares sum to 1.

    Raises
    ------
    ValueError
        At construction, if ``n`` is less than 1.

    See Also
    --------
    boki.delay : Move an amount all at once.
    boki.curve : Spread by arbitrary weights.
    boki.mix : Split an amount between kernels.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    The shares are dimensionless fractions of the amount. With ``recognize=`` the amount is billed in its own
    period into deferred revenue (revenue lines) or prepaid expenses (expense lines) and released to profit by the
    kernel; see the `account and settlement table
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#pl-rows-japanese-gaap>`_.

    Examples
    --------
    An annual insurance premium of 300 paid up front in January and recognized as an expense over three months:

    >>> import boki as b
    >>> months = ["2027-01", "2027-02", "2027-03", "2027-04"]
    >>> m = b.Model("Insurance", start="2027-01", periods=4, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS)
    >>> co.bs.opening(cash=1000)
    >>> premium = co.pl.sga("Premium", {0: 300}, recognize=b.even(3))
    >>> r = m.render()
    >>> [round(r.value(premium, month)) for month in months]
    [100, 100, 100, 0]
    >>> [round(r.value(co.bs.cash, month)) for month in months]
    [700, 700, 700, 700]

    Spread a one-off amount of 100 over two periods:

    >>> m = b.Model("Spread", start="2027-01", periods=3, step=b.month)
    >>> amount = m.series("Amount", data={0: 100})
    >>> r = m.render()
    >>> r[amount.spread(b.even(2))]
    [50.0, 50.0, 0.0]
    """
    if n < 1:
        raise ValueError(f"even() needs a positive period count, got {n}")
    return Kernel([1.0 / n] * n, f"even({n})")


def curve(weights) -> Kernel:
    """Return a kernel from arbitrary weights by periods elapsed, such as a ramp or an S-curve.

    Applied with ``Series.spread``, the last weight keeps applying in every later period, so a ramp that ends at 1
    stays at full. To use a curve as a distribution for ``settle=`` or ``recognize=``, end it with a weight of 0 and
    make the weights sum to 1.

    Parameters
    ----------
    weights : iterable of float
        Share of the amount that falls ``k`` periods later, for ``k = 0, 1, ...``, as dimensionless fractions of the
        amount. At least one weight is required and every weight must be finite. The weights do not have to sum to
        1 for ``Series.spread``.

    Returns
    -------
    Kernel
        A kernel named ``"curve"`` with these weights.

    Raises
    ------
    ValueError
        At construction, if there are no weights or a weight is not finite.

    See Also
    --------
    boki.delay : Move an amount all at once.
    boki.even : Spread an amount evenly.
    boki.mix : Split an amount between kernels.
    boki.shapes.spread : Apply a kernel to a series.

    Notes
    -----
    Only a kernel made by ``curve`` holds its last weight. A `mix` of curves, or a kernel from `delay`, `even`,
    or the tax schedules, applies its weights once and then contributes nothing.

    Examples
    --------
    A ramp-up: a one-off amount of 100 reaches the output at 25%, then 50%, then in full and keeps contributing:

    >>> import boki as b
    >>> m = b.Model("Ramp", start="2027-01", periods=4, step=b.month)
    >>> amount = m.series("Amount", data={0: 100})
    >>> r = m.render()
    >>> r[amount.spread(b.curve([0.25, 0.5, 1]))]
    [25.0, 50.0, 100.0, 100.0]

    A curve that ends in 0 does not keep contributing:

    >>> r[amount.spread(b.curve([0.25, 0.5, 0.25, 0]))]
    [25.0, 50.0, 25.0, 0.0]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Kernel(list(weights), "curve")


def mix(parts: dict) -> Kernel:
    """Return a kernel that is a weighted mix of kernels, such as 70% in the same period and 30% a period later.

    Parameters
    ----------
    parts : dict
        Map each `Kernel` to its share of the amount, a dimensionless fraction. The shares must add up to 1
        (within 1e-9).

    Returns
    -------
    Kernel
        A kernel named ``"mix"`` whose weight in each period is the sum over the parts of the share times the
        part's weight. It is as long as the longest part.

    Raises
    ------
    ValueError
        At construction, if the shares do not add up to 1.

    See Also
    --------
    boki.delay : Move an amount all at once.
    boki.even : Spread an amount evenly.
    boki.curve : Spread by arbitrary weights.

    Notes
    -----
    The result is a plain ``"mix"`` kernel, so a `curve` inside it stops after its last weight instead of holding
    it. Individual shares are not checked beyond the total.

    Examples
    --------
    Customers pay 70% in the month of the sale and 30% a month later:

    >>> import boki as b
    >>> months = ["2027-01", "2027-02", "2027-03"]
    >>> m = b.Model("Collections", start="2027-01", periods=3, step=b.month)
    >>> co = m.entity("A", standard=b.IFRS)
    >>> sales = co.pl.revenue("Sales", 100, settle=b.mix({b.delay(0): 0.7, b.delay(1): 0.3}))
    >>> r = m.render()
    >>> [round(r.value(co.bs.cash, month)) for month in months]
    [70, 170, 270]
    >>> b.mix({b.delay(0): 0.7, b.delay(1): 0.3}).weights
    (0.7, 0.3)
    """
    if abs(sum(parts.values()) - 1) > 1e-9:
        raise ValueError("mix() weights must sum to 1")
    width = max(len(k.weights) for k in parts)
    w = [0.0] * width
    for k, share in parts.items():
        for i, x in enumerate(k.weights):
            w[i] += share * x
    return Kernel(w, "mix")


def _check_kernel_distribution(kernel: Kernel, what: str) -> None:
    """A kernel that distributes one amount over later periods (settle=, recognize=, a VAT
    settlement) must move exactly that amount in total: finite weights summing to 1, and no
    held tail. A curve() keeps applying its last weight every later period, so as a
    distribution it must end in 0 — settle=b.curve([1.0]) otherwise collects the same
    amount again in every period (cash from nothing, the accrual driven negative)."""
    import math
    w = kernel.weights
    if not w or not all(math.isfinite(x) for x in w):
        raise ValueError(f"{what}: kernel weights must be finite, got {list(w)}")
    if kernel.name == "curve" and w[-1] != 0:
        raise ValueError(f"{what}: a curve() kernel keeps applying its last weight ({w[-1]:g}) every "
                         "later period, so it cannot distribute an amount; end it with 0 or use delay/even/mix")
    total = sum(w)
    if abs(total - 1) > 1e-6:
        raise ValueError(f"{what}: kernel weights must sum to 1, got {total:g} ({kernel.name}: {list(w)})")


class _Spread(Series):
    def __init__(self, src, kernel: Kernel, hold_last: bool):
        self.src, self.kernel, self.hold_last = lift(src), kernel, hold_last
        self.unit = self.src.unit
        self.name = f"{self.src.name or 'series'}.spread({kernel.name})"

    def _eval(self, r, t):
        w = self.kernel.weights
        total = 0.0
        for s in range(t + 1):
            k = t - s
            if k < len(w):
                weight = w[k]
            elif self.hold_last:
                weight = w[-1]
            else:
                continue
            if weight:
                v = r.value(self.src, None if self.src.scalar else s)
                total += weight * (v or 0)
        return total


def spread(src, kernel: Kernel) -> Series:
    """Return a series in which each amount of ``src`` is spread over its own and later periods by ``kernel``.

    The value in period ``t`` is the sum over earlier or equal periods ``s`` of ``kernel.weights[t - s]`` times the
    value of ``src`` in period ``s``. A scalar ``src`` counts as the same amount in every period. ``Series.spread``
    is the method form of this function.

    Parameters
    ----------
    src : Series, Quantity, or number
        The amounts to spread, in any unit. A `Series` is read in every period, a scalar counts as the same amount
        in every period.
    kernel : Kernel
        The shares by periods elapsed. A kernel made by `curve` keeps applying its last weight in later periods;
        any other kernel contributes nothing after its last weight.

    Returns
    -------
    Series
        The spread amounts in each period. The series has the unit of ``src``.

    See Also
    --------
    boki.delay : Move an amount all at once.
    boki.even : Spread an amount evenly.
    boki.curve : Spread by arbitrary weights.
    boki.mix : Split an amount between kernels.

    Notes
    -----
    The result adds up to the amounts spread only if the weights add up to 1 and nothing is cut off by the end of
    the model: amounts in the last periods are not fully spread.

    Examples
    --------
    A one-off amount of 100 spread evenly over two months:

    >>> import boki as b
    >>> m = b.Model("Spread", start="2027-01", periods=4, step=b.month)
    >>> amount = m.series("Amount", data={0: 100})
    >>> r = m.render()
    >>> r[b.shapes.spread(amount, b.even(2))]
    [50.0, 50.0, 0.0, 0.0]

    Amounts in several periods add up where their spreads overlap:

    >>> orders = m.series("Orders", data={0: 100, 1: 60})
    >>> r[orders.spread(b.delay(1))]
    [0.0, 100.0, 60.0, 0.0]
    """  # noqa: DOC105, DOC107
    return _Spread(src, kernel, hold_last=kernel.name == "curve")


__all__ = ["Kernel", "by_month", "by_year", "curve", "delay", "even", "mix", "spread", "step"]
