# boki API surface (generated)

Generated from `docs/reference/public-api.toml` by `tools/api_inventory.py`. Do not edit by hand.

`classification`: public, readonly, or internal (reachable but unsupported).
`doc`: none / summary (one line) / prose (several lines, not numpydoc) / numpydoc.
`uses`: attribute-name hits in `examples/` (by name, so approximate).


## boki

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `CheckFailed` | public | class | numpydoc | 0 |  |
| `CycleError` | public | class | numpydoc | 0 |  |
| `EquivalenceError` | public | class | prose | 0 |  |
| `IFRS` | public | value | - | 0 |  |
| `JGAAP` | public | value | - | 0 |  |
| `LedgerError` | public | class | prose | 0 |  |
| `LineItem` | public | class | numpydoc | 0 |  |
| `LineMaker` | public | class | numpydoc | 0 |  |
| `Model` | public | class | numpydoc | 5 |  |
| `Quantity` | public | class | numpydoc | 0 |  |
| `Result` | public | class | numpydoc | 0 |  |
| `Series` | public | class | prose | 1 |  |
| `Style` | public | class | numpydoc | 0 |  |
| `USGAAP` | public | value | - | 5 |  |
| `Unit` | public | class | numpydoc | 0 |  |
| `UnitError` | public | class | prose | 0 |  |
| `above` | public | function | numpydoc | 0 | `(value) -> 'Bound'` |
| `approx` | public | function | numpydoc | 0 | `(value, tol: 'float \| None' = None, rel: 'float \| None' = None) -> 'Bound'` |
| `below` | public | function | numpydoc | 0 | `(value) -> 'Bound'` |
| `between` | public | function | numpydoc | 0 | `(lo, hi) -> 'Bound'` |
| `block` | public | function | numpydoc | 9 | `(target, rows, *, label: 'str \| None' = None, sign: 'int' = 1, total: 'bool \| str' = True, verify: 'str' = 'perturb', fmt: 'str \| None' = None) -> 'Block'` |
| `by_month` | public | function | numpydoc | 0 | `(values, default=None) -> 'Series'` |
| `by_year` | public | function | numpydoc | 0 | `(mapping: 'dict', default=None) -> 'Series'` |
| `calendar` | public | function | numpydoc | 0 | `(model, holidays=None, closed=()) -> 'Calendar'` |
| `ceil` | public | function | numpydoc | 0 | `(x) -> 'Series'` |
| `compare` | public | function | numpydoc | 0 | `(result, reference: 'dict', tol: 'float' = 0.01, rel: 'float' = 0.0001) -> 'Comparison'` |
| `curve` | public | function | numpydoc | 0 | `(weights) -> 'Kernel'` |
| `date` | public | function | numpydoc | 0 | `(x) -> 'date'` |
| `day` | public | value | - | 0 |  |
| `delay` | public | function | numpydoc | 0 | `(n: 'int') -> 'Kernel'` |
| `even` | public | function | numpydoc | 0 | `(n: 'int') -> 'Kernel'` |
| `exp` | public | function | numpydoc | 0 | `(x) -> 'Series'` |
| `expect` | public | function | numpydoc | 0 | `(result, expected: 'dict', tol: 'float' = 0.01, rel: 'float' = 0.0001) -> 'None'` |
| `export` | public | module | prose | 0 |  |
| `fiscal` | public | function | numpydoc | 1 | `(year_end: 'str', change: 'dict \| None' = None) -> 'Fiscal'` |
| `floor` | public | function | numpydoc | 0 | `(x) -> 'Series'` |
| `h` | public | value | - | 0 |  |
| `layouts` | public | module | prose | 0 |  |
| `lib` | public | module | summary | 0 |  |
| `link` | public | function | numpydoc | 38 | `(target, label: 'str \| None' = None, *, sign: 'int' = 1, total: 'bool \| str' = False, fmt: 'str \| None' = None) -> 'Link'` |
| `log` | public | function | numpydoc | 0 | `(x) -> 'Series'` |
| `max` | public | function | numpydoc | 8 | `(*xs) -> 'Series'` |
| `min` | public | function | numpydoc | 5 | `(*xs) -> 'Series'` |
| `mix` | public | function | numpydoc | 0 | `(parts: 'dict') -> 'Kernel'` |
| `mod` | public | function | numpydoc | 0 | `(x, n) -> 'Series'` |
| `month` | public | value | - | 0 |  |
| `nol` | public | function | numpydoc | 0 | `(base, opening=0, cap=None) -> 'NOL'` |
| `panel` | public | function | numpydoc | 7 | `(title: 'str', columns, rows) -> 'Panel'` |
| `quarter` | public | value | - | 0 |  |
| `round` | public | function | numpydoc | 0 | `(x, digits=0) -> 'Series'` |
| `rounddown` | public | function | numpydoc | 0 | `(x, digits=0) -> 'Series'` |
| `roundup` | public | function | numpydoc | 0 | `(x, digits=0) -> 'Series'` |
| `row` | public | function | numpydoc | 157 | `(series, label: 'str \| None' = None, *, sign: 'int' = 1, scale: 'float' = 1, total: 'bool \| str' = False, formula=None, verify: 'str' = 'perturb', fmt: 'str \| None' = None) -> 'Line'` |
| `section` | public | function | numpydoc | 34 | `(title: 'str', entries) -> 'Section'` |
| `sensitivity` | public | function | numpydoc | 4 | `(title: 'str', row_values, col_values, formula, *, fmt: 'str \| None' = None, row_fmt: 'str \| None' = None, col_fmt: 'str \| None' = None, highlight: 'tuple[int, int] \| None' = None, corner: 'str' = '') -> 'Sensitivity'` |
| `sheet` | public | function | numpydoc | 15 | `(name: 'str', entries, *, money: 'str \| float \| int \| None' = None) -> 'Sheet'` |
| `sqrt` | public | function | numpydoc | 0 | `(x) -> 'Series'` |
| `step` | public | function | numpydoc | 1 | `(mapping: 'dict') -> 'Series'` |
| `styles` | public | class | prose | 0 |  |
| `timeline` | public | function | numpydoc | 0 | `(start, segments: 'list[tuple]') -> 'Timeline'` |
| `unit` | public | function | numpydoc | 1 | `(name: 'str', definition: 'Quantity \| Unit \| None' = None) -> 'Unit'` |
| `units` | public | module | prose | 0 |  |
| `year` | public | value | - | 0 |  |

## boki.units

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `unit` | public | function | numpydoc | 0 | `(name: 'str', definition: 'Quantity \| Unit \| None' = None) -> 'Unit'` |
| `Unit` | public | class | numpydoc | 0 |  |
| `Quantity` | public | class | numpydoc | 0 |  |
| `UnitError` | public | class | prose | 0 |  |
| `USD` | public | value | - | 0 |  |
| `JPY` | public | value | - | 0 |  |
| `EUR` | public | value | - | 0 |  |
| `GBP` | public | value | - | 0 |  |
| `CNY` | public | value | - | 0 |  |
| `W` | public | value | - | 0 |  |
| `kW` | public | value | - | 0 |  |
| `MW` | public | value | - | 0 |  |
| `Wh` | public | value | - | 0 |  |
| `kWh` | public | value | - | 0 |  |
| `MWh` | public | value | - | 0 |  |
| `day` | public | value | - | 0 |  |
| `h` | public | value | - | 0 |  |
| `month` | public | value | - | 0 |  |
| `quarter` | public | value | - | 0 |  |
| `year` | public | value | - | 0 |  |

