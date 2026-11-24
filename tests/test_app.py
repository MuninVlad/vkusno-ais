"""Функциональные тесты и тесты защищённости АИС «Вкусно и быстро».
Запуск: python -m pytest -q tests"""
import io
import sqlite3
import time

from app import config, crypto


def case(cid, group, title, inp, expected):
    def deco(fn):
        fn._case = {"id": cid, "group": group, "title": title, "input": inp, "expected": expected}
        return fn
    return deco


def db():
    c = sqlite3.connect(str(config.DB_PATH))
    c.row_factory = sqlite3.Row
    return c


# ====================================================================== ФУНКЦИОНАЛЬНЫЕ
@case("F01", "func", "Главная страница для гостя", "GET /", "200; форма входа; ссылок на стр. 2 и 3 нет")
def test_f01(client, actual):
    r = client.get("/")
    t = r.get_data(as_text=True)
    assert r.status_code == 200 and 'id="login-form"' in t and "/system" not in t and "/archive" not in t
    actual["text"] = "200; форма входа показана; ссылки на /system и /archive отсутствуют"


@case("F02", "func", "Вход с верными данными", "admin / верный пароль", "302 → /; появляются ссылки на стр. 2, 3 и «Выход»")
def test_f02(client, pw, actual):
    r = client.login("admin", pw["admin"])
    assert r.status_code == 302
    t = client.get("/").get_data(as_text=True)
    assert "/system" in t and "/archive" in t and "Выход" in t
    actual["text"] = "302 → /; ссылки «2. Описание системы», «3. Файловый архив» и кнопка «Выход» отображаются"


@case("F03", "func", "Вход с неверным паролем", "admin / wrong123A", "401; «Неверный логин или пароль»")
def test_f03(client, actual):
    r = client.login("admin", "wrong123A")
    assert r.status_code == 401 and "Неверный логин или пароль" in r.get_data(as_text=True)
    actual["text"] = "401; выведено «Неверный логин или пароль.»"
    db().execute("DELETE FROM login_attempts WHERE login='admin'").connection.commit()


@case("F04", "func", "Валидация формы входа на сервере", "логин «a b», пароль пустой", "400; сообщения о формате логина и пустом пароле")
def test_f04(client, actual):
    r = client.post_form("/login", {"login": "a b", "password": ""})
    t = r.get_data(as_text=True)
    assert r.status_code == 400 and "Логин: 3–32 символа" in t and "Введите пароль" in t
    actual["text"] = "400; два сообщения об ошибке, запрос к БД не выполнялся"


@case("F05", "func", "Выход из системы", "POST /logout", "Сессия удалена; /system → переадресация на /")
def test_f05(as_role, actual):
    c = as_role("cashier")
    old = c.sid()
    c.post_form("/logout", {})
    assert db().execute("SELECT COUNT(*) FROM sessions WHERE token_hash=?", (crypto.token_hash(old),)).fetchone()[0] == 0
    r = c.get("/system")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    actual["text"] = "Сессия удалена из БД; GET /system → 302 на /"


@case("F06", "func", "Добавление позиции меню", "manager: «Тестовый ролл», 199.90 ₽, 410 ккал", "201; запись в БД")
def test_f06(as_role, actual):
    c = as_role("manager")
    r = c.api("POST", "/api/menu_items", {"category_id": 2, "name": "Тестовый ролл", "price": "199.90", "calories": 410, "is_available": True})
    assert r.status_code == 201
    row = db().execute("SELECT price FROM menu_items WHERE name='Тестовый ролл'").fetchone()
    assert abs(row["price"] - 199.9) < 1e-9
    actual["text"] = f"201; id={r.json['id']}, цена в БД 199.9"


@case("F07", "func", "Редактирование позиции меню", "PUT price=209, is_available=false", "200; данные изменены")
def test_f07(as_role, actual):
    c = as_role("manager")
    mid = db().execute("SELECT id FROM menu_items WHERE name='Тестовый ролл'").fetchone()[0]
    r = c.api("PUT", f"/api/menu_items/{mid}", {"price": 209, "is_available": False})
    row = db().execute("SELECT price, is_available FROM menu_items WHERE id=?", (mid,)).fetchone()
    assert r.status_code == 200 and row["price"] == 209 and row["is_available"] == 0
    actual["text"] = "200; цена 209, «в продаже» = нет"


@case("F08", "func", "Удаление позиции меню без продаж", "DELETE /api/menu_items/<id>", "200; запись удалена")
def test_f08(as_role, actual):
    c = as_role("manager")
    mid = db().execute("SELECT id FROM menu_items WHERE name='Тестовый ролл'").fetchone()[0]
    r = c.api("DELETE", f"/api/menu_items/{mid}")
    assert r.status_code == 200 and not db().execute("SELECT 1 FROM menu_items WHERE id=?", (mid,)).fetchone()
    actual["text"] = "200; «Запись удалена»"


