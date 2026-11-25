"""Export a plan's render to Excel with formulas, recalculate it with the `formulas` package, and compare
every Model cell with boki's value.

    uv run python tools/excel_check.py examples/<name> [--keep out.xlsx]
"""
from __future__ import annotations

import argparse
import math
import runpy
import sys
import tempfile
import warnings
from pathlib import Path


def _use_excel_irr() -> None:
    """The formulas package's IRR ignores the guess (numpy_financial picks the root nearest 0), and its XIRR
    rejects a negative guess. Excel runs Newton's method from any guess above -100%, so with several roots the
    guess decides which one; do the same."""
    import numpy as np
    from formulas.functions import FUNCTIONS, wrap_func
    from formulas.functions.financial import Error, flatten, replace_empty, text2num

    def irr(values, guess=0.1):
        cf = [float(v) for v in flatten(text2num(replace_empty(values)).ravel())]
        x = float(np.ravel(text2num(replace_empty(guess)))[0])
        for _ in range(100):
            f = sum(c / (1 + x) ** t for t, c in enumerate(cf))
            d = sum(-t * c / (1 + x) ** (t + 1) for t, c in enumerate(cf))
            if d == 0:
                break
            step = f / d
            x -= step
            if abs(step) < 1e-12:
                return x
        return Error.errors["#NUM!"]

    def xirr(values, dates, guess=0.1):
        cf = [float(v) for v in flatten(text2num(replace_empty(values)).ravel())]
        days = [float(d) for d in flatten(text2num(replace_empty(dates)).ravel())]
        years = [(d - days[0]) / 365 for d in days]
        x = float(np.ravel(text2num(replace_empty(guess)))[0])
        for _ in range(100):
            if x <= -1:
                break
            f = sum(c / (1 + x) ** y for y, c in zip(years, cf))
            d = sum(-y * c / (1 + x) ** (y + 1) for y, c in zip(years, cf))
            if d == 0:
                break
            step = f / d
            x -= step
            if abs(step) < 1e-12:
                return x
        return Error.errors["#NUM!"]

    FUNCTIONS["IRR"] = wrap_func(irr)
    FUNCTIONS["XIRR"] = wrap_func(xirr)


def check(plan_dir: Path, keep: Path | None = None) -> dict:
    import formulas
    from boki import excel

    _use_excel_irr()

    sys.path.insert(0, str(plan_dir))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = runpy.run_path(str(plan_dir / "plan.py"), run_name="__plan__")
    from boki.model import Result
    results = [v for v in g.values() if isinstance(v, Result)]
    if not results:
        raise LookupError("the plan keeps no Result in a variable")
    result = g["r"] if isinstance(g.get("r"), Result) else results[-1]
    out = keep or Path(tempfile.mkdtemp()) / "model.xlsx"
    report = excel.to_excel(result, out)
    xl = formulas.ExcelModel().loads(str(out)).finish()
    sol = xl.calculate()
    values, sheets = {}, {}
    for key, rng in sol.items():
        k = str(key).upper()
        if "!" not in k or ":" in k.split("!")[1]:
            continue
        sheet, cell = k.split("]", 1)[1].split("'!") if "]" in k else (None, None)
        if sheet is None:
            continue
        sheets.setdefault(sheet.strip("'"), {})[cell] = rng.value[0, 0]
    values = sheets.get("MODEL", {})
    import openpyxl
    ws = openpyxl.load_workbook(out)["Model"]
    bad, compared = [], 0
    w = excel._Writer(result)
    w.plan()
    for row in w.rows:
        for t in range(w.n):
            cell = ws.cell(row.number, excel.FIRST_COL + t)
            if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                continue
            try:
                want = result._r.value(row.node, None if row.node.scalar else t) if not row.node.scalar or t == 0 else None
            except ArithmeticError:
                continue                       # a branch boki never takes (Excel shows #DIV/0! there)
            got = values.get(cell.coordinate)
            if want is None or hasattr(want, "year"):
                continue
            compared += 1
            try:
                ok = math.isclose(float(got), float(want), rel_tol=1e-9, abs_tol=1e-6)
            except (TypeError, ValueError):
                ok = False
            if not ok:
                bad.append((row.label, cell.coordinate, want, got, cell.value[:120]))
    # statement sheets (banker style): each profit matches boki, the BS balances, cash ends where boki's does
    wb = openpyxl.load_workbook(out)
    st = excel.styles.banker
    from boki.layouts import Stage
    for e in result.model.entities:
        sheets_of = {k: excel._sheet_name(f"{e.name} {k}") for k in ("IS", "BS", "CF")}
        groups = excel.column_groups(result.model, e, st)
        want = [(sheets_of["IS"], st.label(k.name, e.standard), getattr(e.pl, k.name), False)
                for k in e.layout.pl if isinstance(k, Stage)]
        want.append((sheets_of["CF"], st.label("cash_end", e.standard), e.bs.cash, True))
        for sheet, label, node, stock in want:
            ws_ = wb[sheet]
            row = next((r for r in range(1, ws_.max_row + 1) if (ws_.cell(r, 1).value or "").strip() == label), None)
            vals = sheets.get(sheet.upper(), {})
            per = excel.statements._vec(result, node)
            cols = [per[ts[-1]] if stock else (None if any(per[i] is None for i in ts) else sum(per[i] for i in ts))
                    for _, ts in groups]
            for t, v in enumerate(cols):
                compared += 1
                got = vals.get(f"{excel._col(excel.FIRST_COL - 1 + t)}{row}")
                if v is not None and not _close(got, v):
                    bad.append((f"{sheet} {label}", t, v, got, ws_.cell(row, excel.FIRST_COL + t).value))
        # schedules: each closing balance (opening + movements on the sheet) equals the ledger balance
        accounts = [a for group in excel.schedule_accounts(e).values() for a in group]
        if accounts:
            name = excel._sheet_name(f"{e.name} Schedules")
            ws_, vals = wb[name], sheets.get(name.upper(), {})
            closing = [r for r in range(1, ws_.max_row + 1) if ws_.cell(r, 1).value == st.label("closing", e.standard)]
            for a, row in zip(accounts, closing):
                per = excel.statements._vec(result, e._balance(a))
                for t, (_, ts) in enumerate(groups):
                    compared += 1
                    got = vals.get(f"{excel._col(excel.FIRST_COL - 1 + t)}{row}")
                    if not _close(got, per[ts[-1]]):
                        bad.append((f"schedule {a.name}", t, per[ts[-1]], got, ws_.cell(row, excel.FIRST_COL + t).value))
        ws_ = wb[sheets_of["BS"]]
        row = next(r for r in range(1, ws_.max_row + 1) if ws_.cell(r, 1).value == st.label("balance_check", e.standard))
        vals = sheets.get(sheets_of["BS"].upper(), {})
        for t in range(len(groups)):
            compared += 1
            got = vals.get(f"{excel._col(excel.FIRST_COL - 1 + t)}{row}")
            if not _close(got, 0):
                bad.append(("BS does not balance", t, 0, got, ""))
    return {"report": report, "compared": compared, "bad": bad}


def _close(got, want) -> bool:
    try:
        return math.isclose(float(got), float(want), rel_tol=1e-9, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("plan", type=Path)
    p.add_argument("--keep", type=Path)
    a = p.parse_args()
    res = check(a.plan.resolve(), a.keep)
    print(res["report"])
    print(f"recalculated formula cells compared: {res['compared']}, mismatches: {len(res['bad'])}")
    for b in res["bad"][:15]:
        print("  ", b)
