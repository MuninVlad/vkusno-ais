"""REST API рабочего модуля: добавление, редактирование, удаление, поиск, фильтрация.
Права проверяются на сервере при каждом запросе по матрице PERMS."""
import sqlite3

from flask import Blueprint, g, jsonify, request

from . import crypto
from .db import audit, get_db, query
from .security import login_required, password_problems, LOGIN_RE
from .validation import ValidationError, clean, normalize_phone

bp = Blueprint("api", __name__, url_prefix="/api")

ALL = ("admin", "manager", "cashier")
MGR = ("admin", "manager")
ADM = ("admin",)

ORDER_TYPES = ["в зале", "с собой", "доставка"]
PAYMENTS = ["наличные", "карта", "СБП"]
STATUSES = ["новый", "готовится", "готов", "выдан", "отменён"]
# допустимые переходы статусов — по диаграмме состояний заказа (рис. 12)
TRANSITIONS = {"новый": {"готовится", "отменён"}, "готовится": {"готов", "отменён"},
               "готов": {"выдан"}, "выдан": set(), "отменён": set()}
BONUS_RATE = 0.05          # бонусы клиенту: 5 % суммы заказа при выдаче

# ------------------------------------------------------------------ описание сущностей
ENTITIES = {
    "restaurants": {
        "title": "Рестораны", "table": "restaurants",
        "perms": {"read": ALL, "create": ADM, "update": ADM, "delete": ADM},
        "fields": {
            "name": {"type": "str", "label": "Название", "required": True, "min": 2, "max": 100},
            "city": {"type": "name", "label": "Город", "required": True, "min": 2, "max": 60},
            "address": {"type": "str", "label": "Адрес", "required": True, "min": 5, "max": 200},
            "phone": {"type": "phone", "label": "Телефон", "required": True},
            "opened_on": {"type": "date", "label": "Дата открытия", "required": True},
            "is_active": {"type": "bool", "label": "Работает"},
        },
        "list_sql": "SELECT * FROM restaurants t",
        "search": ["t.name", "t.city", "t.address"],
        "filters": {"city": ("t.city", "="), "is_active": ("t.is_active", "=")},
        "order": "t.id",
    },
    "categories": {
        "title": "Категории меню", "table": "categories",
        "perms": {"read": ALL, "create": MGR, "update": MGR, "delete": MGR},
        "fields": {"name": {"type": "str", "label": "Название", "required": True, "min": 2, "max": 60}},
        "list_sql": "SELECT * FROM categories t", "search": ["t.name"], "filters": {}, "order": "t.name",
    },
    "menu_items": {
        "title": "Меню", "table": "menu_items",
        "perms": {"read": ALL, "create": MGR, "update": MGR, "delete": MGR},
        "fields": {
            "category_id": {"type": "fk", "label": "Категория", "required": True, "ref": "categories"},
            "name": {"type": "str", "label": "Наименование", "required": True, "min": 2, "max": 100},
            "price": {"type": "num", "label": "Цена, ₽", "required": True, "min": 0.01, "max": 10000},
            "calories": {"type": "int", "label": "Ккал", "required": True, "min": 0, "max": 5000},
            "is_available": {"type": "bool", "label": "В продаже"},
        },
        "list_sql": "SELECT t.*, c.name AS category_name FROM menu_items t JOIN categories c ON c.id=t.category_id",
        "search": ["t.name", "c.name"],
        "filters": {"category_id": ("t.category_id", "="), "is_available": ("t.is_available", "="),
                    "price_min": ("t.price", ">="), "price_max": ("t.price", "<=")},
        "order": "c.name, t.name",
    },
    "positions": {
        "title": "Должности", "table": "positions",
        "perms": {"read": MGR, "create": ADM, "update": ADM, "delete": ADM},
        "fields": {
            "name": {"type": "str", "label": "Должность", "required": True, "min": 2, "max": 60},
            "base_salary": {"type": "num", "label": "Оклад, ₽", "required": True, "min": 1, "max": 1000000},
        },
        "list_sql": "SELECT * FROM positions t", "search": ["t.name"], "filters": {}, "order": "t.id",
    },
    "employees": {
        "title": "Сотрудники", "table": "employees",
        "perms": {"read": MGR, "create": MGR, "update": MGR, "delete": ADM},
        "fields": {
            "restaurant_id": {"type": "fk", "label": "Ресторан", "required": True, "ref": "restaurants"},
            "position_id": {"type": "fk", "label": "Должность", "required": True, "ref": "positions"},
            "full_name": {"type": "name", "label": "ФИО", "required": True, "min": 5, "max": 120},
            "phone": {"type": "phone", "label": "Телефон", "required": True, "encrypted": "phone_enc"},
            "hire_date": {"type": "date", "label": "Дата приёма", "required": True},
            "salary": {"type": "num", "label": "Зарплата, ₽", "required": True, "min": 1, "max": 1000000},
        },
        "list_sql": ("SELECT t.*, r.name AS restaurant_name, p.name AS position_name FROM employees t "
                     "JOIN restaurants r ON r.id=t.restaurant_id JOIN positions p ON p.id=t.position_id"),
        "search": ["t.full_name", "r.name", "p.name"],
        "filters": {"restaurant_id": ("t.restaurant_id", "="), "position_id": ("t.position_id", "=")},
        "order": "t.full_name",
    },
    "customers": {
        "title": "Клиенты", "table": "customers",
        "perms": {"read": ALL, "create": ALL, "update": ALL, "delete": MGR},
        "fields": {
            "full_name": {"type": "name", "label": "Имя клиента", "required": True, "min": 2, "max": 120},
            "phone": {"type": "phone", "label": "Телефон", "required": True, "encrypted": "phone_enc",
                      "blind_index": "phone_hmac"},
            "email": {"type": "email", "label": "E-mail", "encrypted": "email_enc"},
            "bonus_points": {"type": "int", "label": "Бонусы", "min": 0, "max": 1000000, "default": 0},
        },
        "list_sql": "SELECT * FROM customers t",
        "search": ["t.full_name"],
        "filters": {},
        "order": "t.full_name",
    },
    "users": {
        "title": "Пользователи", "table": "users",
        "perms": {"read": ADM, "create": ADM, "update": ADM, "delete": ADM},
        "fields": {
            "login": {"type": "str", "label": "Логин", "required": True, "min": 3, "max": 32,
                      "regex": LOGIN_RE.pattern, "regex_msg": "латиница, цифры, _ . -"},
            "role_id": {"type": "fk", "label": "Роль", "required": True, "ref": "roles"},
            "employee_id": {"type": "fk", "label": "Сотрудник", "ref": "employees"},
            "is_active": {"type": "bool", "label": "Активен"},
            "password": {"type": "password", "label": "Пароль", "required": True, "optional_on_update": True},
        },
        "list_sql": ("SELECT t.id, t.login, t.role_id, t.employee_id, t.is_active, t.created_at, "
                     "r.name AS role_name, e.full_name AS employee_name FROM users t "
                     "JOIN roles r ON r.id=t.role_id LEFT JOIN employees e ON e.id=t.employee_id"),
        "search": ["t.login", "e.full_name"],
        "filters": {"role_id": ("t.role_id", "=")},
        "order": "t.id",
        "hidden": ["password_hash"],
    },
}

