# Entities and statements

An entity is a company with its own books. `m.entity(...)` creates one, and its income statement (`co.pl`), balance
sheet (`co.bs`) and cash-flow statement (`co.cf`) are built from the entity's layout. The line makers inside `co.pl`
and `co.bs` are documented on the {doc}`line-maker` page and the {doc}`makers/index` pages. This page documents
everything else on the entity, the statement objects, fiscal calendars, business-day calendars, and the error raised
when the books do not balance.

## Entity

The four OCI names are four different things: `co.oci(...)` books an item, `co.bs.oci` is the equity line maker that holds
the accumulated amount, `co.other_comprehensive_income` is the series of the period's OCI, and `co.oci_release(...)`
reclassifies accumulated OCI.

```{eval-rst}
.. autoclass:: boki.ledger.Entity
   :members: journal, label, oci, oci_release, vat_settlement, currency, language, operating_income, depreciation,
      amortization, ebit, ebitda, ebitdar, adjusted_ebitda, noi

.. autoclass:: boki.ledger.EntityChecks
   :members: cash
```

## Statements

```{eval-rst}
.. autoclass:: boki.ledger.PL

.. autoclass:: boki.ledger.BS
   :members: opening, asset, liability, deferred_tax, sell

.. autoclass:: boki.ledger._Equity

.. autoclass:: boki.ledger.CF
   :members: financing_excluding
```

## Calendars

```{eval-rst}
.. autofunction:: boki.fiscal

.. autoclass:: boki.statements.Fiscal
   :members: label

.. autofunction:: boki.calendar

.. autoclass:: boki.statements.Calendar
   :members: days
```

## Errors

```{eval-rst}
.. autoexception:: boki.LedgerError
```
