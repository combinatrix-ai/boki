"""Enforce numpydoc and pydoclint on the registered API with shrink-only exceptions."""
from __future__ import annotations

import ast
import doctest
import importlib
import inspect
import io
import re
import subprocess
import sys
import tempfile
import tomllib
from collections import defaultdict
from pathlib import Path
from types import ModuleType

from numpydoc.docscrape import get_doc_object
from numpydoc.validate import Validator, validate

from boki._maker_docs import TEMPLATES, maker_doc


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from api_samples import build_api_samples, type_samples

REGISTRY_PATH = ROOT / "docs/reference/public-api.toml"
EXCEPTIONS_PATH = ROOT / "docs/reference/doc-exceptions.toml"

# ES01 allows a summary-only docstring during step 1; extended summaries come in the documentation pass.
# SA01 allows missing See Also sections until related-reference links are written.
IGNORED_NUMPYDOC_CODES = {"ES01", "SA01"}
# EX01 is not required where the Examples live elsewhere: a constructor's are on its class, and a built-in stage
# formula is a value of `Stage.formula`, shown on the layouts page.
EXAMPLES_ELSEWHERE = (".__init__", ".<lambda>")

PYDOC_FILES = [
    "src/boki/__init__.py",
    "src/boki/units.py",
    "src/boki/lib.py",
    "src/boki/shapes.py",
    "src/boki/testing.py",
    "src/boki/export.py",
    "src/boki/layouts.py",
    "src/boki/styles.py",
    "src/boki/series.py",
    "src/boki/model.py",
    "src/boki/ledger.py",
    "src/boki/statements.py",
    "src/boki/placement.py",
    "src/boki/excel.py",
    "src/boki/evaluator.py",
    "src/boki/group/core.py",
]
PYDOC_DIAGNOSTIC = re.compile(r"^(?P<file>.*?\.py):(?P<line>\d+):\s+(?P<code>DOC\d{3}):")
MODULE_FILES = {
    "boki": "src/boki/__init__.py",
    "boki.units": "src/boki/units.py",
    "boki.lib": "src/boki/lib.py",
    "boki.shapes": "src/boki/shapes.py",
    "boki.testing": "src/boki/testing.py",
    "boki.export": "src/boki/export.py",
    "boki.layouts": "src/boki/layouts.py",
}
SOURCE_FALLBACKS = {
    "boki.ledger": "boki.Entity",
    "boki.model": "boki.Model",
    "boki.series": "boki.Series",
    "boki.statements": "boki.LedgerError",
    "boki.styles": "boki.Style",
    "boki.placement": "boki.row",
    "boki.excel": "boki.Result",
    "boki.evaluator": "boki.CycleError",
    "boki.group.core": "boki.Group",
}


def _path_object(path: str):
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        try:
            value = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        for part in parts[split:]:
            value = getattr(value, part)
        return value
    raise AssertionError(f"Cannot import registered path {path}; edit {REGISTRY_PATH.relative_to(ROOT)}")


def _class_path(obj) -> str:
    cls = obj if isinstance(obj, type) else type(obj)
    return f"{cls.__module__}.{cls.__qualname__}"


def _validation_path(obj) -> str:
    if isinstance(obj, ModuleType):
        return obj.__name__
    module = getattr(obj, "__module__", type(obj).__module__)
    name = getattr(obj, "__qualname__", getattr(obj, "__name__", type(obj).__qualname__))
    return f"{module}.{name}"


def _record_validation(failures, public_path: str, obj) -> None:
    result = validate(obj, validator_cls=_ObjectValidator)
    for code, _message in result.get("errors", []):
        if code == "EX01" and public_path.endswith(EXAMPLES_ELSEWHERE):
            continue
        if code not in IGNORED_NUMPYDOC_CODES:
            failures[public_path].add(code)


class _ObjectValidator(Validator):
    def __init__(self, obj_name, **kwargs):
        super().__init__(get_doc_object(obj_name, **kwargs))

    @property
    def source_file_def_line(self):
        try:
            return super().source_file_def_line
        except StopIteration:
            try:
                return inspect.getsourcelines(self.obj)[1]
            except (OSError, TypeError):
                return None

    @property
    def method_source(self):
        try:
            return super().method_source
        except OSError:  # a function made at run time, such as the __init__ of a dataclass, has no source
            return ""