ORDER_FIELDS = {
    "restaurant_id": {"type": "fk", "label": "Ресторан", "required": True},
    "employee_id": {"type": "fk", "label": "Кассир", "required": True},
    "customer_id": {"type": "fk", "label": "Клиент"},
    "order_type": {"type": "enum", "label": "Тип заказа", "required": True, "values": ORDER_TYPES},
    "payment_method": {"type": "enum", "label": "Оплата", "required": True, "values": PAYMENTS},
    "status": {"type": "enum", "label": "Статус", "values": STATUSES, "default": "новый"},
}


def _can(entity, action):
    return g.user["role"] in ENTITIES[entity]["perms"][action]


def _deny():
    audit("access_denied", entity=request.path[:100], user_id=g.user["id"], ip=request.remote_addr)
    return jsonify(error="Недостаточно прав для выполнения операции"), 403


def _row_out(entity, row):
    d = dict(row)
    spec = ENTITIES[entity]
    for name, f in spec["fields"].items():
        if f.get("encrypted"):
            col = f["encrypted"]
            try:
                d[name] = crypto.decrypt_field(d.pop(col, None), f"{spec['table']}.{col}")
            except Exception:
                d[name] = "‹ошибка расшифровки›"
        if f.get("blind_index"):
            d.pop(f["blind_index"], None)
    for h in spec.get("hidden", []):
        d.pop(h, None)
    return d


