"""Серверная валидация вводимых данных."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("validation")
        self.errors = errors


NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё .'\-]*$")
TEXT_RE = re.compile(r"^[^<>]*$")           # запрет угловых скобок в текстовых полях
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def normalize_phone(value):
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    else:
        return None
    return "+" + digits


def clean(spec, raw, partial=False):
    """spec: {поле: {type, required, ...}}; возвращает очищенный dict или ValidationError."""
    out, errors = {}, {}
    for name, f in spec.items():
        if f.get("readonly"):
            continue
        present = name in raw
        if partial and not present:
            continue
        v = raw.get(name)
        if isinstance(v, str):
            v = v.strip()
        if v in (None, ""):
            if f.get("required") and not (f.get("optional_on_update") and partial):
                errors[name] = "Обязательное поле"
            else:
                out[name] = f.get("default") if not partial else None
                if f["type"] == "bool":
                    out[name] = 0
            continue
        t = f["type"]
        label = f.get("label", name)
        try:
            if t in ("str", "name"):
                v = str(v)
                lo, hi = f.get("min", 1), f.get("max", 200)
                if not lo <= len(v) <= hi:
                    raise ValueError(f"длина от {lo} до {hi} символов")
                if t == "name" and not NAME_RE.match(v):
                    raise ValueError("только буквы, пробел, дефис")
                if not TEXT_RE.match(v):
                    raise ValueError("недопустимые символы < >")
                if "regex" in f and not re.match(f["regex"], v):
                    raise ValueError(f.get("regex_msg", "неверный формат"))
            elif t == "int" or t == "fk":
                if isinstance(v, bool) or not re.fullmatch(r"-?\d+", str(v)):
                    raise ValueError("целое число")
                v = int(v)
                if t == "int" and not f.get("min", -10**9) <= v <= f.get("max", 10**9):
                    raise ValueError(f"от {f.get('min')} до {f.get('max')}")
            elif t == "num":
                v = Decimal(str(v).replace(",", "."))
                if not v.is_finite() or not Decimal(str(f.get("min", 0))) <= v <= Decimal(str(f.get("max", 10**9))):
                    raise ValueError(f"число от {f.get('min')} до {f.get('max')}")
                v = float(round(v, 2))
            elif t == "date":
                d = date.fromisoformat(str(v))
                if not date(2000, 1, 1) <= d <= date(2100, 1, 1):
                    raise ValueError("дата вне допустимого диапазона")
                v = d.isoformat()
            elif t == "bool":
                v = 1 if v in (True, 1, "1", "true", "on") else 0
            elif t == "enum":
                if v not in f["values"]:
                    raise ValueError("недопустимое значение")
            elif t == "phone":
                v = normalize_phone(v)
                if not v:
                    raise ValueError("телефон в формате +7XXXXXXXXXX")
            elif t == "email":
                v = str(v)
                if len(v) > 120 or not EMAIL_RE.match(v):
                    raise ValueError("некорректный e-mail")
            elif t == "password":
                v = str(v)
            out[name] = v
        except (ValueError, InvalidOperation, TypeError) as e:
            ok_msg = isinstance(e, ValueError) and str(e) and not str(e).startswith(("Invalid", "invalid", "month", "day", "year"))
            msg = str(e) if ok_msg else "неверное значение"
            errors[name] = f"{label}: {msg}"
    if errors:
        raise ValidationError(errors)
    return out
