"""Учётные записи тестовой базы данных.

Пароли не хранятся в исходном коде (репозиторий публичный): при первой установке они
генерируются случайно и записываются в instance/accounts.json (права 0600, в репозиторий
не попадает). Администратор передаёт их пользователям отдельно.
"""
import json
import os
import secrets
import string
from pathlib import Path

from . import config

PATH = Path(os.environ.get("VB_ACCOUNTS_PATH", config.INSTANCE_DIR / "accounts.json"))

# логин, роль, ресторан (id), должность (id) связанного сотрудника
SPEC = [
    ("admin", "admin", None, None), ("admin.it", "admin", None, None),
    ("manager", "manager", 1, 1), ("manager.arbat", "manager", 2, 1), ("manager.nevsky", "manager", 5, 1),
    ("cashier", "cashier", 1, 2), ("kassa.arbat", "cashier", 2, 2), ("kassa.taganka", "cashier", 3, 2),
    ("kassa.nevsky", "cashier", 5, 2), ("kassa.kazan", "cashier", 7, 2), ("kassa.ekb", "cashier", 8, 2),
]


def generate_password(length=12):
    """Случайный пароль по политике сложности: строчные, заглавные, цифры, спецсимвол."""
    alphabet = string.ascii_letters + string.digits
    while True:
        body = [secrets.choice(alphabet) for _ in range(length - 1)]
        body.insert(secrets.randbelow(length), secrets.choice("#!%*-+"))
        pw = "".join(body)
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def passwords():
    """{логин: пароль}; файл создаётся при первом обращении."""
    if PATH.exists():
        return json.loads(PATH.read_text("utf-8"))
    PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {login: generate_password() for login, *_ in SPEC}
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.chmod(PATH, 0o600)
    return data
