# Public API inventory and documentation plan

Status: proposal (2026-11-01), revised after a counterpart review (Codex `gpt-6-astra`, 2026-11-01). The user approved the §6 proposals on 2026-11-01. Step 1 (§5.1) is implemented: `docs/reference/public-api.toml` is the registry, `tests/test_public_api.py` checks it against the code, and `tests/test_docstrings.py` enforces docstrings against the shrink-only exceptions in `docs/reference/doc-exceptions.toml`. Step 3 (§5.3) is implemented: `LineMaker`, the per-template docstrings in `src/boki/_maker_docs.py`, the generated types in `src/boki/_makers.py`, and the generated per-layout reference pages. Step 4 (§5.4) is implemented: every public object has a docstring to §4 with examples, the exception list is empty, and an Examples section is required.

The review's blocking points changed the plan in two ways. First, the boundary is now defined by intent: a hand-written list of supported members, which the script checks. A snapshot of what introspection happens to find no longer defines it. Second, the `boki.layouts` name collision is resolved before anything is made public. §7 lists every review item and where this plan addresses it.

The full generated table is [api-surface.md](api-surface.md) (`uv run python tools/api_inventory.py > docs/api-surface.md`). This note summarizes it and proposes how to define the public API and document it in numpydoc style, the way numpy, pandas, and scipy do. Layers and naming principles already decided are in [api-principles.md](api-principles.md). This plan builds on them and does not reopen them.

## 1. What a user can reach today

"Documentable" means a function, class, method, or property. Plain attributes and constants cannot carry a docstring.

| Surface | Names | Documentable | No docstring | One line | Multi-line prose | numpydoc |
|---|---:|---:|---:|---:|---:|---:|
| `boki` (`__all__`) | 57 | 49 | 11 | 28 | 10 | 0 |
| `units`, `lib`, `shapes`, `testing`, `export`, `styles`, `layouts` | 98 | 60 | 3 | 39 | 18 | 0 |
| `Model` | 18 | 10 | 3 | 1 | 6 | 0 |
| `Entity` | 35 | 16 | 6 | 7 | 3 | 0 |
| `PL` / `BS` / `CF` | 12 / 33 / 5 | 8 / 28 / 1 | 0 / 1 / 0 | 8 / 27 / 1 | 0 | 0 |
| `Series` / `LineItem` | 19 / 27 | 15 / 15 | 6 / 7 | 9 / 8 | 0 | 0 |
| `Result` / `Group` | 9 / 15 | 7 / 10 | 4 / 5 | 0 / 2 | 3 / 3 | 0 |

The PL/BS "one line" count is misleading. Each of those makers shows the same generic `_Kind` class docstring, so in practice they have no documentation.

The `pl.<kind>` / `bs.<kind>` makers have 43 distinct kind names across the general layouts and the bank layout. They are built from 8 create signatures and 7 `mechanism` values. `income_tax` has mechanism `"pl"` but is selected by name and has its own signature.

The `boki` row counts the modules `units` and `export` as documentable, although §3.1 treats modules separately.

The inventory script only covers objects it samples (`Model`, one IFRS `Entity`, its `PL`/`BS`/`CF`, a revenue maker and its `LineItem`, `m.t`, `Result`, `Group`). It also skips re-exported names, constructors, and dunders. §3.1 fixes this, so the counts above are a lower bound.

The most-used calls in the 221 research corpus plans (kept outside this repository) and `examples/`: `m.series` (2868), `m.input` (771), `.where` (373), `.lag` (372), `b.expect` (253), `.sum` (250), `.define` (243), `b.unit` (239), `m.render` (234), `b.Model` (220), `b.year` (197), `b.max` (184), `.cumsum` (138), `b.by_year` (128), `pl.revenue` (103), `pl.sga` (102). Several of these have no docstring at all: `Model`, `.sum`, `.define`, `.cumsum`, `b.max`, `b.min`, and `r.pl/bs/cf/value`.

