// Генерация документов проекта (ГОСТ 7.32-2017 / ГОСТ 34.602-2020): node docs_src/build_docs.js
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, AlignmentType, WidthType,
  BorderStyle, ShadingType, HeadingLevel, LevelFormat, Footer, PageNumber, PageBreak,
  TabStopType, TabStopPosition, Tab,
} = require("docx");
// номера страниц заголовков (второй проход): node build_docs.js docs_src/.build/toc.json
const TOCP = process.argv[2] && fs.existsSync(process.argv[2]) ? JSON.parse(fs.readFileSync(process.argv[2], "utf8")) : {};
const HEADS = [];

const BUILD = path.join(__dirname, ".build");
const D = JSON.parse(fs.readFileSync(path.join(BUILD, "docdata.json"), "utf8"));
const OUT = path.join(__dirname, "..", "storage", "archive", "docs");
fs.mkdirSync(OUT, { recursive: true });

const FONT = "Times New Roman";
const TEXT_W = 11906 - 1701 - 850; // A4 минус поля 30 и 15 мм
const MAX_IMG_W = 600, MAX_IMG_H = 760;

// ---------------------------------------------------------------- примитивы
function run(t, o = {}) { return new TextRun({ text: t, font: FONT, size: o.size || 28, bold: o.bold, italics: o.italics }); }
function P(text, o = {}) {
  const runs = Array.isArray(text) ? text : [run(text, o)];
  return new Paragraph({
    children: runs, alignment: o.align || AlignmentType.JUSTIFIED,
    indent: o.noIndent ? undefined : { firstLine: 709 },
    spacing: { line: o.line || 360, before: o.before || 0, after: o.after || 0 }, keepNext: o.keepNext,
  });
}
function C(text, o = {}) { return P(text, { ...o, align: AlignmentType.CENTER, noIndent: true }); }
function H1(t) { HEADS.push([1, t]); return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(t, { bold: true, size: 32 })], pageBreakBefore: true }); }
function H1c(t) { HEADS.push([1, t]); return new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER, children: [run(t, { bold: true, size: 32 })], pageBreakBefore: true }); }
function H2(t) { HEADS.push([2, t]); return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [run(t, { bold: true })] }); }
function bullet(t) { return new Paragraph({ numbering: { reference: "dash", level: 0 }, children: [run(t)], spacing: { line: 360 }, alignment: AlignmentType.JUSTIFIED }); }
function numbered(t, ref) { return new Paragraph({ numbering: { reference: ref, level: 0 }, children: [run(t)], spacing: { line: 360 }, alignment: AlignmentType.JUSTIFIED }); }
let numRefCounter = 0;
const numRefs = [];
function newNumRef() { const r = "num" + (numRefCounter++); numRefs.push(r); return r; }
function list(items, ordered) { const ref = ordered ? newNumRef() : null; return items.map((t) => (ordered ? numbered(t, ref) : bullet(t))); }

const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const borders = { top: border, bottom: border, left: border, right: border };
let TABLE_FONT = 24;
function cell(t, w, head) {
  return new TableCell({
    borders, width: { size: w, type: WidthType.DXA }, margins: { top: 40, bottom: 40, left: 80, right: 80 },
    shading: head ? { fill: "E7EFEA", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: String(t ?? "").split("\n").map((line) => new Paragraph({ children: [run(line, { size: TABLE_FONT, bold: head })], spacing: { line: 240 } })),
  });
}
function table(headers, rows, ratios) {
  const total = ratios.reduce((a, b) => a + b, 0);
  const widths = ratios.map((r) => Math.floor((TEXT_W * r) / total));
  widths[widths.length - 1] += TEXT_W - widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true)) }),
           ...rows.map((r) => new TableRow({ children: r.map((v, i) => cell(v, widths[i])) }))],
  });
}

// счётчики рисунков и таблиц (свои в каждом документе)
let figN = 0, tabN = 0;
function resetCounters() { figN = 0; tabN = 0; }
function tcap(t) { tabN++; return P(`Таблица ${tabN} — ${t}`, { noIndent: true, keepNext: true, before: 120 }); }
// ГОСТ 7.32: на каждую таблицу и каждый рисунок в тексте даётся ссылка
function tbl(caption, headers, rows, ratios) {
  return [P(`Сведения приведены в таблице ${tabN + 1}.`, { keepNext: true }), tcap(caption), table(headers, rows, ratios), P("", { noIndent: true })];
}
function figure(png, caption, w, h) {
  let k = Math.min(MAX_IMG_W / w, MAX_IMG_H / h, 1);
  figN++;
  const lc = caption.charAt(0).toLowerCase() + caption.slice(1);
  return [
    P(`На рисунке ${figN} — ${/^[A-ZА-ЯЁ]{2}/.test(caption) ? caption : lc}.`, { keepNext: true }),
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(png), transformation: { width: Math.round(w * k), height: Math.round(h * k) } })] }),
    C(`Рисунок ${figN} — ${caption}`, { after: 120 }),
  ];
}
function figs(sect) { return D.figures.filter((f) => f.sect === sect).flatMap((f) => figure(f.png, f.caption, f.w, f.h)); }
function screen(name, caption) { const s = D.screens.find((x) => x.name === name); return s ? figure(s.png, caption, s.w, s.h) : []; }
function code(text) {
  return text.split("\n").map((l) => new Paragraph({ children: [new TextRun({ text: l || " ", font: "Courier New", size: 18 })], spacing: { line: 240 } }));
}