## boki.lib

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `black_scholes` | public | function | numpydoc | 0 | `(underlying, strike, years, volatility, rate, yield_=0.0, call: 'bool' = True) -> 'Series \| Quantity \| float'` |
| `capm` | public | function | numpydoc | 0 | `(beta, rf, erp) -> 'Series \| float'` |
| `compound` | public | function | numpydoc | 0 | `(x0, rate) -> 'Series'` |
| `discount` | public | function | numpydoc | 0 | `(rate) -> 'Series'` |
| `fade` | public | function | numpydoc | 0 | `(a, b, over: 'tuple') -> 'Series'` |
| `gordon` | public | function | numpydoc | 0 | `(cash_flow, rate, growth) -> 'Series'` |
| `hamada` | public | function | numpydoc | 0 | `(unlevered, de, tax) -> 'Series \| float'` |
| `index` | public | function | numpydoc | 1 | `(rate, when=None, start=None) -> 'Series'` |
| `irr` | public | function | numpydoc | 0 | `(cash_flows, initial=None, *, running: 'bool' = False, default=None) -> 'Series'` |
| `levelized` | public | function | numpydoc | 0 | `(cost, quantity, rate) -> 'Series'` |
| `lookup` | public | function | numpydoc | 0 | `(x, table: 'dict') -> 'Series'` |
| `macrs` | public | function | numpydoc | 0 | `(years: 'int') -> 'Kernel'` |
| `nol` | public | function | numpydoc | 0 | `(base, opening=0, cap=None) -> 'NOL'` |
| `npv` | public | function | numpydoc | 0 | `(cash_flows, rate, at: 'int' = -1, initial=None) -> 'Series'` |
| `pmt` | public | function | numpydoc | 0 | `(rate, n, pv) -> 'Series \| Quantity \| float'` |
| `ssfa` | public | function | numpydoc | 0 | `(kg: 'float', w: 'float', attachment: 'float', detachment: 'float', p: 'float' = 0.5, floor: 'float' = 0.2) -> 'float'` |
| `straight_line` | public | function | numpydoc | 0 | `(years: 'int', half_year: 'bool' = True) -> 'Kernel'` |
| `wacc` | public | function | numpydoc | 0 | `(cost_of_equity, cost_of_debt, debt_ratio, tax) -> 'Series \| float'` |
| `xirr` | public | function | numpydoc | 0 | `(cash_flows, dates, *, default=None) -> 'Series'` |
| `xnpv` | public | function | numpydoc | 0 | `(cash_flows, rate, dates) -> 'Series'` |
| `NoRateOfReturn` | public | class | prose | 0 |  |

## boki.shapes

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `Kernel` | public | class | numpydoc | 0 |  |
| `by_month` | public | function | numpydoc | 0 | `(values, default=None) -> 'Series'` |
| `by_year` | public | function | numpydoc | 0 | `(mapping: 'dict', default=None) -> 'Series'` |
| `curve` | public | function | numpydoc | 0 | `(weights) -> 'Kernel'` |
| `delay` | public | function | numpydoc | 0 | `(n: 'int') -> 'Kernel'` |
| `even` | public | function | numpydoc | 0 | `(n: 'int') -> 'Kernel'` |
| `mix` | public | function | numpydoc | 0 | `(parts: 'dict') -> 'Kernel'` |
| `spread` | public | function | numpydoc | 0 | `(src, kernel: 'Kernel') -> 'Series'` |
| `step` | public | function | numpydoc | 0 | `(mapping: 'dict') -> 'Series'` |

## boki.testing

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `Bound` | public | class | numpydoc | 0 |  |
| `Comparison` | public | class | numpydoc | 0 |  |
| `Entry` | public | class | numpydoc | 0 |  |
| `above` | public | function | numpydoc | 0 | `(value) -> 'Bound'` |
| `approx` | public | function | numpydoc | 0 | `(value, tol: 'float \| None' = None, rel: 'float \| None' = None) -> 'Bound'` |
| `below` | public | function | numpydoc | 0 | `(value) -> 'Bound'` |
| `between` | public | function | numpydoc | 0 | `(lo, hi) -> 'Bound'` |
| `compare` | public | function | numpydoc | 0 | `(result, reference: 'dict', tol: 'float' = 0.01, rel: 'float' = 0.0001) -> 'Comparison'` |
| `expect` | public | function | numpydoc | 0 | `(result, expected: 'dict', tol: 'float' = 0.01, rel: 'float' = 0.0001) -> 'None'` |

## boki.export

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `to_beancount` | public | function | numpydoc | 0 | `(result: "'Result'", entity: "'Entity'", currency: 'str \| None' = None) -> 'str'` |

## boki.layouts

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `Layout` | public | class | numpydoc | 0 |  |
| `Kind` | public | class | numpydoc | 0 |  |
| `Stage` | public | class | numpydoc | 0 |  |
| `Standard` | public | class | numpydoc | 0 |  |
| `IFRS` | public | value | - | 0 |  |
| `USGAAP` | public | value | - | 0 |  |
| `JGAAP` | public | value | - | 0 |  |
| `bank` | public | value | - | 0 |  |

## Model

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', start: 'date \| str \| int \| None' = None, end: 'date \| str \| None' = None, periods: 'int \| None' = None, step: 'Unit \| Quantity' = <Unit month>, timeline: 'Timeline \| None' = None, *, actual_until: 'date \| str \| int \| None' = None)` |
| `check` | public | method | numpydoc | 7 | `(cond, message: 'str', level: 'str' = 'error') -> 'None'` |
| `entity` | public | method | numpydoc | 5 | `(name: 'str', standard=None, fiscal=None, layout=None, currency=None, tax_rate=None)` |
| `fx` | public | method | numpydoc | 0 | `(base: 'Unit', quote: 'Unit', *, closing, average, opening) -> 'FxPair'` |
| `group` | public | method | numpydoc | 0 | `(name: 'str', parent)` |
| `input` | public | method | numpydoc | 71 | `(name: 'str', default, scenarios: 'dict \| None' = None, choices=None, *, display=None, source: 'str \| None' = None, note: 'str \| None' = None) -> 'Input'` |
| `render` | public | method | numpydoc | 9 | `(scenario: 'str \| None' = None, inputs: 'dict \| None' = None, fix: 'dict \| None' = None, checks: 'str \| None' = None) -> "'Result'"` |
| `series` | public | method | numpydoc | 170 | `(name=None, expr=None, *, data: 'dict \| None' = None, unit=None, display=None)` |
| `solve` | public | method | numpydoc | 0 | `(unknowns, equations, *, integer: 'bool' = False, min: 'float \| None' = None, tol: 'float' = 1e-09, max_iter: 'int' = 500) -> 'None'` |
| `unknown` | public | method | numpydoc | 0 | `(name: 'str', init=0.0, per_period: 'bool \| None' = None, unit=None) -> 'Unknown'` |
| `actual_until` | readonly | attribute | - | 0 |  |
| `date` | readonly | attribute | - | 0 |  |
| `entities` | readonly | attribute | - | 0 |  |
| `groups` | readonly | attribute | - | 0 |  |
| `is_actual` | readonly | attribute | - | 0 |  |
| `is_forecast` | readonly | attribute | - | 33 |  |
| `n` | readonly | property | numpydoc | 1 |  |
| `name` | readonly | attribute | - | 7 |  |
| `period_end` | readonly | attribute | - | 0 |  |
| `period_length` | readonly | attribute | - | 2 |  |
| `t` | readonly | attribute | - | 17 |  |
| `timeline` | readonly | attribute | - | 1 |  |

