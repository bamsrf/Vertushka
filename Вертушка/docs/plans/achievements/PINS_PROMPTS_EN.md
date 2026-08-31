# Achievement pin prompts — 73 missing visuals (EN)

Каждый промт самодостаточный: материал, палитра, тир, силуэт, размер и негативы вшиты внутрь.
Общий преамбул не нужен — копируй блок целиком в генератор.

Соответствие кодов: `Backend/app/services/achievements/definitions/`.
Готовые визуалы лежат в `Mobile/assets/achievements/designs/`, вектор — в `pins/`.

Тир → маркер редкости внутри пина:
- 💧 Simple / 🔵 Notable — без искр
- 🌸 Rare — 2 золотые искры
- 🌌 Epic — 3 искры + индиго-акцент
- ⚫ Legend — 3 искры + двойной золотой кант

---

## Collection size (B)

### `B6_warden` — «Смотритель» (Legend ⚫)

```text
Generate a soft enamel pin: a keyring where every key is cut from a vinyl record — the collection outgrew its owner, now you are its warden.

Composition: three keys hang overlapping from one thick gold split-ring at the top. Each key has a shaft and a notched bit carved out of a record's edge, and its bow (head) is a record's center label — a small ember circle with a white spindle dot. Behind the keys, a vault door reads as two vertical navy lines closed by an arch, opened a hand's width; a narrow ivory wedge of warm light spills from the gap and falls behind the keys. Flat enamel only, no perspective box, no 3D metal.

Palette: navy #0B1438, vinyl black #1A1A2E, ivory #FBF5EA, ember #E85A2A, gold #D9A84E.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Legend tier: add 3 tiny gold four-point sparkles and a second gold rim tracing the whole silhouette. Silhouette: the split-ring breaks past the top edge, the lowest key past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no drop shadows, no gradient mesh.
```

---

## Rarity (C)

### `C1_limited_x5` — «Тираж ограничен» (Simple 💧)

```text
Generate a soft enamel pin: a vinyl record torn off a roll like a ticket stub — the press run is finite and you took one of the few.

Composition: one bold record fills the pin, but its left edge is not round — it is a straight perforated tear line with a row of punched holes, as if the disc were ripped off a strip of tickets. A narrow sliver of the neighboring disc is still attached beyond the perforation, cut off by the frame. The record's center label carries a raised gold oval seal with a blank ember field inside — a stamp shape, no letters. Everything flat, no paper curl, no perspective.

Palette: vinyl black #1A1A2E (record), gold #D9A84E (grooves, perforation holes, seal), ember #E85A2A (label), ivory #FBF5EA (torn strip sliver), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the perforated edge and the attached sliver break past the left edge.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no background, no frame, no drop shadows, no paper texture.
```

### `C4_collectible_x5` — «Энтомолог» (Rare 🌸)

```text
Generate a soft enamel pin: five butterflies pinned in a specimen case, their wings cut from vinyl records — rarity as a captured species.

Composition: a shallow rectangular specimen case seen straight on, slim gold frame, glass front marked by one long diagonal white streak. Inside, five butterflies are mounted in a loose grid, each with its wings made from two half-discs of vinyl: the curved outer edge of the record forms the wing's outer edge, and the concentric grooves fan across the wings like markings. Every butterfly is impaled by a straight pin with a small round gold head, and the pins are the only rigid verticals in the composition. One butterfly is noticeably larger than the rest, centered.

Palette: vinyl black #1A1A2E (wings) with gold #D9A84E grooves, pink #E89AC0 (wing markings on the largest one), navy #0B1438 (case backing, bodies), ivory #FBF5EA (case mat), gold (frame, pin heads), cobalt soft #5C7AE8 (glass streak).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the case frame breaks past both side edges, the largest butterfly's wingtips past the top.

Output: 1024×1024 PNG, transparent background. No text, no labels, no realistic insect anatomy, no background, no frame beyond the case itself.
```

### `C7_hot_in_collection` — «Тренд на полке» (Rare 🌸)

```text
Generate a soft enamel pin: a frying pan flipping a vinyl record through the air like a pancake — this one is hot right now.

Composition: a frying pan seen from the side in the lower left, its long handle running down to the lower-left corner, the pan's mouth tilted up and to the right as if it has just thrown. Above it, one vinyl record is caught mid-flip in the air, tipped to a steep angle so it reads as a disc in motion rather than a flat circle — its center label clearly visible. Two curved gold motion arcs trace the arc of the throw from the pan's lip up to the record. Three small heat wisps curl up from inside the empty pan.

Palette: navy #0B1438 (pan body and handle), gold #D9A84E (pan rim, motion arcs, grooves), vinyl black #1A1A2E (record), ember #E85A2A (center label, heat wisps), ivory #FBF5EA (one highlight streak on the pan).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the pan handle breaks past the lower-left corner, the flipping record past the top edge.

Output: 1024×1024 PNG, transparent background. No text, no food, no flames, no stove, no background, no frame, no motion blur.
```

### `META_rarity` — «Грааль» (Epic 🌌)

```text
Generate a soft enamel pin: a tonearm driven into a stone like a sword — the grail goes to whoever can reach it, not whoever can pay.

Composition: a rough boulder sits across the lower third of the pin, flat-topped and blocky. Rising vertically out of it, driven deep, is a tonearm standing in for the sword: its stylus buried in the rock, its slim shaft rising straight up, its counterweight forming the pommel at the top and the headshell forming the crossguard. Where the shaft meets the stone, a crack splits the rock and a wedge of light escapes. Behind the whole thing, five straight gold rays fan upward.

Palette: navy #0B1438 (stone) with gold #D9A84E facet lines, gold (tonearm, rays), indigo #1B237D (light in the crack), ember #E85A2A (a small jewel set in the counterweight), ivory #FBF5EA (one highlight face on the stone).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles and one indigo accent inside the piece. Silhouette: the counterweight pommel breaks past the top edge, the outer rays past both sides.

Output: 1024×1024 PNG, transparent background. No text, no actual sword blade, no background, no frame, no religious iconography.
```

---

## Geography (D)

### `D1_country_x5` — «Космополит» (Simple 💧)

```text
Generate a soft enamel pin: an open passport whose pages are a record sleeve, stamped by five countries.

Composition: a passport opened flat, spine down the middle, both halves shaped like the two sides of a split record sleeve. Across the spread, five round entry stamps overlap at angles — each stamp is a micro record: a circle with a gold rim and a single center dot, no lettering. The outer page corners curl outward.

Palette: cobalt #2A4BD7 (cover), ivory #FBF5EA (pages), ember #E85A2A and navy #0B1438 (stamps, alternating), gold #D9A84E.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the curled page corners break past the left and right edges.

Output: 1024×1024 PNG, transparent background. No text, no letters, no flags, no background, no frame.
```

### `D2_country_x15` — «Глобус» (Notable 🔵)

```text
Generate a soft enamel pin: a desk globe whose sphere is a vinyl record — the world already spins on your table.

Composition: a globe held in a curved gold meridian arc on a small navy base. The sphere is a record: its parallels are concentric vinyl grooves, its meridians are thin gold lines, and four irregular blobs stand in for continents. Where the north pole would be sits a record's center label and spindle dot.

Palette: vinyl black #1A1A2E (sphere), cobalt soft #5C7AE8 (continents), ember #E85A2A (pole label), navy #0B1438 (base), gold #D9A84E (arc, meridians, grooves).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the meridian arc breaks past the left edge, the base past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no real world map, no background, no frame.
```

### `D7_german_x10` — «Made in Germany» (Rare 🌸)

```text
Generate a soft enamel pin: a beer stein whose hinged lid is a vinyl record — Oktoberfest, where the German pressing is served by the litre.

Composition: one tall beer stein dominates the pin, seen from the side, its handle curling out to the left. Its hinged pewter lid is a vinyl record — a black disc with gold grooves and a center label — tipped open on a gold thumb-lever so it reads as a lid, not a floating circle. A thick ivory foam head swells over the rim and one blob of it runs down the side. Leaning against the stein's foot, a soft pretzel whose twisted loops echo the curve of a groove.

Palette: cobalt #2A4BD7 (stein body) with an ivory #FBF5EA panel, ivory (foam), gold #D9A84E (lid hinge, thumb-lever, rim, grooves, pretzel), vinyl black #1A1A2E (record lid), ember #E85A2A (center label), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the open record-lid breaks past the top edge, the handle past the left, the pretzel past the bottom-right.

Output: 1024×1024 PNG, transparent background. No text, no flags, no hats, no faces, no background, no frame, no liquid photorealism.
```

### `META_geography` — «Атлас» (Epic 🌌)

```text
Generate a soft enamel pin: a closed atlas whose embossed compass rose is built from tonearms.

Composition: a thick closed volume seen from slightly above, lying flat. On its cover, an embossed compass rose whose center is a record's label and whose eight rays are tonearms of alternating length, each ending in a stylus tip. Five gold ribbon bookmarks slip out from the fore-edge of the pages.

Palette: indigo #1B237D (binding), gold #D9A84E (embossing, rose, ribbons), ember #E85A2A (center label), ivory #FBF5EA (page edges), cobalt #2A4BD7 (two of the ribbons).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: two ribbons hang past the bottom edge, one compass ray breaks past the right.

Output: 1024×1024 PNG, transparent background. No text, no letters, no background, no frame.
```

---

## Eras (E)

### `E6_decade_full` — «Десятилетие» (Epic 🌌)

```text
Generate a soft enamel pin: one full revolution of a record — a decade closed with no year skipped.

Composition: a record face-on, and around it a bold gold arrow that has traveled the entire circle and come back to where it began — its arrowhead almost touching its own tail, the gap deliberately tiny. Around the rim sit ten evenly spaced tick marks, every one of them struck through with a small gold bar, so the ring of ticks reads as complete. At the start point, one short flag marks where the turn began and ended.

Palette: vinyl black #1A1A2E (record), gold #D9A84E (revolution arrow, ticks, flag), indigo #1B237D (field inside the groove band), ember #E85A2A (center label), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles and one indigo accent inside the piece. Silhouette: the revolution arrow is wider than the record and breaks past both side edges.

Output: 1024×1024 PNG, transparent background. No digits, no text, no calendar, no background, no frame.
```

### `META_eras` — «Век винила» (Legend ⚫)

```text
Generate a soft enamel pin: the phases of the moon, but every moon is a vinyl record — one object carried through eight decades.

Composition: eight discs arranged in a wide arc across the pin, rising from the lower left, cresting at the top center, descending to the lower right. Each disc is a record, and each shows a different lunar phase: a thin crescent at the far left, waxing through half and gibbous, a full record at the crest of the arc with its grooves and center label fully visible, then waning back to a crescent at the far right. The lit part of every disc is rendered as vinyl with gold grooves; the dark part is flat and empty. The crest disc is the largest, the end ones smallest.

Palette: lit vinyl black #1A1A2E with gold #D9A84E grooves, dark parts #0A0A1A, center label on the full disc ivory #FBF5EA, a thin gold rim on every disc, navy #0B1438 outline.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Legend tier: add 3 tiny gold four-point sparkles and a second gold rim tracing the whole silhouette. Silhouette: the end discs of the arc break past both side edges, the crest disc past the top.

Output: 1024×1024 PNG, transparent background. No text, no dates, no stars, no sky, no background, no frame.
```

---

## Genres (F)

### `F1_diversity_5` — «Разносторонний» (Simple 💧)

