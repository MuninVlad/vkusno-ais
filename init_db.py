"""Создание и заполнение БД тестовыми данными.

    python init_db.py          — создать БД (если нет) и заполнить данными
    python init_db.py --reset  — удалить БД и создать заново

После заполнения формируется sql/seed.sql — SQL-скрипт заполнения с уже
зашифрованными значениями для текущего ключа instance/data.key."""
import random
import sys
from datetime import date, datetime, timedelta

from app import accounts, config, crypto
from app.db import connect

RESTAURANTS = [
    ("Тверская", "Москва", "ул. Тверская, д. 12", "+74951000101", "2019-03-15"),
    ("Арбат", "Москва", "ул. Арбат, д. 24", "+74951000102", "2019-09-01"),
    ("Таганка", "Москва", "Таганская пл., д. 3", "+74951000103", "2020-06-20"),
    ("Миклухо-Маклая", "Москва", "ул. Миклухо-Маклая, д. 8", "+74951000104", "2021-02-10"),
    ("Невский", "Санкт-Петербург", "Невский пр., д. 45", "+78121000201", "2020-04-05"),
    ("Петроградская", "Санкт-Петербург", "Большой пр. П.С., д. 60", "+78121000202", "2022-08-12"),
    ("Баумана", "Казань", "ул. Баумана, д. 17", "+78431000301", "2021-05-30"),
    ("Плотинка", "Екатеринбург", "пр. Ленина, д. 36", "+73431000401", "2022-11-01"),
    ("Красный проспект", "Новосибирск", "Красный пр., д. 25", "+73831000501", "2023-03-18"),
    ("Покровка", "Нижний Новгород", "ул. Большая Покровская, д. 9", "+78311000601", "2023-09-09", 0),
]
POSITIONS = [("Управляющий рестораном", 95000), ("Кассир", 52000), ("Повар", 60000),
             ("Курьер", 48000), ("Менеджер смены", 70000), ("Старший кассир", 58000), ("Су-шеф", 75000),
             ("Бариста", 50000), ("Администратор зала", 65000), ("Уборщик", 40000)]
CATEGORIES = ["Бургеры", "Роллы и сэндвичи", "Картофель и закуски", "Салаты", "Напитки", "Десерты",
              "Завтраки", "Соусы", "Комбо-наборы", "Детское меню"]
MENU = [
    ("Бургеры", "Гранд Бургер", 289, 520), ("Бургеры", "Чизбургер", 99, 300), ("Бургеры", "Двойной Чизбургер", 189, 450),
    ("Бургеры", "Биг Спешиал", 329, 640), ("Бургеры", "Чикен Бургер", 149, 390),
    ("Роллы и сэндвичи", "Цезарь Ролл", 229, 480), ("Роллы и сэндвичи", "Фиш Бургер", 199, 330),
    ("Картофель и закуски", "Картофель фри (ср.)", 109, 340), ("Картофель и закуски", "Картофель по-деревенски", 119, 315),
    ("Картофель и закуски", "Наггетсы (6 шт.)", 159, 290), ("Картофель и закуски", "Стрипсы (3 шт.)", 179, 320),
    ("Салаты", "Салат овощной", 129, 60), ("Салаты", "Салат Цезарь", 239, 280),
    ("Напитки", "Кофе Капучино", 139, 120), ("Напитки", "Чай чёрный", 69, 0), ("Напитки", "Морс клюквенный", 99, 110),
    ("Напитки", "Молочный коктейль", 159, 330), ("Десерты", "Пирожок вишнёвый", 79, 250),
    ("Десерты", "Мороженое в рожке", 59, 150), ("Десерты", "Чизкейк", 169, 390, 0),
    ("Завтраки", "Омлет с ветчиной", 149, 310), ("Завтраки", "Сырники со сметаной", 159, 360),
    ("Соусы", "Соус сырный", 39, 90), ("Соусы", "Соус кисло-сладкий", 39, 70),
    ("Комбо-наборы", "Комбо Гранд", 449, 1100), ("Детское меню", "Детский набор", 259, 520),
]
LAST = ["Иванов", "Смирнова", "Кузнецов", "Попова", "Васильев", "Петрова", "Соколов", "Михайлова", "Новиков",
        "Фёдорова", "Морозов", "Волкова", "Алексеев", "Лебедева", "Семёнов", "Егорова", "Павлов", "Козлова",
        "Степанов", "Николаева", "Орлов", "Андреева", "Макаров", "Захарова", "Никитин", "Зайцева", "Соловьёв",
        "Борисова", "Яковлев", "Григорьева"]