## Result

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__getitem__` | public | method | numpydoc | 0 | `(key)` |
| `bs` | public | method | numpydoc | 81 | `(entity, by=None)` |
| `cf` | public | method | numpydoc | 24 | `(entity, by=None, method: 'str' = 'direct')` |
| `display_unit` | public | method | numpydoc | 0 | `(node: 'Series') -> 'Unit \| None'` |
| `pl` | public | method | numpydoc | 72 | `(entity, by=None, detail: 'bool' = True)` |
| `table` | public | method | numpydoc | 1 | `(nodes: 'Iterable[Series]', *, where=None, unit=None, title: 'str' = '', by=None, entity=None, stock: 'Iterable[Series]' = ())` |
| `to_excel` | public | method | numpydoc | 5 | `(path, style=None, sheets=None, *, scenarios=None, omit_unused_model: 'bool' = False, checks: 'bool \| None' = None, **overrides)` |
| `value` | public | method | numpydoc | 6 | `(node: 'Series', t=None)` |
| `checks` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(model: 'Model', render: 'Render')` |
| `model` | internal | attribute | - | 0 |  |

## Entity

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `journal` | public | method | numpydoc | 3 | `(name: 'str', amount, *, debit, credit, cf: 'str \| None' = None) -> 'Series'` |
| `label` | public | method | numpydoc | 0 | `(key: 'str') -> 'str'` |
| `load_actuals` | public | method | numpydoc | 2 | `(actuals: 'Mapping') -> 'None'` |
| `oci` | public | method | numpydoc | 0 | `(name: 'str', amount, *, against, recycle: 'bool' = True, tax: 'bool' = False) -> 'LineItem'` |
| `oci_release` | public | method | numpydoc | 0 | `(name: 'str', amount) -> 'Series'` |
| `vat_settlement` | public | method | numpydoc | 0 | `(settle: 'Kernel', name: 'str' = 'VAT settlement') -> 'Series'` |
| `adjusted_ebitda` | readonly | property | prose | 0 |  |
| `amortization` | readonly | property | numpydoc | 0 |  |
| `bs` | readonly | attribute | - | 81 |  |
| `cf` | readonly | attribute | - | 24 |  |
| `checks` | readonly | attribute | - | 0 |  |
| `comprehensive_income` | readonly | attribute | - | 0 |  |
| `currency` | readonly | property | numpydoc | 0 |  |
| `depreciation` | readonly | property | numpydoc | 1 |  |
| `ebit` | readonly | property | prose | 0 |  |
| `ebitda` | readonly | property | prose | 0 |  |
| `ebitdar` | readonly | property | prose | 0 |  |
| `fiscal` | readonly | attribute | - | 0 |  |
| `language` | readonly | property | numpydoc | 0 |  |
| `layout` | readonly | attribute | - | 0 |  |
| `model` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `net_income` | readonly | attribute | - | 0 |  |
| `noi` | readonly | property | prose | 0 |  |
| `operating_income` | readonly | property | numpydoc | 0 |  |
| `other_comprehensive_income` | readonly | attribute | - | 0 |  |
| `pl` | readonly | attribute | - | 72 |  |
| `standard` | readonly | attribute | - | 0 |  |
| `tax_rate` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(model: 'Model', name: 'str', standard: 'Standard', fiscal: 'Fiscal \| None' = None, layout: 'Layout \| None' = None, currency: 'Unit \| None' = None, tax_rate: 'float \| Series \| Quantity \| None' = None)` |
| `retained_earnings` | internal | attribute | - | 0 |  |

## EntityChecks

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `cash` | public | method | numpydoc | 0 | `(level: 'str' = 'error') -> 'None'` |
| `__init__` | internal | method | summary | 0 | `()` |
| `cash_level` | internal | attribute | - | 0 |  |

## PL

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `gross_profit` | readonly | attribute | - | 0 |  |
| `net_income` | readonly | attribute | - | 0 |  |
| `net_interest_income` | readonly | attribute | - | 0 |  |
| `operating_income` | readonly | attribute | - | 0 |  |
| `ordinary_income` | readonly | attribute | - | 0 |  |
| `pretax_income` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entity: 'Entity')` |

## BS

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `asset` | public | method | numpydoc | 0 | `(name: 'str', amount=None, at=None, *, target=None, opening=None, section: 'str' = 'current', cf: 'str \| None' = None, tags=(), kind: 'str' = 'asset', counterparty=None, actuals: 'dict \| None' = None) -> 'LineItem'` |
| `deferred_tax` | public | method | numpydoc | 0 | `(name: 'str', difference, rate=None, recognized=1.0) -> 'None'` |
| `liability` | public | method | numpydoc | 0 | `(name: 'str', amount=None, at=None, *, target=None, opening=None, cf: 'str \| None' = None, tags=(), kind: 'str' = 'liability', counterparty=None, actuals: 'dict \| None' = None) -> 'LineItem'` |
| `opening` | public | method | numpydoc | 15 | `(*, cash=None, retained_earnings=None) -> 'None'` |
| `sell` | public | method | numpydoc | 0 | `(asset_line: 'LineItem', price, *, at, counterparty, life) -> 'LineItem'` |
| `cash` | readonly | attribute | - | 0 |  |
| `equity` | readonly | attribute | - | 0 |  |
| `retained_earnings` | readonly | attribute | - | 0 |  |
| `total_assets` | readonly | attribute | - | 0 |  |
| `total_equity` | readonly | attribute | - | 0 |  |
| `total_liabilities` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entity: 'Entity')` |

## CF

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `financing` | public | attribute | - | 0 |  |
| `financing_excluding` | public | method | numpydoc | 0 | `(*items) -> 'Series'` |
| `fx` | public | attribute | - | 0 |  |
| `investing` | public | attribute | - | 0 |  |
| `operating` | public | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entity: 'Entity')` |

## LineMaker

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__call__` | public | method | numpydoc | 0 | `(*args: 'object', **kwargs: 'object') -> 'LineItem'` |
| `total_of` | public | method | numpydoc | 0 | `(**filters: 'object') -> 'Series'` |
| `entity` | readonly | attribute | - | 5 |  |
| `items` | readonly | property | numpydoc | 2 |  |
| `kind` | readonly | attribute | - | 0 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `total` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entity: 'Entity', kind: 'str', create: 'Callable[..., LineItem]')` |

