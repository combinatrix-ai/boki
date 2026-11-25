# Result

{meth}`boki.Model.render` returns a {class}`~boki.Result`: read series values from it, draw statements and tables, and
write the Excel workbook.

```{eval-rst}
.. autoclass:: boki.Result
   :members: bs, cf, display_unit, pl, table, to_excel, value
   :special-members: __getitem__

.. py:attribute:: boki.Result.checks

   The outcome of every check evaluated in the render, as :class:`boki.model.CheckResult` objects. See the
   Attributes of :class:`boki.Result`.
```

## Tables

```{eval-rst}
.. autoclass:: boki.statements.Table

.. autoclass:: boki.statements.Row
```

Excel output (`Result.to_excel`, `Report` and the export warnings) is on the [output page](output.md).

## Checks

```{eval-rst}
.. autoclass:: boki.model.CheckResult

.. autoclass:: boki.CheckFailed
```
