/**
 * Responsive scaling — кроссплатформенный (iOS + Android).
 *
 * Принцип: iPhone Mini/SE (ширина 375pt) = ЭТАЛОН (scale 1.0). Размеры
 * подбираются «как надо на Mini», на больших экранах мягко растут.
 *
 *   scale = width / 375, с clamp [0.9 … 1.3] чтобы Android-планшеты и
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
import { Dimensions, PixelRatio } from 'react-native';

const { width } = Dimensions.get('window');

const GUIDELINE_BASE = 393; // iPhone 14/15 Pro — эталон («выглядит супер»)
const MIN_SCALE = 0.9;
const MAX_SCALE = 1.3;

const scale = Math.min(Math.max(width / GUIDELINE_BASE, MIN_SCALE), MAX_SCALE);

const COMPACT_WIDTH = 375; // iPhone Mini / SE / 8

/** Признак узкого экрана (Mini / SE / старые) — для точечных правок. */
export const isCompact = width <= COMPACT_WIDTH;

/**
 * Compact-boost: на узких экранах (Mini/SE) текст ФИЗИЧЕСКИ мельче из-за
 * меньшей диагонали (5.4" vs 6.1"). При равной ширине линейный скейл не
 * помогает, поэтому на compact-экранах шрифты умножаются на +12%.
 */
const COMPACT_BOOST = isCompact ? 1.12 : 1;

/**
 * Moderate scale — для шрифтов.
 * - На Mini/SE: +12% (compact-boost) — лечит физически мелкий текст.
 * - На Pro/Max: мягкий рост от ширины (factor 0.5).
 * factor 0 = не масштабировать, 0.5 = мягко (дефолт), 1 = линейно.
 */
export const ms = (size: number, factor = 0.5): number => {
  const scaled = (size + (size * scale - size) * factor) * COMPACT_BOOST;
  return Math.round(PixelRatio.roundToNearestPixel(scaled));
};

/** Линейный масштаб — для отступов, иконок, размеров. */
export const s = (size: number): number =>
  Math.round(PixelRatio.roundToNearestPixel(size * scale));
