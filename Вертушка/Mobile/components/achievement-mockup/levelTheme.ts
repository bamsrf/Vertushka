/**
 * Визуальная идентичность ступеней архетипа.
 *
 * Все десять ступеней «Физики звука» стоят на одной ленте — градиенте
 * айдентики приложения, от почти чёрного фиолетового к почти белому розовому.
 * Ступень отличается от соседней только позицией на ней: выше значит светлее.
 * Отсюда цвет папок, иконки повышения и плашки уровня в разделе ачивок.
 *
 * Ключи совпадают с LevelDef.key из lib/archetype.ts (и с зеркалом на бэкенде
 * Backend/app/services/achievements/levels.py).
 */
/**
 * Палитра ступеней — лента айдентики приложения.
 *
 * Один градиент, снятый с `Design/Color palette.jpeg`: от почти чёрного
 * фиолетового через кобальт к почти белому розовому. Ступень — точка на этой
 * ленте, и ничего кроме позиции её не отличает. Предыдущая лестница гуляла по
 * тонам (графит → синь → пурпур → жар → золото) и жила отдельной жизнью от
 * остального приложения; здесь «выше» значит ровно «светлее».
 *
 * Производные тона считаются не подмешиванием почти-чёрного, а умножением:
 * оно сохраняет тон и насыщенность, тогда как подмешивание уводило бледные
 * верхние ступени в серость.
 *
 * `ink` — контрастный к `base`, выбран по WCAG: ivory на тёмных ступенях,
 * тёмный на светлых. Им рисуются стрелка и канавки иконки повышения, им же
 * обведён её диск — иначе бледный «Первозвук» растворялся бы в светлой ленте
 * уведомлений.
 *
 * `chip` тянут к белилам тем сильнее, чем темнее ступень: у «Тиши» `base` сам
 * почти чёрный и плашка утонула бы в фоне hero.
 *
 * Ключи совпадают с LevelDef.key из lib/archetype.ts.
 */
export interface LevelPalette {
  /** Опорный тон ступени на ленте. */
  base: string;
  /** Осветлённый: верх корпуса папки, светлая сторона диска иконки, обводка плашки. */
  light: string;
  /** Затемнённый: низ клапана папки, тёмная сторона диска иконки. */
  deep: string;
  /** Контрастный к base: стрелка, канавки и обводка диска иконки. */
  ink: string;
  /** Плашка ступени в hero и заливка прогресс-бара. */
  chip: string;
  /** Текст на плашке. */
  chipInk: string;
  /** Верхний и средний стоп фона hero. Держим тёмными: поверх лежит ivory-текст. */
  heroTop: string;
  heroMid: string;
}

