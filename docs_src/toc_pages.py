"""Определение страниц заголовков по PDF (для статического содержания пояснительной записки)."""
import json
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent / ".build"


def norm(text):
    return " ".join(text.split())


def main(pdf):
    heads = json.loads((BUILD / "pz_heads.json").read_text("utf-8"))
    info = subprocess.check_output(["pdfinfo", pdf]).decode().splitlines()
    n = int(next(line for line in info if line.startswith("Pages")).split()[1])
    pages = [subprocess.check_output(["pdftotext", "-f", str(i), "-l", str(i), "-layout", pdf, "-"]).decode()
             for i in range(1, n + 1)]
    res, start = {}, 2          # титульный лист и содержание пропускаются
    for _level, title in heads:
        key = norm(title)[:40]
        for i in range(start, n):
            if key in norm(pages[i]):
                res[title] = i + 1
                start = i
                break
    (BUILD / "toc.json").write_text(json.dumps(res, ensure_ascii=False), "utf-8")
    print(len(res), "из", len(heads))


if __name__ == "__main__":
    main(sys.argv[1])
