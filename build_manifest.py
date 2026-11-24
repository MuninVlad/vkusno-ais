"""Формирование манифеста файлового архива (storage/archive/manifest.json) — белый список файлов страницы 3."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCH = ROOT / "storage" / "archive"
G = ARCH / "graphics"


def main():
    from app.content import FIGURES
    items = []
    def add(i, grp, path, desc):
        items.append({"id": i, "group": grp, "path": path, "description": desc})

    # ---- графические
    add("g-logo", "Графические файлы", "static/img/logo.svg", "Логотип системы")
    for f, cap, _ in FIGURES:
        add("g-" + f.rsplit(".", 1)[0], "Графические файлы", f"storage/archive/graphics/{f}", cap)
    for p in sorted((ARCH / "screens").glob("*.png")):
        add("g-scr-" + p.stem, "Графические файлы", f"storage/archive/screens/{p.name}", "Скриншот интерфейса: " + SCREEN_DESC.get(p.stem, p.stem))

    # ---- документация
    for i, name, desc in DOCS:
        add(i, "Документация", f"storage/archive/docs/{name}", desc)

    # ---- текстовые
    add("s-sql-schema", "Текстовые файлы", "sql/schema.sql", "SQL-скрипт создания таблиц, ограничений целостности, индексов и представления")
    add("s-sql-seed", "Текстовые файлы", "sql/seed.sql", "SQL-скрипт заполнения БД тестовыми данными (сформирован init_db.py)")

    # ---- исходный код
    for rel, desc in SOURCE:
        add("c-" + rel.replace("/", "-").replace(".", "-"), "Исходный код", rel, desc)
    # ---- криптография
    for rel, desc in CRYPTO_FILES:
        add("k-" + rel.replace("/", "-").replace(".", "-"), "Криптографические функции", rel, desc)
    # ---- архив исходников целиком
    src_zip = ARCH / "docs" / "vkusno_ais_source.zip"
    (ARCH / "docs").mkdir(exist_ok=True)
    with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob("*"):
            rel = p.relative_to(ROOT)
            if p.is_file() and rel.parts[0] not in ("instance", "certs", "backups", "storage", ".pytest_cache", "site_github", "docs", ".ruff_cache", ".git") and ".build" not in rel.parts \
                    and "__pycache__" not in rel.parts:
                z.write(p, str(Path("vkusno_ais") / rel))
    add("c-zip", "Исходный код", "storage/archive/docs/vkusno_ais_source.zip", "Полный архив исходных файлов сайта (без БД и ключей)")

    (ARCH / "manifest.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), "utf-8")
    print("Манифест:", len(items), "файлов")


SCREEN_DESC = {"01_index_guest": "страница 1, гость (форма входа)", "02_index_auth": "страница 1 после входа",
               "03_system_top": "страница 2, оглавление", "04_module_orders": "рабочий модуль, заказы",
               "05_module_order_form": "форма нового заказа", "06_module_reports": "отчёт «Выручка по ресторанам»",
               "07_archive": "страница 3, файловый архив", "08_mobile_320": "мобильная версия, 320 px",
               "09_login_error": "сообщение об ошибке входа", "10_module_validation": "проверка ввода в форме"}
DOCS = [
    ("d-tz", "01_Техническое_задание.docx", "Техническое задание (ГОСТ 34.602-2020, упрощённая структура)"),
    ("d-pz", "02_Пояснительная_записка.docx", "Пояснительная записка (ГОСТ 7.32-2017)"),
    ("d-user", "03_Руководство_пользователя.docx", "Руководство пользователя с экранными формами"),
    ("d-admin", "04_Руководство_администратора.docx", "Руководство администратора: установка, настройка, резервное копирование"),
    ("d-db", "05_Описание_БД_и_модулей.docx", "Описание структуры базы данных и программных модулей"),
]
SOURCE = [
    ("README.md", "Краткая инструкция по установке и запуску"),
    ("requirements.txt", "Список зависимостей Python"),
    ("run.py", "Точка входа: запуск HTTPS-сервера (TLS 1.2+)"),
    ("init_db.py", "Создание БД и заполнение тестовыми данными"),
    ("build_manifest.py", "Формирование манифеста файлового архива"),
    ("app/__init__.py", "Фабрика приложения, маршруты страниц, обработка ошибок"),
    ("app/config.py", "Конфигурация и параметры безопасности"),
    ("app/db.py", "Доступ к БД (параметризованные запросы), журнал аудита"),
    ("app/api.py", "REST API: добавление, редактирование, удаление, поиск, фильтрация"),
    ("app/reports.py", "Запросы и 5 отчётов по предметной области"),
    ("app/validation.py", "Серверная валидация вводимых данных"),
    ("app/archive.py", "Файловый архив: выдача файлов с проверкой прав, загрузка"),
    ("app/content.py", "Текстовое содержимое страниц 1 и 2"),
    ("templates/base.html", "Общий шаблон: шапка, навигация, подвал"),
    ("templates/index.html", "Страница 1 — главная и авторизация"),
    ("templates/system.html", "Страница 2 — описание системы и рабочий модуль"),
    ("templates/archive.html", "Страница 3 — файловый архив"),
    ("templates/error.html", "Страница ошибки"),
    ("static/css/style.css", "Стили, адаптивная вёрстка"),
    ("static/js/main.js", "Клиентская валидация форм, меню, таймер сессии"),
    ("static/js/module.js", "Рабочий модуль: CRUD, поиск, фильтры, отчёты"),
    ("tests/conftest.py", "Окружение автотестов"),
    ("tests/test_app.py", "Функциональные тесты и тесты защищённости"),
]
CRYPTO_FILES = [
    ("app/crypto.py", "PBKDF2-HMAC-SHA256 (пароли), AES-256-GCM (поля БД), HMAC-SHA256 (слепой индекс), HKDF (подключи), CSPRNG"),
    ("app/security.py", "Серверные сессии, CSRF-токены, блокировка подбора, заголовки CSP/HSTS"),
    ("gen_cert.py", "Генерация самоподписанного TLS-сертификата RSA-2048 / SHA-256"),
    ("backup.py", "Резервное копирование с контролем целостности SHA-256"),
]

if __name__ == "__main__":
    main()