FIRST_M = ["Алексей", "Дмитрий", "Сергей", "Андрей", "Максим", "Илья", "Кирилл", "Олег"]
FIRST_F = ["Анна", "Мария", "Елена", "Ольга", "Дарья", "Ксения", "Полина", "Виктория"]
MID_M = ["Сергеевич", "Андреевич", "Игоревич", "Олегович"]
MID_F = ["Сергеевна", "Андреевна", "Игоревна", "Олеговна"]
CUSTOMERS = ["Артём Белов", "Светлана Гусева", "Никита Киселёв", "Алина Тихонова", "Роман Комаров",
             "Юлия Широкова", "Тимур Галиев", "Екатерина Власова", "Глеб Фомин", "Вероника Ершова",
             "Павел Данилов", "Наталья Жукова", "Денис Абрамов", "Марина Ковалёва", "Игорь Сафонов"]



def person(i):
    female = LAST[i % len(LAST)].endswith("а")
    first = (FIRST_F if female else FIRST_M)[i % 8]
    mid = (MID_F if female else MID_M)[i % 4]
    return f"{LAST[i % len(LAST)]} {first} {mid}"


def seed(conn):
    rnd = random.Random(2026)
    cur = conn.cursor()
    cur.executemany("INSERT INTO roles(id, code, name) VALUES (?,?,?)",
                    [(1, "admin", "Администратор"), (2, "manager", "Управляющий рестораном"), (3, "cashier", "Кассир")])
    for r in RESTAURANTS:
        cur.execute("INSERT INTO restaurants(name, city, address, phone, opened_on, is_active) VALUES (?,?,?,?,?,?)",
                    (*r[:5], r[5] if len(r) > 5 else 1))
    cur.executemany("INSERT INTO positions(name, base_salary) VALUES (?,?)", POSITIONS)
    cur.executemany("INSERT INTO categories(name) VALUES (?)", [(c,) for c in CATEGORIES])
    cat_id = {r[1]: r[0] for r in cur.execute("SELECT id, name FROM categories")}
    for m in MENU:
        cur.execute("INSERT INTO menu_items(category_id, name, price, calories, is_available) VALUES (?,?,?,?,?)",
                    (cat_id[m[0]], m[1], m[2], m[3], m[4] if len(m) > 4 else 1))
    # сотрудники: в каждом ресторане управляющий, 2 кассира, повар (+ курьер в Москве)
    emp = 0
    cashiers = {}
    for rid in range(1, len(RESTAURANTS) + 1):
        staff = [1, 2, 2, 3, 6 + (rid - 1) % 5] + ([4] if rid <= 4 else [])
        for pos in staff:
            hire = date(2019, 1, 1) + timedelta(days=rnd.randint(200, 2400))
            salary = POSITIONS[pos - 1][1] + rnd.choice([0, 2000, 5000, 8000])
            phone = f"+79{rnd.randint(100000000, 999999999)}"
            cur.execute("INSERT INTO employees(restaurant_id, position_id, full_name, phone_enc, hire_date, salary) "
                        "VALUES (?,?,?,?,?,?)", (rid, pos, person(emp), crypto.encrypt_field(phone, "employees.phone_enc"),
                                                 hire.isoformat(), salary))
            if pos == 2:
                cashiers.setdefault(rid, []).append(cur.lastrowid)
            emp += 1
    # учётные записи: пароли — из instance/accounts.json (генерируются при первой установке)
    pw = accounts.passwords()
    for login, role, rid, pos in accounts.SPEC:
        emp_id = None
        if rid:
            emp_id = cur.execute("SELECT id FROM employees WHERE restaurant_id=? AND position_id=? ORDER BY id LIMIT 1",
                                 (rid, pos)).fetchone()[0]
        cur.execute("INSERT INTO users(login, password_hash, role_id, employee_id) VALUES (?,?,?,?)",
                    (login, crypto.hash_password(pw[login]), {"admin": 1, "manager": 2, "cashier": 3}[role], emp_id))
    for i, name in enumerate(CUSTOMERS):
        phone = f"+7916{rnd.randint(1000000, 9999999)}"
        email = None if i % 4 == 3 else f"client{i + 1}@example.ru"
        cur.execute("INSERT INTO customers(full_name, phone_enc, phone_hmac, email_enc, bonus_points, registered_at) "
                    "VALUES (?,?,?,?,?,?)", (name, crypto.encrypt_field(phone, "customers.phone_enc"),
                                             crypto.blind_index(phone), crypto.encrypt_field(email, "customers.email_enc"),
                                             rnd.randint(0, 2500), (date.today() - timedelta(days=rnd.randint(30, 600))).isoformat()))
    # заказы за последние 60 дней
    menu = [(r[0], r[1]) for r in cur.execute("SELECT id, price FROM menu_items WHERE is_available=1")]
    active = [i + 1 for i, r in enumerate(RESTAURANTS) if (r[5] if len(r) > 5 else 1)]
    now = datetime.now().replace(second=0, microsecond=0)
    for _ in range(320):
        rid = rnd.choice(active)
        created = now - timedelta(days=rnd.randint(0, 59), hours=rnd.randint(0, 11), minutes=rnd.randint(0, 59))
        age = (now - created).total_seconds() / 3600
        status = rnd.choices(["выдан", "отменён"], [94, 6])[0] if age > 2 else rnd.choice(["новый", "готовится", "готов"])
        cur.execute("INSERT INTO orders(restaurant_id, employee_id, customer_id, created_at, order_type, payment_method, status) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (rid, rnd.choice(cashiers[rid]), rnd.choice([None, None] + list(range(1, len(CUSTOMERS) + 1))),
                     created.strftime("%Y-%m-%d %H:%M:%S"), rnd.choices(["в зале", "с собой", "доставка"], [5, 3, 2])[0],
                     rnd.choices(["карта", "СБП", "наличные"], [6, 3, 1])[0], status))
        oid = cur.lastrowid
        for mid, price in rnd.sample(menu, rnd.randint(1, 4)):
            cur.execute("INSERT INTO order_items VALUES (?,?,?,?)", (oid, mid, rnd.choices([1, 2, 3], [7, 2, 1])[0], price))
    conn.commit()


