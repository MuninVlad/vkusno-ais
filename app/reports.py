"""Запросы и отчёты по предметной области (5 отчётов)."""
from datetime import date

from flask import Blueprint, g, jsonify, request

from .db import query
from .security import roles_required
from .validation import ValidationError, clean

bp = Blueprint("reports", __name__, url_prefix="/api/reports")

PERIOD = {"date_from": {"type": "date", "label": "С"}, "date_to": {"type": "date", "label": "По"}}

REPORTS = {
    "revenue_by_restaurant": {
        "title": "Выручка по ресторанам за период",
        "columns": ["Ресторан", "Город", "Заказов", "Выручка, ₽", "Средний чек, ₽"],
        "sql": """SELECT r.name, r.city, COUNT(o.id), ROUND(COALESCE(SUM(v.total),0),2),
                         ROUND(COALESCE(AVG(v.total),0),2)
                  FROM restaurants r
                  LEFT JOIN orders o ON o.restaurant_id=r.id AND o.status<>'отменён'
                       AND date(o.created_at) BETWEEN ? AND ?
                  LEFT JOIN v_order_totals v ON v.order_id=o.id
                  GROUP BY r.id ORDER BY 4 DESC""",
    },
    "top_menu_items": {
        "title": "Топ-10 позиций меню по продажам",
        "columns": ["Позиция", "Категория", "Продано, шт.", "Выручка, ₽"],
        "sql": """SELECT m.name, c.name, SUM(oi.quantity), ROUND(SUM(oi.quantity*oi.unit_price),2)
                  FROM order_items oi JOIN orders o ON o.id=oi.order_id
                  JOIN menu_items m ON m.id=oi.menu_item_id JOIN categories c ON c.id=m.category_id
                  WHERE o.status<>'отменён' AND date(o.created_at) BETWEEN ? AND ?
                  GROUP BY m.id ORDER BY 3 DESC, 4 DESC LIMIT 10""",
    },
    "avg_check_by_type": {
        "title": "Средний чек и доля по типам заказа",
        "columns": ["Тип заказа", "Заказов", "Выручка, ₽", "Средний чек, ₽", "Доля выручки, %"],
        "sql": """WITH t AS (SELECT o.order_type, v.total FROM orders o JOIN v_order_totals v ON v.order_id=o.id
                             WHERE o.status<>'отменён' AND date(o.created_at) BETWEEN ? AND ?)
                  SELECT order_type, COUNT(*), ROUND(SUM(total),2), ROUND(AVG(total),2),
                         ROUND(100.0*SUM(total)/(SELECT SUM(total) FROM t),1)
                  FROM t GROUP BY order_type ORDER BY 3 DESC""",
    },
    "daily_revenue": {
        "title": "Динамика выручки по дням",
        "columns": ["Дата", "Заказов", "Выручка, ₽", "Отменено"],
        "sql": """SELECT date(o.created_at), SUM(o.status<>'отменён'),
                         ROUND(SUM(CASE WHEN o.status<>'отменён' THEN v.total ELSE 0 END),2),
                         SUM(o.status='отменён')
                  FROM orders o JOIN v_order_totals v ON v.order_id=o.id
                  WHERE date(o.created_at) BETWEEN ? AND ?
                  GROUP BY 1 ORDER BY 1""",
    },
    "cashier_performance": {
        "title": "Результаты работы кассиров",
        "columns": ["Сотрудник", "Ресторан", "Заказов", "Выручка, ₽", "Средний чек, ₽"],
        "roles": ("admin", "manager"),
        "sql": """SELECT e.full_name, r.name, COUNT(o.id), ROUND(SUM(v.total),2), ROUND(AVG(v.total),2)
                  FROM orders o JOIN employees e ON e.id=o.employee_id JOIN restaurants r ON r.id=e.restaurant_id
                  JOIN v_order_totals v ON v.order_id=o.id
                  WHERE o.status<>'отменён' AND date(o.created_at) BETWEEN ? AND ?
                  GROUP BY e.id ORDER BY 4 DESC""",
    },
}


@bp.get("")
@roles_required("admin", "manager", "cashier")
def list_reports():
    role = g.user["role"]
    return jsonify(reports=[{"id": k, "title": v["title"]} for k, v in REPORTS.items()
                            if role in v.get("roles", ("admin", "manager", "cashier"))])


@bp.get("/<name>")
@roles_required("admin", "manager", "cashier")
def run_report(name):
    rep = REPORTS.get(name)
    if not rep:
        return jsonify(error="Отчёт не найден"), 404
    if g.user["role"] not in rep.get("roles", ("admin", "manager", "cashier")):
        return jsonify(error="Недостаточно прав для просмотра отчёта"), 403
    try:
        p = clean(PERIOD, request.args.to_dict())
    except ValidationError as e:
        return jsonify(error="Некорректный период", fields=e.errors), 400
    d_from = p.get("date_from") or "2000-01-01"
    d_to = p.get("date_to") or date.today().isoformat()
    if d_from > d_to:
        return jsonify(error="Дата начала периода позже даты окончания"), 400
    rows = [list(r) for r in query(rep["sql"], (d_from, d_to))]
    return jsonify(title=rep["title"], columns=rep["columns"], rows=rows, period=[d_from, d_to])
