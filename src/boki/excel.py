"""Write a rendered model to Excel with live formulas.

The expression graph is already a formula graph: each named series becomes a row, each period a
column, and its definition becomes the cell formula, with references to other rows. Unnamed
sub-expressions are written inline, also where they are used twice; one that refers to its own past
(a running balance, compounding) gets a helper row, and so does a shared one when writing it inline
would make a formula longer than MAX_FORMULA. Inputs go to their own sheet, so the workbook's
parameter list is the model's inputs.

What cannot be written as a formula (an @m.series Python function, a solved unknown)
is written as its value, shaded and with a note, and counted in the returned report. Values are in
base units (JPY, Wh, months), the same as the model.

boki reads only the cells a value needs (the branch of a where that is taken, the one cell of a row an INDEX
picks); Excel's dependency graph counts every reference in a formula. Where those extra references would close a
circular reference that boki does not have, the fewest of them are written as NA() (see _Writer.break_cycles).

How it looks is a Style (boki.styles; banker by default). The style never changes the Model sheet's
formulas or values, only number formats, colors and folding; the statement sheets refer to the Model
sheet and do the scaling and signs.
"""
from __future__ import annotations

import math
import operator
import random
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from . import lib, ledger, placement, series as S, shapes, statements
from ._dataclass_docs import document_init
from .group import series as group_series
from .model import Input, Unknown, _Time
from .styles import AUTOMATIC, Style, _powers_of_1000, money_scale, styles
from .units import Quantity, Unit, _describe, _labeled

if TYPE_CHECKING:
    from .model import Result


class Untranslatable(Exception):
    """A series that cannot be written as an Excel formula.

    The Excel writer raises it while translating a series, and ``to_excel`` catches it: the cell is written as the
    value boki computed, shaded and with a note, and counted in ``Report.values``. The message of the exception is the
    reason, counted in ``Report.reasons``. You do not normally see the exception itself; you see its reasons in the
    report.

    See Also
    --------
    boki.excel.Report : The report that counts the value cells and their reasons.

    Notes
    -----
    Typical reasons are an unknown that was solved (``Unknown``), a Python function used as a series, a period chosen by
    a series, and a reduction that has no row to refer to. See `the Excel notes
    <https://github.com/combinatrix-ai/boki/blob/master/docs/excel.md>`_ for what is written as a formula.

    Examples
    --------
    A solved unknown has no formula, so its cell is a value, and the reason is reported:

    >>> import pathlib, tempfile
    >>> import boki as b
    >>> m = b.Model("Solve", start="2027-01", periods=2, step=b.year)
    >>> size = m.unknown("Size", init=1)
    >>> demand = m.input("Demand", 10)
    >>> m.solve(size, size == b.min(demand * 2, 15))
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     report = r.to_excel(pathlib.Path(folder) / "solve.xlsx")
    >>> report.reasons
    {'Unknown': 1}
    """


class CircularReferenceWarning(UserWarning):
    """Warning that the export guarded cells whose full formula would make a circular reference in Excel.

    boki reads only the cells a value needs, and Excel's dependency graph counts every reference in a formula. When the
    extra references would close a circular reference that boki does not have, ``to_excel`` writes the fewest of them
    as ``NA()`` and warns with the guarded cells. The guarded cells are shaded and have a note, and
    ``Report.guarded`` counts them.

    See Also
    --------
    boki.excel.Report : The report, whose ``guarded`` attribute counts the cells.

    Notes
    -----
    A guarded cell keeps its live condition and the formula for the branch boki reads. If a changed input in the workbook
    makes the cell read the guarded part, it shows ``#N/A`` and so do the cells that use it, instead of a wrong number; export
    again from boki for those inputs. See `circular references boki does not have
    <https://github.com/combinatrix-ai/boki/blob/master/docs/excel.md#circular-references-boki-does-not-have>`_.

    Examples
    --------
    A debt sized from its own cash flow, with the construction years masked by an IF, warns when it is exported:

    >>> import pathlib, tempfile, warnings
    >>> import boki as b
    >>> from boki.units import USD, year
    >>> m = b.Model("Toll road", start="2020", periods=8, step=year)
    >>> calendar = m.date.year
    >>> start = m.input("construction start", 2020)
    >>> opening = m.input("opening year", 2022)
    >>> building = (calendar >= start) & (calendar < opening)
    >>> operating = calendar >= opening
    >>> debt_period = operating & (calendar < opening + 4)
    >>> rate = m.input("debt rate", 0.05)
    >>> capex = m.series("capex", (60 * USD).where(building, 0 * USD))
    >>> revenue = m.series("net revenue", (40 * USD).where(operating, 0 * USD))
    >>> commitment = m.series("debt commitment")
    >>> fee = m.series("arrangement fee", (0.02 * commitment).where(calendar == start, 0 * USD))
    >>> drawdown = m.series("drawdown", (0.7 * (capex + fee)).where(building, 0 * USD))
    >>> equity = m.series("equity", (0.3 * (capex + fee)).where(building, 0 * USD))
    >>> cfads = m.series("CFADS", revenue - capex + equity + drawdown - fee)
    >>> factor = m.series("debt discount factor", (1 + rate) ** -(calendar - opening + 1))
    >>> npv = m.series("NPV of CFADS", (cfads * factor).where(debt_period, 0 * USD).sum())
    >>> sized = commitment.define(npv / 1.3)
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder, warnings.catch_warnings(record=True) as caught:
    ...     warnings.simplefilter("always")
    ...     report = r.to_excel(pathlib.Path(folder) / "toll.xlsx")
    >>> [warning.category.__name__ for warning in caught]
    ['CircularReferenceWarning']
    >>> report.guarded
    8
    """


class UnnamedAssumption(ValueError):
    """Error that a time table used inside a formula has no name.

    A time table (``b.by_year``, ``b.step``, or ``data``) used inside a formula without a name needs a row in the
    workbook, and a row needs a name. ``to_excel`` raises this error and lists each table with the file and line where
    it was made and the row that uses it. Name the table with ``m.input("...", ...)``, or with ``m.series`` when its
    values are other series. A single number such as ``0.45 * sales`` stays inline and needs no name.

    See Also
    --------
    boki.excel.Report : The report, whose ``unnamed`` attribute lists the tables.

    Notes
    -----
    The error is a `ValueError`. It is raised when the workbook is written, before any file is saved.

    Examples
    --------
    A cost ratio that changes by year, used without a name:

    >>> import pathlib, tempfile
    >>> import boki as b
    >>> from boki.units import USD
    >>> from boki.excel import UnnamedAssumption
    >>> m = b.Model("Unnamed", start="2027-01", periods=3, step=b.year)
    >>> co = m.entity("Co", standard=b.IFRS, currency=USD)
    >>> sales = co.pl.revenue("Sales", m.input("Sales plan", b.by_year({0: 100, 1: 120, 2: 150}) * USD))
    >>> ratio = b.by_year({0: 0.4, 1: 0.38, 2: 0.36})
    >>> cost = co.pl.cogs("Cost", ratio * sales)
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     try:
    ...         r.to_excel(pathlib.Path(folder) / "unnamed.xlsx")
    ...     except UnnamedAssumption as error:
    ...         print(str(error).splitlines()[0])
    1 assumption tables have no name; a table needs a row, and a row a name. Name each with m.input("…", …):
    """


class EquivalenceError(AssertionError):
    """Error that a ``b.row(..., formula=...)`` or ``b.block(...)`` rewrite disagrees with boki's model.

    Before writing the workbook, ``to_excel`` checks every verified rewrite against its target series across the base
    render, all declared scenarios, and randomly perturbed numeric inputs. Any mismatch raises this error with the
    row or block label, case, period, expected value, and rewrite value.

    See Also
    --------
    boki.row : Place a row with an optional verified ``formula=`` override.
    boki.block : Expand a series into itemized rows with a verified ``SUM`` total.

    Examples
    --------
    An incorrect override formula fails verification before the file is written:

    >>> import pathlib, tempfile
    >>> import boki as b
    >>> m = b.Model("Equiv", start="2027-01", periods=2, step=b.year)
    >>> x = m.input("X", 10)
    >>> y = m.series("Y", x * 2)
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     try:
    ...         r.to_excel(pathlib.Path(folder) / "bad.xlsx",
    ...                    sheets=[b.sheet("S", [b.row(y, formula=x * 3)])])
    ...     except b.EquivalenceError as error:
    ...         print("mismatch" in str(error).lower())
    True
    """


@dataclass
class Row:
    node: S.Series
    label: str
    section: str | None
    number: int = 0
    helper: bool = False
    alias: S.Series | None = None   # the named series or line item whose expression this row holds
    sheet: str = "Model"
    link: bool = False              # shows a row placed elsewhere (b.link): each cell refers to it
    factor: float = 1               # the cells show value / factor (b.row's sign × scale)
    total: bool | str = False       # False, True (subtotal), or "grand"
    formula: S.Series | None = None # optional verified override expression
    verify: str = "perturb"         # "perturb", "base", or "off"
    fmt: str | None = None          # optional display format hint
    block_rows: list["Row"] | None = None  # component rows for b.block SUM total
    block_sign: int = 1             # sign applied when verifying block sum against target
    link_sign: int = 1              # sign applied on a link row
    in_block: bool = False          # True for rows inside a b.block


@dataclass
class _PanelSpec:
    sheet: str
    panel: placement.Panel | placement.Sensitivity
    start_row: int = 0
    row_var: S.Series | None = None
    col_var: S.Series | None = None
    expr: S.Series | None = None


@dataclass
class _Table:
    node: "lib._Lookup"
    label: str
    shown: Unit | None              # the unit the value cells are written in (None: base units)
    factor: float                   # the value cells hold value / factor
    row: int = 0                    # the keys row on the Inputs sheet; the values are on the next


@document_init("Create a report of the cells written.")
@dataclass
class Report:
    """What an Excel export wrote: how many cells are formulas, data, or values boki computed, and why.

    ``Result.to_excel`` returns one. ``str(report)`` gives a one-line summary.

    Parameters
    ----------
    formulas : int, default=0
        Number of cells of the model's series that were written as live formulas. The formulas of the statement sheets
        are not counted.
    values : int, default=0
        Number of cells that could not be written as formulas and hold the value boki computed, shaded and with a note.
    data : int, default=0
        Number of cells that hold input data, such as the points of a time table.
    guarded : int, default=0
        Number of formula cells written with a part boki does not read as ``NA()``, to avoid a circular reference in Excel.
    reasons : dict, optional
        Why cells hold values, as ``{reason: count}``; the reasons are the messages of `Untranslatable`. The default is an
        empty dict.
    unnamed : list, optional
        Descriptions of the time tables without a name. ``to_excel`` raises `UnnamedAssumption` when any exist, so a
        report that was returned has an empty list. The default is an empty list.
    unplaced : list, optional
        Labels of any rows that remained on the ``Model`` sheet when ``omit_unused_model=True``. Empty when every
        needed calculation lives on placed sheets. The default is an empty list.

    Attributes
    ----------
    formulas : int
        Number of formula cells.
    values : int
        Number of value cells.
    data : int
        Number of data cells.
    guarded : int
        Number of guarded formula cells.
    reasons : dict[str, int]
        The count of value cells for each reason.
    unnamed : list[str]
        The unnamed tables found.
    unplaced : list[str]
        Labels of rows left on the ``Model`` sheet when ``omit_unused_model=True``.

    See Also
    --------
    boki.excel.Untranslatable : The reason a cell is a value.
    boki.excel.CircularReferenceWarning : The warning that goes with ``guarded``.

    Notes
    -----
    Values are in base units (currency, Wh, months), the same as the model. A value cell is a value, not a formula, so
    it does not follow a changed input in the workbook; export again from boki.

    Examples
    --------
    Export to a temporary folder and read the report:

    >>> import pathlib, tempfile
    >>> import boki as b
    >>> m = b.Model("Report", start="2027-01", periods=3, step=b.month)
    >>> customers = m.input("Customers", 100)
    >>> revenue = m.series("Revenue", customers * 20)
    >>> r = m.render()
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     report = r.to_excel(pathlib.Path(folder) / "plan.xlsx")
    >>> report.formulas > 0, report.values, report.guarded, report.unnamed
    (True, 0, 0, [])
    """  # noqa: DOC105, DOC107, DOC603

    formulas: int = 0
    values: int = 0
    data: int = 0
    guarded: int = 0               # formula cells with a part boki does not read written as NA() (break_cycles)
    reasons: dict[str, int] = field(default_factory=dict)
    unnamed: list[str] = field(default_factory=list)   # data rows without a name; to_excel raises on any
    unplaced: list[str] = field(default_factory=list)  # rows left on Model when omit_unused_model=True

    def __str__(self):
        why = ", ".join(f"{k} ×{v}" for k, v in sorted(self.reasons.items(), key=lambda kv: -kv[1]))
        text = f"{self.formulas} formula cells, {self.data} data cells, {self.values} value cells" + \
            (f" ({why})" if why else "")
        if self.guarded:
            text += f", {self.guarded} guarded against a circular reference"
        return text


@dataclass
class _Cell:
    """The Model cell whose formula is being written, and what it refers to (see _Writer.break_cycles).

    Each part of the formula that boki does not read in this period (an IF branch not taken, the rest of a row an
    INDEX picks one cell from) is numbered in the order it is written; its references are kept apart from the
    references boki reads, so that part alone can be guarded."""
    key: tuple[int, int]             # (id(row), period)
    record: bool                     # collect references (the planning pass) or only write
    parts: int = 0                   # unread parts written so far
    open: int | None = None          # the unread part being written, None on the path boki reads
    read: set = field(default_factory=set)
    unread: dict = field(default_factory=dict)   # part number -> cells it refers to
    guarded: bool = False


_BINARY = {operator.add: "+", operator.sub: "-", operator.mul: "*", operator.truediv: "/", operator.pow: "^",
           operator.lt: "<", operator.le: "<=", operator.gt: ">", operator.ge: ">=", operator.eq: "=",
           operator.ne: "<>"}
_FUNCS = {S._vmin: "MIN", S._vmax: "MAX", S._and: "AND", S._or: "OR"}
_SPAN = {"sum": "SUM", "mean": "AVERAGE", "min": "MIN", "max": "MAX"}
_ROUNDS = {S._round_digits: "ROUND", S._round_down: "ROUNDDOWN", S._round_up: "ROUNDUP"}
_MATH = {math.exp: "EXP", math.log: "LN", math.sqrt: "SQRT", S._year_of: "YEAR", S._month_of: "MONTH"}
_DATA = (S.Data, _Time, statements._Days)
_RECURRENT = (S.Cumsum, S.ReverseCumsum, lib._Compound, lib._Discount, lib._Index, ledger._Balance,
              ledger._NOL, ledger._Depreciation, ledger._AssetTradeFlow, group_series._JgaapNciProfit,
              group_series._JgaapSuspendedLoss, group_series._GoodwillAmortization,
              group_series._EquityMethodProfit, group_series._EquityMethodSuspended,
              group_series._EquityMethodAvailable)


def _is_actuals_inline(node) -> bool:
    return bool(getattr(node, "_actuals_inline", False))


def _is_data(node) -> bool:
    if _is_actuals_inline(node):
        return False
    if isinstance(node, shapes._ByYear):
        values = [*node.mapping.values()]
        if node.default is not None:
            values.append(node.default)
        return all(isinstance(S.lift(value), S.Const) for value in values)
    if isinstance(node, shapes._Step):
        return all(isinstance(S.lift(value), S.Const) for value in node.mapping.values())
    return isinstance(node, _DATA)


# -- choosing translations ---------------------------------------------------------------
# How a node is written decides which cells it needs. These two say it for every translation in
# _Writer.expand, so changing a translation (a running sum as SUM over a range rather than the
# previous cell plus this period) changes the rows here too.

def _needs_own_row(node, has_row) -> bool:
    """The translation refers to the node's own cells (a recurrence), or the node is written as data or a value.
    A running sum of a series that has a row is SUM over that row's cells so far, and needs no row of its own."""
    if isinstance(node, S.Cumsum) and not node.src.scalar and has_row(node.src):
        return False
    return _is_data(node) or isinstance(node, _RECURRENT) or isinstance(node, (S.Fn, Unknown))


def _needs_rows_for(node) -> list:
    """Children the translation refers to as a range of cells, so each needs a row."""
    if isinstance(node, S.Reduce):
        return [s for s in node.srcs if not s.scalar]
    if isinstance(node, lib._RunningIrr):
        return [node.src]
    return []
FIRST_COL = 3   # A: label, B: unit, C...: periods
MAX_FORMULA = 200   # characters: a shared sub-expression is written inline until a formula would grow past this


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _range(first: str, last: str) -> str:
    sheet, first = first.rsplit("!", 1) if "!" in first else ("", first)
    last = last.rsplit("!", 1)[-1]
    return f"{sheet}!{first}:{last}" if sheet else f"{first}:{last}"