def _public_candidates(modules, samples, registry):
    for module_path, module in modules.items():
        for name in registry["module"][module_path]["names"]:
            obj = getattr(module, name)
            if isinstance(obj, ModuleType):
                continue
            elif isinstance(obj, type) or callable(obj) or isinstance(obj, property):
                path = f"{module_path}.{name}"
                if isinstance(obj, type) and obj.__name__ == "styles" and obj.__module__ == "boki.styles":
                    path = "boki.styles.styles"
                yield path, obj

    for type_name, entry in registry["type"].items():
        values = type_samples(samples, type_name)
        sample = values[0]
        owner_path = entry.get("path", _class_path(sample))
        if type_name == "FxPair":
            yield owner_path, type(sample)
        for member in entry.get("public", []) + entry.get("readonly", []):
            target = None
            for obj in values:
                try:
                    raw = inspect.getattr_static(obj, member)
                except AttributeError:
                    continue
                if isinstance(raw, property):
                    target = raw.fget
                elif isinstance(raw, (classmethod, staticmethod)):
                    target = raw.__func__
                elif inspect.isroutine(raw) or isinstance(raw, type):
                    target = raw
                else:
                    try:
                        value = getattr(obj, member)
                    except Exception:
                        value = raw
                    if isinstance(value, type) or inspect.isroutine(value):
                        target = value
                    elif callable(value):
                        target = type(value)
                if target is not None:
                    break
            if target is not None:
                if inspect.ismethoddescriptor(target):
                    continue
                path = f"{owner_path}.{member}"
                defined_path = _validation_path(target)
                if "<locals>" not in defined_path:
                    path = defined_path
                yield path, target


def _numpydoc_failures(modules, samples, registry):
    failures = defaultdict(set)
    seen = set()
    for path, obj in _public_candidates(modules, samples, registry):
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        try:
            _record_validation(failures, path, obj)
        except Exception as error:
            raise RuntimeError(f"numpydoc failed for {path} via {_validation_path(obj)}") from error
    return failures


def _source_module(file: str) -> str:
    path = Path(file)
    parts = list(path.with_suffix("").parts)
    if parts[:2] == ["src", "boki"]:
        parts = parts[2:]
    else:
        return "boki"
    if parts == ["__init__"]:
        return "boki"
    return ".".join(["boki", *parts])


def _scope_paths(file: Path, module_path: str):
    tree = ast.parse(file.read_text(encoding="utf-8"))
    scopes = []

    def walk(node, parent):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                path = f"{parent}.{child.name}"
                scopes.append((child.lineno, child.end_lineno or child.lineno, path))
                walk(child, path)
            else:
                walk(child, parent)

    walk(tree, module_path)
    return scopes


def _registered_source_paths(modules, samples, registry):
    paths = set(modules)
    for module_path, entry in registry["module"].items():
        for name in entry["names"]:
            paths.add(f"{module_path}.{name}")
            value = getattr(modules[module_path], name)
            if isinstance(value, type) or callable(value):
                paths.add(_class_path(value))
    for type_name, entry in registry["type"].items():
        values = type_samples(samples, type_name)
        owner = entry.get("path", _class_path(values[0]))
        paths.update((owner, _class_path(values[0])))
        for member in entry.get("public", []) + entry.get("readonly", []):
            paths.add(f"{owner}.{member}")
            paths.add(f"{_class_path(values[0])}.{member}")
    return paths


