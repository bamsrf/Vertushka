/**
 * Дизайн-система Вертушка — B1 Brand Foundation v2 «Stamper Hi-Fi»
 *
 * Источник истины — `T`. Структура из бриф-ответа Claude Design v2:
 *   palette (light + dark) / gradients / type / spacing / radius / shadow / motion / grooves.
 *
 * Концепция: navy/cobalt brand-ось, ivory как ТЁПЛЫЙ АКЦЕНТ (не фон),
 * усиленный ember (центр пластинки маскота) как 2-й акцент. Light + dark first-class.
 *
 * RN-Вертушка-схема: bg = #FAFBFF (фон экрана почти белый), bg.elevated = #F0F2FA
 * (карточки чуть темнее). Эта же логика заложена в SegmentedControl, search-input и др.
 * Material-инверсия (bg cool grey, elevated white) — задача B3/H1, требует пере-стилизации
 * всех компонентов скопом, иначе indicator/container ломаются местами.
 *
 * Маскот-слот константы НЕ зашиты — концепция маскота драфтовая, придёт отдельно.
 * Раскадровки splash / onboarding-birth / loading и component-гайдлайны — придут в B3/B5.
 *
 * Старые экспорты (Colors, Spacing, BorderRadius, Gradients, Typography, Shadows,
 * ComponentSizes, AnimatedGradientPalette) сохранены как легаси-алиасы.
 *
 * См.: docs/plans/PLAN_DESIGN_SYSTEM_V2_FLOW.md
 */

// ───────────────────────────────────────────────────────────────────────────
// Helper: достать light-hex из роли (для legacy aliases)
// ───────────────────────────────────────────────────────────────────────────

import { ms } from '../lib/responsive';

type ThemeMode = 'light' | 'dark';
const MODE: ThemeMode = 'light';
const L = <T,>(role: { light: T; dark: T }): T => role[MODE];

// ───────────────────────────────────────────────────────────────────────────
// T: новый источник истины (palette = light + dark)
// ───────────────────────────────────────────────────────────────────────────