function titlePage(docTitle, subtitle) {
  return [
    C("Министерство науки и высшего образования Российской Федерации", { size: 24 }),
    C("Федеральное государственное автономное образовательное учреждение высшего образования", { size: 24 }),
    C("«Российский университет дружбы народов имени Патриса Лумумбы»", { size: 24, bold: true }),
    C("Факультет физико-математических и естественных наук", { size: 24, after: 1200 }),
    C(docTitle, { bold: true, size: 32, before: 1800 }),
    C(subtitle, { size: 28 }),
    C(`на тему «${D.system}»`, { size: 28 }),
    C(`Индивидуальная тема №${D.topic}`, { size: 28, after: 1600 }),
    P(`Выполнила: студентка группы ${D.group}`, { noIndent: true, align: AlignmentType.RIGHT, before: 1200 }),
    P(D.student, { noIndent: true, align: AlignmentType.RIGHT }),
    P("Проверил: ______________________", { noIndent: true, align: AlignmentType.RIGHT, before: 240 }),
    C("Москва — 2026", { before: 2400 }),
  ];
}

function makeDoc(children, withToc) {
  const body = withToc ? [] : children;
  return new Document({
    creator: D.student, title: D.system,
    styles: {
      default: { document: { run: { font: FONT, size: 28 } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: 32, bold: true }, paragraph: { spacing: { before: 240, after: 240 }, keepNext: true, outlineLevel: 0, indent: { firstLine: 709 } } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: 28, bold: true }, paragraph: { spacing: { before: 240, after: 120 }, keepNext: true, outlineLevel: 1, indent: { firstLine: 709 } } },
      ],
    },
    numbering: { config: [
      { reference: "dash", levels: [{ level: 0, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 1069, hanging: 360 } } } }] },
      ...numRefs.map((r) => ({ reference: r, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1)", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 1069, hanging: 360 } } } }] })),
    ] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1701, right: 850 } }, titlePage: true },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 24 })] })] }) },
      children,
    }],
  });
}
// статическое содержание с номерами страниц (заполняется по результатам первого прохода)
function tocLines(heads) {
  return [new Paragraph({ alignment: AlignmentType.CENTER, children: [run("СОДЕРЖАНИЕ", { bold: true, size: 32 })], pageBreakBefore: true, spacing: { after: 240 } }),
    ...heads.map(([lvl, t]) => new Paragraph({ spacing: { line: 360 }, indent: { left: lvl === 2 ? 425 : 0 },
      tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W, leader: "dot" }],
      children: [run(t), new TextRun({ font: FONT, size: 28, children: [new Tab(), String(TOCP[t] || "")] })] }))];
}
async function save(doc, name) {
  fs.writeFileSync(path.join(OUT, name), await Packer.toBuffer(doc));
  console.log("ok", name);
}

// ---------------------------------------------------------------- общие блоки
const T = D.results.tests;
const passed = T.filter((t) => t.status === "Пройден").length;
const analogsTbl = () => tbl("Сравнение систем-аналогов", ["Система", "Описание", "Достоинства", "Недостатки"], D.ANALOGS, [2, 3, 3, 3]);
const scopeTbl = () => tbl("Границы автоматизации", ["Входит в систему", "Не входит в систему"],
  Array.from({ length: Math.max(D.SCOPE_IN.length, D.SCOPE_OUT.length) }, (_, i) => [D.SCOPE_IN[i] || "", D.SCOPE_OUT[i] || ""]), [1, 1]);
const frTbl = () => tbl("Функциональные требования", ["Код", "Требование", "Роли"], D.FR, [1.2, 5, 3]);
const nfrTbl = () => tbl("Нефункциональные требования", ["Группа", "Код", "Требование"], D.NFR.map((r) => [r[0], r[1], r[2]]), [2, 1.3, 6]);
const rolesTbl = () => tbl("Роли пользователей", ["Роль", "Код", "Функции"], D.ROLES, [2, 1.3, 6]);
const permsTbl = () => tbl("Матрица прав доступа (Ч — чтение, Д — добавление, И — изменение, У — удаление)",
  ["Раздел", "Администратор", "Управляющий", "Кассир"], D.perms.map(([t, r]) => [t, ...r]), [4, 2, 2, 2]);