@case("F09", "func", "Удаление позиции меню, входящей в заказы", "DELETE /api/menu_items/1", "409; запрет (ссылочная целостность)")
def test_f09(as_role, actual):
    r = as_role("admin").api("DELETE", "/api/menu_items/1")
    assert r.status_code == 409 and db().execute("SELECT 1 FROM menu_items WHERE id=1").fetchone()
    actual["text"] = "409; «Операция нарушает ссылочную целостность…», запись сохранена"


@case("F10", "func", "Поиск по меню", "q=бургер", "Только позиции, содержащие «бургер»")
def test_f10(as_role, actual):
    rows = as_role("cashier").get("/api/menu_items?q=Бургер").json["rows"]
    assert rows and all("бургер" in (r["name"] + r["category_name"]).lower() for r in rows)
    actual["text"] = f"Найдено {len(rows)} поз., все содержат «бургер»"


@case("F11", "func", "Фильтрация меню", "category_id=1, price_min=100, price_max=300", "Только бургеры от 100 до 300 ₽")
def test_f11(as_role, actual):
    rows = as_role("cashier").get("/api/menu_items?category_id=1&price_min=100&price_max=300").json["rows"]
    assert rows and all(r["category_id"] == 1 and 100 <= r["price"] <= 300 for r in rows)
    actual["text"] = f"Найдено {len(rows)} поз.: " + ", ".join(r["name"] for r in rows)


@case("F12", "func", "Оформление заказа", "ресторан 1, 2×Гранд Бургер + 1×Картофель фри", "201; сумма = 2·289 + 109 = 687 ₽")
def test_f12(as_role, actual):
    c = as_role("cashier")
    emp = db().execute("SELECT employee_id FROM users WHERE login='cashier'").fetchone()[0]
    r = c.api("POST", "/api/orders", {"restaurant_id": 1, "employee_id": emp, "customer_id": 1, "order_type": "с собой",
                                      "payment_method": "карта", "items": [{"menu_item_id": 1, "quantity": 2}, {"menu_item_id": 8, "quantity": 1}]})
    assert r.status_code == 201
    o = c.get(f"/api/orders/{r.json['id']}").json["order"]
    assert o["total"] == 687 and o["status"] == "новый"
    actual["text"] = f"201; заказ №{r.json['id']}, сумма 687.00 ₽, статус «новый»"


@case("F13", "func", "Изменение статуса заказа", "PUT status=«готовится»", "200; статус изменён")
def test_f13(as_role, actual):
    c = as_role("cashier")
    oid = db().execute("SELECT MAX(id) FROM orders").fetchone()[0]
    r = c.api("PUT", f"/api/orders/{oid}", {"status": "готовится"})
    assert r.status_code == 200 and c.get(f"/api/orders/{oid}").json["order"]["status"] == "готовится"
    actual["text"] = "200; статус «готовится»"


@case("F14", "func", "Заказ без позиций / с количеством 0", "items=[]; quantity=0", "400; сообщение о составе заказа")
def test_f14(as_role, actual):
    c = as_role("cashier")
    base = {"restaurant_id": 1, "employee_id": 2, "order_type": "в зале", "payment_method": "СБП"}
    r1 = c.api("POST", "/api/orders", {**base, "items": []})
    r2 = c.api("POST", "/api/orders", {**base, "items": [{"menu_item_id": 1, "quantity": 0}]})
    assert r1.status_code == 400 and r2.status_code == 400
    actual["text"] = f"400 / 400; «{r1.json['fields']['items']}», «{r2.json['fields']['items']}»"


@case("F15", "func", "Граничные значения цены", "price = 0; 10000; 10000.01; «abc»", "400; 201; 400; 400")
def test_f15(as_role, actual):
    c = as_role("manager")
    codes = []
    for i, p in enumerate(["0", "10000", "10000.01", "abc"]):
        codes.append(c.api("POST", "/api/menu_items", {"category_id": 6, "name": f"Граница {i}", "price": p, "calories": 1}).status_code)
    assert codes == [400, 201, 400, 400]
    actual["text"] = " ; ".join(map(str, codes))


@case("F16", "func", "Регистрация клиента и поиск по телефону", "«Ирина Ветрова», 8 (916) 555-12-34", "201; телефон → +79165551234; поиск по номеру находит клиента")
def test_f16(as_role, actual):
    c = as_role("cashier")
    r = c.api("POST", "/api/customers", {"full_name": "Ирина Ветрова", "phone": "8 (916) 555-12-34", "email": "irina@example.ru"})
    assert r.status_code == 201
    rows = c.get("/api/customers?q=%2B7%20916%20555%2012%2034").json["rows"]
    assert len(rows) == 1 and rows[0]["phone"] == "+79165551234"
    actual["text"] = "201; сохранён +79165551234; поиск «+7 916 555 12 34» вернул 1 запись (через HMAC-индекс)"


@case("F17", "func", "Повторная регистрация телефона", "тот же телефон 89165551234", "409; «Запись с таким значением уже существует»")
def test_f17(as_role, actual):
    r = as_role("cashier").api("POST", "/api/customers", {"full_name": "Дубликат", "phone": "89165551234"})
    assert r.status_code == 409
    actual["text"] = "409; " + r.json["error"]


