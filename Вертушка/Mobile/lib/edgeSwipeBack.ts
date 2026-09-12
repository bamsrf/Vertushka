/**
 * Чистая логика Android-свайпа «назад» от левого края — без нативных
 * импортов, чтобы гоняться в jest. Сам жест живёт в
 * components/AndroidEdgeSwipeBack.tsx.
 */

/** Ширина полосы у левого края, в которой распознаётся жест (dp). */
export const EDGE_WIDTH = 24;
/** Горизонтальный сдвиг, после которого жест активируется (dp). */
export const ACTIVE_OFFSET_X = 15;
/** Вертикальный сдвиг, после которого жест уступает скроллу (dp). */
export const FAIL_OFFSET_Y = 20;
/** Порог «отпустил — уходим назад» по дистанции (dp) и скорости (dp/s). */
export const COMMIT_DISTANCE = 80;
export const COMMIT_VELOCITY = 800;
/** Доля сдвига пальца, на которую контент едет за ним (визуальный отклик). */
export const FOLLOW_FACTOR = 0.3;

/**
 * Корневые сегменты, где возвращаться некуда, а полоса у края мешала бы
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