const toolsTbl = () => {
  TABLE_FONT = 20;
  const t = tbl("Инструментальные средства и критерии выбора", ["Назначение / выбор", "Лицензия", "Производительность", "Поддержка", "Трудоёмкость освоения"],
    D.TOOLS.map((r) => [`${r[0]}: ${r[1]}\n(альтернативы: ${r[6]})`, r[2], r[3], r[4], r[5]]), [2.4, 1.5, 3, 2.6, 2.4]);
  TABLE_FONT = 24;
  return t;
};
const threatsTbl = () => tbl("Угрозы, методы защиты и способы реализации", ["Угроза", "Метод защиты", "Способ реализации"], D.THREATS, [3, 3, 6]);
const cryptoTbl = () => tbl("Криптографические алгоритмы", ["Назначение", "Алгоритм", "Параметры", "Обоснование"], D.CRYPTO, [2.2, 2.2, 3, 4.5]);
const normTbl = () => tbl("Приведение базы данных к 3НФ", ["Форма", "Обоснование"], D.NORMALIZATION, [1.5, 8]);
const datalog = () => D.schema.flatMap((t) => tbl(`Структура таблицы «${t.name}» — ${t.title}`, ["Поле", "Тип", "Ключи и ограничения", "Описание"],
  t.cols.map((c) => [c.name, c.type, c.cons.join("; "), c.note]), [2.2, 1.5, 5, 2.5]));
const testsTbl = (group, title) => tbl(title, ["№", "Описание", "Входные данные", "Ожидаемый результат", "Фактический результат", "Статус"],
  T.filter((t) => t.group === group).map((t) => [t.id, t.title, t.input, t.expected, t.actual, t.status]), [0.9, 2.2, 2.4, 2.4, 2.8, 1.4]);
const statsTbl = () => tbl("Сводные результаты тестирования", ["Показатель", "Значение"], [
  ["Всего сценариев", String(T.length)],
  ["Функциональных / безопасности", `${T.filter((t) => t.group === "func").length} / ${T.filter((t) => t.group === "sec").length}`],
  ["Пройдено / не пройдено", `${passed} / ${T.length - passed}`],
  ["Доля успешных", `${((100 * passed) / T.length).toFixed(1)} %`],
  ["Ошибок выявлено / устранено", `${D.BUGS.length} / ${D.BUGS.length}`],
  ["Дата прогона", D.results.run_at]], [5, 4]);
const bugsTbl = () => tbl("Выявленные и устранённые ошибки", ["№", "Ошибка", "Причина", "Устранение"], D.BUGS.map((b) => b.map(String)), [0.6, 3, 3, 4]);

// ================================================================ 1. ТЗ
async function buildTZ() {
  resetCounters();
  const ch = [...titlePage("ТЕХНИЧЕСКОЕ ЗАДАНИЕ", "на создание автоматизированной информационной системы")];
  D.TZ.forEach(([title, paras], i) => {
    ch.push(i === 0 ? H1(title) : H2(title.replace(/^(\d+)\. /, "$1 ")));
    paras.forEach((p) => ch.push(P(p.replace("см. Таблицу 3", "см. таблицу 4").replace("см. Таблицу 4", "см. таблицу 5"))));
    if (title.startsWith("3.")) { D.DOMAIN.forEach((p) => ch.push(P(p))); ch.push(...scopeTbl()); }
    if (title.startsWith("4.")) {
      ch.push(P("Состав пользователей и их права приведены в таблицах ниже."));
      ch.push(...rolesTbl(), ...permsTbl(), ...frTbl(), ...nfrTbl());
      ch.push(P("Требования к защите информации:"), ...D.THREATS.slice(0, 12).map((t) => bullet(`${t[0]}: ${t[2]}`)));
    }
  });
  await save(makeDoc(ch), "01_Техническое_задание.docx");
}

