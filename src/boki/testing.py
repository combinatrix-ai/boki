"""compare() and expect(): set a render beside numbers taken from the original spreadsheet. approx(), above(),
below() and between() are reference values that are not one exact number."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from .series import Series, lift
from .units import Quantity, UnitError, _describe


@dataclass
class Entry:
    """One compared number: the model's value beside the reference value, for one series and period.

    `compare` returns one entry for each number it compares. An entry is a plain record; read ``ok`` to see whether the
    two agreed within the tolerance.

    Parameters
    ----------
    label : str
        Name of the compared series, or ``name[period]`` for a value picked with ``x[period]``.
    period : str
        Label of the period, or ``""`` for a scalar series.
    got : float | date | None
        The model's value in base units, or ``None`` if the model has no value there.
    want : float | date | Bound
        The reference value in base units, or the `Bound` it must lie within.
    ok : bool
        Whether the model's value agrees with the reference.

    Attributes
    ----------
    label : str
        Name of the compared series.
    period : str
        Label of the period, or ``""`` for a scalar series.
    got : float, date, or None
        The model's value.
    want : float, date, or Bound
        The reference value or bound.
    ok : bool
        Whether the model's value agrees with the reference.

    See Also
    --------
    boki.compare : Returns the entries.
    boki.testing.Comparison : A list of entries.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Entries", start="2027-01", periods=2, step=b.year)
    >>> sales = m.series("Sales", data={0: 100, 1: 120})
    >>> r = m.render()
    >>> entry = b.compare(r, {sales: [100, 121]}).entries[1]
    >>> entry.label, entry.period, entry.got, entry.want, entry.ok, entry.diff
    ('Sales', '2028', 120, 121, False, -1)
    """  # noqa: DOC605
    label: str
    period: str
    got: float | date | None
    want: float | date | Bound
    ok: bool

    @property
    def diff(self) -> float | None:
        """Model value minus reference value.

        Returns
        -------
        float or None
            ``got - want``, in base units. ``None`` when the model has no value, or when the reference is a date or a
            `Bound`, which have no single number to subtract.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Diff", start="2027-01", periods=2, step=b.year)
        >>> sales = m.series("Sales", data={0: 100, 1: 120})
        >>> r = m.render()
        >>> [entry.diff for entry in b.compare(r, {sales: [100, 125]}).entries]
        [0, -5]
        """  # noqa: DOC203
        return None if self.got is None or isinstance(self.want, (date, Bound)) else self.got - self.want


class Bound:
    """Reference value that is a range instead of one number.

    Make one with `boki.approx`, `boki.above`, `boki.below` or `boki.between`, and use it as the reference value in
    `boki.compare` and `boki.expect`. It is never built directly.

    Parameters
    ----------
    text : str
        How the bound reads in a comparison table, such as ``"> 0.5"`` or ``"1.34 ± 0.005"``.
    lo : float | Quantity | None
        Lower end of the range in base units, or ``None`` for no lower end.
    hi : float | Quantity | None
        Upper end of the range in base units, or ``None`` for no upper end.
    strict : bool
        Whether the ends are excluded (``True``) or included (``False``).

    See Also
    --------
    boki.approx : A value within a tolerance.
    boki.above : More than a value.
    boki.below : Less than a value.
    boki.between : From one value to another.

    Examples
    --------
    >>> import boki as b
    >>> str(b.between(1, 2)), str(b.above(0.5))
    ('1 to 2', '> 0.5')
    """

    def __init__(self, text: str, lo: float | Quantity | None = None, hi: float | Quantity | None = None,
                 strict: bool = False):
        self.text, self.lo, self.hi, self.strict = text, lo, hi, strict

    def base(self, node: Series) -> Bound:
        return Bound(self.text, None if self.lo is None else _base(node, self.lo),
                     None if self.hi is None else _base(node, self.hi), self.strict)

    def holds(self, got) -> bool:
        if got is None:
            return False
        if self.strict:
            return (self.lo is None or got > self.lo) and (self.hi is None or got < self.hi)
        return (self.lo is None or got >= self.lo) and (self.hi is None or got <= self.hi)

    def __str__(self) -> str:
        return self.text


def approx(value, tol: float | None = None, rel: float | None = None) -> Bound:
    """Return a reference that accepts values within a tolerance of ``value``.

    Use it as the reference value in `compare` and `expect` when the source gives a rounded figure: a ratio shown as
    1.34 is ``b.approx(1.34, tol=0.005)``.

    Parameters
    ----------
    value : float or Quantity
        The centre of the range, such as ``1.34`` or ``100 * USD``. A `Quantity` is compared in its unit.
    tol : float or Quantity, optional
        Absolute half-width of the range, in the same unit as ``value`` (``tol=1 * USD`` with ``100 * USD``).
    rel : float, optional
        Relative half-width: a fraction of the size of ``value``, so ``rel=0.01`` accepts 1% either way. When both
        ``tol`` and ``rel`` are given, the wider range applies.

    Returns
    -------
    Bound
        A reference for the range ``value - width`` to ``value + width``, both ends included.

    Raises
    ------
    TypeError
        At construction, if neither ``tol`` nor ``rel`` is given. For an exact number, use the plain value.

    See Also
    --------
    boki.above : More than a value.
    boki.between : From one value to another, both included.
    boki.expect : Fail on a value outside its reference.

    Examples
    --------
    A source ratio rounded to two decimals:

    >>> import boki as b
    >>> m = b.Model("Ratio", start="2027-01", periods=2, step=b.year)
    >>> bcr = m.series("BCR", 1.3412)
    >>> r = m.render()
    >>> b.expect(r, {bcr: b.approx(1.34, tol=0.005)})
    >>> str(b.approx(1.34, tol=0.005)), str(b.approx(100, rel=0.01))
    ('1.34 ± 0.005', '100 ± 1')
    """  # noqa: DOC105, DOC107
    if tol is None and rel is None:
        raise TypeError("approx() takes tol= or rel=; without them use the plain value")
    width = max(tol if tol is not None else 0 * value, abs(value) * rel if rel is not None else 0 * value)
    return Bound(f"{_full(value)} ± {_full(width)}", value - width, value + width)


def above(value) -> Bound:
    """Return a reference that accepts values greater than ``value``.

    Use it as the reference value in `compare` and `expect` when the source gives only a lower limit, such as "over
    50%". The limit itself does not pass.

    Parameters
    ----------
    value : float or Quantity
        The limit. A `Quantity` is compared in its unit.

    Returns
    -------
    Bound
        A reference for values strictly above ``value``.

    See Also
    --------
    boki.below : Less than a value.
    boki.between : From one value to another, both included.
    boki.approx : A value within a tolerance.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Share", start="2027-01", periods=2, step=b.year)
    >>> share = m.series("Share", 0.62)
    >>> r = m.render()
    >>> b.expect(r, {share: b.above(0.5)})
    """  # noqa: DOC105, DOC106, DOC107
    return Bound(f"> {_full(value)}", lo=value, strict=True)


def below(value) -> Bound:
    """Return a reference that accepts values less than ``value``.

    Use it as the reference value in `compare` and `expect` when the source gives only an upper limit. The limit itself
    does not pass.

    Parameters
    ----------
    value : float or Quantity
        The limit. A `Quantity` is compared in its unit.

    Returns
    -------
    Bound
        A reference for values strictly below ``value``.

    See Also
    --------
    boki.above : More than a value.
    boki.between : From one value to another, both included.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Leverage", start="2027-01", periods=2, step=b.year)
    >>> ratio = m.series("Debt ratio", 2.4)
    >>> r = m.render()
    >>> b.expect(r, {ratio: b.below(3)})
    """  # noqa: DOC105, DOC106, DOC107
    return Bound(f"< {_full(value)}", hi=value, strict=True)


def between(lo, hi) -> Bound:
    """Return a reference that accepts values from ``lo`` to ``hi``, both included.

    Use it as the reference value in `compare` and `expect` when the source gives a range.

    Parameters
    ----------
    lo : float or Quantity
        Lower end of the range. A `Quantity` is compared in its unit.
    hi : float or Quantity
        Upper end of the range, in the same unit as ``lo``.

    Returns
    -------
    Bound
        A reference for values from ``lo`` to ``hi``.

    See Also
    --------
    boki.approx : A value within a tolerance.
    boki.above : More than a value.
    boki.below : Less than a value.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Range", start="2027-01", periods=2, step=b.year)
    >>> irr = m.series("IRR", 0.12)
    >>> r = m.render()
    >>> b.expect(r, {irr: b.between(0.1, 0.15)})
    """  # noqa: DOC105, DOC106, DOC107
    return Bound(f"{_full(lo)} to {_full(hi)}", lo, hi)


class Comparison:
    """The model's values beside the reference values, one entry for each compared number.

    `compare` returns it. Printing it (or showing it in a notebook) writes a table with the columns period, model,
    source and diff, and marks every disagreement with ``≠``. ``mismatches`` lists the disagreeing entries.

    Parameters
    ----------
    entries : list[Entry]
        The compared numbers, in the order of the reference keys and then of the periods.

    Attributes
    ----------
    entries : list[Entry]
        All compared numbers, agreeing or not.

    See Also
    --------
    boki.compare : Returns a comparison.
    boki.expect : Fail on any mismatch instead of listing.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Compare", start="2027-01", periods=3, step=b.year)
    >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 130})
    >>> r = m.render()
    >>> comparison = b.compare(r, {sales: [100, 121, 130]})
    >>> len(comparison.entries), len(comparison.mismatches)
    (3, 1)
    """  # noqa: DOC602, DOC603

    def __init__(self, entries: list[Entry]):
        self.entries = entries

    @property
    def mismatches(self) -> list[Entry]:
        """The entries where the model and the reference disagree.

        Returns
        -------
        list[Entry]
            A new list of the entries whose ``ok`` is false, in comparison order; empty when everything agrees.

        See Also
        --------
        boki.expect : Raise when this list is not empty.

        Examples
        --------
        >>> import boki as b
        >>> m = b.Model("Mismatch", start="2027-01", periods=2, step=b.year)
        >>> sales = m.series("Sales", data={0: 100, 1: 120})
        >>> r = m.render()
        >>> [(e.label, e.period, e.got, e.want) for e in b.compare(r, {sales: [100, 125]}).mismatches]
        [('Sales', '2028', 120, 125)]
        """
        return [e for e in self.entries if not e.ok]

    def __str__(self) -> str:
        rows = [("", "period", "model", "source", "diff", "")] + [
            (e.label, e.period, _num(e.got), _num(e.want), _num(e.diff), "" if e.ok else "≠") for e in self.entries]
        widths = [max(len(r[i]) for r in rows) for i in range(6)]
        return "\n".join("  ".join(c.ljust(w) if i < 2 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths)))
                         for r in rows)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))


def compare(result, reference: dict, tol: float = 0.01, rel: float = 1e-4) -> Comparison:
    """Return the model's values beside reference values taken from the original spreadsheet.

    Use it to see every number with its difference; `expect` is the same comparison that fails on a mismatch.

    Parameters
    ----------
    result : Result
        The render to read the model's values from.
    reference : dict
        Maps what to compare to the source's value. A key is a scalar series (``revenue[5]``, ``lib.npv(...)``) or a
        whole series. For a whole series, the value is a list with one reference per period, a `Series` of
        references, or a single value that is compared in every period. A list has one value per period of the
        model, with ``None`` for a period the source has no value for (it is not compared). A scalar key takes one
        value. A value can be a `Bound` (`approx`, `above`, `below`, `between`), a date (a date series compares as
        dates), or a `Quantity` such as ``28_032_000 * kWh``, which is compared in its unit.
    tol : float, default=0.01
        Absolute tolerance, in the base unit of the compared series (dollars, Wh, months), not in the unit shown
        in tables.
    rel : float, default=1e-4
        Relative tolerance, a fraction of the larger of the two values. A pair agrees when it is within ``tol`` or
        within ``rel``, whichever is wider.

    Returns
    -------
    Comparison
        One entry for each compared number. A constant series compared with a list of period values is read as
        that constant in every period.

    Raises
    ------
    ValueError
        At evaluation, if a list has a different number of values than the model has periods.
    UnitError
        At evaluation, if a reference `Quantity` has other dimensions than the series.

    See Also
    --------
    boki.expect : Fail on any mismatch.
    boki.approx : Reference within a tolerance.

    Notes
    -----
    The model's values are read from the render, so errors from evaluating the series (an unknown period, a division by
    zero) are raised here too. See `comparing with the source
    <https://github.com/combinatrix-ai/boki/blob/master/docs/conventions.md#compare-results-with-the-source>`_.

    Examples
    --------
    List the entries that disagree with a source sheet's figures:

    >>> import boki as b
    >>> m = b.Model("Source", start="2027-01", periods=3, step=b.year)
    >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 130})
    >>> bcr = m.series("BCR", 1.3412)
    >>> r = m.render()
    >>> comparison = b.compare(r, {sales: [100, 121, 130], bcr: b.approx(1.34, tol=0.005)})
    >>> [(e.label, e.period, e.got, e.want) for e in comparison.mismatches]
    [('Sales', '2028', 120, 121)]

    A single value is compared in every period, and a quantity in its own unit:

    >>> from boki.units import MWh
    >>> gen = m.series("Generation", data={0: 400 * MWh, 1: 400 * MWh, 2: 400 * MWh})
    >>> r = m.render()
    >>> [e.ok for e in b.compare(r, {gen: 400 * MWh}).entries]
    [True, True, True]
    """  # noqa: DOC105, DOC107, DOC503
    entries = []
    for key, want in reference.items():
        node = lift(key)
        got = result[node]
        if isinstance(want, Series):                    # a reference written as a series (by_year(...) * INR)
            want = result[want]
        if not isinstance(got, list) and isinstance(want, (list, tuple)):
            got = [got] * result.model.timeline.n       # a constant series beside a value per period
        if isinstance(got, list):
            wants = list(want) if isinstance(want, (list, tuple)) else [want] * len(got)   # one value: every period
            if len(wants) != len(got):
                raise ValueError(f"{_label(node)}: {len(wants)} reference values for {len(got)} periods")
            pairs = zip((p.label for p in result.model.timeline.periods), got, wants)
        else:
            pairs = [("", got, want)]
        for period, g, w in pairs:
            if w is None:
                continue
            if isinstance(w, Bound):
                w = w.base(node)
                entries.append(Entry(_label(node), period, g, w, w.holds(g)))
                continue
            w = _base(node, w)
            if isinstance(w, date):
                w = w.date() if isinstance(w, datetime) else w             # a spreadsheet date cell reads as midnight
                ok = g == w
            else:
                ok = g is not None and math.isclose(g, w, rel_tol=rel, abs_tol=tol)
            entries.append(Entry(_label(node), period, g, w, ok))
    return Comparison(entries)


def expect(result, expected: dict, tol: float = 0.01, rel: float = 1e-4) -> None:
    """Raise an error that lists every value that differs from the original spreadsheet.

    Use it to verify a model against the source's figures. It does the same comparison as `compare`, which shows
    every number without failing.

    Parameters
    ----------
    result : Result
        The render to read the model's values from.
    expected : dict
        Maps what to compare to the source's value, as the ``reference`` of `compare`: scalar series or whole series
        as keys, and numbers, lists with one value per period, a `Series`, dates, quantities or bounds as values.
    tol : float, default=0.01
        Absolute tolerance, in the base unit of the compared series.
    rel : float, default=1e-4
        Relative tolerance, a fraction of the larger of the two values.

    Raises
    ------
    AssertionError
        At evaluation, if any value differs. The message lists each mismatch with the series, period, expected value and
        the model's value.
    ValueError
        At evaluation, if a list has a different number of values than the model has periods.
    UnitError
        At evaluation, if a reference `Quantity` has other dimensions than the series.

    See Also
    --------
    boki.compare : Show every number without failing.
    boki.approx : Reference within a tolerance.

    Examples
    --------
    Verify a series, then see how a mismatch is reported:

    >>> import boki as b
    >>> m = b.Model("Source", start="2027-01", periods=3, step=b.year)
    >>> sales = m.series("Sales", data={0: 100, 1: 120, 2: 130})
    >>> r = m.render()
    >>> b.expect(r, {sales: [100, 120, 130]})
    >>> try:
    ...     b.expect(r, {sales: [100, 121, 130]})
    ... except AssertionError as error:
    ...     print(error)
    values differ from the source:
      Sales [2028]: expected 121, got 120
    """  # noqa: DOC105, DOC107, DOC503
    bad = compare(result, expected, tol, rel).mismatches
    if bad:
        raise AssertionError("values differ from the source:\n" + "\n".join(
            f"  {e.label}{f' [{e.period}]' if e.period else ''}: expected {_full(e.want)}, got {_full(e.got)}" for e in bad))


def _base(node: Series, want):
    if isinstance(want, Quantity):
        if node.unit is not None and want.dims != node.unit:
            raise UnitError(f"{_label(node)} is in {_describe(node.unit)}, the reference value is in "
                            f"{_describe(want.dims)}")
        return want.value
    return want


def _full(v) -> str:
    if isinstance(v, Quantity):
        return str(v)
    return "-" if v is None else (f"{v:,.10g}" if isinstance(v, (int, float)) else str(v))


def _num(v) -> str:
    return "-" if v is None else str(v) if isinstance(v, (date, Bound)) else f"{v:,.6g}"


def _label(node: Series) -> str:
    src = getattr(node, "src", None)
    if src is not None and hasattr(node, "t"):
        return f"{src.name or type(src).__name__}[{node.t}]"
    return node.name or type(node).__name__


__all__ = ["Bound", "Comparison", "Entry", "above", "approx", "below", "between", "compare", "expect"]