## LineItem

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__abs__` | public | method | numpydoc | 0 | `()` |
| `__add__` | public | method | numpydoc | 0 | `(other)` |
| `__and__` | public | method | numpydoc | 0 | `(other)` |
| `__eq__` | public | method | numpydoc | 0 | `(other)` |
| `__floordiv__` | public | method | numpydoc | 0 | `(other)` |
| `__ge__` | public | method | numpydoc | 0 | `(other)` |
| `__getitem__` | public | method | numpydoc | 0 | `(t)` |
| `__gt__` | public | method | numpydoc | 0 | `(other)` |
| `__invert__` | public | method | numpydoc | 0 | `()` |
| `__le__` | public | method | numpydoc | 0 | `(other)` |
| `__lt__` | public | method | numpydoc | 0 | `(other)` |
| `__mod__` | public | method | numpydoc | 0 | `(other)` |
| `__mul__` | public | method | numpydoc | 0 | `(other)` |
| `__ne__` | public | method | numpydoc | 0 | `(other)` |
| `__neg__` | public | method | numpydoc | 0 | `()` |
| `__or__` | public | method | numpydoc | 0 | `(other)` |
| `__pow__` | public | method | numpydoc | 0 | `(other)` |
| `__radd__` | public | method | numpydoc | 0 | `(other)` |
| `__rand__` | public | method | numpydoc | 0 | `(other)` |
| `__rfloordiv__` | public | method | numpydoc | 0 | `(other)` |
| `__rmod__` | public | method | numpydoc | 0 | `(other)` |
| `__rmul__` | public | method | numpydoc | 0 | `(other)` |
| `__ror__` | public | method | numpydoc | 0 | `(other)` |
| `__rpow__` | public | method | numpydoc | 0 | `(other)` |
| `__rsub__` | public | method | numpydoc | 0 | `(other)` |
| `__rtruediv__` | public | method | numpydoc | 0 | `(other)` |
| `__sub__` | public | method | numpydoc | 0 | `(other)` |
| `__truediv__` | public | method | numpydoc | 0 | `(other)` |
| `balance` | public | attribute | - | 0 |  |
| `capitalized_interest` | public | attribute | - | 0 |  |
| `cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `define` | public | method | numpydoc | 8 | `(expr) -> "'Named'"` |
| `depreciation` | public | attribute | - | 1 |  |
| `draw` | public | attribute | - | 0 |  |
| `draw_or_repay` | public | method | numpydoc | 0 | `(amount) -> 'LineItem'` |
| `interest` | public | attribute | - | 10 |  |
| `interest_expense` | public | attribute | - | 0 |  |
| `lag` | public | method | numpydoc | 26 | `(k: "int \| 'Series'" = 1, fill: 'Any' = None) -> "'Series'"` |
| `last` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `max` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `mean` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `min` | public | method | numpydoc | 1 | `(year: 'int \| None' = None) -> "'Series'"` |
| `nol` | public | attribute | - | 0 |  |
| `reverse_cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `spread` | public | method | numpydoc | 0 | `(kernel) -> "'Series'"` |
| `sum` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `where` | public | method | numpydoc | 53 | `(cond: "'Series'", else_: 'Any' = None) -> "'Series'"` |
| `category` | readonly | attribute | - | 0 |  |
| `change` | readonly | property | numpydoc | 0 |  |
| `counterparty` | readonly | attribute | - | 0 |  |
| `entity` | readonly | attribute | - | 5 |  |
| `kind` | readonly | attribute | - | 0 |  |
| `layout` | readonly | attribute | - | 0 |  |
| `month` | readonly | property | numpydoc | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `principal` | readonly | attribute | - | 10 |  |
| `standard` | readonly | attribute | - | 0 |  |
| `unit` | readonly | attribute | - | 0 |  |
| `year` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str', expr: 'Series', entity: "'Entity'", kind: 'str', account: 'Account', category: 'str \| None' = None)` |
| `account` | internal | attribute | - | 0 |  |
| `book` | internal | attribute | - | 0 |  |
| `display` | internal | attribute | - | 0 |  |
| `expr` | internal | attribute | - | 0 |  |
| `net_investment` | internal | attribute | - | 0 |  |
| `scalar` | internal | attribute | - | 0 |  |

## Series

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__abs__` | public | method | numpydoc | 0 | `()` |
| `__add__` | public | method | numpydoc | 0 | `(other)` |
| `__and__` | public | method | numpydoc | 0 | `(other)` |
| `__eq__` | public | method | numpydoc | 0 | `(other)` |
| `__floordiv__` | public | method | numpydoc | 0 | `(other)` |
| `__ge__` | public | method | numpydoc | 0 | `(other)` |
| `__getitem__` | public | method | numpydoc | 0 | `(t)` |
| `__gt__` | public | method | numpydoc | 0 | `(other)` |
| `__invert__` | public | method | numpydoc | 0 | `()` |
| `__le__` | public | method | numpydoc | 0 | `(other)` |
| `__lt__` | public | method | numpydoc | 0 | `(other)` |
| `__mod__` | public | method | numpydoc | 0 | `(other)` |
| `__mul__` | public | method | numpydoc | 0 | `(other)` |
| `__ne__` | public | method | numpydoc | 0 | `(other)` |
| `__neg__` | public | method | numpydoc | 0 | `()` |
| `__or__` | public | method | numpydoc | 0 | `(other)` |
| `__pow__` | public | method | numpydoc | 0 | `(other)` |
| `__radd__` | public | method | numpydoc | 0 | `(other)` |
| `__rand__` | public | method | numpydoc | 0 | `(other)` |
| `__rfloordiv__` | public | method | numpydoc | 0 | `(other)` |
| `__rmod__` | public | method | numpydoc | 0 | `(other)` |
| `__rmul__` | public | method | numpydoc | 0 | `(other)` |
| `__ror__` | public | method | numpydoc | 0 | `(other)` |
| `__rpow__` | public | method | numpydoc | 0 | `(other)` |
| `__rsub__` | public | method | numpydoc | 0 | `(other)` |
| `__rtruediv__` | public | method | numpydoc | 0 | `(other)` |
| `__sub__` | public | method | numpydoc | 0 | `(other)` |
| `__truediv__` | public | method | numpydoc | 0 | `(other)` |
| `cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `define` | public | method | numpydoc | 8 | `(expr) -> "'Named'"` |
| `lag` | public | method | numpydoc | 26 | `(k: "int \| 'Series'" = 1, fill: 'Any' = None) -> "'Series'"` |
| `last` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `max` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `mean` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `min` | public | method | numpydoc | 1 | `(year: 'int \| None' = None) -> "'Series'"` |
| `reverse_cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `spread` | public | method | numpydoc | 0 | `(kernel) -> "'Series'"` |
| `sum` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `where` | public | method | numpydoc | 53 | `(cond: "'Series'", else_: 'Any' = None) -> "'Series'"` |
| `change` | readonly | property | numpydoc | 0 |  |
| `month` | readonly | property | numpydoc | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `unit` | readonly | attribute | - | 0 |  |
| `year` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str \| None', expr: 'Series \| None' = None, unit: 'Dims \| None' = None)` |
| `display` | internal | attribute | - | 0 |  |
| `expr` | internal | attribute | - | 0 |  |
| `scalar` | internal | attribute | - | 0 |  |