// ================================================================ 2. Пояснительная записка
async function buildPZ() {
  resetCounters();
  HEADS.length = 0;
  const ch = [];
  ch.push(H1c("ВВЕДЕНИЕ"));
  ch.push(P(D.ANNOTATION), P("Актуальность работы определяется тем, что предприятия общественного питания обрабатывают большой поток заказов и персональные данные участников программ лояльности. Для них важны и скорость работы, и защищённость информации."));
  ch.push(P("Цель работы: " + D.GOAL), P("Для достижения цели решались следующие задачи:"), ...list(D.TASKS, true));
  ch.push(P("Техническое задание составлено по ГОСТ 34.602-2020 [1], пояснительная записка оформлена по ГОСТ 7.32-2017 [2]."), P("Объект исследования — процессы обслуживания гостей и управленческого учёта в сети ресторанов. Предмет — автоматизация этих процессов средствами веб-приложения с базой данных."));

  ch.push(H1("1 Анализ предметной области"), H2("1.1 Описание предметной области"), ...D.DOMAIN.map((p) => P(p)),
    P("Обработка телефонов и адресов электронной почты клиентов подпадает под требования Федерального закона № 152-ФЗ «О персональных данных» [3], поэтому такие данные должны быть защищены."));
  ch.push(H2("1.2 Анализ существующих аналогов"), P("Для сравнения выбраны три распространённые системы автоматизации общепита."), ...analogsTbl());
  ch.push(H2("1.3 Обоснование необходимости разработки"), P(D.NEED));

  ch.push(H1("2 Постановка задачи"), H2("2.1 Цель и задачи разработки"), P(D.GOAL), ...list(D.TASKS, true));
  ch.push(H2("2.2 Границы автоматизации"), ...scopeTbl());
  ch.push(H2("2.3 Пользователи системы"), ...rolesTbl(), ...permsTbl());
  ch.push(H2("2.4 Функциональные требования"), ...frTbl());
  ch.push(H2("2.5 Нефункциональные требования"), ...nfrTbl());

  ch.push(H1("3 Проектирование системы"), H2("3.1 UML-модели системы"),
    P("Система описана в нотации UML 2.5 [9] всеми 14 типами диаграмм: семью структурными (классов, объектов, компонентов, развёртывания, пакетов, композитной структуры, профилей) и семью поведенческими (вариантов использования, деятельности, последовательности, коммуникации, состояний, обзора взаимодействия, временно́й)."),
    ...figs("uml"));
  ch.push(H2("3.2 Описание бизнес-процессов"), P("Функциональная модель IDEF0 показывает процесс обслуживания гостей и его декомпозицию на четыре подпроцесса. BPMN-диаграмма описывает порядок обработки заказа по участникам. DFD показывает потоки данных между внешними сущностями, процессами системы и хранилищами."), ...figs("bp"));
  ch.push(H2("3.3 Инфологическая модель данных"), P("Выделены сущности: Ресторан, Должность, Сотрудник, Категория, Позиция меню, Клиент, Заказ, Позиция заказа, Пользователь, Роль, Сессия, Попытка входа, Журнал аудита. Связь «многие ко многим» между заказом и позицией меню реализована через сущность «Позиция заказа»."), ...figs("data"));
  ch.push(H2("3.4 Даталогическая модель"), P("Ниже описаны таблицы базы данных: поля, типы данных, ключи и ограничения целостности."), ...datalog());
  ch.push(H2("3.5 Нормализация базы данных"), P("Нормализация выполнена по классической методике [10]: последовательно проверены требования первой, второй и третьей нормальных форм."), ...normTbl());
  ch.push(H2("3.6 Архитектура системы"), ...D.ARCHITECTURE.map((p) => P(p)), ...figs("arch"));
  ch.push(H2("3.7 Проектирование интерфейса"), ...tbl("Экранные формы", ["Форма", "Адрес", "Состав"], D.SCREENS, [3, 2, 6]), ...figs("ui"));

  ch.push(H1("4 Выбор инструментальных средств"), P("Выбранные средства описаны по их официальной документации [4–6]. Критерии выбора: лицензия (свободное ПО без платежей), производительность для нагрузки сети из 10 ресторанов, наличие поддержки и сообщества, трудоёмкость освоения."), ...toolsTbl());

  ch.push(H1("5 Реализация системы"), H2("5.1 Создание и заполнение базы данных"),
    P("База данных создаётся скриптом sql/schema.sql: таблицы, первичные и внешние ключи, ограничения CHECK, UNIQUE, NOT NULL, индексы и представление v_order_totals. Программа init_db.py заполняет БД тестовыми данными: она шифрует персональные данные, хеширует пароли и выгружает скрипт sql/seed.sql."),
    ...tbl("Количество записей в таблицах", ["Таблица", "Записей"], Object.entries(D.counts).map(([k, v]) => [k, String(v)]), [3, 2]));
  ch.push(H2("5.2 Функции обработки данных"), P("Рабочий модуль на странице 2 реализует добавление, редактирование, удаление, поиск и фильтрацию для разделов: заказы, меню, категории, клиенты, сотрудники, рестораны, должности, пользователи. Интерфейс обращается к REST API (модуль app/api.py). Сервер заново проверяет каждый запрос: сессию, CSRF-токен, права роли и корректность данных."));
  ch.push(H2("5.3 Запросы и отчёты"), ...list(["Выручка по ресторанам за период (количество заказов, выручка, средний чек).", "Топ-10 позиций меню по продажам.", "Средний чек и доля выручки по типам заказа.", "Динамика выручки по дням с числом отменённых заказов.", "Результаты работы кассиров (для управляющего и администратора)."], true));
  ch.push(H2("5.4 Разграничение доступа и защита информации"), P("Меры защиты выбраны по рекомендациям OWASP [7]: хранение паролей, управление сессиями, защита от CSRF и XSS. Режим шифрования GCM соответствует NIST SP 800-38D [8]."), ...threatsTbl(),
    P("Хеширование и шифрование выполняют разные задачи. Хеширование необратимо, поэтому применяется к данным, которые нужно только проверять: паролям, идентификаторам сессий, контрольным суммам резервных копий. Шифрование обратимо при наличии ключа, поэтому применяется к данным, которые нужно восстановить и показать: телефонам и e-mail."),
    ...cryptoTbl(), ...D.KEY_SCHEME.map((p) => P(p)), ...figs("sec").slice(0, 2));
  ch.push(H2("5.5 Обработка ошибок и валидация"), P("Данные проверяются дважды. На клиенте используются атрибуты HTML5 и функции main.js и module.js. На сервере работает модуль app/validation.py: типы, диапазоны, длины, форматы телефона, e-mail и дат, запрет символов < >. Нарушения ограничений БД перехватываются, и пользователь получает понятное сообщение. Отладочный режим выключен: трассировки записываются только в журнал instance/server.log."));
  ch.push(H2("5.6 Резервное копирование"), ...D.BACKUP.map((p) => P(p)), ...figs("sec").slice(2));

  ch.push(H1("6 Тестирование"), H2("6.1 План тестирования"),
    P("Тестирование выполнено автоматизированно (pytest, файл tests/test_app.py) на отдельной временной БД, а также в браузере Chromium (Playwright, файл tests/screenshots.py) на ширинах 1366 и 320 px. Проверялись все функции, граничные и некорректные данные, разграничение доступа и требования безопасности."));
  ch.push(H2("6.2 Функциональное тестирование"), ...testsTbl("func", "Функциональные тесты"));
  ch.push(H2("6.3 Тестирование защищённости"), ...testsTbl("sec", "Тесты защищённости"));
  ch.push(H2("6.4 Результаты тестирования"), ...statsTbl(), ...bugsTbl());

  ch.push(H1c("ЗАКЛЮЧЕНИЕ"),
    P("В ходе работы разработана автоматизированная информационная система учёта заказов сети ресторанов «Вкусно и быстро» в виде трёхстраничного веб-сайта с рабочим модулем для работы с базой данных."),
    P("Решены все поставленные задачи: проанализирована предметная область и аналоги; сформулированы требования; спроектированы БД в 3НФ (13 таблиц) и трёхзвенная архитектура; построены 14 UML-диаграмм, а также модели IDEF0, BPMN и DFD; реализованы операции с данными, поиск, фильтрация и 5 отчётов."),
    P(`Реализованы меры защиты: хеширование паролей PBKDF2 (${D.security.iters.toLocaleString("ru-RU")} итераций), шифрование персональных данных AES-256-GCM, HTTPS с TLS 1.2+, серверные сессии с защитой от фиксации и тайм-аутом ${D.security.idle} мин, CSRF-токены, CSP, блокировка подбора пароля, защищённый файловый архив и резервное копирование с контролем целостности.`),
    P(`Проведено ${T.length} тестовых сценариев, все пройдены. Выявленные при разработке ошибки (${D.BUGS.length}) устранены. Направления развития: интеграция с кассовым оборудованием, складской учёт, мобильное приложение для гостей, переход на PostgreSQL при росте сети.`));

  ch.push(H1c("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"), ...list([
    "ГОСТ 34.602-2020. Информационные технологии. Комплекс стандартов на автоматизированные системы. Техническое задание на создание автоматизированной системы. — М.: Стандартинформ, 2020.",
    "ГОСТ 7.32-2017. Отчёт о научно-исследовательской работе. Структура и правила оформления. — М.: Стандартинформ, 2017.",
    "Федеральный закон от 27.07.2006 № 152-ФЗ «О персональных данных».",
    "Документация Flask 3.x. — URL: https://flask.palletsprojects.com/",
    "Документация SQLite. — URL: https://www.sqlite.org/docs.html",
    "Документация библиотеки cryptography. — URL: https://cryptography.io/",
    "OWASP Cheat Sheet Series: Password Storage, Session Management, CSRF Prevention, XSS Prevention. — URL: https://cheatsheetseries.owasp.org/",
    "NIST SP 800-38D. Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC. — 2007.",
    "OMG Unified Modeling Language (UML) Specification, Version 2.5.1. — 2017.",
    "Коннолли Т., Бегг К. Базы данных. Проектирование, реализация и сопровождение. — М.: Вильямс, 2017.",
  ], true));
  ch.push(H1c("ПРИЛОЖЕНИЕ А. Скрипт создания базы данных"), ...code(D.schema_sql));
  const heads = HEADS.slice();
  fs.writeFileSync(path.join(BUILD, "pz_heads.json"), JSON.stringify(heads));
  await save(makeDoc([...titlePage("ПОЯСНИТЕЛЬНАЯ ЗАПИСКА", "к индивидуальной работе"), ...tocLines(heads), ...ch]), "02_Пояснительная_записка.docx");
}

