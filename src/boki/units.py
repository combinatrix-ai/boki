"""Units: dimension checking at build time; plain floats in base units at evaluation time.

A Unit is a scale times a product of base dimensions. `3 * kW` builds a Quantity at
build time (checked when combined) and a plain float in base units inside a render,
so @m.series functions work on ordinary numbers.

Time is measured in months. `0.05 / year` is stored as a per-month rate; the ledger
integrates rates by each period's length. Days and hours are separate dimensions
(their length in months depends on the calendar), so `day` and `h` never silently
convert to months.
"""
from __future__ import annotations

import math
from typing import Mapping

from . import evaluator

Dims = frozenset  # frozenset[tuple[str, int]]


def _dims(d: Mapping[str, int]) -> Dims:
    return frozenset((k, v) for k, v in d.items() if v)


def _combine(a: Dims, b: Dims, sign: int) -> Dims:
    out = dict(a)
    for k, v in b:
        out[k] = out.get(k, 0) + sign * v
    if out.get("month") and out.get("day"):
        # a month is 28 to 31 days, so month / day has no fixed value
        raise UnitError("months and days do not convert at a fixed rate; for the days in each period use "
                        "m.period_end - m.date")
    return _dims(out)


_DIMENSIONLESS: Dims = frozenset()
_MONTHS: Dims = frozenset({("month", 1)})


def _show(value, unit: "Unit | None", dims: "Dims | None") -> str:
    """A value for a message, in the unit it was written in: '100,000 USD', '6,000 kW'."""
    if unit is not None:
        v = value / unit.scale
        return f"{v:,.10g} {unit.name}" if isinstance(v, (int, float)) else f"{v} {unit.name}"
    return f"{value:,.10g} {_describe(dims)}" if isinstance(value, (int, float)) else f"{value!r}"


def _describe(d: Dims | None) -> str:
    if d is None:
        return "unknown unit"
    if not d:
        return "dimensionless"
    num = [f"{k}^{v}" if v != 1 else k for k, v in sorted(d) if v > 0]
    den = [f"{k}^{-v}" if v != -1 else k for k, v in sorted(d) if v < 0]
    s = "×".join(num) or "1"
    return s + ("/" + "×".join(den) if den else "")


class UnitError(TypeError):
    """Error raised when units do not fit together.

    ``UnitError`` is a `TypeError`. boki raises it when an expression, a series, or a line is declared, and during a
    render when a series function returns a value in a different unit from the one declared. Typical causes:

    * adding, subtracting, comparing, or choosing between values of different dimensions, such as ``USD`` and
      ``kW``, or a nonzero plain number and a quantity with a unit (``0`` fits any unit);
    * combining months and days, which have no fixed ratio; use ``m.period_end - m.date`` for the days in a period;
    * passing a rate per time such as ``0.05 / b.year`` where a dimensionless per-period rate is required (for
      example `boki.lib.compound`, `boki.lib.discount`, `boki.lib.npv`);
    * raising a quantity with a unit to a non-integer power, or converting it to a plain `float`;
    * an amount in a unit other than the entity's currency.

    See Also
    --------
    boki.units.Quantity : A number with a unit.
    boki.units.Unit : A unit of measure.

    Notes
    -----
    A message names the dimensions involved in base units: ``W`` for power, ``month`` for time, and the name of
    each currency. Time is measured in months, so ``1 / b.year`` is a quantity in ``1/month``.

    Examples
    --------
    Adding power to money fails when the sum is written:

    >>> import boki as b
    >>> from boki.units import USD, kW
    >>> try:
    ...     2 * kW + 3 * USD
    ... except b.UnitError as error:
    ...     print(error)
    cannot add W and USD
    """


