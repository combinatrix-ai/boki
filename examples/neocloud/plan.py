# Neocloud (GPU cloud) business plan. First plan written from scratch in boki, not ported from an existing Excel workbook.
# All figures are placeholders and have not been researched.
#
# Overlapping commitments with different terms: DC lease (10 years, payable whether used or not), debt (5 years), depreciation (6 years),
# and customer contracts (3-year take-or-pay). After contract expiry, results depend on market price and utilization.
#
#   uv run python examples/neocloud/plan.py [out-dir]
import sys
from pathlib import Path

import boki as b
from boki.lib import discount, irr
from boki.units import MW, USD, h, kW, kWh, month, year

GPU = b.unit("GPU")
HOURS = 730 * h / month                      # Hours in a month (365 × 24 ÷ 12).

m = b.Model("NeoCloud", start="2026-10", periods=120, step=month)
co = m.entity("NeoCloud", standard=b.USGAAP, currency=USD, fiscal=b.fiscal(year_end="12-31"))

# ---- Assumptions --------------------------------------------------------------------
sofr = m.input("SOFR", b.step({"2026-10": 0.040, "2028-01": 0.035}) / year)
spread = m.input("loan spread", 0.055 / year)
undrawn_fee = m.input("undrawn fee", 0.005 / year)
dscr_target = m.input("sizing DSCR", 1.30)
max_ltv = m.input("max LTV", 0.90)
market_price = m.input("market price", 2.35 * USD / GPU / h, scenarios={"bear": 1.40 * USD / GPU / h})
utilization = m.input("utilization after contract", 0.70)
power_price = m.input("power price", 0.08 * USD / kWh)
gpu_power = m.input("power per GPU", 1.4 * kW / GPU)
pue = m.input("PUE", 1.25)
ops_cost = m.input("operations per GPU", 60 * USD / GPU / month)
min_cash = m.input("minimum cash", 2_000_000 * USD)
lockup = m.input("distribution lock-up DSCR", 1.20)

# ---- Data center: lease capacity for 10 years; pay whether used or not ----------------
dc_capacity = 10 * MW
dc_rent_rate = 140 * USD / kW / month
co.pl.cogs("DC rent", dc_rent_rate * dc_capacity * month)
co.pl.sga("corporate overhead", 300_000 * USD)

rate = m.series("loan rate", (sofr + spread) * m.period_length)   # Period interest rate.
df = discount(rate)                                                  # Period-end discount factors to model start.


# ---- Clusters: order → delivery (5 months) → operation (1 month), one per generation ------
class Cluster:
    def __init__(self, name, gpus, unit_cost, order, contract_price, term=36, tenor=60):
        o = m.timeline.index(order)
        self.name, self.order, self.delivery, self.live = name, o, o + 5, o + 6
        self.contract = (m.t >= self.live) & (m.t < self.live + term)
        self.after = m.t >= self.live + term
        self.power_kw = gpus * gpu_power * pue
        self.hardware = m.series(f"{name} hardware cost", gpus * unit_cost)

        # Hardware: pay 20% at order and 80% at delivery; depreciate over 6 years from operation.
        self.plant = co.bs.construction(
            f"{name} hardware", spend=self.hardware * (0.2 * (m.t == o) + 0.8 * (m.t == self.delivery)),
            complete_at=self.live, life=6 * year)

        # Customer contract: take-or-pay. Receive 15% of total contract value at order and deduct it from monthly invoices; collect the balance the following month.
        monthly = gpus * HOURS * month * contract_price
        prepay = 0.15 * monthly * term
        self.contract_revenue = co.pl.revenue(
            f"{name} contract", monthly.where(self.contract, 0),
            cash=prepay * (m.t == o) + (0.85 * monthly).where(self.contract, 0).lag(1, fill=0 * USD))
        co.pl.revenue(f"{name} spot", (gpus * HOURS * month * utilization * market_price).where(self.after, 0))

        load = self.contract * 1.0 + self.after * utilization
        self.power = power = co.pl.cogs(f"{name} power", self.power_kw * HOURS * month * load * power_price)
        self.ops = ops = co.pl.cogs(f"{name} operations", (gpus * ops_cost * month).where(m.t >= self.live, 0))

        # Debt is underwritten against the contract, not the GPUs: use the lower of the present value of contract CFADS ÷ DSCR (sculpted) and 90% of hardware cost.
        # Match repayments to contract cash flow (target debt service − interest), with a bullet at maturity (5 years after delivery).
        rent_share = dc_rent_rate * self.power_kw * month
        # The 15% advance is deducted from invoices, so monthly collections are 85%; the advance funds the order payment.
        self.cfads = m.series(f"{name} contract CFADS",
                              (0.85 * monthly - power - ops - rent_share).where(self.contract, 0))
        target_ds = self.cfads / dscr_target
        pv = (target_ds * df).sum() / df[self.delivery]
        self.size = m.series(f"{name} debt size", b.min(pv, max_ltv * self.hardware))
        maturity = self.delivery + tenor
        self.loan = co.bs.loan(
            f"{name} loan", draw={self.delivery: self.size}, rate=rate,
            repay=lambda ln: (target_ds - ln.interest).where(self.contract, 0) + ln.opening.where(m.t == maturity, 0))
        co.pl.interest_expense(f"{name} undrawn fee", (self.size * undrawn_fee * m.period_length)
                               .where((m.t >= o) & (m.t < self.delivery), 0))
        self.debt_service = m.series(f"{name} debt service", self.loan.interest + self.loan.principal)
        self.committed_in = m.series(f"{name} committed receipts", prepay * (m.t == o)
                                     + (0.85 * monthly).where(self.contract, 0).lag(1, fill=0 * USD))