class _Writer:
    def __init__(self, result: "Result", style: Style | None = None, sheets=None, *,
                 scenarios=None, omit_unused_model: bool = False, checks: bool | None = None):
        self.r, self.m = result, result.model
        self.style = style or styles.banker
        self.n = self.m.n
        self.scenarios = list(scenarios) if scenarios is not None else None
        if self.scenarios is not None and not self.scenarios:
            raise ValueError("scenarios= must not be empty")
        self.omit_unused_model = bool(omit_unused_model)
        self.emit_checks = self.style.statements if checks is None else bool(checks)
        self.rows: list[Row] = []
        self.row_of: dict[int, Row] = {}
        self.inputs: dict[int, int] = {}   # input node -> row on the Inputs sheet
        self.input_rows: list[tuple[Input, Any]] = []
        self.shared: list[S.Series] = []   # sub-expressions used more than once, written inline unless too long
        self.layout = list(sheets or [])   # b.sheet(...) placements; the Model sheet holds the rest
        self.sheet_meta: dict[str, placement.Sheet] = {sh.name: sh for sh in self.layout}
        self.panels: list[_PanelSpec] = []
        self.panel_cells: dict[int, tuple[str, int, int]] = {}
        self._active_panel_cell: tuple[str, int, int] | None = None
        self._axis_refs: dict[int, str] = {}
        self.local_links: dict[tuple[str, int], Row] = {}
        self._active_row: Row | None = None
        self._scenario_renders: dict[str, "Result"] = {}
        self._formula_sizes: dict[tuple[str | None, int, int], str] = {}
        self._sizing = 0
        self._fixed: dict[int, bool] = {}
        self.shown: dict[int, Unit] = {}   # node -> the unit its row shows (see choose_display_units)
        self.converted: set[int] = set()   # nodes whose cells hold the display value (row factor), not base units
        self.input_factor: dict[int, float] = {}   # input node -> its display unit's scale (the Inputs cell holds value / scale)
        self.input_unit: dict[int, Unit] = {}
        self.prefixed: set[int] = set()    # nodes whose unit boki chose from the values: shown with a decimal
        # each entity's books, then each group's consolidated books (written like another entity)
        self.books = list(self.m.entities) + [g.books for g in self.m.groups]
        self.sheet_now: str | None = "Model"   # the sheet being written: references to it need no sheet name
        self.report = Report()
        self._now: _Cell | None = None     # the Model cell being written (break_cycles, write_rows)
        self.guards: set[tuple] = set()    # (cell, part) written as NA() to avoid a circular reference
        self.guard_notes: list[str] = []   # what break_cycles did, for the warning
        self._formulas: dict[tuple[int, int], str] = {}   # formulas from break_cycles, reused by write_rows

    def plan(self):
        """The passes before writing: collect the rows to show, verify rewrites, give rows to what the translations
        need, place them, then give rows to shared sub-expressions only where a formula would be too long.
        write() emits the cells; tools/excel_check.py verifies them."""
        self.collect()
        self.verify_rewrites()
        self.choose_display_units()
        self.promote()
        self.collect_tables()
        self.place()
        self.shorten()
        if self.omit_unused_model:
            self.prune_unused_model()
        self.report.unnamed = self.unnamed()
        self.break_cycles()

    def unnamed(self) -> list[str]:
        """Data rows with no name (a by_year inside a formula): where each was made and a row that uses it."""
        found = [r for r in self.rows if r.section == "helpers" and _is_data(r.node)]
        if not found:
            return []
        users: dict[int, str] = {}
        for row in self.rows:
            if row.link or row.block_rows is not None:
                continue
            seen, stack = set(), list(self._active_children(self._active_expr(row)))
            while stack:
                node = stack.pop()
                if id(node) in seen:
                    continue
                seen.add(id(node))
                if id(node) in self.row_of:
                    users.setdefault(id(node), row.label)
                    continue
                stack.extend(self._active_children(node))
        out = []
        for r in found:
            site = getattr(r.node, "site", None) or "?"
            used = users.get(id(r.node))
            out.append(f"{type(r.node).__name__.strip('_')} made at {site}" + (f", used in {used!r}" if used else ""))
        return out

    # -- which nodes get rows --------------------------------------------------------

    def add_row(self, node, label, section, helper=False, sheet="Model"):
        if id(node) in self.row_of:
            return
        row = Row(node, label, section, helper=helper, sheet=sheet)
        self.rows.append(row)
        self.row_of[id(node)] = row
        self._formula_sizes.clear()

    def add_named(self, node, label, section, sheet="Model"):
        """A named series or PL line is the row of its expression: the name, and whatever else refers to the
        expression (the posting that books a line, a running sum's recurrence), share one row, so the formula
        sits on the named row rather than on a helper or posting row that the named row only points at. An
        expression that already has a row (another name's) or is a constant or input stays where it is."""
        x = node.expr if isinstance(node, S.Named) else None
        if x is None or id(x) in self.row_of or id(x) in self.inputs or isinstance(x, S.Const):
            self.add_row(node, label, section, sheet=sheet)
            return
        self.add_row(x, label, section, sheet=sheet)
        self.row_of[id(x)].alias = node
        self.row_of[id(node)] = self.row_of[id(x)]

    def _active_expr(self, row: Row) -> S.Series:
        return row.formula if row.formula is not None else row.node

    def _register_local_link(self, sheet_name: str, row: Row):
        if isinstance(row.node, Input):
            return
        self.local_links.setdefault((sheet_name, id(row.node)), row)
        home = self.row_of.get(id(row.node))
        if home is not None:
            self.local_links.setdefault((sheet_name, id(home.node)), row)
            if home.alias is not None:
                self.local_links.setdefault((sheet_name, id(home.alias)), row)

    def place_layout(self):
        """Rows placed with to_excel(sheets=[...]): each on its sheet, in the order given (boki.placement)."""
        links: list[Row] = []
        seen = set()

        def place_one(e, sheet_name: str, title: str | None, *, in_block: bool = False) -> Row | None:
            if isinstance(e, placement.Panel):
                self.panels.append(_PanelSpec(sheet_name, e))
                return None
            if isinstance(e, placement.Sensitivity):
                r_unit = getattr(e.row_values[0], "unit", None) or getattr(e.row_values[0], "dims", None)
                c_unit = getattr(e.col_values[0], "unit", None) or getattr(e.col_values[0], "dims", None)
                r_var = S.Named("__sens_row__", S.Const(1.0, r_unit))
                c_var = S.Named("__sens_col__", S.Const(1.0, c_unit))
                expr = S.lift(e.formula(r_var, c_var))
                self.panels.append(_PanelSpec(sheet_name, e, row_var=r_var, col_var=c_var, expr=expr))
                return None
            if isinstance(e, placement.Block):
                label = e.label or e.target.name
                if not label:
                    raise ValueError(f"b.block: an unnamed target series needs label= (on sheet {sheet_name!r})")
                if id(e.target) in self.row_of:
                    raise ValueError(f"{label!r} is placed twice; show it again with b.link")
                comp_rows: list[Row] = []
                for sub in e.rows:
                    comp = place_one(sub, sheet_name, title, in_block=True)
                    if comp is not None:
                        comp_rows.append(comp)
                self.add_named(e.target, label, title, sheet=sheet_name)
                tot_row = self.row_of[id(e.target)]
                tot_row.total = e.total
                tot_row.fmt = e.fmt
                tot_row.verify = e.verify
                tot_row.block_rows = comp_rows
                tot_row.block_sign = e.sign
                tot_row.factor = e.sign
                return tot_row
            if isinstance(e, placement.Link) or isinstance(e, Input) or \
                    (isinstance(e, placement.Line) and isinstance(e.series, Input)):
                target = e.target if isinstance(e, placement.Link) else e
                node = target.series if isinstance(target, placement.Line) else target
                label = e.label if isinstance(e, (placement.Link, placement.Line)) else None
                row = Row(node, label or getattr(target, "label", None) or node.name, title, sheet=sheet_name,
                          link=True, in_block=in_block)
                if isinstance(e, placement.Link):
                    row.link_sign = e.sign
                    row.total = e.total
                    row.fmt = e.fmt
                elif isinstance(e, placement.Line):
                    row.factor = e.sign * e.scale
                    row.total = e.total
                    row.fmt = e.fmt
                self.rows.append(row)
                links.append(row)
                return row
            node, label = (e.series, e.label) if isinstance(e, placement.Line) else (e, None)
            if in_block and id(node) in self.row_of and not (isinstance(e, placement.Line) and e.formula is not None):
                row = Row(node, label or node.name, title, sheet=sheet_name, link=True, in_block=True)
                if isinstance(e, placement.Line):
                    row.link_sign = e.sign
                    row.factor = e.scale
                    row.total = e.total
                    row.fmt = e.fmt
                self.rows.append(row)
                links.append(row)
                return row
            label = label or node.name
            if not label:
                raise ValueError(f"b.row: an unnamed series needs label= (on sheet {sheet_name!r})")
            if id(node) in self.row_of:
                raise ValueError(f"{label!r} is placed twice; show it again with b.link")
            self.add_named(node, label, title, sheet=sheet_name)
            placed = self.row_of[id(node)]
            placed.in_block = in_block
            if isinstance(e, placement.Line):
                placed.factor = e.sign * e.scale
                placed.total = e.total
                placed.formula = e.formula
                placed.verify = e.verify
                placed.fmt = e.fmt
            return placed

        for sh in self.layout:
            key = sh.name.casefold()
            if key in seen:
                raise ValueError(f"two sheets are named {sh.name!r}")
            seen.add(key)
            for entry in sh.entries:
                inside = entry.entries if isinstance(entry, placement.Section) else (entry,)
                title = entry.title if isinstance(entry, placement.Section) else None
                for e in inside:
                    place_one(e, sh.name, title)
        for row in links:
            if isinstance(row.node, Input):
                continue
            if id(row.node) not in self.row_of:
                raise ValueError(f"b.link({row.label!r}): the row it shows is not placed; place it with b.row")
            self._register_local_link(row.sheet, row)

    def _verify_periods(self, row: Row) -> range:
        if row.node.scalar:
            return range(1)
        au = self.m.actual_until
        if au is None:
            return range(self.n)
        inner = row.node.expr if isinstance(row.node, S.Named) and row.node.expr is not None else row.node
        if isinstance(inner, ledger._CashFlow) or self._is_actual_data_cell(row, 0):
            return range(au + 1, self.n)
        return range(self.n)

    def _scenario_render(self, name: str) -> "Result":
        if name not in self._scenario_renders:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._scenario_renders[name] = self.m.render(scenario=name, checks="warn")
        return self._scenario_renders[name]

    def _perturb_renders(self, count: int = 5) -> list[tuple[str, "Result"]]:
        import warnings
        rng = random.Random(20261125)
        time_dims = frozenset({("time", 1)})
        candidates: list[tuple[Input, Any]] = []
        for node, base_val in self.input_rows:
            if node.choices is not None:
                continue
            if node.unit == time_dims:
                continue
            if isinstance(base_val, bool):
                continue
            if isinstance(base_val, (int, float)):
                if base_val == 0:
                    continue
                if not node.unit and isinstance(node.default, int) and 1900 <= base_val <= 2100:
                    continue
                candidates.append((node, base_val))
            elif isinstance(base_val, list) and base_val and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in base_val):
                if any(v != 0 for v in base_val):
                    candidates.append((node, base_val))
        if not candidates:
            return []
        out: list[tuple[str, "Result"]] = []
        for idx in range(count):
            overrides: dict[Input, Any] = {}
            for node, base_val in candidates:
                factor = rng.uniform(0.85, 0.95) if rng.random() < 0.5 else rng.uniform(1.05, 1.15)
                if isinstance(base_val, list):
                    vals = []
                    for v in base_val:
                        nv = v * factor
                        if not node.unit and 0 < v < 1:
                            nv = min(max(nv, 0.01), 0.95)
                        vals.append(nv)
                    overrides[node] = S.Data(vals, node.unit)
                else:
                    nv = base_val * factor
                    if not node.unit and 0 < base_val < 1:
                        nv = min(max(nv, 0.01), 0.95)
                    overrides[node] = Quantity(nv, node.unit) if node.unit else nv
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    out.append((f"perturb#{idx + 1}", self.m.render(inputs=overrides, checks="warn")))
            except Exception:
                continue
        return out

    def _displayed_value(self, row: Row, case_r: "Result", t: int):
        if row.link:
            val = case_r._r.value(row.node, None if row.node.scalar else t)
            if val is None:
                return 0.0
            home = self.row_of.get(id(row.node))
            denom = (home.factor if home is not None else 1) * row.factor * row.link_sign
            return val / denom
        expr = self._active_expr(row)
        val = case_r._r.value(expr, None if expr.scalar else t)
        if val is None:
            return 0.0
        return val / row.factor

    def verify_rewrites(self):
        """Verify every b.row(..., formula=...) and b.block(...) against boki across base, scenarios, and perturbations."""
        targets = [r for r in self.rows if (r.formula is not None or r.block_rows is not None) and r.verify != "off"]
        if not targets:
            return
        cases: list[tuple[str, "Result"]] = [("base", self.r)]
        need_perturb = any(r.verify == "perturb" for r in targets)
        if need_perturb:
            scenario_names = sorted({s for node, _ in self.input_rows for s in node.scenarios})
            for sname in scenario_names:
                try:
                    cases.append((f"scenario={sname!r}", self._scenario_render(sname)))
                except Exception:
                    pass
            cases.extend(self._perturb_renders(5))
        labels = [p.label for p in self.m.timeline.periods]
        for row in targets:
            row_cases = cases[:1] if row.verify == "base" else cases
            periods = self._verify_periods(row)
            for case_name, case_r in row_cases:
                for t in periods:
                    want = case_r._r.value(row.node, None if row.node.scalar else t)
                    if want is None:
                        continue
                    if row.block_rows is not None:
                        expected = want / row.factor
                        got = sum(self._displayed_value(comp, case_r, t) for comp in row.block_rows)
                        kind = "b.block"
                    else:
                        expected = want
                        got = case_r._r.value(row.formula, None if row.formula.scalar else t)
                        kind = "b.row(formula=...)"
                    if got is None or not math.isclose(float(got), float(expected), rel_tol=1e-6, abs_tol=1e-4):
                        diff = (float(got) - float(expected)) if got is not None else float("nan")
                        raise EquivalenceError(
                            f"{kind} {row.label!r} mismatch in {case_name} at period {labels[t]}: "
                            f"boki={expected}, rewrite={got} (diff={diff:+.6g})"
                        )

    def collect(self):
        """The rows the workbook must show: placed rows, named series, the statements, postings and checks.
        With a layout, a named series that is not placed is written inline where it is used."""
        for name, node in self.m._named.items():
            if isinstance(node, Input):
                self.inputs[id(node)] = 0
                self.input_rows.append((node, self.r[node]))
        self.place_layout()
        for name, node in self.m._named.items():
            if not isinstance(node, Input) and not self.layout:
                self.add_named(node, name, "model")
        populate_books = self.style.statements or not self.omit_unused_model
        if populate_books:
            for e in self.books:
                for kind in e.layout.pl_kinds:
                    k = getattr(e.pl, kind)
                    for item in k.items:
                        self.add_named(item, item.name, f"{e.name} PL")
                    if k.items:
                        self.add_row(k.total, f"{kind} (total)", f"{e.name} PL")
                for stage in e.layout.stages:
                    self.add_row(getattr(e.pl, stage.name), stage.name, f"{e.name} PL")
                attribution = getattr(e, "_group_profit_attribution", None)
                if attribution is not None:
                    self.add_row(attribution["nci"], attribution["nci_label"], f"{e.name} PL")
                    self.add_row(attribution["parent"], attribution["parent_label"], f"{e.name} PL")
                if e._oci_components:
                    self.add_row(e.other_comprehensive_income, "other_comprehensive_income", f"{e.name} PL")
                    for component in e._oci_components.values():
                        self.add_named(component.line, component.name, f"{e.name} PL")
                    self.add_named(e.comprehensive_income, "comprehensive_income", f"{e.name} PL")
                for a in e._accounts:
                    if a.side in ("asset", "liability", "equity"):
                        self.add_row(e._balance(a), a.name, f"{e.name} BS")
                self.add_row(e._cum_profit, "profit to date", f"{e.name} BS")
                self.add_row(e._equity_total, "equity (incl. profit to date)", f"{e.name} BS")
                if getattr(e, "_group_profit_attribution", None) is not None:
                    self.add_row(e.bs.nci.total, "noncontrolling interests (total)", f"{e.name} BS")
                for cls in _cf_classes(e):
                    self.add_row(getattr(e.cf, cls), f"{cls} cash flow", f"{e.name} CF")
                for p in e._postings:
                    if id(p.amount) not in self.inputs and not isinstance(p.amount, S.Const):
                        self.add_row(p.amount, p.name, f"{e.name} postings", helper=True)
        for e in self.books:
            # a balance-sheet line item is its balance
            for kind in e.layout.bs:
                for item in getattr(e.bs, kind.name).items:
                    target = self.row_of.get(id(item.expr))
                    if target is not None:
                        self.row_of[id(item)] = target
        if self.style.statements:                          # schedules start from each account's opening balance
            for e in self.books:
                for accounts in schedule_accounts(e).values():
                    for a in accounts:
                        o = a.opening
                        if o is not None and not isinstance(o, (S.Const, ledger._OpeningPlug)) \
                                and id(o) not in self.inputs:
                            self.add_row(o, f"{a.name} (opening)", f"{e.name} BS", helper=True)
        self.check_rows: list[tuple[str, S.Series]] = []
        if self.emit_checks:
            self.add_checks()

    def _sheet_start_row(self, sheet_name: str) -> int:
        if sheet_name != "Model" and self.style.band is not None:
            has_rows = any(r.sheet == sheet_name for r in self.rows)
            return 5 if has_rows else 4
        return 3

    def place(self):
        """Number the rows of each sheet: sections in the order collected, a blank line between them."""
        self.headers: list[tuple[str, int, str]] = []
        at: dict[str, tuple[int, object]] = {}
        for row in self.rows:
            start = self._sheet_start_row(row.sheet)
            number, section = at.get(row.sheet, (start, ...))
            if row.section != section:
                if number > start:
                    number += 1
                if row.section is not None:
                    self.headers.append((row.sheet, number, row.section))
                    number += 1
            row.number = number
            at[row.sheet] = (number + 1, row.section)
        self.panel_cells.clear()
        for spec in self.panels:
            start = self._sheet_start_row(spec.sheet)
            number, _ = at.get(spec.sheet, (start, ...))
            if number > start:
                number += 1
            spec.start_row = number
            if isinstance(spec.panel, placement.Sensitivity):
                n_rows = len(spec.panel.row_values)
            else:
                n_rows = len(spec.panel.rows)
                hdr_r = number + 1
                for idx, (_, vals, _) in enumerate(spec.panel.rows):
                    rr = hdr_r + 1 + idx
                    for j, val in enumerate(vals):
                        if isinstance(val, S.Series) and val.scalar and not isinstance(val, (Input, S.Const)):
                            coord = (spec.sheet, rr, FIRST_COL + j)
                            if id(val) not in self.row_of and id(val) not in self.panel_cells:
                                self.panel_cells[id(val)] = coord
                            if isinstance(val, S.Named) and val.expr is not None \
                                    and not isinstance(val.expr, (Input, S.Const)) \
                                    and id(val.expr) not in self.row_of and id(val.expr) not in self.panel_cells:
                                self.panel_cells[id(val.expr)] = coord
            at[spec.sheet] = (number + 2 + n_rows + 1, None)
        if self.scenarios is not None:
            scalars = [(n, v) for n, v in self.input_rows if n.scalar]
            series_inputs = [(n, v) for n, v in self.input_rows if not n.scalar]
            r = 6
            for node, _ in scalars:
                self.inputs[id(node)] = r
                r += 1
            if series_inputs:
                r += 2
                for node, _ in series_inputs:
                    self.inputs[id(node)] = r
                    r += 1
                    if node.scenarios:
                        r += len(self.scenarios)
            first = r + 1
        else:
            for i, (node, _) in enumerate(self.input_rows):
                self.inputs[id(node)] = 3 + i
            first = 3 + len(self.input_rows) + 1
        for i, table in enumerate(self.tables.values()):
            table.row = first + 3 * i
        self._formula_sizes.clear()

    def collect_tables(self):
        """Each lookup's table, written as two rows on the Inputs sheet (keys, then values) after the inputs.
        A table whose values are not all constants stays a value cell."""
        self.tables: dict[int, _Table] = {}
        for row in list(self.rows):
            if row.link or row.block_rows is not None:
                continue
            root = self._active_expr(row)
            for node in [root, *self.inline(root).values()]:
                if not isinstance(node, lib._Lookup) or id(node) in self.tables \
                        or not all(isinstance(v, S.Const) for v in node.values):
                    continue
                label = f"{row.label} table" if root is node else f"{row.label}: lookup table"
                shown = {S.written_unit(v) for v in node.values}
                u = shown.pop() if len(shown) == 1 else None
                factor = u.scale if u is not None and _labeled(u) and node.unit is not None else 1
                self.tables[id(node)] = _Table(node, label, u if factor != 1 else None, factor)

    def add_checks(self):
        """Rows that are 1 when a check holds: each entity's books tie out, and every m.check."""
        for e in self.books:
            if e._currency is None:
                continue
            tol = S.Const(0.005, e._currency)               # half a cent (or yen): formulas are exact
            cf_parts = [getattr(e.cf, cls) for cls in _cf_classes(e)]
            flows = cf_parts[0]
            for part in cf_parts[1:]:
                flows = flows + part
            cf_ok = abs(flows - (e.bs.cash - e.bs.cash.opening)) < tol
            if self.m.actual_until is not None:
                cf_ok = S.Const(True).where(self.m.is_actual, cf_ok)
            for label, cond in (
                    (f"{e.name}: assets = liabilities + equity",
                     abs(e.bs.total_assets - e.bs.total_liabilities - e.bs.total_equity) < tol),
                    (f"{e.name}: cash flow = change in cash", cf_ok)):
                node = S.Named(label, cond)
                if not self.omit_unused_model:
                    self.add_row(node, label, "checks")
                self.check_rows.append((label, node))
        for c in self.m._checks:
            if c.level == "off":
                continue
            if not self.omit_unused_model:
                self.add_row(c.cond, c.message, "checks")
            self.check_rows.append((c.message, c.cond))

    def _active_children(self, node) -> list:
        if self.omit_unused_model and isinstance(node, S.Where) and self.fixed(node.cond):
            out = []
            taken_true = any(bool(self.r._r.value(node.cond, t)) for t in range(self.n))
            taken_false = any(not bool(self.r._r.value(node.cond, t)) for t in range(self.n))
            if taken_true:
                out.append(node.then)
            if taken_false:
                out.append(node.else_)
            return out
        return self.children(node)

    def promote(self):
        """Give rows to what the chosen translations need (recurrences, data, ranges). A sub-expression
        used twice is written inline where it is used; shorten() gives it a row only if a formula gets too long."""
        uses: dict[int, int] = {}
        nodes: dict[int, S.Series] = {}
        need: set[int] = set()

        def visit(node, top=False):
            key = id(node)
            if not top:
                uses[key] = uses.get(key, 0) + 1
                if key in self.row_of:
                    return
            if key in nodes:
                return
            nodes[key] = node
            if _needs_own_row(node, self.has_row):
                need.add(key)
            need.update(id(s) for s in _needs_rows_for(node))
            for child in self._active_children(node):
                visit(child)

        for row in list(self.rows):
            if row.link or row.block_rows is not None:
                continue
            visit(self._active_expr(row), top=True)
        for spec in self.panels:
            if isinstance(spec.panel, placement.Sensitivity):
                for val in (*spec.panel.row_values, *spec.panel.col_values):
                    if isinstance(val, S.Series):
                        visit(val, top=True)
                if spec.expr is not None:
                    axis_ids = {id(spec.row_var), id(spec.col_var)}
                    prev_visit = visit
                    def visit_sens(node, top=False):
                        if id(node) in axis_ids:
                            return
                        prev_visit(node, top=top)
                    visit_sens(spec.expr, top=True)
            else:
                for _, vals, _ in spec.panel.rows:
                    for val in vals:
                        if isinstance(val, S.Series):
                            visit(val, top=True)
        if self.omit_unused_model and self.emit_checks:
            for _, cond in self.check_rows:
                visit(cond, top=True)
        for key, node in nodes.items():
            if key in self.row_of or key in self.inputs or isinstance(node, S.Const):
                continue
            if key in need and isinstance(node, (_Time, statements._Days)):
                self.add_timeline(node)
            elif key in need:
                self.add_row(node, _helper_label(node), "helpers", helper=True)
            elif uses.get(key, 0) >= 2 and self.children(node):
                self.shared.append(node)

    def add_timeline(self, node):
        """A calendar series (m.t, m.date, day counts) is a row of the timeline at the top of the Model sheet,
        like the period number and date rows a modeller puts above the calculation."""
        row = Row(node, _TIMELINE.get(node.name, node.name), "timeline")
        first = next((i for i, r in enumerate(self.rows) if r.sheet == "Model" and r.section != "timeline"),
                     len(self.rows))
        self.rows.insert(first, row)
        self.row_of[id(node)] = row

    def shorten(self):
        """Give a row to a sub-expression where writing it inline makes a formula longer than MAX_FORMULA: in
        each such row, the shared one that is longest inline (or, when none is shared, a spread: its formula grows
        with the period, so several summed in one row soon pass the limit), until every formula fits."""
        while True:
            added = False
            for row in list(self.rows):
                if row.link or row.block_rows is not None:
                    continue
                expr = self._active_expr(row)
                if self.longest(expr, top=True) <= MAX_FORMULA:
                    continue
                inside = self.inline(expr)
                candidates = [n for n in self.shared if id(n) in inside and id(n) not in self.row_of] or \
                    [n for n in inside.values() if isinstance(n, shapes._Spread)]
                if candidates:
                    pick = max(candidates, key=self.longest)
                    self.add_row(pick, _helper_label(pick), "helpers", helper=True)
                    added = True
            if not added:
                return
            self.place()

    def prune_unused_model(self):
        """Drop Model rows not referenced by any placed sheet, panel, statement, or check."""
        used_rows: set[int] = set()
        seen_nodes: set[tuple[int, bool]] = set()
        stack: list[tuple[S.Series, bool]] = []

        def enqueue_row(r: Row):
            if id(r) in used_rows:
                return
            used_rows.add(id(r))
            if r.block_rows is not None:
                return
            if r.link:
                home = self.row_of.get(id(r.node))
                if home is not None:
                    enqueue_row(home)
                return
            stack.append((self._active_expr(r), True))

        for r in self.rows:
            if r.sheet != "Model":
                enqueue_row(r)
        for spec in self.panels:
            if isinstance(spec.panel, placement.Sensitivity):
                for val in (*spec.panel.row_values, *spec.panel.col_values):
                    if isinstance(val, S.Series):
                        stack.append((val, False))
                if spec.expr is not None:
                    stack.append((spec.expr, False))
            else:
                for _, vals, _ in spec.panel.rows:
                    for val in vals:
                        if isinstance(val, S.Series):
                            stack.append((val, False))
        if self.emit_checks:
            for _, cond in self.check_rows:
                stack.append((cond, False))
        if self.style.statements:
            for r in self.rows:
                if r.sheet == "Model":
                    enqueue_row(r)

        while stack:
            node, is_root = stack.pop()
            key = id(node)
            if (key, is_root) in seen_nodes:
                continue
            seen_nodes.add((key, is_root))
            if not is_root:
                ref_row = self.row_of.get(key)
                if ref_row is not None:
                    enqueue_row(ref_row)
                    continue
            for child in self._active_children(node):
                stack.append((child, False))

        before = len(self.rows)
        self.rows = [r for r in self.rows if r.sheet != "Model" or id(r) in used_rows]
        if len(self.rows) != before:
            kept = {id(r) for r in self.rows}
            self.row_of = {k: r for k, r in self.row_of.items() if id(r) in kept}
            self.place()
        self.report.unplaced = [r.label for r in self.rows if r.sheet == "Model"]

    def longest(self, node, top=False) -> int:
        """Length of the node's formula at its longest period (the first, second and last are sampled)."""
        if _is_data(node):
            return 0
        best = 0
        for t in sorted({0, 1, self.n - 1} & set(range(self.n))):
            try:
                best = max(best, len(self.sized_formula(node, t, top)))
            except (Untranslatable, KeyError):
                pass
        return best

    def sized_formula(self, node, t, top=False) -> str:
        if not top:
            ref = self.ref(node, t)
            if ref is not None:
                return ref
        key = self.sheet_now, id(node), t
        if key not in self._formula_sizes:
            self._sizing += 1
            try:
                formula = self.expand(node, t)
            finally:
                self._sizing -= 1
            self._formula_sizes[key] = formula if len(formula) <= 8192 else "#" * 8193
        return self._formula_sizes[key]

    def inline(self, root) -> dict[int, S.Series]:
        """The nodes written inside root's formula, by id (stopping at other rows and inputs)."""
        seen: dict[int, S.Series] = {}
        stack = list(self.children(root))
        while stack:
            node = stack.pop()
            key = id(node)
            if key in seen or key in self.row_of or key in self.inputs:
                continue
            seen[key] = node
            stack.extend(self.children(node))
        return seen

    def children(self, node) -> list:
        if isinstance(node, (S.Named,)) and node.expr is not None:
            return [node.expr]
        if isinstance(node, S.Op):
            return node.args
        if isinstance(node, S.Lag):
            return [node.src, node.k] + ([S.lift(node.fill)] if node.fill is not None else [])
        if isinstance(node, S.Where):
            return [node.cond, node.then, node.else_]
        if isinstance(node, S.At) and isinstance(node.t, S.Series):
            return [node.src, node.t]
        if isinstance(node, (S.At, S.Cumsum, S.ReverseCumsum, shapes._Spread, shapes._Year)):
            return [node.src]
        if isinstance(node, ledger._OpeningCollected):
            return [node.balance]
        if isinstance(node, shapes._ByYear):
            values = [*node.mapping.values()]
            if node.default is not None:
                values.append(node.default)
            return [S.lift(value) for value in values]
        if isinstance(node, shapes._Step):
            return [S.lift(value) for value in node.mapping.values()]
        if isinstance(node, S.Reduce):
            return node.srcs
        if isinstance(node, lib._RunningIrr):
            return [node.src]
        if isinstance(node, lib._Compound):
            return [node.x0, node.rate]
        if isinstance(node, lib._Index):
            return [node.rate] + ([node.when] if node.when is not None else [])
        if isinstance(node, lib._Fade):
            return [node.a, node.b]
        if isinstance(node, lib._Lookup):
            return [node.x]
        if isinstance(node, lib._Discount):
            return [node.rate]
        if isinstance(node, ledger._Balance):
            if (gap := _target_gap(node)) is not None:
                return [gap.target]
            return [p.amount for p in node.account.debits + node.account.credits] + \
                ([node.account.opening] if node.account.opening is not None else [])
        if isinstance(node, ledger._Opening):
            return [node.balance]
        if isinstance(node, ledger._NOL):
            return [node.base] + [x for x in (node.carried_in, node.cap) if x is not None]
        if isinstance(node, ledger._AssetTradeFlow):
            return [node.basis]
        if isinstance(node, group_series._JgaapNciProfit):
            return [node.raw, node.nci_opening, node.suspended]
        if isinstance(node, group_series._JgaapSuspendedLoss):
            return [node.raw, node.nci_opening]
        if isinstance(node, group_series._GoodwillAmortization):
            return [node.goodwill, node.impairment]
        if isinstance(node, group_series._EquityMethodProfit):
            return [node.raw, node.available, node.suspended, node.sale_retention]
        if isinstance(node, group_series._EquityMethodSuspended):
            return [node.profit.raw, node.profit.available, node.profit.sale_retention]
        if isinstance(node, group_series._EquityMethodAvailable):
            return node.costs + node.other_movements
        if isinstance(node, ledger._Depreciation):
            return [node.book, node.salvage]
        if isinstance(node, ledger._Total):
            return node.items()
        if isinstance(node, ledger._SideTotal):
            return [node.entity._balance(a) for a in node.entity._accounts if a.side == node.side]
        if isinstance(node, ledger._EquityTotal):
            e = node.entity
            if id(e.bs.retained_earnings) in self.row_of:
                return [e.bs.retained_earnings if a.kind == "retained_earnings" else e._balance(a)
                        for a in e._accounts if a.side == "equity"]
            return [e._balance(a) for a in e._accounts if a.side == "equity"] + [e._cum_profit]
        if isinstance(node, ledger._CashFlow):
            e = node.entity
            return [p.amount for p in e._postings
                    if ledger.cash_class(e, p) == node.cls
                    and p.debit not in node.exclude and p.credit not in node.exclude]
        if isinstance(node, ledger._Gap):
            return [node.target, node.balance] + [p.amount for p in node.balance.account.debits
                                                  + node.balance.account.credits if p is not node.posting]
        return []

    # -- formulas ----------------------------------------------------------------------

    @property
    def row_sheets(self) -> set[str]:
        """Sheet names (as written in a reference) that hold model rows."""
        return {_sheet_ref(r.sheet) for r in self.rows}

    def has_row(self, node) -> bool:
        return id(node) in self.row_of or id(node) in self.inputs

    def prev(self, node, t) -> str:
        """The node's own cell in another period (recurrences need a row)."""
        r = self.ref(node, t)
        if r is None:
            raise KeyError(type(node).__name__)
        return r

    def ref(self, node, t, qualified=False) -> str | None:
        """The node's value in period t: its cell (without a sheet name on the sheet being written, with one
        elsewhere), turned back into the value when the row shows it with sign= or scale=."""
        axis = self._axis_refs.get(id(node))
        if axis is not None:
            return axis
        row = self.row_of.get(id(node))
        if row is not None:
            if not qualified and row.sheet != self.sheet_now:
                lr = self.local_links.get((self.sheet_now, id(node)))
                if lr is not None and lr is not self._active_row and lr.number > 0:
                    self.touch(node, t)
                    local = f"$C${lr.number}" if node.scalar else f"{_col(FIRST_COL - 1 + t)}{lr.number}"
                    return _times(local, row.factor * lr.factor * lr.link_sign)
            return _times(self.cell(node, t, qualified), row.factor)
        pcell = self.panel_cells.get(id(node))
        if pcell is not None and pcell != self._active_panel_cell:
            sheet, pr, pc = pcell
            on = "" if not qualified and sheet == self.sheet_now else f"{_sheet_ref(sheet)}!"
            return f"{on}${_col(pc - 1)}${pr}"
        k = self.inputs.get(id(node))
        if k is not None:
            cell = f"Inputs!$C${k}" if node.scalar else f"Inputs!{_col(FIRST_COL - 1 + t)}{k}"
            return _times(cell, self.input_factor.get(id(node), 1))
        return None

    def cell(self, node, t, qualified=False) -> str:
        """The node's own cell, as shown (no sign= or scale= undone): for ranges and links."""
        row = self.row_of[id(node)]
        self.touch(node, t)
        on = "" if not qualified and row.sheet == self.sheet_now else f"{_sheet_ref(row.sheet)}!"
        if node.scalar:
            return f"{on}$C${row.number}"
        return f"{on}{_col(FIRST_COL - 1 + t)}{row.number}"

    def whole_range(self, node) -> str:
        """All periods of a row, Model or Inputs ($C$5:$H$5), for a function that takes the series as a range."""
        last = _col(FIRST_COL - 2 + self.n)
        k = self.inputs.get(id(node))
        if k is not None:
            if self.input_factor.get(id(node), 1) != 1:
                raise Untranslatable("a range over an input shown in its display unit")
            return _range(f"Inputs!$C${k}", f"${last}${k}")
        row = self.row_of.get(id(node))
        if row is None:
            raise KeyError(type(node).__name__)
        if row.factor != 1:
            raise Untranslatable("a range over a row shown with sign= or scale=")
        self.touch(node, 0, self.n - 1)
        on = "" if row.sheet == self.sheet_now else f"{_sheet_ref(row.sheet)}!"
        return _range(f"{on}$C${row.number}", f"${last}${row.number}")

    def prefix_range(self, node, t) -> str:
        """A row's cells from the first period to period t ($C$5:E5), which grows as the formula is filled right."""
        k = self.inputs.get(id(node))
        if k is not None:
            if self.input_factor.get(id(node), 1) != 1:
                raise Untranslatable("a range over an input shown in its display unit")
            return _range(f"Inputs!$C${k}", f"{_col(FIRST_COL - 1 + t)}{k}")
        row = self.row_of.get(id(node))
        if row is None:
            raise KeyError(type(node).__name__)
        if row.factor != 1:
            raise Untranslatable("a range over a row shown with sign= or scale=")
        self.touch(node, 0, t)
        on = "" if row.sheet == self.sheet_now else f"{_sheet_ref(row.sheet)}!"
        return _range(f"{on}$C${row.number}", f"{_col(FIRST_COL - 1 + t)}{row.number}")

    def f(self, node, t) -> str:
        """The formula fragment for `node` in period t (a reference when the node has a row)."""
        if self._sizing:
            return self.sized_formula(node, t)
        r = self.ref(node, t)
        return r if r is not None else self.expand(node, t)

    def span(self, fn: str, node, t0, t1) -> str:
        """fn (SUM, AVERAGE ...) over a row's cells from period t0 to t1, undoing the row's sign= or scale=."""
        row = self.row_of.get(id(node))
        cells = (self.cell(node, t0), self.cell(node, t1)) if row else (self.ref(node, t0), self.ref(node, t1))
        self.touch(node, t0, t1)
        sheet, first = cells[0].rsplit("!", 1) if "!" in cells[0] else ("", cells[0])
        total = f"{fn}({_range((sheet + '!' if sheet else '') + first, cells[1].rsplit('!', 1)[-1])})"
        return _times(total, row.factor) if row else total

    def number(self, node, t) -> str:
        """A cell that starts a running total: a condition alone would stay TRUE/FALSE, which SUM and LOOKUP skip."""
        x = self.f(node, t)
        return f"IF({x},1,0)" if _boolean(node) and self.ref(node, t) is None else x

    def lag_fill(self, node, t) -> str:
        return self.f(S.lift(node.fill), t) if node.fill is not None else "NA()"

    def expand(self, node, t) -> str:
        if _is_actuals_inline(node):
            return _literal(self.r._r.value(node, t))
        if isinstance(node, S.Const):
            return _literal(node.value)
        if isinstance(node, S.Named):
            if node.expr is None:
                raise Untranslatable("undefined")
            return self.f(node.expr, t)
        if isinstance(node, S.Op):
            return self.op(node, t)
        if isinstance(node, S.Lag):
            if not isinstance(node.k, S.Const):
                if node.src.scalar or not self.has_row(node.src):
                    raise Untranslatable("variable lag")
                # the period k before this one, by position in the source row (INDEX, like Python's int(), truncates)
                pos = f"({t + 1}-{self.f(node.k, 0 if node.k.scalar else t)})"
                s = self.read_period(lambda: t - int(self.r._r.value(node.k, None if node.k.scalar else t)))
                if s is None:
                    return f"IF(AND({pos}>=1,{pos}<={self.n}),INDEX({self.whole_range(node.src)},{pos}),{self.lag_fill(node, t)})"
                # boki reads one cell of the row (or the fill): the rest is unread
                inside = 0 <= s < self.n
                whole = self.unread(lambda: self.whole_range(node.src))
                fill = self.unread(lambda: self.lag_fill(node, t)) if inside else self.lag_fill(node, t)
                if whole is None:
                    if inside:
                        return f"IF({pos}={s + 1},{self.f(node.src, s)},NA())"
                    return f"IF(OR({pos}<1,{pos}>{self.n}),{fill},NA())"
                if inside:
                    self.touch(node.src, s)
                return f"IF(AND({pos}>=1,{pos}<={self.n}),INDEX({whole},{pos}),{'NA()' if fill is None else fill})"
            s = t - int(node.k.value)
            if 0 <= s < self.n:
                return self.f(node.src, s)
            return self.lag_fill(node, t)
        if isinstance(node, S.Where):
            if self.fixed(node.cond):
                # A condition on the calendar alone (m.t >= 7) is the same in every scenario: write only the
                # branch that applies. Excel counts references in the other branch as dependencies, and they
                # can form a cycle boki never evaluates (depreciation of an asset before it is in service).
                branch = node.then if self.r._r.value(node.cond, t) else node.else_
                return self.blank_or(branch, t)
            cond = self.f(node.cond, t)
            taken = self.read_period(lambda: bool(self.r._r.value(node.cond, None if node.cond.scalar else t)))
            then, else_ = (self.blank_or(x, t) if taken is None or taken == side else
                           _or_na(self.unread(lambda x=x: self.blank_or(x, t)))
                           for x, side in ((node.then, True), (node.else_, False)))
            return f"IF({cond},{then},{else_})"
        if isinstance(node, S.At):
            if isinstance(node.t, S.Series):
                # a period chosen by an input: INDEX over the row, so the cell follows a changed input
                if node.src.scalar or not self.has_row(node.src) or node.t.unit not in (None, lib._DIMENSIONLESS):
                    raise Untranslatable("a period chosen by a series")
                k = self.f(node.t, 0)
                pos = f"IF({k}<0,{self.n}+{k},{k})+1"                    # -1 is the last period
                s = self.read_period(lambda: self.r._r.period_index(node.t))
                if s is None:
                    return f"INDEX({self.whole_range(node.src)},{pos})"
                whole = self.unread(lambda: self.whole_range(node.src))   # boki reads one cell of the row
                if whole is None:
                    return f"IF({pos}={s + 1},{self.f(node.src, s)},NA())"
                self.touch(node.src, s)
                return f"INDEX({whole},{pos})"
            return self.f(node.src, self.r._r.period_index(node.t))
        if isinstance(node, (shapes._ByYear, shapes._Step)):
            return self.blank_or(S.lift(node.pick(self.r._r, t)), t)
        if isinstance(node, S.Reduce):
            if node.excel is None:
                raise Untranslatable("reduction")
            args = []
            for i, src in enumerate(node.srcs):
                if i in node.excel_first:
                    args.append(self.f(src, 0))
                elif src.scalar:
                    # boki repeats a constant in every period; one cell would be a range of one period
                    raise Untranslatable("a reduction over a constant")
                else:
                    args.append(self.whole_range(src))
            if node.excel_guess:
                # With several roots Excel's IRR finds the one nearest its guess (10% by default); start it
                # at boki's root so both pick the same one (lib._bisect says which).
                args.append(_literal(self.r._r.value(node, None)))
            return _atom(node.excel(*args))       # a/npv(...) must divide by the whole npv, whatever its formula
        if isinstance(node, lib._RunningIrr):
            # IRR over the row's cells so far, started at boki's root so both pick the same one (lib._bisect)
            cells = self.prefix_range(node.src, t)
            return lib._excel_default(f"IRR({cells},{_literal(self.r._r.value(node, t))})", node.default)
        if isinstance(node, shapes._Year):
            ts = node.periods(self.r._r)
            if node.src.scalar:
                one = self.f(node.src, 0)
                return f"({one}*{len(ts)})" if node.kind == "sum" else one
            if node.kind == "last":
                return self.f(node.src, ts[-1])
            if not self.has_row(node.src):
                raise Untranslatable("a reduction over a year of an expression without a row")
            return self.span(_SPAN[node.kind], node.src, ts[0], ts[-1])
        if isinstance(node, S.Cumsum):
            if not node.src.scalar and self.has_row(node.src):
                row = self.row_of.get(id(node.src))
                cells = (self.cell(node.src, 0), self.cell(node.src, t)) if row else \
                    (self.ref(node.src, 0), self.ref(node.src, t))
                self.touch(node.src, 0, t)
                sheet, first = cells[0].rsplit("!", 1) if "!" in cells[0] else ("", cells[0])
                last = cells[1].rsplit("!", 1)[-1]
                col = "".join(ch for ch in first if ch.isalpha())
                first = f"${col}{first[len(col):]}"
                prefix = f"{sheet}!" if sheet else ""
                total = f"SUM({_range(prefix + first, last)})"
                return _times(total, row.factor) if row else total
            return self.number(node.src, 0) if t == 0 else f"({self.prev(node, t - 1)}+{self.f(node.src, t)})"
        if isinstance(node, S.ReverseCumsum):
            last = t == self.n - 1
            return self.number(node.src, t) if last else f"({self.prev(node, t + 1)}+{self.f(node.src, t)})"
        if isinstance(node, lib._Lookup):
            table = self.tables.get(id(node))
            if table is None:
                raise Untranslatable("a lookup table with values that are not constants")
            last = _col(FIRST_COL - 1 + len(node.keys) - 1)
            keys, values = (_range(f"Inputs!$C${k}", f"${last}${k}") for k in (table.row, table.row + 1))
            return _times(f"LOOKUP({self.f(node.x, t)},{keys},{values})", table.factor)
        if isinstance(node, lib._Compound):
            return self.f(node.x0, 0) if t == 0 else f"{self.prev(node, t - 1)}*(1+{self.f(node.rate, t)})"
        if isinstance(node, lib._Index):
            if t == 0:
                return "1"
            prev = self.prev(node, t - 1)
            if node.start is not None and self.m.timeline.periods[t].start < lib._as_date(node.start):
                return prev
            rate = self.f(node.rate, t)
            if node.rate.unit not in (None, lib._DIMENSIONLESS):
                months = self.m.timeline.periods[t].months
                rate = f"((1+{rate}*12)^{_literal(months / 12)}-1)"
            if node.when is not None:
                rate = f"({rate}*{self.f(node.when, t)})"
            return f"({prev}*(1+{rate}))"
        if isinstance(node, lib._Fade):
            t0, t1 = self.r._r.period_index(node.t0), self.r._r.period_index(node.t1)
            a, b = self.blank_or(S.lift(node.a), t), self.blank_or(S.lift(node.b), t)
            if t <= t0:
                return a
            if t >= t1:
                return b
            return f"({a}+({b}-{a})*{t - t0}/{t1 - t0})"
        if isinstance(node, lib._Discount):
            prev = "1" if t == 0 else self.prev(node, t - 1)
            return f"({prev}/(1+{self.f(node.rate, t)}))"
        if isinstance(node, shapes._Spread):
            w = node.kernel.weights
            terms = []
            for s in range(t + 1):
                k = t - s
                weight = w[k] if k < len(w) else (w[-1] if node.hold_last else 0)
                if weight:
                    terms.append(f"{_literal(weight)}*{self.f(node.src, s)}")
            return f"({'+'.join(terms)})" if terms else "0"
        if isinstance(node, ledger._OpeningCollected):
            share = node.fractions[t] if t < len(node.fractions) else 0
            return f"{_literal(share)}*{self.f(node.balance, 0)}" if share else "0"
        if isinstance(node, ledger._Balance):
            if (gap := _target_gap(node)) is not None:
                return self.f(gap.target, t)
            prev = self.prev(node, t - 1) if t > 0 else self.opening(node)
            flow = self.flow(node.account, t)
            sign = "+" if node.sign > 0 else "-"
            return f"({prev}{sign}({flow}))"
        if isinstance(node, ledger._NOL):
            prev = self.prev(node, t - 1) if t > 0 else self.f(node.carried_in, 0) if node.carried_in is not None else "0"
            b = self.f(node.base, t)
            usable = f"MAX({b},0)" if node.cap is None else f"MAX({b},0)*{self.f(node.cap, t)}"
            return f"({prev}+MAX(-{b},0)-MIN({usable},{prev}))"
        if isinstance(node, ledger._AssetTradeFlow):
            terms = []
            for start in range(t + 1):
                elapsed = sum(self.m.timeline.periods[k].months for k in range(start, t))
                months = min(self.m.timeline.periods[t].months, node.life_months - elapsed)
                if months > 0:
                    terms.append(f"{self.f(node.basis, start)}*{_literal(months / node.life_months)}")
            return f"({'+'.join(terms)})" if terms else "0"
        if isinstance(node, group_series._JgaapNciProfit):
            raw = self.f(node.raw, t)
            suspended = self.f(node.suspended, t - 1) if t > 0 else "0"
            opening = self.f(node.nci_opening, t)
            return f"IF({raw}>=0,{raw}-MIN({raw},{suspended}),-MIN(-{raw},MAX({opening},0)))"
        if isinstance(node, group_series._JgaapSuspendedLoss):
            prior = self.prev(node, t - 1) if t > 0 else "0"
            raw = self.f(node.raw, t)
            opening = self.f(node.nci_opening, t)
            loss = f"(-{raw}-MIN(-{raw},MAX({opening},0)))"
            return f"IF({raw}>=0,MAX({prior}-{raw},0),{prior}+{loss})"
        if isinstance(node, group_series._GoodwillAmortization):
            if t < node.period:
                return "0"
            elapsed = sum(self.m.timeline.periods[k].months for k in range(node.period, t))
            remaining = node.life_months - elapsed
            if remaining <= 0:
                return "0"
            opening = [self.f(node.goodwill, node.period)]
            opening.extend(f"-{self.f(node.impairment, k)}-{self.prev(node, k)}"
                           for k in range(node.period, t))
            beginning = "(" + "".join(opening) + ")"
            fraction = _literal(min(self.m.timeline.periods[t].months, remaining) / remaining)
            return f"MAX({beginning},0)*{fraction}"
        if isinstance(node, group_series._EquityMethodProfit):
            raw = self.f(node.raw, t)
            if not node.loss_limit:
                return raw
            suspended = f"({self.f(node.suspended, t - 1)}*{self.f(node.sale_retention, t)})" if t > 0 else "0"
            available = self.f(node.available, t)
            return f"IF({raw}>=0,{raw}-MIN({raw},{suspended}),-MIN(-{raw},MAX({available},0)))"
        if isinstance(node, group_series._EquityMethodSuspended):
            prior = f"({self.prev(node, t - 1)}*{self.f(node.profit.sale_retention, t)})" if t > 0 else "0"
            raw = self.f(node.profit.raw, t)
            available = self.f(node.profit.available, t)
            loss = f"(-{raw}-MIN(-{raw},MAX({available},0)))"
            return f"IF({raw}>=0,MAX({prior}-{raw},0),{prior}+{loss})"
        if isinstance(node, group_series._EquityMethodAvailable):
            parts = []
            for series in node.costs + node.other_movements:
                periods = (0,) if series.scalar else range(t + 1)
                parts.extend(self.f(series, period) for period in periods)
            parts.extend(self.f(node.profit, period) for period in range(t))
            return f"MAX(0,{'+'.join(parts) if parts else '0'})"
        if isinstance(node, ledger._Depreciation):
            start = self.r._r.period_index(node.at)
            if t <= start:
                return "0"
            k = _literal(self.m.timeline.periods[t].months / node.life_months)
            opening, salvage = self.f(node.book, t - 1), self.f(node.salvage, t)
            room = f"MAX({opening}-{salvage},0)"
            if node.method_at(self.r._r, t) == "straight":
                return f"MIN(({self.f(node.book, start)}-{salvage})*{k},{room})"
            return f"MIN({opening}*2*{k},{room})"
        if isinstance(node, ledger._Opening):
            return self.prev(node.balance, t - 1) if t > 0 else self.opening(node.balance)
        if isinstance(node, ledger._Total):
            return _sum([self.f(i, t) for i in node.items()])
        if isinstance(node, ledger._SideTotal):
            e = node.entity
            return _sum([self.f(e._balance(a), t) for a in e._accounts if a.side == node.side])
        if isinstance(node, ledger._EquityTotal):
            e = node.entity
            if id(e.bs.retained_earnings) in self.row_of:
                parts = [self.f(e.bs.retained_earnings if a.kind == "retained_earnings" else e._balance(a), t)
                         for a in e._accounts if a.side == "equity"]
                return _sum(parts)
            parts = [self.f(e._balance(a), t) for a in e._accounts if a.side == "equity"] + [self.f(e._cum_profit, t)]
            return f"({'+'.join(parts)})"
        if isinstance(node, ledger._CashFlow):
            e = node.entity
            parts = []
            for p in e._postings:
                if ledger.cash_class(e, p) != node.cls or p.debit in node.exclude or p.credit in node.exclude:
                    continue
                parts.append(("+" if p.debit is e._cash_account else "-") + self.f(p.amount, t))
            return f"({''.join(parts).lstrip('+')})" if parts else "0"
        if isinstance(node, ledger._Gap):
            b = node.balance
            prev = self.prev(b, t - 1) if t > 0 else self.opening(b)
            others = []
            for sign, postings in (("+", b.account.debits), ("-", b.account.credits)):
                others += [sign + self.f(p.amount, t) for p in postings if p is not node.posting]
            other = "".join(others).lstrip("+") or "0"
            s = "" if b.sign > 0 else "-"
            return f"({self.f(node.target, t)}-{prev}-{s}({other}))"
        raise Untranslatable(type(node).__name__.strip("_"))

    def blank_or(self, node, t) -> str:
        """A branch with no value (x.where(cond) leaves the other periods empty) is written as "": like boki,
        Excel's SUM, MIN and MAX then skip it (NA() would turn the sum into an error)."""
        if isinstance(node, S.Const) and node.value is None:
            return '""'
        return self.f(node, t)

    # -- what boki reads ----------------------------------------------------------------------
    # break_cycles() writes each Model cell once with a _Cell that records what the formula refers to, and which
    # references boki does not read in that period. write_rows() writes the guarded cells again with the guards.

    def touch(self, node, t0, t1=None) -> None:
        """Record that the cell being written refers to node's cells from period t0 to t1."""
        now = self._now
        row = self.row_of.get(id(node))
        if now is None or not now.record or row is None:
            return
        cells = now.read if now.open is None else now.unread.setdefault(now.open, set())
        if row.node.scalar:
            cells.add((id(row), 0))
        else:
            cells.update((id(row), s) for s in range(t0, (t0 if t1 is None else t1) + 1))

    def read_period(self, find):
        """find() (which branch boki takes, which period it reads), or None when that is not needed or not known:
        then the whole formula counts as read."""
        now = self._now
        if now is None or not (now.record or self.guards):
            return None
        try:
            return find()
        except Exception:
            return None

    def unread(self, write) -> str | None:
        """write(): a part of the cell's formula boki does not read in this period. None where break_cycles()
        guards that part, so the caller writes NA() (or the one cell boki reads) instead."""
        now = self._now
        if now is None or now.open is not None:
            return write()                 # inside an unread part, everything is unread with it
        part = now.parts
        now.parts += 1
        if (now.key, part) in self.guards:
            now.guarded = True
            return None
        now.open = part
        try:
            return write()
        finally:
            now.open = None

    def break_cycles(self):
        """Guard the fewest unread parts of formulas whose references would make a circular reference in Excel.

        boki evaluates a cell from the cells it reads in that period; Excel's dependency graph also counts the IF
        branch that is not taken and every cell of a row an INDEX picks one from. When those references close a
        loop, the export would be circular where boki is not. Each Model cell is written once here, recording
        what it reads and, per unread part, what that part refers to. In each loop (a strongly connected set of
        cells) every unread part that refers back into it is guarded first; then, in a fixed order, each guard is
        lifted again unless that would close a loop. Rows with the most guarded parts are tried first, so the
        guards that stay are the few cells the loops pass through (often the masked periods of a reduction).
        A guarded part is written as NA(): the cell keeps its live condition and its formula for the cells boki
        reads, and shows #N/A if changed inputs in the workbook make it read that part (export again then)."""
        graph: dict[tuple[int, int], tuple[set, dict]] = {}
        sheet = self.sheet_now
        for row in self.rows:
            if row.link or (row.block_rows is None and row.formula is None and _is_data(row.node)):
                continue
            self.sheet_now = row.sheet
            if row.block_rows is not None:
                for t in range(1 if row.node.scalar else self.n):
                    read: set = set()
                    for comp in row.block_rows:
                        target = self.row_of.get(id(comp.node)) if comp.link else comp
                        if target is not None:
                            read.add((id(target), 0 if target.node.scalar else t))
                    graph[(id(row), t)] = (read, {})
                continue
            expr = self._active_expr(row)
            self._active_row = row
            for t in range(1 if row.node.scalar else self.n):
                if self._is_actual_data_cell(row, t):
                    graph[(id(row), t)] = (set(), {})
                    continue
                now = self._now = _Cell((id(row), t), record=True)
                try:
                    self._formulas[now.key] = self.expand(expr, t)
                except (Untranslatable, KeyError):
                    now.read, now.unread = set(), {}          # written as a value: it refers to nothing
                finally:
                    self._now = None
                graph[now.key] = (now.read, now.unread)
            self._active_row = None
        self.sheet_now = sheet
        edges = {u: read.union(*unread.values()) for u, (read, unread) in graph.items()}
        comp = _components(edges)
        loops = {u for u in edges if comp[u][1] > 1 or u in edges[u]}
        candidates = [(u, part) for u in loops for part, cells in graph[u][1].items()
                      if any(comp.get(v, (None,))[0] == comp[u][0] for v in cells)]
        if not candidates:
            return
        index = {id(row): i for i, row in enumerate(self.rows)}
        per_row: dict[int, int] = {}
        for (row, _), _ in candidates:
            per_row[row] = per_row.get(row, 0) + 1
        candidates.sort(key=lambda c: (-per_row[c[0][0]], index[c[0][0]], c[0][1], c[1]))
        guards = set(candidates)
        live = {u: graph[u][0].union(*(cells for part, cells in graph[u][1].items() if (u, part) not in guards))
                for u in edges}
        for u, part in candidates:
            extra = graph[u][1][part] - live[u]
            if not _reaches(extra, u, live, comp):
                live[u] |= extra
                guards.discard((u, part))
        self.guards = guards
        after = _components(live)
        own = {u for u in live if after[u][1] > 1 or u in live[u]}
        rows = {id(row): row for row in self.rows}
        labels = [p.label for p in self.m.timeline.periods]

        def where(cells):
            by_row: dict[int, list[int]] = {}
            for row, t in sorted(cells, key=lambda c: (index[c[0]], c[1])):
                by_row.setdefault(row, []).append(t)
            return "; ".join(f"{rows[r].label.strip()} " + ", ".join(
                labels[t] if not rows[r].node.scalar else "(all periods)" for t in ts) for r, ts in by_row.items())
        cells = {u for u, _ in guards}
        if cells:
            self.guard_notes.append(
                f"{len(cells)} cells write a part of their formula that boki does not read in that period as NA(): "
                f"written out, it would make a circular reference in Excel that boki does not have. {where(cells)}. "
                "They show #N/A if changed inputs in the workbook make them read that part; export again from boki "
                "for those inputs.")
        if own:
            self.guard_notes.append(f"boki itself has a circular reference at {where(own)}: Excel will report it.")

    def fixed(self, node) -> bool:
        """True when a node depends only on the timeline and constants (no inputs, data or results)."""
        cache = self._fixed
        key = id(node)
        if key not in cache:
            if isinstance(node, (S.Const, _Time)):
                cache[key] = True
            elif isinstance(node, (S.Op, S.Where)) or \
                    isinstance(node, S.Named) and node.expr is not None and type(node) is S.Named:
                cache[key] = all(self.fixed(c) for c in self.children(node))
            else:
                cache[key] = False
        return cache[key]

    def opening(self, balance) -> str:
        o = balance.account.opening
        if o is None:
            return "0"
        if isinstance(o, ledger._OpeningPlug):
            return _literal(self.r._r.value(o, None))
        return self.f(o, 0)

    def flow(self, account, t) -> str:
        parts = [f"+{self.f(p.amount, t)}" for p in account.debits] + [f"-{self.f(p.amount, t)}" for p in account.credits]
        return "".join(parts).lstrip("+") or "0"

    def op(self, node, t) -> str:
        fn, a = node.fn, node.args
        if fn in _BINARY:
            x, y = self.f(a[0], t), self.f(a[1], t)
            if fn in (operator.add, operator.sub) and y == "0":
                return x                                        # an empty subtotal: (x+0) is x
            if fn is operator.add and x == "0":
                return y
            if fn in (operator.mul, operator.truediv) and y == "1" and not _boolean(a[0]):
                return x                                        # times a unit of scale 1 (x*USD): x
            if fn is operator.mul and x == "1" and not _boolean(a[1]):
                return y
            if fn is operator.sub and (inner := _unwrap_neg(y)) is not None:
                return f"({x}+{inner})"
            if fn is operator.sub and (terms := _unwrap_neg_sum(y)) is not None:
                return f"({x}+{'+'.join(terms)})"
            if fn is operator.add and y.startswith("-") and y[1:].replace(".", "", 1).isdigit():
                return f"({x}{y})"
            return f"({x}{_BINARY[fn]}{y})"
        if fn is operator.neg:
            return f"(-{self.f(a[0], t)})"
        if fn is operator.abs:
            return f"ABS({self.f(a[0], t)})"
        if fn is S._not:
            return f"NOT({self.f(a[0], t)})"
        if fn in _FUNCS:
            return f"{_FUNCS[fn]}({','.join(self.f(x, t) for x in a)})"
        if fn is S._round_half_up:
            return f"ROUND({self.f(a[0], t)},0)"
        if fn in _ROUNDS:
            return f"{_ROUNDS[fn]}({self.f(a[0], t)},{self.f(a[1], t)})"
        if fn is math.ceil:
            return f"(-INT(-{self.f(a[0], t)}))"
        if fn in (S._add_days, S._sub_days):
            return f"({self.f(a[0], t)}{'+' if fn is S._add_days else '-'}{self.f(a[1], t)})"
        if fn is S._days_between:
            return f"({self.f(a[0], t)}-{self.f(a[1], t)})"
        if fn is math.floor:
            return f"INT({self.f(a[0], t)})"
        if fn is operator.mod:
            return f"MOD({self.f(a[0], t)},{self.f(a[1], t)})"
        if fn is operator.floordiv:
            return f"INT({self.f(a[0], t)}/{self.f(a[1], t)})"
        if fn in _MATH:
            return f"{_MATH[fn]}({self.f(a[0], t)})"
        if fn in (S._add_months, S._sub_months):
            sign = "" if fn is S._add_months else "-"
            return f"EDATE({self.f(a[0], t)},{sign}{self.f(a[1], t)})"
        if fn is lib._pmt:
            r, n, pv = (self.f(x, t) for x in a)
            return f"PMT({r},{n},-{pv})"
        raise Untranslatable(getattr(fn, "__name__", "function"))

    # -- writing -------------------------------------------------------------------------

    def _format_for_hint(self, fmt_hint: str | None, sheet_scale: float) -> str | None:
        st = self.style
        if fmt_hint == "percent":
            return st.percent_format()
        if fmt_hint == "multiple":
            pad = "_)" if st.negatives == "parens" else ""
            if st.negatives == "parens":
                return f'0.0"x"_);(0.0"x");"{st.zero}"_)'
            return f'0.0"x";-0.0"x";"{st.zero}"{pad}'
        if fmt_hint == "price":
            if st.negatives == "parens":
                return f'"$"#,##0.00_);("$"#,##0.00);"{st.zero}"_)'
            return f'"$"#,##0.00;-"$"#,##0.00;"{st.zero}"'
        if fmt_hint == "days":
            if st.negatives == "parens":
                return f'#,##0.0_);(#,##0.0);"{st.zero}"_)'
            return f'#,##0.0;-#,##0.0;"{st.zero}"'
        if fmt_hint == "integer":
            if st.negatives == "parens":
                return f'#,##0_);(#,##0);"{st.zero}"_)'
            return f'#,##0;-#,##0;"{st.zero}"'
        if fmt_hint == "number":
            return st.number_format(1)
        if fmt_hint == "money":
            digits = _powers_of_1000(sheet_scale)
            return self._money_format(sheet_scale if digits else 1, sheet_scale)
        return None

    def _money_format(self, scale_by_format: float, effective_scale: float) -> str:
        st = self.style
        commas = "," * _powers_of_1000(scale_by_format)
        d = st.decimals if st.decimals is not None else (1 if effective_scale >= 1e6 else 0)
        n = "#,##0" + ("." + "0" * d if d else "") + commas
        zero = f'"{st.zero}"' if st.zero != "0" else "0"
        if st.negatives == "parens":
            return f'{n}_);({n});{zero}_)'
        if st.negatives == "triangle":
            return f'{n};"△"{n};{zero}'
        return n

    def _sheet_scale(self, name: str) -> float:
        meta = self.sheet_meta.get(name)
        if meta is not None and meta.money is not None:
            return money_scale(meta.money)
        return self.style.scale

    def _sheet_caption(self, name: str, currencies: set) -> str:
        scale = self._sheet_scale(name)
        currency = next((_describe(c) for c in currencies), None) if len(currencies) == 1 else None
        if scale == self.style.scale:
            return self.style.caption(currency)
        return self.style.replace(money=scale).caption(currency)

    def _write_inputs(self, inp, labels, currencies, bold, blue):
        from openpyxl.styles import Alignment, Border, PatternFill, Side
        st, F = self.style, self.font
        has_source = any(node.source or node.note for node, _ in self.input_rows)
        if self.scenarios is None:
            header = ["Input", "Unit", "Value"]
            if has_source and all(node.scalar for node, _ in self.input_rows):
                header.append("Source")
            inp.append(header)
            inp.append([])
            for c in inp[1]:
                c.font = bold
            for node, value in self.input_rows:
                k = self.input_factor.get(id(node), 1)
                format_value = (lambda v: _value(v / k if k != 1 and isinstance(v, (int, float)) else v))
                row = [node.name, self.input_unit[id(node)].name if id(node) in self.input_unit
                       else _describe(node.unit) if node.unit else ""]
                if isinstance(value, list):
                    row += [format_value(v) for v in value]
                else:
                    row.append(format_value(value))
                    if has_source and all(n.scalar for n, _ in self.input_rows):
                        src = " — ".join(p for p in (node.source, node.note) if p)
                        row.append(src)
                inp.append(row)
                if blue:
                    end_col = len(row) - (1 if has_source and all(n.scalar for n, _ in self.input_rows) else 0)
                    for c in inp[inp.max_row][2:end_col]:
                        c.font = blue
            inp.column_dimensions["A"].width = 40
            if has_source:
                inp.column_dimensions["D"].width = 36
            return

        # Live scenario-switch Inputs sheet
        scens = self.scenarios
        n_scen = len(scens)
        scalars = [(n, v) for n, v in self.input_rows if n.scalar]
        series_inputs = [(n, v) for n, v in self.input_rows if not n.scalar]
        last_col = FIRST_COL + n_scen + (1 if has_source else 0)
        on_band = "FFFFFF" if st.band else None
        inp["A1"] = f"{self.m.name} – Assumptions & Scenarios"
        inp["A1"].font = F(bold=True, size=12, color=on_band)
        inp["A2"] = "Change Active Case in C3 to dynamically switch scenarios across the entire workbook."
        inp["A2"].font = F(italic=True, color=on_band)
        active_idx = 1
        current_scen = getattr(self.r._r, "scenario", None)
        if current_scen in scens:
            active_idx = scens.index(current_scen) + 1
        inp["A3"] = "Active Case"
        inp["A3"].font = F(bold=True)
        c3 = inp["C3"]
        c3.value = active_idx
        c3.font = F(bold=True, color=BLUE if st.colors else BLACK)
        c3.alignment = Alignment(horizontal="center")
        thin = Side(style="thin", color="1F3864" if st.band else "808080")
        c3.border = Border(left=thin, right=thin, top=thin, bottom=thin)
        c3.fill = PatternFill("solid", fgColor="FFF2CC")
        legend = ", ".join(f"{i + 1} = {name}" for i, name in enumerate(scens))
        inp["D3"] = legend
        inp["D3"].font = F(italic=True, color="595959")
        headers = ["Input", "Unit", "Active", *scens] + (["Source"] if has_source else [])
        for col_i, text in enumerate(headers, 1):
            cell = inp.cell(5, col_i, text)
            cell.font = F(bold=True, color=on_band)
            if col_i >= FIRST_COL and text != "Source":
                cell.alignment = Alignment(horizontal="right")
            elif text == "Source":
                cell.alignment = Alignment(indent=1)
            cell.border = Border(bottom=Side(style="thin"))
        if st.band:
            fill = PatternFill("solid", fgColor=st.band)
            for row_i in (1, 2, 5):
                for col_i in range(1, last_col + 1):
                    inp.cell(row_i, col_i).fill = fill
        scen_results = [self._scenario_render(sname) for sname in scens]
        first_scen_col = _col(FIRST_COL)           # D
        last_scen_col = _col(FIRST_COL + n_scen - 1)
        money_digits = _powers_of_1000(st.scale)
        for node, base_val in scalars:
            r = self.inputs[id(node)]
            k = self.input_factor.get(id(node), 1)
            is_money = node.unit in currencies
            if id(node) in self.input_unit:
                unit_text = self.input_unit[id(node)].name
            elif is_money and st.money:
                unit_text = str(st.money) if isinstance(st.money, str) else f"{_describe(node.unit)} ({_scale_word(st.scale, st.language)})"
            else:
                unit_text = _describe(node.unit) if node.unit else ""
            inp.cell(r, 1, node.name).alignment = Alignment(indent=1)
            inp.cell(r, 2, unit_text)
            is_pct = (not node.unit) and isinstance(base_val, float) and -1.0 < base_val < 1.0 and base_val != 0
            num_fmt = (self._money_format(st.scale if money_digits else 1, st.scale) if is_money else
                       st.percent_format() if is_pct else
                       ('#,##0.0_);(#,##0.0);"–"_)' if isinstance(base_val, float) and not base_val.is_integer() else None))
            active_cell = inp.cell(r, FIRST_COL, f"=INDEX({first_scen_col}{r}:{last_scen_col}{r},1,$C$3)")
            active_cell.font = F(bold=True, color=BLACK)
            if num_fmt:
                active_cell.number_format = num_fmt
            for j, sr in enumerate(scen_results):
                v = sr[node]
                val = _value(v / k if k != 1 and isinstance(v, (int, float)) else v)
                sc = inp.cell(r, FIRST_COL + 1 + j, val)
                if blue:
                    sc.font = blue
                if num_fmt:
                    sc.number_format = num_fmt
            if has_source:
                src = " — ".join(p for p in (node.source, node.note) if p)
                src_cell = inp.cell(r, FIRST_COL + 1 + n_scen, src)
                src_cell.font = F(italic=True, color="595959")
                src_cell.alignment = Alignment(indent=1)
        if series_inputs:
            hdr_row = self.inputs[id(series_inputs[0][0])] - 1
            inp.cell(hdr_row, 1, "Time-Series Inputs").font = F(bold=True, underline="single")
            for t, lbl in enumerate(labels):
                c = inp.cell(hdr_row, FIRST_COL + t, lbl)
                c.font = F(bold=True)
                c.alignment = Alignment(horizontal="right")
            for node, base_val in series_inputs:
                r = self.inputs[id(node)]
                k = self.input_factor.get(id(node), 1)
                unit_text = self.input_unit[id(node)].name if id(node) in self.input_unit \
                    else (_describe(node.unit) if node.unit else "")
                inp.cell(r, 1, node.name).alignment = Alignment(indent=1)
                inp.cell(r, 2, unit_text)
                if node.scenarios:
                    for t in range(self.n):
                        col_l = _col(FIRST_COL - 1 + t)
                        c = inp.cell(r, FIRST_COL + t, f"=INDEX({col_l}{r + 1}:{col_l}{r + n_scen},$C$3)")
                        c.font = F(bold=True, color=BLACK)
                    for j, (sname, sr) in enumerate(zip(scens, scen_results)):
                        rr = r + 1 + j
                        inp.cell(rr, 1, f"  {sname}").font = F(italic=True, color="595959")
                        vals = sr[node]
                        for t, v in enumerate(vals):
                            val = _value(v / k if k != 1 and isinstance(v, (int, float)) else v)
                            c = inp.cell(rr, FIRST_COL + t, val)
                            if blue:
                                c.font = blue
                else:
                    for t, v in enumerate(base_val):
                        val = _value(v / k if k != 1 and isinstance(v, (int, float)) else v)
                        c = inp.cell(r, FIRST_COL + t, val)
                        if blue:
                            c.font = blue
        inp.column_dimensions["A"].width = 40
        inp.column_dimensions["B"].width = 12
        for col_i in range(FIRST_COL, FIRST_COL + 1 + n_scen):
            inp.column_dimensions[_col(col_i - 1)].width = 13
        if has_source:
            inp.column_dimensions[_col(FIRST_COL + n_scen)].width = 42
        inp.freeze_panes = "C6"
        inp.page_setup.orientation = "landscape"
        inp.page_setup.fitToWidth, inp.page_setup.fitToHeight = 1, 0
        inp.sheet_properties.pageSetUpPr.fitToPage = True

    def _resolve_axis_fmt(self, fmt_spec: str | None, sheet_scale: float) -> str | None:
        if fmt_spec is None:
            return None
        mapped = self._format_for_hint(fmt_spec, sheet_scale)
        return mapped if mapped is not None else fmt_spec

    def _write_panels(self, ws, sheet_name: str, currencies: set, blue):
        from openpyxl.styles import Alignment, Border, PatternFill, Side
        st, F = self.style, self.font
        sheet_scale = self._sheet_scale(sheet_name)
        sheet_digits = _powers_of_1000(sheet_scale)
        other_sheets = (self.row_sheets | {_sheet_ref(p.sheet) for p in self.panels}) - {_sheet_ref(sheet_name)}
        for spec in self.panels:
            if spec.sheet != sheet_name:
                continue
            r = spec.start_row
            hdr_r = r + 1
            if isinstance(spec.panel, placement.Sensitivity):
                sens = spec.panel
                ws.cell(r, 1, sens.title).font = F(bold=True, underline="single")
                corner_cell = ws.cell(hdr_r, 1, sens.corner)
                corner_cell.font = F(bold=True, color="FFFFFF" if st.band else BLACK)
                corner_cell.border = Border(bottom=Side(style="thin"))
                if st.band:
                    corner_cell.fill = PatternFill("solid", fgColor=st.band)
                    ws.cell(hdr_r, 2).fill = PatternFill("solid", fgColor=st.band)
                col_num_fmt = self._resolve_axis_fmt(sens.col_fmt, sheet_scale)
                row_num_fmt = self._resolve_axis_fmt(sens.row_fmt, sheet_scale)
                cell_num_fmt = self._resolve_axis_fmt(sens.fmt, sheet_scale)
                for j, c_val in enumerate(sens.col_values):
                    hc = ws.cell(hdr_r, FIRST_COL + j)
                    if isinstance(c_val, S.Series):
                        hc.value = "=" + self.f(c_val, 0)
                        self.report.formulas += 1
                    elif isinstance(c_val, Quantity):
                        hc.value = _value(c_val.value)
                    else:
                        hc.value = _value(c_val)
                    hc.font = F(bold=True, color="FFFFFF" if st.band else BLACK)
                    hc.alignment = Alignment(horizontal="right")
                    hc.border = Border(bottom=Side(style="thin"))
                    if col_num_fmt:
                        hc.number_format = col_num_fmt
                    if st.band:
                        hc.fill = PatternFill("solid", fgColor=st.band)
                for i, r_val in enumerate(sens.row_values):
                    rr = hdr_r + 1 + i
                    rc = ws.cell(rr, 1)
                    if isinstance(r_val, S.Series):
                        expr = self.f(r_val, 0)
                        rc.value = "=" + expr
                        self.report.formulas += 1
                        linked = any(f"{q}!" in expr for q in other_sheets)
                        rc.font = F(bold=True, color=GREEN if st.colors and linked else BLACK)
                    elif isinstance(r_val, Quantity):
                        rc.value = _value(r_val.value)
                        rc.font = F(bold=True, color=BLUE if st.colors else BLACK)
                    elif isinstance(r_val, (int, float)) and not isinstance(r_val, bool):
                        rc.value = _value(r_val)
                        rc.font = F(bold=True, color=BLUE if st.colors else BLACK)
                    else:
                        rc.value = r_val
                        rc.font = F(bold=True)
                    rc.alignment = Alignment(indent=1)
                    if row_num_fmt:
                        rc.number_format = row_num_fmt
                    for j in range(len(sens.col_values)):
                        c = ws.cell(rr, FIRST_COL + j)
                        col_l = _col(FIRST_COL - 1 + j)
                        self._axis_refs = {id(spec.row_var): f"$A{rr}", id(spec.col_var): f"{col_l}${hdr_r}"}
                        try:
                            expr = self.f(spec.expr, 0)
                        finally:
                            self._axis_refs = {}
                        c.value = "=" + expr
                        self.report.formulas += 1
                        is_hl = sens.highlight is not None and sens.highlight == (i, j)
                        linked = any(f"{q}!" in expr for q in other_sheets)
                        color = GREEN if st.colors and linked else BLACK
                        c.font = F(bold=is_hl, color=color)
                        if cell_num_fmt:
                            c.number_format = cell_num_fmt
                        if is_hl and st.shade:
                            c.fill = PatternFill("solid", fgColor=st.shade)
                continue

            pnl = spec.panel
            ws.cell(r, 1, pnl.title).font = F(bold=True, underline="single")
            for j, col_label in enumerate(pnl.columns):
                c = ws.cell(hdr_r, FIRST_COL + j, col_label)
                c.font = F(bold=True, color="FFFFFF" if st.band else BLACK)
                c.alignment = Alignment(horizontal="right")
                c.border = Border(bottom=Side(style="thin"))
                if st.band:
                    c.fill = PatternFill("solid", fgColor=st.band)
            if st.band:
                ws.cell(hdr_r, 1).fill = PatternFill("solid", fgColor=st.band)
                ws.cell(hdr_r, 2).fill = PatternFill("solid", fgColor=st.band)
            for idx, (label, vals, opts) in enumerate(pnl.rows):
                rr = hdr_r + 1 + idx
                total = opts.get("total", False)
                strong = total in (True, "grand")
                highlight_col = opts.get("highlight")
                lbl_cell = ws.cell(rr, 1, label)
                lbl_cell.font = F(bold=strong or opts.get("bold", False))
                if not strong:
                    lbl_cell.alignment = Alignment(indent=1)
                fmt_opt = opts.get("fmt")
                for j, val in enumerate(vals):
                    c = ws.cell(rr, FIRST_COL + j)
                    is_hl = highlight_col is not None and j == highlight_col
                    cell_bold = strong or is_hl
                    col_fmt_hint = fmt_opt[j] if isinstance(fmt_opt, (list, tuple)) else fmt_opt
                    if isinstance(val, S.Series):
                        self._active_panel_cell = (sheet_name, rr, FIRST_COL + j)
                        try:
                            expr = self.f(val, 0)
                            c.value = "=" + expr
                            self.report.formulas += 1
                            linked = any(f"{q}!" in expr for q in other_sheets)
                            color = GREEN if st.colors and linked else BLACK
                            c.font = F(bold=cell_bold, color=color)
                        except (Untranslatable, KeyError):
                            c.value = _value(self.r._r.value(val, 0 if not val.scalar else None))
                            c.font = F(bold=cell_bold)
                        finally:
                            self._active_panel_cell = None
                        if col_fmt_hint is None and val.unit in currencies:
                            col_fmt_hint = "money"
                    elif isinstance(val, Quantity):
                        c.value = _value(val.value)
                        c.font = F(bold=cell_bold, color=BLUE if st.colors else BLACK)
                        if col_fmt_hint is None and val.dims in currencies:
                            col_fmt_hint = "money"
                    elif isinstance(val, (int, float)) and not isinstance(val, bool):
                        c.value = _value(val)
                        c.font = F(bold=cell_bold, color=BLUE if st.colors else BLACK)
                    else:
                        c.value = val
                        c.font = F(bold=cell_bold)
                        if isinstance(val, str) and val:
                            c.alignment = Alignment(horizontal="right")
                    fmt = self._format_for_hint(col_fmt_hint, sheet_scale)
                    if fmt:
                        c.number_format = fmt
                    elif isinstance(val, S.Series) and val.unit in currencies:
                        c.number_format = self._money_format(sheet_scale if sheet_digits else 1, sheet_scale)
                    if is_hl and st.shade:
                        c.fill = PatternFill("solid", fgColor=st.shade)
                    if total is True:
                        c.border = Border(top=Side(style="thin"))
                    elif total == "grand":
                        c.border = Border(top=Side(style="thin"), bottom=Side(style="double"))
                if total == "grand" and st.shade:
                    fill = PatternFill("solid", fgColor=st.shade)
                    for col_i in range(1, FIRST_COL + len(pnl.columns)):
                        ws.cell(rr, col_i).fill = fill

    def write(self, path):
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        st = self.style
        self.font = (lambda **kw: Font(name=st.font, **kw)) if st.font else Font
        F = self.font
        wb = openpyxl.Workbook()
        bold = F(bold=True)
        blue = F(color=BLUE) if st.colors else None
        shade = PatternFill("solid", fgColor="FFF2CC")
        data_fill = PatternFill("solid", fgColor="DDEBF7")
        inp = wb.active
        inp.title = "Inputs"
        labels = [p.label for p in self.m.timeline.periods]
        currencies = {e._currency for e in self.books if e._currency is not None}
        self._write_inputs(inp, labels, currencies, bold, blue)
        shown = self.shown
        hidden = self.hidden()
        money_digits = _powers_of_1000(st.scale)
        actual_until = self.m.actual_until
        has_actuals = actual_until is not None
        forecast_col = (actual_until + 1) if (actual_until is not None and 0 <= actual_until < self.n - 1) else None

        for name in [sh.name for sh in self.layout] + ["Model"]:
            rows = [r for r in self.rows if r.sheet == name]
            sheet_panels = [p for p in self.panels if p.sheet == name]
            if not rows and not sheet_panels:
                if name != "Model" or self.omit_unused_model:
                    continue
            ws = wb.create_sheet(name)
            styled = name != "Model" and st.band is not None
            if styled:
                panel_cols = lambda p: len(p.panel.col_values) if isinstance(p.panel, placement.Sensitivity) else len(p.panel.columns)
                last_col = max(FIRST_COL - 1 + self.n,
                               max((FIRST_COL - 1 + panel_cols(p) for p in sheet_panels), default=FIRST_COL))
                on_band = "FFFFFF"
                ws["A1"] = f"{self.m.name} – {name}"
                ws["A1"].font = F(bold=True, size=12, color=on_band)
                ws["A2"] = self._sheet_caption(name, currencies)
                ws["A2"].font = F(italic=True, color=on_band)
                show_units_col = any(r.node.unit is not None and r.node.unit not in currencies and r.fmt is None
                                     for r in rows)
                if show_units_col:
                    ws.cell(4, 2, "Unit").font = F(bold=True, color=on_band)
                if rows:
                    for t, p in enumerate(self.m.timeline.periods):
                        plabel = st.period_label(p)
                        c = ws.cell(4, FIRST_COL + t, plabel)
                        if isinstance(plabel, int):
                            c.number_format = st.heading_format(actual=has_actuals and t <= actual_until,
                                                                has_actuals=has_actuals)
                        c.font = F(bold=True, color=on_band)
                        c.alignment = Alignment(horizontal="right")
                        left = Side(style="medium", color="FFFFFF") if t == forecast_col else None
                        c.border = Border(bottom=Side(style="thin"), left=left)
                fill = PatternFill("solid", fgColor=st.band)
                band_rows = (1, 2, 4) if rows else (1, 2)
                for row_i in band_rows:
                    for col_i in range(1, last_col + 1):
                        ws.cell(row_i, col_i).fill = fill
                for sheet, number, title in self.headers:
                    if sheet == name:
                        ws.cell(number, 1, title).font = F(bold=True, underline="single")
                self.sheet_now = name
                self.write_rows(ws, rows, currencies, shown, hidden, money_digits, blue, shade, data_fill,
                                styled=True, sheet_name=name, forecast_col=forecast_col,
                                show_units_col=show_units_col)
                self._write_panels(ws, name, currencies, blue)
                ws.sheet_properties.outlinePr.summaryBelow = False
                ws.column_dimensions["A"].width = 42
                ws.column_dimensions["B"].width = 14 if show_units_col else 2
                for t in range(max(self.n, max((panel_cols(p) for p in sheet_panels), default=0))):
                    col_l = _col(FIRST_COL - 1 + t)
                    hdr_len = max((len(str(p.panel.columns[t])) + 3 for p in sheet_panels
                                   if isinstance(p.panel, placement.Panel) and t < len(p.panel.columns)),
                                  default=0)
                    ws.column_dimensions[col_l].width = max(13, hdr_len)
                ws.freeze_panes = "C5" if rows else "C4"
                ws.page_setup.orientation = "landscape"
                ws.page_setup.fitToWidth = 1
                ws.page_setup.fitToHeight = 1 if (sheet_panels and ws.max_row <= 52) else 0
                ws.sheet_properties.pageSetUpPr.fitToPage = True
                ws.print_title_cols = "A:B"
            else:
                ws.append(["Series", "Unit", *labels])
                ws.append([])
                for c in ws[1]:
                    c.font = bold
                for sheet, number, title in self.headers:
                    if sheet == name:
                        ws.cell(number, 1, title).font = bold
                self.sheet_now = name
                self.write_rows(ws, rows, currencies, shown, hidden, money_digits, blue, shade, data_fill)
                self._write_panels(ws, name, currencies, blue)
                ws.sheet_properties.outlinePr.summaryBelow = False
                ws.column_dimensions["A"].width = 40
                ws.freeze_panes = "C3"
        self.sheet_now = "Model"
        for e in self.books:
            if st.statements:
                _Statements(self, wb, e).write()
            elif not self.omit_unused_model:
                self.statements(wb, e, labels, bold)
        if self.emit_checks and self.check_rows:
            self.checks_sheet(wb, labels)
        self.write_tables(inp, blue)
        if not self.input_rows and not self.tables:
            wb.remove(inp)
        if st.statements and "Model" in wb.sheetnames:
            wb.move_sheet("Model", offset=len(wb.sheetnames) - 1 - wb.sheetnames.index("Model"))
        for sheet in wb.worksheets:
            sheet.sheet_view.showGridLines = st.gridlines
        wb.save(path)
        return self.report

    def write_tables(self, inp, blue):
        for table in self.tables.values():
            node = table.node
            inp.cell(table.row, 1, f"{table.label}: from")
            inp.cell(table.row + 1, 1, table.label)
            if node.x.unit:
                inp.cell(table.row, 2, _describe(node.x.unit))
            unit = table.shown.name if table.shown else _describe(node.unit) if node.unit else ""
            inp.cell(table.row + 1, 2, unit)
            for j, (k, v) in enumerate(zip(node.keys, node.values)):
                for number, value in ((table.row, k), (table.row + 1, v.value / table.factor)):
                    c = inp.cell(number, FIRST_COL + j, _value(value))
                    if blue:
                        c.font = blue

    def _is_actual_data_cell(self, row: Row, t: int) -> bool:
        """True when a historical period cell on a Model/placed sheet holds an input actual rather than a formula."""
        actual_until = self.m.actual_until
        if actual_until is None or t > actual_until or row.link:
            return False
        if isinstance(row.node, ledger._Balance):
            return True
        if isinstance(row.alias, ledger.LineItem) and not isinstance(row.alias.expr, ledger._Balance):
            return True
        if any(row.alias is e.bs.retained_earnings or row.node is e.bs.retained_earnings for e in self.books):
            return True
        return False

    def write_rows(self, ws, rows, currencies, shown, hidden, money_digits, blue, shade, data_fill, *,
                   styled: bool = False, sheet_name: str = "Model", forecast_col: int | None = None,
                   show_units_col: bool = True):
        from openpyxl.comments import Comment
        from openpyxl.styles import Alignment, Border, PatternFill, Side
        guard_fill = PatternFill("solid", fgColor="FCE4D6")
        guarded_cells = {cell for cell, _ in self.guards}
        st, F = self.style, self.font
        sheet_scale = self._sheet_scale(sheet_name)
        sheet_digits = _powers_of_1000(sheet_scale)
        other_sheets = self.row_sheets - {_sheet_ref(sheet_name)}
        for row in rows:
            lbl_cell = ws.cell(row.number, 1, row.label if not row.helper else f"  {row.label}")
            strong = row.total in (True, "grand")
            is_ratio = row.fmt == "percent"
            if styled:
                lbl_cell.font = F(bold=strong, italic=is_ratio and not strong)
                if not strong:
                    lbl_cell.alignment = Alignment(indent=2 if is_ratio else 1)
            keys = {id(row.node)} | ({id(row.alias)} if row.alias is not None else set())
            unit_text = _describe(row.node.unit) if row.node.unit else ""
            fmt = self._format_for_hint(row.fmt, sheet_scale)
            if fmt is None:
                if row.node.unit in currencies:
                    fmt = self._money_format(sheet_scale if sheet_digits else 1, sheet_scale)
                    if sheet_digits and not styled:
                        unit_text += f" ({_scale_word(sheet_scale, st.language)})"
                elif keys & shown.keys():
                    u = shown[next(iter(keys & shown.keys()))]
                    fmt = st.number_format(u.scale if _by_format(u) and not keys & self.converted else 1)
                    if keys & self.prefixed:
                        fmt = _with_decimal(fmt)
                    unit_text = u.name
            if not styled or show_units_col:
                ws.cell(row.number, 2, unit_text if not (styled and row.node.unit in currencies) else "")
            if row.helper and st.helpers == "group" or keys & hidden:
                ws.row_dimensions[row.number].outlineLevel = 1
                ws.row_dimensions[row.number].hidden = True
            scalar = row.node.scalar and not row.in_block
            self._active_row = row
            for t in range(1 if scalar else self.n):
                cell = ws.cell(row.number, FIRST_COL + t)
                if fmt:
                    cell.number_format = fmt
                left = Side(style="medium", color="808080") if styled and t == forecast_col else None
                if styled:
                    if row.total is True:
                        cell.border = Border(top=Side(style="thin"), left=left)
                    elif row.total == "grand":
                        cell.border = Border(top=Side(style="thin"), bottom=Side(style="double"), left=left)
                    elif left is not None:
                        cell.border = Border(left=left)
                if row.block_rows is not None:
                    col_l = _col(FIRST_COL - 1 + t)
                    nums = [r.number for r in row.block_rows]
                    if nums and nums[-1] - nums[0] == len(nums) - 1:
                        expr = f"SUM({col_l}{nums[0]}:{col_l}{nums[-1]})"
                    else:
                        expr = "+".join(f"{col_l}{n}" for n in nums) if nums else "0"
                    cell.value = "=" + expr
                    if styled:
                        cell.font = F(bold=strong, italic=is_ratio and not strong, color=BLACK)
                    self.report.formulas += 1
                    continue
                if row.link:
                    t_eff = 0 if row.node.scalar else t
                    source = self.cell(row.node, t_eff) if id(row.node) in self.row_of else self.ref(row.node, t_eff)
                    expr = _shown(source, row.factor * row.link_sign)
                    cell.value = "=" + expr
                    if styled:
                        linked = any(f"{q}!" in expr for q in other_sheets)
                        color = GREEN if st.colors and linked else BLACK
                        cell.font = F(bold=strong, italic=is_ratio and not strong, color=color)
                    self.report.formulas += 1
                    continue
                if (row.formula is None and _is_data(row.node)) or self._is_actual_data_cell(row, t):
                    v = self.r._r.value(row.node, None if row.node.scalar else t)
                    cell.value = _value(v / row.factor if row.factor != 1 and isinstance(v, (int, float)) else v)
                    if styled:
                        cell.font = F(bold=strong, italic=is_ratio and not strong,
                                      color=BLUE if st.colors else BLACK)
                    elif blue:
                        cell.font = blue
                    else:
                        cell.fill = data_fill
                    self.report.data += 1
                    continue
                try:
                    key = (id(row), t)
                    formula = self._formulas.get(key)
                    guarded = False
                    if formula is None or key in guarded_cells:
                        self._now = _Cell(key, record=False)
                        try:
                            formula = self.expand(self._active_expr(row), t)
                        finally:
                            guarded, self._now = self._now.guarded, None
                    if guarded:
                        cell.fill = guard_fill
                        cell.comment = Comment(GUARD_NOTE, "boki")
                        self.report.guarded += 1
                    if _boolean(self._active_expr(row)):
                        formula = f"IF({formula},1,0)"     # SUM over a range skips TRUE/FALSE; store 1/0
                    shown_expr = _shown(formula, row.factor)
                    cell.value = "=" + shown_expr
                    if styled:
                        linked = any(f"{q}!" in shown_expr for q in other_sheets)
                        color = GREEN if st.colors and linked else BLACK
                        cell.font = F(bold=strong, italic=is_ratio and not strong, color=color)
                    self.report.formulas += 1
                except (Untranslatable, KeyError) as exc:
                    why = str(exc) if isinstance(exc, Untranslatable) else "missing row"
                    try:
                        v = self.r._r.value(row.node, None if scalar else t)
                    except ArithmeticError:
                        v = None
                    cell.value = _value(v / row.factor if row.factor != 1 and isinstance(v, (int, float)) else v)
                    cell.fill = shade
                    if t == 0:
                        cell.comment = Comment(f"value from boki: {why}", "boki")
                    self.report.values += 1
                    self.report.reasons[why] = self.report.reasons.get(why, 0) + 1
            self._active_row = None
            if styled and row.total == "grand" and st.shade:
                fill = PatternFill("solid", fgColor=st.shade)
                for col_i in range(1, FIRST_COL + self.n):
                    ws.cell(row.number, col_i).fill = fill

    def checks_sheet(self, wb, labels):
        """One row per check: OK in every period, or FAIL where it does not hold. Refers to Model or placed sheets."""
        from openpyxl.formatting.rule import CellIsRule, FormulaRule
        from openpyxl.styles import Alignment, Font, PatternFill
        F, st = self.font, self.style
        ws = wb.create_sheet("Checks")
        on_band = "FFFFFF" if st.band else None
        last_col = FIRST_COL - 1 + self.n
        ws["A1"] = f"{self.m.name} – Checks" if st.band else "Checks"
        ws["A1"].font = F(bold=True, size=12, color=on_band)
        ws["A2"] = "Every check holds in every period when the status is OK."
        ws["A2"].font = F(italic=True, color=on_band)
        ws.cell(4, 2, "Status").font = F(bold=True, color=on_band)
        actual_until = self.m.actual_until
        has_actuals = actual_until is not None
        for t, p in enumerate(self.m.timeline.periods):
            plabel = st.period_label(p) if st.band else labels[t]
            c = ws.cell(4, FIRST_COL + t, plabel)
            if isinstance(plabel, int):
                c.number_format = st.heading_format(actual=has_actuals and t <= actual_until,
                                                    has_actuals=has_actuals)
            c.font, c.alignment = F(bold=True, color=on_band), Alignment(horizontal="right")
        if st.band:
            fill = PatternFill("solid", fgColor=st.band)
            for row_i in (1, 2, 4):
                for col_i in range(1, last_col + 1):
                    ws.cell(row_i, col_i).fill = fill
        last = _col(FIRST_COL - 2 + self.n)
        first_row = 6
        ws.cell(5, 1, "All checks").font = F(bold=True)
        rows = []
        prev_sheet = self.sheet_now
        self.sheet_now = "Checks"
        for i, (label, node) in enumerate(self.check_rows):
            r = first_row + i
            rows.append(r)
            ws.cell(r, 1, label)
            ws.cell(r, 2, f'=IF(MIN({_col(FIRST_COL - 1)}{r}:{last}{r})=1,"OK","FAIL")')
            for t in range(self.n):
                if id(node) in self.row_of:
                    expr = self.ref(node, t, qualified=True)
                else:
                    expr = self.f(node, t)
                    if expr == "TRUE":
                        expr = "1"
                    elif expr == "FALSE":
                        expr = "0"
                    else:
                        expr = f"IF({expr},1,0)"
                c = ws.cell(r, FIRST_COL + t, f"={expr}")
                c.number_format = '"OK";"FAIL";"FAIL"'
                c.alignment = Alignment(horizontal="right")
        self.sheet_now = prev_sheet
        ws.cell(5, 2, f'=IF(COUNTIF(B{rows[0]}:B{rows[-1]},"FAIL")=0,"OK","FAIL")').font = F(bold=True)
        red, green = PatternFill("solid", fgColor="F8D7DA"), Font(color="15803D", bold=True)
        ws.conditional_formatting.add(f"B5:B{rows[-1]}", FormulaRule(formula=['B5="FAIL"'], fill=red,
                                                                    font=Font(color="B91C1C", bold=True)))
        ws.conditional_formatting.add(f"{_col(FIRST_COL - 1)}{rows[0]}:{last}{rows[-1]}",
                                      CellIsRule(operator="equal", formula=["0"], fill=red,
                                                 font=Font(color="B91C1C", bold=True)))
        ws.conditional_formatting.add(f"B5:B{rows[-1]}", CellIsRule(operator="equal", formula=['"OK"'], font=green))
        ws.column_dimensions["A"].width = 48
        ws.column_dimensions["B"].width = 10
        for t in range(self.n):
            ws.column_dimensions[_col(FIRST_COL - 1 + t)].width = 13
        ws.freeze_panes = "C5"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    def explicit_units(self) -> dict[int, Unit]:
        """to_excel(units={series: unit}), checked against the series' dimensions."""
        out = {}
        for key, u in self.style.units.items():
            node = self.m._named[key] if isinstance(key, str) else key
            if node.unit != u.dims:
                raise ValueError(f"units=: {node.name} is in {_describe(node.unit)}, not {u.name}")
            out[id(node)] = u
        return out

    def choose_display_units(self):
        """The unit each row shows, as Result.display_unit chooses it (units= overrides it), and how.

        A unit that is a power of 1000 of the base unit (kW, MWh) is shown by number format alone: the cells keep
        base units, so ranges and references need no conversion. Any other factor (a rate per year, a milli
        prefix) is the row's factor, as for b.row(scale=): the cells hold the value in the display unit and
        every reference converts back; a range over such a row becomes a value cell, as for b.row(scale=). A row
        placed with its own sign= or scale= keeps that and shows no display unit. Money rows are never touched."""
        explicit = self.explicit_units()
        currencies = {e._currency for e in self.books if e._currency is not None}
        for node, _ in self.input_rows:           # editable cells hold the display value, never a format
            u = explicit.get(id(node)) or S.written_unit(node)
            if u is not None and _labeled(u) and node.unit is not None and node.unit not in currencies:
                self.input_unit[id(node)] = u
                self.input_factor[id(node)] = u.scale
        for links in (False, True):               # rows first, so a link follows the row it shows
            for row in self.rows:
                if row.helper or row.link != links or row.factor != 1:
                    continue
                if row.node.unit is None or row.node.unit in currencies:
                    continue
                node, source = row.node, self.row_of.get(id(row.node))
                if links and source is not None:
                    if id(node) not in self.shown:
                        continue                  # the row it shows keeps its own scale
                    u, auto = self.shown[id(node)], False
                else:
                    nodes = [n for n in (row.alias, node) if n is not None]
                    u = next((explicit[id(n)] for n in nodes if id(n) in explicit), None)
                    u = u or next((w for w in map(S.written_unit, nodes) if w is not None), None)
                    auto = u is None
                    u = u or self.r.display_unit(node)
                if u is None or not _labeled(u):
                    continue
                if links and source is None and id(node) in self.input_unit:
                    row.factor = 1                # the reference already converts the input back to base
                    if not _by_format(u):
                        row.factor = u.scale
                        self.converted.add(id(node))
                elif links and source is not None:
                    if id(node) in self.converted:
                        pass                      # inherits the cells of the row it shows
                elif not _by_format(u) or _is_data(node):
                    row.factor = u.scale          # editable cells (data tables) and odd factors hold the display value
                    self.converted.add(id(node))
                    if row.alias is not None:
                        self.converted.add(id(row.alias))
                for n in (row.alias, node):
                    if n is not None:
                        self.shown[id(n)] = u
                        if auto and not links:
                            self.prefixed.add(id(n))

    def hidden(self) -> set[int]:
        return {id(self.m._named[k] if isinstance(k, str) else k) for k in self.style.hide}

    def statements(self, wb, e, labels, bold):
        """PL, BS and CF sheets for an entity, as references to the Model sheet (the plain style)."""
        from .layouts import Stage

        def sheet(title):
            ws = wb.create_sheet(_sheet_name(title))
            ws.append([title, "", *labels])
            ws.cell(1, 1).font = bold
            ws.column_dimensions["A"].width = 40
            ws.freeze_panes = "C2"
            return ws

        def put(ws, label, cells, level=0, strong=False):
            r = ws.max_row + 1
            ws.cell(r, 1, "  " * level + label).font = Font(bold=strong)
            for t, v in enumerate(cells):
                c = ws.cell(r, FIRST_COL + t, v)
                c.number_format = "#,##0"
                if strong:
                    c.font = Font(bold=True)
            return r

        def refs(node):
            return [f"={self.ref(node, t, qualified=True)}" for t in range(self.n)]

        from openpyxl.styles import Font
        pl = sheet(f"{e.name} PL")
        for k in e.layout.pl:
            if isinstance(k, Stage):
                put(pl, e.label(k.name), refs(getattr(e.pl, k.name)), strong=True)
                continue
            kind = getattr(e.pl, k.name)
            if kind.items:
                put(pl, e.label(k.name), refs(kind.total))
                for item in kind.items:
                    put(pl, item.name, refs(item), level=1)
        if e._oci_components:
            put(pl, e.label("other_comprehensive_income"), refs(e.other_comprehensive_income), strong=True)
            for component in e._oci_components.values():
                put(pl, component.name, refs(component.line), level=1)
            put(pl, e.label("comprehensive_income"), refs(e.comprehensive_income), strong=True)
        bs = sheet(f"{e.name} BS")
        for side, title in (("asset", "total assets"), ("liability", "total liabilities")):
            first = bs.max_row + 1
            for a in e._accounts:
                if a.side == side:
                    put(bs, e._account_name(a), refs(e._balance(a)), level=1)
            last = bs.max_row
            put(bs, title, [f"=SUM({_col(FIRST_COL - 1 + t)}{first}:{_col(FIRST_COL - 1 + t)}{last})" if last >= first
                            else 0 for t in range(self.n)], strong=True)
        for a in e._accounts:
            if a.side == "equity":
                cells = refs(e._balance(a))
                if a.kind == "retained_earnings":
                    cells = [f"{c}+{self.ref(e._cum_profit, t, qualified=True)}" for t, c in enumerate(cells)]
                put(bs, e._account_name(a), cells, level=1)
        put(bs, "total equity", refs(e._equity_total), strong=True)
        cf = sheet(f"{e.name} CF")
        rows = [put(cf, f"{cls} cash flow", refs(getattr(e.cf, cls))) for cls in _cf_classes(e)]
        put(cf, "net change in cash", ["=" + "+".join(f"{_col(FIRST_COL - 1 + t)}{r}" for r in rows)
                                       for t in range(self.n)], strong=True)
        put(cf, "cash (end)", refs(e.bs.cash), strong=True)


BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
_BS_CURRENT = {"cash", "receivable", "payable", "deferred_revenue", "prepaid", "vat"}
_SHEET_KEYS = {"en": ("IS", "BS", "CF", "Schedules"), "ja": ("PL", "BS", "CF", "明細")}


def _cf_classes(e) -> tuple[str, ...]:
    fx = any(ledger.cash_class(e, p) == "fx" for p in e._postings)
    return ("operating", "investing", "financing") + (("fx",) if fx else ())


def _scale_word(k: float, language: str) -> str:
    from .styles import _EN_SCALE, _JA_SCALE
    return (_JA_SCALE if language == "ja" else _EN_SCALE).get(k, f"{k:g}")


class _Statements:
    """An entity's income statement, balance sheet and cash-flow statement in the writer's style.

    Every number is a link to the Model sheet (green), scaled to the style's money unit; totals are sums
    of the lines above them on the same sheet (black), so the sheet reads like a hand-built model.
    """

    def __init__(self, w: _Writer, wb, e):
        self.w, self.wb, self.e, self.st = w, wb, e, w.style
        self.groups = column_groups(w.m, e, self.st)
        self.n = len(self.groups)            # statement columns: fiscal years (or the model's own periods)
        self.currency = _describe(e._currency) if e._currency else None

    def L(self, key: str) -> str:
        return self.st.label(key, self.e.standard)

    # -- cells ---------------------------------------------------------------------------

    def link(self, node, sign=1, plus=None, stock=False):
        """One cell per column: a flow sums the column's periods, a balance (stock=True) takes the last one."""
        k = self.st.scale
        out = []
        for _, ts in self.groups:
            terms = [self.span(node, ts, stock)] + ([self.span(plus, ts, stock)] if plus is not None else [])
            body = "+".join(terms)
            if len(terms) > 1 and (sign < 0 or k != 1):
                body = f"({body})"
            out.append("=" + ("-" if sign < 0 else "") + body + (f"/{_literal(k)}" if k != 1 else ""))
        return out

    def span(self, node, ts, stock):
        if isinstance(node, S.Const):                    # a constant amount has no row: write it
            v = _literal(node.value)
            return v if stock or len(ts) == 1 else f"{len(ts)}*{v}"
        row = self.w.row_of.get(id(node))
        if row is None:                                   # an input: its Inputs row
            first, last = self.w.ref(node, ts[0], qualified=True), self.w.ref(node, ts[-1], qualified=True)
            if first is None:
                raise KeyError(f"{node.name} has no row on the Model sheet")
            factor = 1
        else:
            first, last, factor = self.w.cell(node, ts[0], qualified=True), self.w.cell(node, ts[-1], qualified=True), row.factor
        if stock or len(ts) == 1:
            return _times(last, factor)
        if first == last:                                # a scalar row: the same amount every period
            return f"{len(ts)}*{_times(first, factor)}"
        return _times(f"SUM({_range(first, last)})", factor)

    def col(self, t):
        return _col(FIRST_COL - 1 + t)

    def sum_of(self, rows):
        if not rows:
            return [0] * self.n
        return ["=" + "+".join(f"{self.col(t)}{r}" for r in rows) for t in range(self.n)]

    # -- sheet ---------------------------------------------------------------------------

    def sheet(self, key):
        from openpyxl.styles import Alignment, Border, PatternFill, Side
        st, F = self.st, self.w.font
        name = _SHEET_KEYS[st.language][("IS", "BS", "CF", "SC").index(key)]
        ws = self.wb.create_sheet(_sheet_name(f"{self.e.name} {name}"))
        last = FIRST_COL - 1 + self.n
        on_band = "FFFFFF" if st.band else None
        if st.dollars:                       # a filing: company, statement, unit on three lines
            ws["A1"], ws["A2"], ws["A3"] = self.e.name.upper(), self.L(key).upper(), st.caption(self.currency)
            ws["A1"].font, ws["A2"].font, ws["A3"].font = F(bold=True), F(bold=True), F(italic=True)
        else:
            title = self.L(key)
            ws["A1"] = f"{self.e.name} – {title}" if st.language == "en" else f"{self.e.name} {title}"
            ws["A1"].font = F(bold=True, size=12, color=on_band)
            ws["A2"] = st.caption(self.currency)
            ws["A2"].font = F(italic=True, color=on_band)
        if st.header:
            end = self.year_end()
            text = (f"{end}," if key == "BS" else st.header.format(end=end))
            c = ws.cell(3, FIRST_COL, text)
            c.font, c.alignment = F(bold=True), Alignment(horizontal="center")
            if self.n > 1:
                ws.merge_cells(start_row=3, start_column=FIRST_COL, end_row=3, end_column=last)
            for t in range(self.n):
                ws.cell(3, FIRST_COL + t).border = Border(bottom=Side(style="thin"))
        actual_until = self.w.m.actual_until
        self.has_actuals = actual_until is not None
        self.col_actual = [actual_until is not None and max(ts) <= actual_until for _, ts in self.groups]
        self.forecast_col = next((i for i, is_a in enumerate(self.col_actual) if not is_a), None)
        if not any(self.col_actual):
            self.forecast_col = None
        for t, (label, _) in enumerate(self.groups):
            c = ws.cell(4, FIRST_COL + t, label)
            if isinstance(label, int):
                c.number_format = st.heading_format(actual=self.col_actual[t], has_actuals=self.has_actuals)
            c.font = F(bold=True, color=on_band)
            c.alignment = Alignment(horizontal="right")
            left = Side(style="medium", color="FFFFFF" if st.band else "808080") if t == self.forecast_col else None
            c.border = Border(bottom=Side(style="thin"), left=left)
        if st.band:
            fill = PatternFill("solid", fgColor=st.band)
            for row in (1, 2, 4):
                for col in range(1, last + 1):
                    ws.cell(row, col).fill = fill
        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["B"].width = 2
        for t in range(self.n):
            ws.column_dimensions[self.col(t)].width = 14 if st.periods == "ja" else 12
        ws.freeze_panes = "C5"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_title_cols = "A:B"
        self.ws, self.next = ws, 5
        return ws

    def year_end(self) -> str:
        """'December 31' from the entity's fiscal year end (or the calendar year)."""
        import calendar
        rule = self.e.fiscal.year_end if self.e.fiscal is not None else "12-31"
        month, day = (int(x) for x in rule.split("-"))
        return f"{calendar.month_name[month]} {day}"

    def put(self, label, cells, kind="line", dollar=False):
        """kind: line / total / grand / ratio / header / check. dollar: a $ in the cells (a filing's first line
        and totals)."""
        from openpyxl.styles import Alignment, Border, PatternFill, Side
        st, F, ws, r = self.st, self.w.font, self.ws, self.next
        self.next += 1
        ws.cell(r, 1, label)
        strong = kind in ("total", "grand", "header")
        ws.cell(r, 1).font = F(bold=strong, italic=kind == "ratio", underline="single" if kind == "header" else None)
        if kind in ("line", "ratio"):
            ws.cell(r, 1).alignment = Alignment(indent=1 if kind == "line" else 2)
        if kind == "header":
            return r
        for t, v in enumerate(cells):
            c = ws.cell(r, FIRST_COL + t, v)
            c.number_format = st.percent_format() if kind == "ratio" else \
                (st.dollar_format() if dollar and st.dollars else st.number_format())
            linked = isinstance(v, str) and any(f"{q}!" in v for q in self.w.row_sheets)
            color = GREEN if st.colors and linked else BLACK
            c.font = F(color=color, bold=strong, italic=kind in ("ratio", "check"))
            left = Side(style="medium", color="808080") if t == self.forecast_col else None
            if kind == "total":
                c.border = Border(top=Side(style="thin"), left=left)
            elif kind == "grand":
                c.border = Border(top=Side(style="thin"), bottom=Side(style="double"), left=left)
            elif left is not None:
                c.border = Border(left=left)
        if kind == "grand" and st.shade:
            for col in range(1, FIRST_COL + self.n):
                ws.cell(r, col).fill = PatternFill("solid", fgColor=st.shade)
        return r

    def gap(self):
        self.next += 1

    def write(self):
        self.income_statement()
        self.balance_sheet()
        self.cash_flow()
        if schedule_accounts(self.e):
            self.schedules()

    # -- income statement ------------------------------------------------------------------

    def income_statement(self):
        """Lines in the layout's order; each profit is the previous profit plus the lines since it."""
        from .layouts import Stage
        e, st = self.e, self.st
        self.sheet("IS")
        final = [k for k in e.layout.pl if isinstance(k, Stage)][-1]
        revenue_row = pretax_row = previous = None
        since: list[str] = []           # signed references to the kind rows since the previous profit
        first = True
        for k in e.layout.pl:
            if isinstance(k, Stage):
                terms = ([f"+{{c}}{previous}"] if previous else []) + since
                cells = ["=" + "".join(x.format(c=self.col(t)) for x in terms).lstrip("+") if terms else 0
                         for t in range(self.n)]
                kind = "grand" if k is final else "total"
                r = self.put(self.L(k.name), cells, kind, dollar=k is final)
                previous, since = r, []
                if k.name == "pretax_income":
                    pretax_row = r
                if st.ratios and revenue_row is not None:
                    self.ratio(self.L("margin"), r, revenue_row)
                continue
            kind = getattr(e.pl, k.name)
            if not kind.items:
                continue
            shown_negative = k.side == "expense" and st.expenses == "negative"
            sign = -1 if shown_negative else 1
            label = self.L(k.name)
            if len(kind.items) == 1:
                if k.name == "income_tax" and kind.items[0].name == e.label("deferred_tax"):
                    label = self.L("deferred_tax")
                elif kind.items[0].account.tags & {"equity_method_presentation", "equity_method_disposal"}:
                    label = kind.items[0].name
                r = self.put(label, self.link(kind.items[0], sign), dollar=first)
            else:
                rows = [self.put(item.name, self.link(item, sign), dollar=first and n == 0)
                        for n, item in enumerate(kind.items)]
                r = self.put(self.L("total").format(_lower_first(label) if st.language == "en" else label),
                             self.sum_of(rows), "total")
            first = False
            since.append(("-" if k.side == "expense" and not shown_negative else "+") + "{c}" + str(r))
            if k.name == "revenue":
                revenue_row = r
                if st.ratios:
                    self.put(self.L("growth"), [""] + [f"=IF({self.col(t - 1)}{r}=0,\"\",{self.col(t)}{r}/{self.col(t - 1)}{r}-1)"
                                                       for t in range(1, self.n)], "ratio")
            if k.name == "income_tax" and st.ratios and pretax_row is not None:
                s_ = "-" if sign < 0 else ""
                self.put(self.L("tax_rate"), [f"=IF({self.col(t)}{pretax_row}=0,\"\",{s_}{self.col(t)}{r}/{self.col(t)}{pretax_row})"
                                              for t in range(self.n)], "ratio")

        if e._oci_components:
            self.put(self.L("other_comprehensive_income"), self.link(e.other_comprehensive_income), "total")
            for component in e._oci_components.values():
                self.put(component.name, self.link(component.line))
            self.put(self.L("comprehensive_income"), self.link(e.comprehensive_income), "grand", dollar=True)

        attribution = getattr(e, "_group_profit_attribution", None)
        if attribution is not None:
            if e.standard.name == "IFRS":
                self.put("Attributable to:", None, "header")
                nci_label, parent_label = "Non-controlling interests", "Owners of the parent"
            elif e.standard.name == "US GAAP":
                nci_label = "Attributable to noncontrolling interests"
                parent_label = f"Attributable to {e._group_parent_name}"
            elif st.language == "ja":
                nci_label, parent_label = self.L("nci_profit"), self.L("parent_profit")
            else:
                nci_label = "Profit attributable to noncontrolling interests"
                parent_label = "Profit attributable to parent shareholders"
            self.put(nci_label, self.link(attribution["nci"]), dollar=True)
            self.put(parent_label, self.link(attribution["parent"]))

    def ratio(self, label, row, of):
        self.put(label, [f"=IF({self.col(t)}{of}=0,\"\",{self.col(t)}{row}/{self.col(t)}{of})" for t in range(self.n)],
                 "ratio")

    # -- balance sheet ----------------------------------------------------------------------

    def account_label(self, a):
        if a.kind in ("deferred_tax_asset", "deferred_tax_liability"):
            return f"{self.L(a.kind)}: {a.category or a.name}"
        if a.kind == "oci":
            return f"{self.L('oci')}: {a.name}"
        if a.kind in AUTOMATIC and a.name == _default_name(a.kind):
            return self.L(a.kind)
        return a.name

    def section(self, a):
        if a.kind in _BS_CURRENT:
            return "current"
        k = self.e.layout.bs_kind(a.kind)
        return k.section if k is not None else None

    def balance_sheet(self):
        """US GAAP and J-GAAP: current first, cash first, liabilities before equity. IFRS: non-current first,
        cash last among current assets, equity before liabilities."""
        e, r_ = self.e, self.w.r
        self.sheet("BS")
        ifrs = e.standard.bs_order == "noncurrent_first"
        nonzero = lambda a: any(abs(statements._vec(r_, e._balance(a))[ts[-1]] or 0) > 1e-12 for _, ts in self.groups)
        self.first_line = True

        def line(a, plus=None):
            r = self.put(self.account_label(a), self.link(e._balance(a), plus=plus, stock=True), dollar=self.first_line)
            self.first_line = False
            return r

        def side(name):
            accounts = [a for a in e._accounts if a.side == name and (nonzero(a) or a is e._cash_account)]
            current = sorted((a for a in accounts if self.section(a) == "current"),
                             key=lambda a: (a is e._cash_account) if ifrs else (a is not e._cash_account))  # cash last (IFRS) or first
            return current, [a for a in accounts if a not in current]

        def block(current, rest, current_total, rest_total):
            lines = []
            for group, total in ((rest, rest_total), (current, current_total)) if ifrs else \
                    ((current, current_total), (rest, None)):
                rows = [line(a) for a in group]
                lines += rows
                if rows and total and (current and rest):
                    self.put(self.L(total), self.sum_of(rows), "total")
            return lines

        totals = {}
        self.put(self.L("assets"), None, "header")
        cur, rest = side("asset")
        totals["asset"] = self.put(self.L("total_assets"), self.sum_of(block(cur, rest, "current_assets", "noncurrent_assets")),
                                   "grand", dollar=True)
        self.gap()
        self.put(self.L("liabilities_equity"), None, "header")

        def liabilities():
            cur, rest = side("liability")
            totals["liability"] = self.put(self.L("total_liabilities"),
                                           self.sum_of(block(cur, rest, "current_liabilities", "noncurrent_liabilities")), "total")

        def equity():
            eq = []
            group_nci = getattr(e, "_group_profit_attribution", None) is not None
            for a in e._accounts:
                if ledger.ACQUISITION_CLEARING in a.tags:
                    continue
                if group_nci and a.side == "equity" and a.kind == "nci":
                    continue
                if a.side == "equity" and (a.kind == "retained_earnings" or nonzero(a)):
                    eq.append(line(a, plus=e._cum_profit if a.kind == "retained_earnings" else None))
            if group_nci and any(
                    abs(statements._vec(r_, e.bs.nci.total)[ts[-1]] or 0) > 1e-12 for _, ts in self.groups):
                eq.append(self.put(self.L("nci"), self.link(e.bs.nci.total, stock=True), dollar=self.first_line))
                self.first_line = False
            totals["equity"] = self.put(self.L("total_equity"), self.sum_of(eq), "total")

        for part in ((equity, liabilities) if ifrs else (liabilities, equity)):
            part()
        grand = self.put(self.L("total_liabilities_equity"), self.sum_of([totals["liability"], totals["equity"]]),
                         "grand", dollar=True)
        self.gap()
        self.put(self.L("balance_check"), [f"=ROUND({self.col(t)}{totals['asset']}-{self.col(t)}{grand},6)"
                                           for t in range(self.n)], "check")

    # -- cash flow --------------------------------------------------------------------------

    def cash_flow(self):
        e = self.e
        self.sheet("CF")
        rows = [self.put(self.L(cls), self.link(getattr(e.cf, cls)), dollar=i == 0) for i, cls in enumerate(_cf_classes(e))]
        net = self.put(self.L("net_change"), self.sum_of(rows), "total")
        end_row = self.next + 1
        self.put(self.L("cash_begin"), [f"={self.col(t)}{end_row}-{self.col(t)}{net}" for t in range(self.n)])
        self.put(self.L("cash_end"), self.link(e.bs.cash, stock=True), "grand", dollar=True)

    # -- schedules --------------------------------------------------------------------------

    def schedules(self):
        """Roll-forwards: opening balance, each movement from the ledger, closing = opening + movements."""
        e = self.e
        self.sheet("SC")
        for section, accounts in schedule_accounts(e).items():
            self.put(self.L(section), None, "header")
            for a in accounts:
                self.roll_forward(a, itemized=section != "working_capital")
            self.gap()

    def roll_forward(self, a, itemized: bool):
        e, F = self.e, self.w.font
        up = 1 if a.side == "asset" else -1               # debits raise an asset, credits raise a liability
        moves = [(p, up) for p in a.debits] + [(p, -up) for p in a.credits]
        moves.sort(key=lambda m: m[1] < 0)               # increases first: drawn, then repaid
        r0 = self.next
        self.ws.cell(r0, 1, self.account_label(a)).font = F(bold=True)
        self.next += 1
        opening = self.next
        self.next += 1                                    # filled in below, once the movement rows are known
        rows = []
        if itemized:
            names: dict[str, list] = {}
            for p, sign in moves:
                names.setdefault(_movement_name(a, p), []).append((p, sign))
            for name, ps in names.items():
                rows.append(self.put(name, self.combine(ps)))
        else:
            for key, want in (("additions", 1), ("reductions", -1)):
                ps = [(p, s_) for p, s_ in moves if s_ == want]
                if ps:
                    rows.append(self.put(self.L(key), self.combine(ps)))
        bal_links = self.link(e._balance(a), stock=True)
        closing_cells = [
            bal_links[t] if self.col_actual[t] else
            "=" + "+".join([f"{self.col(t)}{opening}"] + [f"{self.col(t)}{r}" for r in rows])
            for t in range(self.n)
        ]
        closing = self.put(self.L("closing"), closing_cells, "total")
        o = a.opening
        if o is None:
            first = "0"
        elif isinstance(o, S.Const):
            first = _literal(o.value)
        elif isinstance(o, ledger._OpeningPlug):
            first = _literal(self.w.r._r.value(o, None))
        else:
            first = self.w.ref(o, 0, qualified=True)      # collect() gave every opening balance a row
        cells = [f"={first}/{_literal(self.st.scale)}" if self.st.scale != 1 else f"={first}"] + \
            [f"={self.col(t - 1)}{closing}" for t in range(1, self.n)]
        r, self.next = self.next, opening
        self.put(self.L("opening"), cells)
        self.next = r
        interest = next((p for p in e._postings if p.name == f"{a.name} interest"), None)
        if interest is not None:
            m = self.put(self.L("interest_memo"), self.link(interest.amount))
            self.ws.cell(m, 1).font = F(italic=True)

    def combine(self, ps):
        """Signed sum of several postings' amounts, one cell per column."""
        k = self.st.scale
        out = []
        for _, ts in self.groups:
            body = "".join(("+" if s_ > 0 else "-") + self.span(p.amount, ts, False) for p, s_ in ps).lstrip("+")
            out.append("=" + (f"({body})/{_literal(k)}" if k != 1 else body))
        return out


