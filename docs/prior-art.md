# Comparison with existing libraries and products

Surveyed on 2026-10-16. I read each project's official documentation, PyPI page, and README but did not install or run it.

## Conclusion

Each part of boki already exists on its own.

- Memoized evaluation of time-indexed formulas: modelx, heavylight, and cashflower (for actuarial models).
- Stock-and-flow simulation: BPTK-Py and PySD (system dynamics).
- Plans with named variables and time dimensions: Causal, Pigment, and Anaplan (FP&A products).
- Forecast future transactions in a double-entry ledger: hledger forecasting and the Fava forecast plugin.
- Programmatic pro forma models: pyproforma, PyCashflow, rangekeeper, and finstmt.

I did not find the following combination:

1. **Forecasting with double-entry journal entries as the source of truth.** Ledger tools such as hledger and Beancount focus on recording actuals. Forecasts repeat scheduled transactions, but do not express formulas, drivers, or backsolving. Planning tools such as Causal, pyproforma, and modelx can express formulas, but users must reconcile P&L, BS, and CF themselves.
2. **Unit type checks**, such as `GPU × $/GPU/h`, that prevent combining incompatible quantities. None of the tools I reviewed provide them.
3. **Explicit syntax for backsolving and cycles**, such as `solve`, sculpting, and fixed-point iteration. modelx and heavylight can express recursion, but users must write the iteration for cycles. heavylight documents stack-depth limits for forward references such as NPV.
4. **A corpus of checks against calculated values in source Excel files**, using `expect`.

However, **boki's core (named series and pull-based memoized evaluation) is close to modelx**. The main difference is whether accounts, moves, units, kernels, and `solve` are built in from the start. The question "Would an accounting library on top of modelx be enough?" remains open, as discussed below.

## Compare tool families