@case("F18", "func", "Некорректные e-mail и дата", "email=«ivan@», hire_date=«2026-02-30»", "400; ошибки у полей")
def test_f18(as_role, actual):
    c = as_role("manager")
    r1 = c.api("POST", "/api/customers", {"full_name": "Иван Тест", "phone": "+79990001122", "email": "ivan@"})
    r2 = c.api("POST", "/api/employees", {"restaurant_id": 1, "position_id": 2, "full_name": "Тестов Тест Тестович",
                                         "phone": "+79990001123", "hire_date": "2026-02-30", "salary": 50000})
    assert r1.status_code == 400 and "email" in r1.json["fields"] and r2.status_code == 400 and "hire_date" in r2.json["fields"]
    actual["text"] = f"400: «{r1.json['fields']['email']}»; 400: «{r2.json['fields']['hire_date']}»"


@case("F19", "func", "Формирование отчётов", "5 отчётов за 60 дней; период с > по", "200 и данные для каждого; 400 для неверного периода")
def test_f19(as_role, actual):
    c = as_role("manager")
    names = [r["id"] for r in c.get("/api/reports").json["reports"]]
    sizes = []
    for n in names:
        r = c.get(f"/api/reports/{n}?date_from=2026-01-01&date_to=2026-12-31")
        assert r.status_code == 200 and r.json["rows"]
        sizes.append(len(r.json["rows"]))
    bad = c.get("/api/reports/daily_revenue?date_from=2026-12-01&date_to=2026-01-01")
    assert len(names) == 5 and bad.status_code == 400
    actual["text"] = f"5 отчётов, строк: {sizes}; неверный период → 400"


@case("F20", "func", "ФИО сотрудника с цифрами", "full_name=«Иванов 2 Иван»", "400; «только буквы, пробел, дефис»")
def test_f20(as_role, actual):
    r = as_role("manager").api("POST", "/api/employees", {"restaurant_id": 1, "position_id": 2, "full_name": "Иванов 2 Иван",
                                                          "phone": "+79990001124", "hire_date": "2026-01-10", "salary": 50000})
    assert r.status_code == 400 and "full_name" in r.json["fields"]
    actual["text"] = "400; " + r.json["fields"]["full_name"]


@case("F21", "func", "Файловый архив: просмотр и скачивание", "GET /archive; /files/<id>?download=1", "200; список файлов; файл отдаётся как вложение")
def test_f21(as_role, actual):
    c = as_role("cashier")
    t = c.get("/archive").get_data(as_text=True)
    assert "schema.sql" in t
    r = c.get("/files/s-sql-schema?download=1")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"] and b"CREATE TABLE" in r.data
    actual["text"] = "200; schema.sql скачан (Content-Disposition: attachment)"


@case("F22", "func", "Создание пользователя администратором", "пароль «qwerty»; затем «Kassa#2026»", "400 (слабый пароль); 201; новый пользователь входит")
def test_f22(as_role, app, actual):
    c = as_role("admin")
    r1 = c.api("POST", "/api/users", {"login": "kassa2", "role_id": 3, "is_active": True, "password": "qwerty"})
    r2 = c.api("POST", "/api/users", {"login": "kassa2", "role_id": 3, "is_active": True, "password": "Kassa#2026"})
    from tests.conftest import Client
    n = Client(app)
    r3 = n.login("kassa2", "Kassa#2026")
    assert r1.status_code == 400 and r2.status_code == 201 and r3.status_code == 302
    actual["text"] = f"400 ({r1.json['fields']['password']}); 201; вход → 302"


# ====================================================================== БЕЗОПАСНОСТЬ
@case("S01", "sec", "Прямой переход на стр. 2 и 3 без входа", "GET /system, GET /archive", "302 → / с сообщением")
def test_s01(client, actual):
    r1, r2 = client.get("/system"), client.get("/archive")
    assert r1.status_code == r2.status_code == 302 and r1.headers["Location"].endswith("/")
    actual["text"] = "302 → /; «Для доступа к странице необходимо войти в систему»"


@case("S02", "sec", "Прямая ссылка на файл без входа", "GET /files/g-19_er", "302 → /; файл не отдан")
def test_s02(client, actual):
    r = client.get("/files/g-19_er")
    assert r.status_code == 302 and b"<svg" not in r.data
    actual["text"] = "302 → /; содержимое файла не передано"


@case("S03", "sec", "Обращение к API без сессии", "GET /api/customers", "401")
def test_s03(client, actual):
    r = client.get("/api/customers")
    assert r.status_code == 401
    actual["text"] = "401 «Требуется авторизация»"


@case("S04", "sec", "Кассир удаляет позицию меню (обход интерфейса)", "cashier: DELETE /api/menu_items/2", "403; запись в журнале аудита")
def test_s04(as_role, actual):
    r = as_role("cashier").api("DELETE", "/api/menu_items/2")
    n = db().execute("SELECT COUNT(*) FROM audit_log WHERE action='access_denied'").fetchone()[0]
    assert r.status_code == 403 and db().execute("SELECT 1 FROM menu_items WHERE id=2").fetchone() and n > 0
    actual["text"] = "403 «Недостаточно прав»; событие access_denied записано в audit_log"


