# modelx feature survey

Surveyed on 2026-10-16 with modelx 0.33.0 (released 2026-09-05) and Python 3.11. I read the documentation and ran boki-related features with `experiments/modelx-features/probe.py`. The output is in `probe.out.txt` in the same directory. The solar project reproduction is in `experiments/modelx-solar/`.

## Overview

- The author works in actuarial science, and the main use is actuarial projection models. lifelib is a collection of models built on modelx. The project describes its design as domain-independent.
- modelx uses the LGPL-3.0 license. Its only dependencies are networkx, asttokens, and libcst. It had 134 GitHub stars, and its latest push was on 2026-10-12, so development was active at the time of this survey.
- modelx has three central concepts: **Cells** are memoized functions, often indexed by time; **Space** is a namespace for Cells and references, with nesting, inheritance, and parameterized copies; **Model** is a collection of Spaces and the unit for saving and exporting.

## Feature results

Legend: ✅ Verified by running; 📄 Verified from documentation only; ❌ Missing or does not work.

| Feature | Check | Behavior | Relevance to boki |
|---|---|---|---|
| Memoization and pull-based evaluation | ✅ | Calculates and caches only the needed Cells and arguments. A second call does not recalculate. | This is the core behavior boki needs from an evaluator. |
| Change inputs | ✅ | Changing a reference such as `s.rate = 0.2` clears the cache, and the next call recalculates. | Could support recalculation when a user changes a slider. |
| Cache invalidation after changing a reference | ✅ | **Also clears caches for Cells that do not depend on the reference** (the entire Space). Dependency tracking covers Cells but not references. | A large model reruns everything when one input changes. At the current scale (a few thousand nodes), this takes about 0.1 seconds and is acceptable. |
| Override an intermediate value with an input | ✅ | `bal[5] = 1000` fixes one period and recalculates later periods (`is_input`). | Could support replacing actuals for one month. |
| Dependency tracking | ✅ | `precedents()`, `preds(t)`, and `succs(t)` show where a value came from and what it affects. `Model.tracegraph` is a directed networkx graph. | Provides the data for a UI that explains where a number came from. |
| Forward references (lead) | ✅ | A backward recurrence that refers to `pv(t + 1)` runs 5,000 periods in 0.02 seconds. The default recursion limit is 65,000. | Can express sculpting as a recurrence. |
| **Circular references** | ✅ ❌ | **Not detected.** Without a recursion limit, recursion deepens until the CPython stack is exhausted and the process segfaults (exit 139). `set_recursion(1000)` raises `FormulaError`, but an internal `TypeError` obscures the cycle in the message. | boki needs its own cycle detection and `solve`. Set a recursion limit so user cycles cannot crash the process. |
| Parameterized Space | ✅ | Calling a Space defined with `formula=lambda gpus, unit_cost: None` as `cluster[1024, 50_000]` creates an `ItemSpace` with those arguments. This supports multiple instances of one structure, such as one cluster per generation. | Useful for templates and instances, including one Space per group company. |
| Inheritance | ✅ | `new_space("Screw", bases=part)` copies Cells and references. The child can override references and formulas with `child.cost.set_formula(...)`. This is prototype inheritance, not class inheritance. | Similar to object-based modeling of components and products, but it cannot use Python `class` syntax. |
| Composition (a Space refers to another Space) | ✅ | A Space can hold another Space as a reference, as in `product.Screw = screw`, and use it in formulas. | Can represent product-to-component relationships. |
| Formula name resolution | ✅ | **Formulas cannot see local variables or closures from their definition site.** They see only the Space namespace of Cells and references. An input reference and a Cell with the same name collide. | Formulas are treated as text in function form. If boki converts series expression objects to Cells, boki must manage the names. |
| pandas conversion | ✅ | Export to a DataFrame with `cells.to_series()` and `space.frame`. It can also create Spaces and Cells from pandas (📄). | Useful for table output and tests. |
| Save as text | ✅ | `write_model` writes each Space as Python-shaped text (`__init__.py`) and JSON. `read_model` reads it back. | Supports diff review, but the text is not executable as ordinary Python; the file says so at the top. |
| Export as a Python package | ✅ | `export_model` creates a **Python package with no modelx dependency**; it imports only the standard library. The exported package returns the same values. | Could support distribution and browser execution with Pyodide. |
| Use an Excel range as input | ✅ | `new_excel_range` reads an Excel range as a dictionary-like reference. | Lets users keep assumption tables, such as price tables, in Excel. |
| **Export to Excel** | 📄 ❌ | Only pandas input data can be saved with `to_excel`. **modelx cannot export a model with formulas to Excel.** | Exporting a business-plan-style workbook from modelx would need custom code. |
| Speed | ✅ | A scalar recurrence takes 0.005 seconds for 1,000 periods. Cells returning numpy arrays take 0.002 seconds for 10,000 scenarios × 120 periods. The full solar project calculation (111 periods, 49 Cells) takes 0.13 seconds. About half the time records dependencies by adding edges to networkx. | Fast enough for business-plan models. Monte Carlo can use Cells that return arrays. |
| Memory-efficient execution | 📄 | `generate_actions` and `execute_actions`; the documentation has no details. | Intended for large models, such as millions of insurance policies. Not needed by boki for now. |
| GUI | 📄 | Only a Spyder (Python IDE) plugin. It shows an object tree, values, and **MxAnalyzer**, which traces dependencies forward and backward. It cannot edit formulas. I found no web UI or Jupyter widgets. | The dependency-tracing view could be useful, but boki needs a separate UI that does not depend on Spyder. |
| Units | ❌ | Not available. | boki will provide them. |
| Accounts and double-entry bookkeeping | ❌ | Not available. | boki will provide them. |
| Cycle solving (`solve`) | ❌ | Not available. | boki will provide it. |

