"""Конфигурация приложения. Все секреты вынесены из исходного кода
в каталог instance/ (вне корня сайта) или в переменные окружения."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"          # БД, ключи — вне каталога static
STORAGE_DIR = BASE_DIR / "storage"            # файловый архив — вне каталога static
ARCHIVE_DIR = STORAGE_DIR / "archive"
UPLOAD_DIR = STORAGE_DIR / "uploads"
CERT_DIR = BASE_DIR / "certs"
BACKUP_DIR = BASE_DIR / "backups"

DB_PATH = Path(os.environ.get("VB_DB_PATH", INSTANCE_DIR / "vkusno.db"))
KEY_PATH = Path(os.environ.get("VB_KEY_PATH", INSTANCE_DIR / "data.key"))

# --- Шапка сайта ---
SYSTEM_NAME = "АИС «Вкусно и быстро»"
SYSTEM_FULL_NAME = "Автоматизированная информационная система учёта заказов сети ресторанов «Вкусно и быстро»"
STUDENT = "Скворцова Анастасия Дмитриевна"
GROUP = "НБИбд-01-24"
TOPIC_NO = "3"

# --- Параметры безопасности ---
PBKDF2_ITERATIONS = 600_000          # рекомендация OWASP 2023+ для PBKDF2-HMAC-SHA256
PASSWORD_MIN_LEN = 8
MAX_FAILED_ATTEMPTS = 5              # неудачных попыток подряд ...
ATTEMPT_WINDOW_SEC = 15 * 60         # ... в течение 15 минут
LOCKOUT_SEC = 5 * 60                 # блокировка входа на 5 минут
SESSION_IDLE_TIMEOUT = 15 * 60       # тайм-аут бездействия
SESSION_ABSOLUTE_TIMEOUT = 8 * 3600  # максимальная длительность сессии
SESSION_COOKIE = "vb_sid"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_UPLOAD = {               # расширение -> (MIME, сигнатура файла)
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".pdf": ("application/pdf", b"%PDF-"),
}

DEBUG = os.environ.get("VB_DEBUG", "0") == "1"   # в рабочем режиме отладка выключена