@case("S05", "sec", "Кассир читает пользователей и сотрудников", "cashier: GET /api/users, /api/employees", "403 / 403")
def test_s05(as_role, actual):
    c = as_role("cashier")
    assert c.get("/api/users").status_code == 403 and c.get("/api/employees").status_code == 403
    actual["text"] = "403 / 403"


@case("S06", "sec", "SQL-инъекция в форме входа", "login: admin' OR '1'='1 ; пароль: x' OR '1'='1", "Вход не выполнен")
def test_s06(client, actual):
    r = client.post_form("/login", {"login": "admin' OR '1'='1", "password": "x' OR '1'='1"})
    r2 = client.post_form("/login", {"login": "admin", "password": "' OR '1'='1' --"})
    assert r.status_code in (400, 401) and r2.status_code == 401 and client.get("/system").status_code == 302
    actual["text"] = f"{r.status_code} (логин отклонён валидацией), {r2.status_code} «Неверный логин или пароль»"
    db().execute("DELETE FROM login_attempts WHERE login='admin'").connection.commit()


@case("S07", "sec", "SQL-инъекция в строке поиска", "q=' OR 1=1 --", "0 записей, без ошибки СУБД")
def test_s07(as_role, actual):
    r = as_role("cashier").get("/api/menu_items?q=%27%20OR%201%3D1%20--")
    assert r.status_code == 200 and r.json["rows"] == []
    actual["text"] = "200; найдено 0 записей (строка обработана как текст)"


@case("S08", "sec", "SQL-инъекция в фильтре и UNION", "category_id=1 OR 1=1; q=x' UNION SELECT login,password_hash…", "Без утечки данных")
def test_s08(as_role, actual):
    c = as_role("cashier")
    r1 = c.get("/api/menu_items?category_id=1%20OR%201%3D1")
    r2 = c.get("/api/orders?q=x%27%20UNION%20SELECT%20login,password_hash,1,1,1,1,1,1,1,1,1,1,1%20FROM%20users--")
    assert r1.json["rows"] == [] and "pbkdf2" not in r2.get_data(as_text=True)
    actual["text"] = "0 записей; хеши паролей в ответе отсутствуют"


@case("S09", "sec", "Хранимая XSS через поля ввода", "full_name=<script>alert(1)</script>", "400; данные не сохранены")
def test_s09(as_role, actual):
    r = as_role("cashier").api("POST", "/api/customers", {"full_name": "<script>alert(1)</script>", "phone": "+79990002233"})
    assert r.status_code == 400
    actual["text"] = "400; " + r.json["fields"]["full_name"]


@case("S10", "sec", "Отражённая XSS и экранирование вывода", "login=\"><script>alert(1)</script>", "Вывод экранирован (&lt;script&gt;)")
def test_s10(client, actual):
    r = client.post_form("/login", {"login": '"><script>alert(1)</script>', "password": "x"})
    t = r.get_data(as_text=True)
    assert "<script>alert(1)" not in t and "&lt;script&gt;" in t
    actual["text"] = "Значение выведено как &#34;&gt;&lt;script&gt;… — скрипт не выполняется"


@case("S11", "sec", "Заголовки безопасности", "GET /", "CSP script-src 'self', X-Frame-Options DENY, HSTS, nosniff")
def test_s11(client, actual):
    h = client.get("/").headers
    assert "script-src 'self'" in h["Content-Security-Policy"] and h["X-Frame-Options"] == "DENY"
    assert "max-age" in h["Strict-Transport-Security"] and h["X-Content-Type-Options"] == "nosniff"
    actual["text"] = "Все заголовки присутствуют"


@case("S12", "sec", "CSRF: запрос без токена", "POST /login и POST /api/customers без токена; с чужим токеном", "403 во всех случаях")
def test_s12(as_role, client, pw, actual):
    r1 = client.post_form("/login", {"login": "admin", "password": pw["admin"]}, csrf=False)
    c = as_role("cashier")
    r2 = c.api("POST", "/api/customers", {"full_name": "Тест", "phone": "+79990003344"}, csrf=False)
    c.csrf = "forged-token"
    r3 = c.api("POST", "/api/customers", {"full_name": "Тест", "phone": "+79990003344"})
    assert r1.status_code == r2.status_code == r3.status_code == 403
    actual["text"] = "403 / 403 / 403; событие csrf_reject в журнале"


@case("S13", "sec", "Подбор пароля", "6 попыток с неверным паролем, затем верный", "После 5-й — блокировка на 5 мин даже с верным паролем")
def test_s13(as_role, app, actual):
    as_role("admin").api("POST", "/api/users", {"login": "victim", "role_id": 3, "is_active": True, "password": "Victim#2026"})
    from tests.conftest import Client
    c = Client(app)
    msgs = [c.login("victim", f"Wrong#{i}x").get_data(as_text=True) for i in range(5)]
    r = c.login("victim", "Victim#2026")
    assert "заблокирован" in msgs[-1] and r.status_code == 401 and "заблокирован" in r.get_data(as_text=True)
    actual["text"] = "Попытки 1–4: «Неверный логин или пароль»; 5-я и верный пароль: «Вход временно заблокирован»"