def _pydoclint_failures(modules, samples, registry):
    command = [
        "pydoclint",
        "--style=numpy",
        "--skip-checking-private-functions",
        "True",
        "--show-filenames-in-every-violation-message",
        "True",
        *PYDOC_FILES,
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    parsed = []
    for line in output.splitlines():
        match = PYDOC_DIAGNOSTIC.match(line)
        if match:
            parsed.append((match.group("file"), int(match.group("line")), match.group("code")))
    if result.returncode not in (0, 1) or (result.returncode == 1 and not parsed):
        raise AssertionError(f"pydoclint did not complete cleanly:\n{output}")

    registered = _registered_source_paths(modules, samples, registry)
    scopes_by_file = {}
    failures = defaultdict(set)
    for file_name, line, code in parsed:
        file_path = Path(file_name)
        if not file_path.is_absolute():
            file_path = ROOT / file_path
        relative = file_path.relative_to(ROOT).as_posix()
        module_path = _source_module(relative)
        scopes = scopes_by_file.setdefault(relative, _scope_paths(file_path, module_path))
        matches = [scope for start, end, scope in scopes if start <= line <= end]
        public_path = min(matches, key=len) if matches else module_path
        if public_path not in registered:
            public_path = SOURCE_FALLBACKS.get(module_path, module_path)
        failures[public_path].add(code)
    return failures


def _collect_failures(output_path: Path):
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    modules, samples = build_api_samples(output_path)
    failures = _numpydoc_failures(modules, samples, registry)
    for path, codes in _pydoclint_failures(modules, samples, registry).items():
        failures[path].update(codes)
    return {path: sorted(codes) for path, codes in failures.items() if codes}


def _write_exceptions():
    with tempfile.TemporaryDirectory() as temp:
        failures = _collect_failures(Path(temp) / "api-sample.xlsx")
    lines = ["# Current public API docstring violations. Remove entries as they are fixed.", "", "[violations]"]
    for path, codes in sorted(failures.items()):
        values = ", ".join(f'"{code}"' for code in codes)
        lines.append(f'"{path}" = [{values}]')
    EXCEPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXCEPTIONS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(failures)} exception paths to {EXCEPTIONS_PATH.relative_to(ROOT)}")


def test_registered_docstrings_match_shrink_only_exceptions(tmp_path):
    actual = _collect_failures(tmp_path / "api-sample.xlsx")
    exceptions = tomllib.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8")).get("violations", {})
    expected = {path: sorted(set(codes)) for path, codes in exceptions.items() if codes}

    unexpected = {
        (path, code)
        for path, codes in actual.items()
        for code in codes
        if code not in expected.get(path, [])
    }
    stale = {
        (path, code)
        for path, codes in expected.items()
        for code in codes
        if code not in actual.get(path, [])
    }
    assert not unexpected, (
        f"New docstring violations {sorted(unexpected)}; update docstrings or "
        f"{EXCEPTIONS_PATH.relative_to(ROOT)}"
    )
    assert not stale, (
        f"Resolved violations remain listed {sorted(stale)}; shrink {EXCEPTIONS_PATH.relative_to(ROOT)}"
    )


def _run_docstring_examples(docstring, name, filename=None):
    test = doctest.DocTestParser().get_doctest(docstring, {}, name, filename, 0)
    output = io.StringIO()
    result = doctest.DocTestRunner().run(test, out=output.write)
    assert result.failed == 0, f"{name} doctest failed:\n{output.getvalue()}"
    return result.attempted


def _example_docstrings(modules, samples, registry):
    """Every registered object's docstring that has examples, keyed by text so a shared docstring runs once."""
    objects = list(_public_candidates(modules, samples, registry))
    for type_name, entry in registry["type"].items():
        sample = type_samples(samples, type_name)[0]
        objects.append((entry.get("path", _class_path(sample)), sample if isinstance(sample, type) else type(sample)))
    docstrings = {}
    for path, obj in objects:
        doc = inspect.getdoc(obj)
        if doc and ">>>" in doc:
            docstrings.setdefault(doc, []).append(path)
    return docstrings


def test_registered_object_docstring_examples_execute(tmp_path):
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    modules, samples = build_api_samples(tmp_path / "api-sample.xlsx")
    docstrings = _example_docstrings(modules, samples, registry)
    assert docstrings
    attempted = 0
    for doc, paths in docstrings.items():
        attempted += _run_docstring_examples(doc, paths[0])
    assert attempted > 500