```text
Generate a soft enamel pin: five sleeves fanned like playing cards — taste starting to open up.

Composition: five square record sleeves fanned from one point at the bottom, overlapping evenly. Each sleeve carries one single-stroke gold genre glyph: a wave, a trumpet bell, a violin scroll, a lightning bolt, and a plain note. Glyphs are line drawings, no letters. Thin gold hairlines separate the overlapping sleeves.

Palette: sleeves alternate cobalt #2A4BD7, ivory #FBF5EA, cobalt soft #5C7AE8, navy #0B1438, and one ember #E85A2A; glyphs gold #D9A84E.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the outermost sleeves break past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no drop shadows.
```

### `F5_classical_x15` — «Классик» (Rare 🌸)

```text
Generate a soft enamel pin: a mechanical metronome whose swinging weight is a vinyl record — classical music keeps its own time.

Composition: a classic pyramid metronome seen straight on, its tall tapering body filling the pin, front panel open. A slim pendulum rod rises from the base and tilts to the right; the sliding weight on that rod is a vinyl record, seen edge-tilted so its grooves and center label read clearly. Two faint gold arc strokes behind the rod show the swing it just made. The base is a plain plinth with a small gold winding key at the side.

Palette: navy #0B1438 (metronome body) with gold #D9A84E edge trim, ivory #FBF5EA (open front panel), vinyl black #1A1A2E (weight-record) with a pink #E89AC0 label, gold (rod, swing arcs, winding key, scale ticks on the panel).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the pendulum rod with its record breaks past the top-right edge, the plinth past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no sheet music, no background, no frame.
```

### `F6_rock_x25` — «Громко» (Rare 🌸)

```text
Generate a soft enamel pin: a guitar cabinet whose speaker is a vinyl record, volume knob pinned to maximum.

Composition: a rectangular amp cabinet seen straight on. Its grille is a woven ivory mesh, and the speaker behind it is a record — concentric groove circles with a center label. Three pairs of sound-wave arcs push outward left and right from the grille. One gold volume knob on the front panel is turned hard right, its pointer at the last tick.

Palette: navy #0B1438 (cabinet), ivory #FBF5EA (grille mesh), vinyl black #1A1A2E (speaker), ember #E85A2A (speaker label), pink #E89AC0 (label ring), gold #D9A84E (waves, knob, corners).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer wave arcs break past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no brand marks, no background, no frame.
```

### `META_genres` — «Эрудит» (Epic 🌌)

```text
Generate a soft enamel pin: a library card-catalog drawer of genres, with one card escaping upward.

Composition: a card catalog drawer seen at a three-quarter angle, pulled open one tier. Inside stand tightly packed divider cards with gold index tabs, each tab carrying one single-stroke genre glyph (wave, trumpet bell, violin scroll, lightning bolt, plain note). Above the drawer, one card floats free in the air, and instead of a glyph it carries a small record with a center label. A gold pull handle sits on the drawer front.

Palette: indigo #1B237D (drawer), ivory #FBF5EA (cards), gold #D9A84E (tabs, glyphs, handle), cobalt #2A4BD7 (floating card), ember #E85A2A (its label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the floating card breaks past the top edge, the handle past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no letters, no background, no frame.
```

---

## Formats — cross-format (FMT)

### `FMT1_beyond_vinyl` — «За пределами винила» (Simple 💧)

```text
Generate a soft enamel pin: a record whose right quarter tears away and becomes a cassette — the first step outside the groove.

Composition: a record face-on. Along a vertical stepped tear line just right of center, the disc's round geometry breaks into the square geometry of a compact cassette: left of the tear, concentric gold grooves and a center label; right of it, a cassette corner with two reels and a rectangular window. The tear itself is a jagged gold seam of four steps.

Palette: vinyl black #1A1A2E (vinyl half), ember #E85A2A (center label), cobalt #2A4BD7 (cassette shell), ivory #FBF5EA (cassette window), gold #D9A84E (grooves, reels, seam).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the cassette corner breaks past the right edge, the record rim past the left.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `FMT2_multiformat` — «Мультиформат» (Notable 🔵)

```text
Generate a soft enamel pin: three formats holding a triangle, no argument between them.

Composition: an equilateral triangular arrangement. At each vertex, one media object turned edge-in toward the center: a vinyl record (circle with grooves), a compact cassette (rectangle with two reels), a CD (thin disc with one rainbow arc). At the exact geometric center, a small gold node joins them with three short straight gold links.

Palette: vinyl black #1A1A2E, cobalt #2A4BD7 (cassette), ivory #FBF5EA (CD) with one thin ember #E85A2A arc, navy #0B1438 (outline), gold #D9A84E (links, node, rims).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the three vertices break past three sides of the frame.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `FMT3_all_formats` — «Всеформатный» (Rare 🌸)

```text
Generate a soft enamel pin: a pocket knife whose four blades are the four formats — one tool, every medium.

Composition: a folding multi-tool seen flat, its handle horizontal across the lower half of the pin, all four tools swung open and fanned upward from the same pivot. Instead of blades: a vinyl record on a short stem, a compact cassette, a compact disc, and a boxset — each one shaped as if it were a blade hinged at the handle. A single gold rivet marks the pivot where all four meet. The handle is plain and unadorned so the fan reads instantly.

Palette: handle navy #0B1438 with gold #D9A84E bolsters and rivet; vinyl black #1A1A2E (record) with a pink #E89AC0 label; cobalt #2A4BD7 (cassette); ivory #FBF5EA (CD) with one thin ember #E85A2A arc; indigo #1B237D (boxset).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer two blades break past the top-left and top-right edges, the handle past both sides.

Output: 1024×1024 PNG, transparent background. No text, no brand marks, no background, no frame.
```

### `META_formats` — «Без предрассудков» (Epic 🌌)

```text
Generate a soft enamel pin: an apothecary balance in perfect equilibrium — vinyl on one pan, everything else on the other.

Composition: a two-pan balance scale, beam dead level, pointer exactly centered. Left pan holds a stack of records; right pan holds a cassette, a CD and a boxset stacked together. The upright post is a tonearm with its counterweight forming the base. Thin gold chains connect beam to pans.

Palette: gold #D9A84E (beam, post, chains), ivory #FBF5EA (pans), vinyl black #1A1A2E with ember #E85A2A labels (left stack), cobalt #2A4BD7 and indigo #1B237D (right stack), navy #0B1438 (base).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: both beam ends with their chains break past the side edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

---

## Formats — cassettes (T)

### `T1_first_tape` — «Перемотка» (Simple 💧)

```text
Generate a soft enamel pin: a cassette with a pencil stuck in its reel — rewinding by hand again.

Composition: a compact cassette face-on. A hexagonal pencil is inserted into the left reel hub, angled like a crank handle, its sharpened tip pointing down-left. One circular arrow wraps around the pencil to show the turning direction. Between the two reels the tape sags in a soft downward curve.

Palette: cobalt #2A4BD7 (shell), ivory #FBF5EA (window), vinyl black #1A1A2E (tape), ember #E85A2A (pencil body) with a gold tip, gold #D9A84E (reels, arrow).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the pencil breaks past the left and top edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `T2_tapes_x10` — «Микстейп» (Simple 💧)

```text
Generate a soft enamel pin: a hand-labeled mixtape — the era of homemade selections.

Composition: a compact cassette face-on. Its paper label is handwritten: three uneven wavy gold strokes standing in for a tracklist, no actual letters. A small heart sticker is pasted onto the shell slightly crooked, one corner already peeling up. Two reel hubs and a rectangular window complete the shell.

Palette: ivory #FBF5EA (shell), cobalt soft #5C7AE8 (label), gold #D9A84E (handwriting strokes, reels), #E55B7A (heart sticker), navy #0B1438 (hubs, outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the peeling sticker corner breaks past the top edge.

Output: 1024×1024 PNG, transparent background. No text, no real handwriting, no background, no frame.
```

### `T3_tapes_x25` — «Хром и металл» (Notable 🔵)

```text
Generate a soft enamel pin: three cassettes of three different tape formulations, fanned.

Composition: three compact cassettes overlapping in a shallow fan. The rearmost shell is matte and plain; the middle one is chrome, marked by one diagonal white streak; the front one is metal, marked by two parallel white streaks. On the front cassette's face sits a three-segment tape-type indicator: three small squares in a row, only the third filled solid.

Palette: shells navy #0B1438, ivory #FBF5EA, cobalt #2A4BD7; tape inside vinyl black #1A1A2E; windows, reels and indicator gold #D9A84E.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the outer cassettes break past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `T4_tapes_x50` — «Эпоха Walkman» (Rare 🌸)

```text
Generate a soft enamel pin: a portable cassette player with one foam earpiece that is secretly a record.

Composition: a pocket cassette player seen straight on, its clear lid flipped open to reveal a cassette loaded inside. A coiled cable rises from the top right of the body and ends in a single round foam earpiece drawn as a micro record — a dark disc with a center label.

Palette: navy #0B1438 (body) with gold #D9A84E buttons, cobalt soft #5C7AE8 (translucent lid), ivory #FBF5EA (cassette), vinyl black #1A1A2E (earpiece) with a pink #E89AC0 label, gold (cable).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the cable and earpiece break past the upper-right corner.

Output: 1024×1024 PNG, transparent background. No text, no brand marks, no background, no frame.
```

---

## Formats — CDs

### `CD1_first_cd` — «Лазер включён» (Simple 💧)

```text
Generate a soft enamel pin: a laser beam replacing the stylus on a compact disc.

Composition: a CD seen at a three-quarter tilt. From the lower right, a thin straight beam strikes a single point on its data surface at a sharp angle; at the contact point sits a gold four-point spark. One broad rainbow arc — three parallel bands — sweeps across the disc's face. A clean center hole with a ring.

Palette: ivory #FBF5EA with a pale blue #A5C8E1 sheen (disc), rainbow arc in ember #E85A2A, cobalt #2A4BD7, cobalt soft #5C7AE8; navy #0B1438 (center ring); gold #D9A84E (beam, spark).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles beyond the contact spark. Silhouette: the beam breaks past the lower-right corner.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no lens flare.
```

### `CD2_cds_x25` — «Jewel Case» (Simple 💧)

```text
Generate a soft enamel pin: a jewel case with the crack it always had.

Composition: a CD jewel case at a three-quarter angle, lid hinged open about 30 degrees. Inside, a disc sits on its rosette hub; behind it a plain inlay card. Across the lid runs the era's signature crack — a single jagged gold polyline of three segments.

Palette: cobalt soft #5C7AE8 (translucent plastic), ivory #FBF5EA (inlay, disc) with one ember #E85A2A arc, gold #D9A84E (hub rosette, crack, hinge), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the open lid breaks past the right edge.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `CD3_cds_x100` — «Серебряная полка» (Notable 🔵)

```text
Generate a soft enamel pin: a shelf that turned silver — a hundred jewel cases in a row.

Composition: a horizontal run of about twelve thin jewel-case spines standing flush against each other on a solid base, seen straight on, separated by 1px gold hairlines. Above the row, one disc has been pulled out and stands upright on its edge, catching a wide white crescent of reflected light.

Palette: spines alternate ivory #FBF5EA, pale blue #A5C8E1, cobalt soft #5C7AE8; base navy #0B1438; standing disc ivory with one ember #E85A2A arc; gold #D9A84E hairlines and rims.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the standing disc breaks past the top edge.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `CD4_cds_x250` — «Ярче павлина» (Rare 🌸)

```text
Generate a soft enamel pin: a peacock whose tail eyes are compact discs — the format everyone kept burying, standing there showing off.