def _to_columns(entity, data):
    spec = ENTITIES[entity]
    cols = {}
    for name, v in data.items():
        f = spec["fields"][name]
        if f.get("encrypted"):
            cols[f["encrypted"]] = crypto.encrypt_field(v, f"{spec['table']}.{f['encrypted']}")
            if f.get("blind_index"):
                cols[f["blind_index"]] = crypto.blind_index(v) if v else None
        elif f["type"] == "password":
            probs = password_problems(v)
            if probs:
                raise ValidationError({"password": "Пароль: требуется " + ", ".join(probs)})
            cols["password_hash"] = crypto.hash_password(v)
        else:
            cols[name] = v
    return cols


def _admin_guard(uid, cols):
    """Защита от потери администрирования: администратор не может понизить или заблокировать себя."""
    admin_role = query("SELECT id FROM roles WHERE code='admin'", one=True)["id"]
    target = query("SELECT role_id, is_active FROM users WHERE id=?", (uid,), one=True)
    if not target:
        return None
    loses_admin = target["role_id"] == admin_role and target["is_active"] == 1 and \
        (cols.get("is_active") == 0 or ("role_id" in cols and cols["role_id"] != admin_role))
    if not loses_admin:
        return None
    if uid == g.user["id"]:     # действующий администратор всегда остаётся → система не останется без администратора
        return "Нельзя снять права администратора или заблокировать собственную учётную запись"
    return None


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError({"_": "Ожидается JSON-объект"})
    return data


def _db_error(e):
    msg = str(e)
    if "UNIQUE" in msg:
        return jsonify(error="Запись с таким значением уже существует"), 409
    if "FOREIGN KEY" in msg:
        return jsonify(error="Операция нарушает ссылочную целостность (есть связанные записи или ссылка не существует)"), 409
    if "CHECK" in msg:
        return jsonify(error="Значение не прошло проверку ограничений БД"), 400
    return jsonify(error="Ошибка базы данных"), 400


@bp.errorhandler(ValidationError)
def _val_err(e):
    return jsonify(error="Проверьте введённые данные", fields=e.errors), 400


# ------------------------------------------------------------------ метаданные для интерфейса
@bp.get("/meta")
@login_required
def meta():
    role = g.user["role"]
    ents = {}
    for k, s in ENTITIES.items():
        if role in s["perms"]["read"]:
            ents[k] = {"title": s["title"],
                       "can": {a: role in r for a, r in s["perms"].items()},
                       "fields": {n: {kk: vv for kk, vv in f.items() if kk not in ("encrypted", "blind_index")}
                                  for n, f in s["fields"].items()},
                       "filters": list(s["filters"].keys())}
    lookups = {
        "restaurants": [dict(r) for r in query("SELECT id, name, is_active FROM restaurants ORDER BY name")],
        "categories": [dict(r) for r in query("SELECT id, name FROM categories ORDER BY name")],
        "positions": [dict(r) for r in query("SELECT id, name FROM positions ORDER BY name")],
        "roles": [dict(r) for r in query("SELECT id, name FROM roles ORDER BY id")],
        "employees": [dict(r) for r in query("SELECT e.id, e.full_name AS name, e.restaurant_id, p.name AS position "
                                             "FROM employees e JOIN positions p ON p.id=e.position_id ORDER BY e.full_name")],
        "customers": [dict(r) for r in query("SELECT id, full_name AS name FROM customers ORDER BY full_name")],
        "menu_items": [dict(r) for r in query("SELECT id, name, price FROM menu_items WHERE is_available=1 ORDER BY name")],
    }
    me = query("SELECT u.employee_id, e.restaurant_id FROM users u LEFT JOIN employees e ON e.id=u.employee_id "
               "WHERE u.id=?", (g.user["id"],), one=True)
    return jsonify(role=role, entities=ents, lookups=lookups, me=dict(me) if me else {}, transitions={k: sorted(v) for k, v in TRANSITIONS.items()},
                   orders={"types": ORDER_TYPES, "payments": PAYMENTS, "statuses": STATUSES,
                           "can_delete": role in MGR})


