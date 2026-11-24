"""Сборка диаграмм: *.dot → Graphviz, *.mmd → Mermaid CLI, 14_timing — генерация SVG.
Результат: storage/archive/graphics/*.svg и *.png"""
import subprocess
import sys
import pathlib
SRC = pathlib.Path(__file__).parent
OUT = SRC.parent / "storage" / "archive" / "graphics"
OUT.mkdir(parents=True, exist_ok=True)
style = (SRC / "_style.inc").read_text()
only = sys.argv[1:]
for f in sorted(SRC.glob("*.dot")):
    if only and f.stem not in only:
        continue
    txt = f.read_text().replace("@STYLE@", style)
    for fmt in ("svg", "png"):
        args = ["dot", "-T" + fmt] + (["-Gdpi=150"] if fmt == "png" else []) + ["-o", str(OUT / f"{f.stem}.{fmt}")]
        r = subprocess.run(args, input=txt.encode(), capture_output=True)
        if r.returncode:
            print(f.name, r.stderr.decode()[:500])
    print("dot", f.stem)
for f in sorted(SRC.glob("*.mmd")):
    if only and f.stem not in only:
        continue
    for fmt in ("svg", "png"):
        extra = ["-s", "2"] if fmt == "png" else []
        r = subprocess.run(["mmdc", "-q", "-i", str(f), "-o", str(OUT / f"{f.stem}.{fmt}"), "-c", str(SRC / "mermaid.json"),
                            "-b", "white"] + extra, capture_output=True)
        if r.returncode:
            print(f.name, r.stderr.decode()[-800:])
    print("mmd", f.stem)