Composition: a peacock seen from the front, its body small and low in the pin, its fanned tail filling everything above and behind it. The tail is a wide semicircular fan of slim feather stems, and at the tip of each stem sits a compact disc standing in for the eye of the feather — a pale silver circle with a visible center hole and one short rainbow arc across it. Nine discs sit along the fan, larger toward the center of the arc. The bird's body is a simple teardrop with a slender neck, a small crest of three thin plumes on its head, and no facial detail beyond one dot for the eye.

Palette: cobalt #2A4BD7 (body and neck) with an indigo #1B237D shadow side, gold #D9A84E (feather stems, crest, disc rims, beak), ivory #FBF5EA with a pale blue #A5C8E1 sheen (discs), ember #E85A2A and pink #E89AC0 (short rainbow arcs on the discs), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer feather stems break past both side edges, the crest past the top.

Output: 1024×1024 PNG, transparent background. No text, no realistic feather barbs, no background, no frame, no photographic iridescence.
```

---

## Formats — boxsets (BX)

### `BX1_first_box` — «Распаковка» (Notable 🔵)

```text
Generate a soft enamel pin: a boxset mid-unboxing — not a purchase, an event.

Composition: a boxset seen at a three-quarter angle with its lid lifted off, the lid floating slightly above and to the right of the base. From the open box protrude the top edges of three record sleeves and the corner of a booklet. Three short gold dashes fill the gap between lid and base to read as air.

Palette: navy #0B1438 (box) with gold #D9A84E edge trim, cobalt #2A4BD7 (lid), ivory #FBF5EA (sleeves), ember #E85A2A (booklet spine), gold (dashes).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the floating lid breaks past the upper-right corner.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no motion blur.
```

### `BX2_boxes_x5` — «Полка ломится» (Rare 🌸)

```text
Generate a soft enamel pin: a shelf visibly bowing under five boxsets.

Composition: a horizontal shelf board on two wall brackets, seen straight on. Five thick boxsets stand on it edge-on, packed tight. The board sags in a clear downward arc under their weight and the brackets flex slightly outward. One short stress line sits under the deepest point of the sag.

Palette: ivory #FBF5EA (board), gold #D9A84E (brackets, spine embossing), boxes in navy #0B1438, cobalt #2A4BD7, indigo #1B237D, vinyl black #1A1A2E, cobalt soft #5C7AE8; one pink #E89AC0 spine.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: both ends of the shelf break past the side edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `BX3_boxes_x15` — «Хранилище делюксов» (Epic 🌌)

```text
Generate a soft enamel pin: a vault rack of deluxe boxsets, one drawer glowing.

Composition: a riveted storage rack seen straight on, a 3×3 grid of deep square cells. Each cell holds a boxset end-on, marked by a gold embossed stripe. The center cell is lit warm from within and its box is pulled a third of the way out. Gold rivets run around the rack's perimeter.

Palette: indigo #1B237D (rack), navy #0B1438 (cell interiors), vinyl black #1A1A2E (boxes) with gold #D9A84E stripes, ivory #FBF5EA (glow in the center cell), gold rivets.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the pulled-out box breaks past the right edge.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

---

## Gifts (J)

### `J4_ten_recipients` — «Праздник» (Rare 🌸)

```text
Generate a soft enamel pin: a bunting garland strung between two tonearms — you became the occasion.

Composition: two tonearms stand upright as masts at the left and right, and a cord swags between them in a deep curve. Ten triangular pennants hang from the cord; on three of them sits a tiny record with a center label. Three small confetti sparks fall beneath the garland.

Palette: pennants cycle ember #E85A2A, cobalt #2A4BD7, ivory #FBF5EA, pink #E89AC0; cord, masts and confetti gold #D9A84E; outlines navy #0B1438.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: both masts break past the side edges, the swag dips past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `J5_first_received` — «С теплом» (Simple 💧)

```text
Generate a soft enamel pin: two open palms cupped beneath a floating record — something warm handed to you.

Composition: two simplified open hands rise from the bottom, cupped together to form a bowl; the hands are pure silhouettes with no finger detail. Above them a record floats at a slight tilt, and three short rays of warmth reach down from the record to the palms.

Palette: ivory #FBF5EA (hands) with navy #0B1438 outline, vinyl black #1A1A2E (record) with an ember #E85A2A label, gold #D9A84E (warmth rays, groove lines), cobalt soft #5C7AE8 (backing shape).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the record breaks past the top edge, the wrists past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no faces, no background, no frame, no realistic anatomy.
```

### `J7_boomerang` — «Бумеранг» (Rare 🌸)

```text
Generate a soft enamel pin: a dog leaping to catch a vinyl record thrown like a frisbee — you throw it out, it comes back to you.

Composition: a dog in full mid-leap, shown in side profile facing right, body stretched out horizontally across the pin, all four legs off the ground, ears blown back, tail streaming behind. Its jaws are open and closing on a vinyl record caught edge-on at the top right — the disc tipped to a steep angle so its grooves and center label read clearly, still spinning. Behind the whole leap, a gold dashed flight path arcs from the lower left, sweeps up and over, and curves back toward the dog — an out-and-back trajectory, not a straight throw. Two short motion arcs trail the spinning disc.

Palette: navy #0B1438 (dog body) with an ivory #FBF5EA chest and muzzle patch, gold #D9A84E (collar, dashed flight path, motion arcs, grooves), vinyl black #1A1A2E (record), pink #E89AC0 (center label), ember #E85A2A (a small tag hanging from the collar).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the record and the dog's muzzle break past the upper-right edge, the tail past the left, the flight path past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no grass, no ground line, no realistic fur, no human figure, no background, no frame, no motion blur.
```

### `J8_loved` — «Любимчик» (Notable 🔵)

```text
Generate a soft enamel pin: three Cupid's arrows struck into one record, and every arrow is a tonearm — three people dropped the needle on you.

Composition: a vinyl record face-on fills the pin, its concentric grooves reading as the rings of a target. Three arrows have landed in it, arriving from three different directions — upper left, right, and lower left — all three buried in the same center label, clustered tight in the bullseye. Each arrow is a tonearm rather than a wooden shaft: a slim segmented arm ending in a fine stylus tip where it enters the label, a small counterweight partway along the shaft, and instead of feather fletching at the tail, one small heart. The arrows sit at different angles and one is slightly longer than the others, so they read as three separate shots rather than a decorative fan.

Palette: vinyl black #1A1A2E (record) with gold #D9A84E grooves, ember #E85A2A (center label), gold (arrow shafts, counterweights, stylus tips), #E55B7A and pink #E89AC0 (the three hearts, not all the same shade), ivory #FBF5EA (one highlight arc on the disc), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: all three arrow tails with their hearts break past the frame — two past the left edge, one past the right.

Output: 1024×1024 PNG, transparent background. No text, no bow, no Cupid figure, no feather fletching, no background, no frame.
```

### `J9_santa` — «Дед Мороз» (Notable 🔵)

```text
Generate a soft enamel pin: a gift sack of records, its snowflake made of tonearms.

Composition: a cinched sack tied at the neck with a gold cord; three records fan out of its open mouth. On the sack's flank, an embossed six-pointed snowflake whose six arms are tonearms ending in stylus tips. Two curved lines at the base form a small snowdrift under the sack.

Palette: cobalt #2A4BD7 (sack) with an ivory #FBF5EA patch, gold #D9A84E (cord, snowflake), vinyl black #1A1A2E (records) with ember #E85A2A labels, ivory (snowdrift), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the records break past the top edge.

Output: 1024×1024 PNG, transparent background. No text, no Santa figure, no background, no frame.
```

### `META_gifts` — «Щедрость» (Epic 🌌)

```text
Generate a soft enamel pin: a cornucopia coiled like a vinyl groove, pouring out gifts.

Composition: a horn of plenty whose body is a spiral coil — the coil itself drawn as an unwound vinyl groove that tapers from a wide mouth down to a tight tip at the lower left. Out of the mouth fly four gift boxes and two records, spreading in a fan toward the upper right. The mouth is trimmed with a gold rim.

Palette: indigo #1B237D (horn) with gold #D9A84E spiral grooves, ivory #FBF5EA and cobalt #2A4BD7 (boxes) with gold ribbons, vinyl black #1A1A2E (records) with ember #E85A2A labels.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the flying objects break past the upper-right corner, the horn's tip past the lower left.

Output: 1024×1024 PNG, transparent background. No text, no fruit, no background, no frame.
```

---

## Community (K)

### `K5_views_x100` — «Витрина» (Notable 🔵)

```text
Generate a soft enamel pin: a shop window with one record on display and passers-by looking in.

Composition: a storefront window under a striped awning. Behind the glass, a single record stands face-on on a small pedestal, lit from below by a short fan of light. One diagonal white streak crosses the glass. Along the bottom edge, three small head-and-shoulders silhouettes seen from behind, facing into the window.

Palette: awning striped in ember #E85A2A and ivory #FBF5EA, frame gold #D9A84E, glass cobalt soft #5C7AE8, record vinyl black #1A1A2E with an ember label, silhouettes navy #0B1438.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the awning breaks past the top and both side edges.

Output: 1024×1024 PNG, transparent background. No text, no signage, no faces, no background, no frame.
```

### `K6_views_x1000` — «На главной» (Rare 🌸)

```text
Generate a soft enamel pin: a theatre stage with one record in the spotlight.

Composition: a proscenium with heavy curtains drawn open at both sides, gathered with gold tiebacks. Center stage, a record stands face-on on a low podium. Two spotlight cones fall from above and cross exactly on the record's label. Along the stage's front lip, five gold footlights in a row.

Palette: curtains #E55B7A with gold #D9A84E tassels, podium navy #0B1438, record vinyl black #1A1A2E with a pink #E89AC0 label, light cones ivory #FBF5EA at 25% opacity, footlights gold.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the curtain rail breaks past the top edge, the curtain hems past both sides.

Output: 1024×1024 PNG, transparent background. No text, no audience, no background, no frame.
```

---

## Invitations (INV)

### `INV_first` — «Сарафан» (Simple 💧)

```text
Generate a soft enamel pin: a tin-can telephone where one can is a record label — word passed on for the first time.

Composition: two tin cans face each other at the left and right, joined by a taut string that sags in a soft curve between them. The left can is a plain cylinder seen end-on; the right can's opening is a record's center label with a spindle dot. One small gold spark sits on the string at its midpoint.

Palette: ivory #FBF5EA (cans) with gold #D9A84E rims, ember #E85A2A (right can's label), gold (string, spark), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles beyond the string spark. Silhouette: both cans break past the left and right edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `INV_three` — «Расходится» (Notable 🔵)

```text
Generate a soft enamel pin: a record dropped into water, three rings spreading out.

Composition: a top-down view of a water surface. At the center, one record is half-submerged at a tilt, its label still visible above the surface. Three concentric rings spread outward from it — but each ring is drawn as a vinyl groove with one small break in it, like a record's run-out. One white crescent highlight sits on the nearest ring.

Palette: water grades cobalt #2A4BD7 to cobalt soft #5C7AE8, rings gold #D9A84E, record vinyl black #1A1A2E with an ember #E85A2A label, outline navy #0B1438.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the outermost ring breaks past all four edges.

Output: 1024×1024 PNG, transparent background. No text, no realistic water, no background, no frame.
```

### `INV_ten` — «Тренд» (Rare 🌸)

```text
Generate a soft enamel pin: a growth chart whose bars are stacks of records.