# ------------------------------------------------------------------ универсальный CRUD
@bp.get("/<entity>")
@login_required
def list_rows(entity):
    if entity not in ENTITIES:
        return jsonify(error="Не найдено"), 404
    if not _can(entity, "read"):
        return _deny()
    s = ENTITIES[entity]
    where, params = [], []
    q = (request.args.get("q") or "").strip()[:100]
    if q:
        conds = [f"{c} LIKE ?" for c in s["search"]]
        params += [f"%{q}%"] * len(conds)
        # поиск по зашифрованному телефону — через «слепой индекс» HMAC
        for f in s["fields"].values():
            if f.get("blind_index") and normalize_phone(q):
                conds.append(f"t.{f['blind_index']} = ?")
                params.append(crypto.blind_index(normalize_phone(q)))
        where.append("(" + " OR ".join(conds) + ")")
    for key, (col, op) in s["filters"].items():
        v = request.args.get(key)
        if v not in (None, ""):
            where.append(f"{col} {op} ?")      # имя столбца и оператор — только из белого списка
            params.append(v[:50])
    sql = s["list_sql"] + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {s['order']} LIMIT 500"
    rows = [_row_out(entity, r) for r in query(sql, params)]
    return jsonify(rows=rows, count=len(rows))


@bp.post("/<entity>")
@login_required
def create_row(entity):
    if entity not in ENTITIES:
        return jsonify(error="Не найдено"), 404
    if not _can(entity, "create"):
        return _deny()
    data = clean(ENTITIES[entity]["fields"], _json_body())
    if entity == "customers" and g.user["role"] == "cashier":
        data["bonus_points"] = 0            # начальный баланс задаёт система, а не кассир
    cols = _to_columns(entity, data)
    names = list(cols)
    try:
        cur = get_db().execute(
            f"INSERT INTO {ENTITIES[entity]['table']} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
            [cols[n] for n in names])
        get_db().commit()
    except sqlite3.IntegrityError as e:
        return _db_error(e)
    audit("create", entity, cur.lastrowid, g.user["id"], request.remote_addr)
    return jsonify(id=cur.lastrowid, message="Запись добавлена"), 201


@bp.put("/<entity>/<int:rid>")
@login_required
def update_row(entity, rid):
    if entity not in ENTITIES:
        return jsonify(error="Не найдено"), 404
    if not _can(entity, "update"):
        return _deny()
    data = clean(ENTITIES[entity]["fields"], _json_body(), partial=True)
    if entity == "customers" and "bonus_points" in data and g.user["role"] == "cashier":
        cur_b = query("SELECT bonus_points FROM customers WHERE id=?", (rid,), one=True)
        if cur_b and data["bonus_points"] != cur_b["bonus_points"]:
            return jsonify(error="Изменять бонусный баланс вручную может только управляющий или администратор"), 403
    if entity == "users" and not data.get("password"):
        data.pop("password", None)
    cols = _to_columns(entity, {k: v for k, v in data.items()})
    if not cols:
        raise ValidationError({"_": "Нет данных для изменения"})
    if entity == "users":
        err = _admin_guard(rid, cols)
        if err:
            return jsonify(error=err), 400
    try:
        cur = get_db().execute(
            f"UPDATE {ENTITIES[entity]['table']} SET {', '.join(f'{c}=?' for c in cols)} WHERE id=?",
            [*cols.values(), rid])
        get_db().commit()
    except sqlite3.IntegrityError as e:
        return _db_error(e)
    if cur.rowcount == 0:
        return jsonify(error="Запись не найдена"), 404
    if entity == "users" and ("password_hash" in cols or cols.get("is_active") == 0):
        get_db().execute("DELETE FROM sessions WHERE user_id=?", (rid,))   # завершить сессии пользователя
        get_db().commit()
    audit("update", entity, rid, g.user["id"], request.remote_addr)
    return jsonify(message="Изменения сохранены")


@bp.delete("/<entity>/<int:rid>")
@login_required
def delete_row(entity, rid):
    if entity not in ENTITIES:
        return jsonify(error="Не найдено"), 404
    if not _can(entity, "delete"):
        return _deny()
    if entity == "users" and rid == g.user["id"]:
        return jsonify(error="Нельзя удалить собственную учётную запись"), 400
    if entity == "users":
        err = _admin_guard(rid, {"is_active": 0})
        if err:
            return jsonify(error=err), 400
    try:
        cur = get_db().execute(f"DELETE FROM {ENTITIES[entity]['table']} WHERE id=?", (rid,))
        get_db().commit()
    except sqlite3.IntegrityError as e:
        return _db_error(e)
    if cur.rowcount == 0:
        return jsonify(error="Запись не найдена"), 404
    audit("delete", entity, rid, g.user["id"], request.remote_addr)
    return jsonify(message="Запись удалена")