# Types and module-level names whose classes, functions and methods must all carry an Examples section. Each area
# of the docstring plan adds its own names when it lands. Plain attributes and properties are exempt.
EXAMPLES_REQUIRED_TYPES = (
    # Model, Series, LineItem and the series functions
    "Model", "Series", "Named", "Input", "Unknown", "Timeline", "Period", "LineItem", "CycleError",
    # Result and boki.testing
    "Result", "CheckResult", "CheckFailed", "Table", "Bound", "Comparison", "Entry",
)
EXAMPLES_REQUIRED_NAMES = (
    "ceil", "exp", "floor", "log", "max", "min", "mod", "round", "rounddown", "roundup", "sqrt", "date", "timeline",
    "above", "approx", "below", "between", "compare", "expect",
)


def _routine(values, member):
    """The function or method behind a registered member, or None for an attribute such as a series."""
    for obj in values:
        try:
            value = getattr(obj, member)
        except Exception:
            continue
        if inspect.ismethod(value) or inspect.isfunction(value):
            return value
    return None


def test_required_areas_document_every_function_method_and_class_with_examples(tmp_path):
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    modules, samples = build_api_samples(tmp_path / "api-sample.xlsx")
    missing = []
    for name in EXAMPLES_REQUIRED_NAMES:
        if ">>>" not in (inspect.getdoc(getattr(modules["boki"], name)) or ""):
            missing.append(f"boki.{name}")
    for type_name in EXAMPLES_REQUIRED_TYPES:
        entry = registry["type"][type_name]
        values = type_samples(samples, type_name)
        cls = _path_object(entry["path"]) if "path" in entry else type(values[0])
        if ">>>" not in (inspect.getdoc(cls) or ""):
            missing.append(f"{type_name} (class)")
        for member in entry.get("public", []):
            routine = _routine(values, member)
            if routine is not None and ">>>" not in (inspect.getdoc(routine) or ""):
                missing.append(f"{type_name}.{member}")
    assert not missing, f"Add an Examples section to: {missing}"


# Areas whose public objects all carry executable examples: every function, method, and class of these modules and
# types is run as a doctest, so a new or changed member cannot ship without a working example.
EXAMPLE_AREAS = {
    "shapes, units, and lib": {
        "modules": ("boki.shapes", "boki.units", "boki.lib"),
        "types": ("Kernel", "Unit", "Quantity", "UnitError", "NoRateOfReturn"),
    },
}
AREA_PAGES = {
    "boki.shapes": "docs/reference/api/shapes.md",
    "boki.units": "docs/reference/api/units.md",
    "boki.lib": "docs/reference/api/lib.md",
}


def _example_area_candidates(tmp_path, area):
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    modules, samples = build_api_samples(tmp_path / "api-sample.xlsx")
    scoped_registry = {
        "module": {name: registry["module"][name] for name in area["modules"]},
        "type": {name: registry["type"][name] for name in area["types"]},
    }
    scoped_modules = {name: modules[name] for name in area["modules"]}
    return list(_public_candidates(scoped_modules, samples, scoped_registry))


def test_example_areas_run_an_example_for_every_public_object(tmp_path):
    for area_name, area in EXAMPLE_AREAS.items():
        candidates = _example_area_candidates(tmp_path, area)
        assert len(candidates) > 40, area_name
        for path, obj in candidates:
            docstring = inspect.getdoc(obj)
            assert docstring and ">>>" in docstring, f"{path} has no example"
            attempted = _run_docstring_examples(docstring, path, inspect.getsourcefile(obj))
            assert attempted, f"{path} ran no example"


def test_example_area_pages_list_every_registered_name():
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    for module, page in AREA_PAGES.items():
        text = (ROOT / page).read_text(encoding="utf-8")
        for name in registry["module"][module]["names"]:
            assert re.search(rf"\b{re.escape(name)}\b", text), f"{page} does not mention {module}.{name}"


