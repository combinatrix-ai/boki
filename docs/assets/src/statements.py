"""Write the README's sample workbooks: the quickstart model in several styles and standards.

    uv run python docs/assets/src/statements.py OUT_DIR
Then render with LibreOffice (soffice --headless --convert-to pdf) and screenshot (see render.sh).
"""
import sys
from pathlib import Path

import boki as b
from boki.lib import compound
from boki.units import USD, year


def widget(standard):
    m = b.Model("Widget Co", start="2027-01", periods=5, step=year)
    co = m.entity("Widget Co", standard=standard, currency=USD)
    co.bs.opening(cash=20e6 * USD)
    growth = m.input("Revenue growth", 0.25)
    sales = co.pl.revenue("Product sales", compound(40e6 * USD, growth))
    co.pl.cogs("Cost of sales", 0.45 * sales)
    co.pl.sga("Operating expenses", 6e6 * USD + 0.15 * sales)
    co.bs.receivable("Accounts receivable", target=0.12 * sales)
    co.bs.fixed_asset("Plant", 30e6 * USD, at=0, life=10 * year)
    co.bs.loan("Term loan", draw={0: 25e6 * USD}, rate=0.07, repay=5e6 * USD)
    co.pl.income_tax("Income taxes", rate=0.21, base=co.pl.pretax_income)
    return m.render()


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    us, ifrs, jp = widget(b.USGAAP), widget(b.IFRS), widget(b.JGAAP)
    us.to_excel(out / "banker-usgaap.xlsx", money="$mm")
    us.to_excel(out / "sec-usgaap.xlsx", style=b.styles.sec, money="$mm")
    ifrs.to_excel(out / "banker-ifrs.xlsx", money="$mm")
    ifrs.to_excel(out / "sec-ifrs.xlsx", style=b.styles.sec, money="$mm")
    jp.to_excel(out / "japanese-jgaap.xlsx", style=b.styles.japanese, money="百万円")