## 2. Problems the inventory shows

1. **The line makers hide their signatures.** Every `pl.<kind>` / `bs.<kind>` reports `(*args, **kwargs) -> LineItem` and the one-line `_Kind` docstring. These are the main way to build a model, yet `help(co.bs.loan)` and IDE completion show nothing about `draw=`, `rate=`, `repay=`. The real signature exists on the mechanism's `create` closure (`loan`, `fixed_asset`, `construction`, `capital`, `dividend`, `line`, `pl`, `income_tax`).
2. **There is no boundary between public and internal.** None of the user-facing modules defines `__all__`, so their internals show up as public:
   - `boki.units`: `describe`, `display_unit_of`, `labeled`, `prefixed`, `show`, `takes_prefix`, `DIMENSIONLESS`
   - `boki.shapes`: `check_kernel_distribution`
   - `boki.styles`: `AUTOMATIC`, `LABELS`, `SCALES`, `money_scale`
   - `boki.layouts`: `GENERAL_BS`, `IFRS_GENERAL`, …
   - `boki.export`: `account_names`
   - Several modules: `annotations`, `TYPE_CHECKING`

   Objects leak engine internals the same way:
   - `m.t.fn(p, t)` (from the `_Time` subclass, not the `Series` base)
   - `LineItem.account`, `.expr`
   - `Entity.accounts`, `.postings`, `.cash_account`, `.account_name`, `.equity_total`, `.cum_profit`
   - `Group.members`, `.ownership`
3. **Names disagree across objects.**
   - `LineItem.company` vs `Kind.entity` / `Group.parent` (the same thing).
   - `Entity.oci(...)` (book an OCI item), `bs.oci(...)` (an equity line maker), `Entity.other_comprehensive_income`, and `Entity.oci_release` overlap.
   - `bs.working_capital` is a line maker, although the name reads like a total.
4. **One PL signature has 15 parameters, 13 of them keyword-only.** It covers four different cases in one maker: plain items, settled trades, intercompany asset trades (`margin=`, `used=`, `life=`), and openings (`opening=`, `opening_collect=`). Each keyword only applies in some of those cases. A docstring can explain the combinations, but the size of the signature is a design smell to keep in mind.
5. **Attributes have no documentation path.** These are plain attributes, not properties, so they cannot carry docstrings:
   - `m.t`, `m.date`, `m.period_end`, `m.period_length` (heavily used)
   - `co.pl`, `co.bs`, `co.cf`
   - `item.kind`, `item.unit`

   numpydoc documents them in the class's `Attributes` section, so those classes need class docstrings.
6. **The default measures are refused on purpose.** `Entity` and `Group` expose `ebit`, `ebitda`, `ebitdar`, `adjusted_ebitda`, and `noi` as properties that raise. Their docs must say that, and point to the parts instead.
7. **The lib return types are inconsistent.**
   - `black_scholes`, `capm`, `hamada`, `pmt`, `wacc`: annotated `Any`
   - `ssfa`: `float`
   - `macrs`, `straight_line`: `Kernel`
   - `nol`: `NOL`
   - The rest: `Series`
8. **`boki.layouts` names two different things.** `boki/__init__.py` imports the preset namespace class `layouts` from the module `boki.layouts`. That class shadows the submodule, so `import boki.layouts as L` binds the class, which has no `Kind`. Only `sys.modules["boki.layouts"]` is the module.
9. **`b.lib` works but is not exported.** It is reachable as `b.lib`, which api-principles §1 endorses, but `__all__` omits it.

## 3. Proposed definition of the public API

