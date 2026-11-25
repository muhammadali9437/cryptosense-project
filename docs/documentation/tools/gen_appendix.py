"""Writes the source-derived appendix (routes, Python catalog, Dart catalog) as LaTeX.
usage: python gen_appendix.py inventory.json out_dir"""
import json
import re
import sys
from pathlib import Path

inv = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = Path(sys.argv[2])

ESC = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "_": r"\_", "&": r"\&", "%": r"\%",
       "#": r"\#", "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def esc(s):
    s = "".join(ESC.get(c, c) for c in s)
    s = s.replace("->", r"$\rightarrow$").replace("<", r"\textless{}").replace(">", r"\textgreater{}")
    s = s.replace("“", "``").replace("”", "''").replace("’", "'").replace("—", "--").replace("–", "--")
    s = s.replace("…", "...").replace("≥", r"$\geq$").replace("≤", r"$\leq$").replace("×", r"$\times$")
    return "".join(c if ord(c) < 128 or c.isalpha() else "" for c in s)


def code(s):
    t = esc(s)
    for a in (r"\_", ",", "/", "(", "."):
        t = t.replace(a, a + r"\allowbreak{}")
    return r"\texttt{" + t + "}"


# --------------------------------------------------------------- routes table (used twice)
rows = []
for r in inv["routes"]:
    rows.append(rf"{r['method']} & {code(r['path'])} & {code(r['handler'])} ({esc(r['file'])}:{r['line']})\\\hline")
routes = "\n".join(rows)
(out / "routes_table.tex").write_text(
    r"""{\renewcommand{\arraystretch}{1.25}\small
\begin{longtable}{|>{\centering\arraybackslash}p{0.11\linewidth}|p{0.42\linewidth}|p{0.37\linewidth}|}
\caption{\routecaption}\\\hline\textbf{HTTP} & \textbf{Path} & \textbf{Handler / Source}\\\hline\endfirsthead
\multicolumn{3}{c}{\small\textit{Table \thetable{} -- continued from previous page}}\\\hline
\textbf{HTTP} & \textbf{Path} & \textbf{Handler / Source}\\\hline\endhead
""" + routes + "\n\\end{longtable}}\n", encoding="utf-8")

# --------------------------------------------------------------- python catalog
py = []
n_py = 0
for f in inv["python"]:
    if not f["entries"]:
        continue
    py.append(r"\subsubsection*{" + esc(f["file"]) + "}")
    if f["doc"]:
        py.append(r"\textit{" + esc(f["doc"]) + "}")
    py.append(r"\begin{itemize}[nosep,leftmargin=1.5em]")
    for e in f["entries"]:
        n_py += 1
        d = (" " + esc(e["doc"])) if e["doc"] else ""
        if e["kind"] == "class":
            py.append(rf"\item \textbf{{Class}} {code(e['name'])} --- Line {e['line']}.{d}")
        else:
            ind = r"\hspace*{1em}" if e["kind"] == "method" else ""
            py.append(rf"\item {ind}{code(e['name'])} --- Line {e['line']}.{d}")
    py.append(r"\end{itemize}")

# --------------------------------------------------------------- dart catalog
CLS = ("class", "enum", "mixin", "extension")
da = []
n_cls = n_mem = 0
for f in inv["dart"]:
    if not f["entries"]:
        continue
    da.append(r"\subsubsection*{" + esc(f["file"]) + "}")
    da.append(r"\begin{itemize}[nosep,leftmargin=1.5em]")
    cur = None
    members = []

    def flush():
        if cur is not None:
            m = ", ".join(f"{code(x['name'] + ('()' if x['kind'] != 'getter' else ''))} ({x['line']})" for x in members)
            doc = (" " + esc(cur["doc"])) if cur["doc"] else ""
            da.append(rf"\item \textbf{{{cur['kind'].capitalize()}}} {code(cur['name'])} --- Line {cur['line']}.{doc}"
                      + (rf" Members: {m}." if m else ""))

    tops = []
    for e in f["entries"]:
        if e["kind"] in CLS:
            flush()
            cur, members = e, []
            n_cls += 1
        elif e["kind"] == "top":
            tops.append(e)
            n_mem += 1
        elif cur is not None and e["name"] != cur["name"]:
            members.append(e)
            n_mem += 1
    flush()
    for t in tops:
        doc = (" " + esc(t["doc"])) if t["doc"] else ""
        da.append(rf"\item Top-level {code(t['name'] + '()')} --- Line {t['line']}.{doc}")
    da.append(r"\end{itemize}")

n_dart_files = sum(1 for f in inv["dart"] if f["entries"])
n_py_files = sum(1 for f in inv["python"] if f["entries"])
(out / "catalog_python.tex").write_text("\n".join(py) + f"\n\\subsection{{Python Inventory Summary}}\nA total of {n_py} "
    f"class, function and method declarations were indexed in {n_py_files} files across \\texttt{{backend/app}} and "
    "\\texttt{backend/ml} with Python's \\texttt{ast} module. Descriptions are the first sentence of each docstring; "
    "entries without a docstring list only their source line.\n", encoding="utf-8")
(out / "catalog_dart.tex").write_text("\n".join(da) + f"\n\\subsection{{Dart Inventory Summary}}\nThe source index reports "
    f"{n_cls} classes, enums and extensions and {n_mem} detected members and top-level functions across {n_dart_files} "
    "Dart files. Some expression-bodied declarations may not be detected by this lightweight index; the original source "
    "remains authoritative.\n", encoding="utf-8")
print("routes", len(inv["routes"]), "py", n_py, n_py_files, "dart", n_cls, n_mem, n_dart_files)
