/* Рабочий модуль АИС: CRUD, поиск, фильтрация, отчёты.
   Все данные выводятся через textContent (защита от XSS), все изменяющие запросы
   отправляются с заголовком X-CSRF-Token. Права дополнительно проверяет сервер. */
(function () {
  "use strict";
  var root = document.getElementById("app-module");
  if (!root) return;
  var CSRF = "";
  var META = null;

  // ------------------------------------------------------------ утилиты
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    });
    return el;
  }
  function api(method, url, body) {          // запросы обрабатываются в браузере (localapi.js)
    return window.VBLocal.request(method, url, body).then(function (r) {
      if (window.__vbTouch) window.__vbTouch();
      if (r.status === 401) { window.location.href = "index.html"; throw new Error("auth"); }
      var d = r.data || {}; d.__status = r.status; return d;
    });
  }
  function toast(msg, err) {
    var t = h("div", { class: "toast" + (err ? " err" : ""), role: "status", text: msg });
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3500);
  }
  function shortFio(n) {   // «Иванов Иван Иванович» → «Иванов И. И.»
    var p = String(n || "").split(/\s+/);
    return p.length === 3 ? p[0] + " " + p[1][0] + ". " + p[2][0] + "." : (n || "");
  }
  function money(v) { return v === null || v === undefined ? "" : Number(v).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function yesno(v) { return h("span", { class: "badge" + (v ? "" : " no"), text: v ? "да" : "нет" }); }
  function qs(obj) {
    return Object.keys(obj).filter(function (k) { return obj[k] !== "" && obj[k] !== null && obj[k] !== undefined; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(obj[k]); }).join("&");
  }
  var REF_OF = { category_id: "categories", restaurant_id: "restaurants", position_id: "positions", role_id: "roles",
                 employee_id: "employees", customer_id: "customers" };

  // ------------------------------------------------------------ столбцы таблиц
  var COLS = {
    restaurants: [["id", "№"], ["name", "Название"], ["city", "Город"], ["address", "Адрес"], ["phone", "Телефон"],
                  ["opened_on", "Открыт"], ["is_active", "Работает", yesno]],
    categories: [["id", "№"], ["name", "Название"]],
    menu_items: [["id", "№"], ["name", "Наименование"], ["category_name", "Категория"], ["price", "Цена, ₽", money, "num"],
                 ["calories", "Ккал", null, "num"], ["is_available", "В продаже", yesno]],
    positions: [["id", "№"], ["name", "Должность"], ["base_salary", "Оклад, ₽", money, "num"]],
    employees: [["id", "№"], ["full_name", "ФИО"], ["position_name", "Должность"], ["restaurant_name", "Ресторан"],
                ["phone", "Телефон 🔒"], ["hire_date", "Принят"], ["salary", "Зарплата, ₽", money, "num"]],
    customers: [["id", "№"], ["full_name", "Клиент"], ["phone", "Телефон 🔒"], ["email", "E-mail 🔒"],
                ["bonus_points", "Бонусы", null, "num"], ["registered_at", "Регистрация"]],
    users: [["id", "№"], ["login", "Логин"], ["role_name", "Роль"], ["employee_name", "Сотрудник"],
            ["is_active", "Активен", yesno], ["created_at", "Создан"]],
  };

  // ------------------------------------------------------------ каркас
  function init() {
    api("GET", "/api/meta").then(function (m) {
      META = m;
      root.textContent = "";
      var tabs = h("div", { class: "tabs", role: "tablist" });
      var panel = h("div", { id: "mod-panel", role: "tabpanel" });
      var list = [["orders", "Заказы"]];
      Object.keys(m.entities).forEach(function (k) { list.push([k, m.entities[k].title]); });
      list.push(["reports", "Отчёты"]);
      list.forEach(function (t, i) {
        tabs.appendChild(h("button", { class: "tab", role: "tab", type: "button", "aria-selected": i === 0 ? "true" : "false",
          "data-tab": t[0], text: t[1], onclick: function () { select(t[0]); } }));
      });
      root.appendChild(tabs); root.appendChild(panel);
      select("orders");
    });
  }
  function select(tab) {
    root.querySelectorAll(".tab").forEach(function (b) { b.setAttribute("aria-selected", b.getAttribute("data-tab") === tab ? "true" : "false"); });
    var panel = document.getElementById("mod-panel");
    panel.textContent = "";
    if (tab === "orders") ordersView(panel);
    else if (tab === "reports") reportsView(panel);
    else entityView(panel, tab);
  }

  // ------------------------------------------------------------ фильтры
  function filterControl(name) {
    var labels = { city: "Город", is_active: "Работает", is_available: "В продаже", price_min: "Цена от", price_max: "Цена до",
                   category_id: "Категория", restaurant_id: "Ресторан", position_id: "Должность", role_id: "Роль",
                   status: "Статус", order_type: "Тип заказа", date_from: "Дата с", date_to: "Дата по" };
    var ctl;
    if (REF_OF[name]) {
      ctl = h("select", { name: name }, [h("option", { value: "", text: "Все" })]);
      (META.lookups[REF_OF[name]] || []).forEach(function (o) { ctl.appendChild(h("option", { value: o.id, text: o.name })); });
    } else if (/^is_/.test(name)) {
      ctl = h("select", { name: name }, [h("option", { value: "", text: "Все" }), h("option", { value: "1", text: "Да" }), h("option", { value: "0", text: "Нет" })]);
    } else if (name === "status" || name === "order_type") {
      ctl = h("select", { name: name }, [h("option", { value: "", text: "Все" })]);
      (name === "status" ? META.orders.statuses : META.orders.types).forEach(function (s) { ctl.appendChild(h("option", { value: s, text: s })); });
    } else if (/^date_/.test(name)) {
      ctl = h("input", { type: "date", name: name });
    } else if (/^price_/.test(name)) {
      ctl = h("input", { type: "number", name: name, min: "0", step: "0.01" });
    } else ctl = h("input", { type: "text", name: name, maxlength: "60" });
    ctl.id = "flt-" + name;
    return h("div", { class: "fld" }, [h("label", { for: ctl.id, text: labels[name] || name }), ctl]);
  }
  function toolbar(filters, onSearch, addLabel, onAdd) {
    var q = h("input", { type: "search", name: "q", id: "flt-q", maxlength: "100", placeholder: "Поиск…" });
    var bar = h("form", { class: "toolbar", role: "search" }, [h("div", { class: "fld q" }, [h("label", { for: "flt-q", text: "Поиск" }), q])]);
    filters.forEach(function (f) { bar.appendChild(filterControl(f)); });
    var btns = h("div", { class: "btns" }, [
      h("button", { class: "btn btn-secondary", type: "submit", text: "Найти" }),
      h("button", { class: "btn btn-ghost", type: "button", text: "Сбросить", onclick: function () { bar.reset(); onSearch({}); } })]);
    if (onAdd) btns.appendChild(h("button", { class: "btn", type: "button", text: addLabel, onclick: onAdd }));
    bar.appendChild(btns);
    bar.addEventListener("submit", function (e) {
      e.preventDefault();
      var params = {};
      Array.prototype.forEach.call(bar.elements, function (el) { if (el.name) params[el.name] = el.value.trim(); });
      onSearch(params);
    });
    return bar;
  }

  // ------------------------------------------------------------ универсальный раздел
  function entityView(panel, entity) {
    var spec = META.entities[entity];
    var tableBox = h("div");
    var params = {};
    function load(p) {
      params = p || params;
      api("GET", "/api/" + entity + "?" + qs(params)).then(function (d) {
        tableBox.textContent = "";
        if (d.__status !== 200) { tableBox.appendChild(h("p", { class: "form-error", text: d.error || "Ошибка" })); return; }
        tableBox.appendChild(h("p", { class: "count", text: "Найдено записей: " + d.rows.length }));
        var cols = COLS[entity];
        var thead = h("tr", {}, cols.map(function (c) { return h("th", { class: c[3] || null, text: c[1] }); }));
        if (spec.can.update || spec.can.delete) thead.appendChild(h("th", { text: "Действия" }));
        var tbody = h("tbody");
        d.rows.forEach(function (r) {
          var tr = h("tr", {}, cols.map(function (c) {
            var v = r[c[0]];
            var td = h("td", { class: c[3] || null });
            if (c[2]) { var out = c[2](v); if (typeof out === "string") td.textContent = out; else td.appendChild(out); }
            else td.textContent = v === null || v === undefined ? "" : String(v);
            return td;
          }));
          if (spec.can.update || spec.can.delete) {
            var act = h("td", { class: "row-actions" });
            if (spec.can.update) act.appendChild(h("button", { class: "btn btn-sm btn-secondary", type: "button", text: "Изменить",
              onclick: function () { editDialog(entity, r, function () { load(); }); } }));
            if (spec.can.delete) act.appendChild(h("button", { class: "btn btn-sm btn-danger", type: "button", text: "Удалить",
              onclick: function () { removeRow(entity, r.id, load); } }));
            tr.appendChild(act);
          }
          tbody.appendChild(tr);
        });
        if (!d.rows.length) tbody.appendChild(h("tr", {}, [h("td", { colspan: cols.length + 1, class: "muted", text: "Ничего не найдено" })]));
        tableBox.appendChild(h("div", { class: "table-wrap" }, [h("table", {}, [h("thead", {}, [thead]), tbody])]));
      });
    }
    panel.appendChild(h("h3", { text: spec.title }));
    if (entity === "customers") panel.appendChild(h("p", { class: "muted", text: "Поиск по телефону выполняется точным совпадением через HMAC-индекс: сам телефон хранится в зашифрованном виде (🔒)." }));
    panel.appendChild(toolbar(spec.filters, load, "Добавить", spec.can.create ? function () { editDialog(entity, null, function () { load(); }); } : null));
    panel.appendChild(tableBox);
    load({});
  }

  function removeRow(entity, id, after) {
    if (!window.confirm("Удалить запись №" + id + "? Действие необратимо.")) return;
    api("DELETE", "/api/" + entity + "/" + id).then(function (d) {
      if (d.__status === 200) { toast(d.message); refreshLookups(); after(); } else toast(d.error || "Ошибка удаления", true);
    });
  }
  function refreshLookups() {
    api("GET", "/api/meta").then(function (m) { META.lookups = m.lookups; });
  }

  // ------------------------------------------------------------ диалог формы
  var dlg = document.getElementById("dlg"), dlgForm = document.getElementById("dlg-form"),
      dlgBody = document.getElementById("dlg-body"), dlgErr = document.getElementById("dlg-error");
  var onSubmit = null;
  document.getElementById("dlg-cancel").addEventListener("click", function () { dlg.close(); });
  dlgForm.addEventListener("submit", function (e) { e.preventDefault(); if (onSubmit) onSubmit(); });

  function openDialog(title, build, submit) {
    document.getElementById("dlg-title").textContent = title;
    dlgBody.textContent = ""; dlgErr.textContent = "";
    build(dlgBody);
    onSubmit = submit;
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    var first = dlgBody.querySelector("input,select"); if (first) first.focus();
  }

  function fieldInput(name, f, value) {
    var id = "fld-" + name, ctl;
    if (f.type === "fk") {
      ctl = h("select", { id: id, name: name }, [h("option", { value: "", text: f.required ? "— выберите —" : "— не указано —" })]);
      (META.lookups[f.ref] || []).forEach(function (o) { ctl.appendChild(h("option", { value: o.id, text: o.name, selected: String(o.id) === String(value) })); });
    } else if (f.type === "enum") {
      ctl = h("select", { id: id, name: name }, f.values.map(function (v) { return h("option", { value: v, text: v, selected: v === value }); }));
    } else if (f.type === "bool") {
      ctl = h("input", { id: id, name: name, type: "checkbox", checked: value === undefined || value === null ? true : !!value });
      return h("div", {}, [h("label", { class: "check", for: id }, [ctl, f.label]), h("span", { class: "field-error", "data-for": id })]);
    } else {
      var type = { date: "date", int: "number", num: "number", email: "email", phone: "tel", password: "password" }[f.type] || "text";
      ctl = h("input", { id: id, name: name, type: type, value: value === null || value === undefined ? "" : value,
                         autocomplete: type === "password" ? "new-password" : "off" });
      if (f.type === "num") ctl.step = "0.01";
      if (f.min !== undefined && (f.type === "int" || f.type === "num")) ctl.min = f.min;
      if (f.max !== undefined && (f.type === "int" || f.type === "num")) ctl.max = f.max;
      if (f.max !== undefined && (f.type === "str" || f.type === "name")) ctl.maxLength = f.max;
      if (f.type === "phone") ctl.placeholder = "+7XXXXXXXXXX";
    }
    var label = f.label + (f.required && !(f.optional_on_update && value === "__edit__") ? " *" : "");
    var hint = f.type === "password" ? h("span", { class: "hint", text: "Не менее 8 символов, строчные и заглавные буквы, цифры." + (value === "__edit__" ? " Оставьте пустым, чтобы не менять." : "") }) : null;
    if (value === "__edit__") ctl.value = "";
    return h("div", {}, [h("label", { for: id, text: label }), ctl, hint, h("span", { class: "field-error", "data-for": id })]);
  }

  function validateClient(fields, data, isEdit) {
    var errs = {};
    Object.keys(fields).forEach(function (n) {
      var f = fields[n], v = data[n];
      var empty = v === "" || v === null || v === undefined;
      if (f.type === "bool") return;
      if (empty) { if (f.required && !(isEdit && f.optional_on_update)) errs[n] = "Обязательное поле"; return; }
      if ((f.type === "str" || f.type === "name") && (v.length < (f.min || 1) || v.length > (f.max || 200))) errs[n] = "Длина от " + (f.min || 1) + " до " + (f.max || 200);
      else if (f.type === "name" && !/^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё .'\-]*$/.test(v)) errs[n] = "Только буквы, пробел, дефис";
      else if ((f.type === "str" || f.type === "name") && /[<>]/.test(v)) errs[n] = "Недопустимые символы < >";
      else if (f.regex && !(new RegExp(f.regex)).test(v)) errs[n] = f.regex_msg || "Неверный формат";
      else if (f.type === "int" && (!/^-?\d+$/.test(v) || +v < f.min || +v > f.max)) errs[n] = "Целое число от " + f.min + " до " + f.max;
      else if (f.type === "num" && (isNaN(+v) || +v < f.min || +v > f.max)) errs[n] = "Число от " + f.min + " до " + f.max;
      else if (f.type === "phone") { var d = v.replace(/\D/g, ""); if (!(d.length === 10 || (d.length === 11 && /^[78]/.test(d)))) errs[n] = "Телефон в формате +7XXXXXXXXXX"; }
      else if (f.type === "email" && !/^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(v)) errs[n] = "Некорректный e-mail";
      else if (f.type === "password" && !(v.length >= 8 && /[a-zа-яё]/.test(v) && /[A-ZА-ЯЁ]/.test(v) && /\d/.test(v))) errs[n] = "Пароль не соответствует требованиям сложности";
      else if (f.type === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(v)) errs[n] = "Дата в формате ГГГГ-ММ-ДД";
    });
    return errs;
  }
  function showErrors(errs) {
    dlgBody.querySelectorAll(".field-error").forEach(function (s) { s.textContent = ""; });
    dlgBody.querySelectorAll("[aria-invalid]").forEach(function (el) { el.removeAttribute("aria-invalid"); });
    Object.keys(errs || {}).forEach(function (n) {
      var el = document.getElementById("fld-" + n);
      var span = dlgBody.querySelector('.field-error[data-for="fld-' + n + '"]');
      if (el) el.setAttribute("aria-invalid", "true");
      if (span) span.textContent = errs[n]; else dlgErr.textContent = errs[n];
    });
  }
  function collect(fields) {
    var data = {};
    Object.keys(fields).forEach(function (n) {
      var el = document.getElementById("fld-" + n);
      if (!el) return;
      data[n] = fields[n].type === "bool" ? el.checked : el.value.trim();
    });
    return data;
  }

  function editDialog(entity, row, after) {
    var spec = META.entities[entity], isEdit = !!row;
    openDialog((isEdit ? "Изменение: " : "Добавление: ") + spec.title.toLowerCase() + (isEdit ? " №" + row.id : ""), function (body) {
      Object.keys(spec.fields).forEach(function (n) {
        var f = spec.fields[n];
        if (entity === "customers" && n === "bonus_points" && META.role === "cashier") return;   // бонусы меняет только управляющий
        var v = isEdit ? (f.type === "password" ? "__edit__" : row[n]) : (f.default !== undefined ? f.default : undefined);
        body.appendChild(fieldInput(n, f, v));
      });
    }, function () {
      var data = collect(spec.fields);
      var errs = validateClient(spec.fields, data, isEdit);
      if (Object.keys(errs).length) { showErrors(errs); return; }
      if (isEdit && spec.fields.password && !data.password) delete data.password;
      api(isEdit ? "PUT" : "POST", "/api/" + entity + (isEdit ? "/" + row.id : ""), data).then(function (d) {
        if (d.__status === 200 || d.__status === 201) { dlg.close(); toast(d.message); refreshLookups(); after(); }
        else { showErrors(d.fields || {}); dlgErr.textContent = d.error || "Ошибка"; }
      });
    });
  }

  // ------------------------------------------------------------ заказы
  function ordersView(panel) {
    var tableBox = h("div"), params = {};
    function load(p) {
      params = p || params;
      api("GET", "/api/orders?" + qs(params)).then(function (d) {
        tableBox.textContent = "";
        var total = d.rows.reduce(function (s, r) { return s + (r.status === "отменён" ? 0 : r.total); }, 0);
        tableBox.appendChild(h("p", { class: "count", text: "Найдено заказов: " + d.rows.length + " · сумма (без отменённых): " + money(total) + " ₽" }));
        var tb = h("tbody");
        d.rows.forEach(function (r) {
          var act = h("td", { class: "row-actions" }, [
            h("button", { class: "btn btn-sm btn-ghost", type: "button", text: "Состав", onclick: function () { orderDetails(r.id); } }),
            (r.status === "выдан" || r.status === "отменён") ? null :
            h("button", { class: "btn btn-sm btn-secondary", type: "button", text: "Изменить", onclick: function () { orderDialog(r.id, function () { load(); }); } })]);
          if (META.orders.can_delete) act.appendChild(h("button", { class: "btn btn-sm btn-danger", type: "button", text: "Удалить", onclick: function () { removeRow("orders", r.id, load); } }));
          tb.appendChild(h("tr", {}, [h("td", { text: r.id }), h("td", { class: "nowrap", text: r.created_at.slice(0, 16) }), h("td", { text: r.restaurant_name }),
            h("td", { class: "nowrap", text: shortFio(r.employee_name) }), h("td", { text: r.customer_name || "—" }),
            h("td", { text: r.order_type + " · " + r.payment_method }), h("td", {}, [h("span", { class: "badge b-" + r.status, text: r.status })]),
            h("td", { class: "num", text: money(r.total) }), act]));
        });
        if (!d.rows.length) tb.appendChild(h("tr", {}, [h("td", { colspan: 9, class: "muted", text: "Ничего не найдено" })]));
        var head = ["№", "Дата и время", "Ресторан", "Кассир", "Клиент", "Тип · оплата", "Статус", "Сумма, ₽", "Действия"];
        tableBox.appendChild(h("div", { class: "table-wrap" }, [h("table", {}, [h("thead", {}, [h("tr", {}, head.map(function (t) { return h("th", { text: t }); }))]), tb])]));
      });
    }
    panel.appendChild(h("h3", { text: "Заказы" }));
    panel.appendChild(h("p", { class: "muted", text: "Поиск: номер заказа, имя клиента, кассира или название ресторана." }));
    panel.appendChild(toolbar(["restaurant_id", "status", "order_type", "date_from", "date_to"], load, "Новый заказ", function () { orderDialog(null, function () { load(); }); }));
    panel.appendChild(tableBox);
    load({});
  }

  function orderDetails(id) {
    api("GET", "/api/orders/" + id).then(function (d) {
      if (d.__status !== 200) { toast(d.error, true); return; }
      openDialog("Заказ №" + id, function (body) {
        var o = d.order;
        body.appendChild(h("p", {}, [o.created_at + " · " + o.restaurant_name + " · " + o.order_type + " · " + o.payment_method + " · ",
          h("span", { class: "badge b-" + o.status, text: o.status })]));
        var tb = h("tbody");
        d.items.forEach(function (i) { tb.appendChild(h("tr", {}, [h("td", { text: i.name }), h("td", { class: "num", text: i.quantity }),
          h("td", { class: "num", text: money(i.unit_price) }), h("td", { class: "num", text: money(i.sum) })])); });
        tb.appendChild(h("tr", {}, [h("td", { colspan: 3 }, [h("b", { text: "Итого" })]), h("td", { class: "num" }, [h("b", { text: money(o.total) })])]));
        body.appendChild(h("div", { class: "table-wrap" }, [h("table", {}, [h("thead", {}, [h("tr", {}, ["Позиция", "Кол-во", "Цена", "Сумма"].map(function (t) { return h("th", { text: t }); }))]), tb])]));
      }, function () { dlg.close(); });
      document.getElementById("dlg-ok").textContent = "Закрыть";
      dlg.addEventListener("close", function rst() { document.getElementById("dlg-ok").textContent = "Сохранить"; dlg.removeEventListener("close", rst); });
    });
  }

  function orderDialog(id, after) {
    var me = META.me || {};
    var start = id ? api("GET", "/api/orders/" + id) : Promise.resolve({ order: { status: "новый", order_type: "в зале", payment_method: "карта",
      restaurant_id: me.restaurant_id, employee_id: me.employee_id }, items: [] });
    start.then(function (d) {
      var o = d.order;
      var F = {
        restaurant_id: { type: "fk", label: "Ресторан", required: true, ref: "restaurants" },
        employee_id: { type: "fk", label: "Кассир", required: true, ref: "employees" },
        customer_id: { type: "fk", label: "Клиент (программа лояльности)", ref: "customers" },
        order_type: { type: "enum", label: "Тип заказа", required: true, values: META.orders.types },
        payment_method: { type: "enum", label: "Оплата", required: true, values: META.orders.payments },
      };
      // статус: для нового заказа всегда «новый», при изменении — только допустимые переходы (рис. 12)
      if (id) F.status = { type: "enum", label: "Статус", required: true, values: [o.status].concat(META.transitions[o.status] || []) };
      var itemsEditable = !id || o.status === "новый";
      var itemsBox, totalEl;
      function recalc() {
        var t = 0;
        itemsBox.querySelectorAll(".item-row").forEach(function (r) {
          var sel = r.querySelector("select"), q = +r.querySelector("input").value || 0;
          var m = (META.lookups.menu_items || []).filter(function (x) { return String(x.id) === sel.value; })[0];
          var price = m ? m.price : +(sel.getAttribute("data-price") || 0);
          t += price * q;
        });
        totalEl.textContent = "Итого: " + money(t) + " ₽";
      }
      function addItem(mid, qty, name, price) {
        var sel = h("select", { "aria-label": "Позиция меню" }, [h("option", { value: "", text: "— позиция меню —" })]);
        var menu = (META.lookups.menu_items || []).slice();
        if (mid && !menu.some(function (m) { return m.id === mid; })) menu.push({ id: mid, name: name + " (снято с продажи)", price: price });
        menu.forEach(function (m) { sel.appendChild(h("option", { value: m.id, text: m.name + " — " + money(m.price) + " ₽", selected: m.id === mid })); });
        var q = h("input", { type: "number", min: "1", max: "50", value: qty || 1, "aria-label": "Количество" });
        var row = h("div", { class: "item-row" }, [sel, q, h("button", { type: "button", class: "btn btn-sm btn-ghost", text: "✕", "aria-label": "Убрать",
          onclick: function () { row.remove(); recalc(); } })]);
        sel.addEventListener("change", recalc); q.addEventListener("input", recalc);
        itemsBox.appendChild(row); recalc();
      }
      openDialog(id ? "Изменение заказа №" + id : "Новый заказ", function (body) {
        Object.keys(F).forEach(function (n) { body.appendChild(fieldInput(n, F[n], o[n])); });
        // в списке кассиров — только сотрудники выбранного ресторана, работающие на кассе
        var rSel = body.querySelector("#fld-restaurant_id"), eSel = body.querySelector("#fld-employee_id");
        function fillEmployees(keep) {
          var cur = keep || eSel.value;
          eSel.textContent = "";
          eSel.appendChild(h("option", { value: "", text: "— выберите —" }));
          (META.lookups.employees || []).filter(function (e) {
            return String(e.restaurant_id) === rSel.value && e.position !== "Повар" && e.position !== "Курьер";
          }).forEach(function (e) { eSel.appendChild(h("option", { value: e.id, text: e.name + " (" + e.position + ")", selected: String(e.id) === String(cur) })); });
        }
        Array.prototype.slice.call(rSel.options).forEach(function (op) {   // закрытые рестораны не принимают заказы
          var r = (META.lookups.restaurants || []).filter(function (x) { return String(x.id) === op.value; })[0];
          if (r && !r.is_active && String(o.restaurant_id) !== op.value) op.remove();
        });
        rSel.addEventListener("change", function () { fillEmployees(); });
        fillEmployees(o.employee_id);
        body.appendChild(h("label", { text: "Состав заказа *" }));
        if (!itemsEditable) {
          body.appendChild(h("p", { class: "muted", text: "Состав можно менять только у заказа в статусе «новый»:" }));
          d.items.forEach(function (i) { body.appendChild(h("p", { text: i.name + " × " + i.quantity + " — " + money(i.sum) + " ₽" })); });
          return;
        }
        itemsBox = h("div", { class: "items-list" });
        totalEl = h("p", { class: "count" });
        body.appendChild(itemsBox);
        body.appendChild(h("button", { type: "button", class: "btn btn-sm btn-secondary mt", text: "+ Добавить позицию", onclick: function () { addItem(); } }));
        body.appendChild(totalEl);
        body.appendChild(h("span", { class: "field-error", "data-for": "fld-items" }));
        if (d.items.length) d.items.forEach(function (i) { addItem(i.menu_item_id, i.quantity, i.name, i.unit_price); }); else addItem();
      }, function () {
        var data = collect(F);
        var errs = validateClient(F, data, false);
        var items = [];
        if (itemsEditable) itemsBox.querySelectorAll(".item-row").forEach(function (r) {
          var mid = r.querySelector("select").value, q = r.querySelector("input").value;
          if (!mid) return;
          if (!/^\d+$/.test(q) || +q < 1 || +q > 50) errs.items = "Количество — целое число от 1 до 50";
          items.push({ menu_item_id: +mid, quantity: +q });
        });
        if (itemsEditable && !items.length) errs.items = "Добавьте хотя бы одну позицию";
        if (Object.keys(errs).length) { showErrors(errs); return; }
        if (itemsEditable) data.items = items;
        api(id ? "PUT" : "POST", "/api/orders" + (id ? "/" + id : ""), data).then(function (r) {
          if (r.__status === 200 || r.__status === 201) { dlg.close(); toast(r.message); after(); }
          else { showErrors(r.fields || {}); dlgErr.textContent = r.error || "Ошибка"; }
        });
      });
    });
  }

  // ------------------------------------------------------------ отчёты
  function reportsView(panel) {
    api("GET", "/api/reports").then(function (d) {
      var sel = h("select", { id: "rep-sel" }, d.reports.map(function (r) { return h("option", { value: r.id, text: r.title }); }));
      var today = new Date(), from = new Date(today.getTime() - 29 * 864e5);
      function iso(x) { return x.toISOString().slice(0, 10); }
      var df = h("input", { type: "date", id: "rep-from", value: iso(from) }), dt = h("input", { type: "date", id: "rep-to", value: iso(today) });
      var out = h("div");
      var form = h("form", { class: "toolbar" }, [
        h("div", { class: "fld q" }, [h("label", { for: "rep-sel", text: "Отчёт" }), sel]),
        h("div", { class: "fld" }, [h("label", { for: "rep-from", text: "Период с" }), df]),
        h("div", { class: "fld" }, [h("label", { for: "rep-to", text: "по" }), dt]),
        h("div", { class: "btns" }, [h("button", { class: "btn", type: "submit", text: "Сформировать" }),
                                     h("button", { class: "btn btn-ghost", type: "button", text: "Печать", onclick: function () { window.print(); } })])]);
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (df.value && dt.value && df.value > dt.value) { out.textContent = ""; out.appendChild(h("p", { class: "form-error", text: "Дата начала позже даты окончания" })); return; }
        api("GET", "/api/reports/" + sel.value + "?" + qs({ date_from: df.value, date_to: dt.value })).then(function (r) {
          out.textContent = "";
          if (r.__status !== 200) { out.appendChild(h("p", { class: "form-error", text: r.error })); return; }
          out.appendChild(h("h4", { text: r.title + " (" + r.period[0] + " — " + r.period[1] + ")" }));
          // столбчатая диаграмма по столбцу «Выручка»
          var vi = r.columns.findIndex(function (c) { return /Выручка/.test(c); });
          if (vi >= 0 && r.rows.length) {
            var max = Math.max.apply(null, r.rows.map(function (x) { return +x[vi] || 0; })) || 1;
            var bars = h("div", { class: "bars", "aria-hidden": "true" });
            r.rows.slice(0, 31).forEach(function (x) {
              var b = h("div", { class: "b" }); b.style.width = (100 * (+x[vi] || 0) / max) + "%";
              bars.appendChild(h("div", { class: "bar-row" }, [h("span", { text: x[0] }), h("div", {}, [b]), h("span", { class: "num", text: money(x[vi]) })]));
            });
            out.appendChild(bars);
          }
          var tb = h("tbody");
          r.rows.forEach(function (x) { tb.appendChild(h("tr", {}, x.map(function (v, i) { return h("td", { class: typeof v === "number" ? "num" : null, text: typeof v === "number" && /₽/.test(r.columns[i]) ? money(v) : (v === null ? "" : v) }); }))); });
          if (!r.rows.length) tb.appendChild(h("tr", {}, [h("td", { colspan: r.columns.length, class: "muted", text: "Нет данных за период" })]));
          out.appendChild(h("div", { class: "table-wrap" }, [h("table", {}, [h("thead", {}, [h("tr", {}, r.columns.map(function (c) { return h("th", { text: c }); }))]), tb])]));
        });
      });
      panel.appendChild(h("h3", { text: "Отчёты" }));
      panel.appendChild(form); panel.appendChild(out);
      form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit"));
    });
  }

  init();
})();