def schedule_accounts(e) -> dict[str, list]:
    """Accounts that get a roll-forward on the Schedules sheet: debt, fixed assets, working capital."""
    out: dict[str, list] = {"debt": [], "fixed_assets": [], "working_capital": []}
    for a in e._accounts:
        if a.side not in ("asset", "liability") or a is e._cash_account or not (a.debits or a.credits):
            continue
        k = e.layout.bs_kind(a.kind)
        mech = k.mechanism if k is not None else ("construction" if a.kind == "construction" else "line")
        if mech == "loan":
            out["debt"].append(a)
        elif mech in ("fixed_asset", "construction"):
            out["fixed_assets"].append(a)
        elif a.cf == "operating" and a.kind not in ("deferred_tax_asset", "deferred_tax_liability"):
            out["working_capital"].append(a)
    return {k: v for k, v in out.items() if v}


def _movement_name(account, posting) -> str:
    """'Term loan (drawn)' on the Term loan account reads 'Drawn'."""
    name = posting.name
    if name.startswith(account.name):
        rest = name[len(account.name):].strip(" :()")
        if rest:
            return rest[0].upper() + rest[1:]
    return name


def _by_format(u: Unit) -> bool:
    """A display unit that a number format alone can show: the base unit or a power of 1000 above it."""
    return u.scale == 1 or (u.scale > 1 and _powers_of_1000(u.scale) > 0)


