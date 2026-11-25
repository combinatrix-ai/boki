# Time shapes and kernels

A time shape is a value that depends on the period: on the model year, the period, or the calendar month. A kernel
says how one amount spreads over its own and later periods, and drives `settle=`, `recognize=`, `used=`, and
`Series.spread`.

## Values over time

```{eval-rst}
.. autofunction:: boki.by_year

.. autofunction:: boki.step

.. autofunction:: boki.by_month
```

## Kernels

A kernel counts periods, not months, so `b.delay(1)` is a quarter in a quarterly model.

```{eval-rst}
.. autoclass:: boki.shapes.Kernel

.. autofunction:: boki.delay

.. autofunction:: boki.even

.. autofunction:: boki.curve

.. autofunction:: boki.mix

.. autofunction:: boki.shapes.spread
```