@case("S14", "sec", "Фиксация сессии", "Сравнить vb_sid до и после входа", "Идентификатор меняется, старый недействителен")
def test_s14(client, pw, actual):
    before = client.sid()
    client.login("manager", pw["manager"])
    after = client.sid()
    old = db().execute("SELECT 1 FROM sessions WHERE token_hash=?", (crypto.token_hash(before),)).fetchone()
    assert before and after and before != after and old is None
    actual["text"] = "Новый идентификатор выдан, старая сессия удалена из БД"


@case("S15", "sec", "Флаги cookie сессии", "Заголовок Set-Cookie", "HttpOnly; Secure; SameSite=Strict")
def test_s15(app, actual):
    r = app.test_client().get("/", base_url="https://localhost")
    sc = r.headers["Set-Cookie"]
    assert "HttpOnly" in sc and "Secure" in sc and "SameSite=Strict" in sc
    actual["text"] = "Set-Cookie: vb_sid=…; Secure; HttpOnly; SameSite=Strict"


@case("S16", "sec", "Тайм-аут бездействия", "last_activity сдвинут на 16 мин назад", "Сессия удалена, переадресация на / с сообщением")
def test_s16(as_role, actual):
    c = as_role("cashier")
    con = db()
    con.execute("UPDATE sessions SET last_activity=? WHERE token_hash=?", (time.time() - 16 * 60, crypto.token_hash(c.sid())))
    con.commit()
    r = c.get("/system")
    assert r.status_code == 302
    t = c.get("/").get_data(as_text=True)
    assert "тайм-ауту" in t
    actual["text"] = "302 → /; «Сессия завершена по тайм-ауту. Войдите снова.»"


@case("S17", "sec", "Хранение паролей", "SELECT password_hash FROM users", "PBKDF2-SHA256, 600 000 итераций, уникальная соль; открытого пароля нет")
def test_s17(pw, actual):
    rows = [r[0] for r in db().execute("SELECT password_hash FROM users")]
    salts = {h.split("$")[2] for h in rows}
    assert all(h.startswith("pbkdf2_sha256$600000$") for h in rows) and len(salts) == len(rows)
    assert not any(p in h for h in rows for p in pw.values())
    actual["text"] = f"{len(rows)} хешей вида pbkdf2_sha256$600000$соль$хеш, все соли различны"


@case("S18", "sec", "Шифрование персональных данных", "Чтение customers из БД напрямую; подмена 1 байта шифртекста", "В БД только v1:…; подмена обнаруживается (тег GCM)")
def test_s18(actual):
    con = db()
    row = con.execute("SELECT phone_enc FROM customers WHERE full_name='Ирина Ветрова'").fetchone()
    assert row["phone_enc"].startswith("v1:") and "9165551234" not in row["phone_enc"]
    raw = row["phone_enc"]
    tampered = raw[:-6] + ("A" if raw[-6] != "A" else "B") + raw[-5:]
    try:
        crypto.decrypt_field(tampered, "customers.phone_enc")
        ok = False
    except Exception:
        ok = True
    assert ok
    actual["text"] = "Хранится шифртекст v1:…; изменённый шифртекст отвергнут (InvalidTag)"


@case("S19", "sec", "Обход каталога (path traversal)", "GET /files/..%2F..%2Finstance%2Fdata.key", "404; ключ не выдан")
def test_s19(as_role, actual):
    c = as_role("admin")
    codes = [c.get(u).status_code for u in ("/files/..%2F..%2Finstance%2Fdata.key", "/files/../instance/data.key",
                                            "/static/../instance/vkusno.db")]
    assert all(code == 404 for code in codes)
    actual["text"] = " / ".join(map(str, codes))


@case("S20", "sec", "Листинг каталогов", "GET /static/, /static/css/, /storage/, /instance/", "404 для всех")
def test_s20(as_role, actual):
    c = as_role("admin")
    codes = [c.get(u).status_code for u in ("/static/", "/static/css/", "/storage/", "/storage/archive/", "/instance/")]
    assert all(code == 404 for code in codes)
    actual["text"] = " / ".join(map(str, codes))


@case("S21", "sec", "Загрузка файлов", ".html; PNG с подменой содержимого; PNG с MIME text/html; 6 МБ; корректный PNG; загрузка кассиром",
      "Отклонено; отклонено; отклонено; отклонено; принято; 403")