// ================================================================ 3. Руководство пользователя
async function buildUser() {
  resetCounters();
  const ch = [...titlePage("РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ", "автоматизированной информационной системы")];
  ch.push(H1("1 Назначение системы"), P(D.ANNOTATION), ...rolesTbl());
  ch.push(H1("2 Начало работы"), P("Откройте в браузере (Chrome, Firefox, Edge) адрес, который сообщил администратор, например https://localhost:8443. Используется учебный самоподписанный сертификат, поэтому при первом входе браузер покажет предупреждение. Нажмите «Дополнительно» → «Перейти на сайт»."),
    ...screen("01_index_guest", "Страница 1 — вход в систему"),
    P("Логин и пароль выдаёт администратор системы. Введите их и нажмите «Войти». Логин: 3–32 символа (латиница, цифры, _ . -). Если данные неверны, появится сообщение об ошибке. После 5 неудачных попыток подряд вход блокируется на 5 минут."),
    ...screen("09_login_error", "Сообщение о неверных данных"),
    P("После входа в меню появляются ссылки «2. Описание системы» и «3. Файловый архив», а также кнопка «Выход». Без активности сессия завершается через 15 минут, оставшееся время показано внизу страницы."),
    ...screen("02_index_auth", "Страница 1 после входа"));
  ch.push(H1("3 Страница 2 «Описание системы»"), P("В начале страницы находится оглавление: нажмите на пункт, чтобы перейти к разделу. Рисунки открываются в полном размере по щелчку."), ...screen("03_system_top", "Страница 2 — оглавление"));
  ch.push(H1("4 Работа с данными (рабочий модуль)"), P("Рабочий модуль находится в конце страницы 2 (пункт оглавления «Рабочий модуль АИС»). Набор вкладок зависит от роли: кассир видит заказы, меню, категории, клиентов, рестораны и отчёты; управляющий дополнительно видит сотрудников и должности; администратор — все разделы, включая пользователей."),
    H2("4.1 Поиск и фильтрация"), P("Введите текст в поле «Поиск» и/или выберите значения фильтров, затем нажмите «Найти». Кнопка «Сбросить» очищает условия. Клиента можно найти по точному номеру телефона в любом формате, например 8 916 555-12-34."),
    ...screen("04_module_orders", "Вкладка «Заказы»"),
    H2("4.2 Оформление заказа"), ...list(["Нажмите «Новый заказ».", "Выберите ресторан. В списке «Кассир» останутся сотрудники только этого ресторана.", "При необходимости выберите клиента программы лояльности.", "Укажите тип заказа и способ оплаты. Новый заказ всегда получает статус «новый».", "Добавьте позиции меню кнопкой «+ Добавить позицию» и укажите количество (1–50). Итоговая сумма считается автоматически.", "Нажмите «Сохранить»."], true),
    ...screen("05_module_order_form", "Форма нового заказа"),
    H2("4.3 Изменение и удаление"), P("Статус заказа меняется по шагам: новый → готовится → готов → выдан; отменить можно новый или готовящийся заказ. Состав меняется только у заказа в статусе «новый». Выданный и отменённый заказы не редактируются. При выдаче заказа клиенту автоматически начисляются бонусы — 5 % суммы."), P("Кнопка «Изменить» открывает форму записи. «Состав» показывает позиции заказа. «Удалить» удаляет запись после подтверждения (заказы удаляют управляющий и администратор). Запись, на которую ссылаются другие данные (например, блюдо из выданных заказов), удалить нельзя. Вместо удаления снимите отметку «В продаже»."),
    H2("4.4 Проверка вводимых данных"), P("Обязательные поля отмечены звёздочкой. При ошибке поле подсвечивается красным, а под ним появляется пояснение."), ...screen("10_module_validation", "Сообщения об ошибках ввода"),
    H2("4.5 Отчёты"), P("На вкладке «Отчёты» выберите отчёт и период, затем нажмите «Сформировать». Кнопка «Печать» выводит отчёт на принтер."), ...screen("06_module_reports", "Отчёт «Выручка по ресторанам»"));
  ch.push(H1("5 Страница 3 «Файловый архив»"), P("Файлы сгруппированы по разделам. Для каждого файла указаны имя, описание, формат, размер и дата изменения. «Открыть» показывает файл в браузере, «Скачать» сохраняет его на компьютер. Администратор может загрузить в архив PNG, JPEG или PDF размером до 5 МБ."), ...screen("07_archive", "Страница 3 — файловый архив"));
  ch.push(H1("6 Работа на мобильных устройствах"), P("Сайт адаптирован для экранов шириной от 320 px. Меню открывается кнопкой ☰ в правом верхнем углу, широкие таблицы прокручиваются по горизонтали."), ...screen("08_mobile_320", "Мобильная версия (320 px)"));
  ch.push(H1("7 Возможные сообщения"), ...tbl("Сообщения системы", ["Сообщение", "Причина и действия"], [
    ["Неверный логин или пароль", "Проверьте раскладку и Caps Lock."], ["Вход временно заблокирован", "5 неудачных попыток. Подождите 5 минут или обратитесь к администратору."],
    ["Сессия завершена по тайм-ауту", "Не было активности 15 минут. Войдите снова."], ["Недостаточно прав", "Операция недоступна для вашей роли."],
    ["Доступ запрещён (403)", "Устарел защитный токен формы. Обновите страницу."], ["Запись с таким значением уже существует", "Например, клиент с этим телефоном уже зарегистрирован."]], [4, 6]));
  await save(makeDoc(ch), "03_Руководство_пользователя.docx");
}

