/**
 * Чистая логика Android-overdrag'а Маркета (вход снизу Поиска / выход
 * сверху Маркета) — без нативных импортов, чтобы гоняться в jest. Сам жест
 * живёт в lib/useAndroidOverdrag.ts.
 *
 * Зачем отдельный жест: Android `ReactScrollView` клампит scrollY в
 * [0, maxY], а overscroll-glow (EdgeEffect) contentOffset не меняет — iOS-
 * хендлер на `onScroll` (app/(tabs)/search.tsx, onScrollSearch/onScrollMarket)
 * на Android никогда не видит overdrag. Палец здесь читаем через RNGH
 * `Gesture.Pan`, одновременный с `Gesture.Native` списка, и превращаем ход
 * пальца в те же «offset-единицы», что даёт UIScrollView на iOS.
 */

/**
 * Коэффициент резинки UIScrollView: `(1 − 1/(x·c/H + 1))·H`, c = 0.55.
 * С ним порог COMMIT_DISTANCE = 110 в offset-единицах ощущается как на iOS:
 * при H ≈ 800 это ≈ 230pt хода пальца ПОСЛЕ активации Pan. Первые
 * PAN_ACTIVE_OFFSET_Y dp до активации теряются (см. useAndroidOverdrag —
 * якорь ставится на первом onUpdate у края), так что реальный ход до
 * commit ≈ 240dp; ровно 230 не обещаем.
 */
export const RUBBER_BAND_COEFF = 0.55;
/**
 * Вертикальный сдвиг, после которого Pan активируется (dp). Больше touch-slop
 * скролла (8–12dp у OEM) не нужно: Pan и Native идут одновременно, и кто
 * первый — не важно. failOffsetX НЕ ставим: горизонтальные соседи (AutoRail,
 * StoreCarousel, FilterBar) сами отменяют наш Pan, активируясь первыми.
 */
export const PAN_ACTIVE_OFFSET_Y = 10;
/** Верхняя граница pullFraction — как в iOS-хендлерах search.tsx. */
export const MAX_PULL_FRACTION = 1.25;
/** Ниже этой доли отпускание — не «промах», а случайное касание: без хаптики. */
export const MISS_MIN_FRACTION = 0.2;
/** Возврат pullFraction/сдвига в 0 после отпускания (мс) — как на iOS. */
export const RESET_DURATION_MS = 260;
/** Системная «Назад» при открытом Маркете выходит из него (гейт по фокусу). */
export const ANDROID_BACK_EXITS_MARKET = true;

export type OverdragEdge = 'top' | 'bottom';

/**
 * Резинка UIScrollView: ход пальца `x` (dp) → overdrag в offset-единицах при
 * высоте вьюпорта `viewportH`. Монотонно растёт, асимптота — `viewportH`.
 * `viewportH <= 0` (layout ещё не измерен) → 0: иначе деление даёт NaN, а
 * NaN в scaleX прогресс-бара на Fabric роняет рендер.
 */
export function rubberBand(x: number, viewportH: number): number {
  'worklet';
  if (viewportH <= 0 || x <= 0) return 0;
  return (1 - 1 / ((x * RUBBER_BAND_COEFF) / viewportH + 1)) * viewportH;
}

/** overdrag (offset-единицы) → pullFraction 0..MAX_PULL_FRACTION. */
export function pullFractionOf(overdrag: number, commitDistance: number): number {
  'worklet';
  if (commitDistance <= 0) return 0;
  return Math.min(MAX_PULL_FRACTION, Math.max(0, overdrag / commitDistance));
}

/**
 * Стоит ли список у нужного края — только тогда ход пальца считается
 * overdrag'ом. Пока вьюпорт не измерен — нет. Контент короче вьюпорта
 * (`maxY <= 0`) — нет: как iOS без alwaysBounceVertical. Допуск 1px —
 * onScroll приходит с погрешностью округления.
 */
export function isAtEdge(
  edge: OverdragEdge,
  scrollY: number,
  contentH: number,
  viewportH: number,
): boolean {
  'worklet';
  if (viewportH <= 0) return false;
  const maxY = contentH - viewportH;
  if (!(maxY > 0)) return false;
  return edge === 'bottom' ? scrollY >= maxY - 1 : scrollY <= 1;
}

/**
 * Ход пальца от якоря в сторону overdrag'а: у нижнего края тянут вверх
 * (translationY убывает), у верхнего — вниз. Отрицательное = откат.
 */
export function fingerPull(edge: OverdragEdge, translationY: number, anchorY: number): number {
  'worklet';
  const delta = translationY - anchorY;
  return edge === 'bottom' ? -delta : delta;
}

/**
 * Знак сдвига контента для визуального отклика: у нижнего края контент
 * уезжает вверх (translateY < 0), у верхнего — вниз.
 */
export function contentShiftOf(edge: OverdragEdge, overdrag: number): number {
  'worklet';
  return edge === 'bottom' ? -overdrag : overdrag;
}

/** Порог commit'а — тот же, что в iOS-хендлерах. */
export function shouldCommit(pullFraction: number): boolean {
  'worklet';
  return pullFraction >= 1;
}

/** Отпустил, не дотянув, но тянул всерьёз — короткая хаптика «промах». */
export function shouldFireMiss(pullFraction: number): boolean {
  'worklet';
  return pullFraction > MISS_MIN_FRACTION && pullFraction < 1;
}
