"""IDEF0-диаграммы (A-0 и A0) — генерация SVG по правилам нотации:
входы слева, выходы справа, управление сверху, механизмы снизу."""
import pathlib
OUT = pathlib.Path(__file__).parent.parent / "storage" / "archive" / "graphics"
INK, ORANGE, FILL = "#12352a", "#c96d14", "#fff4e3"

class S:
    def __init__(s, w, h): s.w, s.h, s.el = w, h, []
    def box(s, x, y, w, h, title, num):
        s.el.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{FILL}" stroke="{INK}" stroke-width="1.6"/>')
        lines = title.split("\n")
        for i, line in enumerate(lines):
            s.text(x + w / 2, y + h / 2 - (len(lines) - 1) * 8 + i * 16, line, 13, "middle", "bold")
        s.text(x + w - 6, y + h - 6, num, 11, "end")
    def text(s, x, y, t, size=12, anchor="start", weight="normal", color=INK):
        s.el.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}">{t}</text>')
    def arrow(s, pts, label=None, lx=None, ly=None, anchor="start", color=INK, dash=False):
        d = " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)
        s.el.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.4" marker-end="url(#ar)"'
                    + (' stroke-dasharray="5 4"' if dash else "") + "/>")
        if label:
            for i, line in enumerate(label.split("\n")):
                s.text(lx, ly + i * 14, line, 11, anchor, color=color)
    def frame(s, node, title, num):
        s.el.append(f'<rect x="1" y="1" width="{s.w-2}" height="{s.h-2}" fill="white" stroke="{INK}"/>')
        y = s.h - 30
        s.el.append(f'<line x1="1" y1="{y}" x2="{s.w-1}" y2="{y}" stroke="{INK}"/>')
        s.el.append(f'<line x1="140" y1="{y}" x2="140" y2="{s.h-1}" stroke="{INK}"/>')
        s.el.append(f'<line x1="{s.w-120}" y1="{y}" x2="{s.w-120}" y2="{s.h-1}" stroke="{INK}"/>')
        s.text(10, y + 20, "УЗЕЛ: " + node, 11, weight="bold")
        s.text(150, y + 20, "НАЗВАНИЕ: " + title, 11, weight="bold")
        s.text(s.w - 110, y + 20, "НОМЕР: " + num, 11, weight="bold")
    def save(s, name):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{s.w}" height="{s.h}" viewBox="0 0 {s.w} {s.h}" font-family="DejaVu Sans, Arial, sans-serif">'
               f'<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{INK}"/></marker></defs>'
               + "".join(s.el) + "</svg>")
        (OUT / name).write_text(svg, "utf-8")

# ---------------- A-0
d = S(900, 520)
d.frame("A-0", "Обслуживать гостей ресторана", "1")
bx, by, bw, bh = 340, 180, 240, 140
d.box(bx, by, bw, bh, "Обслуживать гостей\nресторана", "A0")
d.arrow([(40, 220), (bx, 220)], "Заказ гостя", 40, 212)
d.arrow([(40, 280), (bx, 280)], "Продукты и\nполуфабрикаты", 40, 262)
d.arrow([(bx + bw, 210), (860, 210)], "Выданный заказ", 860, 202, "end")
d.arrow([(bx + bw, 250), (860, 250)], "Чек и данные о продаже", 860, 242, "end")
d.arrow([(bx + bw, 290), (860, 290)], "Отчёты о продажах", 860, 282, "end")
d.arrow([(400, 50), (400, by)], "Меню, цены,\nстандарты обслуживания", 408, 62)
d.arrow([(520, 50), (520, by)], "152-ФЗ, политика\nбезопасности", 528, 62)
d.arrow([(400, 460), (400, by + bh)], "Персонал\nресторана", 408, 430)
d.arrow([(520, 460), (520, by + bh)], "АИС «Вкусно\nи быстро»", 528, 430)
d.text(20, 30, "Цель: описать обслуживание гостей для автоматизации учёта.   Точка зрения: управляющий сетью.", 11, color="#5d6b64")
d.save("15_idef0_context.svg")

