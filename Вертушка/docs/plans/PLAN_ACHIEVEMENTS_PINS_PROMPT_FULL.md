# План: попинный бриф для оставшихся ачивок под Nano Banana 2

> 📍 Companion-документ к:
> - [PLAN_ACHIEVEMENTS_PINS_PROMPT.md](PLAN_ACHIEVEMENTS_PINS_PROMPT.md) — Phase 0 (10 пинов, единый мега-промпт под contact-sheet, уже отрисован).
> - [PLAN_ACHIEVEMENTS_V2.md](PLAN_ACHIEVEMENTS_V2.md) — каталог условий, тиров, бэкенда.
>
> 🎯 **Что это:** попинный список из ~76 промптов под Nano Banana 2 (Google Gemini image gen). Для каждой ачивки — один компактный промпт-блок, готовый к копипасту. Цельность серии держит общий STYLE PREAMBLE — вставляется ОДИН раз в начале сессии Nano Banana.
>
> 🚫 **Что не входит:** D3_country_x30 «Кругосветка» — уже отрисован отдельно (см. `Mobile/assets/achievements/256/circumnavigation.png`); все 10 пинов Phase 0 — см. контактный лист.

---

## Содержание

1. [Workflow](#workflow)
2. [STYLE PREAMBLE](#style-preamble) — вставить один раз в начале чата
3. [Phase 0 reference](#phase-0-reference) — что уже сделано (для контекста)
4. [Брифы по сериям](#брифы-по-сериям)
   - [A — Первые шаги](#серия-a--первые-шаги) (1)
   - [B — Размер коллекции](#серия-b--размер-коллекции) (4)
   - [C — Охота за редкостями](#серия-c--охота-за-редкостями) (7)
   - [D — Кругосветка](#серия-d--кругосветка) (6, без D3)
   - [E — Машина времени](#серия-e--машина-времени) (6)
   - [F — Жанры](#серия-f--жанры) (6)
   - [J — Дарящая рука](#серия-j--дарящая-рука) (7, J6 удалена)
   - [K — Сообщество + Вклад](#серия-k--сообщество) (14)
   - [INV — Глас наружу](#серия-inv--глас-наружу) (6)
   - [H — Дискография](#серия-h--дискография) (5)
   - [R — Рандомные пасхалки](#серия-r--рандомные-пасхалки) (14)
   - [META — Выпускные эпики](#серия-meta--выпускные-эпики) (9)
5. [Фразы для итерации](#фразы-для-итерации)
6. [Verification](#verification)

**Всего пинов в новом доке: 85** (J6 удалена, добавлены J7/J8/J9).

---

## Workflow

1. **Открой Nano Banana 2** (gemini.google.com → image-generation чат, или AI Studio).
2. **Скопируй STYLE PREAMBLE целиком** и отправь как первое сообщение. Дождись короткого подтверждения от модели.
3. **Иди по списку пинов сверху вниз.** Для каждого — копируй ОДИН промпт-блок (внутри ` ```text` ... ``` ` ), отправляй, получай PNG.
4. **Сохраняй PNG** в `Mobile/assets/achievements/_raw/{CODE}@2x.png` — имя строго как код ачивки (например `B3_archivist@2x.png`).
5. **Когда наберётся 5-10 пинов** — батч-ресайз через скрипт ниже (см. [Verification](#verification)).
6. **Если пин получился криво** — не уходи из чата. В том же диалоге пиши итерационные фразы из [секции ниже](#фразы-для-итерации).

> 💡 Совет: одна Nano Banana сессия = одна серия (A, B, C…). Модель лучше держит цельность, если контекст не разрывается. Между сериями можно делать новые чаты, но preamble тогда вставляй заново.

---

## STYLE PREAMBLE

> Вставить **ОДНИМ** сообщением в начале сессии Nano Banana 2. Это единственное, что модель должна знать про общий стиль — дальше будут только пин-брифы.

```text
You are designing a coherent set of soft enamel collector pins for a vinyl record collector mobile app called "Vertushka". Across all of my next requests in this chat, follow this style guide strictly.

MATERIAL — Soft Enamel Pin
The pin is a flat metal frame with recessed colored enamel zones. The outermost edge is a raised gold metal ring (#D9A84E) taking about 3-4% of pin area, with a thin dark navy outline (#0B1438) on the very outside so the pin reads on any background. Inside the pin, thin gold metal lines (1.5-2 px equivalent) separate colored enamel zones. Each large enamel zone has one subtle specular highlight along its upper curve, like real enamel pin photography. NO photorealistic 3D rendering. NO gradient mesh. NO noise. Clean illustrative enamel look.

PALETTE — STRICT, NO OTHER COLORS
- Navy            #0B1438  — outlines, dark zones
- Cobalt          #2A4BD7  — saturated blue accents
- Cobalt Deep     #0E1A52  — deeper blue when needed
- Cobalt Soft     #5C7AE8  — softer blue fills
- Ember           #E85A2A  — warm orange-red, especially vinyl record labels
- Ivory           #FBF5EA  — cream, paper, ribbons, fills
- Vinyl Black     #1A1A2E  — vinyl records themselves
- Gold            #D9A84E  — contour ring, metal lines, sparkles, numerals
- Rose Pink       #E89AC0  — center labels on RARE-tier pins only (see TIER)

TIER — DO NOT paint the whole pin by tier
The tier is rendered as a colored aura BEHIND the pin in the app UI — not inside the pin. So a "rare" pin and a "simple" pin should look like the same enamel set, distinguished by metaphor, not by overall color. Two exceptions only:
- RARE tier (🌸) and higher: add 2-3 tiny 4-pointed gold sparkle stars somewhere inside the pin as a rarity hint. Each star ~3-4% of pin diameter.
- If a pin has a clear "center label" (vinyl center, medallion, certificate seal), RARE-tier may use Rose Pink #E89AC0 for that single label instead of Ember — subtle visual cue without dominating.

FORM
- Pin shape may extend beyond the square frame: mast of a ship, window shutter, ribbon ends, rays, hat tip, horn flare. Each pin has its own silhouette. NEVER make all pins round.
- The pin must read at 64×64 px (grid card). One bold central figure ≥55% of area; small details are sacrificed for silhouette.
- Square 1:1 frame. Pin fills approximately 92% of the frame; small breathing room around it.

OUTPUT
- 1024×1024 PNG with FULLY TRANSPARENT BACKGROUND (alpha channel).
- NO drop shadow under the pin. NO cream/paper rectangular background. NO card frame around the pin.
- NO UI elements, NO share icons, NO buttons, NO watermarks.
- NO text labels OUTSIDE the pin. Inside the pin, text is allowed ONLY when a meaningful number/symbol is part of the metaphor (e.g. "10", "50", "100", "33⅓", "78", "π", "N", "FEB 29"). Use vintage serif or chunky numeral style. Avoid long words.

ITERATION
When I ask for the next pin, keep this exact material, palette, gold contour, and craftsmanship — same enamel series feel. Reply only with the generated image, no commentary unless I ask.

If you understood the style and are ready for the first pin, reply with just: "Ready."
```

---

## Phase 0 reference

Эти 10 уже отрисованы и задают язык серии. Если в чате нужно сослаться — пиши «in the style of A1 Поехали (vinyl with descending tonearm and gold spark)».

| Код | Название | Тир | Метафора (краткая) |
|---|---|---|---|
| `A1_first_record` | Поехали | 💧 | Игла тонарма опускается на пластинку, золотая искра в точке контакта. |
| `A2_first_wishlist` | Хотелка | 💧 | Сердце «выточено из пластинки», 5 канавок внутри. |
| `A3_avatar_set` | Аватар | 💧 | Медальон-портрет 78 RPM, лента-баннер cobalt. |
| `A4_public_profile` | Распахнул | 💧 | Открытое окно, силуэт ночного города из аналоговых форматов. |
| `META_foundation` | На борту | 🔵 | Парусник: корпус-винил на ребре, парус = обложка альбома, флажок «5». |
| `B1_starter` | Десятка | 💧 | Полка из 10 разноцветных корешков + крупная «10» сверху. |
| `B2_collector` | Полтинник | 💧 | DJ flight case, корешки внутри, печать «50» в лавровом венке. |
| `J1_first_gift` | Забронировал | 💧 | Коробка перевязана виниловой лентой, бант = центральный лейбл. |
| `R_self_titled` | Тёзка | 🌸 | Две зеркальные пластинки, золотой знак «=», розовые лейблы. |
| `R_thirty_three` | Тридцать три | 🌸 | Винил-медаль, лейбл «33⅓» в венке, 7 лучей. |

Плюс отдельный D3 «Кругосветка» 🌸 — винил-глобус с парусником и компасом, см. [PLAN_ACHIEVEMENTS_V2.md §4.4](PLAN_ACHIEVEMENTS_V2.md).

---

## Брифы по сериям

### Серия A — Первые шаги

#### `A5_second_collection` — Полка-двойник 💧
> Метафора: вторая коллекция — две независимые полки рядом, разделены по теме.

```text
Generate a soft enamel pin: two vinyl shelves side by side, separated by a thin vertical gold divider with a small gold flag on top — symbolizing a second curated collection.
Composition: left shelf has a cobalt-blue side wall and contains 4 vinyl spine slips in mixed brand colors; right shelf has an ivory-cream side wall with 4 different spines; the gold dividing line runs floor-to-ceiling between them, topped by a small triangular gold pennant.
Palette: navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7, vinyl black #1A1A2E, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия B — Размер коллекции

#### `B3_archivist` — Сотня 🔵
> Метафора: 100 пластинок — архив с табличкой-инвентарём.

```text
Generate a soft enamel pin: a deep archive shelf packed with vinyl in protective sleeves, fronted by an oval gold engraved plaque reading "100" in vintage serif numerals — the archivist's milestone.
Composition: a horizontal navy shelf occupies the bottom 60% of the pin; about 10 vertical spine slips in ivory, cobalt, and cobalt-soft fill the shelf tightly; centered on the shelf face is a bold oval gold plaque with "100" engraved in serif, surrounded by a thin decorative gold border; bottom-right corner shows a small ivory inventory card peeking out.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `B4_curator` — Куратор 🌸
> Метафора: 250 пластинок — куратор, который выбирает. Музейная витрина с одним экземпляром.

```text
Generate a soft enamel pin: a museum-style glass display case showing a single floating vinyl record under a spotlight, with a gold engraved plaque "250" below — the curator who chose every record.
Composition: a square gold-framed glass display case fills 70% of the pin; inside floats one vinyl record (vinyl black with rose pink center label and gold grooves) angled slightly; a downward gold cone of light highlights it; below the case, a horizontal ivory plaque shows "250" in vintage serif gold; add 3 tiny gold sparkle stars inside the case as rarity markers.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `B5_keeper` — Хранитель 🌌
> Метафора: 500 пластинок — банковский сейф-хранилище со штурвалом.

```text
Generate a soft enamel pin: a vault-tower safe with a round wheel-handle door, "500" engraved on the door, and inside (visible through a small gold-framed inspection window) several stacked vinyl records — the keeper's vault.
Composition: a vertical rectangular safe in deep cobalt fills 80% of the pin; centered is a round gold wheel-handle with 6 radiating spokes; above the wheel, "500" in serif gold; below the wheel, a small rectangular gold-framed inspection window shows 3-4 vinyl spines stacked; 4 small gold rivets in the corners; add 2 tiny gold sparkle stars near the upper corners as rarity markers.
Palette: navy #0B1438, vinyl black #1A1A2E, cobalt deep #0E1A52, gold #D9A84E, ember #E85A2A.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `B6_warden` — Смотритель ⚫
> Метафора: 1000 пластинок — фасад классической библиотеки/архива.

```text
Generate a soft enamel pin: the facade of a classical archive building with four columns, a triangular pediment showing "1000" in roman-numeral-style serif gold, and through the open doorway a silhouette of a vinyl shelf — the warden's library.
Composition: an ivory-cream temple facade fills 75% of the pin; four vertical gold columns; triangular gold-edged pediment with "1000" centered; below, a tall navy doorway opening revealing 4-5 vinyl spines in cobalt and ivory; the pediment peak extends beyond the top frame edge; add 3 tiny gold sparkle stars in the sky above the pediment.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, cobalt deep #0E1A52, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия C — Охота за редкостями

#### `C1_limited_x5` — Тираж ограничен 💧
> Метафора: 5 нумерованных лимиток — стопка с печатями.

```text
Generate a soft enamel pin: a fanned-out stack of 5 limited-edition vinyl sleeves, each stamped with a serial number "#1" through "#5", topped with a gold "LIMITED" wax seal.
Composition: 5 vinyl sleeves fanned like playing cards, each in a different brand color (cobalt, ivory, navy, cobalt soft, vinyl black); each sleeve has a small gold rectangular stamp with #N in serif; top-center has a circular gold wax seal embossed with "LIMITED" in tiny letters.
Palette: navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7, cobalt soft #5C7AE8, vinyl black #1A1A2E, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C2_limited_x25` — По счёту 🌸
> Метафора: 25 лимиток — гербовый сертификат коллекционера.

```text
Generate a soft enamel pin: an ornate certificate scroll with a wax seal "25" at center, two ribbon ends curling outside the frame — the numbered collector's diploma.
Composition: a horizontal ivory parchment fills the upper 60%, edges curled; centered is a large round red wax seal in ember stamped with "25" in serif gold; below the scroll, two small vinyl records show numbered rose-pink labels; ribbon ends extend left and right beyond the pin frame; add 2 tiny gold sparkle stars above the seal.
Palette: navy #0B1438, ivory #FBF5EA, ember #E85A2A, rose pink #E89AC0, vinyl black #1A1A2E, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C3_collectible_x1` — Сокровище 🔵
> Метафора: первая коллекционка — сокровище в бархатной шкатулке.

```text
Generate a soft enamel pin: a velvet-lined treasure box, lid open, displaying a single precious vinyl record glowing softly inside — the first collectible.
Composition: rectangular box with navy exterior and cobalt-soft velvet interior fills 75% of pin; the lid is open and tilted back, attached by tiny gold hinges; inside, one vinyl record sits angled — vinyl black with an ember center label and gold grooves; a subtle gold radiance glows around the record; small gold corner decorations on the box.
Palette: navy #0B1438, cobalt soft #5C7AE8, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C4_collectible_x5` — Шкаф редкостей 🌸
> Метафора: 5 коллекционок — кабинет редкостей со стеклянными дверьми.

```text
Generate a soft enamel pin: a tall glass-fronted cabinet of curiosities with 4 shelves, each holding a different rare audio artifact — a vinyl record, a sleeve, a reel-to-reel spool, a small case — gold handle on the door.
Composition: tall narrow navy cabinet fills 90% of the pin height, with 4 horizontal gold-edged shelves; top shelf shows a vinyl on a stand, second shelf an angled album sleeve in cobalt, third shelf a small reel with two visible bobbins, fourth shelf a flat case; thin gold door frame down the middle splits into double doors; a small round gold handle in the center; add 3 tiny gold sparkle stars inside the cabinet.
Palette: navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C5_collectible_x15` — Кладовая 🌌
> Метафора: 15 коллекционок — арочная дверь хранилища с витражом и лучами.

```text
Generate a soft enamel pin: a heavy arched vault door with a stained-glass upper panel showing stacked vinyl, "15" engraved on the door, golden rays of light streaming outward — the rarities storage.
Composition: tall arched navy door fills 85% of pin; top third has a stained-glass arched window in cobalt and rose pink, with silhouette of 3 stacked vinyl records visible inside; below, a heavy gold lock plate engraved "15" in serif; 6 short gold rays radiate from behind the door's edges extending past the pin frame; add 3 tiny gold sparkle stars around the rays.
Palette: navy #0B1438, cobalt #2A4BD7, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C6_hot_in_wishlist` — Хочу горячего 🔵
> Метафора: 5 горячих пластинок в вишлисте — пылающее сердце с цифрой.

```text
Generate a soft enamel pin: a flaming heart-shaped vinyl record — the wishlist of hot, in-demand records — with "5" on the center label.
Composition: classic heart silhouette with concentric vinyl grooves inside in vinyl black and gold; a small ember-colored flame curls above the heart's top extending beyond the frame; centered is a round cobalt label with "5" in serif gold; the heart sits on a small gold curlicue base.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, cobalt #2A4BD7, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `C7_hot_in_collection` — Тренд на полке 🌸
> Метафора: 10 горячих в коллекции — пьедестал с пылающей пластинкой.

```text
Generate a soft enamel pin: a three-tiered gold podium with a flaming vinyl record on the top step and "10" on the front face — the collection has the hottest records.
Composition: stepped podium structure in navy with gold edges, three levels; top step holds a single vinyl record (vinyl black with rose pink center) wreathed in small ember flames at the top; the bottom front face shows large "10" in vintage serif gold; small gold star at the very top extending above the frame; add 2 tiny gold sparkle stars near the flames.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия D — Кругосветка

> D3_country_x30 «Кругосветка» уже сделан отдельно — пропускаем.

#### `D1_country_x5` — Космополит 💧
> Метафора: 5 стран — пять флажков воткнуты в глобус-винил.

```text
Generate a soft enamel pin: a small vinyl globe with 5 tiny gold pennant flags planted on 5 different continents — the cosmopolitan collector's start.
Composition: a circular vinyl record with the world map inlaid in ivory continents and vinyl-black ocean grooves; 5 small triangular gold flags on thin gold stems planted in: North America, South America, Europe, Africa, and Asia; no ship, no compass; a thin gold equator line crossing the center.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `D2_country_x15` — Глобус 🔵
> Метафора: 15 стран — открытый атлас с маркерами на карте.

```text
Generate a soft enamel pin: an open atlas book showing a two-page world map with 15 small gold pin markers scattered across continents, vinyl-groove latitude lines instead of normal coordinates.
Composition: open book at 80% pin width, ivory pages with navy edges, gold spine in the middle; spread across both pages is a stylized world map with continents in cobalt-soft outline; concentric vinyl grooves in gold fan out from center like latitude lines; 15 small gold round dots scattered on continents; bottom-right corner of the page shows a tiny "15" in serif.
Palette: navy #0B1438, ivory #FBF5EA, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `D4_japanese_x10` — Из Японии 🌸
> Метафора: 10 японских прессов — тория-ворота перед пластинкой, Фудзи на фоне.

```text
Generate a soft enamel pin: a red torii gate standing in front of a vertical vinyl record, Mount Fuji silhouette in the background, "10" engraved on a small wooden plaque at the base — the Japanese pressings.
Composition: vinyl record fills 65% of pin as backdrop, vinyl black with rose pink center label and gold grooves; in front of it stands a red ember torii gate, two pillars and the curved top beam, extending slightly beyond the top frame; behind the gate, a small ivory-colored Mt. Fuji silhouette peeks; bottom-center, a small navy plaque with "10" in serif gold; add 2 tiny gold sparkle stars near the Fuji peak.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `D5_melodiya_x10` — Мелодия 🌸
> Метафора: 10 СССР-прессов — пластинка в стиле классической «Мелодии», звезда + декор.

```text
Generate a soft enamel pin: a Soviet-era Melodiya-style vinyl record with a deep cobalt center label, a gold 5-point star above the center, and "x10" in vintage serif on the label.
Composition: large vinyl record centered, vinyl black with concentric gold grooves; center label in deep cobalt #0E1A52 fills 40% of record diameter; on the label, a 5-pointed gold star at top, "x10" in vintage serif gold below it; surrounding the label, a thin ornamental gold ring; below the record, a small ivory ribbon banner with decorative gold curls (no readable text); add 2 tiny gold sparkle stars near the star.
Palette: navy #0B1438, vinyl black #1A1A2E, cobalt deep #0E1A52, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `D6_uk_collectible_x3` — Британский почерк 🌸
> Метафора: 3 редкие UK-коллекционки — британский шик: цилиндр и стилизованный флаг.

```text
Generate a soft enamel pin: a small black top hat resting on a stack of 3 vinyl records, with a Union-Jack-inspired gold cross banner behind — the British collectibles.
Composition: stack of 3 vinyl sleeves slightly offset, top one navy, middle ivory, bottom vinyl black, each about 80% pin width and 12% pin height; on top of the stack a small vinyl black top hat with a thin rose-pink ribbon band; behind the stack, a stylized rectangular banner in navy with a thick gold diagonal cross overlapping a thin gold straight cross (suggesting the Union flag without literal red and white); add 2 tiny gold sparkle stars above the hat.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `D7_german_x10` — Made in Germany 🌸
> Метафора: 10 немецких прессов — шестерёнка-машина, пластинка внутри.

```text
Generate a soft enamel pin: a vinyl record set inside a large golden gear, mechanical precision symbolizing German pressings, "x10" on the record's center label.
Composition: a large 12-tooth gold gear fills 90% of pin frame; vinyl record centered inside the gear (vinyl black with rose pink center label, "x10" in serif gold on the label); gold grooves on the record echo the gear teeth; a tiny golden bolt at the very center of the label; add 3 tiny gold sparkle stars around the gear.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия E — Машина времени

#### `E1_60s` — Шестидесятники 💧
> Метафора: 60-е, flower power — лейбл-ромашка.

```text
Generate a soft enamel pin: a vinyl record with a daisy-flower-shaped center label, "60s" written in playful serif on the label — the 1960s flower-power era.
Composition: vinyl record centered, vinyl black with gold grooves; center label is a 6-petal daisy shape in ivory with an ember circle in the middle; "60s" text in gold serif curves across the daisy center; two small leaves in cobalt soft tucked to the side of the record.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, ember #E85A2A, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `E2_70s` — Золотой век 💧
> Метафора: 70-е, золотой век винила — солнце-лейбл с лучами.

```text
Generate a soft enamel pin: a vinyl record with a sun-burst center label, long gold rays extending beyond the pin frame, "70s" on the label — the golden age of vinyl.
Composition: vinyl record centered, vinyl black with gold grooves; center label is a perfect circle in ember surrounded by 8 long gold rays radiating outward, several rays extending beyond the pin's outer ring; "70s" centered on the ember in vintage gold serif; small gold dots between rays.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `E3_80s` — Неон 💧
> Метафора: 80-е, неон, синт — лейбл-треугольник, молния сверху.

```text
Generate a soft enamel pin: a vinyl record with a neon-triangle center label and a small lightning bolt, "80s" in retro-style — the 1980s synth era.
Composition: vinyl record centered, vinyl black with gold grooves; center label is an inverted triangle in cobalt with a thin gold outline; inside the triangle, "80s" in chunky retro gold serif; a gold lightning bolt zigzags from the top point of the triangle extending past the top frame edge; small dot accents in cobalt soft around the label.
Palette: navy #0B1438, vinyl black #1A1A2E, cobalt #2A4BD7, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `E4_modern` — Сегодняшний 💧
> Метафора: 5 пластинок за 3 года — лейбл-QR (сетка), цифра сбоку.

```text
Generate a soft enamel pin: a vinyl record with a square modern center label resembling a QR code grid (5x5 navy and gold cells), "5" in small serif beside the label — the modern releases.
Composition: vinyl record centered, vinyl black with gold grooves; center label is a square (not round) in ivory cream, containing a 5×5 grid of small alternating gold and navy squares (suggesting a QR code without being one); small gold "5" digit just outside the label at 3 o'clock position.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `E5_pre_1960` — Доисторический 🌸
> Метафора: пластинка до 1960 — патефон с золотой трубой.

```text
Generate a soft enamel pin: a vintage gramophone with a golden flared horn extending beyond the top frame, a 78 RPM record spinning on its platter — the pre-1960 era.
Composition: gramophone occupies center of pin; a circular wooden navy base; ivory platter spinning a vinyl black record with rose pink center; gold curved horn flares upward and to the right, exiting past the top-right corner of the frame; small gold crank handle on the left side; add 2 tiny gold sparkle stars near the horn opening.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `E6_decade_full` — Десятилетие 🌌
> Метафора: по одной пластинке из каждого года 10-летия — таймлайн с 10 точками.

```text
Generate a soft enamel pin: a curved gold timeline ribbon with 10 evenly spaced mini-vinyl markers, "10 YEARS" engraved on the ribbon — every year of a single decade collected.
Composition: a gold ribbon curves in a gentle arc across the pin, ends extending slightly past left and right frame; 10 small vinyl-record dots evenly spaced along the ribbon, each with a tiny gold center; above the ribbon, "10 YEARS" in vintage serif gold; below the ribbon, a small navy starburst; add 3 tiny gold sparkle stars above the ribbon.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия F — Жанры

#### `F1_diversity_5` — Разносторонний 💧
> Метафора: 5 разных жанров — круглая «пицца» с инструментами в каждом сегменте.

```text
Generate a soft enamel pin: a circular pie-chart-style genre wheel split into 5 colored segments, each marked by a small musical icon (note, guitar, drum, synth-key, microphone) — the diverse music lover.
Composition: a large circle fills 85% of pin, divided into 5 equal pie wedges in cobalt, ember, ivory, cobalt soft, navy; thin gold lines separate wedges; in the center of each wedge, a small gold icon: musical note, guitar headstock silhouette, drum, synth keyboard, microphone; small gold center cap where wedges meet.
Palette: navy #0B1438, cobalt #2A4BD7, ember #E85A2A, ivory #FBF5EA, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `F2_diversity_10` — Всеядный 🔵
> Метафора: 10 жанров — ящик-органайзер с 10 ячейками, в каждой иконка.

```text
Generate a soft enamel pin: a small organizer chest with two rows of 5 compartments, each compartment containing a different musical genre icon — the omnivorous listener.
Composition: rectangular navy chest fills 80% of pin; two horizontal rows of 5 square compartments each, gold-framed; each compartment contains a small distinct gold icon (eighth note, treble clef, drum, guitar, saxophone, piano keys, vinyl, microphone, headphones, cassette tape); centered above the chest, a small gold ribbon banner reads "10".
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `F3_jazz_x25` — Эй, Арнольд 🌸
> Метафора: 25 jazz — саксофон за пластинкой.

```text
Generate a soft enamel pin: a saxophone silhouette resting diagonally behind a jazz vinyl record, "25" on the record's center label — the jazz selector.
Composition: gold saxophone silhouette in profile, mouthpiece at top-left exiting past frame, bell at bottom-right; in front of it, a vinyl record (vinyl black, rose pink center label) angled slightly; on the label, "25" in serif gold with a small treble clef beside it; thin gold curl ornament near the sax bell; add 2 tiny gold sparkle stars near the sax mouthpiece.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `F4_electronic_x25` — Рейв 🌸
> Метафора: 25 electronic — синт-клавиши и mod-колесо.

```text
Generate a soft enamel pin: a row of synthesizer keys with a modulation wheel and a vinyl record behind it, "25" on the center label — the electronic-music conductor.
Composition: bottom 40% of pin shows a gold keyboard with 5 white keys and 4 black mini-keys; left side has a round cobalt modulation wheel; behind the keyboard rises a vinyl record (vinyl black, rose pink center, "25" in gold serif); a thin gold cable curve loops from the keyboard around the record; add 2 tiny gold sparkle stars near the modulation wheel.
Palette: navy #0B1438, vinyl black #1A1A2E, cobalt #2A4BD7, rose pink #E89AC0, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `F5_classical_x15` — Классик 🌸
> Метафора: 15 classical — античная колонна и лавровый венок.

```text
Generate a soft enamel pin: an ionic Greek column behind a vinyl record, "15" inside a laurel wreath on the center label — the classical collector.
Composition: vertical fluted gold column on navy background, capital with spiral volutes extending above the top frame; in front, a vinyl record (vinyl black with gold grooves); center label is a rose-pink circle with a small gold laurel wreath surrounding "15" in serif gold; base of column shows a small step block below; add 2 tiny gold sparkle stars above the column capital.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `F6_rock_x25` — Громко 🌸
> Метафора: 25 rock — электрогитара по диагонали, молния.

```text
Generate a soft enamel pin: an electric guitar silhouette diagonally crossing the pin, headstock extending beyond the frame, a gold lightning bolt cutting across, "25" engraved on the guitar body — loud and proud rock.
Composition: a navy electric guitar body in the lower-right; long gold neck extending diagonally up to the top-left, headstock extending past the top-left frame edge; a gold lightning bolt zigzags from upper-right to lower-left, partly overlapping the guitar; "25" in chunky serif gold on the guitar body; add 2 tiny gold sparkle stars near the lightning.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия J — Дарящая рука

#### `J2_gift_done` — Долетело 💧
> Метафора: первый завершённый подарок — конверт с пластинкой и почтовым штампом.

```text
Generate a soft enamel pin: a vinyl-record-shaped envelope with a gold "✓" delivery stamp on it — the first completed gift.
Composition: ivory envelope tilted slightly, flap open at the top; a small vinyl record peeks out the top; on the envelope front, a round gold postage stamp with a thick gold checkmark inside; a small navy address line below the stamp.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `J3_three_recipients` — Дарящая рука 🔵
> Метафора: 3 разных получателя — ладонь с тремя коробочками.

```text
Generate a soft enamel pin: an open palm hand silhouette holding three small wrapped gift boxes, each different colored — the giving hand reaching three recipients.
Composition: gold hand silhouette palm-up, fingers slightly curled, occupying the bottom 60% of pin; resting on the palm are three small wrapped gift boxes lined up: leftmost cobalt with ivory ribbon, middle ember with gold ribbon, right ivory with cobalt ribbon; small gold sparkle dot above each box.
Palette: navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `J4_ten_recipients` — Праздник 🌸
> Метафора: 10 получателей — банкетный стол с 10 коробками и гирляндой.

```text
Generate a soft enamel pin: a long banquet table with 10 wrapped gift boxes in a row, a small bunting garland above — the celebration of generosity.
Composition: horizontal navy table runs across the middle of pin; 10 small gift boxes line the table in alternating colors (cobalt, ivory, ember, cobalt soft, repeating); above the table, a curved gold string with 4 tiny pennant flags in rose pink and ivory; below the table, a small "10" in serif gold on a banner; add 3 tiny gold sparkle stars in the air above the bunting.
Palette: navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7, ember #E85A2A, rose pink #E89AC0, cobalt soft #5C7AE8, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `J5_first_received` — С теплом 💧
> Метафора: получил первый подарок — открытая коробка, пластинка с тёплым свечением.

```text
Generate a soft enamel pin: an open gift box from above, a vinyl record rising out of it surrounded by a warm ember glow — the first gift received.
Composition: ivory gift box at the bottom 40% of pin, lid tilted back showing the open interior; from the box rises a vinyl record (vinyl black, ember center label, gold grooves), partly emerging; behind the record a warm ember-orange aura ring; a thin gold ribbon trails from the box edge.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

> ⚠️ `J6_perfect_match` («В точку», priority=high) удалена из каталога — в
> данных `priority` это int 0..10, у UI-понятия «High» никогда не было
> реального значения. Заменена на J7/J8/J9 ниже.

#### `J7_boomerang` — Бумеранг 🌸
> Метафора: подарок вернулся тому, кто его дарил — бумеранг из винила летит по кругу.

```text
Generate a soft enamel pin: a vinyl-record-shaped boomerang flying in a circular arc, a thin motion-trail looping back to its own tail — the gift that returns to the giver.
Composition: a curved boomerang shape rendered as a vinyl record (vinyl black with gold grooves, ember center label) bent into a wide arc spanning the pin diagonally; a dotted gold motion-trail follows the arc and curls back toward the starting point, forming a near-closed loop; add 2 tiny gold sparkle stars along the trail.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `J8_loved` — Любимчик 🔵
> Метафора: подарки от трёх разных дарителей — раскрытый веер из трёх лент, сходящихся к одной пластинке.

```text
Generate a soft enamel pin: three differently-colored ribbons converging from three directions onto a single vinyl record at the center, like spotlights of affection — gifts from three different givers.
Composition: vinyl record (vinyl black, gold grooves, rose-pink center label) centered in the bottom 60% of pin; three ribbons enter from upper-left (cobalt), top (gold), upper-right (ember), each tied in a small bow where it meets the record edge; small gold sparkle dot at each bow.
Palette: navy #0B1438, vinyl black #1A1A2E, cobalt #2A4BD7, ember #E85A2A, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `J9_santa` — Дед Мороз 🔵
> Метафора: подарок успел к новогодним праздникам — мешок подарков под еловой веткой со снежинкой.

```text
Generate a soft enamel pin: a Santa-style gift sack with a vinyl record peeking out, resting beneath a small pine branch with a snowflake above — the gift that made it under the tree in time.
Composition: ivory gift sack tied with gold cord at the bottom 55% of pin, a vinyl record (vinyl black, ember center label) peeking out the open top; a small navy pine branch with 3 needles curves over the upper-left of the sack; a single 6-point gold snowflake sits in the upper-right corner; add 2 tiny gold sparkle stars near the snowflake.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия K — Сообщество

> **Единый вектор серии K, трек 1 — «сцена»:** путь от зрителя в зале до хедлайнера со своим залом. Держи концертную метафору на K1→K4, K7 — отдельный жест «за кулисы».

#### `K1_following_x5` — Зритель 💧 ✅ отрисован
> Метафора: подписан на 5 — оторванный корешок билета, 5 отверстий компостера.

```text
Generate a soft enamel pin: a single torn concert ticket stub standing upright, tilted slightly, with five punched holes along its gold perforated edge.
Composition: one bold vertical ivory ticket stub fills ~60% of the pin, tilted about 8 degrees; a gold perforated tear-line runs down its left side with 5 clean punched holes; on the stub face, a tiny vinyl record icon with ember center, the word "ADMIT" in small vintage serif, and a chunky gold serif "5" at the bottom; three small gold ticket-confetti flecks float freely around the stub in empty space, like the floating music notes in the microphone pin.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No background scene, no crowd, no frame.
Output: 1024×1024 PNG, transparent background.
```

#### `K2_first_follower` — Первый ряд 💧 ✅ отрисован
> Метафора: первый подписчик — одно откидное кресло первого ряда, и оно занято.

```text
Generate a soft enamel pin: a single vintage theatre seat, folded down, seen three-quarter from the front — the very first seat in the house is taken.
Composition: one bold navy velvet theatre chair fills ~65% of the pin, with gold armrest curls and gold rivets; a small gold plaque on the backrest reads "ROW 1" in tiny vintage serif; resting on the seat cushion sits one small vinyl record (vinyl black, ember center) like a bouquet left by a fan; a chunky gold serif "1" on the chair leg base; two small gold sparkle dots float above the backrest.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No audience, no stage, no frame.
Output: 1024×1024 PNG, transparent background.
```

#### `K3_followers_x5` — Квартирник 💧
> Метафора: 5 подписчиков — домашний концерт: микрофон в комнате, кучка людей сидит вокруг.

```text
Generate a soft enamel pin: an intimate living-room gig — a microphone on a small rug with 5 silhouetted listeners seated around it in a half-circle.
Composition: center holds a vertical gold microphone on a low stand standing on a small ivory rug; around the lower half, 5 small navy silhouetted heads seated in a loose semicircle facing the mic; a small hanging lamp in gold above the mic casts a soft cone; small "5" in serif gold on the rug edge.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K4_followers_x50` — Хедлайнер 🌸 ✅ отрисован
> Метафора: 50 подписчиков — лампочная вывеска-marquee, силуэт выходит за верхний край.

```text
Generate a soft enamel pin: a theatre marquee sign lit with bulbs, its top edge extending past the top of the frame — your name is up in lights.
Composition: one bold horizontal marquee board fills ~65% of the pin, rose pink #E89AC0 panel inside a double gold bulb-lined border with ~14 round gold bulbs; "50" in chunky vintage serif gold centered on the panel, with a small vinyl record silhouette beside it; the sign hangs from two thin gold chains that run off the top edge of the frame; a short ivory banner ribbon drapes under the sign reading "TONIGHT" in tiny serif; three 4-pointed gold sparkle stars float around the sign in empty space.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No crowd, no building, no frame.
Output: 1024×1024 PNG, transparent background.
```

#### `K7_mutual_x10` — Бэкстейдж 🔵 ✅ отрисован
> Метафора: 10 взаимных подписок — ламинированный пропуск на шнурке, петля-восьмёрка намекает на взаимность.

```text
Generate a soft enamel pin: a laminated backstage pass hanging on a lanyard, the lanyard cord looping out past the top of the frame.
Composition: one bold vertical ivory pass card fills ~55% of the pin, slightly tilted, held by a gold clip at the top; the cord is a cobalt #2A4BD7 lanyard strap that crosses over itself in a figure-eight loop before exiting the top edge (hinting at mutual, two-way access); on the card face: "BACKSTAGE" in small chunky serif navy, a gold star, a thin cobalt stripe, and a chunky gold serif "10"; a small vinyl record icon with ember center in the card's lower corner; two small gold sparkle dots float beside the clip.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, cobalt #2A4BD7, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No curtain, no scene, no frame.
Output: 1024×1024 PNG, transparent background.
```

> **K5_views_x100 «Витрина» и K6_views_x1000 «На главной» — СКРЫТЫ с v2.1** (просмотры публичного профиля, ненадёжный подсчёт; см. [PLAN_ACHIEVEMENTS_V2.md §4.8](PLAN_ACHIEVEMENTS_V2.md)). Пины не нужны — старые промпты удалены.

#### `K8_contrib_x1` — Стажёр 💧
> Метафора: 1 одобренный ручной релиз — курьер на первом рейсе, одна коробка-пластинка в руках.

```text
Generate a soft enamel pin: a delivery courier silhouette carrying one vinyl-record box, a small gold checkmark badge on the cap — the rookie's first contribution delivered.
Composition: a navy courier silhouette in profile, walking right, holding a single square package in front with a vinyl-record disc shown on its face (ember center); a small gold delivery-cap on the head with a tiny gold checkmark badge; motion lines in thin gold behind; small "1" in serif gold near the box.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K9_contrib_x5` — Поставщик 🔵
> Метафора: 5 одобренных релизов — подтверждённый канал поставки: ящик с печатью «APPROVED» и пятью пластинками.

```text
Generate a soft enamel pin: an open supply crate stamped "OK", holding 5 vinyl records standing upright, a gold supply-route arrow looping around — the verified supplier.
Composition: a navy wooden crate in the lower 60% of pin, front panel showing a round gold "OK" stamp; inside the crate, 5 vinyl-record edges stand upright in a row (alternating ember and cobalt centers visible); a thin gold dashed delivery-route arrow loops from the crate up and around; small "5" in serif gold on the crate panel.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, cobalt #2A4BD7, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K10_contrib_x20` — Да, шеф! 🌸
> Метафора: 20 одобренных релизов — «Yes Chef»: фигура несёт высокую башню из коробок-пластинок, едва балансируя.

```text
Generate a soft enamel pin: a figure carrying a tall teetering tower of pizza-box-style vinyl crates, a small chef's toque on top, "20" on the lowest box — the master deliverer, "Yes Chef!".
Composition: a navy silhouette figure centered, arms wrapped around a tall stack of 5-6 square crates rising past the top frame, each crate face showing a vinyl-disc icon (ember/ivory centers); a small white chef's toque hat balanced on the very top box; slight lean to suggest balancing weight; "20" in chunky serif gold on the lowest crate; add 3 tiny gold sparkle stars near the top.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K11_msgs_x10` — Есть контакт 💧 ✅ отрисован
> Метафора: 10 сообщений — игла звукоснимателя опустилась в канавку и точка контакта расцвела речевым пузырём.

```text
Generate a soft enamel pin: a tonearm needle touching down into a record groove, and the point of contact blooms into a small speech bubble — the moment the connection is made.
Composition: one bold gold tonearm enters from the upper right at a 45-degree angle, its navy headshell and gold stylus pointing down-left; below it, a partial vinyl record arc (vinyl black with gold groove lines and an ember center label) occupies the lower left; exactly at the stylus tip sits a small rounded ivory speech bubble with three gold typing dots inside and a tiny gold contact spark behind it; a chunky gold serif "10" sits on the record label; two small gold sparkle dots float near the tonearm.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No frame, no background.
Output: 1024×1024 PNG, transparent background.
```

#### `K12_msgs_x50` — Продажник 🔵 ✅ отрисован
> Метафора: 50 сообщений — винтажная трубка, витой провод завивается в виниловую спираль.

```text
Generate a soft enamel pin: a vintage telephone handset held mid-call, its coiled cord spiralling downward and turning into a vinyl record groove spiral.
Composition: one bold gold-and-navy handset lies diagonally across the upper 55% of the pin, receiver end lower-left, mouthpiece upper-right, with a single specular highlight along its top curve; from the mouthpiece end a cobalt #2A4BD7 coiled cord drops and coils tighter and tighter until it becomes a small vinyl record spiral (vinyl black, ember center) in the lower right; three small ivory chat bubbles rise freely from the receiver toward the upper left, the largest carrying a chunky gold serif "50"; the cord's last coil extends slightly past the bottom edge.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, cobalt #2A4BD7, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No human figure, no frame.
Output: 1024×1024 PNG, transparent background.
```

#### `K13_msgs_x200` — Уолл-стрит 🌸 ✅ отрисован
> Метафора: 200 сообщений — зигзаг-график пробивает потолок, стрелка тащит бирку «200». Ось X — время (одни часы), ось Y — сообщения (один пузырь).

```text
Generate a soft enamel pin: a single zigzag chart line that rises in jagged steps and then punches its arrowhead clean through a ceiling line, carrying a "200" tag.
Composition: ONE thick gold polyline is the only chart content — it starts at the lower-left origin and moves right in a sharp zigzag (up, small dip, up, small dip, up), each segment a straight angular stroke, gaining height with every step, then makes one long steep final rise and ends in a large gold arrowhead pointing up-right. The arrowhead pierces through a single thin horizontal ivory ceiling bar near the top; the bar is cracked and split apart exactly at the puncture, with 3 small ivory shards flying outward, and the arrowhead tip extends slightly past the top edge of the frame. A small navy tag with a chunky vintage serif gold "200" hangs from the arrow's neck on a tiny gold ring.
Axes: a thin gold L-shaped axis in the lower left, with small evenly spaced tick marks. Label each axis with exactly ONE glyph, not a repeated series: a single small ivory chat bubble sits at the TOP END of the vertical Y axis, and a single small navy clock face sits at the RIGHT END of the horizontal X axis. Do not repeat these glyphs anywhere else.
Explicitly NOT included: no candlestick bars, no column bars, no red or blue rectangles, no grid lines, no plot-area rectangle, no background panel, no extra chat bubbles floating in the empty space.
Negative space stays empty except for exactly two 4-pointed gold sparkle stars in the upper area.
Palette: navy #0B1438, ivory #FBF5EA, gold #D9A84E. Use cobalt #2A4BD7 only as a thin accent inside the tag if needed. No ember.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). Minimal, clean, reads at 64×64.
Output: 1024×1024 PNG, transparent background.
```

#### `K14_wanted_x1` — За витриной 🔵
> Метафора: 1 твоя пластинка в вишлисте ≥3 людей — пластинка на пьедестале за стеклом, три взгляда снаружи.

```text
Generate a soft enamel pin: a single vinyl record on a small pedestal behind a glass display pane, three small silhouetted faces peering in from outside — your record is being eyed.
Composition: center holds a vinyl record (vinyl black, ember center) standing on a small gold pedestal behind an ivory glass pane with a gold frame and a corner shine line; outside the glass at the bottom edge, 3 small navy silhouetted heads looking up at it; small gold heart-eye dots above each head; small "1" in serif gold on the pedestal.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K15_wanted_x5` — Шоурум 🌸
> Метафора: 5 твоих пластинок хотят — выставочный зал: ряд пластинок на подсвеченных стендах, ценники-сердечки.

```text
Generate a soft enamel pin: a showroom display rail of 5 vinyl records on lit stands, each tagged with a small heart price-tag — your shelf is an exhibition.
Composition: a horizontal gold display rail across the middle; on it, 5 small vinyl records standing upright in a row, each on a tiny gold stand with a spotlight dot above; each record has a small rose-pink heart-shaped tag dangling; "5" in serif gold on the rail's left end; add 2 tiny gold sparkle stars above the rail.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `K16_wanted_x10` — Личный Санта 🌸
> Метафора: 10 твоих пластинок хотят — ты Санта: мешок, набитый пластинками, список желаний целого города.

```text
Generate a soft enamel pin: a Santa-style gift sack overflowing with vinyl records, a long unfurling wish-list scroll beside it marked "10" — you are everyone's personal Santa.
Composition: a plump ivory sack tied with a gold cord in the lower-left, overflowing with 4-5 vinyl-record edges (ember and cobalt centers) spilling out the top; to the right, a navy wish-list scroll unfurls downward past the bottom frame with tiny gold checkmark lines and "10" in chunky serif gold at the top; a small gold star on the sack; add 3 tiny gold sparkle stars around the spill.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, cobalt #2A4BD7, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

> Трек «Космос» (`K17`–`K20`, «первым добавил релиз») **выпилен с v2.1** — на ранней базе метрика тривиально true. Промпты удалены; вернём при росте базы (см. [PLAN_ACHIEVEMENTS_V2.md §4.8](PLAN_ACHIEVEMENTS_V2.md)).

> **K8–K10 и K14–K16 переехали в раздел «Вклад» (`contribution`)** — промпты ниже без изменений, но в каталоге это отдельная секция, не «Сообщество».

---

### Серия INV — Глас наружу

#### `INV_first` — Сарафан 💧
> Метафора: первая регистрация по рефералу — силуэт и расходящиеся звуковые волны.

```text
Generate a soft enamel pin: a small silhouette of a person at the center with three concentric sound waves emanating outward — the word-of-mouth begins.
Composition: small navy silhouette of a head-and-shoulders at the center of pin; three concentric gold arcs of increasing radius spreading outward like sound waves; outer-most wave extends slightly past the pin frame; small gold "+1" in serif near the silhouette.
Palette: navy #0B1438, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `INV_three` — Расходится 🔵
> Метафора: 3 регистрации — деревце с 3 ветками, на каждой пластинка-лист.

```text
Generate a soft enamel pin: a small tree with three branches, each branch ending in a tiny vinyl record like a leaf — the invitation tree branching out.
Composition: thin navy tree trunk rising from the bottom center, with three gold branches forking left, right, and upward; at the end of each branch, a small vinyl black mini-record with an ember center; tiny gold roots visible at the base; a small ivory ground line at the bottom.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `INV_ten` — Тренд 🌸
> Метафора: 10 регистраций — ряд силуэтов с облачком нот сверху.

```text
Generate a soft enamel pin: a tight row of 10 small silhouetted heads, with a small cloud of musical notes floating above — the trending invitation.
Composition: 10 small navy head-and-shoulders silhouettes packed in a horizontal row across the middle of pin, alternating slightly in height; above them, a small cluster of 3-4 gold eighth-notes; a thin gold ribbon banner below them reads "10" in serif gold; add 2 tiny gold sparkle stars in the note cluster.
Palette: navy #0B1438, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `INV_active_circle` — Живой круг 🌸
> Метафора: 5 рефералов остаются активными — круг силуэтов, золотой узел в центре.

```text
Generate a soft enamel pin: five silhouetted heads arranged in a circle facing inward, a glowing gold knot at the center — the active living circle.
Composition: 5 navy silhouette heads positioned around a circular arrangement, each facing center; in the very middle, a complex gold celtic-style knot or pulsing dot; thin gold lines connect each silhouette to the center; small "5" in serif gold below the circle; add 2 tiny gold sparkle stars in the corners.
Palette: navy #0B1438, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `INV_chain` — Цепочка 🌌
> Метафора: цепная реакция (привёл того, кто привёл) — 3 силуэта, цепочка между ними.

```text
Generate a soft enamel pin: three silhouetted figures in receding perspective linked by chain links — the multi-generation referral chain.
Composition: three navy head-and-shoulder silhouettes diminishing in size from foreground (largest, left) to background (smallest, right); between each pair of figures, a gold chain link; the chain extends slightly past the right frame; a small gold "→" arrow above the chain; add 3 tiny gold sparkle stars near the back figure.
Palette: navy #0B1438, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `INV_from_showcase` — Из витрины 🔵
> Метафора: гость пришёл через ссылку на витрину профиля.

```text
Generate a soft enamel pin: a small silhouette of a person looking into a shop display window that holds a vinyl record — the visitor came through the showcase.
Composition: rectangular ivory display window in upper 60% of pin with gold frame, vinyl record (vinyl black, ember center) inside on a stand; below and slightly to the side, a small navy silhouette of a person standing on tiptoes looking up at the window; small "+" symbol in gold between the person and window.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия H — Дискография

#### `H1_artist_x5` — Поклонник 💧
> Метафора: 5 пластинок одного артиста — постер-стена, одинаковые лейблы.

```text
Generate a soft enamel pin: a fan-style wall of 5 vinyl records all sharing the same center-label color, arranged like a poster collage — the dedicated fan.
Composition: 5 mini vinyl records arranged in a tile pattern within the pin frame (one centered, four at corners); all 5 have identical ember center labels; each tilted slightly differently; thin gold pushpins at the top of each record; small gold "x5" tag at bottom-right.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `H2_artist_studio_full` — Полная 🌌
> Метафора: все студийные альбомы артиста — корона над стопкой, лавровый венок.

```text
Generate a soft enamel pin: a golden crown atop a tall stack of vinyl records wreathed in a laurel — the complete discography of one artist.
Composition: vertical stack of 6 vinyl records (alternating spines in vinyl black and navy) fills lower 60% of pin; on top, a 5-point gold crown with a small rose-pink jewel in the center; behind the crown, a gold laurel wreath partially encircling; crown extends past the top frame; add 3 tiny gold sparkle stars near the crown.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `H3_master_pressings_3` — Сравнил 🌸
> Метафора: 3+ разных пресса мастера — три «двойника», лупа над одним.

```text
Generate a soft enamel pin: three nearly identical vinyl records side by side with subtle label color differences, a gold magnifying glass hovering over the middle one — comparing master pressings.
Composition: three vinyl records (vinyl black with gold grooves) lined up horizontally; their center labels are subtly different shades — ember, rose pink, ivory; a tilted gold magnifying glass with a handle pointing down-right hovers over the middle (rose pink) record; the glass lens is partly transparent showing magnification effect; add 2 tiny gold sparkle stars near the lens.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `H4_master_pressings_5` — Археолог 🌌
> Метафора: 5 разных прессов — кисточка-щётка, откапывает пластинку из песка.

```text
Generate a soft enamel pin: an archaeologist's brush dusting off a partially buried vinyl record, with a small tag "5" — the deep archaeology of pressings.
Composition: lower half shows ivory sandy ground from which a vinyl record emerges at an angle, half-buried; a gold archaeologist brush from upper-right brushes the record; a tiny gold tag on a string lies on the ground with "5" in serif; small dust particles in gold around the brush; add 3 tiny gold sparkle stars in the air.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `H5_label_x20` — Лейбл-фанат 🌸
> Метафора: 20 пластинок одного лейбла — стопка с одинаковыми лейблами и ярлычком «x20».

```text
Generate a soft enamel pin: a neat stack of 6 vinyl records all with identical ember labels, "x20" engraved on a gold tag on the side — the label devotee.
Composition: stack of 6 vinyls viewed from a 3/4 angle in the lower 65% of pin; all center labels identical ember orange; gold grooves visible; a small gold rectangular tag hangs from the stack with "x20" in serif; above the stack a small gold logo crown; add 2 tiny gold sparkle stars near the tag.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия R — Рандомные пасхалки

> Все скрыты в UI до анлока. Все 🌸 или выше. См. [§5 V2 плана](PLAN_ACHIEVEMENTS_V2.md) для условий.

#### `R_seventy_eight` — Семьдесят восемь 🌸
> Метафора: ровно 78 пластинок — отсылка к 78 RPM, винтажный шеллак.

```text
Generate a soft enamel pin: a vinyl record with "78" in large vintage shellac-era typography on the center label, "RPM" curving below — exactly 78 records collected.
Composition: vinyl record (vinyl black with gold concentric grooves) fills 90% of pin; center label is a rose-pink circle filling 40% of disc; on the label, "78" in chunky vintage gold serif with thick ornamental flourishes; below "78", curved text "RPM" in smaller serif gold; thin gold ring around the label edge; add 2 tiny gold sparkle stars on the disc surface.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_pi` — Число Пи 🌸
> Метафора: ровно 314 пластинок — π в центре, цифры по канавке.

```text
Generate a soft enamel pin: a vinyl record with the Greek letter "π" boldly on the center label, scattered tiny digits "3.14159" along a groove — exactly 314 records.
Composition: vinyl record (vinyl black with gold grooves) at center; rose-pink center label with a large gold serif "π" in the middle; along one of the outer grooves, tiny gold digits "3.14159..." follow the curve; add 2 tiny gold sparkle stars near the π symbol.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_palindrome` — Палиндром 🌸
> Метафора: год-палиндром на пластинке — вертикальная ось симметрии.

```text
Generate a soft enamel pin: a vinyl record with a palindrome year "2002" on the center label, a vertical gold axis of symmetry running through it — the mirror-year.
Composition: vinyl record (vinyl black with gold grooves) centered; rose-pink center label, "2002" in chunky serif gold; a thin gold vertical line bisects the label and continues across the entire pin diameter; small reflective glints on the gold line; add 2 tiny gold sparkle stars on either side of the line.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_time_machine_50` — Полвека спустя 🌸
> Метафора: пластинка добавлена через 50 лет — золотые песочные часы.

```text
Generate a soft enamel pin: a golden hourglass with a vinyl record inside its top bulb, sand flowing down — fifty years later.
Composition: vertical gold hourglass shape fills 80% of pin height; top bulb holds a small vinyl record (vinyl black with ember center); bottom bulb contains rose-pink "sand" piled up; the narrow neck shows a stream of falling gold sand grains; below the hourglass, a small "+50" in serif gold; add 2 tiny gold sparkle stars near the top of the hourglass.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_birth_year` — Ровесник 🌸
> Метафора: пластинка года твоего рождения — пластинка-торт со свечой.

```text
Generate a soft enamel pin: a vinyl record viewed at an angle like a birthday cake, a single lit candle standing on it — the record from your birth year.
Composition: vinyl record tilted in 3/4 perspective (looking down at the top surface) in the lower half of pin; on the top surface, a single thin gold candle with an ember flame extending past the top frame; gold dripping wax on the candle; below the record, a small gold "=" symbol; add 2 tiny gold sparkle stars around the flame.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_new_year` — Первая в году 🌸
> Метафора: добавил пластинку 1 января в полночь — часы 00:00, конфетти.

```text
Generate a soft enamel pin: a clock face showing midnight with hands meeting at 12, a vinyl record below with celebratory confetti — first record of the new year.
Composition: round gold clock face in upper half of pin, navy background, ivory hour-markers; both clock hands pointing straight up to "12"; below the clock, a vinyl record (vinyl black with ember center) tilted slightly; small gold confetti dots flying around the clock and record; the clock partly extends above the top frame; add 2 tiny gold sparkle stars in the confetti.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_friday_night` — Пятничный спин 🌸
> Метафора: пластинка в пятницу ночью — крутящаяся пластинка под месяцем.

```text
Generate a soft enamel pin: a vinyl record spinning under a golden crescent moon, motion lines indicating the Friday night spin.
Composition: lower half of pin shows a vinyl record at an angle (vinyl black, ember center) with three small curved gold motion arrows indicating rotation; upper half shows a gold crescent moon with a small face profile, partly extending past the top frame; small star dots scattered in the navy "sky"; add 2 tiny gold sparkle stars near the moon.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_leap_day` — 29 февраля 🌸
> Метафора: пластинка добавлена 29 февраля — отрывной лист календаря и лягушка-прыгушка.

```text
Generate a soft enamel pin: a tear-off calendar leaf showing "FEB 29" with a small vinyl postage stamp glued to it, a tiny gold leaping frog beside — the leap day.
Composition: ivory calendar leaf occupies the center-left 55% of pin, top corner torn slightly; large "29" in chunky serif gold on the leaf with smaller "FEB" above; in the corner of the leaf, a tiny vinyl-record postage stamp; to the right of the leaf, a small gold frog silhouette in a leaping pose, partly mid-air; add 2 tiny gold sparkle stars above the frog.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_self_aware` — Самосознание 🌸
> Метафора: title содержит «vinyl/record/винил» — пластинка смотрит на отражение.

```text
Generate a soft enamel pin: a vinyl record on the left facing its own reflection in a small round gold-framed mirror on the right — the self-aware record.
Composition: left half of pin holds a vinyl record (vinyl black, ember center) facing right; right half holds a circular gold-framed mirror containing a smaller mirror-image of the same record (same gold grooves, ember center); a thin gold line connects them like a gaze; add 2 tiny gold sparkle stars between them.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_meta_vertushka` — Вертушка 🌸
> Метафора: title/artist содержит «turntable/вертушка» — проигрыватель сверху.

```text
Generate a soft enamel pin: a turntable viewed from above — square chassis, round vinyl on the platter, a diagonal tonearm with cartridge — the "vertushka" itself.
Composition: square navy turntable chassis fills 90% of pin; on it sits a vinyl record (vinyl black with ember center); a gold tonearm angles from upper-right down to the record's outer edge, with a small cartridge head at the tip; thin gold control buttons in the lower-left corner of the chassis; small "33" indicator beside the controls; add 2 tiny gold sparkle stars at the cartridge.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_long_title` — Поэма 🌸
> Метафора: title > 100 символов — развёрнутый свиток-рукопись.

```text
Generate a soft enamel pin: a long unrolled scroll with rows of decorative text strokes, a vinyl record acting as a seal at the bottom — the epic-length title.
Composition: a long ivory parchment scroll unrolled diagonally from upper-left to lower-right, ends curled; on the scroll, 8-10 horizontal rows of small navy strokes (suggesting tiny text); at the bottom of the scroll, a small vinyl record (vinyl black, ember center) acts as a wax seal; scroll ends extend past the upper-left and lower-right frame; add 2 tiny gold sparkle stars on the scroll.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_first_thousand` — Первая тысяча ⚫
> Метафора: User.id в первой 1000 — медаль основателя с лентой.

```text
Generate a soft enamel pin: a founder's medal hanging from a ribbon, "#1K" engraved in the center, surrounded by laurel wreath — among the first thousand.
Composition: a navy ribbon at the top draping down, holding a round gold medal in the center; the medal has rose-pink enamel inside with "#1K" in chunky serif gold; a gold laurel wreath surrounds the "#1K"; ribbon ends extend slightly past the top frame; add 3 tiny gold sparkle stars around the medal.
Palette: navy #0B1438, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_first_hundred` — Первая сотня ⚫
> Метафора: User.id в первой 100 — медаль высшего ранга с короной и двойным венком.

```text
Generate a soft enamel pin: a higher-rank founder's medal with a crown, "#100" engraved, double laurel wreath — among the first hundred legends.
Composition: a small gold crown at the top extending past the top frame; below it, a navy ribbon draping down and around to suspend a round medal; the medal has rose-pink enamel with "#100" in chunky serif gold; surrounding the number, an inner laurel wreath in gold and an outer ring of gold rays; ribbon ends extend past lower edges; add 3 tiny gold sparkle stars around the medal.
Palette: navy #0B1438, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `R_completionist` — Завершитель 🌸
> Метафора: 30+ других ачивок — венок из мини-силуэтов пинов.

```text
Generate a soft enamel pin: a circular wreath made of 12 tiny pin-icon silhouettes (heart, ship, crown, gear, star, key, vinyl, gift box, mic, lightning, torch, medal), with "30+" in serif gold on a rose-pink medallion at the center — the achievement completionist.
Composition: a large round wreath fills 90% of pin; the wreath is composed of 12 small navy-and-gold pin-silhouette icons interlocked in a circle; in the center of the wreath, "30+" in chunky serif gold on a small rose-pink medallion; add 3 tiny gold sparkle stars around the medallion.
Palette: navy #0B1438, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

### Серия META — Выпускные эпики

> Это 🌌-/⚫-«венцы» серий. По образцу `META_foundation` (парусник с флажком «5» в Phase 0) — каждый META имеет уникальный сюжет, отражающий «выпускной» статус.

#### `META_scale` — Фонотека ⚫
> Метафора: все B-достижения собраны — многоэтажный архив-фонотека.

```text
Generate a soft enamel pin: a towering multi-story vinyl archive building, banners draped from the roof, a tall spire on top — the complete phonotheque.
Composition: tall multi-story navy archive building fills 90% of pin height, 4 visible floors with horizontal vinyl-shelf cross-sections in each; gold spire at the top extends past the frame; two rose-pink banners hang from upper corners with gold tassels; small gold "B" badge above the main door; add 3 tiny gold sparkle stars around the spire.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_rarity` — Грааль 🌌
> Метафора: собрал коллекцию редкостей — золотая чаша с восходящей пластинкой.

```text
Generate a soft enamel pin: a golden chalice from which a glowing rare vinyl record rises, the Holy Grail of collecting.
Composition: ornate gold chalice in the lower 50% of pin, ornamental footed cup with rose-pink jewel inset on stem; from the cup's mouth rises a vinyl record (vinyl black with rose-pink center) with a gold radial glow behind it; add 3 tiny gold sparkle stars around the rising record.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_geography` — Атлас 🌌
> Метафора: D3 + 3 из D4-D7 — толстый атлас с глобусом-винилом на обложке, корона.

```text
Generate a soft enamel pin: a thick atlas tome with a vinyl-globe engraved on the cover, topped by a small gold crown — the geography master.
Composition: tall navy atlas book at 80% of pin height; on the cover, a circular engraved emblem of a vinyl-globe (continents in ivory, ocean in vinyl black with gold groove rings); a small gold crown with rose-pink jewel rests on top of the book extending past the top frame; gold corner ornaments on the book; add 3 tiny gold sparkle stars around the crown.
Palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_eras` — Век винила ⚫
> Метафора: по пластинке из каждой декады 1950-2020 — горизонтальный таймлайн.

```text
Generate a soft enamel pin: a long horizontal timeline ribbon with 8 vinyl-record markers spanning "1950 → 2020", a small crown over the middle — the century of vinyl.
Composition: a gold ribbon horizontally curves across the entire pin, ends extending past left and right frame edges; along the ribbon, 8 small vinyl records at even intervals, each in a slightly different label color (ember, ivory, cobalt, rose pink, navy, ember, ivory, cobalt soft); above the middle, a small gold crown; below the ribbon, "1950 → 2020" in tiny serif gold; add 3 tiny gold sparkle stars above the crown.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, ivory #FBF5EA, cobalt #2A4BD7, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_genres` — Эрудит 🌌
> Метафора: собрал по жанрам + 3 жанровых мастер-серии — пластинка в венке из инструментов.

```text
Generate a soft enamel pin: a central vinyl record surrounded by a wreath of 6 musical instruments — sax, guitar, synth keys, violin, drum, treble clef — the polymath of genres.
Composition: vinyl record (vinyl black, rose pink center) at exact center of pin, 50% diameter; surrounding it, 6 small gold instrument silhouettes arranged in a circle (top: treble clef, top-right: saxophone, bottom-right: synth keyboard, bottom: drum, bottom-left: violin, top-left: guitar); thin gold connecting lines between instruments forming a wreath; add 3 tiny gold sparkle stars around the wreath.
Palette: navy #0B1438, vinyl black #1A1A2E, rose pink #E89AC0, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_gifts` — Щедрость 🌌
> Метафора: ядро серии (J2+J3+J4+J5) — рог изобилия с подарками.

```text
Generate a soft enamel pin: a golden cornucopia spilling wrapped gifts and vinyl records — the generosity master.
Composition: tilted gold cornucopia horn opens to the right, narrow end in lower-left, wide opening upper-right extending past frame; from the opening pour out: 2 small wrapped gift boxes (cobalt and ember), 1 vinyl record (vinyl black with ember center), and a curling ribbon; gold ornamental ridges on the horn; add 3 tiny gold sparkle stars in the spill.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, cobalt #2A4BD7, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_community` — Резидент 🌌 ✅ отрисован
> Метафора: K4 + K7 + K13 — ключ от клуба, бородка собрана из трёх глифов трёх веток. Без свечения: любой halo мешает вырезать альфу.

```text
Generate a soft enamel pin: an ornate club key held upright, its bit shaped from three interlocking symbols — a marquee bulb, a lanyard clip and a ticker tape curl — the master key to the community.
Composition: one bold vertical antique key fills ~70% of the pin, shaft in gold with a navy inlay stripe; the bow (top ring) is a vinyl record — vinyl black with gold groove rings and an ember center label; the bit at the bottom is built from three distinct gold teeth, each a miniature glyph: a round marquee bulb, a small lanyard clip, and a curled ticker tape; a small ivory enamel banner crosses the shaft reading "RESIDENT" in chunky vintage serif navy; four 4-pointed gold sparkle stars of varying size float around the key, one overlapping the bow.
Background: NOTHING behind the key. No glow, no halo, no aura, no radial gradient, no colored disc or oval, no soft light, no blur of any kind. The area around the key silhouette must be 100% empty transparent alpha, hard-edged, so the pin can be cut out cleanly. Every visible element must be a solid enamel shape with a crisp gold or navy outline.
Palette: navy #0B1438, cobalt deep #0E1A52, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone). No frame, no background rectangle, no drop shadow.
Output: 1024×1024 PNG, fully transparent background.
```

#### `META_evangelist` — Эпидемия ⚫
> Метафора: INV_ten + INV_active_circle + INV_chain — взлетающая ракета с шлейфом-пластинками.

```text
Generate a soft enamel pin: a rising rocket leaving a trail of 3 vinyl-record markers, a small crowd of silhouetted heads at the base — the evangelism epidemic.
Composition: gold rocket diagonal from lower-left to upper-right, nose extending past upper-right frame; behind it, a thinning gold smoke trail with 3 small vinyl record markers along it (vinyl black with ember centers); at the rocket base bottom-left, 6 tiny navy silhouetted heads in a small crowd cheering up; add 3 tiny gold sparkle stars in the smoke trail.
Palette: navy #0B1438, vinyl black #1A1A2E, ember #E85A2A, ivory #FBF5EA, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

#### `META_depth` — Учёный ⚫
> Метафора: H2 + H4 + H5 — мудрая сова на стопке альбомов, перо в когте.

```text
Generate a soft enamel pin: a stylized wise owl perched on a stack of vinyl albums, holding a quill — the scholar of music.
Composition: stack of 3 vinyl albums in lower half of pin in navy, ivory, vinyl black with gold spines; perched on top, a stylized owl silhouette in navy with large gold round eyes and a small gold beak; one talon holds a gold quill pen extending past the right frame; the owl's head extends slightly past the top frame; add 3 tiny gold sparkle stars around the owl.
Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, ember #E85A2A, gold #D9A84E.
Same enamel pin style as the previous Vertushka pins (gold contour, navy outline, recessed enamel, single specular per zone).
Output: 1024×1024 PNG, transparent background.
```

---

## Фразы для итерации

Если пин получился не так — НЕ начинай новый чат. Пиши в том же диалоге одну из этих фраз. Nano Banana 2 итерирует над последней генерацией.

| Проблема | Что написать |
|---|---|
| Слишком фотореалистично | `Make the rendering flatter — less photo-realistic, more flat illustrated enamel. Remove any depth-of-field or glossy 3D look.` |
| Появился drop shadow | `Remove the drop shadow under the pin. The background must be fully transparent alpha — no shadow, no glow outside the pin.` |
| Цвет уехал в сторону | `Keep the composition, but redo the colors using only this strict palette: navy #0B1438, ivory #FBF5EA, vinyl black #1A1A2E, ember #E85A2A, gold #D9A84E, rose pink #E89AC0 (rare only), cobalt #2A4BD7. No other colors allowed.` |
| Нет золотого канта | `The pin is missing its raised gold metal contour ring around the outer edge. Add a gold #D9A84E rim, about 3-4% of pin area, with a thin dark navy outline just outside it.` |
| Пин слишком круглый/одинаковый | `The silhouette is too plain. Let part of the design extend beyond the square frame — [укажи что: the ship's mast / the window shutter / the ribbon ends / the rays].` |
| Маленькие детали не читаются | `Simplify the small details. Make the main central figure bolder and larger — about 55-60% of pin area. The pin must be recognizable at 64×64 pixels.` |
| Нет sparkle для редкого | `Add 2-3 tiny 4-pointed gold sparkle stars somewhere inside the pin as a rarity marker. Each star about 3-4% of pin diameter.` |
| Появился текст где не надо | `Remove all text from the pin except for the meaningful number/symbol "[X]". No captions, no labels, no watermarks.` |
| Не прозрачный фон | `The background is not transparent. Output a PNG with full alpha channel — pin floating on absolute transparency, no rectangular background of any color, no card frame.` |

---

## Verification

### Что проверить у каждого пришедшего PNG

1. **Прозрачный фон.** Открой в Preview, посмотри alpha. Не должно быть бежевой/белой подложки за пином.
2. **64 px читаемость.**
   ```bash
   sips -Z 64 _raw/PIN.png --out /tmp/PIN_64.png && open /tmp/PIN_64.png
   ```
   Узнаётся ли метафора? Если сваливается — итерационная фраза «Simplify the small details».
3. **Палитра.** Никаких чужих цветов (фиолетовый, бирюза). Если уехал — итерационная фраза «Keep the composition, but redo the colors using only this strict palette».
4. **Sparkle для 🌸+.** На пинах 🌸, 🌌, ⚫ должны быть 2-3 микро-искры. Если их нет — «Add 2-3 tiny gold sparkle stars».
5. **Тир-нейтральность.** Мысленно положи за пин ауру каждого тира (#A5C8E1 / #5B7DD8 / #E89AC0 / #1B237D / #0A0A1A). Пин не должен сливаться ни с одной — это значит, что палитра выбрана правильно.

### Sizing pipeline

Когда есть 5-10 PNG в `Mobile/assets/achievements/_raw/`:

```bash
cd Mobile/assets/achievements
for f in _raw/*@2x.png; do
  name=$(basename "$f" @2x.png)
  [ -f "700/$name.png" ] && continue
  sips -Z 700 "$f" --out "700/$name.png" >/dev/null
  sips -Z 256 "$f" --out "256/$name.png" >/dev/null
  sips -Z 64  "$f" --out "64/$name.png"  >/dev/null
  echo "✓ $name"
done
```

### Подключение к коду

В `Mobile/components/achievement-scenes/index.tsx` уже есть helper `makeImageScene(src)` (см. `SceneCircumnavigation` как референс). Для каждого нового PNG-пина:

```tsx
// Где-то перед REGISTRY:
export const SceneArchivist: SceneRendererImpl = makeImageScene(
  require('../../assets/achievements/256/B3_archivist.png'),
);

// В REGISTRY:
B3_archivist: SceneArchivist,
```

### Полнота покрытия

После того как заберёшь N PNG из Nano Banana и положишь в репо — прогони diff:

```bash
# Все коды из V2 плана (минус Phase 0 и D3):
grep -oE '`[A-Z][0-9A-Z_]*`' docs/plans/PLAN_ACHIEVEMENTS_V2.md | sort -u > /tmp/codes_v2.txt

# Коды, для которых есть финальный PNG-ассет:
ls Mobile/assets/achievements/_raw/*@2x.png 2>/dev/null \
  | xargs -n1 basename | sed 's/@2x.png//' | sort -u > /tmp/codes_done.txt

# Что осталось:
comm -23 /tmp/codes_v2.txt /tmp/codes_done.txt
```

В этом списке должны постепенно исчезать строки, по мере того как ты добавляешь PNG.

### Smoke-test workflow на одном пине

Перед тем как идти по всему списку — попробуй один:

1. Открой Nano Banana 2, вставь STYLE PREAMBLE.
2. Скопируй промпт `A5_second_collection` (это первый и самый простой пин в доке).
3. Получи PNG, сохрани как `Mobile/assets/achievements/_raw/A5_second_collection@2x.png`.
4. Открой в Preview — прозрачный ли фон, читается ли при 64 px?
5. Если ок — workflow рабочий, иди по списку.
6. Если нет — итерируй в чате (см. фразы) и калибруй preamble под Nano Banana под себя.

---

## Открытые вопросы / на потом

- **Шрифты внутри пина.** Цифры «10», «50», «100», «33⅓», «78» — Nano Banana 2 рендерит их неплохо, но не идеально. Если конкретный пин получился с кривой цифрой — можно после генерации добавить цифру руками в Figma поверх (или попросить SVG-генерацию отдельно для цифры).
- **share-card 700 px.** Сейчас для UI используется 256 PNG. Когда дойдём до share-card — может понадобиться 700 источник + size-aware helper в `makeImageScene`.
- **pngquant.** Для оптимизации веса бандла — `brew install pngquant`, потом батчем по `64/256/700/`. Не критично сейчас.
- **Locked-стейт.** Сейчас просто `opacity: 0.32`. Если визуально слабо — заменим на настоящий desaturate-фильтр через `expo-image` (отдельная задача).