Composition: five vertical bars rising left to right, each bar built from records lying flat and stacked edge-on — one, two, three, four, five discs tall. A gold arrow rises over the tops of the bars in a straight diagonal and punches out through the upper right. A navy baseline runs under the bars.

Palette: vinyl black #1A1A2E (discs) with gold #D9A84E edges, every fifth disc carrying a pink #E89AC0 label, arrow gold, axis navy #0B1438, backing plate ivory #FBF5EA.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the arrow breaks past the upper-right corner.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no background, no frame.
```

### `INV_active_circle` — «Живой круг» (Rare 🌸)

```text
Generate a soft enamel pin: a ring of five figures holding hands, standing on a vinyl groove.

Composition: five simplified head-and-shoulders figures arranged evenly around a circle, arms linked to their neighbors, forming a closed round dance. The circle they stand on is drawn as a vinyl groove line. At the center of the ring sits a small record label with two concentric halo rings around it, as if pulsing.

Palette: figures alternate navy #0B1438 and cobalt #2A4BD7, groove circle gold #D9A84E, center label ember #E85A2A, halo rings pink #E89AC0.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the leftmost and rightmost figures break past the side edges.

Output: 1024×1024 PNG, transparent background. No text, no faces, no background, no frame.
```

### `INV_chain` — «Цепочка» (Epic 🌌)

```text
Generate a soft enamel pin: a chain whose links are records — the reaction continued without you.

Composition: four chain links run diagonally from lower left to upper right. Each link is not an oval but a record with a large center hole, threaded through its neighbor. The last link at the top is still open, splitting upward, and two sparks fly out of the gap.

Palette: vinyl black #1A1A2E (links) with gold #D9A84E grooves and gold link edges, indigo #1B237D glow inside the open gap, gold sparks, navy #0B1438 outline.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the first and last links break past opposite corners.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `INV_from_showcase` — «Из витрины» (Notable 🔵)

```text
Generate a soft enamel pin: a hand pulling a record straight out of a display rack.

Composition: an upright display rack with three slots, each holding a record face-on. From the right, a simplified hand silhouette reaches in and pulls the middle record outward; where it was, an empty gold outline marks its former place. A small tag on a string hangs above the rack.

Palette: navy #0B1438 (rack), vinyl black #1A1A2E (records) with ember #E85A2A labels, ivory #FBF5EA (hand) with navy outline, gold #D9A84E (empty outline, string), cobalt #2A4BD7 (tag).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. No sparkles. Silhouette: the hand with the record breaks past the right edge, the tag past the top.

Output: 1024×1024 PNG, transparent background. No text, no realistic anatomy, no background, no frame.
```

### `META_evangelist` — «Эпидемия» (Legend ⚫)

```text
Generate a soft enamel pin: a branching network of records — this stopped being invitations and became spread.

Composition: one central record node with a label, from which three branches fan out; each of those splits into two second-level nodes, and two of those into one more each. Every node is a small record with a center label; every connection is a straight gold line. Nodes get paler the further from the center, as if still catching light.

Palette: center node ember #E85A2A, first ring cobalt #2A4BD7, second ring cobalt soft #5C7AE8, outermost pale blue #A5C8E1; links gold #D9A84E; backing field #0A0A1A.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Legend tier: add 3 tiny gold four-point sparkles and a second gold rim tracing the whole silhouette. Silhouette: the outer nodes break past all four edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

---

## Collection-state easter eggs (R / MX)

### `R_sixty_nine` — «Шестьдесят девять» (Rare 🌸)

```text
Generate a soft enamel pin: nothing but a face wearing a slow, knowing smirk — he knows exactly what the number is and he is not going to say it.

A reference image is attached. Use it ONLY for the expression — the uneven brows, the half-lidded eyes, the tight one-sided closed-mouth smile, the heavy jaw. Do not reproduce the person's identity or specific features; this is a generic stylized character, not a portrait of anyone.

Composition: one head fills the entire pin, front view, cropped just below the chin and just past the ears — no shoulders, no body, no props, nothing else in the frame. The head is round and heavy with a soft double chin and full cheeks, a bald crown with a receding hairline, hair kept only at the temples. The whole pin is the expression, so it is built big and clean: one eyebrow noticeably higher than the other, both eyes small and half-lidded with a lazy downward lid line, and a closed-mouth smirk pulled up hard to one side, cheek bunching above it. Two short nose lines and one chin crease, nothing more.

Palette: ivory #FBF5EA (face) with navy #0B1438 outline, cobalt soft #5C7AE8 (shading under the chin, cheek, and lids), warm brown #2A1E1A (hair), pink #E89AC0 (a soft blush on the smirking cheek), gold #D9A84E (contour).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the head is slightly wider than the frame and breaks past both side edges and the top.

Output: 1024×1024 PNG, transparent background. No text, no digits, no teeth, no open mouth, no glasses, no hat, no record, no props, no shoulders, no photorealistic skin, no likeness of any real or famous person, no background, no frame.
```

### `R_seventy_eight` — «Семьдесят восемь» (Rare 🌸)

```text
Generate a soft enamel pin: a thick shellac disc from before the LP, with a gramophone horn beside it.

Composition: a shellac record at a three-quarter tilt, noticeably thicker in the edge profile than a vinyl disc, with wide widely spaced grooves. Its paper label is plain with a decorative ring. To the right, the flared bell of an old gramophone horn enters the composition, cropped by the frame edge, its mouth facing the disc.

Palette: warm dark brown #2A1E1A (shellac), ivory #FBF5EA (label), gold #D9A84E (grooves, horn, label ring), pink #E89AC0 (label border), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the horn bell breaks past the right edge.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no background, no frame.
```

### `R_pi` — «Число Пи» (Epic 🌌)

```text
Generate a soft enamel pin: the pi symbol built from tonearms, trailing off into infinity.

Composition: a large pi symbol centered. Both of its legs are tonearms, each ending in a stylus tip pointing down; its top crossbar is a straight segment of vinyl groove. Behind the symbol sits a circular field ruled with faint concentric groove lines. To the lower right, a chain of six diminishing dots runs off toward the frame edge.

Palette: gold #D9A84E (symbol) with navy #0B1438 outline, ember #E85A2A (stylus tips), indigo #1B237D (circular field), gold (dots).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the crossbar breaks past both side edges, the dot chain past the right.

Output: 1024×1024 PNG, transparent background. No text, no digits, no background, no frame.
```

### `R_palindrome` — «Палиндром» (Rare 🌸)

```text
Generate a soft enamel pin: one record played by two styli at once, each arriving from the opposite side — it reads the same either way.

Composition: a vinyl record face-on, centered. Two tonearms reach in toward it, one from the upper left and one from the lower right, placed in exact rotational symmetry — turn the whole pin 180 degrees and the composition is identical. Each arm ends in a stylus resting in the grooves, one tracking inward and one tracking outward, their tips at mirrored positions on the same groove band. A thin gold axis line runs diagonally between them through the center label, marking the pivot the whole image turns around.

Palette: vinyl black #1A1A2E (record) with gold #D9A84E grooves, gold (both tonearms) with navy #0B1438 pivots, pink #E89AC0 (center label), ember #E85A2A (one small jewel on each counterweight), navy (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: both counterweights break past opposite corners — upper left and lower right.

Output: 1024×1024 PNG, transparent background. No text, no digits, no mirror, no background, no frame.
```

### `R_self_aware` — «Самосознание» (Rare 🌸)

```text
Generate a soft enamel pin: a Möbius strip made of vinyl groove — a record that runs along itself and arrives back at itself.

Composition: one continuous ribbon twisted into a Möbius loop, standing upright and filling the pin. The ribbon is a strip of vinyl: its broad face carries fine parallel groove lines running along its whole length, and the single half-twist sits at the lower right where the strip turns over and you see it flip from face to back without a break. Riding the ribbon near the top, a small stylus sits in the grooves, pointed along the direction of travel — it will pass through the twist and come back to where it started on the other side. One thin gold arrow on the ribbon marks that direction.

Palette: vinyl black #1A1A2E (ribbon face) with gold #D9A84E groove lines, indigo #1B237D (the underside revealed at the twist), pink #E89AC0 (a thin edge line running the whole rim of the strip), gold (stylus, direction arrow), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the loop is wider than the frame and breaks past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no infinity symbol, no snake, no background, no frame, no 3D rendering.
```

### `R_meta_vertushka` — «Вертушка» (Epic 🌌)

```text
Generate a soft enamel pin: a turntable seen from above, whose record's label shows the same turntable.

Composition: a square turntable deck with rounded corners, viewed top-down. A record sits on its platter, and on that record's label is drawn the very same turntable in miniature. The real tonearm swings across the disc on a diagonal with its counterweight; the miniature tonearm is a single tiny gold stroke.

Palette: indigo #1B237D (deck) with gold #D9A84E trim, cobalt #2A4BD7 (slipmat), vinyl black #1A1A2E (record), ivory #FBF5EA (label) with a navy #0B1438 miniature, gold (tonearm).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the counterweight breaks past the right edge, a deck corner past the lower left.

Output: 1024×1024 PNG, transparent background. No text, no brand marks, no background, no frame.
```

### `R_long_title` — «Поэма» (Rare 🌸)

```text
Generate a soft enamel pin: a record sleeve from which a scroll unrolls instead of a disc — the title didn't fit.

Composition: a square record sleeve seen straight on. Out of its opening, instead of a disc, a long scroll unrolls downward, its bottom end curling back on itself. Across the scroll run seven wavy gold strokes of varying length standing in for lines of text — no actual letters. The edge of a disc still peeks from the sleeve's top corner.

Palette: cobalt #2A4BD7 (sleeve), ivory #FBF5EA (scroll), gold #D9A84E (text strokes), vinyl black #1A1A2E (disc edge) with a pink #E89AC0 label, navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the scroll runs far past the bottom edge, its curl past the lower-right corner.

Output: 1024×1024 PNG, transparent background. No text, no letters, no background, no frame.
```

### `R_time_machine_50` — «Полвека спустя» (Rare 🌸)

```text
Generate a soft enamel pin: an hourglass that pours records, its waist made of a stylus.

Composition: an hourglass in a slim frame. The upper bulb is nearly empty, the lower nearly full, and what falls between them is a stream of tiny records rather than sand. The narrow waist joining the bulbs is a tonearm with its stylus at the pinch point. On the lower frame bar, a plain notched marker plate.

Palette: cobalt soft #5C7AE8 (translucent bulbs), vinyl black #1A1A2E (falling discs), gold #D9A84E (frame, waist, stylus), ember #E85A2A (marker plate), pink #E89AC0 (one disc's label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the top and bottom frame bars break past the top and bottom edges.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no background, no frame.
```

### `R_new_year` — «Первая в году» (Rare 🌸)

```text
Generate a soft enamel pin: a clock face made of vinyl, both tonearm hands pointing straight up at midnight.

Composition: a circular clock whose dial is a record with concentric grooves and twelve small gold hour markers. Its two hands are tonearms — one long, one short — both aimed exactly at the top marker. Behind the upper rim, three short firework rays burst outward.

Palette: vinyl black #1A1A2E (dial) with gold #D9A84E grooves and markers, ember #E85A2A (center label), gold (tonearm hands) with navy #0B1438 pivots, pink #E89AC0 and gold (fireworks).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the firework rays break past the top edge, the long tonearm's counterweight past the right.

Output: 1024×1024 PNG, transparent background. No text, no numerals, no background, no frame.
```

### `R_friday_night` — «Пятничный спин» (Rare 🌸)

```text
Generate a soft enamel pin: a tear-off calendar whose next page is a record — the week is over, side A begins.

