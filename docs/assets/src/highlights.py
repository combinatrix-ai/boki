"""Print the outputs quoted in the README's highlights, so they stay true to the code.

    uv run python docs/assets/src/highlights.py
"""
import warnings

import boki as b
from boki.units import USD, kW, year

warnings.simplefilter("ignore")

print("== The accounting is done for you")
m = b.Model("Bakery", start="2027-01", periods=3, step=year)
co = m.entity("Bakery", standard=b.USGAAP, currency=USD)
co.bs.opening(cash=50 * USD)
co.pl.revenue("Sales", 120 * USD, settle=b.delay(1))        # customers pay a period later
co.pl.cogs("Flour", 70 * USD, settle=b.delay(1))            # and so do we
co.bs.fixed_asset("Oven", 60 * USD, at=0, life=3 * year)
r = m.render()
print(r.cf(co, method="indirect"))

print("\n== 会計は boki がやる（README.ja.md）")
from boki.units import JPY
m = b.Model("パン屋", start="2027-04", periods=3, step=year)
co = m.entity("パン屋", standard=b.JGAAP, currency=JPY, fiscal=b.fiscal(year_end="03-31"))
co.bs.opening(cash=500 * JPY)
co.pl.revenue("売上", 1_200 * JPY, settle=b.delay(1))      # 入金は翌期
co.pl.cogs("小麦粉", 700 * JPY, settle=b.delay(1))         # 支払も翌期
co.bs.fixed_asset("オーブン", 600 * JPY, at=0, life=3 * year)
print(m.render().cf(co, method="indirect"))

print("\n== Mistakes that cannot get through")
m = b.Model("Solar", start="2027-01", periods=3, step=year)
co = m.entity("Solar", standard=b.USGAAP, currency=USD)
capacity = m.input("Capacity", 6_000 * kW)
try:
    co.pl.cogs("O&M", 100_000 * USD + capacity)
except b.UnitError as e:
    print(f"UnitError: {e}")
m = b.Model("Cafe", start="2027-01", periods=3, step=year)
co = m.entity("Cafe", standard=b.USGAAP, currency=USD)
co.bs.opening(cash=10 * USD)
co.pl.sga("Rent", 8 * USD)
m.check(co.bs.cash >= 0, "never runs out of cash")
try:
    m.render()
except b.CheckFailed as e:
    print(f"CheckFailed: {e}")

print("\n== The hard parts are explicit")
m = b.Model("Plant", start="2027-01", periods=3, step=year)
debt = m.series("Debt")
interest = m.series("Interest during construction", 0.08 * debt)
debt.define(1_000 * USD + interest)
try:
    m.render()[debt]
except b.CycleError as e:
    print(f"CycleError: {e}")
m = b.Model("Plant", start="2027-01", periods=3, step=year)
debt = m.unknown("Debt", unit=USD.dims)
interest = m.series("Interest during construction", 0.08 * debt)
m.solve(debt, debt == 1_000 * USD + interest)
print("solved:", round(m.render()[debt], 2))

print("\n== It is just code")
import runpy
from pathlib import Path
g = runpy.run_path(str(Path(__file__).resolve().parents[3] / "examples/quickstart/plan.py"), run_name="__plan__")
m, co = g["m"], g["co"]
b.expect(m.render(), {co.pl.net_income: [7.9e6, 7.3e6, 11.5e6, 16.7e6, 23.2e6]}, rel=0.01)
print("expect: passed")
try:
    b.expect(m.render(inputs={"Revenue growth": 0.20}), {co.pl.net_income: [7.9e6, 7.3e6, 11.5e6, 16.7e6, 23.2e6]}, rel=0.01)
except AssertionError as e:
    print(e)