## Named

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__getitem__` | public | method | numpydoc | 0 | `(t)` |
| `cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `define` | public | method | numpydoc | 8 | `(expr) -> "'Named'"` |
| `lag` | public | method | numpydoc | 26 | `(k: "int \| 'Series'" = 1, fill: 'Any' = None) -> "'Series'"` |
| `last` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `max` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `mean` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `min` | public | method | numpydoc | 1 | `(year: 'int \| None' = None) -> "'Series'"` |
| `reverse_cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `spread` | public | method | numpydoc | 0 | `(kernel) -> "'Series'"` |
| `sum` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `where` | public | method | numpydoc | 53 | `(cond: "'Series'", else_: 'Any' = None) -> "'Series'"` |
| `change` | readonly | property | numpydoc | 0 |  |
| `month` | readonly | property | numpydoc | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `unit` | readonly | attribute | - | 0 |  |
| `year` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str \| None', expr: 'Series \| None' = None, unit: 'Dims \| None' = None)` |
| `display` | internal | attribute | - | 0 |  |
| `expr` | internal | attribute | - | 0 |  |
| `scalar` | internal | attribute | - | 0 |  |

## Group

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `own` | public | method | numpydoc | 0 | `(entity: 'Entity', share: 'float' = 1.0, *, since=0, method: 'str \| None' = None, consideration=None, proceeds=None, fair_value: 'Mapping \| None' = None, acquired: 'Mapping \| None' = None, tax_basis: 'str' = 'carryover', nci: 'str \| None' = None, nci_value=None, goodwill_life=None, private_company: 'bool' = False, impairment=None, loss_limit: 'bool' = True, previously_held_value=None, retained_value=None, opening: 'Mapping \| None' = None, investment=None) -> 'None'` |
| `adjusted_ebitda` | readonly | property | prose | 0 |  |
| `amortization` | readonly | property | numpydoc | 0 |  |
| `books` | readonly | property | numpydoc | 0 |  |
| `depreciation` | readonly | property | numpydoc | 1 |  |
| `ebit` | readonly | property | prose | 0 |  |
| `ebitda` | readonly | property | prose | 0 |  |
| `ebitdar` | readonly | property | prose | 0 |  |
| `model` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `noi` | readonly | property | prose | 0 |  |
| `operating_income` | readonly | property | numpydoc | 0 |  |
| `parent` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(model: 'Model', name: 'str', parent: 'Entity')` |

## Unit

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__mul__` | public | method | numpydoc | 0 | `(other)` |
| `__pow__` | public | method | numpydoc | 0 | `(k: 'int')` |
| `__rmul__` | public | method | numpydoc | 0 | `(other)` |
| `__rtruediv__` | public | method | numpydoc | 0 | `(other)` |
| `__truediv__` | public | method | numpydoc | 0 | `(other)` |
| `dims` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `scale` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str', dims: 'frozenset', scale: 'float' = 1.0)` |

## Quantity

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__abs__` | public | method | numpydoc | 0 | `()` |
| `__add__` | public | method | numpydoc | 0 | `(o)` |
| `__ge__` | public | method | numpydoc | 0 | `(o)` |
| `__gt__` | public | method | numpydoc | 0 | `(o)` |
| `__le__` | public | method | numpydoc | 0 | `(o)` |
| `__lt__` | public | method | numpydoc | 0 | `(o)` |
| `__mul__` | public | method | numpydoc | 0 | `(o)` |
| `__neg__` | public | method | numpydoc | 0 | `()` |
| `__pow__` | public | method | numpydoc | 0 | `(k)` |
| `__radd__` | public | method | numpydoc | 0 | `(o)` |
| `__rmul__` | public | method | numpydoc | 0 | `(o)` |
| `__rsub__` | public | method | numpydoc | 0 | `(o)` |
| `__rtruediv__` | public | method | numpydoc | 0 | `(o)` |
| `__sub__` | public | method | numpydoc | 0 | `(o)` |
| `__truediv__` | public | method | numpydoc | 0 | `(o)` |
| `dims` | readonly | attribute | - | 0 |  |
| `value` | readonly | attribute | - | 6 |  |
| `__float__` | internal | method | none | 0 | `()` |
| `__init__` | internal | method | summary | 0 | `(base_value: 'float', dims: 'frozenset')` |
| `of` | internal | method | none | 0 | `(x, unit: 'Unit')` |
| `shown` | internal | attribute | - | 0 |  |
| `where` | internal | method | summary | 53 | `(cond, else_=None)` |

## FxPair

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `average` | readonly | attribute | - | 0 |  |
| `base` | readonly | attribute | - | 0 |  |
| `closing` | readonly | attribute | - | 0 |  |
| `opening` | readonly | attribute | - | 15 |  |
| `quote` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(base: 'Unit', quote: 'Unit', closing: 'Series', average: 'Series', opening: 'Series') -> None` |

## Input

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `lag` | public | method | numpydoc | 26 | `(k: "int \| 'Series'" = 1, fill: 'Any' = None) -> "'Series'"` |
| `last` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `max` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `mean` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `min` | public | method | numpydoc | 1 | `(year: 'int \| None' = None) -> "'Series'"` |
| `reverse_cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `spread` | public | method | numpydoc | 0 | `(kernel) -> "'Series'"` |
| `sum` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `where` | public | method | numpydoc | 53 | `(cond: "'Series'", else_: 'Any' = None) -> "'Series'"` |
| `change` | readonly | property | numpydoc | 0 |  |
| `choices` | readonly | attribute | - | 0 |  |
| `default` | readonly | attribute | - | 0 |  |
| `month` | readonly | property | numpydoc | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `note` | readonly | attribute | - | 0 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `scenarios` | readonly | attribute | - | 0 |  |
| `source` | readonly | attribute | - | 0 |  |
| `unit` | readonly | attribute | - | 0 |  |
| `year` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str', default: 'Series \| Quantity \| float \| str', scenarios: 'dict \| None', choices: 'list \| tuple \| dict \| None', display: 'Unit \| None' = None, source: 'str \| None' = None, note: 'str \| None' = None)` |
| `display` | internal | attribute | - | 0 |  |
| `resolve` | internal | method | none | 0 | `(r: 'Render')` |
| `scalar` | internal | attribute | - | 0 |  |
| `shown` | internal | attribute | - | 0 |  |

## Unknown

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `lag` | public | method | numpydoc | 26 | `(k: "int \| 'Series'" = 1, fill: 'Any' = None) -> "'Series'"` |
| `last` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `max` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `mean` | public | method | numpydoc | 0 | `(year: 'int \| None' = None) -> "'Series'"` |
| `min` | public | method | numpydoc | 1 | `(year: 'int \| None' = None) -> "'Series'"` |
| `reverse_cumsum` | public | method | numpydoc | 0 | `() -> "'Series'"` |
| `spread` | public | method | numpydoc | 0 | `(kernel) -> "'Series'"` |
| `sum` | public | method | numpydoc | 6 | `(year: 'int \| None' = None) -> "'Series'"` |
| `where` | public | method | numpydoc | 53 | `(cond: "'Series'", else_: 'Any' = None) -> "'Series'"` |
| `change` | readonly | property | numpydoc | 0 |  |
| `init` | readonly | attribute | - | 0 |  |
| `month` | readonly | property | numpydoc | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `opening` | readonly | property | numpydoc | 15 |  |
| `unit` | readonly | attribute | - | 0 |  |
| `year` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str', init: 'Series \| Quantity \| float', per_period: 'bool', unit: 'Unit \| Dims \| None')` |
| `display` | internal | attribute | - | 0 |  |
| `scalar` | internal | attribute | - | 0 |  |

