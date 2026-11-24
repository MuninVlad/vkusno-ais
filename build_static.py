"""Сборка версии сайта для GitHub Pages (папка docs/ — GitHub Pages публикует её из ветки main).

Страница 1 — открытая. Страницы 2–3, файлы архива и база данных шифруются
AES-256-GCM ключом данных DK. DK хранится только «обёрнутым» паролем каждого
пользователя (PBKDF2-HMAC-SHA256, 600 000 итераций). Без входа по прямой ссылке
доступен только шифртекст.

    python build_static.py
"""
import base64
import hashlib
import json
import re
import secrets
import shutil
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jinja2 import Environment, FileSystemLoader

import init_db
from app import accounts, config, content, create_app, crypto
from app.api import ENTITIES

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"
SRC = ROOT / "static_src"
ITER = 600_000


def seal(key, data: bytes, aad: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, data, aad.encode())


def export_db():
    con = sqlite3.connect(str(config.DB_PATH))
    con.row_factory = sqlite3.Row
    db = {}
    for t in ("roles", "restaurants", "positions", "categories", "menu_items", "employees", "customers", "orders", "order_items", "users"):
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
        for r in rows:
            for col, name in (("phone_enc", "phone"), ("email_enc", "email")):
                if col in r:
                    r[name] = crypto.decrypt_field(r.pop(col), f"{t}.{col}")
            r.pop("phone_hmac", None)
            r.pop("password_hash", None)
        db[t] = rows
    db["seq"] = {t: max([r["id"] for r in db[t]] or [0]) for t in db if t not in ("order_items",)}
    db["audit_log"] = []
    db["meta"] = {"entities": {k: {"title": s["title"], "perms": {a: list(r) for a, r in s["perms"].items()},
                                   "fields": {n: {kk: vv for kk, vv in f.items() if kk not in ("encrypted", "blind_index")}
                                              for n, f in s["fields"].items()},
                                   "filters": list(s["filters"].keys())} for k, s in ENTITIES.items()}}
    return db


def render_secure(app, path, files):
    """Страница сервера (вход под администратором) → содержимое для шифрования."""
    c = app.test_client()
    page = c.get("/", base_url="https://localhost").get_data(as_text=True)
    tok = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
    c.post("/login", data={"login": "admin", "password": accounts.passwords()["admin"], "csrf_token": tok}, base_url="https://localhost")
    html = c.get(path, base_url="https://localhost").get_data(as_text=True)
    html = html.split('<main id="content" class="wrap">', 1)[1].split("</main>", 1)[0]
    html = re.sub(r'<div class="flashes">.*?</div>\s*</div>', "", html, count=1, flags=re.S)

    def link(m):
        fid, dl = m.group(1), m.group(2)
        return f'href="#" data-file="{fid}" data-name="{files[fid]}" data-act="{"download" if dl else "view"}"'
    html = re.sub(r'href="/files/([^"?]+)(\?download=1)?"(?: target="_blank" rel="noopener")?', link, html)
    html = re.sub(r'src="/files/([^"]+)"', lambda m: f'data-file="{m.group(1)}" data-name="{files[m.group(1)]}"', html)
    return html


STATIC_NOTE = """
  <h3 id="pages">6.5. Размещение на GitHub Pages</h3>
  <p>Опубликованная на GitHub Pages версия сайта работает без серверной части, поэтому меры защиты реализованы в браузере средствами Web Crypto API:</p>
  <ul>
    <li><b>Страницы 2 и 3, все файлы архива и база данных</b> хранятся на хостинге только в зашифрованном виде (AES-256-GCM, ключ данных 256 бит). По прямой ссылке без входа доступен лишь шифртекст.</li>
    <li><b>Ключ данных</b> хранится «обёрнутым» отдельно для каждого пользователя: ключ обёртки выводится из пароля функцией PBKDF2-HMAC-SHA256 (600 000 итераций, соль 128 бит). Пароли не хранятся ни в каком виде: верный пароль — это успешная расшифровка профиля (проверка тега GCM).</li>
    <li><b>Канал связи</b> защищает GitHub Pages: HTTPS (TLS 1.2+), заголовок HSTS. Политика CSP задана в каждой странице.</li>
    <li><b>Сессия</b> хранится в sessionStorage вкладки: тайм-аут бездействия 15 минут, «Выход» удаляет ключ из памяти.</li>
    <li><b>Изменения данных</b> в рабочем модуле сохраняются в браузере пользователя в зашифрованном виде.</li>
  </ul>
  <p><b>Ограничение статического размещения:</b> разграничение прав ролей и ограничение числа попыток входа выполняются в браузере. Знающий пользователь может обойти их через инструменты разработчика, но без пароля не получит доступа к данным. Серверная проверка прав при каждом запросе, CSRF-токены, cookie HttpOnly/Secure/SameSite и серверная блокировка подбора реализованы в серверной части системы: её исходный код находится в этом же репозитории GitHub и в архиве исходного кода (страница 3).</p>
"""