Composition: a wall calendar on a gold spiral binding. Its top sheet is half torn away and curls to the right; underneath, where the next page should be, sits a record. Behind the calendar, a thin crescent moon and two stars. Along the bottom of the torn sheet, five short tick marks with the last one struck through.

Palette: ivory #FBF5EA (sheet), gold #D9A84E (spiral, moon, stars), vinyl black #1A1A2E (record) with an ember #E85A2A label, navy #0B1438 (night field), pink #E89AC0 (tick marks).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the tearing sheet breaks past the right edge, the moon past the upper-left corner.

Output: 1024×1024 PNG, transparent background. No text, no dates, no background, no frame.
```

### `R_leap_day` — «29 февраля» (Epic 🌌)

```text
Generate a soft enamel pin: a calendar grid where one cell exists that normally doesn't.

Composition: a 7×5 grid of square cells, all flat and identical, separated by 1px gold lines. One cell in the second-to-last row is pushed forward out of the plane, glowing from within, and instead of a date it holds a small record. Short flat shadows fall from it onto the neighboring cells.

Palette: indigo #1B237D (grid field), navy #0B1438 (cells), gold #D9A84E (grid lines, the special cell's rim), ivory #FBF5EA (glow), ember #E85A2A (the record inside).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the protruding cell breaks past the bottom edge.

Output: 1024×1024 PNG, transparent background. No text, no dates, no background, no frame.
```

### `R_three_lives` — «Три жизни» (Epic 🌌)

```text
Generate a soft enamel pin: one album in three bodies — vinyl, CD, cassette — as a metamorphosis.

Composition: three media objects placed along a shallow arc from left to right: a vinyl record, a compact disc, a compact cassette, each shown face-on. Two thin gold arrows connect them in sequence. All three carry the same cover motif: one circle with a single dot at its center.

Palette: vinyl black #1A1A2E (record), ivory #FBF5EA (CD) with an ember #E85A2A arc, cobalt #2A4BD7 (cassette), gold #D9A84E (arrows, rims), indigo #1B237D (the shared circle motif).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the outer two objects break past the left and right edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `R_tapehead` — «Тру-кассетник» (Epic 🌌)

```text
Generate a soft enamel pin: a balance scale tipped hard — tape beat vinyl.

Composition: a two-pan balance whose beam is tilted about 25 degrees. The right pan, loaded with cassettes, has dropped sharply; the left pan holds a single record and has swung up, the disc visibly sliding toward its rim. The upright post is a tonearm. Thin gold chains connect beam to pans.

Palette: gold #D9A84E (beam, post, chains), cobalt #2A4BD7 and indigo #1B237D (cassettes), vinyl black #1A1A2E (record) with an ember #E85A2A label, ivory #FBF5EA (pans), navy #0B1438 (base).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the low pan breaks past the lower-right corner, the high pan past the upper left.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `R_cd_renaissance` — «Ренессанс CD» (Rare 🌸)

```text
Generate a soft enamel pin: a compact disc rising over the horizon like a sun.

Composition: the upper half of a CD emerges above a straight horizon line, seven straight rays fanning upward from it. Below the horizon, a row of record spines is silhouetted. One broad rainbow arc crosses the visible face of the disc.

Palette: ivory #FBF5EA with a pale blue #A5C8E1 sheen (disc), ember #E85A2A (rainbow arc), gold #D9A84E (rays) with one ray in pink #E89AC0, navy #0B1438 (horizon and spines), cobalt soft #5C7AE8 (sky).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the rays break past the top and both side edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no realistic sun glare.
```

### `R_tabletop_giant` — «Гигант на столе» (Rare 🌸)

```text
Generate a soft enamel pin: a boxset so large the table buckles under it.

Composition: a small four-legged table seen straight on, its thin legs visibly bowing outward under load. On top sits an enormous boxset, twice the table's width, overhanging both sides. Its exposed end reveals a stack of ten disc edges.

Palette: navy #0B1438 (box) with gold #D9A84E embossing, vinyl black #1A1A2E and ivory #FBF5EA (alternating disc edges) with one pink #E89AC0 spine, ivory (tabletop), gold (legs).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the box breaks past both side edges and the top.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `R_type_iv` — «Type IV» (Rare 🌸)

```text
Generate a soft enamel pin: a metal-formulation cassette, the top tape class.

Composition: a compact cassette tilted slightly, its shell unmistakably metal: two parallel white diagonal streaks run across the entire body. Along the bottom edge, four rectangular sensor notches, the fourth one lit gold. On the label, four tally strokes arranged as a Roman four — as pure shapes, not typography.

Palette: cold steel grey #6B7A99 (shell), white (streaks), ivory #FBF5EA (label), navy #0B1438 (notches), gold #D9A84E (lit notch, tally strokes), pink #E89AC0 (reel hubs).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the upper shell corner breaks past the upper-right edge.

Output: 1024×1024 PNG, transparent background. No text, no lettering, no background, no frame.
```

### `R_limited_box` — «Лимитка» (Rare 🌸)

```text
Generate a soft enamel pin: a numbered boxset sealed with wax.

Composition: a boxset at a three-quarter angle. On its front face, a raised gold numbering plaque shaped as a fraction — a horizontal bar with a blank field above and below it, no digits. Over the box's top-right corner, a wax seal is pressed, its impression showing a tiny record with a center label.

Palette: indigo #1B237D (box), gold #D9A84E (plaque, edge trim), ember #E85A2A (wax seal), navy #0B1438 (seal impression), ivory #FBF5EA (box edge), pink #E89AC0 (the impressed label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the wax seal breaks past the right edge, the lid corner past the top.

Output: 1024×1024 PNG, transparent background. No text, no numbers, no background, no frame.
```

### `R_hidden_track` — «Спрятанный трек» (Rare 🌸)

```text
Generate a soft enamel pin: a small door set into the grooves of a record, standing ajar with light coming out — there is a room in here nobody told you about.

Composition: a vinyl record face-on fills the pin. Cut into its groove band, in the lower right quadrant, sits a small arched door — a proper door with a frame, a panel line and a tiny round gold handle, scaled so it is clearly a doorway and not a sticker. It stands open a hand's width, hinged outward toward the viewer, and a narrow wedge of warm light spills out of the gap and falls across the grooves. The grooves interrupt cleanly at the door frame and pick up again on the other side, so the door reads as built into the record rather than laid on top of it.

Palette: vinyl black #1A1A2E (record) with gold #D9A84E grooves, navy #0B1438 (door panel) with a gold frame and handle, ivory #FBF5EA (the wedge of light), pink #E89AC0 (center label), gold (outline of the light spill).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the opened door leaf breaks past the lower-right edge of the disc and past the frame.

Output: 1024×1024 PNG, transparent background. No text, no keyhole, no stairs, no figure in the doorway, no background, no frame.
```

### `MX_night_crate` — «Ночной диггинг» (Rare 🌸)

```text
Generate a soft enamel pin: crate digging at three in the morning by flashlight.

Composition: a record crate seen from above and slightly to the side, packed with spines. Above it, a pocket flashlight enters from the upper right, casting a narrow diagonal cone of light down into the crate; inside that cone, one record is pulled up a third higher than its neighbors. Around the scene, three small stars and a thin crescent moon in the upper corner.

Palette: field #0A0A1A, navy #0B1438 (crate) with gold #D9A84E corner braces, vinyl black #1A1A2E and cobalt #2A4BD7 (spines), ivory #FBF5EA at 25% opacity (light cone), pink #E89AC0 (the lit record's label), gold (stars, moon, flashlight).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the flashlight breaks past the upper-right corner.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no volumetric light rendering.
```

---

## Interaction easter eggs (E)

### `E_glass_eye` — «Глаз-алмаз» (Rare 🌸)

```text
Generate a soft enamel pin: the camera failed to recognize the cover, but the human eye did not.

Composition: four gold corner brackets mark a viewfinder frame; inside it sits a record sleeve with a "not recognized" mark across it — a plain circle crossed by one diagonal bar. Layered in front, larger and closer, a single almond-shaped human eye drawn in flat lines, its pupil replaced by a record's center label.

Palette: gold #D9A84E (brackets), cobalt #2A4BD7 (sleeve), navy #0B1438 (error mark, eye outline), ivory #FBF5EA (eye white) with gold lid, ember #E85A2A (pupil label) with a pink #E89AC0 ring.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the corner brackets break past all four corners.

Output: 1024×1024 PNG, transparent background. No text, no brow, no background, no frame.
```

### `E_digitizer` — «Оцифровщик» (Rare 🌸)

```text
Generate a soft enamel pin: a shelf of records being pulled into a phone, dissolving into pixels.

Composition: a phone standing vertically, seen face-on. A diagonal train of five records shrinks as it approaches the screen from the upper left; the closer they get, the more each disc breaks apart into square pixels that stream into the display. A horizontal scan line crosses the screen.

Palette: navy #0B1438 (phone body) with a gold #D9A84E bezel, cobalt #2A4BD7 (screen), vinyl black #1A1A2E (records) with ember #E85A2A labels, ivory #FBF5EA (pixels), pink #E89AC0 (scan line).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the farthest record breaks past the upper-left corner.

Output: 1024×1024 PNG, transparent background. No text, no UI elements, no background, no frame.
```

### `E_glow` — «Светится в темноте» (Rare 🌸)

```text
Generate a soft enamel pin: the same record, half of it in the dark and half of it glowing.

Composition: one record face-on, split vertically. The left half is ordinary — dark vinyl with detailed grooves against a near-black field. The right half is the same disc glowing, surrounded by three expanding contour rings of light. The boundary between halves is not a straight line but a soft three-step offset.

Palette: vinyl black #1A1A2E on a #0A0A1A field (dark half), glow green #B8F0C8 with an ivory #FBF5EA core (lit half), gold #D9A84E (grooves), pink #E89AC0 (label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the glow rings break past the right and top edges.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no blur, no bloom filter.
```

### `E_spin` — «Закрутил» (Rare 🌸)

```text
Generate a soft enamel pin: a record spun by hand, thirty-three times over.

Composition: a record in motion, trailed by three curved motion streaks sweeping off its edge. A circular arrow ring surrounds the whole disc, open at one end. At the arrow's tail sits a small counter plaque with two blank digit fields. One simplified fingertip touches the disc's rim, giving the push.

Palette: vinyl black #1A1A2E (disc) with gold #D9A84E grooves, cobalt soft #5C7AE8 (motion streaks, fading), gold (arrow ring), ivory #FBF5EA (counter plaque) with navy #0B1438 fields, pink #E89AC0 (label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the arrow ring breaks past all four edges.

Output: 1024×1024 PNG, transparent background. No text, no digits, no background, no frame, no motion blur filter.
```

### `E_rainbow` — «Радуга» (Rare 🌸)

```text
Generate a soft enamel pin: six colored vinyl records fanned so their arcs form a rainbow.

Composition: six records overlapping in a fan, each a different vinyl color, arranged so their upper edges together read as a rainbow arch. All six share one identical detail: the same plain center label, the only thing they have in common.

Palette: vinyls in ember #E85A2A, gold #D9A84E, green #7FBF8F, cobalt #2A4BD7, indigo #1B237D, pink #E89AC0; groove lines gold 1px; labels ivory #FBF5EA with a navy #0B1438 dot.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer records break past both side edges, the arch crest past the top.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame, no gradient blends between colors.
```

### `E_second_thoughts` — «Сомнения» (Rare 🌸)

