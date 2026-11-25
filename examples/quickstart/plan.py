import boki as b
from boki.lib import compound
from boki.units import USD, year

m = b.Model("Widget Co", start="2027-01", periods=5, step=year)
co = m.entity("Widget Co", standard=b.USGAAP, currency=USD)
co.bs.opening(cash=20e6 * USD)

growth = m.input("Revenue growth", 0.25)
sales = co.pl.revenue("Product sales", compound(40e6 * USD, growth))
co.pl.cogs("Cost of sales", 0.45 * sales)
co.pl.sga("Operating expenses", 6e6 * USD + 0.15 * sales)
co.bs.receivable("Accounts receivable", target=0.12 * sales)
co.bs.fixed_asset("Plant", 30e6 * USD, at=0, life=10 * year)
co.bs.loan("Term loan", draw={0: 25e6 * USD}, rate=0.07, repay=5e6 * USD)
co.pl.income_tax("Income taxes", rate=0.21, base=co.pl.pretax_income)

r = m.render()
r.to_excel("widget.xlsx", money="$mm")      # banker style: IS / BS / CF linked to a formula Model sheet
