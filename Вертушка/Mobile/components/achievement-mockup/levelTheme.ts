/**
 * Визуальная идентичность уровней архетипа.
 *
 * Каждая из 10 ступеней «Физики звука» получает свой фон hero-блока и окрас
 * плашки. Драматургия лестницы: холодная тишина → синева → пурпур резонанса →
 * жар амплитуды → золото легенды. Уровень должно быть видно с полувзгляда,
 * не читая подпись.
 *
 * Ключи совпадают с LevelDef.key из lib/archetype.ts (и с зеркалом на бэкенде
 * Backend/app/services/achievements/levels.py).
 */
import {
  M_EMBER,
  M_GOLD,
  M_GOLD_HI,
  M_GOLD_RIM_SOFT,
  M_IVORY,
  M_NAVY,
  M_NAVY_MID,
} from './palette';

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
  /** Заливка диска под пином. Держим в семье фона ступени: единый navy на
   *  золотом «Первозвуке» читался как чужая деталь. */
  discBg: string;
  /** Обводка всей карточки. */
  rim: string;
  /** Прозрачность концентрических «волн» на фоне. */
  grooveOpacity: number;
}

const IVORY_ON_DARK = M_IVORY;

export const LEVEL_THEMES: Record<string, LevelTheme> = {
  // 0 — Тишь: почти чёрная синева, минимум света. Ещё ничего не звучит.
  silence: {
    bg: ['#131A3D', '#0B1438', '#05091C'],
    glow: ['rgba(92,122,232,0.16)', 'rgba(92,122,232,0)'],
    chipBg: 'rgba(244,238,230,0.10)',
    chipFg: IVORY_ON_DARK,
    chipBorder: 'rgba(244,238,230,0.28)',
    accent: '#8FA2D8',
    halo: 'rgba(143,162,216,0.20)',
    discBg: '#101638',
    rim: 'rgba(244,238,230,0.14)',
    grooveOpacity: 0.05,
  },
  // 1 — Шорох: первая искра тепла в холодном фоне.
  rustle: {
    bg: ['#18225A', '#0D1640', '#070C24'],
    glow: ['rgba(92,122,232,0.26)', 'rgba(92,122,232,0)'],
    chipBg: 'rgba(244,238,230,0.92)',
    chipFg: M_NAVY,
    chipBorder: 'rgba(168,126,50,0.55)',
    accent: '#C9D2F2',
    halo: 'rgba(92,122,232,0.28)',
    discBg: '#131C4C',
    rim: 'rgba(244,238,230,0.16)',
    grooveOpacity: 0.06,
  },
  // 2 — Эхо: базовый navy мокапа, золотая плашка. Точка отсчёта серии.
  echo: {
    bg: ['#1B237D', '#0B1438', '#070C24'],
    glow: ['rgba(110,91,198,0.35)', 'rgba(110,91,198,0)'],
    chipBg: M_IVORY,
    chipFg: M_NAVY,
    chipBorder: M_GOLD,
    accent: M_GOLD_HI,
    halo: 'rgba(232,90,42,0.25)',
    discBg: M_NAVY_MID,
    rim: M_GOLD_RIM_SOFT,
    grooveOpacity: 0.07,
  },
  // 3 — Волна: кобальт выходит на первый план, фон «качает».
  wave: {
    bg: ['#22389B', '#101B4E', '#070C24'],
    glow: ['rgba(42,75,215,0.42)', 'rgba(42,75,215,0)'],
    chipBg: '#DDE6FF',
    chipFg: '#16205C',
    chipBorder: '#5C7AE8',
    accent: '#7FA0FF',
    halo: 'rgba(42,75,215,0.35)',
    discBg: '#16265E',
    rim: 'rgba(124,154,255,0.32)',
    grooveOpacity: 0.08,
  },
  // 4 — Резонанс: пурпур, фон начинает «гудеть».
  resonance: {
    bg: ['#3A2A8E', '#1B1550', '#0A0722'],
    glow: ['rgba(150,96,214,0.45)', 'rgba(150,96,214,0)'],
    chipBg: '#EADEFF',
    chipFg: '#2B1A63',
    chipBorder: '#9B6BD8',
    accent: '#C79BF2',
    halo: 'rgba(150,96,214,0.38)',
    discBg: '#231A5E',
    rim: 'rgba(199,155,242,0.34)',
    grooveOpacity: 0.09,
  },
  // 5 — Обертон: пурпур с розовым подтоном — призвук над основным тоном.
  overtone: {
    bg: ['#54277F', '#26124B', '#0C0620'],
    glow: ['rgba(214,106,180,0.45)', 'rgba(214,106,180,0)'],
    chipBg: '#FBE0F2',
    chipFg: '#43164F',
    chipBorder: '#D66AB4',
    accent: '#F09BD8',
    halo: 'rgba(214,106,180,0.40)',
    discBg: '#331A55',
    rim: 'rgba(240,155,216,0.34)',
    grooveOpacity: 0.09,
  },
  // 6 — Амплитуда: жар. Коллекция давит на воздух.
  amplitude: {
    bg: ['#7A2B4C', '#3A122C', '#120616'],
    glow: ['rgba(232,90,42,0.50)', 'rgba(232,90,42,0)'],
    chipBg: '#FFE0D2',
    chipFg: '#5B1A1A',
    chipBorder: M_EMBER,
    accent: '#FF8A5C',
    halo: 'rgba(232,90,42,0.45)',
    discBg: '#4A1A2E',
    rim: 'rgba(255,138,92,0.36)',
    grooveOpacity: 0.10,
  },
  // 7 — Частота: раскалённая медь, точность настройки.
  frequency: {
    bg: ['#8E3A22', '#48170F', '#150707'],
    glow: ['rgba(255,150,60,0.48)', 'rgba(255,150,60,0)'],
    chipBg: '#FFEBD0',
    chipFg: '#5A2708',
    chipBorder: '#E08A3C',
    accent: '#FFB05C',
    halo: 'rgba(255,150,60,0.45)',
    discBg: '#54200F',
    rim: 'rgba(255,176,92,0.38)',
    grooveOpacity: 0.10,
  },
  // 8 — Камертон: золото на глубоком бронзовом. К тебе приходят сверяться.
  tuning_fork: {
    bg: ['#6E5220', '#33240D', '#120C04'],
    glow: ['rgba(242,199,112,0.45)', 'rgba(242,199,112,0)'],
    chipBg: '#FFF3D6',
    chipFg: '#3F2C08',
    chipBorder: M_GOLD_HI,
    accent: M_GOLD_HI,
    halo: 'rgba(58,42,16,0.85)',
    discBg: '#3A2A10',
    rim: 'rgba(242,199,112,0.45)',
    grooveOpacity: 0.11,
  },
  // 9 — Первозвук: почти белое золото на чёрном. Предел лестницы.
  primal_sound: {
    bg: ['#3D3216', '#150F04', '#000000'],
    glow: ['rgba(255,240,200,0.40)', 'rgba(255,240,200,0)'],
    chipBg: '#FFFAF0',
    chipFg: '#1A1206',
    chipBorder: '#FFF0C4',
    accent: '#FFF0C4',
    halo: 'rgba(32,26,10,0.9)',
    discBg: '#151206',
    rim: 'rgba(255,240,200,0.55)',
    grooveOpacity: 0.12,
  },
};

