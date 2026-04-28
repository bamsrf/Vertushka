export type VinylColorType = 'solid' | 'translucent' | 'marble' | 'splatter' | 'swirl' | 'cic' | 'black';

export interface VinylColorConfig {
  type: VinylColorType;
  primaryColor: string;
  secondaryColor?: string;
  tertiaryColor?: string;
  opacity: number;
  isColored: boolean;
}

const BLACK: VinylColorConfig = {
  type: 'black',
  primaryColor: '#1A1A1A',
  opacity: 1,
  isColored: false,
};

// ── Ключевые слова-модификаторы ────────────────────────────────
// Эти слова описывают прозрачность, а не цвет — не идут в COLOR_MAP.
// detectType/detectOpacity их читают отдельно.
const TRANSLUCENT_MODIFIERS = ['translucent', 'transparent', 'frosted'];
const CLEAR_MODIFIERS = ['clear', 'crystal'];

// ── COLOR_MAP: ключевое слово → hex ───────────────────────────
// Compound-ключи (длиннее) имеют приоритет над одиночными.
// 'translucent' / 'transparent' / 'clear' / 'crystal' сюда НЕ входят —
// они модификаторы, иначе "Amber Translucent" ложно даёт 2 цвета → CIC.
const COLOR_MAP: Record<string, string> = {
  // ── Красный ──
  red:          '#E53935',
  crimson:      '#C62828',
  maroon:       '#880E4F',
  scarlet:      '#D32F2F',
  'opaque red': '#E53935',

  // ── Синий ──
  blue:           '#1E88E5',
  cobalt:         '#1565C0',
  navy:           '#0D47A1',
  sapphire:       '#1A237E',
  indigo:         '#3949AB',
  'ice blue':     '#B3E5FC',
  'sky blue':     '#4FC3F7',
  'blue sky':     '#4FC3F7',
  'geneva blue':  '#1E88E5',   // Tyler CMIYGL Estate Sale
  'columbia blue':'#1E88E5',
  'opaque blue':  '#1E88E5',

  // ── Зелёный ──
  green:           '#43A047',
  emerald:         '#2E7D32',
  lime:            '#C6FF00',
  teal:            '#00897B',
  olive:           '#827717',
  turquoise:       '#00BCD4',
  aqua:            '#00BCD4',
  mint:            '#A5D6A7',
  // Compound-ключи для составных зелёных — длиннее, поэтому матчатся первыми,
  // и отдельные 'seafoam' + 'green' не добавляют второй цвет.
  'seafoam green': '#4DB6AC',
  'forest green':  '#2E7D32',
  'neon green':    '#76FF03',
  'crystal green': '#43A047',
  'opaque green':  '#43A047',
  seafoam:         '#4DB6AC',

  // ── Жёлтый ──
  yellow:      '#FDD835',
  lemon:       '#FFEE58',
  cream:       '#FFF8E1',
  ivory:       '#FFFFF0',
  butter:      '#FFF9C4',
  'neon yellow': '#F4FF81',

  // ── Оранжевый ──
  orange:       '#FB8C00',
  amber:        '#FF8F00',
  gold:         '#FFD600',
  golden:       '#FFD600',
  bronze:       '#CD7F32',
  copper:       '#B87333',
  caramel:      '#C68642',
  'neon orange':'#FF6D00',
  'liquid smoke':'#9E9E9E',

  // ── Розовый / Маджента ──
  pink:         '#EC407A',
  magenta:      '#E040FB',
  rose:         '#F06292',
  fuchsia:      '#E040FB',
  coral:        '#FF7043',
  salmon:       '#FF8A65',
  peach:        '#FFAB91',
  'baby pink':  '#F8BBD9',
  'light pink': '#F8BBD9',
  'neon pink':  '#FF4081',
  'neon magenta':'#FF4081',

  // ── Фиолетовый ──
  purple:    '#8E24AA',
  violet:    '#7B1FA2',
  lavender:  '#CE93D8',
  lilac:     '#CE93D8',
  plum:      '#6A1B9A',
  grape:     '#6A1B9A',
  mauve:     '#AB47BC',
  psychedelic: '#7B1FA2',

  // ── Белый / Серый / Серебро ──
  white:        '#F5F5F5',
  pearl:        '#F0EBE3',
  silver:       '#B0BEC5',
  grey:         '#9E9E9E',
  gray:         '#9E9E9E',
  charcoal:     '#455A64',
  'dark grey':  '#616161',
  'dark gray':  '#616161',
  'light grey': '#CFD8DC',
  'light gray': '#CFD8DC',
  'opaque white': '#F5F5F5',

  // ── Флуоресцентный ──
  'neon red':  '#FF1744',
  'neon blue': '#2979FF',
  fluorescent: '#76FF03',

  // ── Crystal Clear — реальный цвет прозрачного винила ──
  // 'clear' и 'crystal' одновременно — в COLOR_MAP (для extractColors)
  // И в CLEAR_MODIFIERS (для detectOpacity → opacity 0.30).
  // "Black" намеренно НЕ здесь — "Black" alone → BLACK_KEYWORDS → чёрный.
  // "Clear With Black Splatter" → 'clear' находит цвет, 'splatter' → тип.
  clear:           '#E3F2FD',
  crystal:         '#E3F2FD',
  'crystal clear': '#E3F2FD',
  'ice clear':     '#E3F2FD',
  frosted:         '#E3F2FD',
};

