# Line item

A {class}`~boki.LineItem` is what a line maker returns (``co.pl.revenue("Sales", 100)``): a series that belongs to an
entity's books. The {doc}`line-maker` page describes how lines are created, and the {doc}`makers/index` pages the
arguments of each kind.

```{eval-rst}
.. autoclass:: boki.LineItem
   :members: change, opening
```

The method ``draw_or_repay`` exists on loan lines only, so it has its own page: {doc}`makers/line-item-loan`.

```{toctree}
:hidden:

makers/line-item-loan
```
