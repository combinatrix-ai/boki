# Groups

A group consolidates entities under a parent. `m.group(name, parent=entity)` creates one, `own` records the ownership
events, and the consolidated statements are derived from the members' ledgers. Read them with `r.pl(group)`,
`r.bs(group)` and `r.cf(group)`, or take `group.books`, the consolidated ledger as an entity. The consolidation rules
for each accounting standard are in the
[consolidation notes](https://github.com/combinatrix-ai/boki/blob/main/docs/consolidation.md).

```{eval-rst}
.. autoclass:: boki.group.core.Group
   :members: own, books, operating_income, depreciation, amortization, ebit, ebitda, ebitdar, adjusted_ebitda, noi
```