def test_unit_constants_table_matches_the_module():
    from boki import units

    rows = {}
    for line in (ROOT / "docs/reference/api/units.md").read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`") and cells[0].endswith("`"):
            rows[cells[0].strip("`")] = (cells[1], float(cells[2].replace(",", "")))
    constants = {name for name in units.__all__ if isinstance(getattr(units, name), units.Unit)}
    assert set(rows) == constants
    for name, (dimension, scale) in rows.items():
        constant = getattr(units, name)
        assert dimension == units._describe(constant.dims), name
        assert scale == constant.scale, name
    import boki

    for name in ("day", "h", "month", "quarter", "year"):
        assert getattr(boki, name) is getattr(units, name)


AREA_3_TYPES = (
    "Entity", "EntityChecks", "PL", "BS", "Equity", "CF", "Group", "Layout", "Kind", "Stage", "Standard", "Fiscal",
    "Calendar", "Style", "StylePresets", "PlacementLine", "Section", "Sheet", "Link", "Block", "Panel", "Sensitivity", "Report",
    "CircularReferenceWarning", "Untranslatable", "UnnamedAssumption", "EquivalenceError", "LedgerError",
)
AREA_3_FUNCTIONS = (
    "boki.fiscal", "boki.calendar", "boki.row", "boki.link", "boki.block", "boki.panel", "boki.sensitivity", "boki.section",
    "boki.sheet", "boki.export.to_beancount",
)
AREA_3_PAGES = ("docs/reference/api/layouts.md",)
DOCTEST_BLOCK = re.compile(r"^```\{doctest\}\n(.*?)^```$", re.S | re.M)


def _member_doc(cls, member):
    """The docstring owner of a registered member: a property's getter, a method, or None for a plain attribute."""
    try:
        raw = inspect.getattr_static(cls, member)
    except AttributeError:
        return None
    if isinstance(raw, property):
        return raw.fget
    return raw if inspect.isroutine(raw) else None


def test_entity_group_layout_and_output_docstring_examples_execute(tmp_path):
    registry = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    _, samples = build_api_samples(tmp_path / "api-sample.xlsx")
    attempted = 0
    for type_name in AREA_3_TYPES:
        entry = registry["type"][type_name]
        cls = _path_object(entry["path"]) if "path" in entry else type(type_samples(samples, type_name)[0])
        assert _run_docstring_examples(inspect.getdoc(cls), f"{type_name} class", inspect.getsourcefile(cls)), type_name
        for member in entry.get("public", []):
            if member == "__init__":
                continue
            owner = _member_doc(cls, member)
            if owner is None:  # a plain attribute, such as a CF section: documented in the class's Attributes
                continue
            attempted += _run_docstring_examples(inspect.getdoc(owner), f"{type_name}.{member}") or _fail(type_name, member)
        for member in entry.get("readonly", []):
            owner = _member_doc(cls, member)
            if owner is not None and ">>>" in (inspect.getdoc(owner) or ""):
                attempted += _run_docstring_examples(inspect.getdoc(owner), f"{type_name}.{member}")
    for path in AREA_3_FUNCTIONS:
        function = _path_object(path)
        attempted += _run_docstring_examples(inspect.getdoc(function), path) or _fail(path, "")
    assert attempted > 100


def _fail(owner, member):
    raise AssertionError(f"{owner}.{member} has no docstring example")


def test_custom_layout_page_examples_execute():
    for page in AREA_3_PAGES:
        text = (ROOT / page).read_text(encoding="utf-8")
        blocks = DOCTEST_BLOCK.findall(text)
        assert blocks, page
        assert _run_docstring_examples("\n".join(blocks), page, page)


def _numpydoc_function_adapter(obj):
    def adapter(*args, **kwargs):
        return obj(*args, **kwargs)

    adapter.__doc__ = obj.__doc__
    adapter.__signature__ = inspect.signature(obj)
    adapter.__name__ = obj.kind
    return adapter


