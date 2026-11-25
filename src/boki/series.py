"""Series: lazily evaluated expressions over the model's periods.

A Series is a node in an expression graph. Building a model only builds nodes and
checks their units; values exist only inside a render (see evaluator.Render).
Scalar nodes ignore the period and evaluate once.
"""
from __future__ import annotations

import math
import operator
import textwrap
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any, Callable

from . import evaluator
from .units import _DIMENSIONLESS, Dims, Quantity, Unit, UnitError, _combine, day, _describe

DATE: Dims = frozenset({("date", 1)})
MONTHS: Dims = frozenset({("month", 1)})



_PACKAGE = __file__.rsplit("/", 1)[0]


def _site() -> str | None:
    """Where in the user's code a series is being made (file:line), for messages that point back to it. Made in a
    helper (a lambda in the plan), it is the helper's caller in the same file, with the helper's line."""
    import sys
    f = sys._getframe(1)
    while f is not None and f.f_code.co_filename.startswith(_PACKAGE):
        f = f.f_back
    if f is None:
        return None
    inner, outer = f, f
    while outer.f_back is not None and outer.f_back.f_code.co_filename == inner.f_code.co_filename:
        outer = outer.f_back
    here = f"{outer.f_code.co_filename}:{outer.f_lineno}"
    return here if outer is inner else f"{here} (in a helper at line {inner.f_lineno})"


def _operator(summary: str, *, other: str | None = None, other_type: str = "Series, Quantity, or number",
              returns: str, raises: tuple[tuple[str, str], ...] = (), notes: str = "",
              see_also: tuple[tuple[str, str], ...] = (), examples: str):
    """Give a `Series` operator its numpydoc text.

    The operators share one layout (one operand, the resulting `Series`, the unit rule, an example) and differ only
    in the fields passed here. The text is assembled once at import, so each operator reads and validates like a
    hand-written docstring.
    """
    def fill(text: str, indent: str = "    ") -> str:
        return "\n".join(textwrap.fill(paragraph, width=118, initial_indent=indent, subsequent_indent=indent)
                         for paragraph in text.split("\n\n"))

    def apply(fn):
        parts = [summary, ""]
        if other is not None:
            parts += ["Parameters", "----------", f"other : {other_type}", fill(other), ""]
        parts += ["Returns", "-------", "Series", fill(returns), ""]
        if raises:
            parts += ["Raises", "------"]
            for error, text in raises:
                parts += [error, fill(text)]
            parts.append("")
        if see_also:
            parts += ["See Also", "--------"]
            parts += [f"{name} : {text}" for name, text in see_also]
            parts.append("")
        if notes:
            parts += ["Notes", "-----", "\n\n".join(textwrap.fill(p, width=118) for p in notes.split("\n\n")), ""]
        parts += ["Examples", "--------", textwrap.dedent(examples).strip("\n")]
        fn.__doc__ = "\n".join(parts) + "\n"
        return fn
    return apply


_UNIT_CONFLICT = ("At construction, if the operands have different units, such as a plain number and a series in USD, "
                  "or USD and JPY. A literal 0 and a series of unknown unit never conflict.")
_UNSUPPORTED = ("At construction, if `other` has a type a series expression cannot use, such as a list or a "
                "dict.")
_COMPARE_OTHER = ("The value to compare with: a series, a number, a `Quantity` such as ``100 * USD``, or a date. "
                  "Its unit must match this series' unit; a literal 0 and an unknown unit never conflict.")