1. **Define the supported surface by intent, then check it.**
   - **Registry.** Add `docs/reference/public-api.toml`, a hand-written registry. Each entry has a canonical import path or receiver path, and a classification: *public*, *public read-only*, or *internal (reachable)*.
   - **What it must cover.** It includes the objects that public calls return:
     - `FxPair` (from `m.fx`)
     - `Input` / `Unknown`, and named series that can be defined later (`.define`)
     - `Timeline` / `Period`, and `Fiscal` / `Calendar`
     - `Kernel`, and `Quantity` with its operators
     - The `testing` result types, `Result.table` output, checks, and `CheckFailed`
     - Placement records (`row` / `section` / `sheet` / `link`)
     - The Excel `Report` and `Untranslatable` / `UnnamedAssumption`
   - **Mechanism-specific attributes.** It also covers attributes that only some line items have:
     - `loan.draw_or_repay`, `.interest`, `.principal`
     - The attributes of assets and income tax
     - `bs.equity.total`
   - **Exposed engine objects.** These are classified explicitly instead of inferred: `LineItem.account` / `.expr`, `Entity.retained_earnings`, `Entity.accounts` / `.postings`.
   - **The script checks the registry.** It walks every public module's `__all__` and the members of every registered type, including constructors and documented dunders such as arithmetic on `Series` and `Quantity`. It fails on anything public that is not registered, and on anything registered that does not exist.
2. **Public modules.**
   - **Public:** `boki`, `boki.units`, `boki.lib`, `boki.shapes`, `boki.testing`, `boki.export`, and the custom-layout API. Each defines `__all__`, and `b.lib` joins top-level `__all__`.
   - **Internal:** `ledger`, `group`, `excel`, `series`, `model`, `statements`, `placement`, `evaluator`, and `styles` apart from `Style` and `styles`.
   - **Returned types.** A public function can return an object whose class is defined in an internal module. That class is still documented and listed in the registry under its canonical import path (pandas does the same for `DataFrameGroupBy`).
3. **Resolve the `layouts` collision first.** Proposal:
   - Keep the module `boki.layouts` as the custom-layout API: `Layout`, `Kind`, `Stage`, `Standard`, and the presets as module-level constants.
   - Delete the namespace class `layouts`, so `b.layouts` is the module.
   - The docs for custom layouts list the valid mechanisms, the required kinds, stage dependencies, and the name-collision rules.
4. **Engine names become private.** Every name classified as internal gets an underscore, or moves under the object that owns it. Callers are migrated in the same PR, and there are no compatibility aliases (backward compatibility is not required).
5. **Line makers are solved separately at runtime, for static analysis, and in the reference.**
   - **Runtime.** Make the maker the public type `LineMaker` (formerly `ledger._Kind`). Plain methods would lose `.total`, `.items`, and `.total_of`. When `PL` or `BS` builds a maker, it sets `__signature__` and `__doc__` from a template for the maker's create function, plus Kind metadata. There is one template per create signature (8), not per mechanism (7), and `income_tax` is handled explicitly. `help(co.bs.loan)` then shows the loan parameters.
   - **Static analysis.** Makers exist only on instances, so class-level autodoc, IDEs, and type checkers cannot see them. Generate `.pyi` stubs: one PL/BS class per layout, each maker attribute typed as a callable `Protocol` with the real signature, and `m.entity(..., layout=...)` overloads returning the matching entity type. A test fails when the stubs and runtime disagree.
   - **Reference.** Generate the maker pages from Kind data, with one table per layout listing kind → create signature → docstring. Autodoc does not need to discover the makers.
   - **Amendment (step 3).** The static types are a generated, checked-in `src/boki/_makers.py` (`tools/generate_makers.py`) instead of `.pyi` stubs, and the `m.entity(..., layout=...)` overloads are out of scope, because layouts are instances, not types: `Entity.pl` and `Entity.bs` are typed for the general layouts, and bank and custom layouts fall back to `PL` and `BS`, whose `__getattr__` returns `LineMaker`.
6. **Pickling is out of scope.** Makers and `Model` already contain local closures and lambdas, so standard pickling fails today. Adding metadata does not change that. The docs say serialization is unsupported, and supporting it would be a separate decision.

