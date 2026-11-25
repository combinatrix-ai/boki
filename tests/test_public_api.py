"""Keep the hand-written public API registry aligned with runtime exports and objects."""
from __future__ import annotations

import importlib
import inspect
import sys
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from api_samples import build_api_samples, type_samples


REGISTRY = ROOT / "docs/reference/public-api.toml"
MODULE_FILES = {
    "boki": "src/boki/__init__.py",
    "boki.units": "src/boki/units.py",
    "boki.lib": "src/boki/lib.py",
    "boki.shapes": "src/boki/shapes.py",
    "boki.testing": "src/boki/testing.py",
    "boki.export": "src/boki/export.py",
    "boki.layouts": "src/boki/layouts.py",
}
LINE_MAKER_TYPES = {"PL", "BS"}
REQUIRED_TYPES = {
    "Model", "Result", "Entity", "EntityChecks", "PL", "BS", "CF", "LineMaker", "LineItem", "Series", "Named",
    "Group", "Unit", "Quantity", "FxPair", "Input", "Unknown", "Timeline", "Period", "Fiscal", "Calendar",
    "Kernel", "Style", "StylePresets", "Bound", "Comparison", "Entry", "CheckResult", "PlacementLine", "Section",
    "Sheet", "Link", "Block", "Panel", "Sensitivity", "Table", "Report", "CircularReferenceWarning", "Untranslatable",
    "UnnamedAssumption", "EquivalenceError", "CheckFailed", "LedgerError",
    "CycleError", "UnitError", "NoRateOfReturn", "NOL", "Equity", "Layout", "Kind", "Stage", "Standard",
}


def _resolve(path: str):
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        try:
            value = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        for part in parts[split:]:
            value = getattr(value, part)
        return value
    raise AssertionError(f"Cannot import {path}; update {REGISTRY.relative_to(ROOT)}")


def test_public_modules_match_registry(tmp_path):
    modules, _ = build_api_samples(tmp_path / "api-sample.xlsx")
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))

    assert set(registry["module"]) == set(modules), (
        f"Public module entries differ; update {REGISTRY.relative_to(ROOT)} and the public module list in "
        "tests/test_public_api.py"
    )
    for path, entry in registry["module"].items():
        module = modules[path]
        expected = set(entry["names"])
        actual = set(getattr(module, "__all__", ()))
        assert actual == expected, (
            f"{path}.__all__ differs from {REGISTRY.relative_to(ROOT)}; edit {MODULE_FILES[path]} or the registry"
        )
        for name in expected:
            assert hasattr(module, name), f"{path}.{name} is missing; edit {MODULE_FILES[path]} or the registry"


def test_registered_type_members_are_complete(tmp_path):
    _, samples = build_api_samples(tmp_path / "api-sample.xlsx")
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))
    receivers = samples["_receivers"]

    assert set(registry["type"]) == REQUIRED_TYPES, (
        f"Registered types differ from the step-1 contract; edit {REGISTRY.relative_to(ROOT)} and "
        "tools/api_samples.py"
    )
    for type_name, entry in registry["type"].items():
        assert ("path" in entry) != ("receiver" in entry), (
            f"{type_name} needs exactly one of path or receiver; edit {REGISTRY.relative_to(ROOT)}"
        )
        objects = type_samples(samples, type_name)
        if "receiver" in entry:
            assert entry["receiver"] in receivers, (
                f"{type_name} receiver {entry['receiver']!r} is not built; edit tools/api_samples.py or "
                f"{REGISTRY.relative_to(ROOT)}"
            )
            assert objects[0] is receivers[entry["receiver"]], (
                f"{type_name} receiver {entry['receiver']!r} does not identify its sample; edit "
                f"tools/api_samples.py or {REGISTRY.relative_to(ROOT)}"
            )
        if "path" in entry:
            type_object = _resolve(entry["path"])
            if isinstance(type_object, type) and not (len(objects) == 1 and objects[0] is type_object):
                assert all(isinstance(obj, type_object) for obj in objects), (
                    f"{type_name} sample does not match {entry['path']}; edit tools/api_samples.py or "
                    f"{REGISTRY.relative_to(ROOT)}"
                )
            else:
                assert len(objects) == 1 and objects[0] is type_object, (
                    f"{type_name} sample does not match {entry['path']}; edit tools/api_samples.py or "
                    f"{REGISTRY.relative_to(ROOT)}"
                )

        categories = {key: entry.get(key, []) for key in ("public", "readonly", "internal")}
        all_members = [name for names in categories.values() for name in names]
        counts = Counter(all_members)
        duplicates = sorted(name for name, count in counts.items() if count != 1)
        assert not duplicates, (
            f"{type_name} members appear in multiple classifications: {duplicates}; edit "
            f"{REGISTRY.relative_to(ROOT)}"
        )

        inherited_exception_members = set().union(
            *(_inherited_builtin_exception_members(obj) for obj in objects)
        )
        registered_inherited = sorted(set(all_members) & inherited_exception_members)
        assert not registered_inherited, (
            f"{type_name} registers inherited built-in exception members {registered_inherited}; edit "
            f"{REGISTRY.relative_to(ROOT)}"
        )

        found = {
            name for obj in objects for name in dir(obj)
            if not name.startswith("_") and name not in inherited_exception_members
        }
        # PL/BS maker names are public but depend on the selected entity layout, so derive them rather than
        # duplicating them in the hand-written registry.
        dynamic_makers = _layout_maker_names(samples, type_name) if type_name in LINE_MAKER_TYPES else set()
        if dynamic_makers:
            assert not dynamic_makers & set(all_members), (
                f"{type_name} lists layout-derived makers in the registry; keep only non-maker members in "
                f"{REGISTRY.relative_to(ROOT)}"
            )
            found -= dynamic_makers
        registered_dunders = {
            name for name in all_members if name.startswith("__") and name.endswith("__")
        }
        found.update(registered_dunders)
        missing = sorted(found - set(all_members))
        assert not missing, (
            f"{type_name} has unclassified members {missing}; add each to public, readonly, or internal in "
            f"{REGISTRY.relative_to(ROOT)}"
        )

        for name in all_members:
            assert any(_has_member(obj, name) for obj in objects), (
                f"{type_name}.{name} is listed but missing from its sample; edit {REGISTRY.relative_to(ROOT)}"
            )


def _has_member(obj, name: str) -> bool:
    try:
        inspect.getattr_static(obj, name)
    except AttributeError:
        return hasattr(obj, name)
    return True


def _inherited_builtin_exception_members(obj) -> set[str]:
    if not isinstance(obj, BaseException):
        return set()
    cls = type(obj)
    return {
        name
        for base in cls.__mro__[1:]
        if base.__module__ == "builtins" and issubclass(base, BaseException)
        for name in vars(base)
        if name not in vars(cls)
    }


def _layout_maker_names(samples, type_name: str) -> set[str]:
    names = set()
    for entity in samples["_layout_entities"]:
        statement = entity.pl if type_name == "PL" else entity.bs
        layout_names = entity.layout.pl_kinds if type_name == "PL" else tuple(kind.name for kind in entity.layout.bs)
        for name in layout_names:
            maker = getattr(statement, name)
            assert callable(maker), f"{type_name}.{name} is not callable for layout {entity.layout.name!r}"
            names.add(name)
    return names