class Series:
    """Lazily evaluated expression over the model's periods, with a unit.

    A series is a node in an expression graph, not a list of numbers. Arithmetic, `lag`, `where` and the other
    operations build new nodes and check units while the model is being written; values exist only after
    `Model.render`, and you read them with ``r[x]`` or ``r.value(x, period)``. A *scalar* series has one value for
    the whole model (an input, a total such as ``x.sum()``); every other series has one value per period. Subclasses
    such as `Named`, `Input`, `Unknown` and `LineItem` add how the values are found; all of them support the
    operations below.

    Build a series with `Model.series`, `Model.input` or `Model.unknown`, from the statement lines of an entity, or
    from the shape functions such as `boki.by_year`. Do not construct `Series` directly.

    A *missing* value is ``None``. Arithmetic and comparison give a missing result when an operand is missing, the
    reductions (`sum`, `mean`, `min`, `max`) skip missing values, and `cumsum` counts them as 0.

    A series has no truth value while the model is being written, because it holds no numbers yet. ``if x > 0:``,
    ``and``, ``or`` and ``not`` raise `TypeError`; branch per period with `where`, combine conditions with ``&``,
    ``|`` and ``~``, and read values with ``x[t]`` inside an ``@m.series`` function. A series cannot be iterated
    either. Because ``==`` builds a series, test whether two names refer to the same series with ``is``.

    Attributes
    ----------
    name : str or None
        Name the series is registered under, or ``None`` for an unnamed expression.
    unit : frozenset or None
        Dimensions of the values, as a set of ``(base unit name, exponent)`` pairs; the empty set is a dimensionless
        number. ``None`` means the unit is unknown and unit checks are skipped.

    See Also
    --------
    boki.Model.series : Create a named series.
    boki.Model.input : Create a named assumption.

    Notes
    -----
    See the `series guide <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#series>`_ for the
    forms of ``m.series`` and the `conventions <https://github.com/combinatrix-ai/boki/blob/master/docs/conventions.md>`_
    for how years, periods and signs are counted.

    Examples
    --------
    Build a series from other series and read its values from a render:

    >>> import boki as b
    >>> m = b.Model("Sales", start="2027-01", periods=3, step=b.month)
    >>> units = m.series("Units", data={0: 10, 1: 12, 2: 9})
    >>> revenue = m.series("Revenue", units * 30)
    >>> r = m.render()
    >>> r[revenue]
    [300, 360, 270]
    >>> r[revenue.sum()]
    930
    """  # noqa: DOC601, DOC603

    scalar = False
    name: str | None = None
    unit: Dims | None = None
    display: Unit | None = None      # the unit tables and Excel show this series in (see Result.display_unit)

    def _eval(self, r: "evaluator.Render", t: int | None) -> Any:
        raise NotImplementedError

    def __getitem__(self, t):
        """Return the value at one period inside a render, or a scalar series for that period outside one.

        Parameters
        ----------
        t : int, str, date, or Series
            The period. An integer is a period index from 0, and a negative integer counts from the last period. A
            string is a period label (``"2028"``, ``"2027-04"``) or a date (``"2027-04-15"``, ``"2027/04"``) inside
            the period. A `datetime.date` is read the same way. A scalar series, such as an input, supplies the key
            when the model is rendered.

        Returns
        -------
        Series or float
            Outside a render (while the model is being written), a scalar series with this series' unit that holds
            the value of the period. Inside a render (in an ``@m.series`` function), the value itself, a plain
            number in base units. Reading a scalar series gives its one value.

        Raises
        ------
        IndexError
            At evaluation, if the period is outside the model's timeline.
        TypeError
            At evaluation, if the key is a bool.

        See Also
        --------
        boki.Series.last : Value in the last period, or in the last period of a model year.
        boki.Result.value : Value of any series in one period, read from a render.

        Examples
        --------
        Pick periods by index, label, or negative index while writing the model:

        >>> import boki as b
        >>> m = b.Model("Pick", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> peak = sales[1]
        >>> r = m.render()
        >>> r[peak], r[sales["2027-03"]], r[sales[-1]]
        (120, 90, 90)

        Inside an ``@m.series`` function the same call returns numbers, so ordinary Python ``if`` works:

        >>> @m.series
        ... def bonus(t):
        ...     return 10 if sales[t] > 100 else 0
        >>> m.render()[bonus]
        [0, 10, 0]
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        r = evaluator.current()
        if r is not None:
            return r.value(self, None if self.scalar else r.period_index(t))
        return At(self, t)

    def __iter__(self):
        # Without this, Python would iterate through __getitem__ forever (s[0], s[1], ... never raise).
        raise TypeError("a series is not iterable; use result[series] for its values in a render")

    def __bool__(self):
        raise TypeError(
            f"{self!r} is a lazy series; it has no truth value at build time. "
            "Use .where(cond, else_) for per-period branching, or read values with x[t] "
            "inside an @m.series function."
        )

    def __repr__(self):
        return f"<{type(self).__name__}{' ' + self.name if self.name else ''}>"

    # ---- time operations --------------------------------------------------------
    def lag(self, k: int | "Series" = 1, fill: Any = None) -> "Series":
        """Return the value ``k`` periods earlier.

        The result in period ``t`` is this series' value in period ``t - k``. Periods whose source falls outside the
        model take ``fill``.

        Parameters
        ----------
        k : int or Series, default=1
            Number of periods to look back; a negative value looks forward. A series gives an offset for each period
            (a fraction is truncated toward zero). It is a count of periods, not of months, so a quarterly model
            looks back one quarter with ``k=1``.
        fill : scalar, Quantity, or Series, optional
            Value for a period whose source is outside the model. A number or `Quantity` is used as given (a
            `Quantity` contributes its base-unit value, and its unit is not checked); a series is read in the same
            period. The default ``None`` leaves such periods missing.

        Returns
        -------
        Series
            A series with this series' unit and a value in every period, also when this series is scalar.

        Raises
        ------
        TypeError
            At construction, if ``fill`` is a list, tuple, or dict. For history before the first period, give a
            series such as ``b.by_year({...})``.

        See Also
        --------
        boki.Series.opening : The previous period's value, 0 before the first period.
        boki.Series.cumsum : Running total up to and including this period.

        Examples
        --------
        Look back one month, with and without a fill value, and forward with a negative ``k``:

        >>> import boki as b
        >>> m = b.Model("Lag", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> r = m.render()
        >>> r[sales.lag(1)]
        [None, 100, 120]
        >>> r[sales.lag(1, fill=0)]
        [0, 100, 120]
        >>> r[sales.lag(-1, fill=0)]
        [120, 90, 0]
        """  # noqa: DOC105, DOC502
        return Lag(self, k, fill)

    def where(self, cond: "Series", else_: Any = None) -> "Series":
        """Return this series in the periods where a condition holds, and another value elsewhere.

        Python's ``if`` cannot branch per period while the model is being written; this is the branch. Both branches
        are built, and each period takes one of them.

        Parameters
        ----------
        cond : Series
            Condition, usually a comparison such as ``x > 0`` or a combination with ``&``, ``|`` and ``~``. A period
            where it is true takes this series; a false or missing condition takes ``else_``.
        else_ : scalar, Quantity, or Series, optional
            Value in the other periods. The default ``None`` leaves them missing (``None``), which the reductions
            skip, so ``x.where(c).mean()`` averages only where ``c`` holds.

        Returns
        -------
        Series
            A series that is scalar only when ``cond``, this series and ``else_`` are all scalar. Its unit is the
            common unit of this series and ``else_``.

        Raises
        ------
        UnitError
            At construction, if this series and ``else_`` have different units. A literal 0, ``None`` and a series of
            unknown unit never conflict.

        See Also
        --------
        boki.Series.__and__ : Combine two conditions.
        boki.max : Larger of several series in each period.

        Examples
        --------
        Keep sales above a threshold, leaving the other months missing or setting them to 0:

        >>> import boki as b
        >>> m = b.Model("Where", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> r = m.render()
        >>> r[sales.where(sales > 100)]
        [None, 120, None]
        >>> r[sales.where(sales > 100, 0)]
        [0, 120, 0]
        >>> r[sales.where(sales > 100).mean()]
        120.0
        """  # noqa: DOC105, DOC502
        return Where(cond, self, else_)

    @property
    def change(self) -> "Series":
        """Change from the previous period.

        Returns
        -------
        Series
            This period's value minus the previous period's, with 0 as the value before the first period. For a
            ledger balance this is the movement of the period.

        See Also
        --------
        boki.Series.opening : The previous period's value.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Change", start="2027-01", periods=3, step=b.month)
        >>> headcount = m.series("Headcount", data={0: 10, 1: 12, 2: 11})
        >>> r = m.render()
        >>> r[headcount.change]
        [10, 2, -1]
        """
        return self - self.lag(1, fill=0)

    @property
    def opening(self) -> "Series":
        """The previous period's value, 0 before the first period.

        Returns
        -------
        Series
            For a flow this is the value one period back; read on a balance it is the opening balance. For a
            `LineItem` that holds a balance, the first period shows the opening balance declared for it.

        See Also
        --------
        boki.Series.lag : The value ``k`` periods back, with a chosen fill.
        boki.Series.change : This period's value minus the opening.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Opening", start="2027-01", periods=3, step=b.month)
        >>> headcount = m.series("Headcount", data={0: 10, 1: 12, 2: 11})
        >>> r = m.render()
        >>> r[headcount.opening]
        [0, 10, 12]
        """
        return self.lag(1, fill=0)

    # year=y limits a reduction to model year y (0 = the first twelve months, as b.by_year counts)
    def sum(self, year: int | None = None) -> "Series":
        """Return the total over all periods, or over one model year.

        Parameters
        ----------
        year : int, optional
            Model year to total, counted from 0 for the first twelve months of the model, as `boki.by_year` counts.
            The default ``None`` totals every period. A model year spans twelve months whatever the period length.

        Returns
        -------
        Series
            A scalar series in this series' unit. Missing values count as 0. The total of a scalar series over a
            model year is the value times the number of periods in that year.

        Raises
        ------
        TypeError
            At construction, if ``year`` is not an int.
        ValueError
            At evaluation, if ``year`` is outside the model's years.

        See Also
        --------
        boki.Series.cumsum : Running total in every period instead of one number.
        boki.Series.mean : Average instead of total.

        Examples
        --------
        Total a monthly fee over the model and over each model year:

        >>> import boki as b
        >>> m = b.Model("Fees", start="2027-01", periods=24, step=b.month)
        >>> fee = m.series("Fee", 10)
        >>> r = m.render()
        >>> r[fee.sum()], r[fee.sum(year=0)], r[fee.sum(year=1)]
        (240, 120, 120)
        """  # noqa: DOC105, DOC502
        if year is not None:
            return _in_year(self, year, "sum")
        return Reduce(_sum, self, unit=self.unit, excel=lambda a: f"SUM({a})")

    def min(self, year: int | None = None) -> "Series":
        """Return the smallest value over all periods, or over one model year.

        Parameters
        ----------
        year : int, optional
            Model year to search, counted from 0 for the first twelve months of the model. The default ``None``
            searches every period.

        Returns
        -------
        Series
            A scalar series in this series' unit. Missing values are skipped.

        Raises
        ------
        TypeError
            At construction, if ``year`` is not an int.
        ValueError
            At evaluation, if ``year`` is outside the model's years, or if ``year`` is not given and no period has a
            value. With ``year``, a model year without values gives a missing result.

        See Also
        --------
        boki.min : Smaller of several series in each period.
        boki.Series.max : Largest value over the periods.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Low", start="2027-01", periods=3, step=b.month)
        >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
        >>> r = m.render()
        >>> r[cash.min()], r[cash.min(year=0)]
        (-20, -20)
        """  # noqa: DOC105, DOC502
        if year is not None:
            return _in_year(self, year, "min")
        return Reduce(_min, self, unit=self.unit, excel=lambda a: f"MIN({a})")

    def max(self, year: int | None = None) -> "Series":
        """Return the largest value over all periods, or over one model year.

        Parameters
        ----------
        year : int, optional
            Model year to search, counted from 0 for the first twelve months of the model. The default ``None``
            searches every period.

        Returns
        -------
        Series
            A scalar series in this series' unit. Missing values are skipped.

        Raises
        ------
        TypeError
            At construction, if ``year`` is not an int.
        ValueError
            At evaluation, if ``year`` is outside the model's years, or if ``year`` is not given and no period has a
            value. With ``year``, a model year without values gives a missing result.

        See Also
        --------
        boki.max : Larger of several series in each period.
        boki.Series.min : Smallest value over the periods.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("High", start="2027-01", periods=3, step=b.month)
        >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
        >>> r = m.render()
        >>> r[cash.max()], r[cash.max(year=0)]
        (50, 50)
        """  # noqa: DOC105, DOC502
        if year is not None:
            return _in_year(self, year, "max")
        return Reduce(_max, self, unit=self.unit, excel=lambda a: f"MAX({a})")

    def last(self, year: int | None = None) -> "Series":
        """Return the value in the last period, or in the last period of one model year.

        Use it for a year-end balance or a headcount at the end of the model.

        Parameters
        ----------
        year : int, optional
            Model year, counted from 0 for the first twelve months of the model. The default ``None`` reads the last
            period of the model.

        Returns
        -------
        Series
            A scalar series in this series' unit.

        Raises
        ------
        TypeError
            At construction, if ``year`` is not an int.
        ValueError
            At evaluation, if ``year`` is outside the model's years.

        See Also
        --------
        boki.Series.__getitem__ : Value in any one period.

        Examples
        --------
        Read a year-end value from a monthly model with two model years:

        >>> import boki as b
        >>> m = b.Model("Ends", start="2027-01", periods=24, step=b.month)
        >>> r = m.render()
        >>> r[m.t.last()], r[m.t.last(year=0)]
        (23, 11)
        """  # noqa: DOC105, DOC502
        return At(self, -1) if year is None else _in_year(self, year, "last")

    def mean(self, year: int | None = None) -> "Series":
        """Return the average over the periods that have a value, or over one model year.

        Parameters
        ----------
        year : int, optional
            Model year to average, counted from 0 for the first twelve months of the model. The default ``None``
            averages every period.

        Returns
        -------
        Series
            A scalar series in this series' unit. Missing values are skipped, so ``x.where(cond).mean()`` averages
            the periods where ``cond`` holds.

        Raises
        ------
        TypeError
            At construction, if ``year`` is not an int.
        ValueError
            At evaluation, if ``year`` is outside the model's years.
        ZeroDivisionError
            At evaluation, if ``year`` is not given and no period has a value. With ``year``, a model year without
            values gives a missing result.

        See Also
        --------
        boki.Series.sum : Total instead of average.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Average", start="2027-01", periods=24, step=b.month)
        >>> r = m.render()
        >>> r[m.t.mean()], r[m.t.mean(year=1)]
        (11.5, 17.5)
        """  # noqa: DOC105, DOC502
        if year is not None:
            return _in_year(self, year, "mean")
        return Reduce(_mean, self, unit=self.unit, excel=lambda a: f"AVERAGE({a})")

    @property
    def year(self) -> "Series":
        """Calendar year of each date in a date series.

        This property extracts the calendar year from each date. It does not group periods into twelve-month model
        years; use `Series.sum`, `Series.mean`, `Series.min`, `Series.max`, or `Series.last` with `year=` for those
        reductions.

        Returns
        -------
        Series
            A dimensionless series containing the calendar year for each date.

        Raises
        ------
        TypeError
            At construction, if this series does not have date units.

        See Also
        --------
        boki.Model.date : The model's date at the start of each period.

        Examples
        --------
        Read calendar years from monthly period-start dates:

        >>> import boki as b
        >>> m = b.Model("Calendar", start="2027-01", periods=24, step=b.month)
        >>> year = m.date.year
        >>> r = m.render()
        >>> [r.value(year, period) for period in ("2027-01", "2028-01")]
        [2027, 2028]
        """  # noqa: DOC502
        return _date_part(self, _year_of, "year")

    @property
    def month(self) -> "Series":
        """Calendar month, 1 to 12, of each date in a date series.

        Returns
        -------
        Series
            A dimensionless series containing the calendar month of each date. Excel writes it as ``MONTH``.

        Raises
        ------
        TypeError
            At construction, if this series does not have date units.

        See Also
        --------
        boki.Series.year : Calendar year of each date.
        boki.Model.date : The model's date at the start of each period.

        Examples
        --------
        Read the calendar month of each monthly period, for example to apply a seasonal factor:

        >>> import boki as b
        >>> m = b.Model("Season", start="2027-11", periods=4, step=b.month)
        >>> month = m.date.month
        >>> r = m.render()
        >>> r[month]
        [11, 12, 1, 2]
        """  # noqa: DOC502
        return _date_part(self, _month_of, "month")

    def cumsum(self) -> "Series":
        """Return the running total up to and including each period.

        Returns
        -------
        Series
            A series in this series' unit whose value in period ``t`` is the sum of this series from the first period
            to ``t``. A missing value counts as 0. A scalar series adds its value in every period.

        See Also
        --------
        boki.Series.reverse_cumsum : Total from each period to the last.
        boki.Series.sum : One total over all periods.
        boki.Series.lag : The value in an earlier period.

        Examples
        --------
        Accumulate monthly sales:

        >>> import boki as b
        >>> m = b.Model("Running", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> r = m.render()
        >>> r[sales.cumsum()]
        [100, 220, 310]
        """
        return Cumsum(self)

    def reverse_cumsum(self) -> "Series":
        """Return the running total from each period to the last period.

        Returns
        -------
        Series
            A series in this series' unit whose value in period ``t`` is the sum of this series from ``t`` to the
            last period, that is, what is still ahead. A missing value counts as 0.

        See Also
        --------
        boki.Series.cumsum : Total from the first period to each period.

        Examples
        --------
        Remaining sales after each month:

        >>> import boki as b
        >>> m = b.Model("Ahead", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> r = m.render()
        >>> r[sales.reverse_cumsum()]
        [310, 210, 90]
        """
        return ReverseCumsum(self)

    def spread(self, kernel) -> "Series":
        """Spread each period's value over later periods with a kernel.

        The result in period ``t`` is the sum over earlier or equal periods ``s`` of ``kernel.weights[t - s]`` times
        this series' value in ``s``. Use it for payment delays, prepayments recognized over time, and ramps. The
        period is the unit of the weights, whatever its length in months.

        Parameters
        ----------
        kernel : Kernel
            Weights by periods elapsed, from `boki.delay`, `boki.even`, `boki.curve` or `boki.mix`. A period beyond
            the weights receives nothing, except that a `boki.curve` keeps applying its last weight.

        Returns
        -------
        Series
            A series in this series' unit. A missing value counts as 0.

        See Also
        --------
        boki.Series.lag : Shift the whole series instead of spreading it.

        Examples
        --------
        Collect sales one month after they are made, or spread each month's sales evenly over two months:

        >>> import boki as b
        >>> m = b.Model("Collections", start="2027-01", periods=3, step=b.month)
        >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
        >>> r = m.render()
        >>> r[sales.spread(b.delay(1))]
        [0.0, 100.0, 120.0]
        >>> r[sales.spread(b.even(2))]
        [50.0, 110.0, 105.0]
        """  # noqa: DOC105, DOC106, DOC107
        from .shapes import spread
        return spread(self, kernel)

    # ---- arithmetic -------------------------------------------------------------
    @_operator(
        "Add another series, quantity, or number to this series, period by period.",
        other="The addend. A plain number is a dimensionless constant, except a literal 0, which takes any unit. A "
              "`Quantity` such as ``100 * USD`` is a constant with its unit.",
        returns="The sum in each period. It is scalar only when both operands are scalar, and has the operands' "
                "common unit.",
        raises=(("UnitError", _UNIT_CONFLICT), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__radd__", "Add when this series is the right operand."),
                  ("boki.Series.__sub__", "Subtract instead of add.")),
        notes="A missing value (``None``) in either operand makes the sum missing in that period.\n\n"
              "When this series is a date series (``m.date``, ``m.period_end``), the sum shifts each date later. A "
              "time in months, or a plain number read as months, moves it by that many months and clamps the day to "
              "the end of a shorter month, as Excel's EDATE does. A time in days (``14 * b.day``) moves it by days. "
              "The result is a date series.",
        examples="""
            Add a one-off bonus to a base amount with units; a plain number would be a unit error:

            >>> import boki as b
            >>> from boki.units import USD
            >>> m = b.Model("Add", start="2027-01", periods=2, step=b.month)
            >>> base = m.series("Base", 100 * USD)
            >>> bonus = m.series("Bonus", data={1: 20 * USD})
            >>> r = m.render()
            >>> r[base + bonus]
            [100.0, 120.0]
            >>> base + 5  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
                ...
            boki.units.UnitError: cannot add Base (USD) and 5 dimensionless

            Shift period-start dates by two months:

            >>> r[m.date + 2 * b.month]
            [datetime.date(2027, 3, 1), datetime.date(2027, 4, 1)]
        """,
    )
    def __add__(self, other): return Op(operator.add, self, other)

    @_operator(
        "Add this series to a number or quantity on the left, period by period.",
        other="The left operand: a number or a `Quantity` such as ``100 * USD``. A plain number is a dimensionless "
              "constant, except a literal 0, which takes any unit.",
        returns="The sum in each period, with the operands' common unit.",
        raises=(("UnitError", _UNIT_CONFLICT), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__add__", "Add when this series is the left operand."),),
        examples="""
            Python calls this for ``number + series``:

            >>> import boki as b
            >>> m = b.Model("Add", start="2027-01", periods=2, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120})
            >>> r = m.render()
            >>> r[10 + sales]
            [110, 130]
        """,
    )
    def __radd__(self, other): return Op(operator.add, other, self)

    @_operator(
        "Subtract another series, quantity, or number from this series, period by period.",
        other="The subtrahend. A plain number is a dimensionless constant, except a literal 0, which takes any unit. "
              "A `Quantity` such as ``100 * USD`` is a constant with its unit.",
        returns="The difference in each period. It is scalar only when both operands are scalar, and has the "
                "operands' common unit, except that a date minus a date is a number of days.",
        raises=(("UnitError", _UNIT_CONFLICT), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__rsub__", "Subtract when this series is the right operand."),
                  ("boki.Series.__add__", "Add instead of subtract.")),
        notes="A missing value (``None``) in either operand makes the difference missing in that period.\n\n"
              "When this series is a date series, the difference moves each date earlier: by a time in months (or a "
              "plain number read as months, clamping the day as Excel's EDATE does), or by a time in days. A date "
              "series minus another date series is the number of days between them, in the unit ``b.day``.",
        examples="""
            Subtract a cost from revenue:

            >>> import boki as b
            >>> m = b.Model("Margin", start="2027-01", periods=2, step=b.month)
            >>> revenue = m.series("Revenue", data={0: 100, 1: 120})
            >>> cost = m.series("Cost", data={0: 60, 1: 70})
            >>> r = m.render()
            >>> r[revenue - cost]
            [40, 50]

            The days in each period are the period end minus its start; the last day is the end minus one day:

            >>> r[m.period_end - m.date]
            [31, 28]
            >>> r[m.period_end - 1 * b.day]
            [datetime.date(2027, 1, 31), datetime.date(2027, 2, 28)]
        """,
    )
    def __sub__(self, other): return Op(operator.sub, self, other)

    @_operator(
        "Subtract this series from a number or quantity on the left, period by period.",
        other="The minuend: a number or a `Quantity` such as ``100 * USD``. A plain number is a dimensionless "
              "constant, except a literal 0, which takes any unit.",
        returns="The difference in each period, with the operands' common unit.",
        raises=(("UnitError", _UNIT_CONFLICT), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__sub__", "Subtract when this series is the left operand."),),
        examples="""
            Python calls this for ``number - series``:

            >>> import boki as b
            >>> m = b.Model("Left", start="2027-01", periods=2, step=b.month)
            >>> used = m.series("Used", data={0: 30, 1: 45})
            >>> r = m.render()
            >>> r[100 - used]
            [70, 55]
        """,
    )
    def __rsub__(self, other): return Op(operator.sub, other, self)

    @_operator(
        "Multiply this series by another series, quantity, or number, period by period.",
        other="The factor. A plain number is dimensionless, and a `Quantity` such as ``3000 * JPY`` is a constant with "
              "its unit.",
        returns="The product in each period. It is scalar only when both operands are scalar. Its unit is the product "
                "of the operands' units (JPY times a plain number is JPY; JPY per month times months is JPY); it is "
                "unknown if either unit is unknown.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__truediv__", "Divide instead of multiply."),),
        notes="A missing value (``None``) in either operand makes the product missing in that period.\n\n"
              "A series in a rate per time is not integrated by the period length automatically. Multiply it by "
              "``m.period_length`` (a series of months in each period) to get the amount in each period.",
        examples="""
            Price times volume in a monthly model; the unit of the revenue is the price's currency:

            >>> import boki as b
            >>> from boki.units import JPY
            >>> m = b.Model("Revenue", start="2027-01", periods=2, step=b.month)
            >>> price = m.series("Price", 3000 * JPY)
            >>> volume = m.series("Volume", data={0: 10, 1: 12})
            >>> revenue = price * volume
            >>> r = m.render()
            >>> r[revenue]
            [30000.0, 36000.0]
            >>> revenue.unit == JPY.dims
            True

            A fee per month becomes an amount per period with ``m.period_length``, so a quarterly model bills three
            months at once:

            >>> m = b.Model("Fees", start="2027-01", periods=2, step=3 * b.month)
            >>> fee = m.series("Fee", 100 * JPY / b.month)
            >>> r = m.render()
            >>> r[fee * m.period_length]
            [300.0, 300.0]
        """,
    )
    def __mul__(self, other): return Op(operator.mul, self, other)

    @_operator(
        "Multiply a number or quantity on the left by this series, period by period.",
        other="The left factor: a number or a `Quantity` such as ``3000 * JPY``.",
        returns="The product in each period. Its unit is the product of the operands' units, and unknown if either "
                "unit is unknown.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__mul__", "Multiply when this series is the left operand."),),
        examples="""
            Python calls this for ``number * series``:

            >>> import boki as b
            >>> m = b.Model("Scale", start="2027-01", periods=2, step=b.month)
            >>> units = m.series("Units", data={0: 10, 1: 12})
            >>> r = m.render()
            >>> r[3 * units]
            [30, 36]
        """,
    )
    def __rmul__(self, other): return Op(operator.mul, other, self)

    @_operator(
        "Divide this series by another series, quantity, or number, period by period.",
        other="The divisor. A plain number is dimensionless, and a `Quantity` such as ``100 * USD`` is a constant with "
              "its unit.",
        returns="The quotient in each period. It is scalar only when both operands are scalar. Its unit is the "
                "quotient of the operands' units, so two series in the same unit give a dimensionless ratio; it is "
                "unknown if either unit is unknown.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if the divisor is 0 in a period.")),
        see_also=(("boki.Series.__floordiv__", "Divide and round down."),
                  ("boki.Series.__mul__", "Multiply instead of divide.")),
        notes="A missing value (``None``) in either operand makes the quotient missing in that period. Dividing by a "
              "series that is 0 raises; guard it with ``Series.where`` on the divisor.",
        examples="""
            A margin is profit divided by revenue; both are in the same currency, so the ratio is dimensionless:

            >>> import boki as b
            >>> from boki.units import USD
            >>> m = b.Model("Ratio", start="2027-01", periods=2, step=b.month)
            >>> revenue = m.series("Revenue", data={0: 100 * USD, 1: 200 * USD})
            >>> profit = m.series("Profit", data={0: 20 * USD, 1: 50 * USD})
            >>> margin = profit / revenue
            >>> r = m.render()
            >>> r[margin]
            [0.2, 0.25]
        """,
    )
    def __truediv__(self, other): return Op(operator.truediv, self, other)

    @_operator(
        "Divide a number or quantity on the left by this series, period by period.",
        other="The dividend: a number or a `Quantity` such as ``100 * USD``.",
        returns="The quotient in each period. Its unit is the quotient of the operands' units, and unknown if either "
                "unit is unknown.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if this series is 0 in a period.")),
        see_also=(("boki.Series.__truediv__", "Divide when this series is the left operand."),),
        examples="""
            Python calls this for ``number / series``; units per customer, for example:

            >>> import boki as b
            >>> m = b.Model("Per unit", start="2027-01", periods=2, step=b.month)
            >>> units = m.series("Units", data={0: 10, 1: 20})
            >>> r = m.render()
            >>> r[100 / units]
            [10.0, 5.0]
        """,
    )
    def __rtruediv__(self, other): return Op(operator.truediv, other, self)

    @_operator(
        "Return the remainder of dividing this series by another, period by period.",
        other="The divisor. Its unit must match this series' unit (a literal 0 and an unknown unit never conflict). "
              "The remainder has the sign of the divisor.",
        returns="The remainder in each period, in the operands' common unit. It is scalar only when both operands are "
                "scalar.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if the divisor is 0 in a period.")),
        see_also=(("boki.mod", "The same operation as a function."),
                  ("boki.Series.__floordiv__", "The whole number of times the divisor fits.")),
        notes="Python's ``%`` and Excel's ``MOD`` agree: the result takes the sign of the divisor.",
        examples="""
            A cycle of three positions from the period index:

            >>> import boki as b
            >>> m = b.Model("Cycle", start="2027-01", periods=4, step=b.month)
            >>> r = m.render()
            >>> r[m.t % 3]
            [0, 1, 2, 0]
        """,
    )
    def __mod__(self, other): return Op(operator.mod, self, other)

    @_operator(
        "Return the remainder of dividing a number or quantity on the left by this series.",
        other="The dividend: a number or a `Quantity`. Its unit must match this series' unit.",
        returns="The remainder in each period, with the sign of this series.",
        raises=(("UnitError", "At construction, if the operands have different units."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if this series is 0 in a period.")),
        see_also=(("boki.Series.__mod__", "Remainder when this series is the dividend."),),
        examples="""
            Python calls this for ``number % series``:

            >>> import boki as b
            >>> m = b.Model("Cycle", start="2027-01", periods=3, step=b.month)
            >>> size = m.series("Size", data={0: 4, 1: 5, 2: 6})
            >>> r = m.render()
            >>> r[17 % size]
            [1, 2, 5]
        """,
    )
    def __rmod__(self, other): return Op(operator.mod, other, self)

    @_operator(
        "Divide this series by another and round down to a whole number, period by period.",
        other="The divisor. A plain number is dimensionless, and a `Quantity` is a constant with its unit.",
        returns="The quotient rounded toward negative infinity. It is scalar only when both operands are scalar. Its "
                "unit is the quotient of the operands' units, and unknown if either unit is unknown.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if the divisor is 0 in a period.")),
        see_also=(("boki.Series.__mod__", "The remainder."), ("boki.floor", "Round a series down to a whole number.")),
        notes="Excel writes it as ``INT(x/n)``.",
        examples="""
            The model year (0 for the first twelve months) of a monthly period index:

            >>> import boki as b
            >>> m = b.Model("Years", start="2027-01", periods=24, step=b.month)
            >>> r = m.render()
            >>> [r.value(m.t // 12, period) for period in ("2027-12", "2028-01")]
            [0, 1]
        """,
    )
    def __floordiv__(self, other): return Op(operator.floordiv, self, other)

    @_operator(
        "Divide a number or quantity on the left by this series and round down to a whole number.",
        other="The dividend: a number or a `Quantity`.",
        returns="The quotient rounded toward negative infinity. Its unit is the quotient of the operands' units.",
        raises=(("UnitError", "At construction, if the units combine months and days, which do not convert at a "
                              "fixed rate."), ("TypeError", _UNSUPPORTED),
                ("ZeroDivisionError", "At evaluation, if this series is 0 in a period.")),
        see_also=(("boki.Series.__floordiv__", "Round down when this series is the dividend."),),
        examples="""
            Python calls this for ``number // series``; how many whole lots of each size fit in 100:

            >>> import boki as b
            >>> m = b.Model("Lots", start="2027-01", periods=2, step=b.month)
            >>> size = m.series("Size", data={0: 30, 1: 40})
            >>> r = m.render()
            >>> r[100 // size]
            [3, 2]
        """,
    )
    def __rfloordiv__(self, other): return Op(operator.floordiv, other, self)

    @_operator(
        "Raise this series to a power, period by period.",
        other="The exponent. A literal whole number keeps a series with a unit valid (``x ** 2`` is square USD); any "
              "other exponent needs a dimensionless base.",
        returns="The power in each period. It is scalar only when both operands are scalar. With a literal "
                "whole-number exponent, the unit is the base's unit raised to it; otherwise the result is "
                "dimensionless.",
        raises=(("UnitError", "At construction, if a series with a unit is raised to anything but a literal whole "
                              "number."), ("TypeError", _UNSUPPORTED),
                ("ValueError", "At evaluation, if a negative base is raised to a non-integer power, which has no real "
                               "value."),
                ("ZeroDivisionError", "At evaluation, if 0 is raised to a negative power.")),
        see_also=(("boki.Series.__rpow__", "Raise a number to this series."),),
        notes="A missing value (``None``) in either operand makes the result missing in that period.",
        examples="""
            Compound a monthly growth rate of 1% over the periods; the exponent is a per-period count:

            >>> import boki as b
            >>> m = b.Model("Growth", start="2027-01", periods=3, step=b.month)
            >>> growth = m.series("Growth", 1 + 0.01)
            >>> r = m.render()
            >>> r[growth ** m.t]
            [1.0, 1.01, 1.0201]
        """,
    )
    def __pow__(self, other): return Op(operator.pow, self, other)

    @_operator(
        "Raise a number on the left to the power of this series, period by period.",
        other="The base: a plain number.",
        other_type="number",
        returns="The power in each period; a dimensionless series.",
        raises=(("TypeError", _UNSUPPORTED),
                ("ValueError", "At evaluation, if a negative base is raised to a non-integer power."),
                ("ZeroDivisionError", "At evaluation, if 0 is raised to a negative power.")),
        see_also=(("boki.Series.__pow__", "Raise this series to a power."),),
        examples="""
            Python calls this for ``number ** series``; a doubling every period:

            >>> import boki as b
            >>> m = b.Model("Doubling", start="2027-01", periods=3, step=b.month)
            >>> r = m.render()
            >>> r[2 ** m.t]
            [1, 2, 4]
        """,
    )
    def __rpow__(self, other): return Op(operator.pow, other, self)

    @_operator(
        "Negate this series, period by period.",
        returns="The negated series, in this series' unit. A missing value stays missing.",
        see_also=(("boki.Series.__abs__", "Absolute value."),),
        examples="""
            >>> import boki as b
            >>> m = b.Model("Negate", start="2027-01", periods=2, step=b.month)
            >>> cost = m.series("Cost", data={0: 60, 1: 70})
            >>> r = m.render()
            >>> r[-cost]
            [-60, -70]
        """,
    )
    def __neg__(self): return Op(operator.neg, self)

    @_operator(
        "Return the absolute value of this series, period by period.",
        returns="The absolute value, in this series' unit. A missing value stays missing.",
        see_also=(("boki.Series.__neg__", "Negate a series."),),
        examples="""
            >>> import boki as b
            >>> m = b.Model("Gap", start="2027-01", periods=2, step=b.month)
            >>> gap = m.series("Gap", data={0: -5, 1: 8})
            >>> r = m.render()
            >>> r[abs(gap)]
            [5, 8]
        """,
    )
    def __abs__(self): return Op(operator.abs, self)

    @_operator(
        "Compare this series with another value: less than, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where this series is less than ``other``. It is "
                "scalar only when both operands are scalar. A missing value in either operand makes the result "
                "missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.where", "Choose values with a condition."),
                  ("boki.Model.check", "State a condition that must hold in every period.")),
        notes="The result is a series, not a Python bool. Use it in ``Series.where``, combine it with ``&``, ``|`` and "
              "``~``, or pass it to ``Model.check``. Writing ``100 < x`` calls ``x > 100``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Compare", start="2027-01", periods=3, step=b.month)
            >>> cash = m.series("Cash", data={0: 50, 1: -20, 2: 30})
            >>> r = m.render()
            >>> r[cash < 0]
            [False, True, False]
        """,
    )
    def __lt__(self, other): return Op(operator.lt, self, other)

    @_operator(
        "Compare this series with another value: less than or equal, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where this series is at most ``other``. It is "
                "scalar only when both operands are scalar. A missing value in either operand makes the result "
                "missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__ge__", "Greater than or equal."),),
        notes="The result is a series, not a Python bool; see ``Series.__lt__``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Compare", start="2027-01", periods=3, step=b.month)
            >>> cash = m.series("Cash", data={0: 50, 1: 0, 2: 30})
            >>> r = m.render()
            >>> r[cash <= 0]
            [False, True, False]
        """,
    )
    def __le__(self, other): return Op(operator.le, self, other)

    @_operator(
        "Compare this series with another value: greater than, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where this series is greater than ``other``. It is "
                "scalar only when both operands are scalar. A missing value in either operand makes the result "
                "missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__lt__", "Less than."),),
        notes="The result is a series, not a Python bool; see ``Series.__lt__``. Dates compare with dates: "
              "``m.date > date(2027, 6, 1)`` is true from the first period that starts after that day.",
        examples="""
            Switch a cost on once sales pass a threshold:

            >>> import boki as b
            >>> m = b.Model("Compare", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
            >>> r = m.render()
            >>> r[sales > 100]
            [False, True, False]
        """,
    )
    def __gt__(self, other): return Op(operator.gt, self, other)

    @_operator(
        "Compare this series with another value: greater than or equal, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where this series is at least ``other``. It is "
                "scalar only when both operands are scalar. A missing value in either operand makes the result "
                "missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__le__", "Less than or equal."), ("boki.Model.check", "State a condition that must "
                  "hold in every period.")),
        notes="The result is a series, not a Python bool; see ``Series.__lt__``.",
        examples="""
            A covenant that cash stays at or above a floor, read period by period:

            >>> import boki as b
            >>> from boki.units import USD
            >>> m = b.Model("Floor", start="2027-01", periods=3, step=b.month)
            >>> cash = m.series("Cash", data={0: 50 * USD, 1: 10 * USD, 2: 30 * USD})
            >>> r = m.render()
            >>> r[cash >= 20 * USD]
            [True, False, True]
        """,
    )
    def __ge__(self, other): return Op(operator.ge, self, other)

    @_operator(
        "Build the condition that this series equals another value, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where the values are equal. It is scalar only when "
                "both operands are scalar. A missing value in either operand makes the result missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__ne__", "Not equal."),),
        notes="``==`` builds a series; it does not tell whether two names refer to the same series. Use ``is`` for "
              "that. A series is hashed by identity, so it works as a dictionary key. The equation form "
              "``Model.solve(u, u == expression)`` also uses it.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Equal", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 100})
            >>> r = m.render()
            >>> r[sales == 100]
            [True, False, True]
        """,
    )
    def __eq__(self, other):  # type: ignore[override]
        return Op(operator.eq, self, other)

    @_operator(
        "Build the condition that this series differs from another value, period by period.",
        other=_COMPARE_OTHER,
        returns="A dimensionless series that is true in the periods where the values differ. It is scalar only when "
                "both operands are scalar. A missing value in either operand makes the result missing.",
        raises=(("UnitError", "At construction, if the operands have different units, such as a plain number and a "
                              "series in USD."), ("TypeError", _UNSUPPORTED)),
        see_also=(("boki.Series.__eq__", "Equal."),),
        notes="The result is a series, not a Python bool; see ``Series.__eq__``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Differ", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 100})
            >>> r = m.render()
            >>> r[sales != 100]
            [False, True, False]
        """,
    )
    def __ne__(self, other):  # type: ignore[override]
        return Op(operator.ne, self, other)

    @_operator(
        "Combine two conditions with logical and, period by period.",
        other="The other condition: a series, usually a comparison, or a bool.",
        other_type="Series or bool",
        returns="A dimensionless series that is true where both conditions are true. A missing value in either "
                "operand makes the result missing.",
        raises=(("TypeError", _UNSUPPORTED),),
        see_also=(("boki.Series.__or__", "Logical or."), ("boki.Series.__invert__", "Logical not.")),
        notes="Python's ``and`` cannot be used on a series; it raises ``TypeError``. ``&`` binds tighter than a "
              "comparison, so write each comparison in parentheses: ``(a > 0) & (b > 0)``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("And", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
            >>> r = m.render()
            >>> r[(sales > 95) & (sales < 110)]
            [True, False, False]
        """,
    )
    def __and__(self, other): return Op(_and, self, other)

    @_operator(
        "Combine a condition on the left with this series using logical and.",
        other="The left condition: a bool or a series.",
        other_type="Series or bool",
        returns="A dimensionless series that is true where both conditions are true.",
        raises=(("TypeError", _UNSUPPORTED),),
        see_also=(("boki.Series.__and__", "Logical and when this series is the left operand."),),
        examples="""
            Python calls this for ``bool & series``:

            >>> import boki as b
            >>> m = b.Model("And", start="2027-01", periods=2, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120})
            >>> r = m.render()
            >>> r[True & (sales > 110)]
            [False, True]
        """,
    )
    def __rand__(self, other): return Op(_and, other, self)

    @_operator(
        "Combine two conditions with logical or, period by period.",
        other="The other condition: a series, usually a comparison, or a bool.",
        other_type="Series or bool",
        returns="A dimensionless series that is true where either condition is true. A missing value in either "
                "operand makes the result missing.",
        raises=(("TypeError", _UNSUPPORTED),),
        see_also=(("boki.Series.__and__", "Logical and."), ("boki.Series.__invert__", "Logical not.")),
        notes="Python's ``or`` cannot be used on a series; it raises ``TypeError``. ``|`` binds tighter than a "
              "comparison, so write each comparison in parentheses: ``(a > 0) | (b > 0)``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Or", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
            >>> r = m.render()
            >>> r[(sales > 110) | (sales < 95)]
            [False, True, True]
        """,
    )
    def __or__(self, other): return Op(_or, self, other)

    @_operator(
        "Combine a condition on the left with this series using logical or.",
        other="The left condition: a bool or a series.",
        other_type="Series or bool",
        returns="A dimensionless series that is true where either condition is true.",
        raises=(("TypeError", _UNSUPPORTED),),
        see_also=(("boki.Series.__or__", "Logical or when this series is the left operand."),),
        examples="""
            Python calls this for ``bool | series``:

            >>> import boki as b
            >>> m = b.Model("Or", start="2027-01", periods=2, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120})
            >>> r = m.render()
            >>> r[False | (sales > 110)]
            [False, True]
        """,
    )
    def __ror__(self, other): return Op(_or, other, self)

    @_operator(
        "Negate a condition with logical not, period by period.",
        returns="A dimensionless series that is true where this series is false. A missing value stays missing.",
        see_also=(("boki.Series.__and__", "Logical and."), ("boki.Series.__or__", "Logical or.")),
        notes="Python's ``not`` cannot be used on a series; it raises ``TypeError``. Write ``~(a > 0)``.",
        examples="""
            >>> import boki as b
            >>> m = b.Model("Not", start="2027-01", periods=3, step=b.month)
            >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 90})
            >>> r = m.render()
            >>> r[~(sales > 95)]
            [False, False, True]
        """,
    )
    def __invert__(self): return Op(_not, self)

    # Hash by identity so series can be dict keys. CPython compares full hashes before
    # calling __eq__, so distinct series never reach the lazy __eq__ inside a dict.
    __hash__ = object.__hash__


def lift(x: Any) -> Series:
    """Wrap a plain value as a constant node. An object we do not understand is an error,
    not an unknown-unit constant, so a typo cannot silently switch off unit checks."""
    if isinstance(x, Series):
        return x
    if isinstance(x, Quantity):
        c = Const(x.value, x.dims)
        c.shown = getattr(x, "shown", None)
        return c
    if isinstance(x, Unit):
        return Const(x.scale, x.dims)
    if isinstance(x, date):
        return Const(x, DATE)
    if x is None:
        return Const(None, None)
    if isinstance(x, bool):
        return Const(x, _DIMENSIONLESS)
    if isinstance(x, (int, float)):
        return Const(x, _DIMENSIONLESS, literal=True)
    if isinstance(x, str):
        return Const(x, None)
    raise TypeError(f"cannot use {x!r} ({type(x).__name__}) in a series expression")


def written_unit(node: Series) -> Unit | None:
    """The unit the modeler chose for a series: display= if given, else the unit a quantity literal was
    written in (`400 * MWh`), looking through named series (`m.series("x", 400 * MWh)`). None for a computed
    series, which has no unit of its own choosing."""
    seen = node
    while True:
        if seen.display is not None:
            return seen.display
        if isinstance(seen, Named) and seen.expr is not None:
            seen = seen.expr
            continue
        return getattr(seen, "shown", None) if type(seen).__name__ in ("Const", "Input") else None


def _and(a, b): return bool(a) and bool(b)


def _or(a, b): return bool(a) or bool(b)


def _not(a): return not a


def _sum(vs): return sum(v for v in vs if v is not None)


def _min(vs): return min(v for v in vs if v is not None)


def _mean(vs):
    vs = [v for v in vs if v is not None]
    return sum(vs) / len(vs)


def _max(vs): return max(v for v in vs if v is not None)


def _add_months(d: date, k) -> date:
    from .model import add_months
    return add_months(d, int(round(k)))


def _sub_months(d: date, k) -> date:
    return _add_months(d, -k)


class Const(Series):
    scalar = True

    def __init__(self, value, unit: Dims | None = None, literal: bool = False):
        self.value, self.unit, self.literal = value, unit, literal

    def _eval(self, r, t):
        return self.value

    def __repr__(self):
        return f"<Const {self.value!r}>"


def _wildcard(node: Series) -> bool:
    """A literal 0 or None fits any unit; an unknown unit skips checks."""
    return node.unit is None or (isinstance(node, Const) and node.literal and node.value == 0)


def _unify(nodes: list[Series], what: str) -> Dims | None:
    known = [n for n in nodes if not _wildcard(n)]
    if not known:
        if any(n.unit is None for n in nodes):
            return None                       # an unknown unit stays unknown; a literal 0 does not decide it
        return next((n.unit for n in nodes if n.unit is not None), None)
    first = known[0].unit
    for n in known[1:]:
        if n.unit != first:
            raise UnitError(f"cannot {what} {_who(known[0])} and {_who(n)}")
    return first


def _who(n: Series) -> str:
    """'100,000 USD', 'Capacity (kW)', 'an expression (USD/month)'."""
    from .units import _show
    shown = getattr(n, "shown", None)
    if isinstance(n, Const):
        return _show(n.value, shown, n.unit)
    unit = shown.name if shown is not None else _describe(n.unit)
    return f"{n.name} ({unit})" if n.name else f"an expression in {unit}"


_ADD = {operator.add: "add", operator.sub: "subtract"}
_CMP = {operator.lt, operator.le, operator.gt, operator.ge, operator.eq, operator.ne}



def _days_between(a: date, b: date) -> int:
    return (a - b).days


def _add_days(d: date, n) -> date:
    return d + timedelta(days=n)


def _sub_days(d: date, n) -> date:
    return d - timedelta(days=n)


def _year_of(d: date) -> int:
    return d.year


def _month_of(d: date) -> int:
    return d.month


def _date_part(x: "Series", fn: Callable, name: str) -> "Series":
    if x.unit != DATE:
        raise TypeError(f".{name} needs a date series such as m.date or m.period_end; {_who(x)} is not a date")
    return Op(fn, x, unit=_DIMENSIONLESS)


def _in_year(src, year, kind: str) -> "Series":
    if not isinstance(year, int) or isinstance(year, bool):
        raise TypeError(f"year= takes a model year number from 0 (the first twelve months), got {year!r}")
    from .shapes import _Year
    return _Year(src, year, kind)


class Op(Series):
    def __init__(self, fn: Callable, *args, unit: Dims | None | str = "infer"):
        self.fn = fn
        self.args = [lift(a) for a in args]
        self.scalar = all(a.scalar for a in self.args)
        self.unit = self._infer() if unit == "infer" else unit

    def _infer(self) -> Dims | None:
        fn, a = self.fn, self.args
        if fn in _ADD:
            if a[0].unit == DATE and a[1].unit in (MONTHS, _DIMENSIONLESS):
                self.fn = _add_months if fn is operator.add else _sub_months
                return DATE
            if a[0].unit == DATE and a[1].unit == day.dims:
                self.fn = _add_days if fn is operator.add else _sub_days
                return DATE
            if fn is operator.sub and a[0].unit == DATE and a[1].unit == DATE:
                self.fn = _days_between
                return day.dims
            return _unify(a, _ADD[fn])
        if fn is operator.floordiv:
            if a[0].unit is None or a[1].unit is None:
                return None
            return _combine(a[0].unit, a[1].unit, -1)
        if fn is operator.mod:
            return _unify(a, "take the remainder of")
        if fn in (operator.mul, operator.truediv):
            if a[0].unit is None or a[1].unit is None:
                return None
            return _combine(a[0].unit, a[1].unit, 1 if fn is operator.mul else -1)
        if fn is operator.pow:
            base, exp = a
            if base.unit and isinstance(exp, Const) and isinstance(exp.value, int):
                return frozenset((k, v * exp.value) for k, v in base.unit)
            if base.unit and not _wildcard(base):
                raise UnitError(f"cannot raise {_who(base)} ({_describe(base.unit)}) to a non-integer power")
            return _DIMENSIONLESS
        if fn in _CMP:
            _unify(a, "compare")
            return _DIMENSIONLESS
        if fn in (_and, _or, _not):
            return _DIMENSIONLESS
        return _unify(a, "combine") if len(a) > 1 else a[0].unit

    def _eval(self, r, t):
        vals = [r.value(a, None if a.scalar else t) for a in self.args]
        if any(v is None for v in vals):
            return None
        v = self.fn(*vals)
        if isinstance(v, complex):     # a negative number to a non-integer power: Excel's #NUM!, not a complex value
            raise ValueError(f"{vals[0]!r} ** {vals[1]!r} has no real value (a negative base to a non-integer power)")
        return v


class Lag(Series):
    def __init__(self, src: Series, k, fill):
        if isinstance(fill, (list, tuple, dict)):
            raise TypeError("lag(fill=) takes one value or a series; for history before the first period use "
                            "fill=b.by_year({...}) or another series")
        self.src, self.k, self.fill = src, lift(k), fill
        self.unit = src.unit

    def _eval(self, r, t):
        s = t - int(r.value(self.k, None if self.k.scalar else t))
        if 0 <= s < r.n:
            return r.value(self.src, None if self.src.scalar else s)
        if isinstance(self.fill, Series):
            return r.value(self.fill, None if self.fill.scalar else t)
        return self.fill.value if isinstance(self.fill, Quantity) else self.fill


class Where(Series):
    def __init__(self, cond, then, else_):
        self.cond, self.then, self.else_ = lift(cond), lift(then), lift(else_)
        self.scalar = self.cond.scalar and self.then.scalar and self.else_.scalar
        self.unit = _unify([self.then, self.else_], "choose between")

    def _eval(self, r, t):
        c = r.value(self.cond, None if self.cond.scalar else t)
        branch = self.then if c else self.else_
        return r.value(branch, None if branch.scalar else t)


class At(Series):
    """The value of a series at one period, as a scalar node."""
    scalar = True

    def __init__(self, src: Series, t):
        self.src, self.t = src, t
        self.unit = src.unit

    def _eval(self, r, _):
        return r.value(self.src, None if self.src.scalar else r.period_index(self.t))


class Reduce(Series):
    """A scalar computed from the whole series (sum, min, npv, irr ...)."""
    scalar = True

    def __init__(self, fn: Callable, *srcs, unit: Dims | None = None, excel: Callable | None = None,
                 excel_guess: bool = False, excel_first: tuple[int, ...] = ()):
        self.fn = fn
        self.srcs = [lift(s) for s in srcs]
        self.unit = unit
        self.excel = excel   # formula from the sources (a range for a series, an expression for a scalar)
        self.excel_guess = excel_guess   # the formula also takes boki's value, as the starting guess of a root search
        self.excel_first = excel_first   # sources the formula reads from their first period, not as a range

    def _eval(self, r, _):
        return self.fn(*[r.values(s) for s in self.srcs])


class Cumsum(Series):
    def __init__(self, src):
        self.src = lift(src)
        self.unit = self.src.unit

    def _eval(self, r, t):
        prev = r.value(self, t - 1) if t > 0 else 0
        v = r.value(self.src, None if self.src.scalar else t)
        return prev + (v or 0)


class ReverseCumsum(Series):
    def __init__(self, src):
        self.src = lift(src)
        self.unit = self.src.unit

    def _eval(self, r, t):
        rest = r.value(self, t + 1) if t + 1 < r.n else 0
        v = r.value(self.src, None if self.src.scalar else t)
        return rest + (v or 0)


class Fn(Series):
    """A per-period Python function (the @m.series form). Reads others with x[t]."""

    def __init__(self, fn: Callable[[int], Any], name: str | None = None, unit: Dims | None = None):
        self.fn = fn
        self.name = name or fn.__name__
        self.unit = unit

    def _eval(self, r, t):
        v = self.fn(t)
        while isinstance(v, Series):
            v = r.value(v, None if v.scalar else t)
        if isinstance(v, Quantity):
            if self.unit is not None and v.dims != self.unit and v.value != 0:
                raise UnitError(f"{self.name}[{t}] returned {_describe(v.dims)}, declared {_describe(self.unit)}")
            v = v.value
        return v


class Named(Series):
    """Named series that can be declared first and defined later.

    `Model.series` returns a `Named` for ``m.series("x", expr)``, and for ``m.series("x")`` followed by
    `Named.define`. Declare first and define later when two series refer to each other: Python runs top to bottom,
    so the name must exist before the expression that uses it. A `Named` supports everything a `Series` does, and
    tables and the Excel output label its values with its name. Create one with `Model.series`, not directly.

    Parameters
    ----------
    name : str | None
        Name the series is registered under, or ``None`` for an unnamed series.
    expr : Series | None
        The expression, a series or anything that becomes one (a number, a `Quantity`). Leave it out, the default, to
        declare the series and call `Named.define` later.
    unit : Dims | None
        Dimensions the series must have, as a frozenset of ``(base unit name, exponent)`` pairs such as ``JPY.dims``;
        `Model.series` takes the unit itself (``unit=JPY``). When given, the expression must have these dimensions.
        The default takes the expression's.

    See Also
    --------
    boki.Model.series : Create a named series, with an expression or declared for later.
    boki.model.Input : A named assumption with a default, scenarios and choices.

    Notes
    -----
    A series that was declared but never defined raises ``ValueError`` when it is evaluated. See the `series guide
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#series>`_ for forward declarations.

    Examples
    --------
    Declare a funding need, use it, then define it once its parts exist:

    >>> import boki as b
    >>> m = b.Model("Funding", start="2027-01", periods=2, step=b.month)
    >>> need = m.series("Need")
    >>> share = m.series("Share", need * 0.5)
    >>> _ = need.define(200)
    >>> m.render()[share]
    [100.0, 100.0]
    """

    def __init__(self, name: str | None, expr: Series | None = None, unit: Dims | None = None):
        self.name = name
        self.expr = None
        self.unit = unit
        if expr is not None:
            self.define(expr)

    def define(self, expr) -> "Named":
        """Set the expression of a series that was declared without one.

        Parameters
        ----------
        expr : Series, Quantity, or number
            The expression, in the series' unit. If the series was declared with a unit (``unit=`` in
            `Model.series`), the expression must have that unit; a literal 0 fits any unit. Otherwise the series
            takes the expression's unit.

        Returns
        -------
        Named
            This series, so a definition can be chained.

        Raises
        ------
        ValueError
            At construction, if the series is already defined. At evaluation, if it is read while still undefined.
        UnitError
            At construction, if the declared unit and the expression's unit differ.
        TypeError
            At construction, if ``expr`` has a type a series expression cannot use, such as a list.

        See Also
        --------
        boki.Model.series : Create a series, declared or with its expression.

        Examples
        --------
        Declare two series that refer to each other, then close the loop with a lag:

        >>> import boki as b
        >>> m = b.Model("Loop", start="2027-01", periods=3, step=b.month)
        >>> cash = m.series("Cash")
        >>> interest = m.series("Interest", cash.lag(1, fill=1000) * 0.01)
        >>> _ = cash.define(cash.lag(1, fill=1000) + interest)
        >>> r = m.render()
        >>> [round(v, 2) for v in r[cash]]
        [1010.0, 1020.1, 1030.3]
        """  # noqa: DOC105, DOC106, DOC107, DOC503
        if self.expr is not None:
            raise ValueError(f"series {self.name!r} is already defined")
        expr = lift(expr)
        if self.unit is not None and not _wildcard(expr) and expr.unit != self.unit:
            raise UnitError(f"{self.name!r} is declared in {_describe(self.unit)} but defined in {_describe(expr.unit)}")
        self.expr = expr
        self.scalar = expr.scalar
        self.unit = self.unit if self.unit is not None else expr.unit
        return self

    def _eval(self, r, t):
        if self.expr is None:
            raise ValueError(f"series {self.name!r} was declared but never defined")
        return r.value(self.expr, None if self.expr.scalar else t)


class Data(Series):
    """Values at a few periods, 0 elsewhere."""

    def __init__(self, points: dict, name: str | None = None):
        self.site = _site()
        self.name = name
        nodes = {k: lift(v) for k, v in points.items()}
        self.unit = _unify(list(nodes.values()), "mix") if nodes else None
        self.points = nodes

    def _eval(self, r, t):
        return r.sparse(self).get(t, 0)

    def define(self, expr):
        raise TypeError(f"{self.name or 'this series'!r} holds fixed data= values and cannot be defined. To add data to "
                        "a recurrence, name the data and use it in the definition: x = m.series(\"x\"); "
                        "x.define(x.lag(1, fill=...) + m.series(\"x data\", data={...}))")


def _vmin(*v):
    return min(v)


def _vmax(*v):
    return max(v)


def smin(*xs) -> Series:
    """Return the smallest of several series, numbers or quantities in each period.

    This compares the arguments period by period. To find the smallest value of one series across the periods, use
    `Series.min`.

    Parameters
    ----------
    *xs : Series, Quantity, or number
        The values to compare. A plain number is a dimensionless constant, except a literal 0, which takes any
        unit. All arguments must have the same unit.

    Returns
    -------
    Series
        In each period, the smallest argument. A missing value in any argument makes the result missing. Its unit
        is the arguments' common unit.

    Raises
    ------
    UnitError
        At construction, if the arguments have different units.
    TypeError
        At construction, if an argument has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.max : Largest of several series in each period.
    boki.Series.min : Smallest value of one series across the periods.

    Examples
    --------
    Cap a repayment at the balance outstanding in each month:

    >>> import boki as b
    >>> m = b.Model("Cap", start="2027-01", periods=3, step=b.month)
    >>> due = m.series("Due", data={0: 100, 1: 40, 2: 70})
    >>> balance = m.series("Balance", data={0: 60, 1: 90, 2: 70})
    >>> r = m.render()
    >>> r[b.min(due, balance)]
    [60, 40, 70]
    """  # noqa: DOC105, DOC106, DOC502
    return Op(_vmin, *xs)


def smax(*xs) -> Series:
    """Return the largest of several series, numbers or quantities in each period.

    This compares the arguments period by period. To find the largest value of one series across the periods, use
    `Series.max`.

    Parameters
    ----------
    *xs : Series, Quantity, or number
        The values to compare. A plain number is a dimensionless constant, except a literal 0, which takes any
        unit. All arguments must have the same unit.

    Returns
    -------
    Series
        In each period, the largest argument. A missing value in any argument makes the result missing. Its unit is
        the arguments' common unit.

    Raises
    ------
    UnitError
        At construction, if the arguments have different units.
    TypeError
        At construction, if an argument has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.min : Smallest of several series in each period.
    boki.Series.max : Largest value of one series across the periods.

    Examples
    --------
    Floor a taxable profit at zero in each month:

    >>> import boki as b
    >>> from boki.units import USD
    >>> m = b.Model("Floor", start="2027-01", periods=3, step=b.month)
    >>> profit = m.series("Profit", data={0: 50 * USD, 1: -20 * USD, 2: 30 * USD})
    >>> r = m.render()
    >>> r[b.max(profit, 0 * USD)]
    [50.0, 0.0, 30.0]
    """  # noqa: DOC105, DOC106, DOC502
    return Op(_vmax, *xs)


def _round_half_up(v):
    # Excel's ROUND rounds halves away from zero; Python's round() rounds them to even.
    return math.copysign(math.floor(abs(v) + 0.5), v)


def _decimal_round(mode):
    def fn(v, digits):
        # through the decimal the value prints as, so 2.675 rounds to 2.68 as in Excel, not to 2.67
        q = Decimal(1).scaleb(-int(digits))
        return float(Decimal(repr(v)).quantize(q, rounding=mode))
    return fn


_round_digits = _decimal_round(ROUND_HALF_UP)
_round_down = _decimal_round(ROUND_DOWN)
_round_up = _decimal_round(ROUND_UP)


def sround(x, digits=0) -> Series:
    """Round half away from zero, as Excel's ROUND does.

    Python's built-in ``round`` rounds halves to the nearest even number and works on the binary value, so
    ``round(2.675, 2)`` is ``2.67``. This function rounds the decimal the value prints as: ``2.675`` becomes ``2.68``.

    Parameters
    ----------
    x : Series, Quantity, or number
        The value to round.
    digits : int or Series, default=0
        Number of decimal places. A negative number rounds to tens, hundreds, and so on (``-2`` rounds to the
        nearest hundred). A series gives a number of places for each period.

    Returns
    -------
    Series
        The rounded value in each period, in the unit of ``x``. A missing value stays missing.

    Raises
    ------
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.rounddown : Round toward zero.
    boki.roundup : Round away from zero.
    boki.floor : Round down to a whole number.

    Examples
    --------
    Halves round away from zero, and decimals round as printed:

    >>> import boki as b
    >>> m = b.Model("Round", start="2027-01", periods=3, step=b.month)
    >>> price = m.series("Price", data={0: 2.5, 1: -2.5, 2: 2.675})
    >>> r = m.render()
    >>> r[b.round(price)]
    [3.0, -3.0, 3.0]
    >>> r[b.round(price, 2)]
    [2.5, -2.5, 2.68]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    if isinstance(digits, int) and digits == 0:
        return Op(_round_half_up, x)
    return Op(_round_digits, x, digits, unit=lift(x).unit)


