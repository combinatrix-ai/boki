"""Keep the generated static types of the line makers (src/boki/_makers.py) equal to the runtime makers."""
from __future__ import annotations

import inspect
import sys
import tomllib
import typing
from pathlib import Path

import boki as b
from boki import _makers
from boki.layouts import Kind

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import generate_makers

REGISTRY = ROOT / "docs/reference/public-api.toml"


def _layout_entities():
    model = b.Model("Maker types", start="2027-01", periods=1, step=b.year)
    general = [model.entity(standard.name, standard=standard) for standard in (b.IFRS, b.USGAAP, b.JGAAP)]
    return general, general + [model.entity("bank", standard=b.IFRS, layout=b.layouts.bank)]


def _makers_of(entity):
    for kind in entity.layout.pl:
        if isinstance(kind, Kind):
            yield "pl", kind.name, getattr(entity.pl, kind.name)
    for kind in entity.layout.bs:
        yield "bs", kind.name, getattr(entity.bs, kind.name)


def _without_self(signature: inspect.Signature) -> inspect.Signature:
    return signature.replace(parameters=list(signature.parameters.values())[1:])


def test_generated_makers_module_is_current():
    assert _makers.__file__ is not None
    assert Path(_makers.__file__).read_text(encoding="utf-8") == generate_makers.render(), (
        "src/boki/_makers.py is stale; run: uv run python tools/generate_makers.py"
    )


def test_every_general_maker_has_a_protocol_with_its_exact_signature():
    general, everything = _layout_entities()
    declared = {"pl": typing.get_type_hints(_makers.GeneralPL), "bs": typing.get_type_hints(_makers.GeneralBS)}
    checked = {"pl": set(), "bs": set()}
    for entity in everything:
        for namespace, name, maker in _makers_of(entity):
            annotation = declared[namespace].get(name)
            if entity not in general and annotation is None:
                continue  # a bank-only kind falls back to LineMaker
            assert annotation is not None, f"{entity.layout.name} {namespace}.{name} has no type in _makers.py"
            assert annotation is getattr(_makers, annotation.__name__)
            protocol_signature = _without_self(inspect.signature(annotation.__call__))
            assert protocol_signature == inspect.signature(maker), (
                f"{annotation.__name__}.__call__ differs from {entity.layout.name} {namespace}.{name}; "
                "run: uv run python tools/generate_makers.py"
            )
            checked[namespace].add(name)
    assert checked["pl"] and checked["bs"]


def test_protocol_annotations_resolve():
    protocols = [value for name, value in vars(_makers).items()
                 if inspect.isclass(value) and name.endswith("Maker") and value.__module__ == _makers.__name__]
    assert len(protocols) == len(generate_makers.PROTOCOL_NAMES)
    for protocol in protocols:
        typing.get_type_hints(protocol.__call__)


def test_subtotals_of_every_builtin_layout_are_typed():
    _, everything = _layout_entities()
    declared = typing.get_type_hints(_makers.GeneralPL)
    for entity in everything:
        for stage in entity.layout.stages:
            assert declared.get(stage.name) is not None, f"{entity.layout.name} subtotal {stage.name} is not typed"


def test_maker_members_protocol_covers_the_registered_line_maker_members():
    registry = tomllib.loads(REGISTRY.read_text(encoding="utf-8"))["type"]["LineMaker"]
    members = set(registry["public"]) | set(registry["readonly"])
    members.discard("__call__")
    declared = set(typing.get_type_hints(_makers._MakerMembers)) | {
        name for name, value in vars(_makers._MakerMembers).items() if isinstance(value, property) or callable(value)
    }
    assert members <= declared, f"_MakerMembers lacks {sorted(members - declared)}; edit tools/generate_makers.py"
