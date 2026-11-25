"""boki: business-plan modeling with lazy series, units, explicit solving, and (soon) a double-entry ledger."""
from . import export, layouts, lib, units
from .evaluator import CycleError
from .excel import EquivalenceError
from .layouts import IFRS, JGAAP, USGAAP
from .lib import nol
from .ledger import LineItem, LineMaker
from .shapes import by_month, by_year, curve, delay, even, mix, step
from .placement import block, link, panel, row, section, sensitivity, sheet
from .statements import LedgerError, calendar, fiscal
from .styles import Style, styles
from .model import CheckFailed, Model, Result, parse_date as date, timeline
from .series import (Series, mod, rounddown, roundup, sceil as ceil, sexp as exp, sfloor as floor, slog as log,
                     smax as max, smin as min, sround as round, ssqrt as sqrt)
from .testing import above, approx, below, between, compare, expect
from .units import Quantity, Unit, UnitError, day, h, month, quarter, unit, year

__all__ = [
    "IFRS", "JGAAP", "LedgerError", "LineItem", "LineMaker", "USGAAP", "calendar", "curve", "delay", "even",
    "fiscal", "mix",
    "CheckFailed", "EquivalenceError", "block", "link", "panel", "row", "section", "sensitivity", "sheet", "CycleError", "Model",
    "Quantity", "Result", "Series", "Unit", "UnitError",
    "above", "approx", "below", "between", "by_month", "by_year", "ceil", "compare", "date", "day", "exp", "expect", "floor", "h", "log", "max", "min", "mod",
    "lib", "nol",
    "month", "quarter", "round", "rounddown", "roundup", "sqrt",
    "step", "Style", "styles", "timeline", "unit", "units", "year", "export", "layouts",
]