def rounddown(x, digits=0) -> Series:
    """Round toward zero, as Excel's ROUNDDOWN does.

    Parameters
    ----------
    x : Series, Quantity, or number
        The value to round.
    digits : int or Series, default=0
        Number of decimal places. A negative number rounds to tens, hundreds, and so on. A series gives a number of
        places for each period.

    Returns
    -------
    Series
        The value with the digits beyond ``digits`` dropped, in the unit of ``x``. A missing value stays missing.

    Raises
    ------
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.round : Round half away from zero.
    boki.roundup : Round away from zero.
    boki.floor : Round down toward negative infinity.

    Examples
    --------
    Drop the digits beyond one decimal and beyond the hundreds:

    >>> import boki as b
    >>> m = b.Model("Down", start="2027-01", periods=2, step=b.month)
    >>> price = m.series("Price", data={0: 2.57, 1: -2.57})
    >>> r = m.render()
    >>> r[b.rounddown(price, 1)]
    [2.5, -2.5]
    >>> r[b.rounddown(price * 1000, -2)]
    [2500.0, -2500.0]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Op(_round_down, x, digits, unit=lift(x).unit)


def roundup(x, digits=0) -> Series:
    """Round away from zero, as Excel's ROUNDUP does.

    Parameters
    ----------
    x : Series, Quantity, or number
        The value to round.
    digits : int or Series, default=0
        Number of decimal places. A negative number rounds to tens, hundreds, and so on. A series gives a number of
        places for each period.

    Returns
    -------
    Series
        The value rounded up in magnitude to ``digits`` places, in the unit of ``x``. A missing value stays missing.

    Raises
    ------
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.round : Round half away from zero.
    boki.rounddown : Round toward zero.
    boki.ceil : Round up toward positive infinity.

    Examples
    --------
    Round a price up to the next tenth and a quantity up to the next hundred:

    >>> import boki as b
    >>> m = b.Model("Up", start="2027-01", periods=2, step=b.month)
    >>> price = m.series("Price", data={0: 2.51, 1: -2.51})
    >>> r = m.render()
    >>> r[b.roundup(price, 1)]
    [2.6, -2.6]
    >>> r[b.roundup(price * 1000, -2)]
    [2600.0, -2600.0]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Op(_round_up, x, digits, unit=lift(x).unit)