## Timeline

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `n` | readonly | attribute | - | 1 |  |
| `periods` | readonly | attribute | - | 0 |  |
| `regular` | readonly | method | numpydoc | 0 | `(start, step, n: 'int \| None' = None, end=None) -> "'Timeline'"` |
| `__init__` | internal | method | summary | 0 | `(periods: 'list[Period]')` |
| `index` | internal | method | none | 1 | `(key) -> 'int'` |

## Period

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `end` | readonly | property | numpydoc | 0 |  |
| `end_date` | readonly | attribute | - | 0 |  |
| `label` | readonly | attribute | - | 0 |  |
| `months` | readonly | attribute | - | 0 |  |
| `start` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(start: 'date \| None', months: 'int', label: 'str', end_date: 'date \| None' = None) -> None` |

## Fiscal

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `change` | readonly | attribute | - | 0 |  |
| `label` | readonly | method | numpydoc | 0 | `(period_start: 'date') -> 'str'` |
| `year_end` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(year_end: 'str', change: 'dict \| None' = None)` |

## Calendar

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `days` | public | method | numpydoc | 0 | `(spec: 'str') -> 'Series'` |
| `closed` | readonly | attribute | - | 0 |  |
| `holidays` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(model: 'Model', holidays: 'Iterable[date \| str] \| None' = None, closed: 'Iterable[str]' = ())` |
| `model` | internal | attribute | - | 0 |  |

## Kernel

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `name` | readonly | attribute | - | 7 |  |
| `weights` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(weights: 'Iterable[float]', name: 'str')` |

## Style

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__call__` | public | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', money: 'str \| float \| None' = None, units: 'dict' = <factory>, hide: 'tuple' = (), helpers: 'str' = 'group', language: 'str' = 'en', negatives: 'str' = 'parens', zero: 'str' = '–', expenses: 'str' = 'negative', colors: 'bool' = True, ratios: 'bool' = True, gridlines: 'bool' = False, periods: 'str' = 'fy', statements: 'bool' = True, columns: 'str' = 'fiscal', font: 'str \| None' = None, decimals: 'int \| None' = None, band: 'str \| None' = None, shade: 'str \| None' = None, dollars: 'bool' = False, titles: 'dict' = <factory>, header: 'str \| None' = None) -> None` |
| `replace` | public | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `band` | readonly | attribute | - | 0 |  |
| `colors` | readonly | attribute | - | 0 |  |
| `columns` | readonly | attribute | - | 0 |  |
| `decimals` | readonly | attribute | - | 0 |  |
| `dollars` | readonly | attribute | - | 0 |  |
| `expenses` | readonly | attribute | - | 0 |  |
| `font` | readonly | attribute | - | 0 |  |
| `gridlines` | readonly | attribute | - | 0 |  |
| `header` | readonly | attribute | - | 0 |  |
| `helpers` | readonly | attribute | - | 0 |  |
| `hide` | readonly | attribute | - | 0 |  |
| `language` | readonly | attribute | - | 0 |  |
| `money` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `negatives` | readonly | attribute | - | 0 |  |
| `periods` | readonly | attribute | - | 0 |  |
| `ratios` | readonly | attribute | - | 0 |  |
| `shade` | readonly | attribute | - | 0 |  |
| `statements` | readonly | attribute | - | 0 |  |
| `titles` | readonly | attribute | - | 0 |  |
| `units` | readonly | attribute | - | 0 |  |
| `zero` | readonly | attribute | - | 0 |  |
| `caption` | internal | method | none | 0 | `(currency: 'str \| None') -> 'str'` |
| `dollar_format` | internal | method | none | 0 | `() -> 'str'` |
| `heading_format` | internal | method | prose | 0 | `(actual: 'bool' = False, has_actuals: 'bool' = False) -> 'str'` |
| `label` | internal | method | prose | 0 | `(key: 'str', standard=None) -> 'str'` |
| `number_format` | internal | method | summary | 0 | `(scale_by_format: 'float' = 1) -> 'str'` |
| `percent_format` | internal | method | none | 0 | `() -> 'str'` |
| `period_label` | internal | method | summary | 0 | `(period, fiscal=None) -> 'str \| int'` |
| `scale` | internal | property | none | 0 |  |

## StylePresets

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `banker` | readonly | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `japanese` | readonly | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `plain` | readonly | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `sec` | readonly | method | numpydoc | 0 | `(**kw: 'object') -> "'Style'"` |
| `__init__` | internal | method | summary | 0 | `(self, /, *args, **kwargs)` |

## Bound

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | internal | method | summary | 0 | `(text: 'str', lo: 'float \| Quantity \| None' = None, hi: 'float \| Quantity \| None' = None, strict: 'bool' = False)` |
| `base` | internal | method | none | 0 | `(node: 'Series') -> 'Bound'` |
| `hi` | internal | attribute | - | 0 |  |
| `holds` | internal | method | none | 0 | `(got) -> 'bool'` |
| `lo` | internal | attribute | - | 0 |  |
| `strict` | internal | attribute | - | 0 |  |
| `text` | internal | attribute | - | 0 |  |

## Comparison

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `entries` | readonly | attribute | - | 0 |  |
| `mismatches` | readonly | property | numpydoc | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entries: 'list[Entry]')` |

## Entry

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `diff` | readonly | property | numpydoc | 0 |  |
| `got` | readonly | attribute | - | 0 |  |
| `label` | readonly | attribute | - | 0 |  |
| `ok` | readonly | attribute | - | 0 |  |
| `period` | readonly | attribute | - | 0 |  |
| `want` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(label: 'str', period: 'str', got: 'float \| date \| None', want: 'float \| date \| Bound', ok: 'bool') -> None` |

## CheckResult

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `detail` | readonly | attribute | - | 0 |  |
| `level` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `passed` | readonly | attribute | - | 0 |  |
| `periods` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(name: 'str', level: 'str', passed: 'bool', periods: 'list[str]', detail: 'str') -> None` |

## PlacementLine

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `fmt` | readonly | attribute | - | 0 |  |
| `formula` | readonly | attribute | - | 0 |  |
| `label` | readonly | attribute | - | 0 |  |
| `scale` | readonly | attribute | - | 0 |  |
| `series` | readonly | attribute | - | 170 |  |
| `sign` | readonly | attribute | - | 0 |  |
| `total` | readonly | attribute | - | 0 |  |
| `verify` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(series: 'object', label: 'str \| None' = None, sign: 'int' = 1, scale: 'float' = 1, total: 'bool \| str' = False, formula: 'object' = None, verify: 'str' = 'perturb', fmt: 'str \| None' = None) -> None` |

## Section

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `entries` | readonly | attribute | - | 0 |  |
| `title` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(title: 'str', entries: 'tuple') -> None` |

## Sheet

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `entries` | readonly | attribute | - | 0 |  |
| `money` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `__init__` | internal | method | numpydoc | 0 | `(name: 'str', entries: 'tuple', money: 'str \| float \| int \| None' = None) -> None` |

## Link

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `fmt` | readonly | attribute | - | 0 |  |
| `label` | readonly | attribute | - | 0 |  |
| `sign` | readonly | attribute | - | 0 |  |
| `target` | readonly | attribute | - | 0 |  |
| `total` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(target: 'object', label: 'str \| None' = None, sign: 'int' = 1, total: 'bool \| str' = False, fmt: 'str \| None' = None) -> None` |