def _with_decimal(fmt: str) -> str:
    """A number format with one decimal place, unless it has decimals already (1.2 MWh, not 1)."""
    return fmt if "#,##0." in fmt else fmt.replace("#,##0", "#,##0.0")


def _reciprocal(factor: float) -> int | None:
    """n when factor is 1/n for a whole n > 1 (a monthly rate shown per year divides by 1/12: multiply by 12)."""
    n = round(1 / factor) if factor else 0
    return n if n > 1 and math.isclose(1 / n, factor, rel_tol=1e-12) else None


def _times(expr: str, factor: float) -> str:
    """The value behind a cell shown as value / factor."""
    if factor == 1:
        return expr
    if factor > 0 and (n := _reciprocal(factor)):
        return f"({expr}/{n})"
    if factor == -1:
        return f"(-{expr})"
    return f"(-{expr}*{_literal(-factor)})" if factor < 0 else f"({expr}*{_literal(factor)})"


def _shown(formula: str, factor: float) -> str:
    """A formula for the value, shown as value / factor."""
    if factor == 1:
        return formula
    if factor > 0 and (n := _reciprocal(factor)):
        return f"({formula})*{n}"
    sign, k = ("-" if factor < 0 else ""), abs(factor)
    return f"{sign}({formula})" + (f"/{_literal(k)}" if k != 1 else "")