def sceil(x) -> Series:
    """Round up to the smallest whole number at or above ``x``.

    Parameters
    ----------
    x : Series, Quantity, or number
        The value to round.

    Returns
    -------
    Series
        The smallest whole number not below ``x``, in the unit of ``x``. A missing value stays missing. Excel writes
        it as ``-INT(-x)``.

    Raises
    ------
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.floor : Round down to a whole number.
    boki.roundup : Round away from zero to a number of decimals.

    Examples
    --------
    Whole buses needed for a passenger count:

    >>> import boki as b
    >>> m = b.Model("Buses", start="2027-01", periods=2, step=b.month)
    >>> passengers = m.series("Passengers", data={0: 130, 1: 100})
    >>> r = m.render()
    >>> r[b.ceil(passengers / 50)]
    [3, 2]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Op(math.ceil, x)


def sfloor(x) -> Series:
    """Round down to the largest whole number at or below ``x``, as Excel's INT does.

    Parameters
    ----------
    x : Series, Quantity, or number
        The value to round.

    Returns
    -------
    Series
        The largest whole number not above ``x``, in the unit of ``x``. A negative number rounds away from zero
        (``-2.1`` becomes ``-3``). A missing value stays missing.

    Raises
    ------
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.

    See Also
    --------
    boki.ceil : Round up to a whole number.
    boki.rounddown : Round toward zero to a number of decimals.

    Examples
    --------
    Whole units a budget buys:

    >>> import boki as b
    >>> m = b.Model("Units", start="2027-01", periods=2, step=b.month)
    >>> budget = m.series("Budget", data={0: 130, 1: 100})
    >>> r = m.render()
    >>> r[b.floor(budget / 50)]
    [2, 2]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Op(math.floor, x)