// ================================================================ 4. Руководство администратора
async function buildAdmin() {
  resetCounters();
  const ch = [...titlePage("РУКОВОДСТВО АДМИНИСТРАТОРА", "автоматизированной информационной системы")];
  ch.push(H1("1 Требования к окружению"), ...list(["Сервер: Linux или Windows, 1 ГБ ОЗУ, 200 МБ на диске.", "Python 3.10 или новее.", "Пакеты: Flask ≥ 3.0, cryptography ≥ 42 (файл requirements.txt).", "Клиенты: современный браузер (Chrome, Firefox, Edge)."], false));
  ch.push(H1("2 Установка"), ...list(["Скачайте исходный код из репозитория GitHub (кнопка Code → Download ZIP) и распакуйте, например, в /opt/vkusno_ais.", "Установите зависимости: pip install -r requirements.txt.", "Создайте базу данных: python init_db.py. Будут созданы instance/vkusno.db, ключ шифрования instance/data.key и файл паролей instance/accounts.json.", "Запустите сервер: python run.py. При первом запуске создаётся сертификат certs/server.crt.", "Откройте https://localhost:8443 и войдите под учётной записью администратора (пароль — в instance/accounts.json)."], true));
  ch.push(H1("3 Настройка"), P("Параметры находятся в файле app/config.py."), ...tbl("Основные параметры", ["Параметр", "Значение", "Назначение"], [
    ["PBKDF2_ITERATIONS", String(D.security.iters), "Число итераций хеширования паролей"], ["MAX_FAILED_ATTEMPTS", String(D.security.attempts), "Неудачных попыток до блокировки"],
    ["LOCKOUT_SEC", `${D.security.lock * 60}`, "Длительность блокировки входа, с"], ["SESSION_IDLE_TIMEOUT", `${D.security.idle * 60}`, "Тайм-аут бездействия, с"],
    ["SESSION_ABSOLUTE_TIMEOUT", "28800", "Максимальная длительность сессии, с"], ["MAX_UPLOAD_BYTES", "5 МБ", "Лимит загружаемого файла"],
    ["VB_MASTER_KEY (окружение)", "base64, 32 байта", "Мастер-ключ шифрования вместо файла data.key"], ["VB_DEBUG (окружение)", "0", "Отладочный режим (в работе — только 0)"]], [3.5, 2.5, 5]),
    P("Порт и адрес задаются при запуске: python run.py --host 0.0.0.0 --port 8443. Для рабочей эксплуатации рекомендуется поставить сервер за обратным прокси (nginx) с сертификатом от доверенного центра."));
  ch.push(H1("4 Управление пользователями"), P("Вкладка «Пользователи» рабочего модуля доступна только администратору. Здесь можно создать учётную запись (логин, роль, связанный сотрудник, пароль по политике сложности), изменить роль, сбросить пароль и заблокировать учётную запись. При блокировке или смене пароля все сессии пользователя сразу завершаются. Удалить собственную учётную запись нельзя."),
    P("Пароли учётных записей тестовой базы данных не хранятся в исходном коде: при первой установке они генерируются случайным образом (12 символов, строчные и заглавные буквы, цифры, спецсимвол) и записываются в файл instance/accounts.json с правами 0600. Этот файл не публикуется в репозитории; администратор передаёт пароли пользователям лично и после первого входа рекомендует их сменить."),
    ...tbl("Учётные записи тестовой базы данных", ["Логин", "Роль"], [
      ["admin, admin.it", "Администратор"], ["manager, manager.arbat, manager.nevsky", "Управляющий (Тверская, Арбат, Невский)"],
      ["cashier, kassa.arbat, kassa.taganka, kassa.nevsky, kassa.kazan, kassa.ekb", "Кассир (Тверская, Арбат, Таганка, Невский, Баумана, Плотинка)"]], [5, 5]));
  ch.push(H1("5 Ключи и сертификаты"), ...D.KEY_SCHEME.map((p) => P(p)),
    P("Перевыпуск сертификата: python gen_cert.py. Файлы instance/data.key и certs/server.key должны иметь права 0600 и не должны попадать в общий доступ. Потеря data.key означает потерю зашифрованных телефонов и e-mail."));
  ch.push(H1("6 Резервное копирование и восстановление"), ...D.BACKUP.map((p) => P(p)), ...figs("sec").slice(2),
    P("Пример задания cron: 0 3 * * * cd /opt/vkusno_ais && python3 backup.py"), P("Восстановление: остановите сервер, выполните python backup.py --restore backups/vkusno_ГГГГММДД_ЧЧММСС.zip и запустите сервер. Перед восстановлением текущая БД сохраняется как vkusno.db.before_restore."));
  ch.push(H1("7 Журналы и контроль"), P("Таблица audit_log хранит входы, выходы, изменения данных, отказы в доступе, CSRF-отказы и операции с файлами. Файл instance/server.log хранит технические ошибки сервера. Таблица login_attempts используется для блокировки подбора паролей."));
  ch.push(H1("8 Проверка работоспособности"), P("Запуск автотестов: python -m pytest -q tests. Тесты используют временную БД и не изменяют рабочие данные. Проверка интерфейса в браузере (при запущенном сервере): python tests/screenshots.py."));
  await save(makeDoc(ch), "04_Руководство_администратора.docx");
}

