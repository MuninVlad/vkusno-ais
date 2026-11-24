/* Общие сценарии страниц версии для GitHub Pages: вход/выход, проверка сессии,
   расшифровка страниц 2–3 и файлов архива после входа, клиентская валидация. */
(function () {
  "use strict";
  var page = document.body.getAttribute("data-page");
  var sess = window.VBAuth.session();

  // ---------- защищённые страницы: без сессии — на страницу 1
  if ((page === "system" || page === "archive") && !sess) {
    window.VBAuth.flash("Для доступа к странице необходимо войти в систему.", "warning");
    location.replace("index.html");
    return;
  }
  if (sess) {
    window.VBAuth.touch();
    document.body.classList.add("is-auth");
    document.querySelectorAll("[data-user-login]").forEach(function (el) { el.textContent = sess.login; });
    document.querySelectorAll("[data-user-role]").forEach(function (el) { el.textContent = sess.role_name; });
  }

  // ---------- сообщения
  var box = document.getElementById("flashes");
  window.VBAuth.takeFlashes().forEach(function (f) {
    var d = document.createElement("div"); d.className = "flash flash-" + f[0]; d.setAttribute("role", "alert"); d.textContent = f[1];
    box.appendChild(d);
  });

  // ---------- меню, пароль
  var toggle = document.querySelector(".nav-toggle"), nav = document.getElementById("main-nav");
  if (toggle && nav) toggle.addEventListener("click", function () {
    var open = nav.classList.toggle("open"); toggle.setAttribute("aria-expanded", open ? "true" : "false");
  });
  document.querySelectorAll(".pw-toggle").forEach(function (b) {
    b.addEventListener("click", function () { var i = b.parentNode.querySelector("input"); i.type = i.type === "password" ? "text" : "password"; });
  });
  document.querySelectorAll(".js-logout").forEach(function (b) {
    b.addEventListener("click", function () {
      window.VBAuth.logout(); window.VBAuth.flash("Вы вышли из системы.", "success"); location.href = "index.html";
    });
  });

  function setErr(input, msg) {
    var span = document.querySelector('.field-error[data-for="' + input.id + '"]');
    if (span) span.textContent = msg || "";
    input.setAttribute("aria-invalid", msg ? "true" : "false");
  }

  // ---------- вход
  var lf = document.getElementById("login-form");
  if (lf) lf.addEventListener("submit", function (e) {
    e.preventDefault();
    var login = document.getElementById("f-login"), pw = document.getElementById("f-password"), ok = true;
    if (!/^[A-Za-z0-9_.\-]{3,32}$/.test(login.value.trim())) { setErr(login, "Логин: 3–32 символа — латиница, цифры, _ . -"); ok = false; } else setErr(login, "");
    if (!pw.value) { setErr(pw, "Введите пароль"); ok = false; } else if (pw.value.length > 128) { setErr(pw, "Не более 128 символов"); ok = false; } else setErr(pw, "");
    if (!ok) return;
    var btn = lf.querySelector("button[type=submit]"); btn.disabled = true; btn.textContent = "Проверка…";
    window.VBAuth.login(login.value, pw.value).then(function (r) {
      if (r.ok) { window.VBAuth.flash("Добро пожаловать, " + r.login + "!", "success"); location.reload(); return; }
      box.textContent = "";
      var d = document.createElement("div"); d.className = "flash flash-error"; d.setAttribute("role", "alert"); d.textContent = r.msg; box.appendChild(d);
      pw.value = ""; btn.disabled = false; btn.textContent = "Войти";
    }).catch(function () { btn.disabled = false; btn.textContent = "Войти"; });
  });

  // ---------- таймер бездействия
  var idle = document.getElementById("idle-info");
  if (sess && idle) {
    var last = Date.now(), lastTouch = 0;
    window.__vbTouch = function () { last = Date.now(); };
    ["click", "keydown"].forEach(function (ev) {
      window.addEventListener(ev, function () { last = Date.now(); if (last - lastTouch > 30000) { lastTouch = last; window.VBAuth.touch(); } });
    });
    setInterval(function () {
      var left = Math.max(0, window.VBAuth.IDLE - (Date.now() - last));
      var m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
      idle.textContent = "Автоматический выход через " + m + ":" + (s < 10 ? "0" : "") + s + " без активности.";
      if (left === 0) { window.VBAuth.logout(); window.VBAuth.flash("Сессия завершена по тайм-ауту. Войдите снова.", "warning"); location.href = "index.html"; }
    }, 1000);
  }

  // ---------- расшифровка содержимого страниц 2–3
  var MIME = { svg: "image/svg+xml", png: "image/png", jpg: "image/jpeg", pdf: "application/pdf", zip: "application/zip",
               docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" };
  function mimeOf(name) { var ext = name.split(".").pop().toLowerCase(); return MIME[ext] || "text/plain;charset=utf-8"; }
  async function fileBlob(id, name) {
    var key = await window.VBAuth.dataKey();
    if (!key) { location.replace("index.html"); throw new Error("auth"); }
    var raw = new Uint8Array(await (await fetch("files/" + id + ".enc")).arrayBuffer());
    window.VBAuth.touch();
    return new Blob([await window.VBAuth.decrypt(key, raw, "file:" + id)], { type: mimeOf(name) });
  }
  function hydrate(root) {
    root.querySelectorAll("img[data-file]").forEach(function (img) {
      fileBlob(img.getAttribute("data-file"), img.getAttribute("data-name")).then(function (b) { img.src = URL.createObjectURL(b); });
    });
    root.querySelectorAll("a[data-file]").forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        var id = a.getAttribute("data-file"), name = a.getAttribute("data-name"), dl = a.getAttribute("data-act") === "download";
        var w = dl ? null : window.open("", "_blank");          // окно открывается сразу — иначе браузер блокирует
        fileBlob(id, name).then(function (b) {
          var url = URL.createObjectURL(b);
          if (dl) { var t = document.createElement("a"); t.href = url; t.download = name; document.body.appendChild(t); t.click(); t.remove(); }
          else if (w) w.location = url;
          setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
        }).catch(function () { if (w) w.close(); });
      });
    });
  }
  var secure = document.getElementById("secure");
  if (secure && sess) {
    (async function () {
      var key = await window.VBAuth.dataKey();
      var raw = new Uint8Array(await (await fetch(secure.getAttribute("data-src"), { cache: "no-store" })).arrayBuffer());
      var html = new TextDecoder().decode(await window.VBAuth.decrypt(key, raw, secure.getAttribute("data-aad")));
      secure.innerHTML = html;       // собственное содержимое сайта, расшифрованное ключом пользователя
      hydrate(secure);
      secure.querySelectorAll("[data-user-role]").forEach(function (el) { el.textContent = sess.role_name; });
      if (page === "system") { var s = document.createElement("script"); s.src = "assets/js/module.js"; document.body.appendChild(s); }
      if (location.hash) { var t = document.getElementById(location.hash.slice(1)); if (t) t.scrollIntoView(); }
    })().catch(function () {
      secure.textContent = "Не удалось расшифровать страницу. Войдите в систему заново.";
      window.VBAuth.logout();
    });
  }
})();