## Findings from the solar project reproduction

- Every spreadsheet output matched within 1e-6. The port was nearly one-to-one.
- A period-length change from one month to three months required only one `months(i)` call.
- The cycle was solved by rebuilding the model externally and iterating six times. boki's `solve` performs this within the model.
- The experiment was slow because it reread the xlsm file on every build, not because of modelx. Reading the file took about one second.

## If boki is built on modelx

**Use directly:** memoization and pull-based evaluation, input changes and recalculation, dependency tracking, parameterized Spaces and inheritance, text storage, export to a package without modelx dependencies, and pandas input and output.

**Add in boki:**

1. **Convert series expression objects to Cells.** Formulas resolve names through the Space namespace, so boki must name and register them in a Space. Users can still work with series as Python variables without managing those names.
2. **Accounts and moves.** Convert account balances into Cells defined as the prior-period balance plus the current period's moves.
3. **Cycle detection and `solve`.** modelx does not detect cycles and can crash, so boki should detect cycles in its dependency graph before evaluation and raise an error. Run fixed-point iteration only for `solve` targets by exposing unknowns as references and clearing the cache when they change. A reference change clears the entire Space, so every iteration recalculates everything; that cost is acceptable.
4. **Units.** Either make Cell values unit-aware or check units when boki converts expressions and keep values as plain floats. The latter is faster and makes exported packages more direct.
5. **Object-based modeling**, from the user's idea. Add a layer that converts Python `class Product(boki.Part)` declarations into modelx Spaces, using `bases` for inheritance and composition for component references.

**Concerns**

- modelx had 134 stars, so its user base was small. Development was active, but it could stop. Under LGPL, distributing a modified version requires publishing the source for the modified parts.
- boki must handle modelx behaviors such as segfaults on cycles and clearing the entire Space when a reference changes.
- Decide how to preserve boki account and unit metadata in exported packages and saved models.

## Proposed next steps

1. Prototype boki's core (`series`, `account`, `move`, and `solve`) as a thin layer that creates modelx Spaces and Cells. Check whether the solar project produces the same values.
2. Implement cycle detection in boki by building a dependency graph during conversion.
3. Prototype a web UI that uses `precedents` and `succs` to show where a value came from and compare scenarios. Do not require Spyder.