batches = [
    Cluster("batch1", 1024 * GPU, 50_000 * USD / GPU, "2026-11", 3.00 * USD / GPU / h),
    Cluster("batch2", 2048 * GPU, 60_000 * USD / GPU, "2027-06", 3.50 * USD / GPU / h),
]
m.check(sum((c.power_kw for c in batches), 0 * kW) <= dc_capacity, "GPUs fit in the leased DC capacity")

co.pl.income_tax("income tax", rate=0.21, base=co.pl.pretax_income)

# ---- Cash flow: DSRA (6 months of debt service) → distributions when DSCR clears lock-up ----
debt_service = m.series("debt service", sum((c.debt_service for c in batches), 0 * USD))
co.bs.asset("DSRA", target=sum((debt_service.lag(-k, fill=0 * USD) for k in range(1, 7)), 0 * USD),
            cf="investing")
interest = sum((c.loan.interest for c in batches), 0 * USD)
has_debt_service = debt_service > 1 * USD                        # A sculpted loan amortizes to a rounding residue, not to exactly zero.
dscr = m.series("DSCR", ((co.cf.operating + interest) / debt_service).where(has_debt_service, 99))

# Contribute only enough equity to restore the minimum cash balance when needed; the total is required equity.
equity_in = m.series("equity contributions")                     # Forward declaration: amount depends on cash before contributions and distributions.
distributions = m.series("distributions")
sponsor = co.bs.capital("sponsor equity", equity_in)
paid = co.bs.dividend("distributions", distributions)
before = co.bs.cash.opening + co.cf.operating + co.cf.investing + co.cf.financing_excluding(sponsor, paid)
operating = m.t > max(c.live for c in batches)                  # After all clusters are online and the first collection arrives.
equity_in.define(b.max(min_cash - before, 0 * USD))
distributions.define(b.max(before - min_cash, 0 * USD).where(operating & (dscr >= lockup), 0 * USD))
required_equity = m.series("required equity", equity_in.sum())

# ---- Outputs -------------------------------------------------------------------------
last = m.n - 1
equity_cf = m.series("equity cash flow", distributions - equity_in + co.bs.cash.where(m.t == last, 0))
equity_irr = m.series("equity IRR (annual)", (1 + irr(equity_cf)) ** 12 - 1)
min_dscr = dscr.where(operating & has_debt_service).min()
ltv = {c.name: c.size / c.hardware for c in batches}

# Commitment ladder: contractually committed receipts and payments due whether capacity is used or not.
committed_in = m.series("committed receipts", sum((c.committed_in for c in batches), 0 * USD))
committed_out = m.series("committed payments (DC rent + debt service)", dc_rent_rate * dc_capacity * month + debt_service)

# Cost per GPU-hour (average over batch2 contract, $/GPU-h).
c2 = batches[1]
gpu_hours = (2048 * GPU * HOURS * month).where(c2.contract, 0).sum()
per_hour = {"power": c2.power, "operations": c2.ops, "depreciation": c2.plant.depreciation,
            "interest": c2.loan.interest}
cost_stack = {k: (v.where(c2.contract, 0).sum() / gpu_hours) for k, v in per_hour.items()}
cost_stack["DC rent (share)"] = (dc_rent_rate * c2.power_kw * month).where(c2.contract, 0).sum() / gpu_hours

r = m.render()

if __name__ == "__main__":
    print(f"required equity    {r[required_equity] / 1e6:10.1f} $mm")
    for c in batches:
        print(f"{c.name} debt       {r[c.size] / 1e6:10.1f} $mm  (LTV {r[ltv[c.name]]:.0%})")
    print(f"min DSCR           {r[min_dscr]:10.2f}")
    print(f"equity IRR         {r[equity_irr]:10.1%}")

    print("\ncost per GPU-hour, batch2 contract ($3.50 price):")
    for k, v in cost_stack.items():
        print(f"  {k:18} {r[v]:6.3f}")
    print(f"  {'total':18} {sum(r[v] for v in cost_stack.values()):6.3f}")

    print("\ncommitment ladder ($mm per year):")
    print(r.table([committed_in, committed_out], unit=1e6 * USD, by="fiscal_year", entity=co))

    print("\nsensitivity (market price after contract × utilization):")
    print(f"  {'':8} {'util':>5} {'equity $mm':>11} {'equity IRR':>11}")
    for scenario in (None, "bear"):
        for u in (0.5, 0.7, 0.9):
            s_ = m.render(scenario=scenario, inputs={utilization: u})
            print(f"  {scenario or 'base':8} {u:5.0%} {s_[required_equity] / 1e6:11.1f} {s_[equity_irr]:11.1%}")

    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
        print(r.to_excel(out / "neocloud.xlsx", money="$mm"))