def mod(x, n) -> Series:
    """Return the remainder of ``x`` divided by ``n``, with the sign of ``n``, as Excel's MOD does.

    Parameters
    ----------
    x : Series, Quantity, or number
        The dividend.
    n : Series, Quantity, or number
        The divisor. Its unit must match the unit of ``x``; a literal 0 and an unknown unit never conflict.

    Returns
    -------
    Series
        The remainder in each period, in the common unit. A missing value in either argument makes the result
        missing.

    Raises
    ------
    UnitError
        At construction, if ``x`` and ``n`` have different units.
    TypeError
        At construction, if an argument has a type a series expression cannot use, such as a list.
    ZeroDivisionError
        At evaluation, if ``n`` is 0 in a period.

    See Also
    --------
    boki.Series.__mod__ : The ``%`` operator, which does the same.
    boki.Series.__floordiv__ : The whole number of times the divisor fits.

    Examples
    --------
    A remainder takes the sign of the divisor, as Python's ``%`` does:

    >>> import boki as b
    >>> m = b.Model("Mod", start="2027-01", periods=2, step=b.month)
    >>> x = m.series("X", data={0: 7, 1: -7})
    >>> r = m.render()
    >>> r[b.mod(x, 3)]
    [1, 2]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return Op(operator.mod, x, n)


def _plain_number(x, fn: Callable, what: str) -> Series:
    node = lift(x)
    if node.unit not in (None, _DIMENSIONLESS):
        raise UnitError(f"{what} takes a plain number, got {_describe(node.unit)}")
    return Op(fn, node, unit=_DIMENSIONLESS)


def sexp(x) -> Series:
    """Return ``e`` raised to the power of ``x``, as Excel's EXP does.

    Parameters
    ----------
    x : Series or number
        A plain number: a series that is dimensionless or of unknown unit.

    Returns
    -------
    Series
        The exponential in each period; a dimensionless series. A missing value stays missing.

    Raises
    ------
    UnitError
        At construction, if ``x`` has a unit.
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.
    OverflowError
        At evaluation, if the result is too large to represent (``x`` above about 709).

    See Also
    --------
    boki.log : Natural logarithm.
    boki.Series.__pow__ : Raise a series to a power.

    Examples
    --------
    Continuous compounding at 5% over the period index, in a monthly model:

    >>> import boki as b
    >>> m = b.Model("Exp", start="2027-01", periods=3, step=b.month)
    >>> r = m.render()
    >>> [round(v, 4) for v in r[b.exp(0.05 * m.t)]]
    [1.0, 1.0513, 1.1052]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return _plain_number(x, math.exp, "exp")