def main():
    if not config.DB_PATH.exists():
        init_db.main()
    if OUT.exists():
        shutil.rmtree(OUT)
    for d in ("assets/css", "assets/js", "assets/img", "data", "files"):
        (OUT / d).mkdir(parents=True, exist_ok=True)

    dk = secrets.token_bytes(32)
    build = secrets.token_hex(8)
    manifest = json.loads((config.ARCHIVE_DIR / "manifest.json").read_text("utf-8"))
    files = {e["id"]: Path(e["path"]).name for e in manifest}

    # файлы архива
    for e in manifest:
        (OUT / "files" / f"{e['id']}.enc").write_bytes(seal(dk, (ROOT / e["path"]).read_bytes(), "file:" + e["id"]))

    # страницы 2 и 3
    app = create_app(testing=True)
    p2 = render_secure(app, "/system", files)
    p2 = p2.replace('<li><a href="#backup">Резервное копирование</a></li></ol></li>',
                    '<li><a href="#backup">Резервное копирование</a></li><li><a href="#pages">Размещение на GitHub Pages</a></li></ol></li>')
    p2 = p2.replace('<!-- ================================================================ 7 Реализация -->',
                    STATIC_NOTE.replace("\n  <h3", '\n<section class="doc" id="sec-pages">\n  <h3', 1) + "</section>\n"
                    "<!-- ================================================================ 7 Реализация -->")
    p2 = re.sub(r'<p class="muted">Работа с базой данных в соответствии с правами роли.*?</p>',
                '<p class="muted">Работа с данными в соответствии с правами роли «<span data-user-role></span>». Недоступные разделы не отображаются. '
                'В версии для GitHub Pages данные обрабатываются в браузере и хранятся в зашифрованном виде (см. п. 6.5).</p>', p2, flags=re.S)
    p3 = render_secure(app, "/archive", files)
    p3 = re.sub(r'<section class="card" id="upload">.*?</section>', "", p3, flags=re.S)
    p3 = re.sub(r'<p class="muted">Все файлы выдаются через.*?</p>',
                '<p class="muted">Файлы хранятся на хостинге в зашифрованном виде (AES-256-GCM) и расшифровываются в браузере только после входа. '
                '«Открыть» показывает файл в новой вкладке, «Скачать» сохраняет его на компьютер.</p>', p3, flags=re.S)
    (OUT / "data" / "page2.enc").write_bytes(seal(dk, p2.encode(), "page2"))
    (OUT / "data" / "page3.enc").write_bytes(seal(dk, p3.encode(), "page3"))

    # база данных
    (OUT / "data" / "db.enc").write_bytes(seal(dk, json.dumps(export_db(), ensure_ascii=False).encode(), "db"))

    # пользователи: ключ данных, обёрнутый паролем каждого пользователя
    users = {}
    for login, pw in accounts.passwords().items():
        salt = secrets.token_bytes(16)
        kek = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER, dklen=32)
        blob = seal(kek, json.dumps({"login": login.lower(), "dk": base64.b64encode(dk).decode()}).encode(), "user:" + login.lower())
        users[hashlib.sha256(login.lower().encode()).hexdigest()] = {
            "salt": base64.b64encode(salt).decode(), "iter": ITER, "blob": base64.b64encode(blob).decode()}
    (OUT / "data" / "users.json").write_text(json.dumps({"build": build, "users": users}, indent=1), "utf-8")

    # страницы
    env = Environment(loader=FileSystemLoader(str(SRC / "templates")), autoescape=True)
    ctx = {"cfg": config, "c": content}
    (OUT / "index.html").write_text(env.get_template("index.html").render(page="index", **ctx), "utf-8")
    (OUT / "system.html").write_text(env.get_template("page.html").render(
        page="system", title="Описание системы", src="data/page2.enc", aad="page2", **ctx), "utf-8")
    (OUT / "archive.html").write_text(env.get_template("page.html").render(
        page="archive", title="Файловый архив", src="data/page3.enc", aad="page3", **ctx), "utf-8")

    # ресурсы
    shutil.copy(ROOT / "static/css/style.css", OUT / "assets/css/style.css")
    shutil.copy(ROOT / "static/img/logo.svg", OUT / "assets/img/logo.svg")
    for js in ("auth.js", "store.js", "localapi.js", "app.js"):
        shutil.copy(SRC / "js" / js, OUT / "assets/js" / js)
    module = (ROOT / "static/js/module.js").read_text("utf-8")
    start = module.index("  function api(method, url, body) {")
    end = module.index("  function toast(")
    module = module[:start] + '''  function api(method, url, body) {          // запросы обрабатываются в браузере (localapi.js)
    return window.VBLocal.request(method, url, body).then(function (r) {
      if (window.__vbTouch) window.__vbTouch();
      if (r.status === 401) { window.location.href = "index.html"; throw new Error("auth"); }
      var d = r.data || {}; d.__status = r.status; return d;
    });
  }
''' + module[end:]
    module = module.replace('document.querySelector(\'meta[name="csrf-token"]\').getAttribute("content")', '""')
    (OUT / "assets/js/module.js").write_text(module, "utf-8")
    (OUT / ".nojekyll").write_text("", "utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"Готово: {OUT} ({n} файлов), сборка {build}")


if __name__ == "__main__":
    main()
