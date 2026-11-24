/* Аутентификация и криптография версии для GitHub Pages (Web Crypto API).
   Схема: ключ данных DK (AES-256) шифрует страницы 2–3, файлы архива и БД.
   Для каждого пользователя DK «обёрнут» ключом, выведенным из пароля
   PBKDF2-HMAC-SHA256 (600 000 итераций, соль 128 бит) → AES-256-GCM.
   Пароль нигде не хранится: верный пароль = успешная расшифровка профиля (тег GCM). */
(function () {
  "use strict";
  var IDLE = 15 * 60 * 1000, ABSOLUTE = 8 * 3600 * 1000;
  var MAX_FAILS = 5, WINDOW = 15 * 60 * 1000, LOCK = 5 * 60 * 1000;
  var enc = new TextEncoder(), dec = new TextDecoder();

  function b64(buf) { var s = "", a = new Uint8Array(buf); for (var i = 0; i < a.length; i++) s += String.fromCharCode(a[i]); return btoa(s); }
  function unb64(str) { var s = atob(str), a = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) a[i] = s.charCodeAt(i); return a; }
  async function sha256hex(text) {
    var h = await crypto.subtle.digest("SHA-256", enc.encode(text));
    return Array.prototype.map.call(new Uint8Array(h), function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
  }
  async function kek(password, salt, iterations) {
    var base = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveKey"]);
    return crypto.subtle.deriveKey({ name: "PBKDF2", salt: salt, iterations: iterations, hash: "SHA-256" }, base,
      { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  }
  async function aesDecrypt(key, blob, aad) {     // blob = nonce(12) ‖ шифртекст ‖ тег(16)
    return crypto.subtle.decrypt({ name: "AES-GCM", iv: blob.slice(0, 12), additionalData: enc.encode(aad) }, key, blob.slice(12));
  }
  async function aesEncrypt(key, data, aad) {
    var iv = crypto.getRandomValues(new Uint8Array(12));
    var ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv, additionalData: enc.encode(aad) }, key, data);
    var out = new Uint8Array(12 + ct.byteLength); out.set(iv, 0); out.set(new Uint8Array(ct), 12);
    return out;
  }

  // ---------------- сессия (sessionStorage: закрытие вкладки = выход)
  function readSession() {
    try {
      var s = JSON.parse(sessionStorage.getItem("vb_sess") || "null");
      if (!s) return null;
      var now = Date.now();
      if (now - s.last > IDLE || now - s.created > ABSOLUTE) {
        sessionStorage.removeItem("vb_sess");
        flash("Сессия завершена по тайм-ауту. Войдите снова.", "warning");
        return null;
      }
      return s;
    } catch (e) { return null; }
  }
  function touch() {
    var s = readSession(); if (!s) return;
    s.last = Date.now(); sessionStorage.setItem("vb_sess", JSON.stringify(s));
  }
  function flash(msg, kind) {
    try { var a = JSON.parse(sessionStorage.getItem("vb_flash") || "[]"); a.push([kind || "success", msg]); sessionStorage.setItem("vb_flash", JSON.stringify(a)); } catch (e) { /* без хранилища — без сообщения */ }
  }
  function takeFlashes() {
    try { var a = JSON.parse(sessionStorage.getItem("vb_flash") || "[]"); sessionStorage.removeItem("vb_flash"); return a; } catch (e) { return []; }
  }

  // ---------------- ограничение попыток (в браузере)
  function attempts(login) { try { return JSON.parse(localStorage.getItem("vb_fail_" + login) || "[]"); } catch (e) { return []; } }
  function lockedFor(login) {
    var now = Date.now(), a = attempts(login).filter(function (t) { return now - t < WINDOW; });
    if (a.length >= MAX_FAILS) { var left = a[a.length - MAX_FAILS] + LOCK - now; if (left > 0) return left; }
    return 0;
  }
  function addFail(login) { var a = attempts(login); a.push(Date.now()); try { localStorage.setItem("vb_fail_" + login, JSON.stringify(a.slice(-20))); } catch (e) { /* нет хранилища */ } }
  function clearFails(login) { try { localStorage.removeItem("vb_fail_" + login); } catch (e) { /* нет хранилища */ } }

  var usersCache = null;
  async function userRecords() {
    if (!usersCache) usersCache = await (await fetch("data/users.json", { cache: "no-store" })).json();
    var extra = {};
    try { extra = JSON.parse(localStorage.getItem("vb_users_extra") || "{}"); } catch (e) { extra = {}; }
    return Object.assign({}, usersCache.users, extra);
  }

  async function login(loginName, password) {
    var l = String(loginName || "").trim().toLowerCase();
    var locked = lockedFor(l);
    if (locked) return { ok: false, msg: "Слишком много неудачных попыток. Вход заблокирован на " + Math.ceil(locked / 60000) + " мин." };
    var recs = await userRecords();
    var rec = recs[await sha256hex(l)];
    var profile = null;
    if (rec) {
      try {
        var key = await kek(password, unb64(rec.salt), rec.iter);
        profile = JSON.parse(dec.decode(await aesDecrypt(key, unb64(rec.blob), "user:" + l)));
      } catch (e) { profile = null; }       // неверный пароль → тег GCM не сошёлся
    } else {
      await kek(password, new Uint8Array(16), 600000);   // одинаковое время ответа для несуществующего логина
    }
    if (profile) {
      var dk = await crypto.subtle.importKey("raw", unb64(profile.dk), "AES-GCM", false, ["encrypt", "decrypt"]);
      var db = await window.VBStore.load(dk);
      var u = db.users.filter(function (x) { return x.login.toLowerCase() === l; })[0];
      if (!u || !u.is_active) profile = null;
      else {
        var role = db.roles.filter(function (r) { return r.id === u.role_id; })[0];
        clearFails(l);
        sessionStorage.setItem("vb_sess", JSON.stringify({ login: u.login, user_id: u.id, role: role.code, role_name: role.name,
          dk: profile.dk, created: Date.now(), last: Date.now() }));
        window.VBStore.audit(db, u.id, "login");
        await window.VBStore.save(dk, db);
        return { ok: true, login: u.login };
      }
    }
    addFail(l);
    if (lockedFor(l)) return { ok: false, msg: "Слишком много неудачных попыток. Вход временно заблокирован на 5 мин." };
    return { ok: false, msg: "Неверный логин или пароль." };
  }

  async function dataKey() {
    var s = readSession(); if (!s) return null;
    return crypto.subtle.importKey("raw", unb64(s.dk), "AES-GCM", false, ["encrypt", "decrypt"]);
  }
  async function wrapForUser(loginName, password, dkB64) {
    var l = loginName.toLowerCase(), salt = crypto.getRandomValues(new Uint8Array(16));
    var key = await kek(password, salt, 600000);
    var blob = await aesEncrypt(key, enc.encode(JSON.stringify({ login: l, dk: dkB64 })), "user:" + l);
    var extra = {};
    try { extra = JSON.parse(localStorage.getItem("vb_users_extra") || "{}"); } catch (e) { extra = {}; }
    extra[await sha256hex(l)] = { salt: b64(salt), iter: 600000, blob: b64(blob) };
    localStorage.setItem("vb_users_extra", JSON.stringify(extra));
  }

  window.VBAuth = {
    session: readSession, touch: touch, login: login, dataKey: dataKey, flash: flash, takeFlashes: takeFlashes,
    logout: function () { sessionStorage.removeItem("vb_sess"); },
    decrypt: aesDecrypt, encrypt: aesEncrypt, b64: b64, unb64: unb64, wrapForUser: wrapForUser, IDLE: IDLE,
  };
})();