# ------------------------------------------------------------------ заказы (составная сущность)
# сумма считается только для отобранных заказов (по индексу PK order_items), а не по всей таблице
ORDER_LIST = ("SELECT o.*, r.name AS restaurant_name, e.full_name AS employee_name, c.full_name AS customer_name, "
              "(SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) FROM order_items oi WHERE oi.order_id = o.id) AS total, "
              "(SELECT COALESCE(SUM(oi.quantity), 0) FROM order_items oi WHERE oi.order_id = o.id) AS items_count "
              "FROM orders o JOIN restaurants r ON r.id=o.restaurant_id JOIN employees e ON e.id=o.employee_id "
              "LEFT JOIN customers c ON c.id=o.customer_id")


@bp.get("/orders")
@login_required
def orders_list():
    where, params = [], []
    q = (request.args.get("q") or "").strip()[:100]
    if q:
        if q.isdigit():
            where.append("o.id = ?")
            params.append(int(q))
        else:
            where.append("(c.full_name LIKE ? OR e.full_name LIKE ? OR r.name LIKE ?)")
            params += [f"%{q}%"] * 3
    for key, col, op in (("restaurant_id", "o.restaurant_id", "="), ("status", "o.status", "="),
                         ("order_type", "o.order_type", "="), ("date_from", "date(o.created_at)", ">="),
                         ("date_to", "date(o.created_at)", "<=")):
        v = request.args.get(key)
        if v:
            where.append(f"{col} {op} ?")
            params.append(v[:30])
    sql = ORDER_LIST + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY o.created_at DESC LIMIT 500"
    return jsonify(rows=[dict(r) for r in query(sql, params)])


@bp.get("/orders/<int:oid>")
@login_required
def order_get(oid):
    o = query(ORDER_LIST + " WHERE o.id=?", (oid,), one=True)
    if not o:
        return jsonify(error="Заказ не найден"), 404
    items = query("SELECT oi.menu_item_id, m.name, oi.quantity, oi.unit_price, oi.quantity*oi.unit_price AS sum "
                  "FROM order_items oi JOIN menu_items m ON m.id=oi.menu_item_id WHERE oi.order_id=?", (oid,))
    return jsonify(order=dict(o), items=[dict(i) for i in items])


def _check_employee(restaurant_id, employee_id):
    r = query("SELECT is_active FROM restaurants WHERE id=?", (restaurant_id,), one=True)
    if not r:
        raise ValidationError({"restaurant_id": "Ресторан: не найден"})
    if not r["is_active"]:
        raise ValidationError({"restaurant_id": "Ресторан: точка не работает, приём заказов невозможен"})
    e = query("SELECT restaurant_id FROM employees WHERE id=?", (employee_id,), one=True)
    if not e:
        raise ValidationError({"employee_id": "Кассир: сотрудник не найден"})
    if e["restaurant_id"] != restaurant_id:
        raise ValidationError({"employee_id": "Кассир: сотрудник работает в другом ресторане"})


