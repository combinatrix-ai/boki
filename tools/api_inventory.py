"""Inventory boki's registered API: exports, member classes, signatures, and corpus usage.

Usage: uv run python tools/api_inventory.py [--json] > docs/api-surface.md
"""
import ast
import inspect
import json
import pathlib
import re
import sys
import tempfile
import types
import tomllib
from collections import Counter

from api_samples import build_api_samples, type_samples

ROOT = pathlib.Path(__file__).resolve().parents[1]
AS_JSON = "--json" in sys.argv[1:]
REGISTRY_PATH = ROOT / "docs/reference/public-api.toml"
REGISTRY = tomllib.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def doc_status(obj):
    doc = inspect.getdoc(obj) or ""
    if not doc:
        return "none"
    if re.search(r"^(Parameters|Returns)\n-{3,}", doc, re.M):
        return "numpydoc"
    return "summary" if "\n" not in doc.strip() else "prose"


def sig(obj):
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return ""


def public_modules(samples):
    modules = samples
    rows = []
    for module_path, entry in REGISTRY["module"].items():
        module = modules[module_path]
        for name in entry["names"]:
            value = getattr(module, name)
            kind = "module" if isinstance(value, types.ModuleType) else \
                "class" if isinstance(value, type) else "function" if callable(value) else "value"
            rows.append({
                "owner": module_path,
                "name": name,
                "classification": "public",
                "kind": kind,
                "signature": sig(value) if kind == "function" else "",
                "doc": doc_status(value) if kind in ("function", "class", "module") else "-",
                "defined_in": getattr(value, "__module__", ""),
            })
    return rows


def type_members(samples):
    rows = []
    for type_name, entry in REGISTRY["type"].items():
        objects = type_samples(samples, type_name)
        for classification in ("public", "readonly", "internal"):
            for name in entry.get(classification, []):
                raw = None
                value = None
                for obj in objects:
                    try:
                        raw = inspect.getattr_static(obj, name)
                    except AttributeError:
                        continue
                    if isinstance(raw, property):
                        break
                    try:
                        value = getattr(obj, name)
                    except Exception:
                        value = raw
                    break
                kind = "property" if isinstance(raw, property) else \
                    "class" if isinstance(value, type) else \
                    "method" if callable(value) and not isinstance(value, type) else "attribute"
                target = raw.fget if isinstance(raw, property) else value
                rows.append({
                    "owner": type_name,
                    "name": name,
                    "classification": classification,
                    "kind": kind,
                    "signature": sig(target) if kind == "method" else "",
                    "doc": doc_status(target) if kind in ("method", "property", "class") else "-",
                    "defined_in": getattr(target, "__module__", ""),
                })
    return rows


def usage_counts():
    usage = Counter()
    files = [*ROOT.glob("examples/**/*.py")]
    for file in files:
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute):
                base = node.value
                if isinstance(base, ast.Attribute) and base.attr in ("pl", "bs", "cf"):
                    usage[f"{base.attr}.{node.attr}"] += 1
                elif isinstance(base, ast.Name) and base.id == "b":
                    usage[f"b.{node.attr}"] += 1
                else:
                    usage[f".{node.attr}"] += 1
    return usage


def layout_kinds(samples):
    kinds = []
    for entity in samples["_layout_entities"]:
        layout = entity.layout
        for name in layout.pl_kinds:
            maker = getattr(entity.pl, name)
            kinds.append({"layout": layout.name, "standard": entity.standard.name, "ns": "pl", "kind": name,
                          "signature": sig(getattr(maker, "_create", None))})
        for kind in layout.bs:
            maker = getattr(entity.bs, kind.name)
            kinds.append({"layout": layout.name, "standard": entity.standard.name, "ns": "bs", "kind": kind.name,
                          "mechanism": kind.mechanism, "signature": sig(getattr(maker, "_create", None))})
    return kinds


def markdown(rows, kinds, usage):
    print("# boki API surface (generated)\n")
    print("Generated from `docs/reference/public-api.toml` by `tools/api_inventory.py`. Do not edit by hand.\n")
    print("`classification`: public, readonly, or internal (reachable but unsupported).")
    print("`doc`: none / summary (one line) / prose (several lines, not numpydoc) / numpydoc.")
    print("`uses`: attribute-name hits in `examples/` (by name, so approximate).\n")
    owner = None
    calls = dict(usage)
    for row in rows:
        if row["owner"] != owner:
            owner = row["owner"]
            print(f"\n## {owner}\n\n| name | classification | kind | doc | uses | signature |\n|---|---|---|---|---:|---|")
        hits = calls.get(f"b.{row['name']}" if owner == "boki" else f".{row['name']}", 0)
        signature = row["signature"].replace("|", "\\|")
        cells = [f"`{row['name']}`", row["classification"], row["kind"], row["doc"], str(hits),
                 f"`{signature}`" if signature else ""]
        print("| " + " | ".join(cells) + " |")

    print("\n## Line makers by layout (pl.<kind> / bs.<kind>)\n\n| classification | standard | layout | ns | mechanism | kinds | signature |\n|---|---|---|---|---|---|---|")
    groups = {}
    for kind in kinds:
        groups.setdefault((kind["standard"], kind["layout"], kind["ns"], kind.get("mechanism", "pl"),
                           kind["signature"]), set()).add(kind["kind"])
    for (standard, layout, ns, mechanism, signature), names in sorted(groups.items()):
        print(f"| public | {standard} | {layout} | {ns} | {mechanism} | {', '.join(sorted(names))} | `{signature}` |")

    print("\n## Usage by `pl.` / `bs.` / `cf.` / `b.`\n\n| call | uses |\n|---|---:|")
    for name, count in usage.most_common():
        if name.split(".")[0] in ("pl", "bs", "cf", "b"):
            print(f"| `{name}` | {count} |")


def main():
    with tempfile.TemporaryDirectory() as temp:
        modules, samples = build_api_samples(pathlib.Path(temp) / "api-sample.xlsx")
        rows = public_modules(modules) + type_members(samples)
        kinds = layout_kinds(samples)
    usage = usage_counts()
    if AS_JSON:
        json.dump({"rows": rows, "kinds": kinds, "usage": usage.most_common()}, sys.stdout, indent=1, default=str)
        sys.exit()
    markdown(rows, kinds, usage)


if __name__ == "__main__":
    main()
