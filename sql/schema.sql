-- =====================================================================
--  АИС учёта заказов сети ресторанов «Вкусно и быстро»
--  Скрипт создания базы данных (СУБД SQLite 3)
--  Автор: Скворцова А. Д., группа НБИбд-01-24, индивидуальная тема №3
--  Модель приведена к 3НФ: каждый неключевой атрибут зависит
--  только от первичного ключа своей таблицы; производные значения
--  (сумма заказа) не хранятся, а вычисляются представлением v_order_totals.
-- =====================================================================
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;          -- параллельное чтение во время записи

-- ---------- Справочники ---------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER PRIMARY KEY,
    code        TEXT    NOT NULL UNIQUE CHECK (code IN ('admin','manager','cashier')),
    name        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS restaurants (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 2 AND 100),
    city        TEXT    NOT NULL CHECK (length(city) BETWEEN 2 AND 60),
    address     TEXT    NOT NULL CHECK (length(address) BETWEEN 5 AND 200),
    phone       TEXT    NOT NULL CHECK (length(phone) BETWEEN 10 AND 20),
    opened_on   TEXT    NOT NULL CHECK (date(opened_on) IS NOT NULL),
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1))
);

CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 2 AND 60),
    base_salary NUMERIC NOT NULL CHECK (base_salary > 0)
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 2 AND 60)
);

-- ---------- Основные таблицы ----------------------------------------
CREATE TABLE IF NOT EXISTS menu_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    name         TEXT    NOT NULL UNIQUE CHECK (length(name) BETWEEN 2 AND 100),
    price        NUMERIC NOT NULL CHECK (price > 0 AND price <= 10000),
    calories     INTEGER NOT NULL CHECK (calories BETWEEN 0 AND 5000),
    is_available INTEGER NOT NULL DEFAULT 1 CHECK (is_available IN (0,1))
);

CREATE TABLE IF NOT EXISTS employees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    position_id   INTEGER NOT NULL REFERENCES positions(id)   ON UPDATE CASCADE ON DELETE RESTRICT,
    full_name     TEXT    NOT NULL CHECK (length(full_name) BETWEEN 5 AND 120),
    phone_enc     TEXT    NOT NULL,              -- AES-256-GCM (конфиденциально)
    hire_date     TEXT    NOT NULL CHECK (date(hire_date) IS NOT NULL),
    salary        NUMERIC NOT NULL CHECK (salary > 0)
);

CREATE TABLE IF NOT EXISTS customers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL CHECK (length(full_name) BETWEEN 2 AND 120),
    phone_enc     TEXT    NOT NULL,              -- AES-256-GCM (конфиденциально)
    phone_hmac    TEXT    NOT NULL UNIQUE,       -- HMAC-SHA256 для поиска и уникальности
    email_enc     TEXT,                          -- AES-256-GCM (конфиденциально)
    bonus_points  INTEGER NOT NULL DEFAULT 0 CHECK (bonus_points >= 0),
    registered_at TEXT    NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id  INTEGER NOT NULL REFERENCES restaurants(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    employee_id    INTEGER NOT NULL REFERENCES employees(id)   ON UPDATE CASCADE ON DELETE RESTRICT,
    customer_id    INTEGER          REFERENCES customers(id)   ON UPDATE CASCADE ON DELETE SET NULL,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    order_type     TEXT    NOT NULL CHECK (order_type IN ('в зале','с собой','доставка')),
    payment_method TEXT    NOT NULL CHECK (payment_method IN ('наличные','карта','СБП')),
    status         TEXT    NOT NULL DEFAULT 'новый' CHECK (status IN ('новый','готовится','готов','выдан','отменён'))
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id     INTEGER NOT NULL REFERENCES orders(id)     ON UPDATE CASCADE ON DELETE CASCADE,
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON UPDATE CASCADE ON DELETE RESTRICT,
    quantity     INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 50),
    unit_price   NUMERIC NOT NULL CHECK (unit_price > 0),  -- цена на момент продажи (историческая)
    PRIMARY KEY (order_id, menu_item_id)
);

-- ---------- Безопасность --------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    login         TEXT    NOT NULL UNIQUE COLLATE NOCASE CHECK (length(login) BETWEEN 3 AND 32),
    password_hash TEXT    NOT NULL,              -- pbkdf2_sha256$итерации$соль$хеш
    role_id       INTEGER NOT NULL REFERENCES roles(id),
    employee_id   INTEGER UNIQUE REFERENCES employees(id) ON DELETE SET NULL,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash    TEXT    PRIMARY KEY,           -- SHA-256 от идентификатора сессии
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,  -- NULL = гостевая сессия
    csrf_token    TEXT    NOT NULL,
    created_at    REAL    NOT NULL,
    last_activity REAL    NOT NULL,
    ip            TEXT,
    user_agent    TEXT
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    login     TEXT    NOT NULL COLLATE NOCASE,
    ip        TEXT,
    ts        REAL    NOT NULL,
    success   INTEGER NOT NULL CHECK (success IN (0,1))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT    NOT NULL,
    entity     TEXT,
    entity_id  INTEGER,
    ip         TEXT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ---------- Индексы --------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_orders_created    ON orders(created_at);
CREATE INDEX IF NOT EXISTS ix_orders_status     ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS ix_orders_restaurant ON orders(restaurant_id);
CREATE INDEX IF NOT EXISTS ix_employees_rest    ON employees(restaurant_id);
CREATE INDEX IF NOT EXISTS ix_menu_category     ON menu_items(category_id);
CREATE INDEX IF NOT EXISTS ix_attempts_login    ON login_attempts(login, ts);

-- ---------- Представления --------------------------------------------
CREATE VIEW IF NOT EXISTS v_order_totals AS
SELECT o.id AS order_id,
       COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total,
       COALESCE(SUM(oi.quantity), 0)                  AS items_count
FROM orders o LEFT JOIN order_items oi ON oi.order_id = o.id
GROUP BY o.id;