# ---------------- A0 (декомпозиция)
d = S(1180, 700)
d.frame("A0", "Обслуживать гостей ресторана", "2")
B = {1: (150, 120), 2: (420, 250), 3: (690, 380), 4: (900, 120)}
W, H = 200, 100
names = {1: "Принять и\nоформить заказ", 2: "Приготовить\nзаказ", 3: "Выдать заказ,\nначислить бонусы", 4: "Анализировать\nпродажи"}
for k, (x, y) in B.items():
    d.box(x, y, W, H, names[k], f"A{k}")
# входы / выходы
d.arrow([(20, B[1][1] + 50), (B[1][0], B[1][1] + 50)], "Заказ гостя", 22, B[1][1] + 42)
d.arrow([(20, B[2][1] + 70), (B[2][0], B[2][1] + 70)], "Продукты", 22, B[2][1] + 62)
d.arrow([(B[1][0] + W, B[1][1] + 70), (B[2][0] - 40, B[1][1] + 70), (B[2][0] - 40, B[2][1] + 35), (B[2][0], B[2][1] + 35)],
        "Заказ «новый»", B[1][0] + W + 8, B[1][1] + 62)
d.arrow([(B[2][0] + W, B[2][1] + 50), (B[3][0] - 40, B[2][1] + 50), (B[3][0] - 40, B[3][1] + 40), (B[3][0], B[3][1] + 40)],
        "Заказ «готов»", B[2][0] + W + 8, B[2][1] + 42)
d.arrow([(B[3][0] + W, B[3][1] + 50), (1160, B[3][1] + 50)], "Выданный заказ", 1160, B[3][1] + 42, "end")
d.arrow([(B[1][0] + W, B[1][1] + 30), (B[4][0], B[1][1] + 30)], "Данные о продаже (чек)", B[1][0] + W + 140, B[1][1] + 22)
d.arrow([(B[3][0] + W, B[3][1] + 20), (B[4][0] + 60, B[3][1] + 20), (B[4][0] + 60, B[4][1] + H)], "Статус «выдан»", B[3][0] + W + 6, B[3][1] + 12)
d.arrow([(B[4][0] + W, B[4][1] + 50), (1160, B[4][1] + 50)], "Отчёты", 1160, B[4][1] + 42, "end")
# обратная связь (управление от A4 к A1)
d.arrow([(B[4][0] + 100, B[4][1]), (B[4][0] + 100, 70), (B[1][0] + 150, 70), (B[1][0] + 150, B[1][1])],
        "Изменения меню и цен (обратная связь)", B[1][0] + 300, 64, color=ORANGE, dash=True)
# управление
d.arrow([(B[1][0] + 60, 40), (B[1][0] + 60, B[1][1])], "Меню и цены", B[1][0] + 66, 52)
d.arrow([(B[2][0] + 100, 40), (B[2][0] + 100, B[2][1])], "Технологические карты", B[2][0] + 106, 52)
d.arrow([(B[3][0] + 100, 40), (B[3][0] + 100, B[3][1])], "Правила программы\nлояльности", B[3][0] + 106, 52)
d.arrow([(B[4][0] + 160, 40), (B[4][0] + 160, B[4][1])], "Политика\nбезопасности", B[4][0] + 166, 52)
# механизмы
mech_y = 640
d.arrow([(B[1][0] + 100, mech_y), (B[1][0] + 100, B[1][1] + H)], "Кассир + АИС", B[1][0] + 106, mech_y - 8)
d.arrow([(B[2][0] + 100, mech_y), (B[2][0] + 100, B[2][1] + H)], "Повар", B[2][0] + 106, mech_y - 8)
d.arrow([(B[3][0] + 100, mech_y), (B[3][0] + 100, B[3][1] + H)], "Кассир + АИС", B[3][0] + 106, mech_y - 8)
d.arrow([(B[4][0] + 140, mech_y), (B[4][0] + 140, B[4][1] + H)], "Управляющий\n+ АИС (отчёты)", B[4][0] + 146, mech_y - 22)
d.save("16_idef0_a0.svg")
print("ok")