## 4. Docstring standard

Docstrings use numpydoc, enforced on the public surface only:

- **Summary line.** One line, imperative for functions ("Return …", "Add …") and a noun phrase for classes.
- **Parameters.** Each parameter states:
  - its type
  - its **unit**
  - its accepted forms: scalar, `Series`, `dict` of period labels, kernel, or callback
  - its default

  Unit semantics must be exact. A dimensionless rate is **per period**: `0.12` means 12% per period, whether the period is a month or a year. A rate per unit of time (`0.12 / b.year`) is integrated by period length. Write these out ("currency per period", "dimensionless, per period", "per time, integrated by period length") rather than "rate per year".
- **Returns.** The returned type, with the row or line it creates when there is one.
- **Raises.** Only errors a user can trigger, separated into errors raised **at construction** (when the line or series is declared) and errors raised **at evaluation** (`m.render`, `r[...]`). Examples are `UnitError`, `LedgerError`, an unknown period label, and an unnamed assumption.
- **Notes.** Notes cover accounting-standard differences (IFRS / US GAAP / J-GAAP) and the journal entries created. They link to the narrative docs (`double-entry.md`, `consolidation.md`) instead of repeating them.
- **Examples.** Each example builds a fresh small model, calls `r = m.render()`, and reads results with `r[x]`, `r.value(x, "2027")`, or a scalar reduction. A bare `r.value(x)` on a series that varies by period is avoided. Where units or rates matter, at least one example uses monthly periods, because annual-only examples hide the difference between a per-period rate and a per-time rate. Examples run as doctests.
- **See Also.** See Also links related functions where users commonly confuse them, such as `by_year`/`step`/`by_month`, `lag`/`cumsum`, `settle=`/`cash=`/`recognize=`/`against=`, and `bs.opening`/`opening=`.

Enforcement, by what each check sees:

| Check | Runs on | Catches |
|---|---|---|
| `numpydoc.validate` | runtime objects in the registry, with an adapter for `LineMaker` instances (numpydoc treats callable instances as non-functions, so Parameters and Returns checks are applied explicitly) | missing or ill-formed sections, undocumented parameters |
| `pydoclint` (numpy style) | source | docstring vs signature, return, and attribute mismatches in ordinary code |
| doctest | docstrings and generated maker pages | examples that no longer run or no longer match |
| stub/runtime test | `.pyi` vs `inspect.signature` | drift in maker signatures |

Ruff `D` is not a substitute: its parameter-completeness rule (D417) does not apply to NumPy-style sections. Exceptions are tracked per public path **and violation code**, and may only shrink. An object that is exempt for one code can still fail on a new one.

## 5. Order of work

1. **Registry and boundary (one PR).**
   - Write `public-api.toml` and extend the script to check it as in §3.1.
   - Resolve the `layouts` collision, add `__all__` (including `b.lib`), and make the internal names private.
   - Add the registry test and the docstring checks, with every current failure listed as an exception.
   - Behavior otherwise unchanged: the existing tests pass, and the ledger-call trace is identical.
2. **Reference-build spike (one PR).** Before writing docstrings in bulk, take one example of each kind of public object all the way through: an ordinary function (`b.by_year`), a property (`Series.year`), a returned record (`FxPair`), and a generated maker (`bs.loan`). Each must pass validation, render in Sphinx, resolve its cross-references, and run its doctests. This settles the tooling before the docstring work depends on it.
3. **Line makers (one PR).** `LineMaker`, the runtime `__signature__`/`__doc__`, the generated stubs, and the per-layout reference pages, plus the stub/runtime test.
4. **Docstrings by area, most-used first (one PR each).** Rename questions for an area (§6.3) are settled before its docstrings are written, and callers are migrated in the same PR. Each PR removes its entries from the exception list.
   1. `Model` and `Series`/`LineItem`
   2. `Result` and `testing`
   3. `shapes` and `units`
   4. `Entity` with `BS`/`PL`/`CF`
   5. `lib` (including the return-type fixes)
   6. `Group` and `layouts`
   7. `Style`, `export`, and placement (`row`/`section`/`sheet`/`link`)