def slog(x) -> Series:
    """Return the natural logarithm of ``x``, as Excel's LN does.

    Parameters
    ----------
    x : Series or number
        A plain number: a series that is dimensionless or of unknown unit.

    Returns
    -------
    Series
        The natural logarithm in each period; a dimensionless series. A missing value stays missing.

    Raises
    ------
    UnitError
        At construction, if ``x`` has a unit.
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.
    ValueError
        At evaluation, if ``x`` is zero or negative in a period.

    See Also
    --------
    boki.exp : The exponential.

    Examples
    --------
    The continuous growth rate between two index values:

    >>> import boki as b
    >>> m = b.Model("Log", start="2027-01", periods=2, step=b.month)
    >>> index = m.series("Index", data={0: 1, 1: 2})
    >>> r = m.render()
    >>> [round(v, 4) for v in r[b.log(index)]]
    [0.0, 0.6931]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return _plain_number(x, math.log, "log")


def ssqrt(x) -> Series:
    """Return the square root of ``x``, as Excel's SQRT does.

    Parameters
    ----------
    x : Series or number
        A plain number: a series that is dimensionless or of unknown unit.

    Returns
    -------
    Series
        The square root in each period; a dimensionless series. A missing value stays missing.

    Raises
    ------
    UnitError
        At construction, if ``x`` has a unit.
    TypeError
        At construction, if ``x`` has a type a series expression cannot use, such as a list.
    ValueError
        At evaluation, if ``x`` is negative in a period.

    See Also
    --------
    boki.Series.__pow__ : Raise a series to a power, such as ``x ** 0.5``.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Root", start="2027-01", periods=2, step=b.month)
    >>> variance = m.series("Variance", data={0: 4, 1: 9})
    >>> r = m.render()
    >>> r[b.sqrt(variance)]
    [2.0, 3.0]
    """  # noqa: DOC105, DOC106, DOC107, DOC502
    return _plain_number(x, math.sqrt, "sqrt")
