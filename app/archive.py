"""Файловый архив (страница 3). Файлы хранятся вне корня сайта и выдаются только
через этот обработчик после проверки сессии. Доступны лишь файлы из манифеста
(белый список); прямые пути, «../» и листинг каталогов невозможны."""
import json
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, flash, g, redirect, request, send_file, url_for

from . import config
from .db import audit
from .security import login_required, roles_required

bp = Blueprint("files", __name__)

MANIFEST = config.ARCHIVE_DIR / "manifest.json"
FORBIDDEN_DIRS = {"instance", "certs", "backups", ".git"}
GROUP_ORDER = ["Графические файлы", "Документация", "Текстовые файлы", "Исходный код",
               "Криптографические функции", "Загруженные файлы"]
TEXT_EXT = {".py", ".sql", ".md", ".txt", ".js", ".css", ".html", ".json", ".cfg", ".ini"}
FORMATS = {".svg": "SVG", ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".pdf": "PDF", ".docx": "DOCX",
           ".pptx": "PPTX", ".py": "Python", ".sql": "SQL", ".md": "Markdown", ".txt": "TXT", ".js": "JavaScript",
           ".css": "CSS", ".html": "HTML", ".json": "JSON", ".zip": "ZIP"}


def _safe_path(rel):
    p = (config.BASE_DIR / rel).resolve()
    if config.BASE_DIR.resolve() not in p.parents or p.parts[len(config.BASE_DIR.resolve().parts)] in FORBIDDEN_DIRS:
        return None
    return p if p.is_file() else None


def _human(n):
    for unit in ("Б", "КБ", "МБ"):
        if n < 1024 or unit == "МБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024


def _uploads():
    out = []
    for meta in sorted(config.UPLOAD_DIR.glob("*.json")):
        try:
            m = json.loads(meta.read_text("utf-8"))
        except ValueError:
            continue
        out.append({"id": "u-" + m["stored"].split(".")[0], "group": "Загруженные файлы",
                    "path": str((config.UPLOAD_DIR / m["stored"]).relative_to(config.BASE_DIR)),
                    "name": m["original"], "description": m.get("description") or "Файл, загруженный администратором"})
    return out


def entries():
    items = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else []
    items += _uploads()
    result = []
    for it in items:
        p = _safe_path(it["path"])
        if not p:                       # отсутствующие файлы не показываются → нет «битых» ссылок
            continue
        st = p.stat()
        ext = p.suffix.lower()
        result.append({**it, "name": it.get("name") or p.name, "format": FORMATS.get(ext, ext[1:].upper()),
                       "size": _human(st.st_size), "bytes": st.st_size,
                       "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M"),
                       "viewable": ext in TEXT_EXT or ext in (".svg", ".png", ".jpg", ".jpeg", ".pdf")})
    groups = {}
    for e in result:
        groups.setdefault(e["group"], []).append(e)
    return [(gname, groups[gname]) for gname in GROUP_ORDER if gname in groups] + \
           [(k, v) for k, v in groups.items() if k not in GROUP_ORDER]


def find(fid):
    for _, items in entries():
        for e in items:
            if e["id"] == fid:
                return e
    return None


@bp.get("/files/<fid>")
@login_required
def get_file(fid):
    e = find(fid)
    if not e:
        abort(404)
    p = _safe_path(e["path"])
    download = request.args.get("download") == "1"
    ext = p.suffix.lower()
    mime = "text/plain; charset=utf-8" if ext in TEXT_EXT else (mimetypes.guess_type(p.name)[0] or "application/octet-stream")
    audit("file_download" if download else "file_view", "file", None, g.user["id"], request.remote_addr)
    resp = send_file(p, mimetype=mime, as_attachment=download, download_name=e["name"], max_age=0)
    # файл открывается в «песочнице»: скрипты внутри SVG/HTML не выполняются
    resp.headers["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.post("/files/upload")
@roles_required("admin")
def upload():
    f = request.files.get("file")
    desc = (request.form.get("description") or "").strip()[:200].replace("<", "").replace(">", "")
    if not f or not f.filename:
        flash("Выберите файл для загрузки.", "error")
        return redirect(url_for("main.archive"))
    ext = Path(f.filename).suffix.lower()
    if ext not in config.ALLOWED_UPLOAD:
        flash("Недопустимое расширение. Разрешены: PNG, JPEG, PDF.", "error")
        return redirect(url_for("main.archive"))
    data = f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        flash("Файл больше 5 МБ.", "error")
        return redirect(url_for("main.archive"))
    mime, magic = config.ALLOWED_UPLOAD[ext]
    if (f.mimetype or "") not in (mime, "application/octet-stream"):
        flash("Тип файла (MIME) не соответствует расширению.", "error")
        return redirect(url_for("main.archive"))
    if not data.startswith(magic):
        flash("Содержимое файла не соответствует его расширению.", "error")
        return redirect(url_for("main.archive"))
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = uuid.uuid4().hex + ext                       # имя на сервере генерируется, а не берётся от клиента
    (config.UPLOAD_DIR / stored).write_bytes(data)
    original = "".join(ch for ch in Path(f.filename).name if ch.isalnum() or ch in "._- ")[:100] or stored
    (config.UPLOAD_DIR / (stored.split(".")[0] + ".json")).write_text(
        json.dumps({"stored": stored, "original": original, "mime": mime, "description": desc}, ensure_ascii=False),
        "utf-8")
    audit("upload", "file", None, g.user["id"], request.remote_addr)
    flash(f"Файл «{original}» загружен.", "success")
    return redirect(url_for("main.archive"))


@bp.post("/files/<fid>/delete")
@roles_required("admin")
def delete_upload(fid):
    if not fid.startswith("u-") or not all(c in "0123456789abcdef" for c in fid[2:]):
        abort(404)
    for p in config.UPLOAD_DIR.glob(fid[2:] + ".*"):
        p.unlink()
    audit("delete", "file", None, g.user["id"], request.remote_addr)
    flash("Файл удалён.", "success")
    return redirect(url_for("main.archive"))