```text
Generate a soft enamel pin: the same record added and removed, three times over — still deciding.

Composition: one record drawn three times as ghost phases at different positions: entering a bin, leaving it, entering again. The leftmost phase is faintest, the rightmost fully solid. A double-headed gold arrow loops between them in a curl. The bin itself is only a dashed navy outline.

Palette: record phases vinyl black #1A1A2E at 35%, 65% and 100% opacity, labels ember #E85A2A, arrow loop gold #D9A84E, bin outline navy #0B1438 dashed, pink #E89AC0 accent on the solid phase.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the arrow loop breaks past the right edge, the faintest phase past the left.

Output: 1024×1024 PNG, transparent background. No text, no background, no frame.
```

### `E_photo_shy` — «Не та фотка» (Rare 🌸)

```text
Generate a soft enamel pin: five instant photos of yourself, four of them crossed out.

Composition: five square instant-photo cards scattered in a loose fan. Four of them carry a simplified head-and-shoulders silhouette, each turned at a slightly different angle, and each struck through with one thin gold diagonal. The fifth card is blank and still developing.

Palette: ivory #FBF5EA (cards) with a navy #0B1438 image frame, cobalt #2A4BD7 (silhouettes), gold #D9A84E (strike-throughs), cobalt soft #5C7AE8 (developing card) with a pink #E89AC0 border.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer cards break past the left edge and the bottom.

Output: 1024×1024 PNG, transparent background. No text, no faces, no background, no frame.
```

### `E_anniversary` — «Год спустя» (Epic 🌌)

```text
Generate a soft enamel pin: a tree's annual rings that are actually vinyl grooves, with one ring lit and a candle on it.

Composition: a slightly elliptical cross-section of a trunk, seen in gentle perspective, its growth rings drawn as concentric vinyl grooves. Exactly one ring — the outermost — is highlighted in brighter gold with an ivory contour, and a tiny candle stands on it, its flame lit. The center of the section is a record label.

Palette: indigo #1B237D (section) with gold #D9A84E rings, brighter gold plus an ivory #FBF5EA contour on the lit ring, ivory (candle), ember #E85A2A (flame), pink #E89AC0 (center label).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles. Silhouette: the candle flame breaks past the top edge.

Output: 1024×1024 PNG, transparent background. No text, no wood texture, no background, no frame.
```

### `E_pull_78` — «Заело» (Rare 🌸)

```text
Generate a soft enamel pin: a pull-to-refresh arrow that got stuck in its own groove.

Composition: a circular refresh arrow that has looped back on itself and wound into a three-turn spiral. At the spiral's center, a stylus is lodged in a single groove, with three short jitter arcs around it showing the skip. Below the spiral sits a small counter plaque with two blank digit fields.

Palette: gold #D9A84E (spiral arrow, tapering in width), vinyl black #1A1A2E (disc field) with gold grooves, navy #0B1438 (stylus body) with a gold tip, pink #E89AC0 (jitter arcs), ivory #FBF5EA (plaque) with navy fields.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the spiral's arrowhead breaks past the upper-right corner.

Output: 1024×1024 PNG, transparent background. No text, no digits, no background, no frame.
```

---

## Community — остальные (K)


### `K1_following_x5` — «Зритель» (Simple 💧)

```text
Generate a soft enamel pin: a pair of opera glasses whose two lenses are records — you came to watch other people's collections.

Composition: one pair of opera glasses held up front-on, filling the pin, with a slim gold handle angling down to the right. The two barrels are short and stout, and each eyepiece facing the viewer is a vinyl record: concentric grooves with a small center label at the middle, standing in for the lens. A gold bridge joins the barrels. Nothing else in frame.

Palette: navy #0B1438 (barrels) with an ivory #FBF5EA band around each, gold #D9A84E (bridge, handle, rims, grooves), vinyl black #1A1A2E (lens faces), ember #E85A2A (center labels).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the handle breaks past the lower-right corner, the barrels past both sides.

Output: 1024×1024 PNG, transparent background. No text, no eyes behind the lenses, no background, no frame.
```

### `K7_mutual_x10` — «Бэкстейдж» (Notable 🔵)

```text
Generate a soft enamel pin: a backstage laminate on a lanyard, and the pass itself is a record — the door swings both ways now.

Composition: a rectangular laminate pass hanging front-on in the center of the pin, suspended from a lanyard whose two straps rise from its top corners and run off the top edge. Set into the pass, filling most of its face, is a vinyl record with grooves and a center label. A gold clip joins pass to lanyard, and one corner of the laminate is dog-eared from use. Behind the pass, the vertical edge of a heavy stage curtain enters from the left.

Palette: cobalt #2A4BD7 (lanyard straps), ivory #FBF5EA (laminate), vinyl black #1A1A2E (record) with gold #D9A84E grooves, ember #E85A2A (center label), navy #0B1438 (curtain, outline), gold (clip).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the lanyard straps break past the top edge, the curtain past the left.

Output: 1024×1024 PNG, transparent background. No text, no barcode, no faces, no background, no frame.
```

### `K8_contrib_x1` — «Стажёр» (Simple 💧)

```text
Generate a soft enamel pin: a rubber stamp coming down on a blank catalogue card — your first release just got approved.

Composition: a wooden-handled rubber stamp caught mid-strike, angled from the upper right, its head about to meet a plain catalogue card lying flat below. On the card, already printed, sits one round ink impression showing a simple record disc. Three short motion dashes above the stamp show it dropping. The card's corner is clipped.

Palette: navy #0B1438 (stamp handle) with a gold #D9A84E collar, vinyl black #1A1A2E (stamp head), ivory #FBF5EA (card), ember #E85A2A (the ink impression), gold (motion dashes, card edge).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the stamp handle breaks past the upper-right corner, the card past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no letters in the stamp impression, no hands, no background, no frame.
```

### `K9_contrib_x5` — «Поставщик» (Notable 🔵)

```text
Generate a soft enamel pin: a hand truck loaded with records — you are not a visitor here, you are the supply.

Composition: a two-wheel hand truck seen from the side, tilted back on its wheel at a working angle, its long frame running up to the right. Stacked on its plate, a bundle of five record sleeves strapped together with one gold band. The truck's handle is bare and worn. One wheel is drawn as a plain dark circle, deliberately not a record, so the load reads as the cargo.

Palette: navy #0B1438 (truck frame, wheel), gold #D9A84E (strap, frame joints, handle grip), ivory #FBF5EA and cobalt #2A4BD7 (alternating sleeve edges), ember #E85A2A (one sleeve spine).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the handle breaks past the upper-right corner, the wheel past the bottom-left.

Output: 1024×1024 PNG, transparent background. No text, no delivery van, no figure pushing it, no background, no frame.
```

### `K10_contrib_x20` — «Да, шеф!» (Rare 🌸)

```text
Generate a soft enamel pin: a kitchen service bell struck hard, with a record plated up on the pass — twenty orders out, chef.

Composition: a domed service bell sits centered on a small base, its striker button just pressed down, and three gold sound arcs ring out from its dome on both sides. Beside it on the same counter line, one vinyl record lies flat like a plated dish under a raised gold cloche rim. The bell is the hero and roughly twice the visual weight of the plate.

Palette: ivory #FBF5EA (bell dome) with gold #D9A84E rim and striker, navy #0B1438 (base, counter line), vinyl black #1A1A2E (plated record) with gold grooves, ember #E85A2A (center label), gold (sound arcs).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the outer sound arcs break past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no food, no chef figure, no background, no frame.
```

### `K11_msgs_x10` — «Есть контакт» (Simple 💧)

```text
Generate a soft enamel pin: two styli touching tip to tip with a spark jumping between them — contact established.

Composition: two tonearms enter from the left and the right edges, angled toward each other, and their stylus tips almost meet at the exact center of the pin. In the tiny gap between the tips, one bright four-point spark flashes, ringed by two thin concentric shock rings. The arms are slim and symmetrical, each with a counterweight at its outer end.

Palette: gold #D9A84E (tonearms, spark), navy #0B1438 (pivots, outline), ember #E85A2A (the spark core), cobalt soft #5C7AE8 (shock rings), ivory #FBF5EA (a highlight on each arm).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: both counterweights break past the left and right edges.

Output: 1024×1024 PNG, transparent background. No text, no lightning bolts, no background, no frame.
```

### `K12_msgs_x50` — «Продажник» (Notable 🔵)

```text
Generate a soft enamel pin: a coat held open to reveal records lining the inside — everything is for sale and you know it.

Composition: a long coat shown front-on and empty of any wearer, both front panels swung wide open like wings. Pinned in rows down the exposed lining, six record sleeves hang neatly, each showing a disc edge peeking out. The coat's collar is turned up and its shoulders keep their shape, so the garment reads as worn by someone invisible.

Palette: navy #0B1438 (coat outer) with gold #D9A84E buttons and seams, ember #E85A2A (lining), vinyl black #1A1A2E and ivory #FBF5EA (alternating sleeves), cobalt #2A4BD7 (two sleeves).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: both open coat panels break past the left and right edges, the collar past the top.

Output: 1024×1024 PNG, transparent background. No text, no face, no hands, no legs, no background, no frame.
```

### `K13_msgs_x200` — «Уолл-стрит» (Rare 🌸)

```text
Generate a soft enamel pin: a ticker-tape machine spilling a ribbon that is one long vinyl groove — two hundred deals and counting.

Composition: a domed glass stock-ticker on a round base stands in the upper left of the pin. From its mouth a long paper ribbon pours out, loops once in the air and cascades down to the lower right, pooling in loose coils. The ribbon is not printed with numbers: instead it carries parallel groove lines running its full length, so it reads as an unwound record groove.

Palette: cobalt soft #5C7AE8 (glass dome, semi-transparent), navy #0B1438 (ticker body, base), gold #D9A84E (base trim, groove lines), ivory #FBF5EA (ribbon), pink #E89AC0 (one thin edge stripe along the ribbon).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the ticker dome breaks past the upper-left corner, the pooling ribbon past the bottom-right.

Output: 1024×1024 PNG, transparent background. No text, no digits, no charts, no background, no frame.
```

### `K14_wanted_x1` — «Разыскивается» (Notable 🔵)

```text
Generate a soft enamel pin: a wanted poster nailed to a board, and the face in the portrait oval is one of your records.

Composition: a single sheet of paper nailed at its top corners to a plank wall, curling slightly at the bottom, filling the pin. In the center of the sheet, a portrait oval framed in gold holds a vinyl record shown face-on — grooves and center label clearly visible, staring back like a mugshot. Below the oval, three blank ruled lines stand in for the notice text, and a small gold sheriff star sits at the top of the sheet. Two round nail heads pin the top corners.

Palette: ivory #FBF5EA (poster) with warm brown #2A1E1A plank behind, gold #D9A84E (oval frame, star, nails, ruled lines), vinyl black #1A1A2E (record) with gold grooves, ember #E85A2A (center label), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the poster's curling bottom edge breaks past the bottom, the plank past both sides.

Output: 1024×1024 PNG, transparent background. No text, no readable words on the ruled lines, no faces, no background, no frame.
```

### `K15_wanted_x5` — «Шоурум» (Rare 🌸)