def _sheet_ref(name: str) -> str:
    return name if name.replace("_", "").isalnum() and name.isascii() else "'" + name.replace("'", "''") + "'"


def column_groups(model, entity, style) -> list[tuple[str | int, list[int]]]:
    """Statement columns: one per fiscal year (the entity's, else the calendar year) when the model's periods
    are shorter than a year, else one per period. style.columns="periods" keeps the model's periods."""
    periods = model.timeline.periods
    if style.columns == "periods" or all(p.months >= 12 or p.start is None for p in periods):
        return [(style.period_label(p, entity.fiscal), [t]) for t, p in enumerate(periods)]
    fiscal = entity.fiscal or statements.Fiscal("12-31")
    groups: list[tuple[str | int, list[int]]] = []
    for t, p in enumerate(periods):
        end = fiscal._end_for(p.start)
        label = f"{end.year}年{end.month}月期" if style.periods == "ja" else \
            (end.year if style.periods == "fy" else f"FY{end.year}-{end.month:02d}")
        if groups and groups[-1][0] == label:
            groups[-1][1].append(t)
        else:
            groups.append((label, [t]))
    return groups


_TIMELINE = {"t": "period number", "date": "period start", "period_end": "period end",
             "period_length": "months in period"}


def _helper_label(node) -> str:
    return node.name or f"({type(node).__name__.strip('_').lower()})"