// ================================================================ 5. Описание БД и модулей
async function buildDB() {
  resetCounters();
  const ch = [...titlePage("ОПИСАНИЕ СТРУКТУРЫ БАЗЫ ДАННЫХ И ПРОГРАММНЫХ МОДУЛЕЙ", "автоматизированной информационной системы")];
  ch.push(H1("1 Структура базы данных"), P("СУБД — SQLite 3. База содержит 13 таблиц и представление v_order_totals (сумма и количество позиций заказа). Ограничения целостности: первичные и внешние ключи (ON DELETE RESTRICT / CASCADE / SET NULL), UNIQUE, NOT NULL, CHECK."), ...figs("data"), ...datalog(), ...normTbl());
  ch.push(H1("2 Программные модули"), ...tbl("Модули сервера", ["Модуль", "Назначение", "Основные функции"], [
    ["app/__init__.py", "Фабрика приложения, страницы", "create_app, index, login, logout, system, archive, schema_info"],
    ["app/config.py", "Конфигурация", "Пути, параметры безопасности, данные шапки"],
    ["app/db.py", "Доступ к данным", "get_db, query, execute, audit"],
    ["app/security.py", "Безопасность", "load_session, check_csrf, authenticate, login_user, logout_user, login_required, roles_required, security_headers"],
    ["app/crypto.py", "Криптография", "hash_password, verify_password, encrypt_field, decrypt_field, blind_index, new_token"],
    ["app/validation.py", "Валидация", "clean, normalize_phone"],
    ["app/api.py", "REST API", "meta, list_rows, create_row, update_row, delete_row, orders_list, order_create, order_update, order_delete"],
    ["app/reports.py", "Отчёты", "list_reports, run_report"],
    ["app/archive.py", "Файловый архив", "entries, get_file, upload, delete_upload"],
    ["run.py / init_db.py / gen_cert.py / backup.py", "Служебные программы", "Запуск HTTPS, создание БД, сертификат, резервные копии"]], [3, 2.5, 6]),
    ...tbl("Клиентские модули", ["Файл", "Назначение"], [["static/js/main.js", "Меню, клиентская валидация форм, таймер сессии"], ["static/js/module.js", "Рабочий модуль: вкладки, таблицы, формы, отчёты"], ["static/css/style.css", "Стили и адаптивная вёрстка"], ["templates/*.html", "Шаблоны Jinja2 трёх страниц и страницы ошибки"]], [3, 7]),
    ...tbl("Точки REST API", ["Метод и адрес", "Назначение"], [["GET /api/meta", "Разделы и права текущей роли, справочники"], ["GET /api/<раздел>?q=&фильтры", "Поиск и фильтрация"], ["POST /api/<раздел>", "Добавление"], ["PUT /api/<раздел>/<id>", "Изменение"], ["DELETE /api/<раздел>/<id>", "Удаление"], ["GET/POST/PUT/DELETE /api/orders…", "Заказы с позициями"], ["GET /api/reports/<отчёт>?date_from=&date_to=", "Отчёты"], ["GET /files/<id>[?download=1]", "Выдача файла архива"]], [4, 6]),
    ...figs("arch"));
  await save(makeDoc(ch), "05_Описание_БД_и_модулей.docx");
}

(async () => { await buildTZ(); await buildPZ(); await buildUser(); await buildAdmin(); await buildDB(); })();
