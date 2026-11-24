"""Аутентификация, серверные сессии, CSRF, разграничение доступа, заголовки безопасности."""
import functools
import hmac
import re
import time

from flask import abort, g, jsonify, redirect, request, url_for, flash
from werkzeug.serving import WSGIRequestHandler

from . import config, crypto
from .db import execute, query, audit

# ---------------------------------------------------------------- политика паролей
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def password_problems(pw: str):
    problems = []
    if len(pw) < config.PASSWORD_MIN_LEN:
        problems.append(f"не менее {config.PASSWORD_MIN_LEN} символов")
    if len(pw) > 128:
        problems.append("не более 128 символов")
    if not re.search(r"[a-zа-яё]", pw):
        problems.append("строчная буква")
    if not re.search(r"[A-ZА-ЯЁ]", pw):
        problems.append("заглавная буква")
    if not re.search(r"\d", pw):
        problems.append("цифра")
    return problems


# ---------------------------------------------------------------- сессии
def _client_ip():
    return request.remote_addr or "-"


def _create_session(user_id=None):
    token = crypto.new_token()
    now = time.time()
    execute("INSERT INTO sessions(token_hash, user_id, csrf_token, created_at, last_activity, ip, user_agent)"
            " VALUES (?,?,?,?,?,?,?)",
            (crypto.token_hash(token), user_id, crypto.new_token(), now, now,
             _client_ip(), (request.user_agent.string or "")[:200]))
    g.new_session_token = token
    return _load(token)


def _load(token):
    if not token:
        return None
    return query("SELECT s.*, u.login, u.is_active, r.code AS role, r.name AS role_name "
                 "FROM sessions s LEFT JOIN users u ON u.id = s.user_id "
                 "LEFT JOIN roles r ON r.id = u.role_id WHERE s.token_hash = ?",
                 (crypto.token_hash(token),), one=True)


def _destroy(token_hash):
    execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


_last_cleanup = [0.0]


def load_session():
    """Вызывается перед каждым запросом."""
    if time.time() - _last_cleanup[0] > 300:          # раз в 5 минут — удаление просроченных сессий
        _last_cleanup[0] = time.time()
        cleanup_sessions()
    g.session = None
    g.user = None
    g.session_expired = False
    token = request.cookies.get(config.SESSION_COOKIE)
    s = _load(token)
    now = time.time()
    if s is not None:
        expired = (now - s["last_activity"] > config.SESSION_IDLE_TIMEOUT or
                   now - s["created_at"] > config.SESSION_ABSOLUTE_TIMEOUT)
        if expired or (s["user_id"] is not None and not s["is_active"]):
            g.session_expired = s["user_id"] is not None
            _destroy(s["token_hash"])
            s = None
        elif now - s["last_activity"] > 30:      # запись не чаще раза в 30 с — меньше блокировок БД
            execute("UPDATE sessions SET last_activity=? WHERE token_hash=?", (now, s["token_hash"]))
    if s is None:
        s = _create_session(None)        # гостевая сессия — нужна для CSRF-токена формы входа
    g.session = s
    if s["user_id"] is not None:
        g.user = {"id": s["user_id"], "login": s["login"], "role": s["role"], "role_name": s["role_name"]}


def set_cookie(response):
    token = g.pop("new_session_token", None)
    if token:
        response.set_cookie(config.SESSION_COOKIE, token, httponly=True, secure=True,
                            samesite="Strict", path="/", max_age=config.SESSION_ABSOLUTE_TIMEOUT)
    if getattr(g, "clear_cookie", False):
        response.delete_cookie(config.SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="Strict")
    return response


def csrf_token():
    return g.session["csrf_token"] if g.get("session") else ""


def check_csrf():
    """Проверка CSRF-токена для всех запросов, изменяющих состояние."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
        if not g.session or not hmac.compare_digest(sent, g.session["csrf_token"]):
            audit("csrf_reject", ip=_client_ip(), user_id=g.user["id"] if g.user else None)
            abort(403)


# ---------------------------------------------------------------- вход / выход
def is_locked(login):
    since = time.time() - config.ATTEMPT_WINDOW_SEC
    rows = query("SELECT ts, success FROM login_attempts WHERE login=? AND ts>=? ORDER BY ts DESC",
                 (login.lower(), since))
    fails = []
    for r in rows:
        if r["success"]:
            break
        fails.append(r["ts"])
    if len(fails) >= config.MAX_FAILED_ATTEMPTS:
        remaining = int(fails[0] + config.LOCKOUT_SEC - time.time())
        if remaining > 0:
            return remaining
    return 0


def authenticate(login, password):
    """Возвращает (user_row | None, сообщение_об_ошибке)."""
    login_n = login.strip().lower()
    locked = is_locked(login_n)
    if locked:
        return None, f"Слишком много неудачных попыток. Вход заблокирован на {locked // 60 + 1} мин."
    user = query("SELECT u.*, r.code AS role FROM users u JOIN roles r ON r.id=u.role_id "
                 "WHERE lower(u.login)=?", (login_n,), one=True)
    ok = crypto.verify_password(password, user["password_hash"] if user else crypto.DUMMY_HASH)
    ok = ok and user is not None and user["is_active"] == 1
    execute("INSERT INTO login_attempts(login, ip, ts, success) VALUES (?,?,?,?)",
            (login_n, _client_ip(), time.time(), 1 if ok else 0))
    if not ok:
        audit("login_failed", ip=_client_ip())
        if is_locked(login_n):
            return None, "Слишком много неудачных попыток. Вход временно заблокирован на 5 мин."
        return None, "Неверный логин или пароль."
    return user, None


def login_user(user):
    """Смена идентификатора сессии после входа (защита от фиксации сессии)."""
    if g.session:
        _destroy(g.session["token_hash"])
    g.session = _create_session(user["id"])
    g.user = {"id": user["id"], "login": user["login"], "role": g.session["role"],
              "role_name": g.session["role_name"]}
    audit("login", user_id=user["id"], ip=_client_ip())


def logout_user():
    if g.session:
        if g.user:
            audit("logout", user_id=g.user["id"], ip=_client_ip())
        _destroy(g.session["token_hash"])
    g.user = None
    g.session = _create_session(None)


def cleanup_sessions():
    now = time.time()
    execute("DELETE FROM sessions WHERE last_activity < ? OR created_at < ?",
            (now - config.SESSION_IDLE_TIMEOUT, now - config.SESSION_ABSOLUTE_TIMEOUT))
    execute("DELETE FROM login_attempts WHERE ts < ?", (now - 30 * 24 * 3600,))   # журнал попыток — 30 дней


# ---------------------------------------------------------------- декораторы доступа
def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Требуется авторизация"), 401
            flash("Сессия завершена по тайм-ауту. Войдите снова." if g.session_expired
                  else "Для доступа к странице необходимо войти в систему.", "warning")
            return redirect(url_for("main.index"))
        return view(*a, **kw)
    return wrapped


def roles_required(*roles):
    def deco(view):
        @functools.wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return login_required(view)(*a, **kw)
            if g.user["role"] not in roles:
                audit("access_denied", entity=request.path[:100], user_id=g.user["id"], ip=_client_ip())
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


# ---------------------------------------------------------------- заголовки
# сервер не сообщает версии ПО (Werkzeug/Python) в заголовке Server
WSGIRequestHandler.server_version = "AIS"
WSGIRequestHandler.sys_version = ""

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'none'")


def security_headers(response):
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if response.mimetype in ("text/html", "application/json"):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["Cache-Control"] = "no-store"
    return response