def test_s21(as_role, actual):
    c = as_role("admin")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    def up(cl, name, data, ctype=None):
        f = (io.BytesIO(data), name, ctype) if ctype else (io.BytesIO(data), name)
        return cl.c.post("/files/upload", data={"csrf_token": cl.csrf, "file": f, "description": "тест"},
                         content_type="multipart/form-data", base_url="https://localhost", follow_redirects=True)
    t1 = up(c, "evil.html", b"<script>alert(1)</script>").get_data(as_text=True)
    t2 = up(c, "fake.png", b"MZ\x90\x00 not png").get_data(as_text=True)
    t3 = up(c, "big.png", png + b"\x00" * (6 * 1024 * 1024))
    t2m = up(c, "ok.png", png, "text/html").get_data(as_text=True)
    t4 = up(c, "ok.png", png, "image/png").get_data(as_text=True)
    r5 = up(as_role("cashier"), "ok.png", png)
    assert "Недопустимое расширение" in t1
    assert "не соответствует" in t2
    assert "MIME" in t2m
    assert t3.status_code == 413 or "больше 5 МБ" in t3.get_data(as_text=True)
    assert "загружен" in t4 and r5.status_code == 403
    stored = list(config.UPLOAD_DIR.glob("*.png"))
    assert stored and all(p.parent == config.UPLOAD_DIR for p in stored)
    for p in config.UPLOAD_DIR.glob("*"):
        if p.name != ".gitkeep":
            p.unlink()
    actual["text"] = f"Отклонено (расширение); отклонено (сигнатура); отклонено (MIME); {t3.status_code} (лимит размера); принято (имя на сервере — UUID, вне static); 403"


@case("S22", "sec", "Скрытие системных ошибок", "Некорректный JSON в API; несуществующий маршрут", "Общее сообщение без трассировки")
def test_s22(as_role, actual):
    c = as_role("admin")
    r1 = c.c.post("/api/orders", data="{bad json", headers={"X-CSRF-Token": c.csrf, "Content-Type": "application/json"},
                  base_url="https://localhost")
    r2 = c.get("/no/such/page")
    t = r1.get_data(as_text=True) + r2.get_data(as_text=True)
    assert r1.status_code == 400 and r2.status_code == 404 and "Traceback" not in t and "sqlite3" not in t
    actual["text"] = f"{r1.status_code} «{r1.json['error']}»; 404 — страница «Страница не найдена»"


@case("S23", "sec", "Блокировка учётной записи администратором", "PUT /api/users/<id> is_active=false", "Все сессии пользователя завершаются")
def test_s23(as_role, app, actual):
    from tests.conftest import Client
    victim = Client(app)
    victim.login("kassa2", "Kassa#2026")
    assert victim.get("/system").status_code == 200
    uid = db().execute("SELECT id FROM users WHERE login='kassa2'").fetchone()[0]
    as_role("admin").api("PUT", f"/api/users/{uid}", {"is_active": False})
    assert victim.get("/system").status_code == 302
    actual["text"] = "Сессия заблокированного пользователя удалена; /system → 302"


@case("F23", "func", "Заказ с кассиром другого ресторана", "restaurant_id=1, кассир ресторана 5", "400; «сотрудник работает в другом ресторане»")
def test_f23(as_role, actual):
    emp = db().execute("SELECT id FROM employees WHERE restaurant_id=5 AND position_id=2").fetchone()[0]
    r = as_role("cashier").api("POST", "/api/orders", {"restaurant_id": 1, "employee_id": emp, "order_type": "в зале",
                                                        "payment_method": "карта", "items": [{"menu_item_id": 1, "quantity": 1}]})
    assert r.status_code == 400 and "другом ресторане" in r.json["fields"]["employee_id"]
    actual["text"] = "400; " + r.json["fields"]["employee_id"]


@case("S24", "sec", "Версия протокола TLS и раскрытие версий ПО", "Подключение с TLS 1.1 и TLS 1.2 к серверу; заголовок Server",
      "TLS 1.1 — отказ рукопожатия; TLS 1.2+ — соединение; версии Werkzeug/Python не раскрываются")
def test_s24(app, actual):
    import socket
    import ssl
    import threading
    from run import make_https_server
    srv = make_https_server(app, "127.0.0.1", 0)          # тот же сервер, что запускает run.py
    port = srv.server_port
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def connect(maxv):
        c = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        c.check_hostname = False
        c.verify_mode = ssl.CERT_NONE
        c.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        c.maximum_version = maxv
        try:
            c.set_ciphers("ALL:@SECLEVEL=0")
        except ssl.SSLError:
            pass
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            try:
                with c.wrap_socket(s, server_hostname="localhost") as t:
                    return t.version()
            except (ssl.SSLError, ConnectionResetError, OSError):
                return "отказ"
    v11, v12, best = connect(ssl.TLSVersion.TLSv1_1), connect(ssl.TLSVersion.TLSv1_2), connect(ssl.TLSVersion.MAXIMUM_SUPPORTED)
    import urllib.request
    server_hdr = urllib.request.urlopen(f"https://127.0.0.1:{port}/", context=ssl._create_unverified_context()).headers.get("Server")  # noqa: S310,S323
    srv.shutdown()
    assert "Werkzeug" not in server_hdr and "Python" not in server_hdr
    assert v11 == "отказ" and v12 == "TLSv1.2" and best in ("TLSv1.2", "TLSv1.3")
    actual["text"] = f"TLS 1.1: {v11}; TLS 1.2: соединение ({v12}); по умолчанию: {best}; заголовок Server: «{server_hdr.strip()}» (без версий ПО)"