5. **Reference site.** Publish the reference generated from docstrings. Drop the parameter lists that `docs/api.md` repeats, and keep `api.md` as the narrative guide.
   - Amended (2026-11-04, user decision "User docs only"): the site carries user documentation only — a home page, a new user guide under `docs/guide/`, and the reference. The design documents in `docs/*.md`, `api.md` included, are dated proposals rather than a guide, so they stay out of the site unchanged; the guide is written fresh from them and checked against the code.

Step 1 also defines the module boundaries for the planned `ledger.py` / `excel.py` splits, so it should land before them. The `excel.expand` dispatch change is internal and independent of all of this.

## 6. Decisions needed

Each item gives the proposal, then the reviewer's position.

1. **Reference tooling: Sphinx + numpydoc** (pydata theme, as numpy/pandas/scipy use), rather than mkdocs + mkdocstrings. It is the standard pairing, and it uses the same `numpydoc.validate` as step 1.
   - Reviewer: agrees, provided the step-2 spike succeeds.
2. **Line-maker type name: `LineMaker`.** It keeps the callable collection separate from the `Kind` metadata.
   - Reviewer: agrees.
3. **Names (§2.3).**
   - **`LineItem.company` → `entity`.** Reviewer agrees.
   - **OCI.** Keep separate names for the four concepts: booking an item, the accumulated balance, the period's OCI, and recycling. Proposal:
     - `co.oci(...)` books an item
     - `bs.oci` is the accumulated balance line
     - `co.other_comprehensive_income` is the period total
     - `co.oci_release` handles recycling

     Only the docs change, unless a name turns out to be misleading once documented. Reviewer: the original plan was underspecified here.
   - **`bs.working_capital` stays a line maker.** It is documented as a declared line, not a computed aggregate. Reviewer agrees.
4. **`boki.layouts` is public for custom layouts, after resolving the name collision (§3.3).**
   - Reviewer: agrees on that condition.
5. **The 15-parameter PL maker stays as one maker.** Document the valid combinations now, preserving the decided `counterparty=` and opening-balance contracts, and decide on a split separately (api-principles §1 item 2).
   - Reviewer: agrees.
6. **Serialization stays unsupported, and the docs say so (§3.6).**

## 7. Review disposition

Each item is a counterpart-review comment and the section of this plan that addresses it.

| # | Severity | Comment | Where addressed |
|---|---|---|---|
| 1 | blocking | The inventory is incomplete and cannot enforce the boundary. | §1 caveat, §3.1, §5.1 |
| 2 | blocking | `layouts` name collision; `b.lib` not exported. | §2.8–9, §3.2–3 |
| 3 | should-fix | Makers need separate runtime, typing, and docs solutions; `income_tax` is a special case. | §1, §3.5 |
| 4 | should-fix | The doctest pattern is wrong, and the per-period vs per-time rate distinction is missing. | §4 |
| 5 | should-fix | Specify what each docs gate checks; ruff D417 does not cover numpy; track exceptions by code. | §4 table |
| 6 | should-fix | Factual fixes: lib return types, `m.t.fn`, 221 plans, top-level modules, 13 keyword-only parameters. | §1, §2.2, §2.4, §2.7 |
| 7 | should-fix | Build the reference earlier; schedule `Style`/`export`/placement; settle names before documenting. | §5.2, §5.4 |
| 8 | nice-to-have | Pickling | §3.6, §6.6 |

The reviewer's `r.value(x)` failure did not reproduce for a constant series (it returned the scalar). §4 still avoids that pattern, because the behavior for a series that varies by period was not checked.