def dump_seed(conn):
    tables = ["roles", "restaurants", "positions", "categories", "menu_items", "employees", "customers",
              "users", "orders", "order_items"]
    lines = ["-- Скрипт заполнения БД тестовыми данными (сформирован init_db.py).",
             "-- Поля *_enc зашифрованы AES-256-GCM ключом instance/data.key; password_hash — PBKDF2.",
             "-- Без того же ключа зашифрованные значения не расшифруются: для новой установки",
             "-- используйте `python init_db.py --reset`.", "PRAGMA foreign_keys = ON;", "BEGIN;"]
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
        lines.append(f"\n-- {t}")
        for row in conn.execute(f"SELECT * FROM {t}"):
            vals = ", ".join("NULL" if v is None else (str(v) if isinstance(v, (int, float)) else
                                                         "'" + str(v).replace("'", "''") + "'") for v in row)
            lines.append(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({vals});")
    lines.append("COMMIT;")
    (config.BASE_DIR / "sql" / "seed.sql").write_text("\n".join(lines) + "\n", "utf-8")


def main():
    config.INSTANCE_DIR.mkdir(exist_ok=True)
    if "--reset" in sys.argv and config.DB_PATH.exists():
        config.DB_PATH.unlink()
    fresh = not config.DB_PATH.exists()
    conn = connect()
    conn.executescript((config.BASE_DIR / "sql" / "schema.sql").read_text("utf-8"))
    if fresh or conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
        seed(conn)
        dump_seed(conn)
        print("База данных создана и заполнена:", config.DB_PATH)
        print("Пароли учётных записей:", accounts.PATH)
    else:
        print("База данных уже существует:", config.DB_PATH)
    for t in ("restaurants", "positions", "categories", "employees", "menu_items", "customers", "orders", "order_items", "users"):
        print(f"  {t:12s} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
