"""Source inventory for the documentation appendices: routes, Python classes/functions, Dart classes/members.
usage: python inventory.py <project root> <out.json>"""
import ast
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = {"routes": [], "python": [], "dart": []}


def doc1(node):
    d = ast.get_docstring(node) or ""
    d = " ".join(d.split())
    m = re.match(r"(.+?[.!?])(\s|$)", d)
    return (m.group(1) if m else d)[:220]


def sig(fn):
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    names += [x.arg for x in a.kwonlyargs]
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    pre = "async " if isinstance(fn, ast.AsyncFunctionDef) else ""
    return f"{pre}{fn.name}({', '.join(names)})"


# ---------------- python
for f in sorted(list((root / "backend/app").rglob("*.py")) + list((root / "backend/ml").glob("*.py"))):
    if "__pycache__" in f.parts or f.name == "__init__.py":
        continue
    rel = f.relative_to(root).as_posix()
    tree = ast.parse(f.read_text(encoding="utf-8"))
    prefix = ""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "APIRouter":
            for k in n.keywords:
                if k.arg == "prefix":
                    prefix = k.value.value
    entries = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            entries.append({"kind": "class", "name": n.name, "line": n.lineno, "doc": doc1(n)})
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entries.append({"kind": "method", "name": sig(m), "line": m.lineno, "doc": doc1(m)})
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            entries.append({"kind": "func", "name": sig(n), "line": n.lineno, "doc": doc1(n)})
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("get", "post", "put", "patch", "delete") \
                        and getattr(d.func.value, "id", "") in ("router", "app") and d.args:
                    out["routes"].append({"method": d.func.attr.upper(), "path": prefix + d.args[0].value,
                                          "handler": n.name, "file": f.name, "line": n.lineno})
    out["python"].append({"file": rel, "doc": doc1(tree), "entries": entries})

# ---------------- dart
cls_re = re.compile(r"^\s*(?:abstract\s+|sealed\s+|final\s+)*(class|enum|mixin|extension)\s+(\w+)")
mem_re = re.compile(r"^\s{2}(?:@override\s+)?(?:static\s+|final\s+|const\s+|factory\s+|Future<[^>]*>\s+|[\w<>?,\[\] ]+\s+)?(get\s+)?([_a-zA-Z]\w*)\s*(\(|=>|\{)")
top_re = re.compile(r"^(?:Future<[^>]*>|[\w<>?,]+)\s+([_a-zA-Z]\w*)\s*\(")
skip = {"if", "for", "while", "switch", "return", "super", "this", "catch", "setState", "assert"}
for f in sorted((root / "frontend/lib").rglob("*.dart")):
    rel = f.relative_to(root).as_posix()
    entries = []
    lines = f.read_text(encoding="utf-8").splitlines()
    comment = ""
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("///"):
            comment = (comment + " " + s[3:].strip()).strip()
            continue
        m = cls_re.match(ln)
        if m and not ln.startswith("  "):
            entries.append({"kind": m.group(1), "name": m.group(2), "line": i, "doc": comment[:200]})
        elif ln.startswith("  ") and not ln.startswith("   ") and (mm := mem_re.match(ln)) and mm.group(2) not in skip:
            entries.append({"kind": "getter" if mm.group(1) else "member", "name": mm.group(2), "line": i, "doc": comment[:200]})
        elif not ln.startswith(" ") and (mt := top_re.match(ln)) and mt.group(1) not in skip:
            entries.append({"kind": "top", "name": mt.group(1), "line": i, "doc": comment[:200]})
        if s and not s.startswith("@"):
            comment = ""
    out["dart"].append({"file": rel, "entries": entries})

out["routes"].sort(key=lambda r: (r["path"], r["method"]))
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
print("routes", len(out["routes"]), "py files", len(out["python"]), "py decls", sum(len(x["entries"]) for x in out["python"]),
      "dart files", len(out["dart"]), "dart classes", sum(1 for x in out["dart"] for e in x["entries"] if e["kind"] in ("class", "enum", "mixin", "extension")),
      "dart members", sum(1 for x in out["dart"] for e in x["entries"] if e["kind"] not in ("class", "enum", "mixin", "extension")))
