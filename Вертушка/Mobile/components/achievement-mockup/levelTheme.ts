/**
 * Визуальная идентичность ступеней архетипа — лента айдентики приложения.
 *
 * Все десять ступеней «Физики звука» стоят на одном градиенте, снятом с
 * `Design/Color palette.jpeg`: от почти чёрного фиолетового через кобальт к
 * почти белому розовому. Ступень — точка на этой ленте, и ничего кроме позиции
 * её не отличает: «выше» значит ровно «светлее». Отсюда цвет папок, иконки
 * повышения, карточки уровня в разделе ачивок и chip-а в профиле.
 *
 * **Ступень несёт САМА КАРТОЧКА, а не мелкая плашка на ней.** Раньше фон hero
 * считался затемнением `base` и упирался в общий для всех почти чёрный стоп:
 * шаг между соседними ступенями падал до ΔE 3–5, а плашка на тёмных ступенях
 * тянулась к белилам и первые четыре ступени сходились в один тон (L* 52, 52,
 * 54, 56). На экране «Волна» и «Обертон» читались как одна и та же тёмно-синяя
 * карточка, хотя сам `base` разведён отлично — L* от 17 до 90, ΔE 8–10 на шаг.
 * Теперь `base` и есть поверхность карточки, а цвет текста выбирается под неё.
 *
 * Пересэмплировать исходник смысла нет: текущие значения уже совпадают с ним по
 * светлоте, насыщенности и тону с точностью до пары единиц, и запаса там больше
 * нет — сам градиент однотонный (H 262–270 почти на всём протяжении, C ≤ 22).
 *
 * Производные тона считаются не подмешиванием почти-чёрного, а умножением: оно
 * сохраняет тон и насыщенность, тогда как подмешивание уводило бледные верхние
 * ступени в серость.
 *
 * Ключи совпадают с LevelDef.key из lib/archetype.ts (и с зеркалом на бэкенде
 * Backend/app/services/achievements/levels.py).
 */
export interface LevelPalette {
  /** Опорный тон ступени на ленте. Он же — поверхность карточки уровня. */
  base: string;
  /** Осветлённый: верх корпуса папки, светлая сторона диска иконки. */
  light: string;
  /** Затемнённый: низ клапана папки, тёмная сторона диска иконки, гнездо пина. */
  deep: string;
  /** Контрастный к base: стрелка, канавки и обводка диска иконки повышения. */
  ink: string;
  /** Плашка ступени на СВЕТЛОЙ поверхности — профиль. Пара под контраст ≥ 4.5. */
  soft: string;
  softInk: string;
  softBorder: string;
}

export const LEVEL_PALETTE: Record<string, LevelPalette> = {
  // Тишь — почти чёрный фиолетовый низ градиента. Ещё ничего не звучит.
  silence: {
    base: '#0D0A24',
    light: '#565466',
    deep: '#070513',
    ink: '#F4EEE6',
    soft: '#DDDDE0',
    softInk: '#0D0A24',
    softBorder: '#7F7E8B',
  },
  // Шорох — тьма начинает синеть.
  rustle: {
    base: '#1A1746',
    light: '#5B587A',
    deep: '#0E0D26',
    ink: '#F4EEE6',
    soft: '#D7D7DF',
    softInk: '#1A1746',
    softBorder: '#82819A',
  },
  // Эхо — синий проступил, но глухой.
  echo: {
    base: '#202C72',
    light: '#5B6497',
    deep: '#121942',
    ink: '#F4EEE6',
    soft: '#D1D3E2',
    softInk: '#202C72',
    softBorder: '#8188B0',
  },
  // Волна — чистый глубокий синий.
  wave: {
    base: '#1C3FA8',
    light: '#546EBD',
    deep: '#112666',
    ink: '#F4EEE6',
    soft: '#C9D1EA',
    softInk: '#1C3FA8',
    softBorder: '#7B8FCC',
  },
  // Резонанс — кобальт, самая насыщенная точка ленты.
  resonance: {
    base: '#2A5AD8',
    light: '#5B80E1',
    deep: '#1B3989',
    ink: '#F4EEE6',
    soft: '#C5D2F4',
    softInk: '#2651C2',
    softBorder: '#7D98DE',
  },
  // Обертон — кобальт светлеет в барвинок.
  overtone: {
    base: '#5B79DB',
    light: '#7E95E3',
    deep: '#3C5092',
    ink: '#0B0A22',
    soft: '#CDD6F4',
    softInk: '#405599',
    softBorder: '#8E9CCB',
  },
  // Амплитуда — цвет отдаёт светлоту, насыщенность падает.
  amplitude: {
    base: '#8193DF',
    light: '#99A8E5',
    deep: '#59669B',
    ink: '#0B0A22',
    soft: '#D4DAF4',
    softInk: '#4D5886',
    softBorder: '#97A0C2',
  },
  // Частота — бледная лаванда.
  frequency: {
    base: '#A9AEE3',
    light: '#B8BCE8',
    deep: '#7A7EA4',
    ink: '#0B0A22',
    soft: '#DFE1F5',
    softInk: '#5D607D',
    softBorder: '#A4A7BF',
  },
  // Камертон — сирень уходит в розовое.
  tuning_fork: {
    base: '#CDC3DF',
    light: '#D5CCE4',
    deep: '#9A92A7',
    ink: '#0B0A22',
    soft: '#EBE7F2',
    softInk: '#66616F',
    softBorder: '#AFABB7',
  },
  // Первозвук — почти белый розовый. Предел ленты.
  primal_sound: {
    base: '#F2D3DC',
    light: '#F4D9E1',
    deep: '#BDA5AC',
    ink: '#0B0A22',
    soft: '#F9ECF0',
    softInk: '#79696E',
    softBorder: '#BFB1B6',
  },};

