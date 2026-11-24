"""Криптографические функции системы.

Хеширование (необратимо) — пароли и поиск по зашифрованным полям:
  * PBKDF2-HMAC-SHA256, 600 000 итераций, соль 16 байт, выход 32 байта;
  * HMAC-SHA256 (ключ 256 бит) — «слепой индекс» телефона клиента.
Шифрование (обратимо) — конфиденциальные поля БД:
  * AES-256-GCM, ключ 256 бит, nonce 96 бит (случайный для каждой записи),
    тег аутентичности 128 бит; ассоциированные данные = имя поля.

Схема хранения ключа: мастер-ключ 32 байта хранится в файле instance/data.key
(права 0600, вне корня сайта, не попадает в БД и резервные копии БД) или
передаётся через переменную окружения VB_MASTER_KEY (base64). Из мастер-ключа
функцией HKDF-SHA256 выводятся два независимых подключа: для AES и для HMAC.
"""
import base64
import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import config

_ENC_PREFIX = "v1:"
_keys = {}


# ---------------------------------------------------------------- пароли
def hash_password(password: str, iterations: int = config.PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 base64.b64decode(salt_b64), int(iters), dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))   # сравнение за постоянное время
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password("dummy-password-for-timing", 600_000)


# ---------------------------------------------------------------- ключи
def _master_key() -> bytes:
    env = os.environ.get("VB_MASTER_KEY")
    if env:
        key = base64.b64decode(env)
    else:
        path = config.KEY_PATH
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64encode(secrets.token_bytes(32)))
            os.chmod(path, 0o600)
        key = base64.b64decode(path.read_bytes())
    if len(key) != 32:
        raise RuntimeError("Мастер-ключ должен иметь длину 256 бит")
    return key


def _subkey(purpose: bytes) -> bytes:
    if purpose not in _keys:
        _keys[purpose] = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                              info=b"vkusno-ais/" + purpose).derive(_master_key())
    return _keys[purpose]


def reset_key_cache():
    _keys.clear()


# ---------------------------------------------------------------- AES-256-GCM
def encrypt_field(plaintext, field: str):
    if plaintext is None or plaintext == "":
        return None
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_subkey(b"aes")).encrypt(nonce, str(plaintext).encode("utf-8"), field.encode())
    return _ENC_PREFIX + base64.b64encode(nonce + ct).decode()


def decrypt_field(token, field: str):
    if not token:
        return None
    if not token.startswith(_ENC_PREFIX):
        raise ValueError("Неизвестный формат шифртекста")
    raw = base64.b64decode(token[len(_ENC_PREFIX):])
    return AESGCM(_subkey(b"aes")).decrypt(raw[:12], raw[12:], field.encode()).decode("utf-8")


# ---------------------------------------------------------------- HMAC
def blind_index(value: str) -> str:
    return hmac.new(_subkey(b"hmac"), value.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- токены
def new_token() -> str:
    """Криптостойкий идентификатор (256 бит, модуль secrets → os.urandom)."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