def _atom(formula: str) -> str:
    """The formula as one operand: unchanged when it is a function call or a parenthesized group as a whole
    (SUM(...), (a+b)), else in parentheses, so that x/formula and formula^2 apply to all of it."""
    head = 0
    while head < len(formula) and (formula[head].isalnum() or formula[head] in "._"):
        head += 1
    if formula.endswith(")") and head < len(formula) and formula[head] == "(":
        depth, quoted = 0, False
        for i, ch in enumerate(formula[head:], head):
            if ch == '"':
                quoted = not quoted
            elif not quoted and ch == "(":
                depth += 1
            elif not quoted and ch == ")":
                depth -= 1
                if depth == 0:
                    if i == len(formula) - 1:
                        return formula
                    break
    return f"({formula})"


GUARD_NOTE = ("boki: NA() stands for a part of this formula that boki does not read in this period (an IF branch "
              "not taken, or the rest of a row INDEX picks one cell from). Written out, it would make a circular "
              "reference that boki does not have. If changed inputs make this cell read it, the cell shows #N/A: "
              "export again from boki.")


def _or_na(text: str | None) -> str:
    return "NA()" if text is None else text


def _components(edges: dict) -> dict:
    """Strongly connected components (Tarjan, iterative): node -> (component number, its size)."""
    index: dict = {}
    low: dict = {}
    on: set = set()
    stack: list = []
    out: dict = {}
    counter = 0
    for root in edges:
        if root in index:
            continue
        work = [(root, iter(edges.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(edges.get(w, ()))))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    members = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        members.append(w)
                        if w == v:
                            break
                    for w in members:
                        out[w] = (index[v], len(members))
    return out


def _reaches(starts, goal, edges, comp) -> bool:
    """True when goal can be reached from any of starts (searching only goal's component: a path back to goal
    stays inside it)."""
    home = comp[goal][0]
    seen, todo = set(), [v for v in starts if comp.get(v, (None,))[0] == home]
    while todo:
        v = todo.pop()
        if v == goal:
            return True
        if v in seen:
            continue
        seen.add(v)
        todo.extend(w for w in edges.get(v, ()) if w not in seen and comp.get(w, (None,))[0] == home)
    return False


def _target_gap(balance: ledger._Balance) -> ledger._Gap | None:
    """When an account's closing balance is determined by a single target= (_Gap) posting, return that Gap."""
    a = balance.account
    postings = a.debits + a.credits
    if len(postings) != 1:
        return None
    amt = postings[0].amount
    if isinstance(amt, S.Where) and isinstance(amt.else_, S.Const) and amt.else_.value == 0:
        amt = amt.then
    if isinstance(amt, ledger._Gap) and amt.balance is balance:
        return amt
    return None


def _unwrap_neg(expr: str) -> str | None:
    """For '(-C8)' or '(-IS!F13)' return 'C8' / 'IS!F13', avoiding double-negation 'x-(-y)' in banker sheets."""
    if not (expr.startswith("(-") and expr.endswith(")")):
        return None
    inner = expr[2:-1]
    if not inner or any(ch in inner for ch in "+-*/^,() "):
        return None
    return inner


def _unwrap_neg_sum(expr: str) -> list[str] | None:
    """For '((-C11)+(-C12)+(-C13))' return ['C11', 'C12', 'C13'], turning 'C9-((-C11)+(-C12))' into '(C9+C11+C12)'."""
    if not (expr.startswith("(") and expr.endswith(")")):
        return None
    body = expr[1:-1]
    parts: list[str] = []
    depth, start = 0, 0
    for i, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "+" and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    if len(parts) < 2:
        return None
    out = []
    for p in parts:
        u = _unwrap_neg(p)
        if u is None:
            return None
        out.append(u)
    return out


def _sum(parts: list[str]) -> str:
    if not parts:
        return "0"
    return parts[0] if len(parts) == 1 else f"({'+'.join(parts)})"


def _lower_first(label: str) -> str:
    """'Operating expenses' -> 'operating expenses' after 'Total'; acronyms such as 'SG&A' stay."""
    return label[0].lower() + label[1:] if len(label) > 1 and label[1].islower() else label


def _default_name(kind: str) -> str:
    return ledger.AUTOMATIC_NAMES[kind]


def _sheet_name(title: str) -> str:
    r"""Excel sheet names: at most 31 characters, none of []:*?/\ and no quotes (they need escaping)."""
    return "".join(ch for ch in title if ch not in "[]:*?/\\'")[:31]


def _boolean(node) -> bool:
    while isinstance(node, S.Named) and node.expr is not None:
        node = node.expr
    if isinstance(node, S.Const):
        return isinstance(node.value, bool)
    if isinstance(node, S.Where):
        return _boolean(node.then) or _boolean(node.else_)
    return isinstance(node, S.Op) and (node.fn in S._CMP or node.fn in (S._and, S._or, S._not))


def _literal(v) -> str:
    if v is None:
        return "NA()"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        if isinstance(v, float):
            if not math.isfinite(v):
                raise Untranslatable("non-finite number")
            v = float(f"{v:.15g}")                  # Excel keeps 15 digits: 1400000, not 1400000.0000000002
        if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
            return str(int(v))                      # 1000000, not 1000000.0
        return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, date):
        return f"DATE({v.year},{v.month},{v.day})"
    if hasattr(v, "value"):
        return _literal(v.value)
    raise Untranslatable(type(v).__name__)


