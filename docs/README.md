# boki design documents

The user documentation is the Sphinx site built from [index.md](index.md), [guide/](guide/index.md) and [reference/api/](reference/api/) (`uv run sphinx-build -b html docs docs/_build/html`; `uv run python tools/build_site.py` builds the whole website into `_site/`: the landing page in `site/` at the root and these docs under `docs/`), plus the root [README.md](../README.md) (English) and [README.ja.md](../README.ja.md) (Japanese). This page indexes the development history and design documents, which are not part of the site and describe proposals as they were made.

A planned Python library for writing business plans. It treats timestamped journal entries as the source of truth, produces P&L, BS, and CF statements, represents amounts with units, and replaces reverse calculations and waterfalls that relied on Excel circular references or macros with explicit syntax.

```python
import boki as b
from boki.units import JPY, month

m = b.Model("example", start="2027-04", step=b.month, periods=36)
co = m.entity("example", standard=b.JGAAP, currency=JPY, fiscal=b.fiscal(year_end="03-31"))
co.bs.opening(cash=1_000_000 * JPY)

@m.series
def customers(t):
    return 0 if t == 0 else customers[t - 1] * (1 - 0.03) + 50

sales = co.pl.revenue("subscription", customers * 3000 * JPY / month, settle=b.delay(1))
co.pl.sga("hosting", 0.2 * sales, category="Other")
r = m.render()
r.pl(co, by="fiscal_year")
```

Status: Implemented through v0.3 (2026-10-16). The evaluator supports series, `@m.series`, memoization, cycle detection, `solve`, and unit checks. Entity support, P&L and BS rows, double-entry ledgers, direct and indirect cash flow statements, consistency checks, quantity rows, construction in progress, capitalized construction interest, and Beancount export (`b.export.to_beancount`) also work.

```sh
uv sync && uv run pytest
```

- [docs/api.md](api.md) — API design (v0.0.2 proposal). The corpus `plan.py` files use this API.
- [docs/api-principles.md](api-principles.md) — API principles: ledger rows carry an amount, time, and counterparty; `counterparty=`; quantities and series; time points; intermediate Excel rows; and boki as a compiler.
- [docs/goals.md](goals.md) — Goals and development plan. The evaluator is custom-built.
- [docs/double-entry.md](double-entry.md) — Proposal for representing double-entry bookkeeping with accounts and moves.
- [docs/entities-and-timeline.md](entities-and-timeline.md) — Proposal for entities, fiscal periods, account names, and consolidation.
- [docs/dsl-v0.0.1.md](dsl-v0.0.1.md) — DSL proposal and patterns found in public models.
- [docs/methods.md](methods.md) — Method reference (nine core methods and the standard library).
- [docs/prior-art.md](prior-art.md) — Comparison with existing libraries and products.
- [docs/modelx.md](modelx.md) — Survey of modelx features.

The design notes mention `research/` and `experiments/`: the corpus of rewritten public models, the experiments that used it, and the sweep reports that measured the API against it. They live in a separate repository because the plans follow their source workbooks cell by cell.
