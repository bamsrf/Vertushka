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

const GUIDELINE_BASE = 375; // iPhone Mini / SE — эталон
const MIN_SCALE = 0.9;
const MAX_SCALE = 1.3;

const scale = Math.min(Math.max(width / GUIDELINE_BASE, MIN_SCALE), MAX_SCALE);

/** Признак узкого экрана (Mini / SE / старые) — для точечных правок. */
export const isCompact = width <= GUIDELINE_BASE;

/**
 * Moderate scale — для шрифтов.
 * factor 0 = не масштабировать, 0.5 = мягко (дефолт), 1 = линейно.
 */
export const ms = (size: number, factor = 0.5): number => {
  const scaled = size + (size * scale - size) * factor;
  return Math.round(PixelRatio.roundToNearestPixel(scaled));
};

/** Линейный масштаб — для отступов, иконок, размеров. */
export const s = (size: number): number =>
  Math.round(PixelRatio.roundToNearestPixel(size * scale));