@case("F24", "func", "Жизненный цикл заказа и начисление бонусов", "заказ №F12: готовится → выдан; → готов → выдан; выдан → новый",
      "400 (пропуск этапа); 200, 200 и +5 % суммы бонусами клиенту; 400 (выданный заказ не меняется)")
def test_f24(as_role, actual):
    c = as_role("cashier")
    oid = db().execute("SELECT MAX(id) FROM orders WHERE customer_id=1").fetchone()[0]
    before = db().execute("SELECT bonus_points FROM customers WHERE id=1").fetchone()[0]
    total = c.get(f"/api/orders/{oid}").json["order"]["total"]
    r1 = c.api("PUT", f"/api/orders/{oid}", {"status": "выдан"})
    r2 = c.api("PUT", f"/api/orders/{oid}", {"status": "готов"})
    r3 = c.api("PUT", f"/api/orders/{oid}", {"status": "выдан"})
    after = db().execute("SELECT bonus_points FROM customers WHERE id=1").fetchone()[0]
    r4 = c.api("PUT", f"/api/orders/{oid}", {"status": "новый"})
    assert (r1.status_code, r2.status_code, r3.status_code, r4.status_code) == (400, 200, 200, 400)
    assert after - before == int(total * 0.05)
    actual["text"] = f"400; 200; 200, начислено {after - before} бонусов (5 % от {total:.2f} ₽); 400 «{r4.json['fields']['status']}»"


@case("F25", "func", "Изменение состава заказа после передачи на кухню", "статус «готовится», PUT items", "400; состав не изменён")
def test_f25(as_role, actual):
    c = as_role("cashier")
    r = c.api("POST", "/api/orders", {"restaurant_id": 1, "employee_id": 2, "order_type": "в зале", "payment_method": "карта",
                                      "items": [{"menu_item_id": 2, "quantity": 1}]})
    oid = r.json["id"]
    c.api("PUT", f"/api/orders/{oid}", {"status": "готовится"})
    r2 = c.api("PUT", f"/api/orders/{oid}", {"items": [{"menu_item_id": 2, "quantity": 5}]})
    qty = db().execute("SELECT quantity FROM order_items WHERE order_id=?", (oid,)).fetchone()[0]
    assert r2.status_code == 400 and qty == 1
    actual["text"] = "400; " + r2.json["fields"]["items"]


@case("F26", "func", "Заказ в закрытом ресторане", "restaurant_id=10 («Покровка», is_active=0)", "400; приём заказов невозможен")
def test_f26(as_role, actual):
    emp = db().execute("SELECT id FROM employees WHERE restaurant_id=10 AND position_id=2").fetchone()[0]
    r = as_role("admin").api("POST", "/api/orders", {"restaurant_id": 10, "employee_id": emp, "order_type": "в зале",
                                                      "payment_method": "карта", "items": [{"menu_item_id": 1, "quantity": 1}]})
    assert r.status_code == 400 and "restaurant_id" in r.json["fields"]
    actual["text"] = "400; " + r.json["fields"]["restaurant_id"]


@case("S25", "sec", "Кассир начисляет бонусы вручную", "cashier: PUT /api/customers/2 bonus_points=99999; POST с bonus_points=5000",
      "403; новый клиент создаётся с 0 бонусов")
def test_s25(as_role, actual):
    c = as_role("cashier")
    r1 = c.api("PUT", "/api/customers/2", {"bonus_points": 99999})
    r2 = c.api("POST", "/api/customers", {"full_name": "Бонус Тест", "phone": "+79990007788", "bonus_points": 5000})
    b = db().execute("SELECT bonus_points FROM customers WHERE id=?", (r2.json["id"],)).fetchone()[0]
    assert r1.status_code == 403 and r2.status_code == 201 and b == 0
    actual["text"] = f"403 «{r1.json['error']}»; клиент создан с балансом {b}"


@case("F27", "func", "Производительность (НФТ-01)", "БД дополнена до 10 000+ заказов; 20 параллельных пользователей по 5 запросов к /api/orders",
      "Отчёт ≤ 3 с; каждый типовой запрос ≤ 1 с")
