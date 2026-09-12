/**
 * Responsive scaling — кроссплатформенный (iOS + Android).
 *
 * Принцип: iPhone 14/15 Pro (ширина 393pt) = ЭТАЛОН (scale 1.0, «выглядит
 * супер»). На больших экранах шрифт мягко растёт; на узких iPhone (Mini/SE) —
 * compact-boost +12%, т.к. при равной ширине текст физически мельче.
 * Буст — ТОЛЬКО iOS: Android-телефон в 360dp — это 6.5" экран с крупной
 * плотностью, там +12% раздувает текст и ломает переносы (см. compactBoostFor).
 *
 *   scale = width / 393, с clamp [0.9 … 1.3] чтобы Android-планшеты и
 *   foldable не раздували верстку.
 *
 * Две функции:
 *   ms(size, factor) — для шрифтов: мягкий рост (factor 0.5 = половина прибавки)
 *   s(size)          — для отступов/иконок: линейный масштаб
 *
 * Системный font-scale (настройка «Размер текста» на устройстве) — ОТДЕЛЬНАЯ
 * ось, ms() её не трогает. Контролируется через allowFontScaling /
 * maxFontSizeMultiplier на <Text>.
 */
import { Dimensions, PixelRatio, Platform } from 'react-native';
import { MAX_FONT_SCALE } from './fontScale/maxFontScale';

const { width } = Dimensions.get('window');

const GUIDELINE_BASE = 393; // iPhone 14/15 Pro — эталон («выглядит супер»)
const MIN_SCALE = 0.9;
const MAX_SCALE = 1.3;

const scale = Math.min(Math.max(width / GUIDELINE_BASE, MIN_SCALE), MAX_SCALE);

const COMPACT_WIDTH = 375; // iPhone Mini / SE / 8; Android 360dp тоже попадает

/**
 * Признак узкого экрана (≤ 375) — для точечных правок вёрстки (меньше гэпы и
 * паддинги, мельче пин ачивки). Платформо-независим: на Android 360dp тоже
 * true — там места по ширине действительно меньше. Размеры шрифтов через него
 * НЕ увеличивать — для этого есть compactBoostFor.
 */
export const isCompact = width <= COMPACT_WIDTH;

/**
 * Compact-boost: на узких iPhone (Mini/SE) текст ФИЗИЧЕСКИ мельче из-за
 * меньшей диагонали (5.4" vs 6.1"). При равной ширине линейный скейл не
 * помогает, поэтому на compact-экранах шрифты умножаются на +12%.
 *
 * Только iOS. Android-телефон шириной 360dp (realme/oppo/samsung) — это
 * 6.5" экран: текст там и так крупный, буст делал его раздутым и ломал слова
 * по слогам. Чистая функция — чтобы тест мог проверить обе платформы, не
 * пересобирая модуль под мок Dimensions/Platform.
 */
export const compactBoostFor = (os: string, screenWidth: number): number =>
  os === 'ios' && screenWidth <= COMPACT_WIDTH ? 1.12 : 1;

const COMPACT_BOOST = compactBoostFor(Platform.OS, width);

/** Линейный скейл ширины с clamp — чистая часть ms()/s(). */
export const widthScaleFor = (screenWidth: number): number =>
  Math.min(Math.max(screenWidth / GUIDELINE_BASE, MIN_SCALE), MAX_SCALE);

/**
 * Чистая версия ms() — та же формула, но платформа и ширина приходят
 * параметрами (для тестов и для мест, где нужен расчёт под другую ширину).
 */
export const moderateScaleFor = (
  size: number,
  factor: number,
  { os, screenWidth }: { os: string; screenWidth: number },
): number => {
  const widthScale = widthScaleFor(screenWidth);
  return (size + (size * widthScale - size) * factor) * compactBoostFor(os, screenWidth);
};

/**
 * Moderate scale — для шрифтов.
 * - На iPhone Mini/SE: +12% (compact-boost) — лечит физически мелкий текст.
 * - На Pro/Max: мягкий рост от ширины (factor 0.5).
 * - На Android 360dp: только clamp-скейл (0.916), без буста.
 * factor 0 = не масштабировать, 0.5 = мягко (дефолт), 1 = линейно.
 */
export const ms = (size: number, factor = 0.5): number => {
  const scaled = (size + (size * scale - size) * factor) * COMPACT_BOOST;
  return Math.round(PixelRatio.roundToNearestPixel(scaled));
};

/** Линейный масштаб — для отступов, иконок, размеров. */
export const s = (size: number): number =>
  Math.round(PixelRatio.roundToNearestPixel(size * scale));

/**
 * Потолок системного font-scale — см. `lib/fontScale/maxFontScale.ts`.
 * Сам clamp живёт в `lib/fontScale/scaledText.tsx`: `Text`/`TextInput` с
 * дефолтным `maxFontSizeMultiplier`, подставленные вместо RN-экспортов через
 * alias в `metro.config.js`. Прежний `Text.defaultProps` на RN 0.86 / React 19
 * был no-op — function-компоненты `defaultProps` больше не читают.
 */
export { MAX_FONT_SCALE };
