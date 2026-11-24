"""Тестовое окружение: отдельная временная БД и ключ, результаты пишутся в tests/results.json
(фактические результаты затем выводятся на странице 2)."""
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="vkusno_test_"))
os.environ["VB_DB_PATH"] = str(TMP / "test.db")
os.environ["VB_KEY_PATH"] = str(TMP / "test.key")
os.environ["VB_ACCOUNTS_PATH"] = str(TMP / "accounts.json")
sys.path.insert(0, str(ROOT))

import init_db                      # noqa: E402
from app import create_app          # noqa: E402

RESULTS = {}
BASE = "https://localhost"


@pytest.fixture(scope="session")
def app():
    init_db.main()
    return create_app(testing=True)


class Client:
    """Обёртка над тестовым клиентом: хранит CSRF-токен текущей сессии."""
    def __init__(self, app):
        self.c = app.test_client()
        self.csrf = None
        self.refresh()

    def refresh(self):
        r = self.c.get("/", base_url=BASE)
        m = re.search(r'name="csrf-token" content="([^"]*)"', r.get_data(as_text=True))
        self.csrf = m.group(1) if m else None
        return r

    def get(self, url, **kw):
        return self.c.get(url, base_url=BASE, **kw)

    def post_form(self, url, data, csrf=True):
        data = dict(data)
        if csrf:
            data["csrf_token"] = self.csrf
        return self.c.post(url, data=data, base_url=BASE)

    def api(self, method, url, body=None, csrf=True):
        headers = {"X-CSRF-Token": self.csrf} if csrf else {}
        return self.c.open(url, method=method, json=body, headers=headers, base_url=BASE)

    def login(self, login, password):
        r = self.post_form("/login", {"login": login, "password": password})
        self.refresh()
        return r

    def sid(self):
        ck = self.c.get_cookie("vb_sid", domain="localhost")
        return ck.value if ck else None


@pytest.fixture
def client(app):
    return Client(app)


@pytest.fixture
def as_role(app):
    from app.accounts import passwords
    creds = passwords()

    def make(role):
        cl = Client(app)
        cl.login(role, creds[role])
        return cl
    return make


@pytest.fixture
def pw():
    """Пароли учётных записей тестовой БД (случайные, из accounts.json)."""
    from app.accounts import passwords
    return passwords()


@pytest.fixture
def actual(request):
    """Тест записывает сюда фактический результат."""
    holder = {"text": ""}
    request.node._actual = holder
    return holder


def pytest_runtest_makereport(item, call):
    if call.when != "call":
        return
    meta = getattr(item.function, "_case", None)
    if not meta:
        return
    holder = getattr(item, "_actual", {"text": ""})
    failed = call.excinfo is not None
    RESULTS[meta["id"]] = {**meta, "status": "Не пройден" if failed else "Пройден",
                           "actual": (holder["text"] or "") + (f" | ОШИБКА: {call.excinfo.value}" if failed else "")}


def pytest_sessionfinish(session, exitstatus):
    if not RESULTS:
        return
    def order(k):
        return k[0], int(k[1:])
    data = {"run_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "tests": [RESULTS[k] for k in sorted(RESULTS, key=order)]}
    (ROOT / "tests" / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
