<p align="center">
  <img src="docs/assets/icon.svg" width="88" height="88" alt="boki">
</p>

<h1 align="center">boki</h1>

<p align="center">
  <b>Financial models as code. Banker-grade Excel as output.</b><br>
  Write the business in Python. Compile 3-statement, LBO, and DCF workbooks where every cell is a live, verified formula — built for engineers and AI agents.
</p>

<p align="center">
  <a href="https://combinatrix.ai/boki/">Website</a> ·
  <a href="https://combinatrix.ai/boki/docs/">Docs</a> ·
  <a href="README.ja.md">日本語</a>
</p>

<p align="center">
  <img src="docs/assets/ib-showcase.svg" alt="boki IB-grade Excel output: LBO Returns with live 2D sensitivity and DCF Valuation Summary">
</p>

Spreadsheet models cannot be diffed, tested, or reviewed, and their hardest parts — circular references, macro-pasted values, broken links — are the least visible. **boki** keeps the model in Python and compiles Excel as the output, not the source.

---

## Quickstart

```sh
uv add "boki[excel]"   # or: pip install "boki[excel]"
```

Core `boki` has **zero required dependencies**; the `[excel]` extra installs `openpyxl` for `.xlsx` export.

```python
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

m.render().to_excel("widget.xlsx", money="$mm")
```

You never wrote a journal entry, a depreciation schedule, or a cash-flow statement — they are all live formulas in `widget.xlsx` (`Inputs`, `IS`, `BS`, `CF`, `Schedules`, `Checks`, `Model`).

---

## Investment-banking grade models

boki builds presentation-ready IB workbooks with historical actuals (`actual_until` + `actuals=`, `FY2024A` | `FY2025E` divider), proof-carrying Excel formula rewrites (`b.row(..., formula=...)`, `b.block`), live `=INDEX` scenario switchers (`Inputs!$C$3`), 2D summary panels (`b.panel`), live 2D sensitivity matrices (`b.sensitivity`), and optional omission of the `Model` sheet (`omit_unused_model=True`).

Three complete benchmark workbooks ship in `examples/` and are recalculated and verified automatically in `pytest` with **zero formula mismatches**:

| Model | Example | Highlights |
|---|---|---|
| **3-Statement** | [examples/ib_3statement](examples/ib_3statement/) | 3Y historical actuals (2022A–2024A) + 5Y forecast (2025E–2029E), US GAAP, indirect CF, Valuation & Credit Bridge, zero `Model` sheet |
| **LBO** | [examples/ib_lbo](examples/ib_lbo/) | Live Sources & Uses, Goodwill, Pro Forma Opening BS, 2-tranche Debt Waterfall + 100% Excess Cash Sweep, Exit Bridge, Sponsor IRR/MoIC, live Entry × Exit sensitivity |
| **DCF** | [examples/ib_dcf](examples/ib_dcf/) | CAPM WACC, mid-year discounted UFCF, Perpetuity Growth & Exit Multiple cross-check, live WACC × g and WACC × Exit Multiple sensitivity |

```sh
uv run python examples/ib_lbo/plan.py out/         # generates out/apex_lbo.xlsx
uv run python examples/ib_dcf/plan.py out/         # generates out/veridian_dcf.xlsx
uv run python examples/ib_3statement/plan.py out/  # generates out/acme_ib_3statement.xlsx
```

---

## Every number is a live formula

<p align="center">
  <img src="docs/assets/formula-trace.svg" alt="Live Excel formula trace from Inputs to Income Statement to Checks">
</p>

Every assumption lives once on `Inputs` in blue, flows cleanly through statement formulas in black, and ties out automatically on `Checks`. An analyst can change a growth rate, scenario selector, or sensitivity axis header right inside Excel and watch the entire workbook recalculate.

---

## Built for AI agents — mistakes cannot get through

<p align="center">
  <img src="docs/assets/agent-guardrails.svg" alt="Four compile-time guardrails that verify AI-generated financial models before exporting Excel">
</p>

