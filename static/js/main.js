/* Общие сценарии: меню, клиентская валидация форм, таймер бездействия. Без inline-скриптов (CSP). */
(function () {
  "use strict";

  // ---------- мобильное меню
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("main-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // ---------- показать/скрыть пароль
  document.querySelectorAll(".pw-toggle").forEach(function (b) {
    b.addEventListener("click", function () {
      var inp = b.parentNode.querySelector("input");
      inp.type = inp.type === "password" ? "text" : "password";
    });
  });

  function setErr(input, msg) {
    var span = document.querySelector('.field-error[data-for="' + input.id + '"]');
    if (span) span.textContent = msg || "";
    input.setAttribute("aria-invalid", msg ? "true" : "false");
  }

  // ---------- валидация формы входа (дублируется на сервере)
  var lf = document.getElementById("login-form");
  if (lf) {
    lf.addEventListener("submit", function (e) {
      var login = document.getElementById("f-login"), pw = document.getElementById("f-password");
      var ok = true;
      if (!/^[A-Za-z0-9_.\-]{3,32}$/.test(login.value.trim())) {
        setErr(login, "Логин: 3–32 символа — латиница, цифры, _ . -"); ok = false;
      } else setErr(login, "");
      if (!pw.value) { setErr(pw, "Введите пароль"); ok = false; }
      else if (pw.value.length > 128) { setErr(pw, "Не более 128 символов"); ok = false; }
      else setErr(pw, "");
      if (!ok) e.preventDefault();
    });
  }

  // ---------- валидация загрузки файла
  var uf = document.getElementById("upload-form");
  if (uf) {
    uf.addEventListener("submit", function (e) {
      var inp = document.getElementById("u-file"), f = inp.files[0];
      var msg = "";
      if (!f) msg = "Выберите файл";
      else if (!/\.(png|jpe?g|pdf)$/i.test(f.name)) msg = "Разрешены только PNG, JPEG, PDF";
      else if (f.size > 5 * 1024 * 1024) msg = "Размер файла не должен превышать 5 МБ";
      setErr(inp, msg);
      if (msg) e.preventDefault();
    });
  }

  // ---------- подтверждение действий
  document.querySelectorAll("form.js-confirm").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm") || "Подтвердите действие")) e.preventDefault();
    });
  });

  // ---------- таймер бездействия: по истечении сервер уже удалил сессию → обновляем страницу
  var idle = document.getElementById("idle-info");
  if (idle) {
    var timeout = parseInt(idle.getAttribute("data-timeout"), 10) * 1000;
    var last = Date.now();
    window.__vbTouch = function () { last = Date.now(); };   // вызывается после запросов к серверу
    setInterval(function () {
      var left = Math.max(0, timeout - (Date.now() - last));
      var m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
      idle.textContent = "Автоматический выход через " + m + ":" + (s < 10 ? "0" : "") + s + " без активности на сервере.";
      if (left === 0) window.location.href = "/";
    }, 1000);
  }
})();
