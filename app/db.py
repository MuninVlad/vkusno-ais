"""Доступ к БД. Используются только параметризованные запросы (защита от SQL-инъекций)."""
import sqlite3

from flask import g

from . import config


def connect(path=None):
    conn = sqlite3.connect(str(path or config.DB_PATH), detect_types=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")       # ожидание блокировки вместо ошибки при параллельной записи
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def audit(action, entity=None, entity_id=None, user_id=None, ip=None):
    get_db().execute(
        "INSERT INTO audit_log(user_id, action, entity, entity_id, ip) VALUES (?,?,?,?,?)",
        (user_id, action, entity, entity_id, ip))
    get_db().commit()
