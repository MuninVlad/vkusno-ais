/* Обработчик запросов рабочего модуля в браузере (версия для GitHub Pages).
   Повторяет логику серверного API: права ролей, проверка данных, ограничения целостности,
   правила статусов заказа, бонусы, отчёты. */
(function () {
  "use strict";
  var ALL = ["admin", "manager", "cashier"];
  var STATUSES = ["новый", "готовится", "готов", "выдан", "отменён"];
  var TRANSITIONS = { "новый": ["готовится", "отменён"], "готовится": ["готов", "отменён"], "готов": ["выдан"], "выдан": [], "отменён": [] };
  var ORDER_TYPES = ["в зале", "с собой", "доставка"], PAYMENTS = ["наличные", "карта", "СБП"];
  var BONUS_RATE = 0.05;

  function Err(status, error, fields) { this.status = status; this.error = error; this.fields = fields; }
  function vErr(fields) { return new Err(400, "Проверьте введённые данные", fields); }

  // ---------------------------------------------------------------- проверка данных
  var NAME_RE = /^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё .'\-]*$/, EMAIL_RE = /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/;
  function normPhone(v) {
    var d = String(v).replace(/\D/g, "");
    if (d.length === 11 && /^[78]/.test(d)) d = "7" + d.slice(1); else if (d.length === 10) d = "7" + d; else return null;
    return "+" + d;
  }
  function validDate(v) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
    var d = new Date(v + "T00:00:00Z");
    return !isNaN(d) && d.toISOString().slice(0, 10) === v && v >= "2000-01-01" && v <= "2100-01-01";
  }
  function clean(spec, raw, partial) {
    var out = {}, errs = {};
    Object.keys(spec).forEach(function (n) {
      var f = spec[n];
      if (f.readonly) return;
      var present = Object.prototype.hasOwnProperty.call(raw, n);
      if (partial && !present) return;
      var v = raw[n];
      if (typeof v === "string") v = v.trim();
      if (v === null || v === undefined || v === "") {
        if (f.required && !(f.optional_on_update && partial)) errs[n] = "Обязательное поле";
        else out[n] = f.type === "bool" ? 0 : (partial ? null : (f.default !== undefined ? f.default : null));
        return;
      }
      var lab = f.label || n, s;
      if (f.type === "str" || f.type === "name") {
        s = String(v); var lo = f.min || 1, hi = f.max || 200;
        if (s.length < lo || s.length > hi) errs[n] = lab + ": длина от " + lo + " до " + hi + " символов";
        else if (f.type === "name" && !NAME_RE.test(s)) errs[n] = lab + ": только буквы, пробел, дефис";
        else if (/[<>]/.test(s)) errs[n] = lab + ": недопустимые символы < >";
        else if (f.regex && !(new RegExp(f.regex)).test(s)) errs[n] = lab + ": " + (f.regex_msg || "неверный формат");
        else out[n] = s;
      } else if (f.type === "int" || f.type === "fk") {
        if (typeof v === "boolean" || !/^-?\d+$/.test(String(v))) errs[n] = lab + ": целое число";
        else if (f.type === "int" && (+v < f.min || +v > f.max)) errs[n] = lab + ": от " + f.min + " до " + f.max;
        else out[n] = parseInt(v, 10);
      } else if (f.type === "num") {
        var x = Number(String(v).replace(",", "."));
        if (!isFinite(x) || x < (f.min || 0) || x > (f.max || 1e9) || !/^-?\d+([.,]\d+)?$/.test(String(v))) errs[n] = lab + ": число от " + f.min + " до " + f.max;
        else out[n] = Math.round(x * 100) / 100;
      } else if (f.type === "date") {
        if (!validDate(String(v))) errs[n] = lab + ": неверное значение"; else out[n] = String(v);
      } else if (f.type === "bool") {
        out[n] = (v === true || v === 1 || v === "1" || v === "true" || v === "on") ? 1 : 0;
      } else if (f.type === "enum") {
        if (f.values.indexOf(v) < 0) errs[n] = lab + ": недопустимое значение"; else out[n] = v;
      } else if (f.type === "phone") {
        s = normPhone(v); if (!s) errs[n] = lab + ": телефон в формате +7XXXXXXXXXX"; else out[n] = s;
      } else if (f.type === "email") {
        s = String(v); if (s.length > 120 || !EMAIL_RE.test(s)) errs[n] = lab + ": некорректный e-mail"; else out[n] = s;
      } else if (f.type === "password") out[n] = String(v);
    });
    if (Object.keys(errs).length) throw vErr(errs);
    return out;
  }
  function pwProblems(pw) {
    var p = [];
    if (pw.length < 8) p.push("не менее 8 символов");
    if (pw.length > 128) p.push("не более 128 символов");
    if (!/[a-zа-яё]/.test(pw)) p.push("строчная буква");
    if (!/[A-ZА-ЯЁ]/.test(pw)) p.push("заглавная буква");
    if (!/\d/.test(pw)) p.push("цифра");
    return p;
  }

  // ---------------------------------------------------------------- данные
  var db = null, me = null, dk = null;
  function byId(table, id) { return db[table].filter(function (r) { return r.id === id; })[0]; }
  function nextId(table) { db.seq[table] = (db.seq[table] || 0) + 1; return db.seq[table]; }
  function like(v, q) { return String(v || "").toLowerCase().indexOf(q.toLowerCase()) >= 0; }
  function nm(table, id, field) { var r = byId(table, id); return r ? r[field || "name"] : null; }

  var JOINS = {
    menu_items: function (r) { r.category_name = nm("categories", r.category_id); return r; },
    employees: function (r) { r.restaurant_name = nm("restaurants", r.restaurant_id); r.position_name = nm("positions", r.position_id); return r; },
    users: function (r) {
      var o = { id: r.id, login: r.login, role_id: r.role_id, employee_id: r.employee_id, is_active: r.is_active, created_at: r.created_at };
      o.role_name = nm("roles", r.role_id); o.employee_name = r.employee_id ? nm("employees", r.employee_id, "full_name") : null; return o;
    },
  };
  var SEARCH = { restaurants: ["name", "city", "address"], categories: ["name"], menu_items: ["name", "category_name"], positions: ["name"],
                 employees: ["full_name", "restaurant_name", "position_name"], customers: ["full_name"], users: ["login", "employee_name"] };
  var FILTERS = { city: ["city", "="], is_active: ["is_active", "="], category_id: ["category_id", "="], is_available: ["is_available", "="],
                  price_min: ["price", ">="], price_max: ["price", "<="], restaurant_id: ["restaurant_id", "="], position_id: ["position_id", "="],
                  role_id: ["role_id", "="] };
  var SORT = { restaurants: ["id"], categories: ["name"], menu_items: ["category_name", "name"], positions: ["id"], employees: ["full_name"],
               customers: ["full_name"], users: ["id"] };
  function cmp(keys) { return function (a, b) { for (var i = 0; i < keys.length; i++) { var x = a[keys[i]], y = b[keys[i]]; if (x < y) return -1; if (x > y) return 1; } return 0; }; }
  function pass(row, key, val) {
    var f = FILTERS[key], v = row[f[0]];
    if (f[1] === "=") return String(v) === String(val);
    if (f[1] === ">=") return Number(v) >= Number(val);
    return Number(v) <= Number(val);
  }
  function can(entity, action) { return db.meta.entities[entity].perms[action].indexOf(me.role) >= 0; }
  function deny() { audit("access_denied"); throw new Err(403, "Недостаточно прав для выполнения операции"); }
  function audit(action, entity, id) { window.VBStore.audit(db, me.user_id, action, entity, id); }

  // ограничения уникальности и ссылочной целостности (как в schema.sql)
  var UNIQUE = { restaurants: ["name"], positions: ["name"], categories: ["name"], menu_items: ["name"], customers: ["phone"], users: ["login", "employee_id"] };
  var REFS = { restaurants: [["employees", "restaurant_id"], ["orders", "restaurant_id"]], positions: [["employees", "position_id"]],
               categories: [["menu_items", "category_id"]], menu_items: [["order_items", "menu_item_id"]], employees: [["orders", "employee_id"]] };
  var SET_NULL = { customers: [["orders", "customer_id"]], employees: [["users", "employee_id"]] };
  function checkUnique(entity, row, id) {
    (UNIQUE[entity] || []).forEach(function (f) {
      if (row[f] === null || row[f] === undefined) return;
      var dup = db[entity].some(function (r) { return r.id !== id && String(r[f]).toLowerCase() === String(row[f]).toLowerCase(); });
      if (dup) throw new Err(409, "Запись с таким значением уже существует");
    });
  }
  function checkFk(spec, row) {
    Object.keys(spec).forEach(function (n) {
      if (spec[n].type === "fk" && row[n] !== null && row[n] !== undefined && !byId(spec[n].ref, row[n]))
        throw new Err(409, "Операция нарушает ссылочную целостность (есть связанные записи или ссылка не существует)");
    });
  }

  // ---------------------------------------------------------------- универсальный CRUD
  function list(entity, q) {
    if (!can(entity, "read")) deny();
    var rows = db[entity].map(function (r) { var c = Object.assign({}, r); return JOINS[entity] ? JOINS[entity](c) : c; });
    var text = (q.get("q") || "").trim().slice(0, 100);
    if (text) {
      var ph = entity === "customers" ? normPhone(text) : null;
      rows = rows.filter(function (r) { return SEARCH[entity].some(function (f) { return like(r[f], text); }) || (ph && r.phone === ph); });
    }
    db.meta.entities[entity].filters.forEach(function (k) { var v = q.get(k); if (v) rows = rows.filter(function (r) { return pass(r, k, v.slice(0, 50)); }); });
    rows.sort(cmp(SORT[entity]));
    return { rows: rows.slice(0, 500), count: Math.min(rows.length, 500) };
  }
  async function toRow(entity, data, id) {
    if (entity !== "users") return data;
    var out = Object.assign({}, data);
    if (out.password) {
      var p = pwProblems(out.password);
      if (p.length) throw vErr({ password: "Пароль: требуется " + p.join(", ") });
      var login = out.login || byId("users", id).login;
      await window.VBAuth.wrapForUser(login, out.password, window.VBAuth.session().dk);
    }
    delete out.password;
    return out;
  }
  async function create(entity, body) {
    if (!can(entity, "create")) deny();
    var data = clean(db.meta.entities[entity].fields, body, false);
    if (entity === "customers" && me.role === "cashier") data.bonus_points = 0;
    checkFk(db.meta.entities[entity].fields, data); checkUnique(entity, data, null);
    data = await toRow(entity, data, null);
    var id = nextId(entity);
    var row = Object.assign({ id: id }, data);
    if (entity === "customers") row.registered_at = window.VBStore.now().slice(0, 10);
    if (entity === "users") row.created_at = window.VBStore.now();
    db[entity].push(row); audit("create", entity, id);
    return [201, { id: id, message: "Запись добавлена" }];
  }
  function adminGuard(uid, row) {
    var target = byId("users", uid);
    if (!target) return;
    var loses = target.role_id === 1 && target.is_active === 1 && (row.is_active === 0 || (row.role_id !== undefined && row.role_id !== 1));
    if (loses && uid === me.user_id) throw new Err(400, "Нельзя снять права администратора или заблокировать собственную учётную запись");
  }
  async function update(entity, id, body) {
    if (!can(entity, "update")) deny();
    var cur = byId(entity, id); if (!cur) throw new Err(404, "Запись не найдена");
    var data = clean(db.meta.entities[entity].fields, body, true);
    if (entity === "users" && !data.password) delete data.password;
    if (entity === "customers" && "bonus_points" in data && me.role === "cashier" && data.bonus_points !== cur.bonus_points)
      throw new Err(403, "Изменять бонусный баланс вручную может только управляющий или администратор");
    Object.keys(data).forEach(function (k) { if (data[k] === null && db.meta.entities[entity].fields[k].required) delete data[k]; });
    if (!Object.keys(data).length) throw vErr({ _: "Нет данных для изменения" });
    if (entity === "users") adminGuard(id, data);
    checkFk(db.meta.entities[entity].fields, data); checkUnique(entity, Object.assign({}, cur, data), id);
    data = await toRow(entity, data, id);
    Object.assign(cur, data); audit("update", entity, id);
    return [200, { message: "Изменения сохранены" }];
  }
  function remove(entity, id) {
    if (!can(entity, "delete")) deny();
    if (entity === "users" && id === me.user_id) throw new Err(400, "Нельзя удалить собственную учётную запись");
    if (entity === "users") adminGuard(id, { is_active: 0 });
    var idx = db[entity].findIndex(function (r) { return r.id === id; });
    if (idx < 0) throw new Err(404, "Запись не найдена");
    (REFS[entity] || []).forEach(function (rf) {
      if (db[rf[0]].some(function (r) { return r[rf[1]] === id; }))
        throw new Err(409, "Операция нарушает ссылочную целостность (есть связанные записи или ссылка не существует)");
    });
    (SET_NULL[entity] || []).forEach(function (rf) { db[rf[0]].forEach(function (r) { if (r[rf[1]] === id) r[rf[1]] = null; }); });
    db[entity].splice(idx, 1); audit("delete", entity, id);
    return [200, { message: "Запись удалена" }];
  }

  // ---------------------------------------------------------------- заказы
  var ORDER_FIELDS = {
    restaurant_id: { type: "fk", label: "Ресторан", required: true, ref: "restaurants" },
    employee_id: { type: "fk", label: "Кассир", required: true, ref: "employees" },
    customer_id: { type: "fk", label: "Клиент", ref: "customers" },
    order_type: { type: "enum", label: "Тип заказа", required: true, values: ORDER_TYPES },
    payment_method: { type: "enum", label: "Оплата", required: true, values: PAYMENTS },
    status: { type: "enum", label: "Статус", values: STATUSES },
  };
  function totals(oid) {
    var t = 0, n = 0;
    db.order_items.forEach(function (i) { if (i.order_id === oid) { t += i.quantity * i.unit_price; n += i.quantity; } });
    return [Math.round(t * 100) / 100, n];
  }
  function orderView(o) {
    var r = Object.assign({}, o), tt = totals(o.id);
    r.restaurant_name = nm("restaurants", o.restaurant_id); r.employee_name = nm("employees", o.employee_id, "full_name");
    r.customer_name = o.customer_id ? nm("customers", o.customer_id, "full_name") : null; r.total = tt[0]; r.items_count = tt[1];
    return r;
  }
  function checkEmployee(rid, eid) {
    var r = byId("restaurants", rid);
    if (!r) throw vErr({ restaurant_id: "Ресторан: не найден" });
    if (!r.is_active) throw vErr({ restaurant_id: "Ресторан: точка не работает, приём заказов невозможен" });
    var e = byId("employees", eid);
    if (!e) throw vErr({ employee_id: "Кассир: сотрудник не найден" });
    if (e.restaurant_id !== rid) throw vErr({ employee_id: "Кассир: сотрудник работает в другом ресторане" });
  }
  function cleanItems(raw) {
    if (!Array.isArray(raw) || !raw.length || raw.length > 30) throw vErr({ items: "Добавьте в заказ от 1 до 30 позиций" });
    var items = {};
    raw.forEach(function (it) {
      var mid = parseInt(it && it.menu_item_id, 10), q = parseInt(it && it.quantity, 10);
      if (isNaN(mid) || isNaN(q)) throw vErr({ items: "Некорректная позиция заказа" });
      if (q < 1 || q > 50) throw vErr({ items: "Количество — от 1 до 50" });
      items[mid] = (items[mid] || 0) + q;
    });
    return items;
  }
  function ordersList(q) {
    var rows = db.orders.map(orderView), text = (q.get("q") || "").trim().slice(0, 100);
    if (text) rows = /^\d+$/.test(text) ? rows.filter(function (r) { return r.id === +text; })
      : rows.filter(function (r) { return like(r.customer_name, text) || like(r.employee_name, text) || like(r.restaurant_name, text); });
    var f;
    if ((f = q.get("restaurant_id"))) rows = rows.filter(function (r) { return String(r.restaurant_id) === f; });
    if ((f = q.get("status"))) rows = rows.filter(function (r) { return r.status === f; });
    if ((f = q.get("order_type"))) rows = rows.filter(function (r) { return r.order_type === f; });
    if ((f = q.get("date_from"))) rows = rows.filter(function (r) { return r.created_at.slice(0, 10) >= f; });
    if ((f = q.get("date_to"))) rows = rows.filter(function (r) { return r.created_at.slice(0, 10) <= f; });
    rows.sort(function (a, b) { return a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0; });
    return { rows: rows.slice(0, 500) };
  }
  function orderGet(id) {
    var o = byId("orders", id); if (!o) throw new Err(404, "Заказ не найден");
    var items = db.order_items.filter(function (i) { return i.order_id === id; }).map(function (i) {
      return { menu_item_id: i.menu_item_id, name: nm("menu_items", i.menu_item_id), quantity: i.quantity, unit_price: i.unit_price,
               sum: Math.round(i.quantity * i.unit_price * 100) / 100 };
    });
    return { order: orderView(o), items: items };
  }
  function orderCreate(body) {
    var data = clean(ORDER_FIELDS, body, false), items = cleanItems(body.items);
    checkEmployee(data.restaurant_id, data.employee_id);
    if (data.customer_id && !byId("customers", data.customer_id)) throw new Err(409, "Операция нарушает ссылочную целостность (есть связанные записи или ссылка не существует)");
    var rows = Object.keys(items).map(function (mid) {
      var m = byId("menu_items", +mid);
      if (!m || !m.is_available) throw vErr({ items: "Позиция меню #" + mid + " недоступна" });
      return { menu_item_id: +mid, quantity: items[mid], unit_price: m.price };
    });
    var id = nextId("orders");
    db.orders.push({ id: id, restaurant_id: data.restaurant_id, employee_id: data.employee_id, customer_id: data.customer_id || null,
                     created_at: window.VBStore.now(), order_type: data.order_type, payment_method: data.payment_method, status: "новый" });
    rows.forEach(function (r) { r.order_id = id; db.order_items.push(r); });
    audit("create", "orders", id);
    return [201, { id: id, message: "Заказ №" + id + " оформлен" }];
  }
  function orderUpdate(id, body) {
    var cur = byId("orders", id); if (!cur) throw new Err(404, "Заказ не найден");
    var data = clean(ORDER_FIELDS, body, true);
    Object.keys(data).forEach(function (k) { if (data[k] === null && k !== "customer_id") delete data[k]; });
    var oldS = cur.status, newS = data.status || cur.status;
    var other = Object.keys(data).filter(function (k) { return k !== "status"; });
    if ((oldS === "выдан" || oldS === "отменён") && (other.length || "items" in body || newS !== oldS))
      throw vErr({ status: "Статус: заказ в статусе «" + oldS + "» изменять нельзя" });
    if (newS !== oldS && TRANSITIONS[oldS].indexOf(newS) < 0) throw vErr({ status: "Статус: переход «" + oldS + "» → «" + newS + "» недопустим" });
    if ("items" in body && oldS !== "новый") throw vErr({ items: "Состав можно менять только у заказа в статусе «новый»" });
    if ("restaurant_id" in data || "employee_id" in data) checkEmployee(data.restaurant_id || cur.restaurant_id, data.employee_id || cur.employee_id);
    var newItems = null;
    if ("items" in body) {
      var items = cleanItems(body.items), old = {};
      db.order_items.forEach(function (i) { if (i.order_id === id) old[i.menu_item_id] = i.unit_price; });
      newItems = Object.keys(items).map(function (mid) {
        var price = old[mid];
        if (price === undefined) { var m = byId("menu_items", +mid); if (!m || !m.is_available) throw vErr({ items: "Позиция меню #" + mid + " недоступна" }); price = m.price; }
        return { order_id: id, menu_item_id: +mid, quantity: items[mid], unit_price: price };
      });
    }
    Object.assign(cur, data);
    if (newItems) { db.order_items = db.order_items.filter(function (i) { return i.order_id !== id; }).concat(newItems); }
    var bonus = 0, customer = "customer_id" in data ? data.customer_id : cur.customer_id;
    if (newS === "выдан" && oldS !== "выдан" && customer) {
      bonus = Math.floor(totals(id)[0] * BONUS_RATE); byId("customers", customer).bonus_points += bonus;
    }
    audit("update", "orders", id);
    return [200, { message: "Заказ обновлён" + (bonus ? "; клиенту начислено " + bonus + " бонусов" : "") }];
  }
  function orderDelete(id) {
    if (["admin", "manager"].indexOf(me.role) < 0) deny();
    var idx = db.orders.findIndex(function (o) { return o.id === id; }); if (idx < 0) throw new Err(404, "Заказ не найден");
    db.orders.splice(idx, 1); db.order_items = db.order_items.filter(function (i) { return i.order_id !== id; });
    audit("delete", "orders", id);
    return [200, { message: "Заказ удалён" }];
  }

  // ---------------------------------------------------------------- отчёты
  var REPORTS = {
    revenue_by_restaurant: { title: "Выручка по ресторанам за период", columns: ["Ресторан", "Город", "Заказов", "Выручка, ₽", "Средний чек, ₽"] },
    top_menu_items: { title: "Топ-10 позиций меню по продажам", columns: ["Позиция", "Категория", "Продано, шт.", "Выручка, ₽"] },
    avg_check_by_type: { title: "Средний чек и доля по типам заказа", columns: ["Тип заказа", "Заказов", "Выручка, ₽", "Средний чек, ₽", "Доля выручки, %"] },
    daily_revenue: { title: "Динамика выручки по дням", columns: ["Дата", "Заказов", "Выручка, ₽", "Отменено"] },
    cashier_performance: { title: "Результаты работы кассиров", columns: ["Сотрудник", "Ресторан", "Заказов", "Выручка, ₽", "Средний чек, ₽"], roles: ["admin", "manager"] },
  };
  function r2(x) { return Math.round(x * 100) / 100; }
  function report(name, q) {
    var rep = REPORTS[name]; if (!rep) throw new Err(404, "Отчёт не найден");
    if ((rep.roles || ALL).indexOf(me.role) < 0) throw new Err(403, "Недостаточно прав для просмотра отчёта");
    var from = q.get("date_from") || "2000-01-01", to = q.get("date_to") || window.VBStore.now().slice(0, 10);
    if ((q.get("date_from") && !validDate(from)) || (q.get("date_to") && !validDate(to))) throw new Err(400, "Некорректный период");
    if (from > to) throw new Err(400, "Дата начала периода позже даты окончания");
    var inP = db.orders.filter(function (o) { var d = o.created_at.slice(0, 10); return d >= from && d <= to; });
    var ok = inP.filter(function (o) { return o.status !== "отменён"; }), tot = {}, rows = [];
    db.orders.forEach(function (o) { tot[o.id] = totals(o.id)[0]; });
    function group(list, key) { var g = {}; list.forEach(function (o) { var k = key(o); (g[k] = g[k] || []).push(o); }); return g; }
    if (name === "revenue_by_restaurant") {
      var gr = group(ok, function (o) { return o.restaurant_id; });
      rows = db.restaurants.map(function (r) { var l = gr[r.id] || [], s = l.reduce(function (a, o) { return a + tot[o.id]; }, 0);
        return [r.name, r.city, l.length, r2(s), r2(l.length ? s / l.length : 0)]; }).sort(function (a, b) { return b[3] - a[3]; });
    } else if (name === "top_menu_items") {
      var ids = {}; ok.forEach(function (o) { ids[o.id] = 1; }); var g2 = {};
      db.order_items.forEach(function (i) { if (ids[i.order_id]) { var e = g2[i.menu_item_id] = g2[i.menu_item_id] || [0, 0]; e[0] += i.quantity; e[1] += i.quantity * i.unit_price; } });
      rows = Object.keys(g2).map(function (k) { var m = byId("menu_items", +k); return [m ? m.name : "#" + k, m ? nm("categories", m.category_id) : "", g2[k][0], r2(g2[k][1])]; })
        .sort(function (a, b) { return b[2] - a[2] || b[3] - a[3]; }).slice(0, 10);
    } else if (name === "avg_check_by_type") {
      var all = ok.reduce(function (a, o) { return a + tot[o.id]; }, 0), g3 = group(ok, function (o) { return o.order_type; });
      rows = Object.keys(g3).map(function (k) { var s = g3[k].reduce(function (a, o) { return a + tot[o.id]; }, 0);
        return [k, g3[k].length, r2(s), r2(s / g3[k].length), Math.round(1000 * s / all) / 10]; }).sort(function (a, b) { return b[2] - a[2]; });
    } else if (name === "daily_revenue") {
      var g4 = group(inP, function (o) { return o.created_at.slice(0, 10); });
      rows = Object.keys(g4).sort().map(function (d) { var l = g4[d], good = l.filter(function (o) { return o.status !== "отменён"; });
        return [d, good.length, r2(good.reduce(function (a, o) { return a + tot[o.id]; }, 0)), l.length - good.length]; });
    } else {
      var g5 = group(ok, function (o) { return o.employee_id; });
      rows = Object.keys(g5).map(function (k) { var e = byId("employees", +k), s = g5[k].reduce(function (a, o) { return a + tot[o.id]; }, 0);
        return [e ? e.full_name : "#" + k, e ? nm("restaurants", e.restaurant_id) : "", g5[k].length, r2(s), r2(s / g5[k].length)]; })
        .sort(function (a, b) { return b[3] - a[3]; });
    }
    return { title: rep.title, columns: rep.columns, rows: rows, period: [from, to] };
  }

  function meta() {
    var ents = {};
    Object.keys(db.meta.entities).forEach(function (k) {
      var s = db.meta.entities[k];
      if (s.perms.read.indexOf(me.role) < 0) return;
      var c = {}; Object.keys(s.perms).forEach(function (a) { c[a] = s.perms[a].indexOf(me.role) >= 0; });
      ents[k] = { title: s.title, can: c, fields: s.fields, filters: s.filters };
    });
    var emp = me.employee_id ? byId("employees", me.employee_id) : null;
    function lk(t, f) { return db[t].map(function (r) { return { id: r.id, name: r[f || "name"] }; }).sort(function (a, b) { return a.name < b.name ? -1 : 1; }); }
    return {
      role: me.role, entities: ents, me: { employee_id: me.employee_id, restaurant_id: emp ? emp.restaurant_id : null },
      transitions: TRANSITIONS,
      lookups: {
        restaurants: db.restaurants.map(function (r) { return { id: r.id, name: r.name, is_active: r.is_active }; }).sort(function (a, b) { return a.name < b.name ? -1 : 1; }),
        categories: lk("categories"), positions: lk("positions"), roles: db.roles.map(function (r) { return { id: r.id, name: r.name }; }),
        employees: db.employees.map(function (e) { return { id: e.id, name: e.full_name, restaurant_id: e.restaurant_id, position: nm("positions", e.position_id) }; })
          .sort(function (a, b) { return a.name < b.name ? -1 : 1; }),
        customers: lk("customers", "full_name"),
        menu_items: db.menu_items.filter(function (m) { return m.is_available; }).map(function (m) { return { id: m.id, name: m.name, price: m.price }; })
          .sort(function (a, b) { return a.name < b.name ? -1 : 1; }),
      },
      orders: { types: ORDER_TYPES, payments: PAYMENTS, statuses: STATUSES, can_delete: ["admin", "manager"].indexOf(me.role) >= 0 },
    };
  }

  // ---------------------------------------------------------------- маршрутизация
  async function request(method, url, body) {
    var sess = window.VBAuth.session();
    if (!sess) return { status: 401, data: { error: "Требуется авторизация" } };
    window.VBAuth.touch();
    dk = await window.VBAuth.dataKey();
    db = await window.VBStore.load(dk);
    var u = db.users.filter(function (x) { return x.id === sess.user_id; })[0];
    if (!u || !u.is_active) { window.VBAuth.logout(); return { status: 401, data: { error: "Требуется авторизация" } }; }
    var role = db.roles.filter(function (r) { return r.id === u.role_id; })[0];
    me = { user_id: u.id, role: role.code, employee_id: u.employee_id };
    var loc = new URL(url, location.href), parts = loc.pathname.replace(/^.*\/api\//, "").split("/"), q = loc.searchParams;
    var res, changed = method !== "GET";
    try {
      if (parts[0] === "meta") res = [200, meta()];
      else if (parts[0] === "reports") res = parts[1] ? [200, report(parts[1], q)]
        : [200, { reports: Object.keys(REPORTS).filter(function (k) { return (REPORTS[k].roles || ALL).indexOf(me.role) >= 0; }).map(function (k) { return { id: k, title: REPORTS[k].title }; }) }];
      else if (parts[0] === "orders") {
        var oid = parts[1] ? parseInt(parts[1], 10) : null;
        if (method === "GET") res = [200, oid ? orderGet(oid) : ordersList(q)];
        else if (method === "POST") res = orderCreate(body || {});
        else if (method === "PUT") res = orderUpdate(oid, body || {});
        else res = orderDelete(oid);
      } else if (db.meta.entities[parts[0]]) {
        var id = parts[1] ? parseInt(parts[1], 10) : null;
        if (method === "GET") res = [200, list(parts[0], q)];
        else if (method === "POST") res = await create(parts[0], body || {});
        else if (method === "PUT") res = await update(parts[0], id, body || {});
        else res = remove(parts[0], id);
      } else res = [404, { error: "Не найдено" }];
    } catch (e) {
      if (!(e instanceof Err)) throw e;
      res = [e.status, e.fields ? { error: e.error, fields: e.fields } : { error: e.error }];
      changed = e.status === 403;     // отказ в доступе фиксируется в журнале
    }
    if (changed) await window.VBStore.save(dk, db);
    return { status: res[0], data: res[1] };
  }
  window.VBLocal = { request: request };
})();