def test_f27(as_role, app, pw, actual):
    import random
    import ssl
    import threading
    import urllib.request
    import urllib.parse
    import http.cookiejar
    from concurrent.futures import ThreadPoolExecutor
    from run import make_https_server
    con = db()
    n0 = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    rnd = random.Random(1)
    for _ in range(10000 - n0 + 100):
        cur = con.execute("INSERT INTO orders(restaurant_id, employee_id, created_at, order_type, payment_method, status) "
                          "VALUES (1, 2, datetime('now', ?), 'в зале', 'карта', 'выдан')", (f"-{rnd.randint(0, 300)} days",))
        con.execute("INSERT INTO order_items VALUES (?,?,?,?)", (cur.lastrowid, rnd.randint(1, 19), 1, 100))
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    c = as_role("manager")
    times = {}
    for rep in ("revenue_by_restaurant", "top_menu_items", "avg_check_by_type", "daily_revenue", "cashier_performance"):
        t = time.perf_counter()
        r = c.get(f"/api/reports/{rep}?date_from=2025-01-01&date_to=2027-01-01")
        times[rep] = time.perf_counter() - t
        assert r.status_code == 200
    # 20 одновременных пользователей через настоящий HTTPS-сервер
    srv = make_https_server(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"https://127.0.0.1:{srv.server_port}"
    cctx = ssl._create_unverified_context()  # noqa: S323 — учебный самоподписанный сертификат тестового сервера

    barrier = threading.Barrier(20)

    def user(_):
        jar = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), urllib.request.HTTPSHandler(context=cctx))
        page = op.open(base + "/").read().decode()
        import re as _re
        tok = _re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        op.open(base + "/login", urllib.parse.urlencode({"login": "manager", "password": pw["manager"], "csrf_token": tok}).encode())
        barrier.wait(timeout=60)       # замер начинается, когда все 20 пользователей вошли (вход — отдельная операция)
        lat = []
        for _ in range(5):
            t = time.perf_counter()
            op.open(base + "/api/orders?status=" + urllib.parse.quote("готов")).read()
            lat.append(time.perf_counter() - t)
        return lat
    with ThreadPoolExecutor(20) as ex:
        lat = sorted(x for lst in ex.map(user, range(20)) for x in lst)
    srv.shutdown()
    p95, worst = lat[int(len(lat) * 0.95) - 1], lat[-1]
    assert max(times.values()) <= 3 and worst <= 1
    actual["text"] = (f"{n} заказов: самый долгий отчёт {max(times.values()):.2f} с; 20 пользователей × 5 запросов: "
                      f"95 % ответов ≤ {p95:.2f} с, максимум {worst:.2f} с")


@case("F28", "func", "Уникальность логина без учёта регистра", "создать «ADMIN» при существующем «admin»", "409; запись не создана")
def test_f28(as_role, actual):
    r = as_role("admin").api("POST", "/api/users", {"login": "ADMIN", "role_id": 3, "is_active": True, "password": "Qwerty#2026"})
    n = db().execute("SELECT COUNT(*) FROM users WHERE lower(login)='admin'").fetchone()[0]
    assert r.status_code == 409 and n == 1
    actual["text"] = "409; " + r.json["error"]


@case("S26", "sec", "Защита от потери прав администратора", "admin: снять с себя роль администратора; заблокировать себя; понизить admin.it",
      "400; 400; 200 (в системе остаётся активный администратор)")
def test_s26(as_role, actual):
    c = as_role("admin")
    me = db().execute("SELECT id FROM users WHERE login='admin'").fetchone()[0]
    other = db().execute("SELECT id FROM users WHERE login='admin.it'").fetchone()[0]
    r1 = c.api("PUT", f"/api/users/{me}", {"role_id": 3})
    r2 = c.api("PUT", f"/api/users/{me}", {"is_active": False})
    r3 = c.api("PUT", f"/api/users/{other}", {"role_id": 2})
    c.api("PUT", f"/api/users/{other}", {"role_id": 1})
    admins = db().execute("SELECT COUNT(*) FROM users u JOIN roles r ON r.id=u.role_id WHERE r.code='admin' AND is_active=1").fetchone()[0]
    assert (r1.status_code, r2.status_code, r3.status_code) == (400, 400, 200) and admins >= 1
    actual["text"] = f"400 «{r1.json['error']}»; 400; 200; активных администраторов: {admins}"


@case("S27", "sec", "Устойчивость к «молчащим» подключениям", "3 TCP-подключения без TLS-рукопожатия (как упреждающие соединения браузера) + 20 параллельных запросов",
      "Все 20 запросов — 200 за ≤ 5 с; «молчащие» соединения не блокируют сервер")
def test_s27(app, actual):
    import socket
    import ssl
    import threading
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    from run import make_https_server
    srv = make_https_server(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    idle = [socket.create_connection(("127.0.0.1", srv.server_port)) for _ in range(3)]   # не отправляют ClientHello
    cctx = ssl._create_unverified_context()  # noqa: S323 — учебный самоподписанный сертификат

    def hit(_):
        try:
            return urllib.request.urlopen(f"https://127.0.0.1:{srv.server_port}/static/css/style.css", context=cctx, timeout=5).status
        except Exception as e:
            return type(e).__name__
    t = time.perf_counter()
    with ThreadPoolExecutor(20) as ex:
        codes = list(ex.map(hit, range(20)))
    took = time.perf_counter() - t
    for sck in idle:
        sck.close()
    srv.shutdown()
    assert codes.count(200) == 20, codes
    actual["text"] = f"20 из 20 ответов — 200 за {took:.2f} с при 3 «молчащих» соединениях"
