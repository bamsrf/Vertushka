# -*- coding: utf-8 -*-
"""Vertushka mascot — AE/Lottie animation brief generator."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, ListFlowable, ListItem,
)
from reportlab.lib.styles import ParagraphStyle

# ---- Fonts (Arial has Cyrillic) ----
AF = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("AR", AF + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("AR-B", AF + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("AR-I", AF + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("AR-BI", AF + "Arial Bold Italic.ttf"))
pdfmetrics.registerFont(TTFont("MONO", AF + "Courier New.ttf"))
pdfmetrics.registerFont(TTFont("MONO-B", AF + "Courier New Bold.ttf"))
pdfmetrics.registerFont(TTFont("SYM", AF + "Arial Unicode.ttf"))  # check/cross/box glyphs
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("AR", normal="AR", bold="AR-B", italic="AR-I", boldItalic="AR-BI")

# ---- Palette (mascot: deep blue + cream) ----
BLUE   = colors.HexColor("#1F3BE0")
BLUE_D = colors.HexColor("#15238F")
INK    = colors.HexColor("#1A2138")
CREAM  = colors.HexColor("#FAF3E0")
CREAMD = colors.HexColor("#F0E6C8")
GREY   = colors.HexColor("#6B7280")
WARN_BG= colors.HexColor("#FFF4E5")
WARN_BR= colors.HexColor("#E08A1F")
LINE   = colors.HexColor("#D9DEEA")

# ---- Styles ----
def S(name, **kw):
    base = dict(fontName="AR", fontSize=10.5, leading=15, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)

st_title   = S("title", fontName="AR-B", fontSize=27, leading=31, textColor=BLUE_D)
st_sub     = S("sub", fontSize=12, leading=17, textColor=GREY)
st_kicker  = S("kicker", fontName="AR-B", fontSize=9, leading=12, textColor=BLUE,
               spaceAfter=2)
st_h1      = S("h1", fontName="AR-B", fontSize=15, leading=19, textColor=BLUE_D,
               spaceBefore=4, spaceAfter=6)
st_h2      = S("h2", fontName="AR-B", fontSize=11.5, leading=15, textColor=INK,
               spaceBefore=8, spaceAfter=3)
st_body    = S("body", spaceAfter=5)
st_bodyc   = S("bodyc", spaceAfter=2)
st_li      = S("li", leading=14.5, spaceAfter=3)
st_note    = S("note", fontSize=9.5, leading=13.5, textColor=GREY)
st_warn    = S("warn", fontSize=10.5, leading=15, textColor=colors.HexColor("#7A4A12"))
st_warnh   = S("warnh", fontName="AR-B", fontSize=12.5, leading=16,
               textColor=WARN_BR, spaceAfter=4)
st_mono    = S("mono", fontName="MONO", fontSize=9.5, leading=13,
               textColor=BLUE_D)
st_card_t  = S("card_t", fontName="AR-B", fontSize=12, leading=15, textColor="white")
st_card_b  = S("card_b", fontSize=10, leading=14, textColor=CREAM)
st_diag    = S("diag", fontName="AR-B", fontSize=10, leading=13, textColor="white",
               alignment=TA_CENTER)
st_diags   = S("diags", fontSize=8.5, leading=11, textColor=CREAM, alignment=TA_CENTER)
st_chk     = S("chk", fontSize=11, leading=20, textColor=INK)
st_foot    = S("foot", fontSize=8, leading=10, textColor=GREY)

def bullets(items, style=st_li, bullet="–"):
    return ListFlowable(
        [ListItem(Paragraph(t, style), leftIndent=10, value=bullet) for t in items],
        bulletType="bullet", start=bullet, leftIndent=12, bulletFontName="AR",
        bulletFontSize=10, spaceBefore=0,
    )

def kicker_h1(kick, title):
    return KeepTogether([Paragraph(kick, st_kicker), Paragraph(title, st_h1),
                         HRFlowable(width="100%", thickness=1.2, color=LINE,
                                    spaceBefore=2, spaceAfter=7)])

# ---- Page furniture ----
def header_footer(canvas, doc):
    canvas.saveState()
    # top accent bar
    canvas.setFillColor(BLUE)
    canvas.rect(0, A4[1]-6*mm, A4[0], 6*mm, fill=1, stroke=0)
    # footer
    canvas.setFillColor(GREY); canvas.setFont("AR", 8)
    canvas.drawString(18*mm, 12*mm, "Vertushka — Animation Brief · Lottie / Bodymovin")
    canvas.drawRightString(A4[0]-18*mm, 12*mm, "стр. %d" % doc.page)
    canvas.setStrokeColor(LINE); canvas.setLineWidth(0.5)
    canvas.line(18*mm, 15*mm, A4[0]-18*mm, 15*mm)
    canvas.restoreState()

doc = BaseDocTemplate(
    "Vertushka_AE_Lottie_Brief.pdf", pagesize=A4,
    leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=20*mm,
    title="Vertushka — Бриф на анимацию маскота (AE → Lottie)",
    author="Vertushka",
)
frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=header_footer)])

E = []  # story

# ================= COVER =================
E.append(Spacer(1, 6*mm))
E.append(Paragraph("ТЕХНИЧЕСКИЙ БРИФ · MOTION DESIGN", st_kicker))
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Анимация маскота Vertushka", st_title))
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Экраны загрузки · векторный Lottie (JSON) через Bodymovin · "
                   "автозапуск + бесшовный loop", st_sub))
E.append(Spacer(1, 5*mm))

intro = ("Документ — бриф для motion-дизайнера на две зацикленные анимации маскота "
         "приложения Vertushka (коллекция виниловых пластинок, iOS + Android, "
         "React Native). Анимации неинтерактивные («плёночные»): автозапуск и "
         "бесконечный цикл, без реакции на жесты. Финальный формат доставки — "
         "<b>Lottie (JSON)</b>, экспорт плагином <b>Bodymovin</b>. Не видео, не GIF — "
         "строго вектор.")
E.append(Paragraph(intro, st_body))
E.append(Spacer(1, 3*mm))

note = ("Дизайнер — профи в After Effects, поэтому акцент в брифе сделан на "
        "специфике <b>Lottie / Bodymovin</b>: именно несовместимые эффекты — "
        "главный источник ошибок при экспорте. Раздел совместимости выделен "
        "отдельно — прочитать до начала работы.")
tn = Table([[Paragraph(note, st_warn)]], colWidths=[doc.width])
tn.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), CREAM),
    ("BOX", (0,0), (-1,-1), 0, CREAM),
    ("LEFTPADDING", (0,0), (-1,-1), 12), ("RIGHTPADDING", (0,0), (-1,-1), 12),
    ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ("LINEBEFORE", (0,0), (0,-1), 3, BLUE),
]))
E.append(tn)
E.append(Spacer(1, 6*mm))

# Quick facts table
facts = [
    ["Платформа", "iOS + Android, React Native"],
    ["Где используется", "Экраны загрузки (loading)"],
    ["Поведение", "Автозапуск, бесконечный loop, без интерактива"],
    ["Формат сдачи", "Lottie JSON (Bodymovin) + превью для согласования"],
    ["Композиция", "Квадрат 512×512 и 1024×1024, фон прозрачный"],
    ["Стиль маскота", "Rubber-hose, плоский; синий + кремовый"],
]
tf = Table([[Paragraph("<b>"+k+"</b>", st_bodyc), Paragraph(v, st_bodyc)] for k,v in facts],
           colWidths=[42*mm, doc.width-42*mm])
tf.setStyle(TableStyle([
    ("FONTNAME", (0,0), (-1,-1), "AR"),
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.white, CREAM]),
    ("LINEBELOW", (0,0), (-1,-2), 0.5, LINE),
    ("LEFTPADDING", (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ("BOX", (0,0), (-1,-1), 0.8, LINE),
]))
E.append(tf)

# ================= 1. WHAT TO ANIMATE =================
E.append(PageBreak())
E.append(kicker_h1("РАЗДЕЛ 1", "Что нужно анимировать"))

def anim_card(num, title, desc, specs):
    head = Table([[Paragraph("0%d" % num, S("n", fontName="AR-B", fontSize=20,
                  textColor="white")), Paragraph(title, st_card_t)]],
                 colWidths=[16*mm, None])
    head.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),BLUE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),8),
        ("BOTTOMPADDING",(0,0),(-1,-1),8),
    ]))
    body_rows = [[Paragraph(desc, st_body)]]
    for s in specs:
        body_rows.append([Paragraph(s, st_li)])
    bt = Table(body_rows, colWidths=[doc.width])
    bt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),CREAM),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
        ("TOPPADDING",(0,0),(0,0),10),("BOTTOMPADDING",(0,-1),(-1,-1),10),
        ("TOPPADDING",(0,1),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-2),1),
    ]))
    return KeepTogether([head, bt, Spacer(1, 5*mm)])

E.append(anim_card(1, "Вращение персонажа",
    "Весь маскот вращается вокруг своей вертикальной оси (или вокруг центра — "
    "финальный вариант уточняет дизайнер с заказчиком). Зацикленно.",
    ["Anchor point — по центру композиции.",
     "Easing: linear (без ease), чтобы стык цикла был бесшовным.",
     "Рекомендуемая длительность оборота: 3–5 сек (оставить настраиваемой)."]))

E.append(anim_card(2, "Вращение головы-пластинки",
    "Голова-винил раскручивается руками персонажа и крутится вокруг своего центра, "
    "как проигрываемая пластинка. Тело неподвижно. Зацикленно.",
    ["<b>Anchor point строго в геометрическом центре пластинки</b> — там, где "
     "отверстие винила. Это критично: смещённый anchor даст «болтанку».",
     "Анимируется только слой головы; тело и руки — статичны.",
     "Easing: linear. Длительность оборота 3–5 сек (настраиваемая)."]))

# Layer structure diagram
E.append(Paragraph("Структура слоёв (схема)", st_h2))
E.append(Paragraph("Голова обязана быть самостоятельным слоем, отделённым от тела — "
                   "иначе вращение головы технически невозможно.", st_body))

def dbox(title, sub, bg):
    p = [Paragraph(title, st_diag)]
    if sub: p.append(Paragraph(sub, st_diags))
    t = Table([[p]], colWidths=[58*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),bg),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("ROUNDEDCORNERS",[6,6,6,6]),
    ]))
    return t

tree = Table([
    [dbox("COMP: vertushka_loader", "512×512 / 1024×1024 · прозрачный фон", BLUE_D)],
    [Paragraph("│", S("t", fontSize=12, alignment=TA_CENTER, textColor=GREY))],
    [dbox("GROUP: mascot", "корневая группа маскота", BLUE)],
], colWidths=[doc.width])
tree.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),
    ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1)]))
E.append(tree)

children = Table([
    [dbox("LAYER: head_record", "anchor = центр пластинки (отверстие) · крутится", WARN_BR),
     dbox("LAYER: body", "торс + руки + ноги · статичен", GREY)],
], colWidths=[doc.width/2, doc.width/2])
children.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),
    ("VALIGN",(0,0),(-1,-1),"TOP"),
    ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),1)]))
E.append(Spacer(1, 2*mm))
E.append(children)
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Имена слоёв — латиницей, осмысленные. Структура групп "
                   "сохраняется при экспорте, поэтому держим её чистой.", st_note))

# ================= 2. SOURCE PREP + COMPOSITION =================
E.append(PageBreak())
E.append(kicker_h1("РАЗДЕЛ 2", "Подготовка исходника и композиция"))

E.append(Paragraph("Подготовка .ai", st_h2))
E.append(bullets([
    "Разнести .ai на отдельные группы/слои: <b>голова отдельно от тела</b>.",
    "Голова — самостоятельный слой; anchor в геометрическом центре пластинки "
    "(точка отверстия винила).",
    "Импорт в AE с сохранением слоёв (Create Composition from layers), "
    " retain layer sizes.",
    "Все элементы — векторные shape-слои. Растровых вложений быть не должно.",
]))

E.append(Paragraph("Композиция", st_h2))
E.append(bullets([
    "Форма — <b>квадрат</b>. Делать два размера: <b>512×512</b> и <b>1024×1024</b>.",
    "Фон — <b>прозрачный</b> (alpha). Никакой заливки фонового слоя.",
    "Центрировать маскот: anchor персонажа и центр головы — предсказуемые точки.",
    "Частота кадров: 30 fps (стандарт для RN-Lottie; 60 — только при явной "
    "необходимости, вес растёт).",
]))

# ================= 3. LOTTIE COMPAT — HIGHLIGHT =================
E.append(PageBreak())
E.append(Paragraph("ГЛАВНОЕ · ЧИТАТЬ ДО НАЧАЛА", st_kicker))

warn_inner = []
warn_inner.append(Paragraph("(!)  Совместимость с Lottie / Bodymovin", st_warnh))
warn_inner.append(Paragraph(
    "Lottie воспроизводит НЕ весь арсенал After Effects. Часть эффектов "
    "игнорируется или растеризуется при экспорте — анимация в Lottie-плеере "
    "будет выглядеть иначе, чем в AE. Ниже — что нельзя и что можно.", st_warn))
warn_inner.append(Spacer(1, 3*mm))

warn_inner.append(Paragraph("<font face='SYM'>✗</font>  НЕ поддерживается (избегать)", S("x", fontName="AR-B",
    fontSize=11, textColor=colors.HexColor("#B3261E"), spaceAfter=3)))
warn_inner.append(bullets([
    "Растровые блюры (Gaussian / Fast Blur по растру), тени слоёв (Drop Shadow).",
    "Многие режимы наложения (blend modes) — часть просто не парсится.",
    "Track matte с растровым источником; эффекты искажения (Turbulent Displace и т.п.).",
    "<b>Растровые .png-текстуры для шейдинга</b> — Lottie их растеризует "
    "(теряется вес и масштабируемость) либо игнорирует.",
    "Parenting к слоям с выражениями, которые Bodymovin не парсит.",
], style=st_warn))

warn_inner.append(Paragraph("<font face='SYM'>✓</font>  Поддерживается (использовать)", S("v", fontName="AR-B",
    fontSize=11, textColor=colors.HexColor("#1E7A3D"), spaceBefore=4, spaceAfter=3)))
warn_inner.append(bullets([
    "Только <b>векторные shape-слои</b>, заливки и градиенты.",
    "Анимация трансформаций: <b>rotation, position, scale, opacity</b>.",
    "Анимация параметров shape-слоёв (path, trim paths, stroke).",
    "Полутоновый / винтажный шейдинг — воспроизводить <b>векторными</b> средствами "
    "(градиенты, halftone из векторных точек), не растровой текстурой.",
], style=st_warn))

warn_inner.append(Spacer(1, 2*mm))
chk_one = Paragraph("<b>Дешёвая страховка:</b> перед полной анимацией прогнать "
    "ОДИН статичный кадр через Bodymovin и проверить рендер в Lottie-превью "
    "(lottiefiles.com/preview или приложение LottieFiles). Несовместимость "
    "ловится на одном кадре — это в разы дешевле, чем переделывать готовую сцену.",
    st_warn)
ci = Table([[chk_one]], colWidths=[doc.width-24])
ci.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.white),
    ("BOX",(0,0),(-1,-1),1,WARN_BR),("LEFTPADDING",(0,0),(-1,-1),10),
    ("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),8),
    ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
warn_inner.append(ci)

wbox = Table([[warn_inner]], colWidths=[doc.width])
wbox.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,-1),WARN_BG),("BOX",(0,0),(-1,-1),2,WARN_BR),
    ("LEFTPADDING",(0,0),(-1,-1),16),("RIGHTPADDING",(0,0),(-1,-1),16),
    ("TOPPADDING",(0,0),(-1,-1),14),("BOTTOMPADDING",(0,0),(-1,-1),14),
]))
E.append(wbox)

# ================= 4. ROTATION + LOOP =================
E.append(PageBreak())
E.append(kicker_h1("РАЗДЕЛ 3", "Вращение и бесшовный loop"))

E.append(Paragraph("Анимация вращения", st_h2))
E.append(bullets([
    "Ставить rotation <b>0° → 360°</b> — выражением <font face='MONO'>time*N</font> "
    "или двумя ключами.",
    "Easing для лоадера — <b>linear</b> (без ease in/out), иначе на стыке цикла "
    "будет рывок.",
    "Длительность одного оборота — настраиваемая. Рекомендация: <b>3–5 сек</b>.",
]))

E.append(Paragraph("Выражение (rotation), вариант со временем:", st_note))
expr = Table([[Paragraph("rotateSpeed = 90;  // град/сек → оборот за 4 сек<br/>"
                         "time * rotateSpeed;", st_mono)]], colWidths=[doc.width])
expr.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F3F5FF")),
    ("BOX",(0,0),(-1,-1),0.8,LINE),("LEFTPADDING",(0,0),(-1,-1),12),
    ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
E.append(expr)
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Если Bodymovin капризничает с выражением — заменить на 2 "
    "линейных ключа (0° на кадре 0, 360° на последнем) и зациклить композицию. "
    "Ключи парсятся всегда; сложные выражения — не всегда.", st_note))

E.append(Paragraph("Бесшовный loop", st_h2))
E.append(bullets([
    "Первый и последний кадр должны совпадать: <b>360° = 0°</b>.",
    "<b>Без дабл-кадра на стыке</b>: если последний кадр уже показывает 360° "
    "(= 0°), а следующий цикл снова рисует 0° — получится микро-заминка. "
    "Последний кадр держать на 359.x° / делать длину так, чтобы 360° приходился "
    "на «нулевой кадр следующего цикла».",
    "Проверка: запустить loop в Lottie-превью на 30+ сек, смотреть на стык.",
]))

# ================= 5. BODYMOVIN EXPORT =================
E.append(Paragraph("Настройки экспорта Bodymovin", st_h2))
E.append(bullets([
    "Glyphs / Fonts — <b>выключить</b> (текста в анимациях нет).",
    "Убрать лишнее: Demo, Standalone — не нужны для RN.",
    "Включить только то, что нужно для отдачи JSON: чистый .json на каждую "
    "анимацию.",
    "Не включать «Assets → Include in json» с растром — ассетов-картинок быть "
    "не должно (всё вектор).",
    "Проверить, что в экспортированном JSON нет блока <font face='MONO'>"
    "assets</font> с .png. Если есть — где-то остался растровый слой.",
]))

# ================= 6. AE MCP =================
E.append(PageBreak())
E.append(kicker_h1("РАЗДЕЛ 4", "MCP для After Effects — настройка анимаций текстом"))
E.append(Paragraph("Чтобы параметры анимации (скорость вращения, длительность "
    "оборота, easing, anchor) можно было править прямо из Claude Code текстом — "
    "подключаем MCP-сервер, который управляет After Effects через его "
    "scripting-движок (ExtendScript / UXP). Принцип: Claude отдаёт команды → "
    "MCP исполняет их скриптом внутри AE.", st_body))

E.append(Paragraph("Что нужно один раз", st_h2))
E.append(bullets([
    "After Effects с разрешённым исполнением скриптов: "
    "<b>Preferences → Scripting &amp; Expressions → Allow Scripts to Write "
    "Files and Access Network</b> — включить.",
    "Node.js (LTS) — для запуска MCP-сервера.",
    "Claude Code CLI (уже есть).",
]))

E.append(Paragraph("Подключение MCP", st_h2))
E.append(Paragraph("MCP-серверы для AE есть готовые (например, на базе "
    "<font face='MONO'>aeft</font> / ExtendScript-моста). Регистрируем сервер "
    "в Claude Code командой:", st_body))
mcp_cmd = Table([[Paragraph(
    "claude mcp add ae-mcp -- npx -y &lt;ae-mcp-package&gt;", st_mono)]],
    colWidths=[doc.width])
mcp_cmd.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#0E1430")),
    ("BOX",(0,0),(-1,-1),0,colors.black),("LEFTPADDING",(0,0),(-1,-1),12),
    ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
    ("TEXTCOLOR",(0,0),(-1,-1),colors.white)]))
mcp_cmd2 = Table([[Paragraph(
    "ae-mcp add ae-mcp -- npx -y &lt;ae-mcp-package&gt;", st_mono)]], colWidths=[doc.width])
E.append(Table([[Paragraph("claude mcp add ae-mcp -- npx -y &lt;имя-пакета-ae-mcp&gt;",
    S("m2", fontName="MONO", fontSize=10, textColor=colors.white))]],
    colWidths=[doc.width], style=TableStyle([
    ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#0E1430")),
    ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
    ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9)])))
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Альтернатива — прописать сервер вручную в "
    "<font face='MONO'>~/.claude.json</font> (или <font face='MONO'>"
    ".mcp.json</font> в проекте):", st_body))

cfg = ('{\n'
       '  "mcpServers": {\n'
       '    "ae-mcp": {\n'
       '      "command": "npx",\n'
       '      "args": ["-y", "<имя-пакета-ae-mcp>"],\n'
       '      "env": { "AE_HOST": "localhost", "AE_PORT": "8088" }\n'
       '    }\n'
       '  }\n'
       '}')
cfgp = Paragraph(cfg.replace("\n","<br/>").replace(" ","&nbsp;"),
                 S("cfg", fontName="MONO", fontSize=8.8, leading=12.5,
                   textColor=colors.white))
cfgt = Table([[cfgp]], colWidths=[doc.width])
cfgt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#0E1430")),
    ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
    ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]))
E.append(cfgt)
E.append(Spacer(1, 3*mm))

E.append(Paragraph("Проверка и работа", st_h2))
E.append(bullets([
    "Открыть проект в AE, держать его запущенным.",
    "В Claude Code выполнить <font face='MONO'>/mcp</font> — сервер ae-mcp "
    "должен быть в списке (status: connected).",
    "Дальше анимацию правим текстом, например: «поставь rotation головы "
    "0→360 за 4 секунды, easing linear, anchor по центру слоя head_record», "
    "«сделай оборот персонажа 3 сек», «прогони текущий кадр через Bodymovin».",
]))
E.append(Spacer(1, 2*mm))
E.append(Paragraph("Примечание: конкретный npm-пакет AE-MCP выбираем на момент "
    "настройки (экосистема обновляется). Главное — сервер должен уметь: читать/"
    "создавать слои, ставить keyframes на transform-свойства, задавать anchor, "
    "запускать Bodymovin-экспорт. Если пакет требует панель-компаньон внутри AE "
    "(CEP/UXP-расширение) — установить её по инструкции пакета.", st_note))

# ================= CHECKLIST PAGE =================
E.append(PageBreak())
E.append(Paragraph("ЧЕКЛИСТ СДАЧИ", st_kicker))
E.append(Paragraph("Чеклист приёмки", st_h1))
E.append(HRFlowable(width="100%", thickness=1.2, color=LINE, spaceBefore=2, spaceAfter=8))
E.append(Paragraph("Печатается отдельной страницей — отмечать по ходу сдачи.", st_note))
E.append(Spacer(1, 4*mm))

checks = [
    ".ai разнесён на группы, голова — отдельный слой, anchor в центре пластинки",
    "Композиция квадратная (512×512 и 1024×1024), фон прозрачный",
    "Только векторные слои, нет растровых текстур (.png) для шейдинга",
    "Обе анимации зацикливаются бесшовно (360°=0°, без дабл-кадра)",
    "Прогнан тест-кадр через Bodymovin, рендер совпадает с AE",
    "Анимация «вращение персонажа» — готова, loop, linear",
    "Анимация «вращение головы» — готова, anchor строго в центре пластинки",
    "Два .json файла (по одному на анимацию)",
    "Превью .mp4 / .gif на каждую анимацию для согласования",
    "Имена слоёв осмысленные (латиницей), структура групп сохранена",
    "В JSON нет блока assets с растром (проверено)",
]
rows = []
for c in checks:
    rows.append([Paragraph("<font face='SYM'>☐</font>", S("box", fontSize=14, textColor=BLUE)),
                 Paragraph(c, st_chk)])
ct = Table(rows, colWidths=[10*mm, doc.width-10*mm])
ct.setStyle(TableStyle([
    ("VALIGN",(0,0),(-1,-1),"TOP"),
    ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white, colors.HexColor("#F7F9FF")]),
    ("LINEBELOW",(0,0),(-1,-1),0.5,LINE),
    ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
    ("LEFTPADDING",(0,0),(0,-1),8),
]))
E.append(ct)
E.append(Spacer(1, 8*mm))

E.append(Paragraph("Файлы на сдачу", st_h2))
deliv = Table([
    [Paragraph("<b>character_spin.json</b>", st_bodyc), Paragraph("анимация 1 — вращение персонажа", st_bodyc)],
    [Paragraph("<b>head_spin.json</b>", st_bodyc), Paragraph("анимация 2 — вращение головы", st_bodyc)],
    [Paragraph("<b>*_preview.mp4 / .gif</b>", st_bodyc), Paragraph("превью на каждую — для согласования", st_bodyc)],
], colWidths=[55*mm, doc.width-55*mm])
deliv.setStyle(TableStyle([
    ("ROWBACKGROUNDS",(0,0),(-1,-1),[CREAM, colors.white]),
    ("BOX",(0,0),(-1,-1),0.8,LINE),("LINEBELOW",(0,0),(-1,-2),0.5,LINE),
    ("LEFTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),7),
    ("BOTTOMPADDING",(0,0),(-1,-1),7),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
]))
E.append(deliv)

doc.build(E)
print("OK -> Vertushka_AE_Lottie_Brief.pdf")
