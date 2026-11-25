# Excel and Beancount output

`r.to_excel(path, ...)` writes a workbook with live formulas. The {py:class}`boki.Style` decides how it looks,
`b.sheet`, `b.section`, `b.row`, `b.block`, `b.panel` and `b.link` decide where rows go, and the returned
{py:class}`boki.excel.Report` says what was written. `boki.export.to_beancount` writes an entity's ledger as Beancount
text. The narrative guides are the
[Excel notes](https://github.com/combinatrix-ai/boki/blob/main/docs/excel.md) and the
[Excel presentation notes](https://github.com/combinatrix-ai/boki/blob/main/docs/excel-presentation.md).

## Style

```{eval-rst}
.. autoclass:: boki.Style
   :members: replace
   :special-members: __call__

.. autoclass:: boki.styles.styles
```

## Placement

```{eval-rst}
.. autofunction:: boki.sheet

.. autofunction:: boki.section

.. autofunction:: boki.row

.. autofunction:: boki.link

.. autofunction:: boki.block

.. autofunction:: boki.panel

.. autofunction:: boki.sensitivity

.. autoclass:: boki.placement.Sheet

.. autoclass:: boki.placement.Section

.. autoclass:: boki.placement.Line

.. autoclass:: boki.placement.Link

.. autoclass:: boki.placement.Block

.. autoclass:: boki.placement.Panel

.. autoclass:: boki.placement.Sensitivity
```

## The report and its warnings

```{eval-rst}
.. autoclass:: boki.excel.Report

.. autoexception:: boki.excel.Untranslatable

.. autoexception:: boki.excel.UnnamedAssumption

.. autoexception:: boki.excel.EquivalenceError

.. autoexception:: boki.excel.CircularReferenceWarning
```

## Beancount

```{eval-rst}
.. autofunction:: boki.export.to_beancount
```