def _custom_layout():
    from boki.layouts import Kind, Layout, Stage

    return Layout(
        "custom",
        pl=(
            Kind("royalty", "income", cf="pl", mechanism="pl"),
            Kind("income_tax", "expense", cf="pl", mechanism="pl"),
            Stage("net_income", lambda pl: pl.royalty.total - pl.income_tax.total),
        ),
        bs=(
            Kind("escrow", "asset", "current"),
            Kind("pool", "asset", "noncurrent", "investing", mechanism="fixed_asset"),
            Kind("note", "liability", "noncurrent", "financing", mechanism="loan"),
            Kind("shares", "equity", cf="financing", mechanism="capital"),
        ),
        interest_kind="income_tax",
        depreciation_kind="royalty",
    )


def _layout_entities():
    import boki as b

    model = b.Model("Maker docs", start="2027-01", periods=2, step=b.month)
    return [
        model.entity("IFRS", standard=b.IFRS),
        model.entity("US GAAP", standard=b.USGAAP),
        model.entity("J-GAAP", standard=b.JGAAP),
        model.entity("bank", standard=b.IFRS, layout=b.layouts.bank),
        model.entity("custom", standard=b.IFRS, layout=_custom_layout()),
    ]


def _entity_makers(entity):
    from boki.layouts import Kind

    for kind in entity.layout.pl:
        if isinstance(kind, Kind):
            yield f"{entity.layout.name} pl.{kind.name}", kind, getattr(entity.pl, kind.name)
    for kind in entity.layout.bs:
        yield f"{entity.layout.name} bs.{kind.name}", kind, getattr(entity.bs, kind.name)


def test_every_maker_of_every_layout_is_documented_and_validates():
    from boki.ledger import LineMaker

    seen_templates = set()
    count = 0
    for entity in _layout_entities():
        for label, kind, maker in _entity_makers(entity):
            count += 1
            assert isinstance(maker, LineMaker), label
            failures = defaultdict(set)
            _record_validation(failures, label, _numpydoc_function_adapter(maker))
            assert not failures.get(label), f"{label} docstring violations: {sorted(failures[label])}"

            signature = inspect.signature(maker)
            assert signature == inspect.signature(maker._create), label
            parsed = get_doc_object(_numpydoc_function_adapter(maker))
            assert [parameter.name for parameter in parsed["Parameters"]] == list(signature.parameters), label
            assert parsed["Returns"], label
            assert f"``{kind.name}`` is " in maker.__doc__, label
            seen_templates.add(maker._template)
    assert count > 100
    assert seen_templates == set(TEMPLATES)


def test_maker_documents_its_kind_metadata():
    import boki as b

    model = b.Model("Maker metadata", start="2027-01", periods=2, step=b.month)
    company = model.entity("A", standard=b.IFRS)
    assert ("``loan`` is a liability kind of the IFRS general layout, in the ``noncurrent`` section. "
            "Its cash-flow class is ``financing``.") in company.bs.loan.__doc__
    assert "``revenue`` is an income kind of the IFRS general layout, listed before the ``gross_profit`` subtotal." \
        in company.pl.revenue.__doc__
    assert "``capital`` is an equity kind of the IFRS general layout. Its cash-flow class is ``financing``." \
        in company.bs.capital.__doc__


def test_a_maker_without_a_template_is_an_error():
    import boki as b
    from boki.ledger import _line_maker

    model = b.Model("Missing template", start="2027-01", periods=1, step=b.year)
    company = model.entity("A", standard=b.IFRS)
    kind = next(item for item in company.layout.bs if item.name == "loan")
    try:
        _line_maker(company, kind, company.bs.loan._create, "missing")
    except KeyError as error:
        assert "missing" in str(error)
    else:
        raise AssertionError("a maker with an unknown template key was built")


def test_maker_template_examples_execute_once_per_template():
    for key in TEMPLATES:
        assert _run_docstring_examples(inspect.cleandoc(maker_doc(key)), f"maker template {key}"), key


if __name__ == "__main__" and sys.argv[1:] == ["--write-exceptions"]:
    _write_exceptions()


def test_guide_page_examples_execute():
    for page in sorted((ROOT / "docs").glob("index.md")) + sorted((ROOT / "docs/guide").glob("*.md")):
        blocks = DOCTEST_BLOCK.findall(page.read_text(encoding="utf-8"))
        if blocks:
            assert _run_docstring_examples("\n".join(blocks), page.name, str(page))