| Family | Examples | Similarities | Differences | What boki can use |
|---|---|---|---|---|
| Memoized recursive formulas (actuarial) | [modelx](https://docs.modelx.io/) (+[lifelib](https://pypi.org/project/lifelib/)), [heavylight](https://pypi.org/project/heavylight/), [cashflower](https://pypi.org/project/cashflower/) | Define variables as functions of time `t` and recurse with `f(t-1)`. Cache results. modelx also tracks dependencies, copies models with different parameters, and exports models as Python modules without modelx dependencies. | No accounting (accounts, BS, or CF) or units. Users write their own cycle iteration. heavylight can recurse deeply on forward references. | Evaluator design (Cells as memoized functions, Space as namespace, and parameterization). The idea of exporting a model as plain Python. |
| System dynamics | [BPTK-Py](https://bptk.transentis.com/), PySD | `model.stock()`, `flow()`, and `converter()` resemble boki's accounts, moves, and series. Supports XMILE (Stella) imports and agent-based models. | Assumes continuous-time integration (Euler method). No accounting or backsolving. | Stock-and-flow vocabulary and scenario management. |
| FP&A products | [Causal](https://www.lucanet.com/en/press-releases/causal-joins-the-lucanet-group-31-10-2024/) (acquired by Lucanet in 2024), [Pigment](https://kb.pigment.com/docs/models-formulas.md), [Anaplan](https://help.anaplan.com/6d742812-f1c7-4296-a504-651b1c8086f3) | Use named variables instead of cell references and treat time as a dimension. | These GUI products do not support code diffs or tests. Their strength is first-class **dimensions** (product × region × department × entity). | **Dimensions.** boki currently substitutes Python `for` loops and dictionaries, which is weaker for group-company and product-level plans. |
| Text-based double-entry bookkeeping | [hledger forecasting](https://hledger.org/forecasting.html), [Fava forecast plugin](https://beancount.io/docs/Tips/forecast-plugin) | Forecasts live in a double-entry ledger, so P&L and BS reports are available directly. | Forecasts repeat scheduled transactions. They cannot express drivers (customer count × price), collection-delay distributions, or backsolving. | Ledger format. Export boki results in Beancount format and verify them with Fava. |
| Code-based pro forma models | [pyproforma](https://pyproforma.readthedocs.io/), [PyCashflow](https://github.com/kmiller96/pycashflow), [rangekeeper](https://github.com/daniel-fink/rangekeeper) (real estate DCF), [finstmt](https://pypi.org/project/finstmt/), [waccy](https://github.com/DecisionNerd/waccy) | Share the concern that "Excel has no version control or tests" (pyproforma README). Define rows with expressions such as `lambda li, t: li.revenue[t] * 0.55`. | They use a single table of rows, without accounts, double-entry bookkeeping, units, or backsolving. I did not find these features on pyproforma's homepage. finstmt focuses on loading historical statements and forecasting. | Table exports to HTML, Excel, and DataFrames. |
| Valuation-function libraries | pyfinmod, efin | Provide NPV, IRR, DCF, and WACC. | Do not provide a model-building system. | Reference implementations of valuation functions for the standard library. |

## Expressing the six cases with existing tools

| Case | Easiest existing tool | Main gaps |
|---|---|---|
| capbudg (capital budgeting) | pyproforma, modelx | No major gaps. The model is too small to show much difference. |
| Ginzu (DCF) | modelx | NOL balance and terminal year. It can express the model but offers no accounting support. |
| LBO | modelx | Book-value equity balance and repayment schedule. Users reconcile CF by hand. |
| SaaS | BPTK-Py (plan transitions are stocks and flows) | Backsolve from target MRR, align deferred revenue and sales, and round to whole numbers. |
| Solar project finance | modelx (write iterations like Bodmer's by hand) | Forward references in sculpting, cycles among uses, debt, and construction interest, and waterfalls. |
| Japan Finance Corporation izakaya | hledger forecasting for the ledger, plus Excel for the supporting formulas | Count business days by weekday, model collection delays, and ramp-up. |

boki has a clear advantage when **a model needs accounting consistency and also has backsolving or cycles**, such as solar project finance, SaaS deferred revenue, and Japan Finance Corporation cash flow. For formula-only models such as DCF, boki offers little over modelx.

## Context in 2025–2026: LLMs write plans

- LLM agents are entering Excel through products such as Microsoft Copilot and Claude for Excel. If "have an LLM write Excel" becomes common, boki offers another option: have an LLM write text, review the diff, and verify it with tests.
- Anthropic's skill catalog also lists a financial-modeling skill, `creating-financial-models` ([smithery](https://smithery.ai/skills/anthropics/creating-financial-models)). I have not reviewed its contents.
- In this context, boki's unit checks and `expect` comparisons can detect errors in LLM-generated models. A small example appeared in the capbudg sheet: NPV included the salvage value, but IRR did not.

## Claims and open questions

Claims we can make:

- boki connects ledger tools and planning tools. A formula-based plan becomes a double-entry ledger, keeping P&L, BS, and CF consistent.
- boki checks unit types.
- boki makes backsolving and cycles explicit. These require macros or iteration in Excel and hand-written iteration in modelx.

Unverified claims:

- If accounts, moves, and units can be added to modelx to create boki, there may be little reason to build a custom evaluator. I have not tested how much of boki's requirements modelx can handle: forward references with `lag(-1)`, simultaneous `solve`, kernel convolution, and units.
- How much the lack of dimensions (product × region × entity) limits practical plans, especially for groups of companies.

## Proposed next steps

1. **Model the solar project in modelx.** Measure how hard sculpting, cycles, and waterfalls are to express. If the difference is small, build boki as a library on modelx.
2. **Decide whether dimensions belong in the core.** Write a group-company model (entity × account) and a product-sales model (product × month) to see whether Python loops and dictionaries are enough.
3. Add Beancount export early as a verification tool. Fava can display the P&L and BS.

## Sources checked on 2026-10-16

- modelx: https://docs.modelx.io/, https://pypi.org/project/modelx/
- lifelib: https://pypi.org/project/lifelib/
- heavylight: https://pypi.org/project/heavylight/
- cashflower: https://pypi.org/project/cashflower/
- BPTK-Py: https://bptk.transentis.com/, https://pypi.org/project/bptk-py/
- Causal (acquired by Lucanet): https://www.lucanet.com/en/press-releases/causal-joins-the-lucanet-group-31-10-2024/
- Pigment: https://kb.pigment.com/docs/models-formulas.md
- Anaplan: https://help.anaplan.com/6d742812-f1c7-4296-a504-651b1c8086f3
- hledger forecasting: https://hledger.org/forecasting.html
- Fava forecast plugin: https://beancount.io/docs/Tips/forecast-plugin
- pyproforma: https://pyproforma.readthedocs.io/
- PyCashflow: https://github.com/kmiller96/pycashflow
- rangekeeper: https://github.com/daniel-fink/rangekeeper
- finstmt: https://pypi.org/project/finstmt/
- waccy: https://github.com/DecisionNerd/waccy
- pyfinmod: https://pypi.org/project/pyfinmod/0.2
- creating-financial-models skill: https://smithery.ai/skills/anthropics/creating-financial-models
