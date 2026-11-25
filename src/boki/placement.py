"""Where rows go in the workbook: to_excel(sheets=[b.sheet(...)]) with b.section, b.row, b.link, b.block, and b.panel.

A sheet lists sections, rows, links, verified blocks, and non-time-series panels in reading order. A series placed
with b.row (or given as is) is written where it is placed, with its formula there. b.row(..., formula=...) lets the
modeler override the Excel formula of a row with an equivalent expression that boki verifies against the model across
scenarios and perturbed inputs. b.block(target, rows=[...]) expands a series into itemized rows plus a SUM total row
verified against target. b.link shows a placed row again elsewhere, as a reference to it.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._dataclass_docs import document_init

_VERIFY_MODES = ("perturb", "base", "off")
_FORMATS = (None, "percent", "multiple", "days", "integer", "number", "price")


def _check_verify(verify: str, where: str) -> str:
    if verify not in _VERIFY_MODES:
        raise ValueError(f"{where}: verify= must be one of {_VERIFY_MODES}, got {verify!r}")
    return verify


def _check_fmt(fmt: str | None, where: str) -> str | None:
    if fmt not in _FORMATS:
        raise ValueError(f"{where}: fmt= must be one of {_FORMATS[1:]} or None, got {fmt!r}")
    return fmt


def _check_total(total: bool | str, where: str) -> bool | str:
    if total not in (False, True, "grand"):
        raise ValueError(f"{where}: total= must be False, True, or 'grand', got {total!r}")
    return total


@document_init("Create a placed row.")
@dataclass(frozen=True, eq=False)
class Line:
    """A series placed on a sheet: the row where its formula is written, and how the row shows it.

    ``b.row(series, ...)`` makes one. Put it in the entries of a `Sheet`, `Section`, or `Block`. The row's display
    settings change only how the value is shown; formulas that refer to the row convert it back, so a result never
    changes. An optional ``formula`` overrides the Excel formula written for this row after boki verifies equivalence
    against ``series``. A `Line` is immutable and compares by identity.

    Parameters
    ----------
    series : Series
        The series to write. Required.
    label : str, optional
        Row label, which replaces the series' name. The default is ``None``, which keeps the name; an unnamed series
        needs a label.
    sign : int, default=1
        ``1`` shows the value as it is and ``-1`` shows it negated, such as a cost shown as a negative number.
    scale : float, default=1
        A positive divisor for display: ``1000`` shows the value in thousands. The cell shows ``value * sign / scale``.
    total : bool or str, default=False
        Row emphasis: ``False`` for a regular line, ``True`` for a bold subtotal with a top rule, or ``"grand"`` for a
        bold total with a top rule, double bottom rule, and shading.
    formula : Series, optional
        Alternative expression written to Excel in place of ``series``'s own formula (for forecast periods when the
        row has historical actuals). Verified against ``series`` according to ``verify``.
    verify : str, default="perturb"
        Equivalence check for ``formula``: ``"perturb"`` checks base, all scenarios, and perturbed inputs; ``"base"``
        checks the rendered result only; ``"off"`` skips verification.
    fmt : str, optional
        Display format hint: ``"percent"``, ``"multiple"``, ``"days"``, ``"integer"``, or ``"number"``.

    Attributes
    ----------
    series : object
        The placed series.
    label : str | None
        The row label, or ``None``.
    sign : int
        ``1`` or ``-1``.
    scale : float
        The display divisor.
    total : bool | str
        ``False``, ``True``, or ``"grand"``.
    formula : object
        Optional override expression, or ``None``.
    verify : str
        Equivalence verification mode.
    fmt : str | None
        Optional format hint.

    See Also
    --------
    boki.row : Make a placed row, with its checks.
    boki.block : Expand a series into itemized rows and a verified SUM total.
    boki.link : Show a placed row again on another sheet.

    Examples
    --------
    A cost shown as a negative number, in thousands:

    >>> import boki as b
    >>> m = b.Model("Line", start="2027-01", periods=2, step=b.month)
    >>> cost = m.series("Cost", 5)
    >>> line = b.row(cost, "Operating cost", sign=-1, scale=1000)
    >>> line.label, line.sign, line.scale, line.series is cost
    ('Operating cost', -1, 1000, True)
    """  # noqa: DOC105, DOC107, DOC603

    series: object
    label: str | None = None
    sign: int = 1
    scale: float = 1
    total: bool | str = False
    formula: object = None
    verify: str = "perturb"
    fmt: str | None = None


@document_init("Create a link to a placed row.")
@dataclass(frozen=True, eq=False)
class Link:
    """A placed row shown again elsewhere: each cell refers to the row it links to.

    ``b.link(row)`` makes one. A value then has one formula, in the row that was placed, and the link shows it as that
    row shows it (optionally negated with ``sign=-1``). A `Link` is immutable and compares by identity.

    Parameters
    ----------
    target : Line or Series
        The placed row to show again: the `Line` made by ``b.row``, or a series that is placed elsewhere. Required.
    label : str, optional
        Row label for the link. The default is ``None``, which uses the label of the target.
    sign : int, default=1
        ``1`` keeps the target's sign and ``-1`` negates it.
    total : bool or str, default=False
        Row emphasis: ``False``, ``True``, or ``"grand"``.
    fmt : str, optional
        Optional format hint: ``"percent"``, ``"multiple"``, ``"days"``, ``"integer"``, or ``"number"``.

    Attributes
    ----------
    target : object
        The row or series the link shows.
    label : str | None
        The row label, or ``None``.
    sign : int
        ``1`` or ``-1``.
    total : bool | str
        ``False``, ``True``, or ``"grand"``.
    fmt : str | None
        Optional format hint.

    See Also
    --------
    boki.link : Make a link.
    boki.row : Place a series.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Link", start="2027-01", periods=2, step=b.month)
    >>> revenue = m.series("Revenue", 5)
    >>> row = b.row(revenue)
    >>> shown_again = b.link(row, "Revenue (summary)")
    >>> shown_again.label, shown_again.target is row
    ('Revenue (summary)', True)
    """  # noqa: DOC105, DOC107, DOC603

    target: object          # a Line, or a series placed elsewhere
    label: str | None = None
    sign: int = 1
    total: bool | str = False
    fmt: str | None = None


@document_init("Create a verified block of itemized rows that sums to a target series.")
@dataclass(frozen=True, eq=False)
class Block:
    """An itemized group of rows whose Excel ``SUM`` is verified equal to a target series.

    ``b.block(target, rows, ...)`` makes one. In Excel, the itemized ``rows`` appear first, followed by a total row
    that sums them with ``=SUM(...)`` and acts as the home row of ``target``. Before writing the workbook, boki
    verifies that the sum of ``rows`` equals ``target`` across the base render, every scenario, and perturbed inputs.
    A `Block` is immutable and compares by identity.

    Parameters
    ----------
    target : Series
        The canonical series whose home becomes the block's ``SUM`` row (for example ``co.cf.operating``). Required.
    rows : tuple
        Itemized rows whose displayed values sum to ``target``: series, `Line`, or `Link`. Required.
    label : str, optional
        Label for the ``SUM`` total row. Defaults to ``target.name``.
    sign : int, default=1
        ``1`` or ``-1`` applied to the target comparison.
    total : bool or str, default=True
        Emphasis of the total row: ``True`` (subtotal) or ``"grand"``.
    verify : str, default="perturb"
        Equivalence verification mode: ``"perturb"``, ``"base"``, or ``"off"``.
    fmt : str, optional
        Optional display format hint for the total row.

    Attributes
    ----------
    target : object
        The canonical target series.
    rows : tuple
        The itemized component entries.
    label : str | None
        Total row label, or ``None``.
    sign : int
        ``1`` or ``-1``.
    total : bool | str
        Total row emphasis.
    verify : str
        Verification mode.
    fmt : str | None
        Optional format hint.

    See Also
    --------
    boki.block : Construct a verified block.
    boki.row : Place a single row with an optional verified formula override.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Block", start="2027-01", periods=2, step=b.year)
    >>> a = m.series("A", 10)
    >>> c = m.series("C", 20)
    >>> total = m.series("Total", a + c)
    >>> blk = b.block(total, [a, c], label="Combined")
    >>> blk.label, len(blk.rows)
    ('Combined', 2)
    """  # noqa: DOC105, DOC107, DOC603

    target: object
    rows: tuple
    label: str | None = None
    sign: int = 1
    total: bool | str = True
    verify: str = "perturb"
    fmt: str | None = None


@document_init("Create a non-time-series 2D table panel.")
@dataclass(frozen=True, eq=False)
class Panel:
    """A 2D summary table (such as Sources & Uses or a DCF Valuation Bridge) placed on a sheet.

    ``b.panel(title, columns, rows)`` makes one. Each cell value may be a scalar `Series` (written as a live Excel
    formula referring to placed rows or inputs), a `Quantity`, a number, or a string. A `Panel` is immutable and
    compares by identity.

    Parameters
    ----------
    title : str
        Heading written above the panel. Required.
    columns : tuple
        Column headers, such as ``("$mm", "%", "x EBITDA")``. Required.
    rows : tuple
        Rows of the panel as ``(label, values)`` or ``(label, values, options_dict)`` pairs, where ``values`` has one
        entry per column and ``options_dict`` may specify ``total`` and ``fmt``. Required.

    Attributes
    ----------
    title : str
        The panel heading.
    columns : tuple
        The column headers.
    rows : tuple
        The panel rows.

    See Also
    --------
    boki.panel : Construct a 2D panel.
    boki.sheet : Place panels alongside time-series sections on a sheet.

    Examples
    --------
    >>> import boki as b
    >>> pnl = b.panel("Sources", ["$mm", "%"], [("Debt", [60, 0.6]), ("Equity", [40, 0.4])])
    >>> pnl.title, pnl.columns, len(pnl.rows)
    ('Sources', ('$mm', '%'), 2)
    """  # noqa: DOC105, DOC107, DOC603

    title: str
    columns: tuple
    rows: tuple


@document_init("Create a 2D sensitivity table with live Excel axis references.")
@dataclass(frozen=True, eq=False)
class Sensitivity:
    """A 2D sensitivity matrix whose Excel formulas reference live numeric row and column headers.

    ``b.sensitivity(title, row_values, col_values, formula, ...)`` makes one. Row headers live in Column A and column
    headers live in the panel header row as real numbers or live formulas (formatted with ``row_fmt`` / ``col_fmt``),
    and every matrix cell emits a live Excel formula referencing ``$A<row>`` and ``<col>$<hdr>``. Editing any axis
    header directly in Excel recalculates that row or column live. A `Sensitivity` is immutable and compares by
    identity.

    Parameters
    ----------
    title : str
        Heading written above the sensitivity table. Required.
    row_values : tuple
        Row-axis values written into Column A (numbers or scalar `Series`). Required.
    col_values : tuple
        Column-axis values written into the table header row (numbers or scalar `Series`). Required.
    formula : callable
        Callable ``(row_var, col_var) -> Series`` defining each cell in terms of the row and column axis variables.
        Required.
    fmt : str, optional
        Display format hint for matrix cells (``"percent"``, ``"multiple"``, ``"price"``, ``"money"``, etc.).
    row_fmt : str, optional
        Display format hint or Excel number format for Column A row headers (for example ``'"Entry "0.0"x"'`` or
        ``"percent"``).
    col_fmt : str, optional
        Display format hint or Excel number format for top-row column headers (for example ``'"Exit "0.0"x"'`` or
        ``'"g = "0.0%'``).
    highlight : tuple of int, optional
        Optional ``(row_index, col_index)`` (0-based) to highlight as the Base-case cell.
    corner : str, default=""
        Optional label for the top-left corner cell of the header band (for example ``"Entry / Exit"``).

    Attributes
    ----------
    title : str
        Table heading.
    row_values : tuple
        Row-axis header values.
    col_values : tuple
        Column-axis header values.
    formula : object
        Callable building the matrix cell expression.
    fmt : str | None
        Cell format hint.
    row_fmt : str | None
        Row-header format hint or Excel format string.
    col_fmt : str | None
        Column-header format hint or Excel format string.
    highlight : tuple | None
        Highlighted ``(row_idx, col_idx)`` or ``None``.
    corner : str
        Top-left corner header text.

    See Also
    --------
    boki.sensitivity : Construct a 2D sensitivity table.
    boki.panel : Construct a general 2D summary table.

    Examples
    --------
    >>> import boki as b
    >>> s = b.sensitivity("Grid", [1.0, 2.0], [10.0, 20.0], lambda r, c: r * c, fmt="number")
    >>> s.title, len(s.row_values), len(s.col_values)
    ('Grid', 2, 2)
    """  # noqa: DOC105, DOC107, DOC603

    title: str
    row_values: tuple
    col_values: tuple
    formula: object
    fmt: str | None = None
    row_fmt: str | None = None
    col_fmt: str | None = None
    highlight: tuple | None = None
    corner: str = ""


@document_init("Create a section of a sheet.")
@dataclass(frozen=True, eq=False)
class Section:
    """A titled group of rows on a sheet.

    ``b.section(title, entries)`` makes one. A section heading is written above its rows. A `Section` is immutable and
    compares by identity.

    Parameters
    ----------
    title : str
        The heading. Required.
    entries : tuple
        The rows, in order: series, placed rows (`Line`), links (`Link`), verified blocks (`Block`), and panels
        (`Panel`). Required.

    Attributes
    ----------
    title : str
        The section heading.
    entries : tuple
        The entries of the section.

    See Also
    --------
    boki.section : Make a section.
    boki.sheet : A sheet holds sections and rows.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Section", start="2027-01", periods=2, step=b.month)
    >>> revenue = m.series("Revenue", 5)
    >>> block = b.section("Revenue", [b.row(revenue)])
    >>> block.title, len(block.entries)
    ('Revenue', 1)
    """  # noqa: DOC105, DOC107, DOC603

    title: str
    entries: tuple


@document_init("Create a sheet of placed rows.")
@dataclass(frozen=True, eq=False)
class Sheet:
    """A workbook sheet of placed rows, in reading order.

    ``b.sheet(name, entries, ...)`` makes one, and ``Result.to_excel(sheets=[...])`` writes each as a workbook sheet,
    in the order given. A `Sheet` is immutable and compares by identity.

    Parameters
    ----------
    name : str
        The sheet's name. Required. ``Inputs``, ``Model`` and ``Checks`` belong to the workbook, in any capitalization.
    entries : tuple
        The sections, blocks, panels, rows, links, and series, in order. Required.
    money : str, float, or int, optional
        Optional sheet-level money display scale such as ``"$mm"`` or ``"$000"``. Overrides the workbook style's
        ``money`` for this sheet when set.

    Attributes
    ----------
    name : str
        The sheet name.
    entries : tuple
        The entries of the sheet.
    money : str | float | int | None
        Optional money scale for this sheet.

    See Also
    --------
    boki.sheet : Make a sheet.
    boki.section : Group rows under a heading.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Sheet", start="2027-01", periods=2, step=b.month)
    >>> revenue = m.series("Revenue", 5)
    >>> summary = b.sheet("Summary", [b.row(revenue)])
    >>> summary.name, len(summary.entries)
    ('Summary', 1)
    """  # noqa: DOC105, DOC107, DOC603

    name: str
    entries: tuple
    money: str | float | int | None = None


def row(series, label: str | None = None, *, sign: int = 1, scale: float = 1,
        total: bool | str = False, formula=None, verify: str = "perturb",
        fmt: str | None = None) -> Line:
    """Place a series on a sheet: its formula is written in this row.

    Put the result in the entries of `b.sheet`, `b.section`, or `b.block`. The display settings change only how the
    row shows the value; formulas and statements that refer to the row turn it back into the value, so they never
    change a result. Pass ``formula=`` to write an alternative equivalent expression in Excel, verified against
    ``series`` across scenarios and perturbed inputs.

    Parameters
    ----------
    series : Series
        The series to write. Required.
    label : str, optional
        Row label, which replaces the series' name. The default is ``None``, which keeps the name. An unnamed series
        needs a label.
    sign : int, default=1
        ``1`` or ``-1``. ``-1`` shows the value negated, such as a cost shown as a negative number.
    scale : float, default=1
        A positive number the row's value is divided by for display, such as ``1000`` for thousands. A ``bool`` is not
        accepted.
    total : bool or str, default=False
        Row emphasis: ``False``, ``True`` (bold subtotal with top rule), or ``"grand"`` (double bottom rule and
        shading).
    formula : Series, optional
        Equivalent expression to emit in Excel instead of ``series``'s lowered expression. Verified against ``series``
        when ``to_excel`` runs.
    verify : str, default="perturb"
        Equivalence check mode for ``formula``: ``"perturb"``, ``"base"``, or ``"off"``.
    fmt : str, optional
        Display format hint: ``"percent"``, ``"multiple"``, ``"days"``, ``"integer"``, or ``"number"``.

    Returns
    -------
    Line
        The placed row, to use in a `Sheet`, `Section`, or `Block`, and as the target of `Link`.

    Raises
    ------
    ValueError
        At construction, if ``sign`` is not 1 or -1, ``scale`` is not a positive number, or ``total``, ``verify``, or
        ``fmt`` is invalid. At evaluation (when ``Result.to_excel`` writes the sheets), if the same series is placed by
        two rows, or an unnamed series is placed without a ``label``.

    See Also
    --------
    boki.block : Expand a series into itemized rows with a verified SUM total.
    boki.link : Show a placed row again on another sheet.
    boki.sheet : Make the sheet that holds placed rows.

    Notes
    -----
    A row shows ``value * sign / scale``. Use ``link`` to show a placed row again; placing the same series twice with
    ``row`` is an error. An input placed on a sheet is written as a link to its row on the Inputs sheet.
    See `Excel row placement
    <https://github.com/combinatrix-ai/boki/blob/master/docs/api.md#excel-row-placement>`_.

    Examples
    --------
    A cost shown as a negative number, in thousands:

    >>> import boki as b
    >>> m = b.Model("Row", start="2027-01", periods=2, step=b.month)
    >>> cost = m.series("Cost", 5000)
    >>> line = b.row(cost, "Operating cost", sign=-1, scale=1000)
    >>> line.label, line.sign, line.scale
    ('Operating cost', -1, 1000)
    >>> b.row(cost, sign=2)
    Traceback (most recent call last):
    ...
    ValueError: b.row: sign= is 1 or -1, got 2
    """  # noqa: DOC105, DOC107
    if sign not in (1, -1):
        raise ValueError(f"b.row: sign= is 1 or -1, got {sign!r}")
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
        raise ValueError(f"b.row: scale= is a positive number, got {scale!r}")
    _check_total(total, "b.row")
    _check_verify(verify, "b.row")
    _check_fmt(fmt, "b.row")
    return Line(series, label, sign, scale, total, formula, verify, fmt)


def link(target, label: str | None = None, *, sign: int = 1, total: bool | str = False,
         fmt: str | None = None) -> Link:
    """Show a placed row again: each cell refers to the row that ``b.row`` placed elsewhere.

    The value keeps one formula, in the placed row, and the link shows it as that row shows it (or negated when
    ``sign=-1``).

    Parameters
    ----------
    target : Line or Series
        The placed row to show again, as returned by ``b.row``, or a series that is placed elsewhere. Required.
    label : str, optional
        Row label of the link. The default is ``None``, which uses the label of the target.
    sign : int, default=1
        ``1`` keeps the target's sign and ``-1`` negates it.
    total : bool or str, default=False
        Row emphasis: ``False``, ``True``, or ``"grand"``.
    fmt : str, optional
        Optional display format hint: ``"percent"``, ``"multiple"``, ``"days"``, ``"integer"``, or ``"number"``.

    Returns
    -------
    Link
        The link, to use in the entries of a `Sheet`, `Section`, or `Block`.

    Raises
    ------
    ValueError
        At construction, if ``sign`` is not 1 or -1, or ``total`` or ``fmt`` is invalid.

    See Also
    --------
    boki.row : Place a series.
    boki.sheet : Make the sheet that holds links.

    Examples
    --------
    Place revenue on one sheet and show it again on a summary sheet:

    >>> import boki as b
    >>> m = b.Model("Link", start="2027-01", periods=2, step=b.month)
    >>> revenue = m.series("Revenue", 5)
    >>> row = b.row(revenue)
    >>> summary = b.sheet("Summary", [b.link(row, "Revenue")])
    >>> summary.entries[0].target is row
    True
    """  # noqa: DOC105, DOC107
    if sign not in (1, -1):
        raise ValueError(f"b.link: sign= is 1 or -1, got {sign!r}")
    _check_total(total, "b.link")
    _check_fmt(fmt, "b.link")
    return Link(target, label, sign, total, fmt)


def block(target, rows, *, label: str | None = None, sign: int = 1, total: bool | str = True,
          verify: str = "perturb", fmt: str | None = None) -> Block:
    """Expand a series into itemized rows followed by a verified ``SUM`` total row.

    Use ``b.block`` to present a canonical boki series (such as ``co.cf.operating``) as human-authored component rows
    summed by ``=SUM(...)`` in Excel (such as an indirect cash-flow block). Before writing the workbook, boki verifies
    that the sum of ``rows`` matches ``target`` across the base render, every scenario, and perturbed inputs; any
    discrepancy raises `EquivalenceError`.

    Parameters
    ----------
    target : Series
        The canonical series whose home becomes the block's ``SUM`` row. Required.
    rows : iterable
        The component rows whose values sum to ``target``: series, `Line`, or `Link`. Must be non-empty.
    label : str, optional
        Label for the total row. Defaults to ``target.name``.
    sign : int, default=1
        ``1`` or ``-1`` applied when comparing the sum against ``target``.
    total : bool or str, default=True
        Emphasis of the total row: ``True`` (subtotal) or ``"grand"``.
    verify : str, default="perturb"
        Equivalence check mode: ``"perturb"``, ``"base"``, or ``"off"``.
    fmt : str, optional
        Optional display format hint for the total row.

    Returns
    -------
    Block
        The verified block, to place inside a `Sheet` or `Section`.

    Raises
    ------
    ValueError
        At construction, if ``rows`` is empty, ``sign`` is not 1 or -1, or ``total``, ``verify``, or ``fmt`` is
        invalid.

    See Also
    --------
    boki.row : Place a single row with an optional verified formula override.
    boki.excel.EquivalenceError : Raised when the block sum disagrees with ``target``.

    Examples
    --------
    Expand a total into two component rows and verify equivalence on export:

    >>> import boki as b
    >>> m = b.Model("Block", start="2027-01", periods=2, step=b.year)
    >>> a = m.series("A", 10)
    >>> c = m.series("C", 20)
    >>> combined = m.series("Combined", a + c)
    >>> blk = b.block(combined, [a, c], label="Total")
    >>> blk.label, len(blk.rows)
    ('Total', 2)
    """  # noqa: DOC105, DOC107
    items = tuple(rows)
    if not items:
        raise ValueError("b.block: rows must not be empty")
    if sign not in (1, -1):
        raise ValueError(f"b.block: sign= is 1 or -1, got {sign!r}")
    _check_total(total, "b.block")
    _check_verify(verify, "b.block")
    _check_fmt(fmt, "b.block")
    return Block(target, items, label, sign, total, verify, fmt)


def panel(title: str, columns, rows) -> Panel:
    """Create a 2D non-time-series table panel (such as Sources & Uses or a Valuation Bridge).

    Parameters
    ----------
    title : str
        Heading written above the panel. Required.
    columns : iterable of str
        Column labels for the table. Must be non-empty.
    rows : iterable
        Rows as ``(label, values)`` or ``(label, values, options)`` tuples, where ``values`` has one cell per column
        (a scalar `Series`, `Quantity`, number, or string) and ``options`` is an optional dict with ``total`` / ``fmt``.

    Returns
    -------
    Panel
        The panel, to include in a `Sheet` or `Section`.

    Raises
    ------
    ValueError
        At construction, if ``columns`` is empty or a row's value count does not match ``columns``.

    See Also
    --------
    boki.sheet : Place panels on a workbook sheet.

    Examples
    --------
    >>> import boki as b
    >>> p = b.panel("Valuation", ["$mm", "x EBITDA"], [("Enterprise value", [500, 10.0])])
    >>> p.title, p.columns
    ('Valuation', ('$mm', 'x EBITDA'))
    """  # noqa: DOC105, DOC107
    cols = tuple(columns)
    if not cols:
        raise ValueError("b.panel: columns must not be empty")
    norm_rows = []
    for entry in rows:
        if len(entry) == 2:
            label, vals = entry
            opts = {}
        elif len(entry) == 3:
            label, vals, opts = entry
        else:
            raise ValueError(f"b.panel: each row must be (label, values) or (label, values, options), got {entry!r}")
        vals_t = tuple(vals)
        if len(vals_t) != len(cols):
            raise ValueError(f"b.panel({title!r}): row {label!r} has {len(vals_t)} values for {len(cols)} columns")
        norm_rows.append((label, vals_t, dict(opts)))
    return Panel(title, cols, tuple(norm_rows))


def sensitivity(title: str, row_values, col_values, formula, *, fmt: str | None = None,
                row_fmt: str | None = None, col_fmt: str | None = None,
                highlight: tuple[int, int] | None = None, corner: str = "") -> Sensitivity:
    """Create a 2D sensitivity matrix whose cells reference live numeric row and column headers in Excel.

    Parameters
    ----------
    title : str
        Heading written above the sensitivity table. Required.
    row_values : iterable
        Values for the row axis (numbers or scalar `Series`). Must be non-empty.
    col_values : iterable
        Values for the column axis (numbers or scalar `Series`). Must be non-empty.
    formula : callable
        Function ``(row_var, col_var) -> Series`` returning the expression for each cell. Required.
    fmt : str, optional
        Display format hint for matrix cells (``"percent"``, ``"multiple"``, ``"price"``, ``"money"``, etc.).
    row_fmt : str, optional
        Format hint or Excel format string for row headers in Column A.
    col_fmt : str, optional
        Format hint or Excel format string for column headers.
    highlight : tuple of int, optional
        Optional 0-based ``(row_index, col_index)`` of the Base-case cell to shade.
    corner : str, default=""
        Optional label for the top-left corner cell of the header band.

    Returns
    -------
    Sensitivity
        The sensitivity matrix, to place in a `Sheet` or `Section`.

    Raises
    ------
    ValueError
        At construction, if ``row_values`` or ``col_values`` is empty, ``formula`` is not callable, or ``highlight``
        is out of range.

    See Also
    --------
    boki.panel : Construct a general 2D summary table.
    boki.sheet : Place tables on a workbook sheet.

    Examples
    --------
    >>> import boki as b
    >>> s = b.sensitivity("Products", [2.0, 3.0], [10.0, 20.0], lambda r, c: r * c, highlight=(0, 1))
    >>> s.title, s.highlight
    ('Products', (0, 1))
    """  # noqa: DOC105, DOC107
    rows_t = tuple(row_values)
    cols_t = tuple(col_values)
    if not rows_t:
        raise ValueError("b.sensitivity: row_values must not be empty")
    if not cols_t:
        raise ValueError("b.sensitivity: col_values must not be empty")
    if not callable(formula):
        raise ValueError("b.sensitivity: formula must be callable(row_var, col_var)")
    if highlight is not None:
        if len(highlight) != 2 or not (0 <= highlight[0] < len(rows_t)) or not (0 <= highlight[1] < len(cols_t)):
            raise ValueError(f"b.sensitivity: highlight={highlight!r} out of range for {len(rows_t)}x{len(cols_t)}")
        highlight = (int(highlight[0]), int(highlight[1]))
    return Sensitivity(title, rows_t, cols_t, formula, fmt, row_fmt, col_fmt, highlight, corner)


def section(title: str, entries) -> Section:
    """Group rows under a heading on a sheet.

    Parameters
    ----------
    title : str
        The heading written above the rows. Required.
    entries : iterable
        The rows in order: series, placed rows made by ``b.row``, links made by ``b.link``, blocks made by
        ``b.block``, and panels made by ``b.panel``. Required.

    Returns
    -------
    Section
        The section, to use in the entries of a `Sheet`.

    See Also
    --------
    boki.sheet : Make the sheet that holds sections.
    boki.row : Place a series.

    Examples
    --------
    >>> import boki as b
    >>> m = b.Model("Section", start="2027-01", periods=2, step=b.month)
    >>> customers = m.input("Customers", 100)
    >>> revenue = m.series("Revenue", customers * 5)
    >>> block = b.section("Revenue", [customers, b.row(revenue)])
    >>> block.title, len(block.entries)
    ('Revenue', 2)
    """  # noqa: DOC105, DOC107
    return Section(title, tuple(entries))


def sheet(name: str, entries, *, money: str | float | int | None = None) -> Sheet:
    """Make a workbook sheet of placed rows, in reading order.

    Pass the sheets to ``Result.to_excel(sheets=[...])``. A placed series is written on its sheet with its formula, and
    the rest of the model stays where boki puts it.

    Parameters
    ----------
    name : str
        The sheet's name. Required. ``Inputs``, ``Model`` and ``Checks`` are the workbook's own sheets, in any
        capitalization.
    entries : iterable
        The sections, blocks, panels, rows, links, and series, in order. Required.
    money : str, float, or int, optional
        Optional sheet-level money scale such as ``"$mm"`` or ``"$000"``.

    Returns
    -------
    Sheet
        The sheet, to pass in ``sheets=`` of ``Result.to_excel``.

    Raises
    ------
    ValueError
        At construction, if ``name`` is ``Inputs``, ``Model`` or ``Checks``, in any capitalization.

    See Also
    --------
    boki.section : Group rows under a heading.
    boki.row : Place a series.
    boki.block : Expand a series into verified component rows.
    boki.panel : Add a 2D non-time-series table.
    boki.link : Show a row again.

    Examples
    --------
    Place revenue on a Sales sheet and link it from a Summary sheet, in a workbook written to a temporary folder:

    >>> import pathlib, tempfile
    >>> import boki as b
    >>> m = b.Model("Sheets", start="2027-01", periods=3, step=b.month)
    >>> customers = m.input("Customers", 100)
    >>> revenue = m.series("Revenue", customers * 20)
    >>> revenue_row = b.row(revenue)
    >>> sales = b.sheet("Sales", [b.section("Revenue", [customers, revenue_row])])
    >>> summary = b.sheet("Summary", [b.link(revenue_row)])
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     report = r.to_excel(pathlib.Path(folder) / "plan.xlsx", sheets=[sales, summary])
    >>> report.formulas > 0
    True
    >>> b.sheet("Model", [])
    Traceback (most recent call last):
    ...
    ValueError: b.sheet('Model'): that name is the workbook's own sheet
    """  # noqa: DOC105, DOC107
    if name.casefold() in {"inputs", "model", "checks"}:
        raise ValueError(f"b.sheet({name!r}): that name is the workbook's own sheet")
    if money is not None:
        from .styles import money_scale
        money_scale(money)
    return Sheet(name, tuple(entries), money)