def _value(v):
    if hasattr(v, "value") and not isinstance(v, (int, float)):
        return v.value
    if isinstance(v, date) or isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def to_excel(result: "Result", path, style: Style | None = None, sheets=None, *,
             scenarios=None, omit_unused_model: bool = False, checks: bool | None = None,
             **overrides) -> Report:
    """Write the model with formulas (see the module docstring). Returns what was written as formulas.

    style= is a preset from boki.styles (banker when omitted); keyword arguments override it:
    to_excel(r, path, money="$mm", units={generation: MWh}, hide=[...]).

    sheets= places rows on sheets of their own, in reading order (boki.placement):
    to_excel(r, path, sheets=[b.sheet("Sales", [b.section("Customers", [customers, b.row(revenue)])])]).
    """
    style = style or styles.banker
    if overrides:
        style = style.replace(**overrides)
    w = _Writer(result, style, sheets, scenarios=scenarios, omit_unused_model=omit_unused_model, checks=checks)
    w.plan()
    if w.report.unnamed:
        shown = "\n  ".join(w.report.unnamed[:20]) + ("\n  …" if len(w.report.unnamed) > 20 else "")
        raise UnnamedAssumption(f"{len(w.report.unnamed)} assumption tables have no name; a table needs a row, and "
                                f"a row a name. Name each with m.input(\"…\", …):\n  {shown}")
    report = w.write(path)
    for note in w.guard_notes:
        import warnings
        warnings.warn(note, CircularReferenceWarning, stacklevel=3)
    return report