/** Палитра ступени по ключу. Неизвестный ключ → «Эхо». */
export function levelPalette(key: string): LevelPalette {
  return LEVEL_PALETTE[key] ?? LEVEL_PALETTE.echo;
}

export interface LevelTheme {
  /** Три стопа вертикального градиента фона (сверху вниз). */
  bg: readonly [string, string, string];
  /** Radial-подсвет из угла: [цвет с альфой, прозрачный]. */
  glow: readonly [string, string];
  /** Заливка плашки уровня. */
  chipBg: string;
  /** Текст и точка на плашке. */
  chipFg: string;
  /** Обводка плашки. */
  chipBorder: string;
  /** Акцент: заливка прогресс-бара, маркер, звёздочки. */
  accent: string;
  /** Гало вокруг гнезда пина. */
  halo: string;
  /** Заливка диска под пином. */
  discBg: string;
  /** Обводка всей карточки. */
  rim: string;
  /** Прозрачность концентрических «волн» на фоне. */
  grooveOpacity: number;
  /** Основной текст поверх карточки — ivory на тёмных ступенях, тёмный на светлых. */
  ink: string;
  /** Вторичный текст. */
  inkDim: string;
  /** Третичный текст: подписи, флейвор, XP. */
  inkMuted: string;
  /** Подложка карточки под градиентом. */
  surface: string;
  /** Дорожка прогресс-бара. */
  trackBg: string;
  /** Полупрозрачная заливка пустого гнезда. */
  veil: string;
}

const IVORY = '#F4EEE6';
const DARK_INK = '#0B0A22';

/** Минимальный контраст текста к фону: WCAG AA для обычного текста. */
const TEXT_CONTRAST = 4.6;

function toRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toHex(c: [number, number, number]): string {
  return (
    '#' +
    c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
  ).toUpperCase();
}

/** Умножение канала: темнит, сохраняя тон и насыщенность. */
function mul(hex: string, f: number): string {
  return toHex(toRgb(hex).map((v) => v * f) as [number, number, number]);
}

function mix(a: string, b: string, t: number): string {
  const x = toRgb(a);
  const y = toRgb(b);
  return toHex([0, 1, 2].map((i) => x[i] + (y[i] - x[i]) * t) as [number, number, number]);
}

/** hex → rgba(). Альфа нужна ореолам и обводкам, а палитра хранит чистый тон. */
function alpha(hex: string, a: number): string {
  const [r, g, b] = toRgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}

function luminance(hex: string): number {
  const ch = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = toRgb(hex);
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}

function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/** Цвет текста, который лучше читается на этом фоне. */
function inkFor(bg: string): string {
  return contrast(IVORY, bg) >= contrast(DARK_INK, bg) ? IVORY : DARK_INK;
}

