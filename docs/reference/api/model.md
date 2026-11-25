# Model

A {class}`~boki.Model` holds the timeline, inputs, named series, entities and checks; {meth}`~boki.Model.render`
evaluates it and returns a {doc}`result`. Series are described on the {doc}`series` page, and entities and groups on
their own pages.

```{eval-rst}
.. autoclass:: boki.Model
   :members: check, entity, fx, group, input, n, render, series, solve, unknown

.. py:attribute:: boki.Model.date

   First day of each period, a date series; missing for an undated model. See the Attributes of :class:`boki.Model`.

.. py:attribute:: boki.Model.period_end

   First day after each period, which is the start of the next one. See the Attributes of :class:`boki.Model`.
```

## Inputs and unknowns

```{eval-rst}
.. autoclass:: boki.model.Input

.. autoclass:: boki.model.Unknown
```

## Timeline and periods

```{eval-rst}
.. autoclass:: boki.model.Timeline
   :members: regular

.. autoclass:: boki.model.Period
   :members: end

.. autofunction:: boki.timeline

.. autofunction:: boki.date
```

## Errors

```{eval-rst}
.. autoclass:: boki.CycleError
```
