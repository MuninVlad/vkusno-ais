"""Снимки экранных форм и проверка вёрстки в браузере (Playwright).
Сервер должен быть запущен: python run.py.   Запуск: python tests/screenshots.py [chromium|firefox]"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.accounts import passwords  # noqa: E402

PW = passwords()

URL = "https://localhost:8443"
OUT = Path(__file__).resolve().parent.parent / "storage" / "archive" / "screens"
OUT.mkdir(parents=True, exist_ok=True)
engine = sys.argv[1] if len(sys.argv) > 1 else "chromium"
shots = engine == "chromium"
problems = []

with sync_playwright() as p:
    browser = getattr(p, engine).launch()
    ctx = browser.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 860}, locale="ru-RU")
    page = ctx.new_page()
    page.on("console", lambda m: m.type in ("error", "warning") and problems.append(f"console {m.type}: {m.text}"))
    page.on("response", lambda r: r.status >= 400 and problems.append(f"HTTP {r.status} {r.url}"))
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    def snap(name, full=False):
        if shots:
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)

    page.goto(URL + "/system")                       # без входа → переадресация
    assert page.url.rstrip("/") == URL, page.url
    snap("01_index_guest")
    page.fill("#f-login", "admin")
    page.fill("#f-password", "bad-password1A")
    page.click("#login-form button[type=submit]")
    page.wait_for_selector(".flash-error")
    snap("09_login_error")
    page.fill("#f-login", "admin")
    page.fill("#f-password", PW["admin"])
    page.click("#login-form button[type=submit]")
    page.wait_for_selector(".flash-success")
    snap("02_index_auth")

    page.click("text=2. Описание системы")
    page.wait_for_selector("#app-module .tabs")
    snap("03_system_top")
    imgs = page.eval_on_selector_all(".fig img", "els => els.map(e => [e.getAttribute('src'), e.naturalWidth])")
    page.evaluate("Promise.all([...document.images].map(i => { i.loading='eager'; return i.decode().catch(()=>{}); }))")
    page.wait_for_timeout(500)
    imgs = page.eval_on_selector_all(".fig img", "els => els.map(e => [e.getAttribute('src'), e.naturalWidth])")
    broken = [s for s, w in imgs if not w]
    if broken:
        problems.append(f"не загрузились рисунки: {broken}")
    print("рисунков на странице 2:", len(imgs), "не загружено:", len(broken))

    page.locator("#module").scroll_into_view_if_needed()
    page.wait_for_selector("#mod-panel tbody tr")
    page.wait_for_timeout(400)
    page.evaluate("window.scrollTo(0, document.getElementById('module').getBoundingClientRect().top + window.scrollY - 70)")
    page.wait_for_timeout(400)
    snap("04_module_orders")
    page.click("text=Новый заказ")
    page.wait_for_selector("#dlg[open]")
    page.select_option("#fld-restaurant_id", "1")
    page.select_option("#fld-employee_id", index=2)
    page.select_option(".item-row select", "1")
    page.click("text=+ Добавить позицию")
    page.locator(".item-row select").nth(1).select_option("8")
    page.locator(".item-row input").nth(0).fill("2")
    snap("05_module_order_form")
    page.click("#dlg-ok")
    page.wait_for_selector(".toast")
    toast = page.inner_text(".toast")
    print("создание заказа:", toast)

    page.click(".tab[data-tab=menu_items]")
    page.wait_for_selector("#mod-panel tbody tr")
    page.click("#mod-panel >> text=Добавить")
    page.fill("#fld-name", "<b>x</b>")
    page.fill("#fld-price", "0")
    page.fill("#fld-calories", "-5")
    page.click("#dlg-ok")
    snap("10_module_validation")
    page.click("#dlg-cancel")

    page.click(".tab[data-tab=reports]")
    page.wait_for_selector("#mod-panel h4")
    snap("06_module_reports")

    for tab in ["restaurants", "categories", "positions", "employees", "customers", "users"]:
        page.click(f".tab[data-tab={tab}]")
        page.wait_for_selector("#mod-panel tbody tr")

    page.click("text=3. Файловый архив")
    page.wait_for_selector("table.files")
    snap("07_archive")
    links = page.eval_on_selector_all("table.files a", "els => els.map(e => e.href)")
    bad = []
    for href in links:
        r = ctx.request.get(href)
        if r.status != 200:
            bad.append((href, r.status))
    print("ссылок в архиве:", len(links), "битых:", len(bad), bad[:5])
    if bad:
        problems.append(f"битые ссылки: {bad}")

    # мобильная версия 320 px
    m = browser.new_context(ignore_https_errors=True, viewport={"width": 320, "height": 640}, storage_state=ctx.storage_state(),
                            is_mobile=engine == "chromium", has_touch=True)
    mp = m.new_page()
    for path in ("/", "/system", "/archive"):
        mp.goto(URL + path)
        w = mp.evaluate("document.documentElement.scrollWidth")
        if w > 320:
            problems.append(f"горизонтальная прокрутка на {path}: {w}px")
    mp.goto(URL + "/")
    mp.click(".nav-toggle")
    if shots:
        mp.screenshot(path=str(OUT / "08_mobile_320.png"), full_page=False)
    browser.close()

print(engine, "ПРОБЛЕМЫ:" if problems else "проблем не обнаружено", *problems, sep="\n")