```text
Generate a soft enamel pin: a velvet rope drawn around a single record on a plinth — your shelf became an exhibit.

Composition: a low round plinth stands center, and on it one vinyl record is displayed upright in a slim gold cradle, face-on to the viewer. In front of the plinth, two short gold stanchions carry a heavy velvet rope that swags between them in a deep curve, cordoning the record off. The rope and stanchions sit clearly in front, overlapping the plinth's base.

Palette: navy #0B1438 (plinth) with gold #D9A84E trim, vinyl black #1A1A2E (record) with gold grooves, pink #E89AC0 (center label), #E55B7A (velvet rope), gold (stanchions, cradle), ivory #FBF5EA (one highlight on the plinth).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the stanchions break past both side edges, the rope swag past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no visitors, no museum wall, no background, no frame.
```

### `K16_wanted_x10` — «Личный Санта» (Rare 🌸)

```text
Generate a soft enamel pin: a mailbox bursting with wish letters addressed to you — ten of your records are on somebody's list.

Composition: a classic post-mounted mailbox seen from the side, its front flap hanging open, crammed so full that envelopes fan out of the mouth and two have spilled past the frame. Each envelope carries a small heart wax seal instead of a stamp. From the middle of the pile, the edge of one vinyl record juts out among the letters. The raised signal flag on the mailbox is up, and its flag panel is a tiny record.

Palette: cobalt #2A4BD7 (mailbox) with gold #D9A84E hinges and trim, ivory #FBF5EA (envelopes), #E55B7A (wax seals), vinyl black #1A1A2E (record edge, flag panel), navy #0B1438 (post, outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: two spilling envelopes break past the bottom-right, the raised flag past the top.

Output: 1024×1024 PNG, transparent background. No text, no addresses, no Santa figure, no background, no frame.
```

### `META_community` — «Резидент» (Epic 🌌)

```text
Generate a soft enamel pin: a two-deck DJ booth with the house keys hanging off the mixer — you are not a guest here, you are resident.

Composition: a DJ setup seen straight on and slightly from above: two turntables side by side, each with a record on the platter and a tonearm swung across it, and a narrow mixer standing between them with a row of faders and one crossfader. Hooked over the corner of the mixer, a small ring of keys hangs down. The whole rig sits on a plain counter line and is drawn flat and symmetrical.

Palette: indigo #1B237D (decks, mixer) with gold #D9A84E faders, knobs and trim, vinyl black #1A1A2E (records) with gold grooves, ember #E85A2A (center labels), ivory #FBF5EA (one highlight along the mixer face), gold (keys).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles and one indigo accent inside the piece. Silhouette: the outer edges of both turntables break past the side edges.

Output: 1024×1024 PNG, transparent background. No text, no headphones, no DJ figure, no background, no frame.
```


---

## Market — остальные (M)


### `M1_first_drawer` — «Прицениться» (Simple 💧)

```text
Generate a soft enamel pin: a swing tag being lifted to peek at the price — look first, decide later.

Composition: a vinyl record stands upright, filling the left two thirds of the pin, and from its top edge hangs a blank swing tag on a short string. Two simplified fingers enter from the right and pinch the tag's lower corner, tipping it up toward the viewer to read it. The tag's face is empty — no number, just a ruled line where one would be. One short motion arc shows the tag just lifted.

Palette: vinyl black #1A1A2E (record) with gold #D9A84E grooves, ember #E85A2A (center label), ivory #FBF5EA (tag, fingers) with navy #0B1438 outline, gold (string, ruled line, motion arc).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the fingers break past the right edge, the record past the left and bottom.

Output: 1024×1024 PNG, transparent background. No text, no digits, no currency symbols, no full hand or arm, no background, no frame.
```

### `M2_first_click` — «Первая вылазка» (Simple 💧)

```text
Generate a soft enamel pin: a shop door pushed open with its bell still ringing — the first step outside.

Composition: a shop door standing ajar, hinged open toward the viewer, seen from the outside. Above it, a small brass shopkeeper's bell on a curved bracket swings sharply, with two gold sound arcs on each side of it. Through the open gap, the edge of one record sleeve is visible inside. On the threshold, a single footprint points inward.

Palette: navy #0B1438 (door) with gold #D9A84E frame, handle and bell, ivory #FBF5EA (light in the gap), cobalt #2A4BD7 (visible sleeve edge), gold (sound arcs, footprint outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the open door leaf breaks past the right edge, the bell bracket past the top.

Output: 1024×1024 PNG, transparent background. No text, no signage, no figure, no background, no frame.
```

### `M3_wishlist_hunter` — «Закрыл гештальт» (Notable 🔵)

```text
Generate a soft enamel pin: the exact record sliding into the exact gap it was missing from — the shape finally closes.

Composition: a row of record spines stands packed on a shelf line, and one slot in the middle is empty, its void drawn as a clean gold outline of a missing sleeve. From the upper right, the matching record slides down into that slot at a slight angle, already halfway in, its silhouette exactly matching the outline. Two short gold motion lines trail it.

Palette: navy #0B1438 and cobalt #2A4BD7 (shelf spines), gold #D9A84E (gap outline, motion lines, shelf line), vinyl black #1A1A2E (the arriving record) with an ember #E85A2A label, ivory #FBF5EA (its sleeve).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the arriving record breaks past the upper-right corner, the shelf past both sides.

Output: 1024×1024 PNG, transparent background. No text, no hands, no background, no frame.
```

### `M4_deal_finder` — «Цена-огонь» (Rare 🌸)

```text
Generate a soft enamel pin: a stylus slashing clean through a price tag like a blade — the number never stood a chance.

Composition: a large swing tag hangs at a slight tilt in the center of the pin, and a tonearm sweeps across it diagonally from upper right to lower left, its stylus cutting the tag clean in two. The tag's lower half is already falling away, tipping loose below the cut, and the cut edge glows hot. On the tag's face, a bold downward arrow instead of any number. Two short gold speed lines follow the arm.

Palette: ivory #FBF5EA (tag) with navy #0B1438 outline, gold #D9A84E (tonearm, string, speed lines), ember #E85A2A (glowing cut edge, downward arrow), pink #E89AC0 (a thin border on the tag).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the tonearm's counterweight breaks past the upper-right corner, the falling half of the tag past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no digits, no currency symbols, no flames, no background, no frame.
```

### `M5_regular` — «Завсегдатай» (Rare 🌸)

```text
Generate a soft enamel pin: a doormat worn through by your own footsteps, and the worn path is a vinyl groove.

Composition: a rectangular doormat lies flat, seen from directly above, filling the pin at a slight angle. Its bristle texture is drawn as fine short strokes — except along one curved path where the mat is worn smooth and bare, and that worn path is a spiral groove winding in from the mat's edge toward its center. At the center of the spiral, where the wear is deepest, a small worn circle sits like a record's label. Two faint footprint outlines sit on the path.

Palette: warm brown #2A1E1A (mat bristles), gold #D9A84E (worn spiral path, mat border), ivory #FBF5EA (the worn circle at center), pink #E89AC0 (footprint outlines), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the mat's corners break past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no shoes, no doorway, no background, no frame.
```

### `META_market` — «Рыночный нюх» (Notable 🔵)

```text
Generate a soft enamel pin: a hound following a scent trail straight to a price tag — you smell the number before you see it.

Composition: a dog's head and neck in side profile, facing right, filling the left half of the pin, nose lifted and working. From its nostril, a dashed gold scent trail loops and meanders through the air to the right, curling twice before ending at a small swing tag hanging in the lower right. On the tag's face sits a tiny vinyl record instead of a price. The dog wears a collar with a round gold tag.

Palette: navy #0B1438 (dog) with an ivory #FBF5EA muzzle and brow patch, ember #E85A2A (nose), gold #D9A84E (collar, collar tag, scent trail, tag string), ivory (swing tag), vinyl black #1A1A2E (the record on the tag).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the dog's neck breaks past the left edge, the swing tag past the bottom-right.

Output: 1024×1024 PNG, transparent background. No text, no digits, no full dog body, no background, no frame.
```


---

## Collection value (MV)


### `MV1_appraised` — «Оценено» (Simple 💧)

```text
Generate a soft enamel pin: an auction gavel coming down on a record — the shelf finally has a number.

Composition: an auctioneer's gavel caught at the moment of impact, angled down from the upper right, its head striking a round sound block. Lying flat on that block, taking the strike, is a vinyl record seen face-on. Three short gold impact dashes burst from the contact point, and the record's grooves ripple outward in two arcs.

Palette: warm brown #2A1E1A (gavel handle) with gold #D9A84E bands, navy #0B1438 (gavel head, sound block), vinyl black #1A1A2E (record) with gold grooves, ember #E85A2A (center label), gold (impact dashes).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the gavel handle breaks past the upper-right corner, the block past the bottom.

Output: 1024×1024 PNG, transparent background. No text, no digits, no hands, no background, no frame.
```

### `MV2_50k` — «Полтинник» (Simple 💧)

```text
Generate a soft enamel pin: a piggy bank whose coin slot takes records instead of coins.

Composition: a plump piggy bank in side profile facing left, filling most of the pin, standing on four stubby legs with a curled tail. Along its back, the slot is cut wide and rectangular — sized for a disc, not a coin — and one vinyl record is halfway in, tipped at an angle, its upper half still sticking out. The pig is drawn in clean flat shapes with one dot for the eye and a simple snout.

Palette: cobalt #2A4BD7 (pig) with an ivory #FBF5EA belly and cobalt soft #5C7AE8 shading, gold #D9A84E (slot rim, hoof caps, grooves), vinyl black #1A1A2E (record) with an ember #E85A2A label, navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the record breaks past the top edge, the pig's snout past the left.

Output: 1024×1024 PNG, transparent background. No text, no digits, no coins, no background, no frame.
```

### `MV3_100k` — «Шестизнак» (Notable 🔵)

```text
Generate a soft enamel pin: a banded bundle of notes with a record pressed in as its seal.

Composition: a thick brick of banknotes seen at a three-quarter angle, its many layered edges visible along the side, bound by one broad paper band across the middle. Where the band closes, a vinyl record sits pressed into it like a wax seal — face-on, grooves and label visible, overlapping the band's join. The note edges are drawn as fine stacked lines, texture rather than countable sheets.

Palette: ivory #FBF5EA and cobalt soft #5C7AE8 (note edges), cobalt #2A4BD7 (paper band) with gold #D9A84E trim, vinyl black #1A1A2E (record seal) with gold grooves, ember #E85A2A (center label), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. No sparkles. Silhouette: the bundle breaks past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no digits, no currency symbols, no faces on the notes, no background, no frame.
```

### `MV4_250k` — «Четверть лимона» (Rare 🌸)

```text
Generate a soft enamel pin: a lemon cut into quarters, and one quarter is a wedge of vinyl — a quarter of a million, literally.

Composition: a whole lemon shown from above, sliced into four equal quarters that sit slightly apart with thin gaps between them. Three quarters are ordinary fruit, drawn flat with radiating segment lines and a pale rind. The fourth quarter, at the lower right, is cut from a vinyl record instead: same wedge shape, but filled with concentric groove arcs and a sliver of center label at its inner point. The swap is the whole joke, so that wedge is the darkest thing in the pin.

Palette: gold #D9A84E (lemon rind), ivory #FBF5EA (fruit flesh) with pink #E89AC0 segment lines, vinyl black #1A1A2E (the vinyl quarter) with gold groove arcs, ember #E85A2A (center label sliver), navy #0B1438 (outline).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: the lemon is wider than the frame and breaks past both side edges.

Output: 1024×1024 PNG, transparent background. No text, no digits, no leaves, no background, no frame.
```

### `MV5_500k` — «Сокровищница» (Epic 🌌)

