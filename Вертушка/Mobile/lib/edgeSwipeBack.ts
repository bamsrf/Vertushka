/**
 * Чистая логика Android-свайпа «назад» (с любого места экрана) — без
 * нативных импортов, чтобы гоняться в jest. Сам жест живёт в
 * components/AndroidEdgeSwipeBack.tsx.
 *
 * Пороги подобраны под соседей по дереву. Все свои Gesture.Pan в проекте
 * (свайп-строки сообщений/вишлиста/уведомлений, AutoRail, ThresholdSheet,
 * ReanimatedSwipeable) активируются на 6–12dp, нативные ScrollView/FlatList
 * перехватывают тач на системном touch-slop (`ViewConfiguration.
 * getScaledTouchSlop`, 8dp на стоковом Android, до ~12dp у части OEM).
 * Наш ACTIVE_OFFSET_X заведомо больше — кто раньше активировался, тот и
 * победил, а RNGH отменяет опоздавшего (проверено по android/ RNGH 2.32:
 * horizontal ScrollView на touch-slop зовёт `requestDisallowInterceptTouchEvent`,
 * RNGestureHandlerRootView через `tryCancelAllHandlers` отменяет все ещё не
 * активные жесты; свои Pan'ы — через `makeActive` → `shouldHandlerBeCancelledBy`).
 * Поэтому карусели и свайп-строки продолжают работать, а свайп «назад»
 * ловится там, где горизонтальному жесту никто не претендует.
 * НЕ опускать ниже 13: 12dp — верхняя граница соседей, ниже начнётся лотерея.
 */
import { create } from 'zustand';

/**
 * Горизонтальный сдвиг вправо, после которого жест активируется (dp).
 * 16 = максимум соседей (12) + запас на дрожание пальца; меньше владелец
 * ощущает как «сразу», больше — как задержку старта.
 */
export const ACTIVE_OFFSET_X = 16;
/** Сдвиг влево, после которого жест сдаётся (dp) — назад только вправо. */
export const FAIL_OFFSET_X = 10;
/** Вертикальный сдвиг, после которого жест уступает скроллу (dp). */
export const FAIL_OFFSET_Y = 15;
/** Порог «отпустил — уходим назад»: доля ширины окна и скорость (dp/s). */
export const COMMIT_FRACTION = 0.35;
export const COMMIT_VELOCITY = 800;
/** Доанимировать экран за край окна перед pop (мс). */
export const COMMIT_DURATION_MS = 180;
/** Вернуть экран на место при отмене (мс). */
export const CANCEL_DURATION_MS = 200;
/**
 * Если после эмуляции «Назад» маршрут не сменился за это время — «Назад»
 * съел оверлей (useAndroidBackClose), экран возвращаем на место.
 */
export const POP_FALLBACK_MS = 400;
/** Максимальная непрозрачность тёмной подложки, видимой слева от экрана. */
export const BACKDROP_MAX_OPACITY = 0.3;

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
export function shouldCommitSwipeBack(
  { translationX, velocityX }: SwipeEnd,
  windowWidth: number,
): boolean {
  'worklet';
  return translationX > windowWidth * COMMIT_FRACTION || velocityX > COMMIT_VELOCITY;
}

/**
 * Сдвиг контента вслед за пальцем 1:1. `origin` — translationX в момент
 * активации (≈ ACTIVE_OFFSET_X): вычитаем его, чтобы экран стартовал с 0,
 * а не прыгал на порог активации. Влево контент не уезжает.
 */
export function followShift(translationX: number, origin: number): number {
  'worklet';
  return Math.max(0, translationX - origin);
}

/** Прогресс ухода экрана 0..1 по сдвигу и ширине окна. */
export function swipeProgress(shift: number, windowWidth: number): number {
  'worklet';
  if (windowWidth <= 0) return 0;
  return Math.min(1, Math.max(0, shift / windowWidth));
}

/**
 * Непрозрачность подложки слева от уезжающего экрана: темнее в начале,
 * светлеет к концу — как затемнение нижнего экрана в iOS-стеке.
 */
export function backdropOpacity(progress: number): number {
  'worklet';
  return BACKDROP_MAX_OPACITY * (1 - progress);
}

/** Включать ли жест на экране с таким первым сегментом маршрута. */
export function isEdgeSwipeEnabledForSegment(firstSegment: string | undefined): boolean {
  return !ROOT_SEGMENTS.has(firstSegment ?? '');
}

/**
 * Флаг «pop без нативной анимации». Свайп сам довозит экран за край окна,
 * после чего native-stack должен убрать его мгновенно — иначе экран
 * вернётся на 0 и уедет второй раз нативным slide. `_layout.tsx` читает
 * флаг в `screenOptions.animation` (только Android); свайп поднимает его
 * перед эмуляцией «Назад» и опускает после смены маршрута.
 */
interface SwipeBackPopState {
  popWithoutAnimation: boolean;
  setPopWithoutAnimation: (value: boolean) => void;
}

export const useSwipeBackPopStore = create<SwipeBackPopState>((set) => ({
  popWithoutAnimation: false,
  setPopWithoutAnimation: (popWithoutAnimation) => set({ popWithoutAnimation }),
}));
