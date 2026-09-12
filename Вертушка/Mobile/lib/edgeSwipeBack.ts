/**
 * Чистая логика Android-свайпа «назад» (с любого места экрана) — без
 * нативных импортов, чтобы гоняться в jest. Сам жест живёт в
 * components/AndroidEdgeSwipeBack.tsx.
 *
 * Пороги подобраны под соседей по дереву. Все свои Gesture.Pan в проекте
 * (свайп-строки сообщений/вишлиста/уведомлений, AutoRail, ThresholdSheet,
 * ReanimatedSwipeable) активируются на 6–12dp, нативные ScrollView/FlatList
 * перехватывают тач на системном touch-slop (~8dp). Наш ACTIVE_OFFSET_X
 * заведомо больше — кто раньше активировался, тот и победил, а RNGH
 * отменяет опоздавшего. Поэтому карусели и свайп-строки продолжают
 * работать, а свайп «назад» ловится там, где горизонтальному жесту никто
 * не претендует. НЕ опускать ниже 13.
 */

/** Горизонтальный сдвиг вправо, после которого жест активируется (dp). */
export const ACTIVE_OFFSET_X = 25;
/** Сдвиг влево, после которого жест сдаётся (dp) — назад только вправо. */
export const FAIL_OFFSET_X = 10;
/** Вертикальный сдвиг, после которого жест уступает скроллу (dp). */
export const FAIL_OFFSET_Y = 15;
/** Порог «отпустил — уходим назад» по дистанции (dp) и скорости (dp/s). */
export const COMMIT_DISTANCE = 100;
export const COMMIT_VELOCITY = 900;
/** Доля сдвига пальца, на которую контент едет за ним (визуальный отклик). */
export const FOLLOW_FACTOR = 0.3;

/**
 * Корневые сегменты, где возвращаться некуда, а полноэкранный жест мешал бы
 * горизонтальным скроллам папок/каруселей табов.
 */
const ROOT_SEGMENTS: ReadonlySet<string> = new Set(['(tabs)', '(auth)', 'onboarding']);

interface SwipeEnd {
  translationX: number;
  velocityX: number;
}

/** Достаточно ли дотянул/швырнул палец, чтобы уйти назад. */
export function shouldCommitSwipeBack({ translationX, velocityX }: SwipeEnd): boolean {
  'worklet';
  return translationX > COMMIT_DISTANCE || velocityX > COMMIT_VELOCITY;
}

/** Сдвиг контента вслед за пальцем: только вправо, с коэффициентом. */
export function followShift(translationX: number): number {
  'worklet';
  return Math.max(0, translationX) * FOLLOW_FACTOR;
}

/** Включать ли жест на экране с таким первым сегментом маршрута. */
export function isEdgeSwipeEnabledForSegment(firstSegment: string | undefined): boolean {
  return !ROOT_SEGMENTS.has(firstSegment ?? '');
}
