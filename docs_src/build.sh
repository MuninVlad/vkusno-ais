#!/bin/sh
# Сборка документов: данные → DOCX (проход 1) → PDF → номера страниц → DOCX (проход 2)
set -e
cd "$(dirname "$0")/.."
python3 docs_src/export_data.py
export NODE_PATH=$(npm root -g)
rm -f docs_src/.build/toc.json
node docs_src/build_docs.js
D=docs_src/.build; cp storage/archive/docs/02_*.docx "$D/pz.docx"
(cd "$D" && soffice --headless --convert-to pdf pz.docx >/dev/null 2>&1)
python3 docs_src/toc_pages.py "$D/pz.pdf"
node docs_src/build_docs.js docs_src/.build/toc.json
for f in storage/archive/docs/*.docx; do zip -d "$f" '*/' >/dev/null 2>&1 || true; done