export const T = {
  palette: {
    // brand
    'brand.navy':         { light: '#0B1438', dark: '#0B1438' },
    'brand.cobalt':       { light: '#2A4BD7', dark: '#5C7AE8' },
    'brand.cobaltDeep':   { light: '#0E1A52', dark: '#11225C' },
    'brand.cobaltSoft':   { light: '#5C7AE8', dark: '#7B95F5' },

    // accent
    'accent.ember':       { light: '#E85A2A', dark: '#FF7A4A' },
    'accent.emberSoft':   { light: '#FFD9C8', dark: '#3A1F12' },
    'accent.ivory':       { light: '#F4EEE6', dark: '#2A241A' },
    'accent.ivorySoft':   { light: '#FBF5EA', dark: '#1F1B14' },

    // surface — RN-Вертушка-схема: фон экрана светлее (#FAFBFF), surface чуть темнее (#F0F2FA).
    // SegmentedControl построен по этой логике: container = surface (серая подложка),
    // indicator = background (видимый светлый сегмент). Поэтому переворачивать в Material-
    // схему (bg cool, elevated white) можно только когда B3 явно перепишет SegmentedControl
    // и все прочие компоненты на новые роли.
    'bg':                 { light: '#FAFBFF', dark: '#13151C' },
    'bg.elevated':        { light: '#F0F2FA', dark: '#22252F' },
    'bg.deep':            { light: '#0B1438', dark: '#06080F' },
    'bg.sunken':          { light: '#E8EBFA', dark: '#22252F' },
    'surface.hover':      { light: '#E8EBFA', dark: '#2C303C' },

    // border / divider
    'border':             { light: '#DEE2EB', dark: '#363A4A' },
    'border.strong':      { light: '#C4CAD6', dark: '#4D5263' },
    'divider':            { light: '#E8EBF1', dark: '#262A36' },

    // text
    'text':               { light: '#0E121C', dark: '#F4F5F7' },
    'text.secondary':     { light: '#4D5263', dark: '#B6BCCC' },
    'text.muted':         { light: '#6B7080', dark: '#8B91A3' },
    'text.disabled':      { light: '#9CA3B4', dark: '#5A5F70' },
    'text.onBrand':       { light: '#FFFFFF', dark: '#FFFFFF' },
    'text.onIvory':       { light: '#0B1438', dark: '#F4EEE6' },

    // state
    'state.error':        { light: '#C8362E', dark: '#FF6B62' },
    'state.errorSoft':    { light: '#FBE5E2', dark: '#3A1A18' },
    'state.success':      { light: '#2A7A4E', dark: '#52C285' },
    'state.successSoft':  { light: '#E2F1E7', dark: '#142E20' },
    'state.warning':      { light: '#A86614', dark: '#E8A654' },
    'state.warningSoft':  { light: '#F8EAD0', dark: '#332617' },
    'state.info':         { light: '#2A4BD7', dark: '#7B95F5' },

    // fx
    'fx.overlay':         { light: 'rgba(11,20,56,0.55)',    dark: 'rgba(0,0,0,0.65)' },
    'fx.cardShadow':      { light: 'rgba(11,20,56,0.10)',    dark: 'rgba(0,0,0,0.35)' },
    'fx.glassBg':         { light: 'rgba(244,245,247,0.82)', dark: 'rgba(19,21,28,0.78)' },
    'fx.glow':            { light: 'rgba(42,75,215,0.40)',   dark: 'rgba(123,149,245,0.50)' },
    'fx.emberGlow':       { light: 'rgba(232,90,42,0.45)',   dark: 'rgba(255,122,74,0.55)' },
  },

  gradients: {
    brand:      { light: ['#0E1A52', '#2A4BD7', '#5C7AE8'] as const,
                  dark:  ['#06080F', '#11225C', '#2A4BD7'] as const },
    ember:      { light: ['#B8431B', '#E85A2A', '#FFB347'] as const,
                  dark:  ['#8C2F10', '#E85A2A', '#FF9466'] as const },
    onboarding: { light: ['#11225C', '#2A4BD7', '#5C7AE8', '#E8B4C0'] as const,
                  dark:  ['#06080F', '#11225C', '#2A4BD7', '#E85A2A'] as const },
    navySheet:  { light: ['#0B1438', '#11225C'] as const,
                  dark:  ['#06080F', '#0B1438'] as const },
  },

  // Type — Rubik Mono One для heroTitle (1 уровень), Inter для остального.
  type: {
    heroTitle:   { fontSize: 40, weight: 400, lineHeight: 44, letterSpacing: -0.5, font: 'RubikMonoOne-Regular' },
    display:     { fontSize: 32, weight: 800, lineHeight: 36, letterSpacing: -0.8, font: 'Inter_800ExtraBold' },
    h1:          { fontSize: 26, weight: 700, lineHeight: 30, letterSpacing: -0.4, font: 'Inter_700Bold' },
    h2:          { fontSize: 20, weight: 700, lineHeight: 26, letterSpacing: -0.2, font: 'Inter_700Bold' },
    h3:          { fontSize: 17, weight: 600, lineHeight: 22, letterSpacing: 0,    font: 'Inter_600SemiBold' },
    subhead:     { fontSize: 15, weight: 600, lineHeight: 20, letterSpacing: 0,    font: 'Inter_600SemiBold' },
    body:        { fontSize: 16, weight: 400, lineHeight: 24, letterSpacing: 0,    font: 'Inter_400Regular' },
    bodyBold:    { fontSize: 16, weight: 600, lineHeight: 24, letterSpacing: 0,    font: 'Inter_600SemiBold' },
    bodySmall:   { fontSize: 14, weight: 400, lineHeight: 20, letterSpacing: 0,    font: 'Inter_400Regular' },
    button:      { fontSize: 16, weight: 600, lineHeight: 20, letterSpacing: 0.3,  font: 'Inter_600SemiBold' },
    buttonSmall: { fontSize: 14, weight: 500, lineHeight: 18, letterSpacing: 0.2,  font: 'Inter_500Medium' },
    caption:     { fontSize: 12, weight: 400, lineHeight: 16, letterSpacing: 0.1,  font: 'Inter_400Regular' },
    overline:    { fontSize: 11, weight: 700, lineHeight: 14, letterSpacing: 1.2,  font: 'Inter_700Bold' },
  },

  spacing: { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, '2xl': 32, '3xl': 48 } as const,

  radius: { xs: 6, sm: 10, md: 14, lg: 20, xl: 28, '2xl': 36, full: 9999 } as const,

  shadow: {
    xs:        { y: 1,  blur: 2,  opacity: 0.04, elevation: 1,  colorRole: 'fx.cardShadow' as const },
    sm:        { y: 2,  blur: 6,  opacity: 0.06, elevation: 2,  colorRole: 'fx.cardShadow' as const },
    md:        { y: 6,  blur: 16, opacity: 0.10, elevation: 4,  colorRole: 'fx.cardShadow' as const },
    lg:        { y: 12, blur: 28, opacity: 0.14, elevation: 10, colorRole: 'fx.cardShadow' as const },
    tabBar:    { y: -4, blur: 24, opacity: 0.12, elevation: 14, colorRole: 'fx.cardShadow' as const },
    glow:      { y: 0,  blur: 20, opacity: 0.40, elevation: 0,  colorRole: 'fx.glow'       as const },
    glowEmber: { y: 0,  blur: 24, opacity: 0.45, elevation: 0,  colorRole: 'fx.emberGlow'  as const },
  },

  motion: {
    easing: {
      standard:   [0.2, 0, 0, 1] as const,
      emphasized: [0.3, 0, 0, 1] as const,
      decelerate: [0,   0, 0, 1] as const,
      accelerate: [0.3, 0, 1, 1] as const,
      expressive: [0.34, 1.56, 0.64, 1] as const,
    },
    duration: { instant: 120, standard: 220, expressive: 480 },
    longLoop: {
      vinylSpin: 1800,
      hotPulse: 2000,
      limitedPulse: 4000,
      collectibleSpin: 8000,
      autoRail: 30000,
    },
    spring: {
      soft:   { damping: 18, stiffness: 140 },
      snap:   { damping: 12, stiffness: 180 },
      bouncy: { damping: 9,  stiffness: 200 },
    },
  },

  grooves: {
    stroke: 1,
    strokeOpacityOnDeep: 0.18,
    spacing: 4,
    centerDot: 12,
    centerColorRole: 'accent.ember' as const,
    centerGlowRole:  'fx.emberGlow' as const,
    timing: {
      pulse: 2400,
      wave: 900,
      birth: 1800,
    },
  },

  // ── ICON SYSTEM — Stamper Outline v3 ────────────────────────────────
  // Концепция (закреплена, не меняем):
  //   2 уровня без серединных вариаций.
  //
  //   • HERO (3 brand-сущности): узнаваемый силуэт = заливка.
  //       heart  → fill      (вишлист/лайк, brand symbol)
  //       disc   → duotone   (пластинка с канавками)
  //       gift   → duotone   (подарок-коробка)
  //
  //   • UI (всё остальное): тонкий outline = regular.
  //       bell, check, x, plus, trophy, chat-circle, ... — никаких halo,
  //       никакой заливки. Active state = смена color, не утолщение.
  //
  // Halo glow удалён полностью (и внешний wrapper, и встроенный FeGaussianBlur
  // у V2-иконок). Если нужно подсветить иконку — это делается обёрткой во
  // вне (View с shadow), а не в Icon-системе.
  //
  // НЕ импортируй Ionicons или Phosphor напрямую — только через <Icon>.
  icon: {
    library: 'phosphor-react-native' as const,
    customPath: 'Mobile/components/icons/hero/' as const,

    // Дефолтная стилистика: тонкий outline + закруглённые концы.
    style: {
      weight: 'regular' as const,
      strokeWidth: 2,
      linecap: 'round' as const,
      linejoin: 'round' as const,
    },

    // 5 размерных пресетов
    sizes: { xs: 16, sm: 20, md: 24, lg: 32, xl: 48 } as const,

    // Auto-hitSlop под ≥44pt touch target для каждого пресета.
    hitSlop: { xs: 14, sm: 12, md: 10, lg: 6, xl: 0 } as const,

    // Color roles → palette token. Wrapper резолвит в hex по T.palette[token][mode].
    colors: {
      default:   'text.muted'      as const,
      secondary: 'text.secondary'  as const,
      primary:   'text'            as const,
      brand:     'brand.cobalt'    as const,
      accent:    'accent.ember'    as const,
      success:   'state.success'   as const,
      error:     'state.error'     as const,
      warning:   'state.warning'   as const,
      onBrand:   'text.onBrand'    as const,
      disabled:  'text.disabled'   as const,
    },

    // Hero set — единственные имена с дефолт не-regular weight.
    // Закреплено в Icon.tsx (HERO_FILL_NAMES + HERO_DUOTONE_NAMES).
    heroFill:    ['heart'] as const,
    heroDuotone: ['disc', 'gift', 'vinyl-label'] as const,

    // Custom hero set — иконки-обёртки в components/icons/hero/index.tsx.
    customSet: [
      { name: 'disc-grooves',   sizes: [16, 24, 48], use: 'Tab bar, empty state, onboarding' },
      { name: 'gift-vinyl',     sizes: [20, 24],     use: 'Profile, GiftGivenItem, booked badge. НЕ использовать в вишлист-сценариях.' },
      { name: 'trophy-disc',    sizes: [20, 32, 48], use: 'Achievements, top collector — outline.' },
      { name: 'scan-target',    sizes: [24, 48],     use: 'Tab bar Сканер — outline.' },
      { name: 'vinyl-label',    sizes: [24, 32],     use: 'Центр VinylSpinner — duotone.' },
    ] as const,
  },
} as const;