// ── Паттерны для типа визуального эффекта ─────────────────────
const PATTERN_KEYWORDS = {
  splatter: ['splatter', 'chunk splatter', 'three dots'],
  marble:   ['marble', 'marbled', 'marbling', 'serenity marble'],
  swirl:    ['swirl', 'pinwheel', 'twist'],
  // CIC только по явным маркерам раздельных цветов, НЕ по кол-ву цветов
  cic: [' & ', ' and ', 'half', 'tri-color', 'tri color', 'bicolor',
        'bi-color', 'butterfly', 'two-tone', 'merge'],
};

// ── Технические метки без цвета (→ чёрный) ────────────────────
const BLACK_KEYWORDS = [
  'black', 'standard', 'normal', 'regular', 'recycled',
  '180 gram', '180g', '200 gram', '200g', '140 gram', '140g',
  '175 gram', '175g', '130 gram',
  'pressing', 'gatefold', 'embossed', 'signed', 'numbered',
  'reissue', 'anniversary', 'edition', 'mastered', 'lacquer',
  'prc', 'rca', 'rti', 'mpo', 'gzm', 'wea', 'teldec',
];

// ─────────────────────────────────────────────────────────────────

function extractColors(raw: string): string[] {
  const lower = raw.toLowerCase();
  const found: string[] = [];

  // Длинные ключи первыми — compound ("seafoam green") победит над отдельными
  const sortedKeys = Object.keys(COLOR_MAP).sort((a, b) => b.length - a.length);
  for (const key of sortedKeys) {
    if (lower.includes(key) && !found.includes(COLOR_MAP[key])) {
      found.push(COLOR_MAP[key]);
    }
  }

  return found;
}

function detectType(raw: string): VinylColorType {
  const lower = raw.toLowerCase();

  if (PATTERN_KEYWORDS.splatter.some(k => lower.includes(k))) return 'splatter';
  if (PATTERN_KEYWORDS.marble.some(k => lower.includes(k))) return 'marble';
  if (PATTERN_KEYWORDS.swirl.some(k => lower.includes(k))) return 'swirl';
  if (PATTERN_KEYWORDS.cic.some(k => lower.includes(k))) return 'cic';

  const isTranslucent =
    TRANSLUCENT_MODIFIERS.some(k => lower.includes(k)) ||
    CLEAR_MODIFIERS.some(k => lower.includes(k));

  return isTranslucent ? 'translucent' : 'solid';
}

function detectOpacity(raw: string, type: VinylColorType): number {
  const lower = raw.toLowerCase();
  if (TRANSLUCENT_MODIFIERS.some(k => lower.includes(k))) return 0.72;
  if (CLEAR_MODIFIERS.some(k => lower.includes(k))) return 0.30;
  if (type === 'translucent') return 0.72;
  return 1.0;
}

function isBlackOrStandard(raw: string): boolean {
  const lower = raw.toLowerCase().trim();
  if (!lower) return true;

  const hasColorWord = Object.keys(COLOR_MAP).some(k => lower.includes(k));
  if (hasColorWord) return false;

  // Также не чёрный, если есть модификатор прозрачности
  const hasTranslucency =
    TRANSLUCENT_MODIFIERS.some(k => lower.includes(k)) ||
    CLEAR_MODIFIERS.some(k => lower.includes(k));
  if (hasTranslucency) return false;

  return BLACK_KEYWORDS.some(k => lower.includes(k));
}

export function parseVinylColor(raw: string | null | undefined): VinylColorConfig {
  if (!raw || !raw.trim()) return BLACK;
  if (isBlackOrStandard(raw)) return BLACK;

  const colors = extractColors(raw);
  const type = detectType(raw);
  const opacity = detectOpacity(raw, type);

  // Если цвет не нашли — для translucent используем crystal-clear, иначе чёрный
  if (colors.length === 0) {
    if (type === 'translucent') {
      return { type: 'translucent', primaryColor: '#E3F2FD', opacity: 0.30, isColored: true };
    }
    return BLACK;
  }

  return {
    type,
    primaryColor: colors[0],
    secondaryColor: colors[1],
    tertiaryColor: colors[2],
    opacity,
    isColored: true,
  };
}
