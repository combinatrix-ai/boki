"""The landing page shows a real model: its hero code builds the statement its hero table shows."""
import html
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "site/index.html"


def _hero_table() -> dict[str, list[str]]:
    table = re.search(r'<table class="fs">(.*?)</table>', PAGE.read_text(encoding="utf-8"), re.S).group(1)
    rows = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) == 6 and cells[0]:
            rows.setdefault(cells[0], []).append(cells[1:])
    return rows


def _excel_round(value, places):  # Excel rounds halves away from zero
    return Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)


def _money(values, negative=False):
    shown = [_excel_round(v / 1e6, 1) for v in values]
    return ["–" if x == 0 else f"({x})" if negative else f"{x}" for x in shown]


def _percent(values):
    return [f"{_excel_round(v * 100, 1)}%" for v in values]


def test_hero_table_is_the_income_statement_of_the_hero_code():
    code = html.unescape(re.sub(r"<[^>]+>", "", re.search(r'<div class="code">(.*?)</div>', PAGE.read_text(
        encoding="utf-8"), re.S).group(1))).replace("plan.py", "", 1)
    *model, export = code.strip().splitlines()
    assert export.startswith("m.render().to_excel(")
    names = {}
    exec("\n".join(model), names)
    m, co, sales = names["m"], names["co"], names["sales"]
    cogs, opex, tax = co.pl.cogs.items[0], co.pl.sga.items[0], co.pl.income_tax.items[0]
    plant, loan = co.bs.fixed_asset.items[0], co.bs.loan.items[0]
    r = m.render()

    revenue = r[sales]
    expected = {
        "Revenue": [_money(revenue)],
        "% growth": [[""] + _percent([b_ / a - 1 for a, b_ in zip(revenue, revenue[1:])])],
        "Cost of revenue": [_money(r[cogs], negative=True)],
        "Gross profit": [_money(r[co.pl.gross_profit])],
        "Operating expenses": [_money(r[opex], negative=True)],
        "Plant depreciation": [_money(r[plant.depreciation], negative=True)],
        "Total operating expenses": [_money(r[co.pl.sga.total], negative=True)],
        "Operating income (EBIT)": [_money(r[co.pl.operating_income])],
        "Interest expense": [_money(r[loan.interest_expense], negative=True)],
        "Pre-tax income": [_money(r[co.pl.pretax_income])],
        "Income taxes": [_money(r[tax], negative=True)],
        "% effective tax rate": [_percent([t / p for t, p in zip(r[tax], r[co.pl.pretax_income])])],
        "Net income": [_money(r[co.pl.net_income])],
        "% margin": [_percent([x / s for x, s in zip(r[line], revenue)]) for line in
                     (co.pl.gross_profit, co.pl.operating_income, co.pl.pretax_income, co.pl.net_income)],
    }
    assert _hero_table() == expected