// ───────────────────────────────────────────────────────────────────────────
// Legacy aliases — мигрируются в B3/H1
// ───────────────────────────────────────────────────────────────────────────

// Legacy `Colors` экспорт — pristine Blue Gradient Edition (commit 0fe5f85).
// Это финальные значения для существующих компонентов и экранов: тёплая
// сине-розовая палитра (royalBlue / lavender / softPink + синяя cardShadow),
// благодаря которой фон #FAFBFF читается как голубоватый, а не белый.
//
// НОВАЯ B1 v2 палитра (navy/cobalt/ember/ivory) живёт в `T.palette` выше и
// используется через Icon API и будущую миграцию (B3/H1). Мигрировать
// существующие компоненты на T.* — задача B3, не сейчас.
export const Colors = {
  // Основная градиентная палитра — Blue Gradient v1
  deepNavy:     '#0A0B3B',
  royalBlue:    '#3B4BF5',
  electricBlue: '#5B6AF5',
  periwinkle:   '#8B9CF7',
  lavender:     '#C5B8F2',
  softPink:     '#F0C4D8',
  blushPink:    '#F8E4EE',

  // Нейтральные
  background:   '#FAFBFF',
  surface:      '#F0F2FA',
  surfaceHover: '#E8EBFA',

  // Текст
  text:          '#0A0B3B',
  textSecondary: '#5A5F8A',
  textMuted:     '#9A9EBF',

  // Состояния
  error:   '#E5484D',
  success: '#30A46C',
  warning: '#F5A623',

  // Границы и разделители
  border:  '#E0E3F0',
  divider: '#ECEEF7',

  // Специальные
  overlay:    'rgba(10, 11, 59, 0.5)',
  cardShadow: 'rgba(59, 75, 245, 0.08)',
  glassBg:    'rgba(250, 251, 255, 0.85)',
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const BorderRadius = {
  sm: 10,
  md: 14,
  lg: 18,
  xl: 26,
  full: 9999,
};

// Gradients — pristine Blue Gradient (royalBlue / electricBlue / lavender / softPink).
//
// hotStock — фирменный градиент Hot Stock pill и активного чипа «В продаже»:
// от холодного cobaltDeep через бренд-cobalt к огненному ember. Это
// единственное место, где ember проявляется как пятно света — он редкий по
// замыслу, потому что заметность держится на контрасте с холодным фоном.
// Источник: B2/Hot Stock spec (MARKET_AND_PRICE_DRAWER.md §2.2 / atoms.jsx).
//
// hotStockSoft — softer вариант для transition-кадров (когда glow «гаснет»
// при mid-fade фона маркета). На 1 шаг светлее по cobaltDeep + emberSoft.
export const Gradients = {
  blue:     ['#3B4BF5', '#5B6AF5'] as const,
  bluePink: ['#3B4BF5', '#8B9CF7', '#F0C4D8'] as const,
  blueLight:['#5B6AF5', '#8B9CF7'] as const,
  overlay:  ['transparent', 'rgba(10, 11, 59, 0.7)'] as const,
  hotStock:     ['#0E1A52', '#2A4BD7', '#E85A2A'] as const, // cobaltDeep → cobalt → ember
  hotStockSoft: ['#11225C', '#2A4BD7', '#FF7A4A'] as const,
  // Outline gradient для altVersion/preorder pill — мягкий cobaltSoft → ember
  hotStockOutline: ['#5C7AE8', '#E85A2A'] as const,
};

// ───────────────────────────────────────────────────────────────────────────
// Market palette — отдельный «тёплый/насыщенный» мир для раздела Маркет
// (бэкграунд с radial-смешением фиолетового/cobalt/azure/peach + grain).
// Источник: bg-reference.png + tokens.js Design Claude (market.*).
//
// Используется через MarketBackground.tsx — composite из 5 LinearGradient
// и/или radial-svg слоёв. Цвета не идут в основную T.palette, чтобы не
// смешивать «холодную» дефолт-тему с «горячей» Маркет-айдентикой.
// ───────────────────────────────────────────────────────────────────────────

export const MarketPalette = {
  void:    '#0E0726', // тёмный фиолетовый «пустотный» верх-лево
  indigo:  '#241057', // глубокий индиго
  violet:  '#5E2099', // насыщенный фиолет
  cobalt:  '#2D4FDB', // бренд-cobalt «мост» между мирами
  azure:   '#5780F0', // голубой акцент верх-право
  peach:   '#F4A06A', // тёплый персик низ-право
  blush:   '#F8C0A0', // мягкий peach edge
  magenta: '#B53B91', // magenta низ-лево
  plum:    '#3A124A', // приглушённый сливовый
  darkVoid: '#0A0218', // signature тень в верхней центральной части (тёмное пятно)

  // Chrome-цвета на market-фоне: белые с альфой (всё остальное даст слишком
  // контрастный кричащий вид). Используем для borders/fills стеклянных
  // элементов (search input, chips, exit button).
  chrome: {
    borderSoft:   'rgba(255,255,255,0.10)',
    border:       'rgba(255,255,255,0.18)',
    fill:         'rgba(255,255,255,0.06)',
    fillStrong:   'rgba(255,255,255,0.10)',
    textPrimary:  '#FFFFFF',
    textSecondary:'rgba(255,255,255,0.70)',
    textMuted:    'rgba(255,255,255,0.55)',
    textDim:      'rgba(255,255,255,0.40)',
  },
} as const;

// Type scale legacy. heroTitle — RubikMonoOne (был Inter Bold).
//
// Все размеры прогнаны через ms() (см. lib/responsive.ts): на iPhone Mini/SE
// (эталон 375pt) = без изменений, на больших экранах fontSize/lineHeight мягко
// растут. letterSpacing/fontFamily не трогаем. Один источник → 300+ мест
// `...Typography.x` становятся адаптивными автоматически.
const TYPOGRAPHY_BASE = {
  heroTitle: {
    fontSize: 40,
    fontFamily: 'RubikMonoOne-Regular',
    lineHeight: 44,
    letterSpacing: -0.5,
  },
  display: {
    fontSize: 32,
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: 36,
    letterSpacing: -0.8,
  },
  h1: {
    fontSize: 26,
    fontFamily: 'Inter_700Bold',
    lineHeight: 30,
    letterSpacing: -0.4,
  },
  h2: {
    fontSize: 20,
    fontFamily: 'Inter_700Bold',
    lineHeight: 26,
    letterSpacing: -0.2,
  },
  h3: {
    fontSize: 17,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 22,
  },
  h4: {
    fontSize: 15,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 20,
  },
  subhead: {
    fontSize: 15,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 20,
  },
  body: {
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    lineHeight: 24,
  },
  bodyBold: {
    fontSize: 16,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 24,
  },
  bodySmall: {
    fontSize: 14,
    fontFamily: 'Inter_400Regular',
    lineHeight: 20,
  },
  button: {
    fontSize: 16,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 20,
    letterSpacing: 0.3,
  },
  buttonSmall: {
    fontSize: 14,
    fontFamily: 'Inter_500Medium',
    lineHeight: 18,
    letterSpacing: 0.2,
  },
  caption: {
    fontSize: 12,
    fontFamily: 'Inter_400Regular',
    lineHeight: 16,
    letterSpacing: 0.1,
  },
  overline: {
    fontSize: 11,
    fontFamily: 'Inter_700Bold',
    lineHeight: 14,
    letterSpacing: 1.2,
  },
  // Used only by VinylSpinner center label.
  label: {
    fontSize: 11,
    fontFamily: 'RubikMonoOne-Regular',
    lineHeight: 12,
    letterSpacing: 1.5,
  },
};

// Прогон через ms(): fontSize + lineHeight масштабируются, остальное as-is.
type TypeStyle = { fontSize: number; lineHeight?: number; [k: string]: unknown };
const scaleType = <T extends Record<string, TypeStyle>>(base: T): T =>
  Object.fromEntries(
    Object.entries(base).map(([key, v]) => [
      key,
      {
        ...v,
        fontSize: ms(v.fontSize),
        ...(v.lineHeight != null ? { lineHeight: ms(v.lineHeight) } : {}),
      },
    ]),
  ) as T;

export const Typography = scaleType(TYPOGRAPHY_BASE);

// Shadow color — pristine Blue Gradient (royalBlue), не navy. Вместе с тёплой
// Colors-палитрой даёт характерный сине-фиолетовый shadow вокруг карточек.
const SHADOW_COLOR = '#3B4BF5';                         // royalBlue
const GLOW_COLOR = '#3B4BF5';                           // тоже royalBlue для glow
const GLOW_EMBER_COLOR = L(T.palette['accent.ember']);  // ember остаётся для B2 hot-rarity

export const Shadows = {
  xs: {
    shadowColor: SHADOW_COLOR,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 2,
    elevation: 1,
  },
  sm: {
    shadowColor: SHADOW_COLOR,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  md: {
    shadowColor: SHADOW_COLOR,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.10,
    shadowRadius: 16,
    elevation: 4,
  },
  lg: {
    shadowColor: SHADOW_COLOR,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.14,
    shadowRadius: 28,
    elevation: 10,
  },
  tabBar: {
    shadowColor: SHADOW_COLOR,
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.12,
    shadowRadius: 24,
    elevation: 14,
  },
  glow: {
    shadowColor: GLOW_COLOR,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.40,
    shadowRadius: 20,
    elevation: 0,
  },
  glowEmber: {
    shadowColor: GLOW_EMBER_COLOR,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.45,
    shadowRadius: 24,
    elevation: 0,
  },
};

export const ComponentSizes = {
  buttonHeight: 56,
  buttonHeightSmall: 44,
  inputHeight: 56,
  cardPadding: Spacing.md,
  tabBarHeight: 84,
  headerHeight: 56,
  iconSm: 20,
  iconMd: 24,
  iconLg: 32,
};

// AnimatedGradientPalette — pristine Blue Gradient (royal/lavender/pink-rose loop).
export const AnimatedGradientPalette = {
  colors: [
    '#2D3E8F',  // Тёмно-синий
    '#4A6FDB',  // Насыщенный синий
    '#6B9EF5',  // Средне-синий
    '#93C4FF',  // Светло-синий
    '#C8D9F7',  // Очень светло-синий
    '#E8CEEB',  // Светло-розово-фиолетовый
    '#F5B5D8',  // Светло-розовый
  ] as const,
  presets: [
    ['#2D3E8F', '#4A6FDB', '#6B9EF5'],
    ['#4A6FDB', '#6B9EF5', '#93C4FF'],
    ['#6B9EF5', '#93C4FF', '#C8D9F7'],
    ['#93C4FF', '#C8D9F7', '#E8CEEB'],
    ['#C8D9F7', '#E8CEEB', '#F5B5D8'],
    ['#E8CEEB', '#F5B5D8', '#93C4FF'],
    ['#F5B5D8', '#6B9EF5', '#2D3E8F'],
  ] as const,
  darkPresets: [
    ['#2D3E8F', '#4A6FDB', '#6B5EC2'],
    ['#4A6FDB', '#6B5EC2', '#5B3FA0'],
    ['#6B5EC2', '#5B3FA0', '#8B4DA8'],
    ['#5B3FA0', '#8B4DA8', '#C75895'],
    ['#8B4DA8', '#C75895', '#4A6FDB'],
    ['#C75895', '#4A6FDB', '#2D3E8F'],
  ] as const,
};

export default {
  T,
  Colors,
  Spacing,
  BorderRadius,
  Typography,
  Shadows,
  ComponentSizes,
  Gradients,
  AnimatedGradientPalette,
};
