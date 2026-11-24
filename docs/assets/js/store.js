/* Хранилище данных версии для GitHub Pages: БД — зашифрованный JSON (AES-256-GCM).
   Исходные данные — data/db.enc; изменения сохраняются в браузере (localStorage) тоже в зашифрованном виде. */
(function () {
  "use strict";
  var enc = new TextEncoder(), dec = new TextDecoder();
  var build = null;

  async function buildId() {
    if (!build) build = (await (await fetch("data/users.json", { cache: "no-store" })).json()).build;
    return build;
  }
  async function load(dk) {
    var id = await buildId();
    try {
      var saved = JSON.parse(localStorage.getItem("vb_db") || "null");
      if (saved && saved.build === id) {
        return JSON.parse(dec.decode(await window.VBAuth.decrypt(dk, window.VBAuth.unb64(saved.blob), "db")));
      }
    } catch (e) { /* повреждённая или чужая копия — берём исходную */ }
    var raw = new Uint8Array(await (await fetch("data/db.enc", { cache: "no-store" })).arrayBuffer());
    return JSON.parse(dec.decode(await window.VBAuth.decrypt(dk, raw, "db")));
  }
  async function save(dk, db) {
    var blob = await window.VBAuth.encrypt(dk, enc.encode(JSON.stringify(db)), "db");
    localStorage.setItem("vb_db", JSON.stringify({ build: await buildId(), blob: window.VBAuth.b64(blob) }));
  }
  function audit(db, userId, action, entity, entityId) {
    db.audit_log.push({ id: (db.audit_log.length ? db.audit_log[db.audit_log.length - 1].id : 0) + 1, user_id: userId,
      action: action, entity: entity || null, entity_id: entityId || null, created_at: now() });
    if (db.audit_log.length > 2000) db.audit_log.splice(0, db.audit_log.length - 2000);
  }
  function now() {
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }
  window.VBStore = { load: load, save: save, audit: audit, now: now };
})();
