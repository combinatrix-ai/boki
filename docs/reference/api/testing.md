# Comparing with a source

`boki.testing` sets a render beside figures taken from the original spreadsheet. `expect` fails on a mismatch;
`compare` shows every number with its difference. `approx`, `above`, `below` and `between` make a reference that is a range
instead of one number.

```{eval-rst}
.. autofunction:: boki.expect

.. autofunction:: boki.compare

.. autofunction:: boki.approx

.. autofunction:: boki.above

.. autofunction:: boki.below

.. autofunction:: boki.between

.. autoclass:: boki.testing.Comparison
   :members: mismatches

.. autoclass:: boki.testing.Entry
   :members: diff

.. autoclass:: boki.testing.Bound
```