/**
 * Отодвигает фон от чернил, пока не наберётся нужный контраст.
 *
 * Нужен ровно для середины ленты: на L* около 50–60 («Резонанс», «Обертон»)
 * ни ivory, ни тёмный текст не набирают AA — это мёртвая зона, куда `base`
 * попадает буквально одной-двумя ступенями. Их и подталкиваем, остальные
 * девять проходят порог нетронутыми.
 */
function ensureContrast(bg: string, ink: string, target: number): string {
  const away = (c: string) => (ink === IVORY ? mul(c, 0.96) : mix(c, '#FFFFFF', 0.05));
  let out = bg;
  for (let i = 0; i < 40 && contrast(ink, out) < target; i++) out = away(out);
  return out;
}

/**
 * Верхний и нижний стопы градиента карточки вокруг середины.
 *
 * Уходят ОТ чернил: тёмные ступени темнеют книзу, светлые светлеют. Наоборот
 * нельзя — затемнение светлой ступени загоняет её низ в мёртвую зону, где
 * тёмный текст перестаёт читаться.
 */
function gradientStops(mid: string, onDark: boolean): [string, string] {
  return onDark
    ? [mix(mid, '#FFFFFF', 0.1), mul(mid, 0.6)]
    : [mul(mid, 0.96), mix(mid, '#FFFFFF', 0.3)];
}

/**
 * Плотность «волн» на фоне растёт со ступенью — единственное, что не выводится
 * из палитры, поэтому лежит таблицей.
 */
const GROOVE_OPACITY: Record<string, number> = {
  silence: 0.05,
  rustle: 0.06,
  echo: 0.07,
  wave: 0.08,
  resonance: 0.09,
  overtone: 0.09,
  amplitude: 0.1,
  frequency: 0.1,
  tuning_fork: 0.11,
  primal_sound: 0.12,
};

/**
 * Тема карточки целиком выводится из `LEVEL_PALETTE` — своей таблицы цветов у
 * неё нет.
 *
 * Направление градиента внутри карточки — см. gradientStops.
 */
function themeFor(key: string): LevelTheme {
  const p = levelPalette(key);
  const ink = inkFor(p.base);
  const onDark = ink === IVORY;

  // Порог проверяем по ВСЕМ трём стопам, а не по середине: у тёмных ступеней
  // верхний стоп светлее середины, у светлых нижний светлее — и «Резонанс»
  // проваливался в 4.2 именно там, хотя его середина порог держала.
  let mid = p.base;
  for (let i = 0; i < 40; i++) {
    const [t, b] = gradientStops(mid, onDark);
    const worst = Math.min(contrast(ink, t), contrast(ink, mid), contrast(ink, b));
    if (worst >= TEXT_CONTRAST) break;
    mid = onDark ? mul(mid, 0.96) : mix(mid, '#FFFFFF', 0.05);
  }
  const [top, bottom] = gradientStops(mid, onDark);

  const chipBg = ensureContrast(
    onDark ? mix(mid, '#FFFFFF', 0.34) : mul(mid, 0.6),
    onDark ? DARK_INK : IVORY,
    TEXT_CONTRAST,
  );
  const chipFg = inkFor(chipBg);

  return {
    bg: [top, mid, bottom],
    glow: [alpha(onDark ? p.light : '#FFFFFF', 0.28), alpha(onDark ? p.light : '#FFFFFF', 0)],
    chipBg,
    chipFg,
    chipBorder: mix(chipBg, chipFg, 0.35),
    accent: chipBg,
    halo: alpha(ink, 0.14),
    discBg: p.deep,
    rim: alpha(ink, 0.22),
    grooveOpacity: GROOVE_OPACITY[key] ?? 0.07,
    ink,
    inkDim: mix(ink, mid, 0.25),
    inkMuted: mix(ink, mid, 0.42),
    surface: mid,
    trackBg: alpha(ink, 0.16),
    veil: alpha(ink, 0.08),
  };
}

export const LEVEL_THEMES: Record<string, LevelTheme> = Object.fromEntries(
  Object.keys(LEVEL_PALETTE).map((key) => [key, themeFor(key)]),
);

/** Тема уровня по ключу. Неизвестный ключ → «Эхо». */
export function levelTheme(key: string): LevelTheme {
  return LEVEL_THEMES[key] ?? LEVEL_THEMES.echo;
}