class Unit:
    """A unit of measure: a scale times a product of base dimensions.

    ``kW`` is the dimension power (``W``) with the scale 1000, ``year`` is the dimension ``month`` with the scale
    12, and ``USD`` is a dimension of its own with the scale 1. A number times a unit is a `Quantity`, checked
    when it is combined with others: ``3 * kW`` is 3000 W. Units multiply and divide into new units (``kW * h``,
    ``USD / year``) and raise to integer powers. Make a new countable unit with `unit`; the built-in constants
    are listed on the units reference page.

    Parameters
    ----------
    name : str
        Name shown in messages and labels, such as ``"kW"``.
    dims : frozenset
        The dimension: a `frozenset` of ``(dimension name, exponent)`` pairs such as ``frozenset({("W", 1)})``. The
        empty set is dimensionless.
    scale : float
        Size of one unit in the base unit of its dimension, so ``1000.0`` for ``kW`` (base unit W). The default is
        ``1.0``.

    Attributes
    ----------
    name : str
        The unit's name.
    dims : frozenset
        The dimension, as ``(dimension name, exponent)`` pairs.
    scale : float
        Size of one unit in base units.

    See Also
    --------
    boki.unit : Define a new unit.
    boki.units.Quantity : A number with a unit.

    Notes
    -----
    Base units are the dimension names themselves: a currency in itself, power in W, energy in W×h, and time in
    months. Days (``day``) and hours (``h``) are dimensions of their own, because their length in months depends on
    the calendar. Only `unit`, the constants, and arithmetic on them create units, so the constructor is listed for
    completeness.

    Examples
    --------
    Read a built-in unit:

    >>> from boki.units import kW, year
    >>> (kW.name, kW.scale)
    ('kW', 1000.0)
    >>> (year.name, year.scale)
    ('year', 12.0)

    Divide units to make a rate unit:

    >>> from boki.units import USD
    >>> rate = USD / year
    >>> (rate.name, round(rate.scale, 4))
    ('USD/year', 0.0833)
    """

    name: str
    dims: frozenset
    scale: float

    def __init__(self, name: str, dims: frozenset, scale: float = 1.0):
        self.name, self.dims, self.scale = name, dims, scale

    def __repr__(self):
        return f"<Unit {self.name}>"

    def _derive(self, other, sign) -> "Unit":
        if isinstance(other, Unit):
            op = "*" if sign > 0 else "/"
            return Unit(f"{self.name}{op}{other.name}", _combine(self.dims, other.dims, sign),
                        self.scale * other.scale ** sign)
        return NotImplemented

    def __mul__(self, other):
        """Return this unit times ``other``: a unit when ``other`` is a unit, else a quantity or series.

        Parameters
        ----------
        other : Unit, Quantity, number, or Series
            The factor. A unit gives the product unit, with the dimensions added and the scales multiplied. A
            number or `Quantity` gives that amount in this unit. A `Series` gives the series in this unit.

        Returns
        -------
        Unit, Quantity, or Series
            A unit named ``"<this>*<other>"`` when ``other`` is a unit. Otherwise a `Quantity`, or a `Series` when
            ``other`` is a series. Inside a render the quantity is a plain float in base units.

        Raises
        ------
        UnitError
            At construction, if the product combines months and days.

        See Also
        --------
        boki.units.Unit.__rmul__ : The number-first form, ``3 * kW``.

        Examples
        --------
        Multiply two units, or a unit by a number:

        >>> from boki.units import kW, h
        >>> energy = kW * h
        >>> (energy.name, energy.scale)
        ('kW*h', 1000.0)
        >>> (kW * 3).value
        3000.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        if isinstance(other, Unit):
            return self._derive(other, 1)
        return Quantity.of(other, self)

    def __rmul__(self, other):
        """Return ``other`` times this unit: a quantity, or a series when ``other`` is a series.

        This is the usual way to write a quantity: ``3 * kW``, ``100 * USD``, ``12 * month``.

        Parameters
        ----------
        other : number, Quantity, or Series
            The amount in this unit. A `Quantity` is multiplied by the unit, which combines their dimensions.

        Returns
        -------
        Quantity, Series, or float
            A `Quantity` holding the amount in base units. It is a `Series` when ``other`` is a series, and a plain
            float in base units inside a render (in an ``@m.series`` function).

        Raises
        ------
        UnitError
            At construction, if the product combines months and days.

        See Also
        --------
        boki.units.Unit.__mul__ : The unit-first form, ``kW * 3``.

        Examples
        --------
        A quantity stores its value in base units:

        >>> from boki.units import kW, year
        >>> q = 3 * kW
        >>> q.value
        3000.0
        >>> (2 * year).value
        24.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return Quantity.of(other, self)

    def __truediv__(self, other):
        """Return this unit divided by ``other``: a unit when ``other`` is a unit, else a quantity.

        Parameters
        ----------
        other : Unit, Quantity, or number
            The divisor. A unit gives a rate unit, with the dimensions subtracted and the scales divided. A
            `Quantity` such as ``1000 * cf`` gives the price of one unit, in this unit per the quantity's unit. A
            number divides this unit's scale.

        Returns
        -------
        Unit or Quantity
            A unit named ``"<this>/<other>"`` when ``other`` is a unit. Otherwise a `Quantity` equal to this unit's
            scale divided by ``other``.

        Raises
        ------
        UnitError
            At construction, if the quotient combines months and days.

        See Also
        --------
        boki.units.Unit.__rtruediv__ : The number-first form, ``1 / year``.

        Examples
        --------
        Divide money by time to get a rate unit, or by a quantity to get a price:

        >>> from boki.units import USD, kW, month, unit
        >>> (USD / month).name
        'USD/month'
        >>> cf = unit("cf")
        >>> price = USD / (1000 * cf)
        >>> (price.value, sorted(price.dims))
        (0.001, [('USD', 1), ('cf', -1)])
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        if isinstance(other, Unit):
            return self._derive(other, -1)
        if isinstance(other, Quantity):                       # USD / (1000 * cf)
            return Quantity(self.scale / other.value, _combine(self.dims, other.dims, -1))
        if isinstance(other, (int, float)):
            return Quantity(self.scale / other, self.dims)
        return NotImplemented

    def __rtruediv__(self, other):
        """Return ``other`` divided by this unit: a quantity in the inverse unit.

        ``1 / b.year`` and ``0.05 / b.year`` are how a rate per time is written. Time is measured in months, so the
        quantity is stored per month and the ledger integrates it by each period's length.

        Parameters
        ----------
        other : number
            The numerator, such as ``0.05`` for 5% per year.

        Returns
        -------
        Quantity
            The amount in the inverse unit, in base units: ``0.05 / year`` is ``0.05 / 12`` per month.

        See Also
        --------
        boki.units.Unit.__truediv__ : Divide a unit by something.

        Examples
        --------
        A 6% annual rate is stored as 0.5% per month:

        >>> from boki.units import year
        >>> rate = 0.06 / year
        >>> round(rate.value, 6)
        0.005
        >>> sorted(rate.dims)
        [('month', -1)]
        """  # noqa: DOC105, DOC106, DOC107, DOC203
        return Quantity.of(other, Unit(f"1/{self.name}", _combine(_DIMENSIONLESS, self.dims, -1), 1 / self.scale))

    def __pow__(self, k: int):
        """Return this unit raised to the power ``k``.

        Parameters
        ----------
        k : int
            The exponent. It multiplies the exponent of every dimension, and the scale is raised to it.

        Returns
        -------
        Unit
            A unit named ``"<this>^<k>"``.

        Examples
        --------
        Square a unit, or invert it with a negative exponent:

        >>> from boki.units import kW, year
        >>> squared = kW ** 2
        >>> (squared.name, squared.scale)
        ('kW^2', 1000000.0)
        >>> (year ** -1).name
        'year^-1'
        """  # noqa: DOC203
        return Unit(f"{self.name}^{k}", _dims({n: e * k for n, e in self.dims}), self.scale ** k)


class Quantity:
    """A number with a unit, built at model-construction time.

    A quantity is what ``3 * kW``, ``100 * USD``, ``12 * month`` and ``0.05 / year`` produce. It stores its value
    in the base units of its dimensions (``3 * kW`` holds 3000 W) together with those dimensions, and every
    operation checks the dimensions: only quantities of the same dimensions are added, subtracted, or compared. A
    quantity is accepted wherever a model takes an amount, a rate, a life, or a period length. Inside a render, the
    same expressions give plain floats in base units, so ``@m.series`` functions work on ordinary numbers.

    Parameters
    ----------
    base_value : float
        The value in the base units of ``dims``.
    dims : frozenset
        The dimension, as for `Unit.dims`.

    Attributes
    ----------
    value : float
        The value in base units: currency units, W, W×h, and months.
    dims : frozenset
        The dimension, as ``(dimension name, exponent)`` pairs.

    See Also
    --------
    boki.units.Unit : A unit of measure.
    boki.UnitError : The error for units that do not fit.

    Notes
    -----
    Write quantities by multiplying a number by a unit; the constructor is listed for completeness. A plain number
    and a quantity with dimensions do not mix, except ``0``, which fits any unit. Quantities do not define ``==``,
    which compares identity: compare ``a.value == b.value`` after checking the dimensions. A quantity of months
    added to or subtracted from a date shifts the date, as ``date + 3 * month`` does. When one operand is a
    `Series`, the operation gives a series.

    Examples
    --------
    Add quantities, and convert a rate per year to a rate per month:

    >>> from boki.units import USD, kW, year
    >>> power = 3 * kW + 2 * kW
    >>> power.value
    5000.0
    >>> sorted(power.dims)
    [('W', 1)]
    >>> fee = 120 * USD / year
    >>> fee.value
    10.0
    >>> sorted(fee.dims)
    [('USD', 1), ('month', -1)]
    """

    value: float
    dims: frozenset

    def __init__(self, base_value: float, dims: frozenset):
        self.value, self.dims = base_value, dims   # value already in base units
        self.shown: "Unit | None" = None

    @staticmethod
    def of(x, unit: Unit):
        from .series import Series
        if isinstance(x, Series):
            return x * Quantity(1.0 * unit.scale, unit.dims)
        if isinstance(x, Quantity):
            return Quantity(x.value * unit.scale, _combine(x.dims, unit.dims, 1))
        v = x * unit.scale
        if evaluator.current() is not None:
            return v
        q = Quantity(v, unit.dims)
        q.shown = unit                            # how it was written (kW), for messages
        return q

    def __repr__(self):
        return f"<Quantity {self.value} {_describe(self.dims)}>"

    def _same(self, o, op):
        if isinstance(o, Quantity):
            if o.dims != self.dims:
                raise UnitError(f"cannot {op} {_describe(self.dims)} and {_describe(o.dims)}")
            return o.value
        if o == 0:
            return 0
        if not self.dims:
            return o
        raise UnitError(f"cannot {op} {_describe(self.dims)} and a plain number ({o!r})")

    def _shift(self, d, sign):
        from datetime import date as _date
        if isinstance(d, _date) and self.dims == _MONTHS:
            from .model import add_months
            return add_months(d, sign * int(round(self.value)))
        return None

    def __add__(self, o):
        """Return the sum of this quantity and ``o``, or a date shifted by this many months.

        Parameters
        ----------
        o : Quantity, number, date, or Series
            The value to add. A `Quantity` must have the same dimensions as this one. A plain number is accepted
            only if it is ``0`` or this quantity is dimensionless. A date is shifted forward when this quantity is
            a number of months (``date + 3 * month``), rounded to a whole number of months, with the day of the
            month clamped to the length of the resulting month. A `Series` defers to the series.

        Returns
        -------
        Quantity, date, or Series
            A `Quantity` in base units when ``o`` is a quantity or number, the shifted date when ``o`` is a date,
            and a `Series` when ``o`` is a series.

        Raises
        ------
        UnitError
            At construction, if the dimensions differ, if ``o`` is a plain nonzero number and this quantity has
            dimensions, or if ``o`` is a date and this quantity is not a number of months.

        See Also
        --------
        boki.units.Quantity.__sub__ : Subtract a quantity.

        Examples
        --------
        Add quantities of the same dimension, or shift a date by months:

        >>> import datetime
        >>> from boki.units import kW, month
        >>> (2 * kW + 3 * kW).value
        5000.0
        >>> datetime.date(2027, 1, 31) + 3 * month
        datetime.date(2027, 4, 30)
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .series import Series
        if isinstance(o, Series):
            return NotImplemented
        shifted = self._shift(o, 1)
        if shifted is not None:
            return shifted
        return Quantity(self.value + self._same(o, "add"), self.dims)

    def __radd__(self, o):
        """Return ``o`` plus this quantity, so that a date or ``0`` can be on the left.

        Python calls this for ``o + quantity`` when ``o`` cannot add a quantity itself. It is ``__add__`` with the
        operands swapped, so the rules of `Quantity.__add__` apply: ``date + 3 * month`` shifts the date, and
        ``0 + quantity`` is the quantity.

        Parameters
        ----------
        o : number, date, or Quantity
            The left operand, with the forms of `Quantity.__add__`.

        Returns
        -------
        Quantity, date, or Series
            The result of ``o + quantity``, as for `Quantity.__add__`.

        Raises
        ------
        UnitError
            At construction, as for `Quantity.__add__`: a nonzero plain number does not add to a quantity with
            dimensions.

        See Also
        --------
        boki.units.Quantity.__add__ : The quantity-first form.

        Examples
        --------
        A date on the left shifts by a quantity of months, and ``0`` is accepted:

        >>> import datetime
        >>> from boki.units import kW, quarter
        >>> datetime.date(2027, 1, 15) + 1 * quarter
        datetime.date(2027, 4, 15)
        >>> (0 + 2 * kW).value
        2000.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self.__add__(o)

    def __sub__(self, o):
        """Return this quantity minus ``o``.

        Parameters
        ----------
        o : Quantity, number, or Series
            The value to subtract. A `Quantity` must have the same dimensions as this one. A plain number is
            accepted only if it is ``0`` or this quantity is dimensionless. A `Series` defers to the series. A date
            is not accepted here; subtract months from a date with ``date - 3 * month``.

        Returns
        -------
        Quantity or Series
            The difference in base units, or a `Series` when ``o`` is a series.

        Raises
        ------
        UnitError
            At construction, if the dimensions differ, or if ``o`` is a plain nonzero number and this quantity has
            dimensions.

        See Also
        --------
        boki.units.Quantity.__add__ : Add a quantity.
        boki.units.Quantity.__rsub__ : Subtract from a number or a date.

        Examples
        --------
        >>> from boki.units import USD
        >>> (500 * USD - 120 * USD).value
        380.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .series import Series
        if isinstance(o, Series):
            return NotImplemented
        return Quantity(self.value - self._same(o, "subtract"), self.dims)

    def __rsub__(self, o):
        """Return ``o`` minus this quantity, or a date shifted back by this many months.

        Python calls this for ``o - quantity`` when ``o`` cannot subtract a quantity itself.

        Parameters
        ----------
        o : number or date
            The left operand. A date is shifted back when this quantity is a number of months
            (``date - 3 * month``), rounded to a whole number of months, with the day of the month clamped to the
            length of the resulting month. A plain number is accepted only if it is ``0`` or this quantity is
            dimensionless.

        Returns
        -------
        Quantity or date
            ``o`` minus this quantity as a `Quantity`, or the shifted date.

        Raises
        ------
        UnitError
            At construction, if ``o`` is a plain nonzero number and this quantity has dimensions, or if ``o`` is a
            date and this quantity is not a number of months.

        See Also
        --------
        boki.units.Quantity.__sub__ : The quantity-first form.

        Examples
        --------
        Shift a date back by a quantity of months, or negate a quantity with ``0``:

        >>> import datetime
        >>> from boki.units import USD, month
        >>> datetime.date(2027, 5, 31) - 3 * month
        datetime.date(2027, 2, 28)
        >>> (0 - 2 * USD).value
        -2.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        shifted = self._shift(o, -1)
        if shifted is not None:
            return shifted
        return Quantity(self._same(o, "subtract") - self.value, self.dims)

    def __mul__(self, o):
        """Return this quantity times ``o``.

        Parameters
        ----------
        o : number, Quantity, Unit, or Series
            The factor. A number scales the quantity. A `Quantity` multiplies the values and adds the dimensions. A
            `Unit` multiplies by the unit's scale and adds its dimensions. A `Series` defers to the series.

        Returns
        -------
        Quantity or Series
            The product in base units, with the combined dimensions, or a `Series` when ``o`` is a series.

        Raises
        ------
        UnitError
            At construction, if the product combines months and days.

        See Also
        --------
        boki.units.Quantity.__truediv__ : Divide a quantity.

        Examples
        --------
        Multiply a power by a time to get an energy:

        >>> from boki.units import h, kW
        >>> energy = (3 * kW) * (2 * h)
        >>> energy.value
        6000.0
        >>> sorted(energy.dims)
        [('W', 1), ('h', 1)]
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .series import Series
        if isinstance(o, Series):
            return NotImplemented
        if isinstance(o, Unit):
            return Quantity.of(self, o)
        if isinstance(o, Quantity):
            return Quantity(self.value * o.value, _combine(self.dims, o.dims, 1))
        return Quantity(self.value * o, self.dims)

    def __rmul__(self, o):
        """Return ``o`` times this quantity, so that a number can be on the left.

        Python calls this for ``number * quantity``. It is ``__mul__`` with the operands swapped, so ``2 * (3 * kW)``
        is ``6 * kW``.

        Parameters
        ----------
        o : number, Quantity, or Unit
            The left operand, with the forms of `Quantity.__mul__`.

        Returns
        -------
        Quantity or Series
            The product in base units, as for `Quantity.__mul__`.

        Raises
        ------
        UnitError
            At construction, if the product combines months and days.

        See Also
        --------
        boki.units.Quantity.__mul__ : The quantity-first form.

        Examples
        --------
        >>> from boki.units import kW
        >>> (2 * (3 * kW)).value
        6000.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self.__mul__(o)

    def __truediv__(self, o):
        """Return this quantity divided by ``o``.

        Parameters
        ----------
        o : number, Quantity, Unit, or Series
            The divisor. A number scales the quantity. A `Quantity` divides the values and subtracts the dimensions.
            A `Unit` divides by the unit's scale and subtracts its dimensions, so ``120 * USD / year`` is a rate per
            month. A `Series` defers to the series.

        Returns
        -------
        Quantity or Series
            The quotient in base units, with the dimensions subtracted, or a `Series` when ``o`` is a series. It is
            dimensionless when both operands have the same dimensions.

        Raises
        ------
        UnitError
            At construction, if the quotient combines months and days.

        See Also
        --------
        boki.units.Quantity.__mul__ : Multiply a quantity.
        boki.units.Quantity.__rtruediv__ : Divide a number by a quantity.

        Notes
        -----
        Time is measured in months, so dividing an amount by ``year`` gives the amount per month: the ledger
        integrates a rate per time by the length of each period.

        Examples
        --------
        Convert a yearly amount to a monthly rate, and divide two quantities of the same dimension:

        >>> from boki.units import USD, kW, year
        >>> rate = 120 * USD / year
        >>> rate.value
        10.0
        >>> sorted(rate.dims)
        [('USD', 1), ('month', -1)]
        >>> ratio = (6 * kW) / (2 * kW)
        >>> (ratio.value, sorted(ratio.dims))
        (3.0, [])
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        from .series import Series
        if isinstance(o, Series):
            return NotImplemented
        if isinstance(o, Unit):
            return Quantity(self.value / o.scale, _combine(self.dims, o.dims, -1))
        if isinstance(o, Quantity):
            return Quantity(self.value / o.value, _combine(self.dims, o.dims, -1))
        return Quantity(self.value / o, self.dims)

    def __rtruediv__(self, o):
        """Return ``o`` divided by this quantity.

        Python calls this for ``number / quantity``. The result has the inverse dimensions.

        Parameters
        ----------
        o : number
            The numerator.

        Returns
        -------
        Quantity
            ``o`` divided by the value, in the inverse dimensions of this quantity.

        See Also
        --------
        boki.units.Quantity.__truediv__ : The quantity-first form.

        Examples
        --------
        Invert a price per unit:

        >>> from boki.units import kW
        >>> inverse = 1 / (4 * kW)
        >>> (inverse.value, sorted(inverse.dims))
        (0.00025, [('W', -1)])
        """  # noqa: DOC105, DOC106, DOC107, DOC203
        return Quantity(o / self.value, _combine(_DIMENSIONLESS, self.dims, -1))

    def __neg__(self):
        """Return this quantity with its sign changed.

        Returns
        -------
        Quantity
            The same dimensions, with the value negated.

        Examples
        --------
        >>> from boki.units import USD
        >>> (-(5 * USD)).value
        -5.0
        """  # noqa: DOC203
        return Quantity(-self.value, self.dims)

    def __abs__(self):
        """Return the absolute value of this quantity.

        Returns
        -------
        Quantity
            The same dimensions, with the value made nonnegative.

        Examples
        --------
        >>> from boki.units import USD
        >>> abs(-5 * USD).value
        5.0
        """  # noqa: DOC203
        return Quantity(abs(self.value), self.dims)

    def __pow__(self, k):
        """Return this quantity raised to the power ``k``.

        Parameters
        ----------
        k : int or float
            The exponent. It multiplies the exponent of every dimension. A quantity with dimensions needs an `int`
            exponent; a dimensionless quantity accepts any number.

        Returns
        -------
        Quantity
            The value raised to ``k``, with the dimensions scaled by ``k``.

        Raises
        ------
        UnitError
            At construction, if this quantity has dimensions and ``k`` is not an `int`.

        Examples
        --------
        Square a power, or take the root of a dimensionless ratio:

        >>> from boki.units import kW
        >>> square = (3 * kW) ** 2
        >>> (square.value, sorted(square.dims))
        (9000000.0, [('W', 2)])
        >>> (((4 * kW) / (1 * kW)) ** 0.5).value
        2.0
        """  # noqa: DOC105, DOC106, DOC107, DOC203
        if self.dims and not isinstance(k, int):
            raise UnitError(f"cannot raise {_describe(self.dims)} to a non-integer power")
        return Quantity(self.value ** k, _dims({n: e * k for n, e in self.dims}))

    def _cmp(self, o, op):
        return op(self.value, self._same(o, "compare"))

    def __lt__(self, o):
        """Return whether this quantity is less than ``o``.

        Parameters
        ----------
        o : Quantity or number
            The value to compare with. A `Quantity` must have the same dimensions as this one. A plain number is
            accepted only if it is ``0`` or this quantity is dimensionless.

        Returns
        -------
        bool
            Whether the value in base units is less than ``o``'s.

        Raises
        ------
        UnitError
            At construction, if the dimensions differ, or if ``o`` is a plain nonzero number and this quantity has
            dimensions.

        See Also
        --------
        boki.units.Quantity.__le__ : Less than or equal.
        boki.units.Quantity.__gt__ : Greater than.

        Notes
        -----
        To compare a quantity with a `Series`, write the series on the left (``series > quantity``): a quantity
        on the left raises a `TypeError` for a series, because the comparison does not defer to the series.

        Examples
        --------
        >>> from boki.units import kW
        >>> 2 * kW < 3 * kW
        True
        >>> 2 * kW < 0
        False
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self._cmp(o, float.__lt__)

    def __le__(self, o):
        """Return whether this quantity is less than or equal to ``o``.

        Parameters
        ----------
        o : Quantity or number
            The value to compare with, with the rules of `Quantity.__lt__`.

        Returns
        -------
        bool
            Whether the value in base units is at most ``o``'s.

        Raises
        ------
        UnitError
            At construction, as for `Quantity.__lt__`.

        See Also
        --------
        boki.units.Quantity.__lt__ : Less than.
        boki.units.Quantity.__ge__ : Greater than or equal.

        Examples
        --------
        >>> from boki.units import kW
        >>> 3 * kW <= 3 * kW
        True
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self._cmp(o, float.__le__)

    def __gt__(self, o):
        """Return whether this quantity is greater than ``o``.

        Parameters
        ----------
        o : Quantity or number
            The value to compare with, with the rules of `Quantity.__lt__`.

        Returns
        -------
        bool
            Whether the value in base units is greater than ``o``'s.

        Raises
        ------
        UnitError
            At construction, as for `Quantity.__lt__`.

        See Also
        --------
        boki.units.Quantity.__ge__ : Greater than or equal.
        boki.units.Quantity.__lt__ : Less than.

        Examples
        --------
        >>> from boki.units import kW
        >>> 3 * kW > 2 * kW
        True
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self._cmp(o, float.__gt__)

    def __ge__(self, o):
        """Return whether this quantity is greater than or equal to ``o``.

        Parameters
        ----------
        o : Quantity or number
            The value to compare with, with the rules of `Quantity.__lt__`.

        Returns
        -------
        bool
            Whether the value in base units is at least ``o``'s.

        Raises
        ------
        UnitError
            At construction, as for `Quantity.__lt__`.

        See Also
        --------
        boki.units.Quantity.__gt__ : Greater than.
        boki.units.Quantity.__le__ : Less than or equal.

        Examples
        --------
        >>> from boki.units import kW
        >>> 3 * kW >= 3 * kW
        True
        """  # noqa: DOC105, DOC106, DOC107, DOC203, DOC502
        return self._cmp(o, float.__ge__)

    def where(self, cond, else_=None):
        """A constant in periods where cond holds (e.g. rent only after opening)."""
        from .series import Where
        return Where(cond, self, else_)

    def __float__(self):
        if self.dims:
            raise UnitError(f"a quantity in {_describe(self.dims)} is not a plain number")
        return float(self.value)


# ---- display units ----------------------------------------------------------------

# Dimensions that take SI prefixes, with the symbol of their base unit. Currencies, counts and
# dimensionless numbers are absent on purpose: "k$" and "kGPU" are not units. Time is always
# months, so a per-month form (W/month, g/month) takes the same prefixes.
_PREFIXABLE: dict[Dims, str] = {
    frozenset({("W", 1)}): "W",
    frozenset({("W", 1), ("h", 1)}): "Wh",
    frozenset({("g", 1)}): "g",
    frozenset({("m", 1)}): "m",
}
_PREFIXES = ((-9, "n"), (-6, "µ"), (-3, "m"), (0, ""), (3, "k"), (6, "M"), (9, "G"), (12, "T"), (15, "P"))


def _prefixable(dims: Dims | None) -> str | None:
    """The base-unit symbol ('W', 'Wh/month') when dims take SI prefixes, else None."""
    if not dims:
        return None
    per = dict(dims).get("month", 0)
    if per not in (0, -1):
        return None
    symbol = _PREFIXABLE.get(frozenset(kv for kv in dims if kv[0] != "month"))
    return None if symbol is None else symbol + ("/month" if per else "")


def _takes_prefix(dims: Dims | None) -> bool:
    """Whether a series of these dimensions is shown with an SI prefix chosen from its values."""
    return _prefixable(dims) is not None


def _prefixed(dims: Dims, values) -> "Unit | None":
    """The unit to show values of these dimensions in: the power-of-1000 prefix of the base unit that puts
    the largest absolute value in [1, 1000) (Wh, kWh, MWh, GWh, ...); the base unit if every value is zero.

    None when the dimensions take no SI prefix (money, counts, dimensionless numbers).

    Notes
    -----
    One unit is chosen for the whole row, never per period, so that a row reads on one scale. Prefixes run from
    nano to peta; a value outside that range is shown with the nearest prefix.
    """
    symbol = _prefixable(dims)
    if symbol is None:
        return None
    peak = max((abs(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)
                and v == v and abs(v) != float("inf")), default=0.0)
    exponent, prefix = 0, ""
    if peak > 0:
        for e, p in _PREFIXES:
            if peak >= 10.0 ** e:
                exponent, prefix = e, p
        if peak < 10.0 ** _PREFIXES[0][0]:
            exponent, prefix = _PREFIXES[0]
    return Unit(prefix + symbol, dims, 10.0 ** exponent)


def _labeled(u: Unit) -> bool:
    """Whether a display unit is worth naming next to a value: it rescales the base unit or is a physical
    unit with a prefix choice. Money and counts shown in their own unit stay unlabeled, as before."""
    return u.scale != 1 or _takes_prefix(u.dims)


def _display_unit_of(x) -> Unit:
    """A unit for display=: a Unit, or a quantity such as `1 / year` (which stands for its unit)."""
    if isinstance(x, Unit):
        return x
    if isinstance(x, Quantity) and x.value > 0:
        shown = x.shown
        if shown is not None and math.isclose(shown.scale, x.value, rel_tol=1e-12):
            return shown
        name = _describe(x.dims) if shown is None else f"{x.value / shown.scale:g} {shown.name}"
        return Unit(name, x.dims, x.value)
    raise TypeError(f"display= must be a unit such as MWh or 1 / year, got {x!r}")


def unit(name: str, definition: Quantity | Unit | None = None) -> Unit:
    """Return a new unit: a countable unit of its own, or one defined from other units.

    Use it for quantities that are not money, power, or time, such as customers, GPUs, or cubic feet. A unit made
    from a name alone is a dimension of its own, and a unit made with a definition is a multiple of the definition.

    Parameters
    ----------
    name : str
        Name of the unit, shown in messages and labels. Without ``definition`` the name is also the name of the
        new dimension, so two calls with the same name give units of the same dimension, and a name such as
        ``"USD"`` or ``"month"`` gives the built-in dimension of that name.
    definition : Quantity or Unit, optional
        What one new unit equals, such as ``8 * GPU`` for a node of eight GPUs. The new unit has the dimensions of
        ``definition`` and its size. If it is `None`, the new unit is a dimension of its own. The default is `None`.

    Returns
    -------
    Unit
        The new unit. A number times it is a `Quantity` of that unit.

    See Also
    --------
    boki.units.Unit : The class of units.
    boki.units.Quantity : A number with a unit.

    Notes
    -----
    Currencies are distinct dimensions: ``USD`` and ``JPY`` do not convert. Convert with an exchange-rate series
    (``Model.fx``). Money and counts take no SI prefix in tables (there is no ``kGPU``).

    Examples
    --------
    Define a countable unit and a unit built from it:

    >>> from boki.units import unit
    >>> gpu = unit("GPU")
    >>> node = unit("node", 8 * gpu)
    >>> (2 * node + 4 * gpu).value
    20.0

    Two units with the same name are the same dimension:

    >>> (unit("GPU") * 1 + 2 * gpu).value
    3.0
    """  # noqa: DOC105
    if definition is None:
        return Unit(name, _dims({name: 1}))
    if isinstance(definition, Unit):
        return Unit(name, definition.dims, definition.scale)
    return Unit(name, definition.dims, definition.value)


# Built-in units. Currencies are distinct dimensions; convert with an exchange-rate series.
month = Unit("month", _dims({"month": 1}))
quarter = Unit("quarter", month.dims, 3.0)
year = Unit("year", month.dims, 12.0)
day = Unit("day", _dims({"day": 1}))
h = Unit("h", _dims({"h": 1}))
W = Unit("W", _dims({"W": 1}))
kW = Unit("kW", W.dims, 1e3)
MW = Unit("MW", W.dims, 1e6)
Wh = W * h
kWh = Unit("kWh", Wh.dims, 1e3)
MWh = Unit("MWh", Wh.dims, 1e6)
JPY, USD, EUR, GBP, CNY = (unit(c) for c in ("JPY", "USD", "EUR", "GBP", "CNY"))


__all__ = [
    "unit", "Unit", "Quantity", "UnitError", "USD", "JPY", "EUR", "GBP", "CNY", "W", "kW", "MW", "Wh",
    "kWh", "MWh", "day", "h", "month", "quarter", "year",
]