Editing spreadsheets by cell coordinates is fragile for humans and worse for LLMs. With `boki`, an engineer or AI agent writes typed Python and `boki` enforces four hard guardrails before a single cell hits Excel:

1. **Units are types.** Adding `USD` and `kW` raises `UnitError` immediately.
2. **Double-entry ledger.** Every line posts double entries; the balance sheet balances and `CF = ΔCash` in every period of every scenario.
3. **Explicit circularity.** Debt sculpting, interest during construction, and goal seeks are solved explicitly with `m.solve`; any unintended loop stops with `CycleError`:
   ```python
   debt = m.unknown("Debt", unit=USD.dims)
   idc = m.series("Interest during construction", 0.08 * debt)
   m.solve(debt, debt == 1_000 * USD + idc)   # 1,086.96
   ```
4. **Proof-carrying Excel rewrites.** Override verbose ledger expansions with clean banker `=SUM(...)` blocks — `boki` verifies equivalence across Base, all scenarios, and random perturbations before writing (`EquivalenceError` on mismatch):
   ```python
   b.block(
       co.cf.operating,
       [co.pl.net_income, depreciation, change_in_nwc],
       label="Cash flow from operations",
       verify="perturb",
   )
   ```

And because it is just Python, you can diff assumptions in Git, run scenarios in a loop, and pin board-approved numbers in `pytest`:

```python
b.expect(m.render(), {co.pl.net_income: [7.9e6, 7.3e6, 11.5e6, 16.7e6, 23.2e6]}, rel=0.01)
```

---

## Proof

| Metric | Result |
|---|---|
| Public financial models rewritten in `boki` | **228** |
| Models reproducing their source workbooks | **211** |
| Silent inconsistencies uncovered in published originals | **102** (across 50 models) |
| Formula mismatches across all exported Excel workbooks | **0** |

The 117 matching models published by public bodies and universities are catalogued in [docs/public-models.md](docs/public-models.md) alongside every source inconsistency found. Every formula cell `boki` exports is recalculated by an independent engine and compared against Python.

---

## Features & multi-standard support

Switch between **US GAAP**, **IFRS**, and **J-GAAP** — or between `banker`, `sec` (10-K), `japanese`, and `plain` Excel styles — without rewriting your business logic.

- **Time & actuals**: monthly, quarterly, annual, or mixed-frequency timelines; fiscal years (including year-end changes); historical actuals (`actual_until` + `actuals=`) with automatic opening-balance handoff into forecast.
- **Accounting**: double-entry ledger, payment terms (`settle=`), deferred revenue/prepaids (`recognize=`), VAT, opening BS, arbitrary journal entries, indirect & direct cash flow.
- **Assets & debt**: straight-line, declining-balance, MACRS tax depreciation, construction in progress with capitalized interest, multi-tranche loans, revolvers, cash sweeps.
- **Consolidation**: non-controlling interests, goodwill, equity & cost methods, intercompany eliminations, foreign subsidiary translation.
- **Tax & finance**: income tax with loss carryforwards and brackets; `npv`, `irr`, `xirr`, `pmt`, `wacc`, `capm`, `gordon`, `levelized`, `black_scholes`, banded `lookup`.
- **Excel & Beancount**: custom sheet layouts (`b.sheet`, `b.section`, `b.row`, `b.link`), verified blocks (`b.block`), 2D panels (`b.panel`), live 2D sensitivities (`b.sensitivity`), live scenario switches (`scenarios=`), Beancount ledger export.

---

## Documentation & status

- **Website**: [combinatrix.ai/boki](https://combinatrix.ai/boki/)
- **User guide & API reference**: [combinatrix.ai/boki/docs](https://combinatrix.ai/boki/docs/)
- **More examples**: [examples/neocloud](examples/neocloud/) (GPU cloud project finance), [examples/quickstart](examples/quickstart/)
- **Design notes**: [docs/](docs/README.md)

**Status**: `v0.1` (pre-1.0 — the API may evolve). Not there yet: a cover sheet, accounting-policy differences between standards (goodwill amortization, leases).

## License

[MIT](LICENSE).
