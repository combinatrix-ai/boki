# Series

A {class}`~boki.Series` is a lazily evaluated expression over the model's periods. Make one with
{meth}`boki.Model.series`, {meth}`boki.Model.input` or {meth}`boki.Model.unknown`; the operations below build new series
and check units while the model is being written, and values exist only in a {doc}`render <result>`.

```{eval-rst}
.. autoclass:: boki.Series
   :members: change, cumsum, lag, last, max, mean, min, month, opening, reverse_cumsum, spread, sum, where, year
   :special-members: __getitem__, __add__, __radd__, __sub__, __rsub__, __mul__, __rmul__, __truediv__, __rtruediv__, __mod__, __rmod__, __floordiv__, __rfloordiv__, __pow__, __rpow__, __neg__, __abs__, __lt__, __le__, __gt__, __ge__, __eq__, __ne__, __and__, __rand__, __or__, __ror__, __invert__
```

## Named series

```{eval-rst}
.. autoclass:: boki.series.Named
   :members: define
```

Inputs and unknowns are series too: see {class}`boki.model.Input` and {class}`boki.model.Unknown`. The line items of an
entity are described on the {doc}`line-item` page.

## Functions of series

These take series, numbers or quantities and return series. They work period by period; for a reduction over the
periods use {meth}`boki.Series.sum`, {meth}`boki.Series.min`, {meth}`boki.Series.max` and {meth}`boki.Series.mean`.

```{eval-rst}
.. autofunction:: boki.max

.. autofunction:: boki.min

.. autofunction:: boki.round

.. autofunction:: boki.rounddown

.. autofunction:: boki.roundup

.. autofunction:: boki.ceil

.. autofunction:: boki.floor

.. autofunction:: boki.mod

.. autofunction:: boki.exp

.. autofunction:: boki.log

.. autofunction:: boki.sqrt
```
