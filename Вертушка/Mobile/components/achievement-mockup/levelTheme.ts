/**
 * Визуальная идентичность ступеней архетипа — лента айдентики приложения.
 *
 * Все десять ступеней «Физики звука» стоят на одном градиенте, снятом с
 * `Design/Color palette.jpeg`: от почти чёрного фиолетового через кобальт к
 * чистому белому ЧЕРЕЗ РОЗОВЫЙ. Верх ленты доведён до #FFFFFF, а точки разложены
 * равными шагами по светлоте: прежняя выборка давала неровные шаги (ΔE от
 * 7.1 до 10.3) и упиралась в бледно-розовый, теперь шаг 9.3–10.7 при том же
 * тоне и насыщенности — они берутся из кривой самого градиента.
 *
 * Исключение — верхние четыре ступени. Кривая исходника доворачивает тон к
 * розовому только на самом верху (Обертон 271°, Амплитуда 278°, Частота 299°)
 * и к тому моменту гасит насыщенность до 3–5: розовое мелькало одной ступенью
 * и почти не читалось. Поэтому от точки переворота чернил тон разворачивается
 * вручную (290° → 315° → 335° → 352°), а насыщенность держится (13 → 6.5), и к
 * белому лента приходит через четыре внятно розовых шага.
 *
 * Белый верх обязан иметь контур: тело «Первозвука» неотличимо от светлого
 * фона приложения. Роль контура несёт `deep` — он затемнён от `base` по
 * построению и потому виден на любой ступени (контраст к фону ≥ 2.6). Ступень — точка на этой ленте, и ничего кроме позиции
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
  /** Затемнённый: низ клапана, тёмная сторона диска, контур силуэта папки. */
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
    base: '#0E0A25',
    light: '#565466',
    deep: '#090617',
    ink: '#F4EEE6',
    soft: '#D4D3D8',
    softInk: '#0E0A25',
    softBorder: '#7B7987',
  },
  // Шорох — тьма начинает синеть.
  rustle: {
    base: '#1B1A4B',
    light: '#5F5F81',
    deep: '#11102E',
    ink: '#F4EEE6',
    soft: '#D6D6DF',
    softInk: '#1B1A4B',
    softBorder: '#82819C',
  },
  // Эхо — синий проступил, но глухой.
  echo: {
    base: '#212C77',
    light: '#646BA0',
    deep: '#141B4A',
    ink: '#F4EEE6',
    soft: '#D7D9E7',
    softInk: '#212C77',
    softBorder: '#858BB5',
  },
  // Волна — чистый глубокий синий.
  wave: {
    base: '#2240A6',
    light: '#6479C1',
    deep: '#152867',
    ink: '#F4EEE6',
    soft: '#D7DDEF',
    softInk: '#2240A6',
    softBorder: '#8696CE',
  },
  // Резонанс — кобальт, самая насыщенная точка ленты.
  resonance: {
    base: '#2F57CB',
    light: '#6D89DB',
    deep: '#1D367E',
    ink: '#F4EEE6',
    soft: '#DAE1F6',
    softInk: '#2F57CB',
    softBorder: '#8DA3E3',
  },
  // Обертон — кобальт светлеет в барвинок.
  overtone: {
    base: '#8C7DD5',
    light: '#AEA4E2',
    deep: '#574E84',
    ink: '#0B0A22',
    soft: '#EAE8F7',
    softInk: '#675C9C',
    softBorder: '#AFA9CE',
  },
  // Амплитуда — цвет отдаёт светлоту, насыщенность падает.
  amplitude: {
    base: '#C391D9',
    light: '#D5B2E4',
    deep: '#795A87',
    ink: '#0B0A22',
    soft: '#F4EBF8',
    softInk: '#7E5E8C',
    softBorder: '#BFACC7',
  },
  // Частота — бледная лаванда.
  frequency: {
    base: '#F2ACCA',
    light: '#F6C5DA',
    deep: '#966B7D',
    ink: '#0B0A22',
    soft: '#FDF0F5',
    softInk: '#8A6275',
    softBorder: '#C9B0BB',
  },
  // Камертон — сирень уходит в розовое.
  tuning_fork: {
    base: '#FDDDA0',
    light: '#FEE7BC',
    deep: '#9D8963',
    ink: '#0B0A22',
    soft: '#FFF9EE',
    softInk: '#807051',
    softBorder: '#C6BBA7',
  },
  // Первозвук — почти белый розовый. Предел ленты.
  primal_sound: {
    base: '#FFFFFF',
    light: '#FFFFFF',
    deep: '#9E9E9E',
    ink: '#0B0A22',
    soft: '#FFFFFF',
    softInk: '#727272',
    softBorder: '#C0C0C0',
  },
};

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