## Block

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `fmt` | readonly | attribute | - | 0 |  |
| `label` | readonly | attribute | - | 0 |  |
| `rows` | readonly | attribute | - | 0 |  |
| `sign` | readonly | attribute | - | 0 |  |
| `target` | readonly | attribute | - | 0 |  |
| `total` | readonly | attribute | - | 0 |  |
| `verify` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(target: 'object', rows: 'tuple', label: 'str \| None' = None, sign: 'int' = 1, total: 'bool \| str' = True, verify: 'str' = 'perturb', fmt: 'str \| None' = None) -> None` |

## Panel

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `columns` | readonly | attribute | - | 0 |  |
| `rows` | readonly | attribute | - | 0 |  |
| `title` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(title: 'str', columns: 'tuple', rows: 'tuple') -> None` |

## Sensitivity

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `col_fmt` | readonly | attribute | - | 0 |  |
| `col_values` | readonly | attribute | - | 0 |  |
| `corner` | readonly | attribute | - | 0 |  |
| `fmt` | readonly | attribute | - | 0 |  |
| `formula` | readonly | method | numpydoc | 0 | `(row_var, col_var)` |
| `highlight` | readonly | attribute | - | 0 |  |
| `row_fmt` | readonly | attribute | - | 0 |  |
| `row_values` | readonly | attribute | - | 0 |  |
| `title` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | numpydoc | 0 | `(title: 'str', row_values: 'tuple', col_values: 'tuple', formula: 'object', fmt: 'str \| None' = None, row_fmt: 'str \| None' = None, col_fmt: 'str \| None' = None, highlight: 'tuple \| None' = None, corner: 'str' = '') -> None` |

## Table

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `columns` | readonly | attribute | - | 0 |  |
| `rows` | readonly | attribute | - | 0 |  |
| `title` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(title: 'str', columns: 'list[str]', rows: 'list[Row]')` |
| `row` | internal | method | none | 0 | `(label: 'str') -> 'list[Any]'` |

## Report

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `data` | readonly | attribute | - | 0 |  |
| `formulas` | readonly | attribute | - | 0 |  |
| `guarded` | readonly | attribute | - | 0 |  |
| `reasons` | readonly | attribute | - | 0 |  |
| `unnamed` | readonly | attribute | - | 0 |  |
| `unplaced` | readonly | attribute | - | 3 |  |
| `values` | readonly | attribute | - | 1 |  |
| `__init__` | internal | method | numpydoc | 0 | `(formulas: 'int' = 0, values: 'int' = 0, data: 'int' = 0, guarded: 'int' = 0, reasons: 'dict[str, int]' = <factory>, unnamed: 'list[str]' = <factory>, unplaced: 'list[str]' = <factory>) -> None` |

## CheckFailed

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `failures` | readonly | attribute | - | 0 |  |
| `result` | readonly | attribute | - | 0 |  |

## CycleError

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `chain` | readonly | attribute | - | 0 |  |

## NOL

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `balance` | readonly | attribute | - | 0 |  |
| `taxable` | readonly | attribute | - | 0 |  |
| `used` | readonly | attribute | - | 0 |  |
| `count` | internal | method | summary | 0 | `(value, /)` |
| `index` | internal | method | prose | 1 | `(value, start=0, stop=9223372036854775807, /)` |

## Equity

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `total` | readonly | attribute | - | 0 |  |
| `__init__` | internal | method | summary | 0 | `(entity: 'Entity')` |

## Layout

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', pl: 'tuple', bs: 'tuple[Kind, ...]', interest_kind: 'str', depreciation_kind: 'str') -> None` |
| `bs_kind` | public | method | numpydoc | 0 | `(name: 'str') -> 'Kind \| None'` |
| `bs` | readonly | attribute | - | 81 |  |
| `depreciation_kind` | readonly | attribute | - | 0 |  |
| `income_kinds` | readonly | property | numpydoc | 0 |  |
| `interest_kind` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `pl` | readonly | attribute | - | 72 |  |
| `pl_kinds` | readonly | property | numpydoc | 0 |  |
| `stages` | readonly | property | numpydoc | 0 |  |

## Kind

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', side: 'str', section: 'str \| None' = None, cf: 'str' = 'operating', tags: 'frozenset' = frozenset(), contra: 'bool' = False, mechanism: 'str' = 'line') -> None` |
| `cf` | readonly | attribute | - | 24 |  |
| `contra` | readonly | attribute | - | 0 |  |
| `mechanism` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |
| `section` | readonly | attribute | - | 0 |  |
| `side` | readonly | attribute | - | 0 |  |
| `tags` | readonly | attribute | - | 0 |  |

## Stage

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', formula: "Callable[['PL'], 'Series']") -> None` |
| `formula` | readonly | method | numpydoc | 0 | `(pl)` |
| `name` | readonly | attribute | - | 7 |  |

## Standard

| name | classification | kind | doc | uses | signature |
|---|---|---|---|---:|---|
| `__init__` | public | method | numpydoc | 0 | `(name: 'str', general: 'Layout', labels: 'dict' = <factory>, display: 'dict' = <factory>, bs_order: 'str' = 'current_first') -> None` |
| `bs_order` | readonly | attribute | - | 0 |  |
| `display` | readonly | attribute | - | 0 |  |
| `general` | readonly | attribute | - | 0 |  |
| `labels` | readonly | attribute | - | 0 |  |
| `name` | readonly | attribute | - | 7 |  |

## Line makers by layout (pl.<kind> / bs.<kind>)

