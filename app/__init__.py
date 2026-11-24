"""Фабрика приложения Flask."""
import json
import logging

from flask import Flask, Blueprint, flash, g, redirect, render_template, request, url_for, jsonify

from . import config, security, content
from .db import close_db, query
from .security import login_required

main = Blueprint("main", __name__)


@main.get("/")
def index():
    if g.get("session_expired"):
        flash("Сессия завершена по тайм-ауту. Войдите снова.", "warning")
    return render_template("index.html", page="index")


@main.post("/login")
def login():
    login_v = (request.form.get("login") or "").strip()
    password = request.form.get("password") or ""
    errors = []
    if not security.LOGIN_RE.match(login_v):
        errors.append("Логин: 3–32 символа (латиница, цифры, _ . -).")
    if not 1 <= len(password) <= 128:
        errors.append("Введите пароль (до 128 символов).")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("index.html", page="index", form_login=login_v), 400
    user, err = security.authenticate(login_v, password)
    if not user:
        flash(err, "error")
        return render_template("index.html", page="index", form_login=login_v), 401
    security.login_user(user)
    flash(f"Добро пожаловать, {user['login']}!", "success")
    return redirect(url_for("main.index"))


@main.post("/logout")
def logout():
    security.logout_user()
    flash("Вы вышли из системы.", "success")
    return redirect(url_for("main.index"))


@main.get("/system")
@login_required
def system():
    results = {}
    path = config.BASE_DIR / "tests" / "results.json"
    if path.exists():
        results = json.loads(path.read_text("utf-8"))
    counts = {k: query(f"SELECT COUNT(*) AS n FROM {k}", one=True)["n"] for k in
              ("restaurants", "positions", "categories", "employees", "menu_items", "customers", "orders", "order_items", "users")}
    return render_template("system.html", page="system", results=results, counts=counts, schema=schema_info(), perms=perms_matrix())


def perms_matrix():
    from .api import ENTITIES
    rows = []
    for e in ENTITIES.values():
        row = []
        for role in ("admin", "manager", "cashier"):
            letters = "".join(letter for a, letter in (("read", "Ч"), ("create", "Д"), ("update", "И"), ("delete", "У"))
                              if role in e["perms"][a])
            row.append(letters or "—")
        rows.append((e["title"], row))
    rows.insert(0, ("Заказы", ["ЧДИУ", "ЧДИУ", "ЧДИ"]))
    rows.append(("Отчёты (кассиры — только админ./управл.)", ["Ч", "Ч", "Ч (4 из 5)"]))
    rows.append(("Файловый архив (загрузка — админ.)", ["ЧДУ", "Ч", "Ч"]))
    return rows


def schema_info():
    """Даталогическая модель, извлечённая из самой БД (всегда соответствует реальной структуре)."""
    import re
    tables = []
    for t in query("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"):
        fks = {r["from"]: f'{r["table"]}({r["to"]})' for r in query(f'PRAGMA foreign_key_list("{t["name"]}")')}
        uniques = set()
        for idx in query(f'PRAGMA index_list("{t["name"]}")'):
            if idx["unique"] and idx["origin"] == "u":
                cols = [c["name"] for c in query(f'PRAGMA index_info("{idx["name"]}")')]
                if len(cols) == 1:
                    uniques.add(cols[0])
        pk_cols = [c["name"] for c in query(f'PRAGMA table_info("{t["name"]}")') if c["pk"]]
        cols = []
        for c in query(f'PRAGMA table_info("{t["name"]}")'):
            cons = []
            if c["pk"]:
                cons.append("PK" + (" (составной)" if len(pk_cols) > 1 else ""))
            if c["name"] in fks:
                cons.append("FK → " + fks[c["name"]])
            if c["notnull"] or c["pk"]:
                cons.append("NOT NULL")
            if c["name"] in uniques:
                cons.append("UNIQUE")
            if c["dflt_value"] is not None:
                cons.append("DEFAULT " + c["dflt_value"])
            m = re.search(r"^\s*" + re.escape(c["name"]) + r"\b[^\n]*?CHECK\s*\((.*)\)\s*,?\s*(--.*)?$", t["sql"], re.M)
            if m:
                cons.append("CHECK (" + m.group(1).strip().rstrip(",") + ")")
            cols.append({"name": c["name"], "type": c["type"], "cons": cons,
                         "note": content.FIELD_NOTES.get(c["name"], "")})
        tables.append({"name": t["name"], "title": content.DATA_MODEL_NOTES.get(t["name"], ""), "cols": cols})
    return tables


@main.get("/archive")
@login_required
def archive():
    from .archive import entries
    return render_template("archive.html", page="archive", groups=entries())


def create_app(testing=False):
    app = Flask(__name__, template_folder=str(config.BASE_DIR / "templates"),
                static_folder=str(config.BASE_DIR / "static"))
    app.config.update(SECRET_KEY=security.crypto.new_token(),   # нужен только для flash-сообщений
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True,
                      SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=config.MAX_UPLOAD_BYTES + 64 * 1024,
                      TESTING=testing, DEBUG=config.DEBUG, PROPAGATE_EXCEPTIONS=False,
                      JSON_AS_ASCII=False)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    from .api import bp as api_bp
    from .reports import bp as reports_bp
    from .archive import bp as files_bp
    app.register_blueprint(main)
    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(files_bp)

    @app.before_request
    def _before():
        if request.endpoint == "static":
            return None
        security.load_session()
        security.check_csrf()

    @app.after_request
    def _after(resp):
        security.set_cookie(resp)
        return security.security_headers(resp)

    app.teardown_appcontext(close_db)

    @app.context_processor
    def _ctx():
        return {"cfg": config, "user": g.get("user"), "csrf_token": security.csrf_token, "c": content}

    def _err(code, title, text):
        def handler(e):
            if request.path.startswith("/api/"):
                return jsonify(error=title), code
            return render_template("error.html", code=code, title=title, text=text, page="error"), code
        return handler

    app.register_error_handler(400, _err(400, "Некорректный запрос", "Сервер не смог обработать запрос."))
    app.register_error_handler(403, _err(403, "Доступ запрещён", "Недостаточно прав или истёк защитный токен формы. Обновите страницу."))
    app.register_error_handler(404, _err(404, "Страница не найдена", "Проверьте адрес или вернитесь на главную."))
    app.register_error_handler(405, _err(405, "Метод не поддерживается", "Запрос этого типа не допускается."))
    app.register_error_handler(413, _err(413, "Слишком большой файл", "Максимальный размер файла — 5 МБ."))

    @app.errorhandler(Exception)
    def _unhandled(e):
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        app.logger.exception("Внутренняя ошибка")          # подробности — только в журнал сервера
        if request.path.startswith("/api/"):
            return jsonify(error="Внутренняя ошибка сервера"), 500
        return render_template("error.html", code=500, title="Внутренняя ошибка",
                               text="Произошла ошибка. Подробности записаны в журнал сервера.", page="error"), 500

    logging.basicConfig(filename=str(config.INSTANCE_DIR / "server.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    with app.app_context():
        security.cleanup_sessions()
    return app