```text
Generate a soft enamel pin: a treasure chest that overflows with records instead of gold.

Composition: a banded wooden chest with a domed lid, seen from the front and thrown wide open, filling the pin. Out of it spill records — five or six discs tumbling over the front rim and down the chest's face, overlapping each other, one balanced on the edge mid-fall. Inside the open lid, a warm glow rises from the pile. The chest's iron bands and lock plate are heavy and gold.

Palette: indigo #1B237D (chest) with gold #D9A84E bands, lock plate and corner caps, vinyl black #1A1A2E (records) with gold grooves, ember #E85A2A (center labels), ivory #FBF5EA (the glow inside the lid).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles and one indigo accent inside the piece. Silhouette: the open lid breaks past the top edge, the spilling records past the bottom and right.

Output: 1024×1024 PNG, transparent background. No text, no coins, no gems, no background, no frame.
```

### `MV6_million` — «Миллионер» (Legend ⚫)

```text
Generate a soft enamel pin: a whole lemon carved entirely from vinyl, wearing a small crown — the full million, not a quarter of it.

Composition: one whole lemon standing upright and centered, filling the pin, its classic tapered oval shape unmistakable. Its entire surface is vinyl: concentric groove lines wrap the body following its curve, and a record's center label sits at the fruit's midpoint like a maker's mark. Balanced on its top nub, a small five-point crown. The form is clean and heavy, no leaves, no stem.

Palette: vinyl black #1A1A2E (lemon body) with gold #D9A84E grooves, ember #E85A2A (center label), gold (crown), ivory #FBF5EA (one specular streak down the left side), navy #0B1438 (outline), indigo #1B237D (shadow side).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Legend tier: add 3 tiny gold four-point sparkles and a second gold rim tracing the whole silhouette. Silhouette: the crown breaks past the top edge, the lemon past both sides.

Output: 1024×1024 PNG, transparent background. No text, no digits, no leaves, no background, no frame.
```

### `MV_crown_jewel` — «Жемчужина» (Rare 🌸)

```text
Generate a soft enamel pin: an oyster opened to reveal a pearl that is a record — one disc worth more than a whole shelf.

Composition: an oyster shell seen from the front, hinged open wide, its two halves fanning up and down with deep radiating ridges along both. Cradled in the lower half, resting on the smooth nacre, sits a single vinyl record standing in for the pearl — face-on, grooves and center label visible, sized so it nearly fills the opening. A soft halo of three thin arcs rises behind it from inside the shell.

Palette: navy #0B1438 (shell exterior) with gold #D9A84E ridge lines, ivory #FBF5EA (nacre interior), vinyl black #1A1A2E (record) with gold grooves, pink #E89AC0 (center label), gold (halo arcs).

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Rare tier: add 2 tiny gold four-point sparkles. Silhouette: both shell halves break past the top and bottom edges.

Output: 1024×1024 PNG, transparent background. No text, no water, no sand, no actual round pearl, no background, no frame.
```


---

## Origins (OG)


### `OG1_first_hundred` — «Первая сотня» (Epic 🌌)

```text
Generate a soft enamel pin: the Vertushka mascot hoisting a big 100 over its head — the app thanking the hundred people who showed up first.

Composition: a cartoon character standing centered, front on. Its head is a large vinyl record: a full circle with concentric groove lines, a small center hole, and a simple face — two half-lidded eyes with heavy angled brows, two round blush patches, and a small confident closed smile. A tonearm lies diagonally across the upper head like a visor, its stylus end resting at the temple. The body is tiny next to the head: two tube arms raised straight overhead and two tube legs in chunky sneakers, one foot lifted mid-step. Held up in both raised hands, above the head, the numeral 100 in bold rounded display digits, sized so it is the second thing you read after the face.

Palette: ivory #FBF5EA (record head) with gold #D9A84E grooves and navy #0B1438 face lines, pink #E89AC0 (cheek blush), cobalt #2A4BD7 (arms, legs, torso) with navy shadow sides, ivory (sneakers) with cobalt trim, gold (the numeral 100, tonearm), navy (outline). Flat fills only: no gradients and no halftone dot texture, even if the character is usually drawn with them.

Style: soft enamel pin — raised gold contour #D9A84E with a 1px dark navy #0B1438 outline, recessed flat enamel, gold divider lines 1.5–2px between color zones, one thin white specular arc per large fill. Epic tier: add 3 tiny gold four-point sparkles and one indigo accent inside the piece. Silhouette: the numeral 100 breaks past the top edge, the lifted foot past the bottom-right.

Output: 1024×1024 PNG, transparent background. No text other than the digits 100, no background, no frame, no gradients, no halftone, no drop shadows.
```

---

## Locked-заглушки серий

Отдельный визуальный язык, не эмаль: тёмный медальон с контурной иконкой и замком. Показывается, пока ачивка закрыта, и выбирается **по серии**, а не по коду ачивки — см. `SERIES_PLACEHOLDERS` в `Mobile/components/AchievementPin.tsx`.

Промты ниже описывают весь набор целиком, включая уже нарисованные, — чтобы при перегенерации язык не разъехался. Иконки существующих серий описаны по факту того, что нарисовано сейчас.

### `foundation` — «Первые шаги» (5)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a young sprout with two leaves rising on a slender stem out of the center of a record — the disc drawn as a wide flat ellipse with a few groove rings and a small center label, the sprout growing straight up from it. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `scale` — «Размер коллекции» (7)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a tall stack of records seen in slight perspective, roughly ten flat ellipses layered one on another, the topmost one showing its center label as a small ellipse with a dot. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `rarity` — «Охота за редкостями» (8)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a cut gemstone seen face-on: a wide flat table at the top, angled crown facets below it, and a pointed pavilion tapering to a tip at the bottom, all as clean straight-edged facet lines. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `geography` — «География» (8)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a globe: a circle crossed by continent outlines, with the record's groove rings showing through the sphere as its parallels so the world and the disc read as the same object. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `eras` — «Эпохи» (7)

Существующая версия сильно детальнее (два кольца подписей, шестерни). Здесь описан упрощённый вариант — при 64 px мелкие подписи всё равно схлопываются в шум.

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: an ornate clock face: an outer ring of tick marks, an inner ring of roman numerals, two hands set at an angle, and a small toothed gear tucked behind the dial at the lower right. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `genres` — «Жанры» (7)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a treble clef on the left standing beside a row of five vertical equalizer bars of uneven height on the right, joined by one horizontal baseline running through both. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `community` — «Сообщество» (11)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a human head in profile facing right, drawn as one continuous outline, with a row of five vertical equalizer bars of uneven height inside the skull where a brain would be. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `contribution` — «Вклад» (6)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: an open hand rising from the bottom, palm up, holding a record above it; above the disc a short upward arrow and one small four-point sparkle. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `discography` — «Дискография» (6)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a square record sleeve seen face-on with a row of equalizer bars inside it, set over a second square rotated 45 degrees behind it so the corners peek out as a star. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `gifts` — «Дарящая рука» (9)

Сейчас нарисована в эмалевом стиле на квадратной подложке 2048×2048 — самая выбивающаяся из набора.

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a gift box seen at a three-quarter angle: a cube with a separate lid line across the top and a wide ribbon bow with two loops sitting on the lid, ribbon bands running down the front faces. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `origins` — «Истоки» (1)

Сейчас отдаёт общий трофей вместе с мета-ачивками. Своя иконка отделит «Истоки» от меты.

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a small pennant flag on a straight pole, planted upright in the center of a record — the disc as a wide flat ellipse with a few groove rings, the flag streaming to the right. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `value` — «Стоимость коллекции» (7)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: three coins stacked one on top of another, seen slightly from the side, the front coin marked with one small concentric circle so it reads as a record. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `market` — «Рыночный нюх» (6)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a swing price tag — a rectangle with one clipped corner and a small hole, hanging from a short looped string, with one concentric circle on its face. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `formats` — «Форматы» (4)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: three overlapping media shapes fanned in a row: a circle, an upright rectangle, and a square, each just an outline, the circle in front. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `cassettes` — «Кассеты» (4)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a compact cassette seen face-on: a rounded rectangle shell with a wide window across the middle and two circles inside it for the reels. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `cds` — «Компакт-диски» (4)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

CENTER ICON — read this carefully, it is the part that usually fails. Dead center of the medallion sits one icon at roughly 45% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue. The icon is a CD jewel case with the disc sliding out of it: a SQUARE with slightly rounded corners, tilted about 10 degrees off upright, and emerging from behind its right edge the right two-thirds of a compact disc, drawn as a circle with a small ring at its middle for the center hole. The square overlaps and hides the left third of the circle. A single short crescent stroke on the exposed part of the disc suggests a sheen.

The square is mandatory and must dominate the icon: a bare circle would vanish into the round grooved medallion behind it, which is the failure to avoid. The icon must NOT be concentric with the medallion — the whole group sits centered, but the disc inside it is pushed to the right of the square, so nothing in the icon shares a center point with the background disc. No ring of the icon may run parallel to the medallion's groove rings.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The icon must read instantly as a silhouette at 64 px: bold strokes, no small internal detail.

Output: 1024×1024 PNG. The area outside the medallion is transparent; the medallion face itself is fully opaque — do not punch a transparent hole through the center or anywhere inside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `boxsets` — «Бокс-сеты» (3)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a boxset seen at a slight angle: a thick rectangular slab with a separate lid line across the top and two narrow sleeve edges poking out of the opening. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `invitations` — «Приглашения» (7)

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: an envelope seen face-on, flap closed and pointing down as a wide V, with one small circle centered on the flap where a wax seal would be. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```

---

## Locked-заглушки особых состояний

Эти две не привязаны к серии: `egg` отдаётся любой скрытой пасхалке до анлока, `trophy` — любой мета-ачивке.

### `egg` — «Пасхалка (скрытая)»

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: an egg standing upright, its outline a clean oval tapering at the top, split down the middle by a jagged lightning-shaped crack running from the top edge to the bottom. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
### `trophy` — «Мета-ачивка»

```text
Generate a locked-achievement placeholder medallion for a vinyl collecting app. This is NOT an enamel pin — it is the dark "still locked" badge shown in the achievements grid.

Composition: one perfect circle centered on a square canvas, filling almost the whole frame. The disc is deep navy with a soft radial gradient, lighter at the center and darkening toward the rim. Across its entire face run faint concentric groove rings, evenly spaced and barely brighter than the disc, like the grooves of a record. The rim carries two thin rings: an outer ring in cobalt blue, and just inside it a second ring in warm gold that fades from bright at the top-left to darker at the bottom-right. Dead center sits a single icon at roughly 40% of the disc width, drawn in OUTLINE ONLY with no fill, in a uniform rounded stroke of cool grey-blue: a two-handled trophy cup on a stepped base: a wide bowl tapering to a short stem, one curled handle on each side, standing on a small plinth. Overlapping the disc's lower-right edge, a small circular badge filled with a warm gold gradient holds a dark navy padlock — a closed shackle above a rounded body with one keyhole dot.

Palette: disc gradient #1B2138 at center to #0A0E1C at rim, groove rings #212A45, outer ring cobalt #2A4BD7, inner ring gold #D9A84E fading to #8A6A2F, center icon stroke #8B93A8, lock badge gold #F0CE86 to #C08A3E with a #0B1438 padlock.

Style: flat vector, clean geometry, no texture, no noise, no photorealism. The center icon must read instantly as a silhouette at small size, so keep it to a few bold strokes and drop any small internal detail.

Output: 1024×1024 PNG, transparent background outside the disc. No text, no numbers, no background, no frame, no drop shadow beyond the disc itself.
```
