"""Резервное копирование БД и файлового архива.

    python backup.py                     — создать копию backups/vkusno_ГГГГММДД_ЧЧММ.zip
    python backup.py --restore ФАЙЛ.zip  — восстановить (с проверкой SHA-256)

Ротация: хранятся 7 последних ежедневных копий и 4 воскресные (еженедельные).
Ключ шифрования instance/data.key в копию НЕ включается — его резервируют отдельно.
Пример задания cron:  0 3 * * *  cd /opt/vkusno_ais && python3 backup.py
"""
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app import config
from app.crypto import file_sha256

MANIFEST = config.BACKUP_DIR / "manifest.txt"


def create():
    config.BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = config.BACKUP_DIR / f"vkusno_{stamp}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        db_copy = Path(tmp) / "vkusno.db"
        src, dst = sqlite3.connect(str(config.DB_PATH)), sqlite3.connect(str(db_copy))
        src.backup(dst)                         # Online Backup API: согласованная копия без остановки
        src.close()
        dst.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_copy, "instance/vkusno.db")
            for p in config.STORAGE_DIR.rglob("*"):
                if p.is_file():
                    z.write(p, str(p.relative_to(config.BASE_DIR)))
    digest = file_sha256(target)
    with open(MANIFEST, "a", encoding="utf-8") as m:
        m.write(f"{target.name}  sha256={digest}\n")
    rotate()
    print("Резервная копия:", target, "\nSHA-256:", digest)
    return target


def rotate():
    copies = sorted(config.BACKUP_DIR.glob("vkusno_*.zip"), reverse=True)
    keep = set(copies[:7])
    weekly = [c for c in copies if datetime.strptime(c.stem[7:15], "%Y%m%d").weekday() == 6]
    keep |= set(weekly[:4])
    for c in copies:
        if c not in keep:
            c.unlink()


def restore(path):
    path = Path(path)
    expected = None
    if MANIFEST.exists():
        for line in MANIFEST.read_text("utf-8").splitlines():
            if line.startswith(path.name + " "):
                expected = line.split("sha256=")[1].strip()
    if expected and file_sha256(path) != expected:
        sys.exit("Ошибка: хеш-сумма архива не совпадает — копия повреждена или изменена.")
    if config.DB_PATH.exists():
        shutil.copy2(config.DB_PATH, config.DB_PATH.with_suffix(".db.before_restore"))
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                sys.exit("Ошибка: недопустимый путь в архиве")
        z.extractall(config.BASE_DIR)
    print("Восстановлено из", path, "(контроль целостности:", "пройден)" if expected else "манифест не найден)")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--restore":
        restore(sys.argv[2])
    else:
        create()