export const LEVEL_PALETTE: Record<string, LevelPalette> = {
  // Тишь — почти чёрный фиолетовый низ градиента. Ещё ничего не звучит.
  silence: {
    base: '#0D0A24',
    light: '#565466',
    deep: '#070513',
    ink: '#F4EEE6',
    chip: '#696777',
    chipInk: '#F4EEE6',
    heroTop: '#05040E',
    heroMid: '#030208',
  },
  // Шорох — тьма начинает синеть.
  rustle: {
    base: '#1A1746',
    light: '#5B587A',
    deep: '#0E0D26',
    ink: '#F4EEE6',
    chip: '#676584',
    chipInk: '#F4EEE6',
    heroTop: '#0A091C',
    heroMid: '#06050F',
  },
  // Эхо — синий проступил, но глухой.
  echo: {
    base: '#202C72',
    light: '#5B6497',
    deep: '#121942',
    ink: '#F4EEE6',
    chip: '#626A9C',
    chipInk: '#F4EEE6',
    heroTop: '#0D122E',
    heroMid: '#070A19',
  },
  // Волна — чистый глубокий синий.
  wave: {
    base: '#1C3FA8',
    light: '#546EBD',
    deep: '#112666',
    ink: '#F4EEE6',
    chip: '#5670BE',
    chipInk: '#0B0A22',
    heroTop: '#0B1943',
    heroMid: '#060E25',
  },
  // Резонанс — кобальт, самая насыщенная точка ленты.
  resonance: {
    base: '#2A5AD8',
    light: '#5B80E1',
    deep: '#1B3989',
    ink: '#F4EEE6',
    chip: '#577DE0',
    chipInk: '#0B0A22',
    heroTop: '#112456',
    heroMid: '#091430',
  },
  // Обертон — кобальт светлеет в барвинок.
  overtone: {
    base: '#5B79DB',
    light: '#7E95E3',
    deep: '#3C5092',
    ink: '#0B0A22',
    chip: '#7790E1',
    chipInk: '#0B0A22',
    heroTop: '#243058',
    heroMid: '#141B30',
  },
  // Амплитуда — цвет отдаёт светлоту, насыщенность падает.
  amplitude: {
    base: '#8193DF',
    light: '#99A8E5',
    deep: '#59669B',
    ink: '#0B0A22',
    chip: '#91A1E3',
    chipInk: '#0B0A22',
    heroTop: '#343B59',
    heroMid: '#1C2031',
  },
  // Частота — бледная лаванда.
  frequency: {
    base: '#A9AEE3',
    light: '#B8BCE8',
    deep: '#7A7EA4',
    ink: '#0B0A22',
    chip: '#B0B5E5',
    chipInk: '#0B0A22',
    heroTop: '#44465B',
    heroMid: '#252632',
  },
  // Камертон — сирень уходит в розовое.
  tuning_fork: {
    base: '#CDC3DF',
    light: '#D5CCE4',
    deep: '#9A92A7',
    ink: '#0B0A22',
    chip: '#CFC6E0',
    chipInk: '#0B0A22',
    heroTop: '#524E59',
    heroMid: '#2D2B31',
  },
  // Первозвук — почти белый розовый. Предел ленты.
  primal_sound: {
    base: '#F2D3DC',
    light: '#F4D9E1',
    deep: '#BDA5AC',
    ink: '#0B0A22',
    chip: '#F2D3DC',
    chipInk: '#0B0A22',
    heroTop: '#615458',
    heroMid: '#352E30',
  },
};

/** Палитра ступени по ключу. Неизвестный ключ → «Эхо». */
export function levelPalette(key: string): LevelPalette {
  return LEVEL_PALETTE[key] ?? LEVEL_PALETTE.echo;
}

export interface LevelTheme {
  /** Три стопа вертикального градиента фона (сверху вниз). */
  bg: readonly [string, string, string];
  /** Тёплый radial-подсвет из угла: [цвет с альфой, прозрачный]. */
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
}

/** hex → rgba(). Альфа нужна ореолам и обводкам, а палитра хранит чистый тон. */
function alpha(hex: string, a: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/**
 * Плотность «волн» на фоне hero растёт со ступенью — единственное, что не
 * выводится из палитры, поэтому лежит таблицей.
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
 * Тема hero целиком выводится из `LEVEL_PALETTE` — своей таблицы цветов у неё
 * больше нет. Раньше здесь жил отдельный набор (золотая плашка «Эха», медь
 * «Частоты», бронза «Камертона»), и он расходился с остальным приложением.
 *
 * Фон намеренно берёт только тёмные стопы ленты: поверх него лежит ivory-текст
 * и пины, и светлые верхние ступени сделали бы его нечитаемым. Светлоту ступени
 * несут плашка и прогресс-бар — они как раз идут по ленте до почти белого.
 */
function themeFor(key: string): LevelTheme {
  const p = levelPalette(key);
  return {
    bg: [p.heroTop, p.heroMid, '#05060F'],
    glow: [alpha(p.light, 0.3), alpha(p.light, 0)],
    chipBg: p.chip,
    chipFg: p.chipInk,
    chipBorder: p.light,
    accent: p.chip,
    halo: alpha(p.light, 0.32),
    discBg: p.deep,
    rim: alpha(p.light, 0.32),
    grooveOpacity: GROOVE_OPACITY[key] ?? 0.07,
  };
}

export const LEVEL_THEMES: Record<string, LevelTheme> = Object.fromEntries(
  Object.keys(LEVEL_PALETTE).map((key) => [key, themeFor(key)]),
);

/** Тема уровня по ключу. Неизвестный ключ → «Эхо». */
export function levelTheme(key: string): LevelTheme {
  return LEVEL_THEMES[key] ?? LEVEL_THEMES.echo;
}