/** Тема уровня по ключу. Неизвестный ключ → «Эхо» (базовый navy мокапа). */
export function levelTheme(key: string): LevelTheme {
  return LEVEL_THEMES[key] ?? LEVEL_THEMES.echo;
}

/**
 * Акцент иконки повышения уровня — см. components/LevelUpIcon.tsx.
 *
 * Почему отдельно от `LevelTheme.accent`: тот подобран под прогресс-бар и
 * маркер на конкретном фоне своей ступени. У «Эха» он золотой (M_GOLD_HI) —
 * в hero это читается, но в лестнице иконок золото между двумя синими рвёт
 * прогрессию. А иконку видно вне hero: в пуше, в ленте «Ты», в шапке. Ей
 * нужна монотонная драматургия холод → синь → пурпур → жар → золото → свет,
 * различимая без подписи.
 *
 * Шаг между соседями идёт сразу по трём осям — тон, насыщенность, светлота.
 * Одного тона мало: первые ступени в hero-палитре все синие и в ряду иконок
 * сливались в одно пятно.
 *
 * Ключи те же, что у LEVEL_THEMES. Порядок = порядок LEVELS в lib/archetype.ts.
 */
export const LEVEL_ICON_ACCENT: Record<string, string> = {
  silence: '#7F8798',       // тусклый серый — ещё ничего не звучит
  rustle: '#7E9BC8',        // та же светлота, но появился цвет
  echo: '#5C93F5',
  wave: '#3E63E8',          // кобальт бренда — «Волна» и есть базовая нота
  resonance: '#9B6BE8',
  overtone: '#E070C8',
  amplitude: '#FF6A4A',
  frequency: '#FF9E2B',
  tuning_fork: '#E8C24A',
  primal_sound: '#FFEFA8',  // белое золото — предел лестницы
};

/** Акцент иконки уровня по ключу. Неизвестный ключ → «Эхо». */
export function levelIconAccent(key: string): string {
  return LEVEL_ICON_ACCENT[key] ?? LEVEL_ICON_ACCENT.echo;
}

/**
 * Корпус иконки папки — верхний и нижний стоп градиента.
 *
 * Почему не `LevelTheme.bg`: тот рассчитан на полноэкранный тёмный фон hero,
 * где все ступени намеренно глубокие. Иконка 80 px живёт на светлом #FAFBFF,
 * её видно мельком в горизонтальном скролле, и ступень должна читаться
 * с полувзгляда — поэтому здесь и насыщенность выше, и разброс по светлоте
 * больше. «Первозвук» тут прямо золотой, а не бронзовый: это вершина
 * лестницы, и в коллекции она должна светиться.
 *
 * Ключи те же, что у LEVEL_THEMES. См. components/FolderIcon.tsx.
 */
export const LEVEL_FOLDER_BODY: Record<string, readonly [string, string]> = {
  silence: ['#3E4657', '#232833'],       // графит, цвета почти нет
  rustle: ['#35486E', '#1C2740'],        // сталь с синевой
  echo: ['#24479E', '#12224F'],          // глубокий синий
  wave: ['#2F62E0', '#16307A'],          // яркий кобальт
  resonance: ['#6A45C8', '#331F66'],
  overtone: ['#A63FAE', '#4E1B57'],
  amplitude: ['#C93A66', '#5F1730'],
  frequency: ['#E2622A', '#6E2410'],
  tuning_fork: ['#C98A2E', '#5E3D0F'],   // бронзовое золото
  primal_sound: ['#FFD24F', '#B8801C'],  // яркое золото — предел лестницы
};

/** Градиент корпуса папки по ключу ступени. Неизвестный ключ → «Эхо». */
export function levelFolderBody(key: string): readonly [string, string] {
  return LEVEL_FOLDER_BODY[key] ?? LEVEL_FOLDER_BODY.echo;
}
