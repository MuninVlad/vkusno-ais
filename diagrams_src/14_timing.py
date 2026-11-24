"""Временная диаграмма UML (timing): состояния сессии и пользователя во времени."""
import pathlib
OUT = pathlib.Path(__file__).parent.parent / "storage" / "archive" / "graphics"
W, H = 980, 420
X0, X1 = 200, 940
T = [0, 1, 2, 4, 10, 25, 26, 30]          # минуты
def x(t): return X0 + (X1 - X0) * t / 30
lines = []
def text(xx, yy, s, size=12, anchor="start", weight="normal", color="#12352a"):
    lines.append(f'<text x="{xx}" y="{yy}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{color}">{s}</text>')
lifelines = [
    ("Сессия :Session", ["нет", "гостевая", "аутентиф.", "истекла"],
     [(0, "нет"), (0.3, "гостевая"), (2, "аутентиф."), (25, "истекла"), (26, "гостевая")], 40),
    ("Пользователь", ["гость", "вводит данные", "работает", "бездействует"],
     [(0, "гость"), (1, "вводит данные"), (2, "работает"), (10, "бездействует"), (26, "гость")], 210),
]
lines.append(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" fill="white" stroke="#1f5641"/>')
text(12, 22, "sd Тайм-аут сессии", 13, weight="bold")
for name, states, changes, top in lifelines:
    h = 34
    lines.append(f'<line x1="10" y1="{top+5}" x2="{W-10}" y2="{top+5}" stroke="#1f5641"/>')
    text(16, top + 26 + h * len(states) / 2 - 10, name, 13, weight="bold")
    for i, s in enumerate(states):
        yy = top + 25 + i * h
        text(X0 - 10, yy + 4, s, 11, "end", color="#33443d")
        lines.append(f'<line x1="{X0}" y1="{yy}" x2="{X1}" y2="{yy}" stroke="#e5ebe7" stroke-dasharray="3 3"/>')
    pts = []
    for j, (t, s) in enumerate(changes):
        yy = top + 25 + states.index(s) * h
        t_end = changes[j + 1][0] if j + 1 < len(changes) else 30
        if pts:
            pts.append((x(t), pts[-1][1]))
        pts.append((x(t), yy))
        pts.append((x(t_end), yy))
    path = " ".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    lines.append(f'<polyline points="{path}" fill="none" stroke="#ee8a2b" stroke-width="3"/>')
ax = 380
lines.append(f'<line x1="{X0}" y1="{ax}" x2="{X1}" y2="{ax}" stroke="#1f5641"/>')
for t in T:
    lines.append(f'<line x1="{x(t)}" y1="{ax}" x2="{x(t)}" y2="{ax+6}" stroke="#1f5641"/>')
    text(x(t), ax + 20, f"{t}", 11, "middle")
text(X1, ax + 36, "время, мин", 11, "end", color="#5d6b64")
# ограничения
def brace(t1, t2, y, label):
    lines.append(f'<line x1="{x(t1)}" y1="{y}" x2="{x(t2)}" y2="{y}" stroke="#c8372d" marker-start="url(#a)" marker-end="url(#a)"/>')
    text((x(t1) + x(t2)) / 2, y - 6, label, 11, "middle", color="#c8372d")
brace(10, 25, 196, "{ бездействие ≤ 15 мин }")
lines.append(f'<line x1="{x(2)}" y1="60" x2="{x(2)}" y2="{ax}" stroke="#2f7a5c" stroke-dasharray="4 3"/>')
text(x(2) + 4, 58, "вход: смена id сессии", 11, color="#2f7a5c")
lines.append(f'<line x1="{x(25)}" y1="60" x2="{x(25)}" y2="{ax}" stroke="#c8372d" stroke-dasharray="4 3"/>')
text(x(25) - 4, 58, "сервер удаляет сессию", 11, "end", color="#c8372d")
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="DejaVu Sans, Arial, sans-serif">'
       '<defs><marker id="a" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
       '<path d="M0,0 L10,5 L0,10 z" fill="#c8372d"/></marker></defs>' + "".join(lines) + "</svg>")
(OUT / "14_timing.svg").write_text(svg, "utf-8")
print("ok")
