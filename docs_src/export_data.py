"""Выгрузка данных для генерации документов (docs_src/build_docs.js)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = Path(__file__).resolve().parent / ".build"
sys.path.insert(0, str(ROOT))
from app import config, content, create_app  # noqa: E402 — путь к пакету добавляется выше

app = create_app(testing=True)
with app.app_context():
    from app import schema_info, perms_matrix
    from app.db import query
    schema = schema_info()
    perms = perms_matrix()
    counts = {k: query(f"SELECT COUNT(*) AS n FROM {k}", one=True)["n"] for k in
              ("restaurants", "positions", "categories", "employees", "menu_items", "customers", "orders", "order_items", "users")}

def size(p):
    w, h = subprocess.check_output(["identify", "-format", "%w %h", str(p)]).decode().split()
    return int(w), int(h)

figs = []
for f, cap, sect in content.FIGURES:
    png = ROOT / "storage/archive/graphics" / f.replace(".svg", ".png")
    w, h = size(png)
    figs.append({"png": str(png), "caption": cap, "sect": sect, "w": w, "h": h})
screens = []
for p in sorted((ROOT / "storage/archive/screens").glob("*.png")):
    w, h = size(p)
    screens.append({"name": p.stem, "png": str(p), "w": w, "h": h})
results = json.loads((ROOT / "tests/results.json").read_text("utf-8"))
data = {k: getattr(content, k) for k in dir(content) if k.isupper()}
data.update(schema=schema, perms=perms, counts=counts, figures=figs, screens=screens, results=results,
            schema_sql=(ROOT / "sql/schema.sql").read_text("utf-8"),
            student=config.STUDENT, group=config.GROUP, topic=config.TOPIC_NO, system=config.SYSTEM_FULL_NAME,
            security={"iters": config.PBKDF2_ITERATIONS, "attempts": config.MAX_FAILED_ATTEMPTS,
                      "lock": config.LOCKOUT_SEC // 60, "idle": config.SESSION_IDLE_TIMEOUT // 60})
BUILD.mkdir(exist_ok=True)
(BUILD / "docdata.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
print("ok", len(figs), len(screens))