| classification | standard | layout | ns | mechanism | kinds | signature |
|---|---|---|---|---|---|---|
| public | IFRS | IFRS general | bs | capital | capital, nci, oci | `(name: 'str', amount=None, at=None, *, opening=None, cf: 'str | None' = None, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | bs | construction | construction | `(name: 'str', spend, complete_at=None, life=None, *, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | bs | dividend | dividend | `(name: 'str', amount, *, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | bs | fixed_asset | fixed_asset, intangible | `(name: 'str', cost=None, at=None, *, life=None, method='straight', salvage: 'Series | Quantity | float' = 0, sell_at=None, depreciation=None, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | bs | line | accrued, deferred_revenue, deferred_tax_asset, deferred_tax_liability, deposit, inventory, lease_liability, other_asset, other_current_asset, other_current_liability, other_liability, payable, prepaid, receivable, working_capital | `(name: 'str', amount=None, at=None, *, data: 'dict | None' = None, target=None, opening=None, cf: 'str | None' = None, tags: 'Iterable[str]' = (), counterparty=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | bs | loan | loan | `(name: 'str', draw=None, rate: 'Series | Quantity | float | None' = 0, repay=None, *, opening=None, target=None, capitalize_during=None, capitalize_into=None, counterparty=None, net_investment: 'bool' = False, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | pl | pl | cogs, finance_cost, finance_income, other_expense, other_income, revenue, sga | `(name: 'str', amount=None, *, data: 'dict | None' = None, settle: 'Kernel | None' = None, recognize: 'Kernel | None' = None, cash=None, category: 'str | None' = None, against=None, vat=None, counterparty=None, margin=None, used: 'Kernel | None' = None, life=None, opening=None, opening_collect: 'dict | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | IFRS general | pl | pl | income_tax | `(name: 'str', amount=None, *, rate=None, base=None, nol: 'Series | Quantity | float | bool' = True, data: 'dict | None' = None, settle: 'Kernel | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | bs | capital | capital, nci, oci | `(name: 'str', amount=None, at=None, *, opening=None, cf: 'str | None' = None, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | bs | dividend | dividend | `(name: 'str', amount, *, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | bs | fixed_asset | fixed_asset, intangible | `(name: 'str', cost=None, at=None, *, life=None, method='straight', salvage: 'Series | Quantity | float' = 0, sell_at=None, depreciation=None, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | bs | line | allowance, deferred_tax_asset, deferred_tax_liability, deposits, earning_asset, other_asset, other_liability | `(name: 'str', amount=None, at=None, *, data: 'dict | None' = None, target=None, opening=None, cf: 'str | None' = None, tags: 'Iterable[str]' = (), counterparty=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | bs | loan | loan | `(name: 'str', draw=None, rate: 'Series | Quantity | float | None' = 0, repay=None, *, opening=None, target=None, capitalize_during=None, capitalize_into=None, counterparty=None, net_investment: 'bool' = False, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | pl | pl | interest_expense, interest_income, non_interest_expense, non_interest_income, provision | `(name: 'str', amount=None, *, data: 'dict | None' = None, settle: 'Kernel | None' = None, recognize: 'Kernel | None' = None, cash=None, category: 'str | None' = None, against=None, vat=None, counterparty=None, margin=None, used: 'Kernel | None' = None, life=None, opening=None, opening_collect: 'dict | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | IFRS | bank | pl | pl | income_tax | `(name: 'str', amount=None, *, rate=None, base=None, nol: 'Series | Quantity | float | bool' = True, data: 'dict | None' = None, settle: 'Kernel | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | capital | capital, nci, oci | `(name: 'str', amount=None, at=None, *, opening=None, cf: 'str | None' = None, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | construction | construction | `(name: 'str', spend, complete_at=None, life=None, *, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | dividend | dividend | `(name: 'str', amount, *, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | fixed_asset | fixed_asset, intangible | `(name: 'str', cost=None, at=None, *, life=None, method='straight', salvage: 'Series | Quantity | float' = 0, sell_at=None, depreciation=None, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | line | accrued, deferred_revenue, deferred_tax_asset, deferred_tax_liability, deposit, inventory, lease_liability, other_asset, other_current_asset, other_current_liability, other_liability, payable, prepaid, receivable, working_capital | `(name: 'str', amount=None, at=None, *, data: 'dict | None' = None, target=None, opening=None, cf: 'str | None' = None, tags: 'Iterable[str]' = (), counterparty=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | bs | loan | loan | `(name: 'str', draw=None, rate: 'Series | Quantity | float | None' = 0, repay=None, *, opening=None, target=None, capitalize_during=None, capitalize_into=None, counterparty=None, net_investment: 'bool' = False, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | pl | pl | cogs, non_operating_expense, non_operating_income, revenue, sga, special_gain, special_loss | `(name: 'str', amount=None, *, data: 'dict | None' = None, settle: 'Kernel | None' = None, recognize: 'Kernel | None' = None, cash=None, category: 'str | None' = None, against=None, vat=None, counterparty=None, margin=None, used: 'Kernel | None' = None, life=None, opening=None, opening_collect: 'dict | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | J-GAAP | J-GAAP general | pl | pl | income_tax | `(name: 'str', amount=None, *, rate=None, base=None, nol: 'Series | Quantity | float | bool' = True, data: 'dict | None' = None, settle: 'Kernel | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | capital | capital, nci, oci | `(name: 'str', amount=None, at=None, *, opening=None, cf: 'str | None' = None, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | construction | construction | `(name: 'str', spend, complete_at=None, life=None, *, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | dividend | dividend | `(name: 'str', amount, *, counterparty=None, fx_rate=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | fixed_asset | fixed_asset, intangible | `(name: 'str', cost=None, at=None, *, life=None, method='straight', salvage: 'Series | Quantity | float' = 0, sell_at=None, depreciation=None, opening=None, category: 'str' = 'Depreciation expense', actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | line | accrued, deferred_revenue, deferred_tax_asset, deferred_tax_liability, deposit, inventory, lease_liability, other_asset, other_current_asset, other_current_liability, other_liability, payable, prepaid, receivable, working_capital | `(name: 'str', amount=None, at=None, *, data: 'dict | None' = None, target=None, opening=None, cf: 'str | None' = None, tags: 'Iterable[str]' = (), counterparty=None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | bs | loan | loan | `(name: 'str', draw=None, rate: 'Series | Quantity | float | None' = 0, repay=None, *, opening=None, target=None, capitalize_during=None, capitalize_into=None, counterparty=None, net_investment: 'bool' = False, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | pl | pl | cogs, interest_expense, other_expense, other_income, revenue, sga | `(name: 'str', amount=None, *, data: 'dict | None' = None, settle: 'Kernel | None' = None, recognize: 'Kernel | None' = None, cash=None, category: 'str | None' = None, against=None, vat=None, counterparty=None, margin=None, used: 'Kernel | None' = None, life=None, opening=None, opening_collect: 'dict | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |
| public | US GAAP | US GAAP general | pl | pl | income_tax | `(name: 'str', amount=None, *, rate=None, base=None, nol: 'Series | Quantity | float | bool' = True, data: 'dict | None' = None, settle: 'Kernel | None' = None, actuals: 'dict | None' = None) -> 'LineItem'` |

## Usage by `pl.` / `bs.` / `cf.` / `b.`

| call | uses |
|---|---:|
| `b.row` | 157 |
| `b.link` | 38 |
| `b.section` | 34 |
| `bs.cash` | 26 |
| `b.sheet` | 15 |
| `pl.net_income` | 13 |
| `pl.operating_income` | 12 |
| `pl.sga` | 10 |
| `cf.operating` | 10 |
| `pl.pretax_income` | 9 |
| `bs.other_asset` | 9 |
| `b.block` | 9 |
| `b.max` | 8 |
| `bs.retained_earnings` | 8 |
| `pl.cogs` | 7 |
| `cf.investing` | 7 |
| `pl.gross_profit` | 7 |
| `b.panel` | 7 |
| `pl.revenue` | 6 |
| `bs.loan` | 6 |
| `cf.financing` | 6 |
| `bs.total_liabilities` | 6 |
| `bs.total_equity` | 6 |
| `bs.total_assets` | 6 |
| `b.Model` | 5 |
| `pl.income_tax` | 5 |
| `b.USGAAP` | 5 |
| `b.min` | 5 |
| `bs.capital` | 4 |
| `b.sensitivity` | 4 |
| `pl.interest_expense` | 3 |
| `bs.dividend` | 2 |
| `bs.opening` | 2 |
| `bs.other_liability` | 2 |
| `b.unit` | 1 |
| `bs.asset` | 1 |
| `cf.financing_excluding` | 1 |
| `b.fiscal` | 1 |
| `b.step` | 1 |
| `bs.construction` | 1 |
| `bs.receivable` | 1 |
| `bs.fixed_asset` | 1 |
| `b.Series` | 1 |
| `b.series` | 1 |
