# Standard library

`boki.lib` holds financial formulas that follow published definitions, such as discounting, returns, cost of capital,
tax depreciation, and option value. They build ordinary series, so they take scalars, quantities, and series, and
their results work in expressions and in Excel output. Rates are dimensionless and per period unless a function says
otherwise: `0.01` is 1% per period whether the period is a month or a year. See the
[conventions](https://github.com/combinatrix-ai/boki/blob/main/docs/conventions.md) for the timing of flows, year
zero, and signs.

## Growth and lookup

```{eval-rst}
.. autofunction:: boki.lib.compound

.. autofunction:: boki.lib.index

.. autofunction:: boki.lib.fade

.. autofunction:: boki.lib.lookup
```

## Discounting and returns

```{eval-rst}
.. autofunction:: boki.lib.discount

.. autofunction:: boki.lib.npv

.. autofunction:: boki.lib.xnpv

.. autofunction:: boki.lib.irr

.. autofunction:: boki.lib.xirr

.. autoexception:: boki.lib.NoRateOfReturn

.. autofunction:: boki.lib.gordon

.. autofunction:: boki.lib.levelized

.. autofunction:: boki.lib.pmt
```

## Cost of capital and options

```{eval-rst}
.. autofunction:: boki.lib.capm

.. autofunction:: boki.lib.hamada

.. autofunction:: boki.lib.wacc

.. autofunction:: boki.lib.black_scholes
```

## Tax and regulatory capital

```{eval-rst}
.. autofunction:: boki.lib.macrs

.. autofunction:: boki.lib.straight_line

.. autofunction:: boki.lib.nol

.. autofunction:: boki.lib.ssfa
```