def _clean_items(raw):
    if not isinstance(raw, list) or not raw or len(raw) > 30:
        raise ValidationError({"items": "Добавьте в заказ от 1 до 30 позиций"})
    items = {}
    for it in raw:
        try:
            mid, qty = int(it["menu_item_id"]), int(it["quantity"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError({"items": "Некорректная позиция заказа"})
        if not 1 <= qty <= 50:
            raise ValidationError({"items": "Количество — от 1 до 50"})
        items[mid] = items.get(mid, 0) + qty
    return items


@bp.post("/orders")
@login_required
def order_create():
    body = _json_body()
    data = clean(ORDER_FIELDS, body)
    data["status"] = "новый"                 # новый заказ всегда начинается со статуса «новый»
    items = _clean_items(body.get("items"))
    _check_employee(data["restaurant_id"], data["employee_id"])
    db = get_db()
    try:
        cur = db.execute("INSERT INTO orders(restaurant_id, employee_id, customer_id, order_type, payment_method, status) "
                         "VALUES (?,?,?,?,?,?)", (data["restaurant_id"], data["employee_id"], data.get("customer_id"),
                                                  data["order_type"], data["payment_method"], data["status"]))
        oid = cur.lastrowid
        for mid, qty in items.items():
            m = db.execute("SELECT price FROM menu_items WHERE id=? AND is_available=1", (mid,)).fetchone()
            if not m:
                db.rollback()
                raise ValidationError({"items": f"Позиция меню #{mid} недоступна"})
            db.execute("INSERT INTO order_items(order_id, menu_item_id, quantity, unit_price) VALUES (?,?,?,?)",
                       (oid, mid, qty, m["price"]))
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return _db_error(e)
    audit("create", "orders", oid, g.user["id"], request.remote_addr)
    return jsonify(id=oid, message=f"Заказ №{oid} оформлен"), 201


@bp.put("/orders/<int:oid>")
@login_required
def order_update(oid):
    body = _json_body()
    data = clean(ORDER_FIELDS, body, partial=True)
    data = {k: v for k, v in data.items() if v is not None or k == "customer_id"}
    db = get_db()
    cur_o = query("SELECT restaurant_id, employee_id, customer_id, status FROM orders WHERE id=?", (oid,), one=True)
    if not cur_o:
        return jsonify(error="Заказ не найден"), 404
    old_status, new_status = cur_o["status"], data.get("status") or cur_o["status"]
    if old_status in ("выдан", "отменён") and (set(data) - {"status"} or "items" in body or new_status != old_status):
        raise ValidationError({"status": f"Статус: заказ в статусе «{old_status}» изменять нельзя"})
    if new_status != old_status and new_status not in TRANSITIONS[old_status]:
        raise ValidationError({"status": f"Статус: переход «{old_status}» → «{new_status}» недопустим"})
    if "items" in body and old_status != "новый":
        raise ValidationError({"items": "Состав можно менять только у заказа в статусе «новый»"})
    if "restaurant_id" in data or "employee_id" in data:
        _check_employee(data.get("restaurant_id") or cur_o["restaurant_id"], data.get("employee_id") or cur_o["employee_id"])
    try:
        if data:
            db.execute(f"UPDATE orders SET {', '.join(f'{k}=?' for k in data)} WHERE id=?", [*data.values(), oid])
        if "items" in body:
            items = _clean_items(body["items"])
            old = {r["menu_item_id"]: r["unit_price"] for r in
                   db.execute("SELECT menu_item_id, unit_price FROM order_items WHERE order_id=?", (oid,))}
            db.execute("DELETE FROM order_items WHERE order_id=?", (oid,))
            for mid, qty in items.items():
                price = old.get(mid)
                if price is None:
                    m = db.execute("SELECT price FROM menu_items WHERE id=? AND is_available=1", (mid,)).fetchone()
                    if not m:
                        db.rollback()
                        raise ValidationError({"items": f"Позиция меню #{mid} недоступна"})
                    price = m["price"]
                db.execute("INSERT INTO order_items VALUES (?,?,?,?)", (oid, mid, qty, price))
        bonus = 0
        customer = data["customer_id"] if "customer_id" in data else cur_o["customer_id"]
        if new_status == "выдан" and old_status != "выдан" and customer:
            total = db.execute("SELECT total FROM v_order_totals WHERE order_id=?", (oid,)).fetchone()["total"]
            bonus = int(total * BONUS_RATE)
            db.execute("UPDATE customers SET bonus_points = bonus_points + ? WHERE id=?", (bonus, customer))
        db.commit()
    except sqlite3.IntegrityError as e:
        db.rollback()
        return _db_error(e)
    audit("update", "orders", oid, g.user["id"], request.remote_addr)
    return jsonify(message="Заказ обновлён" + (f"; клиенту начислено {bonus} бонусов" if bonus else ""))


@bp.delete("/orders/<int:oid>")
@login_required
def order_delete(oid):
    if g.user["role"] not in MGR:
        return _deny()
    cur = get_db().execute("DELETE FROM orders WHERE id=?", (oid,))
    get_db().commit()
    if cur.rowcount == 0:
        return jsonify(error="Заказ не найден"), 404
    audit("delete", "orders", oid, g.user["id"], request.remote_addr)
    return jsonify(message="Заказ удалён")
