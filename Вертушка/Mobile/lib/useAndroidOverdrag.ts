/**
 * useAndroidOverdrag — Android-аналог iOS-overdrag'а входа/выхода Маркета
 * в (tabs)/search.tsx.
 *
 * Почему не onScroll и не touch-responder: Android `ReactScrollView` клампит
 * offset в [0, maxY], а `onInterceptTouchEvent` → `NativeGestureUtil.
 * notifyNativeGestureStarted` → `JSTouchDispatcher.onChildStartedNativeGesture`
 * шлёт в JS touchCancel и дропает дальнейшие MOVE/UP — родительский
 * responder ничего не видит. Работает RNGH: `RNGestureHandlerRootView.
 * dispatchTouchEvent` получает MotionEvent раньше иерархии, а
 * `requestDisallowInterceptTouchEvent` от ScrollView при `passingTouch`
 * игнорируется; `Gesture.Simultaneous(pan, native)` → `canRunSimultaneously`
 * → Pan не отменяется скроллом. Тот же паттерн у @gorhom/bottom-sheet.
 *
 * Контракт с search.tsx: жест пишет ТОЛЬКО в те же shared values, что и
 * iOS-хендлеры (pullFraction/dragging/lastHapticStep/committedAnim), поэтому
 * хаптик-лесенка, прогресс-бар CTA и MarketExitHint не знают о платформе.
 * Плюс `shift` — визуальный сдвиг контента (на Android contentOffset не
 * двигается, и без него CTA остаётся под fade-градиентом, а exit-hint — под
 * кромкой).
 *
 * На iOS хук вызывается безусловно (rules-of-hooks), но возвращает `undefined`
 * во всех полях — дерево и поведение iOS не меняются.
 */
import { useCallback, useMemo } from 'react';
import { Platform, type LayoutChangeEvent } from 'react-native';
import { Gesture, type ComposedGesture, type GestureType } from 'react-native-gesture-handler';
import {
  runOnJS,
  useAnimatedScrollHandler,
  useSharedValue,
  withSpring,
  withTiming,
  type ScrollHandlerProcessed,
  type SharedValue,
  type WithSpringConfig,
} from 'react-native-reanimated';
import {
  contentShiftOf,
  fingerPull,
  isAtEdge,
  PAN_ACTIVE_OFFSET_Y,
  pullFractionOf,
  RESET_DURATION_MS,
  rubberBand,
  shouldCommit,
  shouldFireMiss,
  type OverdragEdge,
} from './androidOverdrag';

const IS_ANDROID = Platform.OS === 'android';

export interface AndroidOverdragParams {
  /** У какого края списка живёт overdrag: низ Поиска или верх Маркета. */
  edge: OverdragEdge;
  /**
   * Worklet-гейт «можно ли сейчас тянуть» (home-view, слой не committed…).
   * Должен быть стабильной ссылкой без deps — читает только shared values.
   */
  canPull: () => boolean;
  pullFraction: SharedValue<number>;
  dragging: SharedValue<number>;
  lastHapticStep: SharedValue<number>;
  committedAnim: SharedValue<number>;
  /** Текущее committed в UI-потоке — чтобы не запускать spring в ту же точку. */
  committedSv: SharedValue<number>;
  /** Куда едет committedAnim на commit: 1 — вход в Маркет, 0 — выход. */
  commitTarget: 0 | 1;
  /** Порог commit'а в offset-единицах (COMMIT_DISTANCE / EXIT_COMMIT_DISTANCE). */
  distance: number;
  spring: WithSpringConfig;
  onCommit: () => void;
  onMiss: () => void;
}

export interface AndroidOverdragBinding {
  /** RNGH-жест на список (Pan ∥ Native). iOS — undefined. */
  listGesture?: ComposedGesture | GestureType;
  /** Замена iOS-onScroll: пишет метрики списка в shared values. iOS — undefined. */
  onScroll?: ScrollHandlerProcessed;
  /** Знаковый translateY для контента/шапки списка: rubberBand(finger). iOS — undefined. */
  shift?: SharedValue<number>;
  /** Метрики не только из onScroll: до первого скролла его просто нет. */
  onLayout?: (e: LayoutChangeEvent) => void;
  onContentSizeChange?: (w: number, h: number) => void;
}

export function useAndroidOverdrag({
  edge,
  canPull,
  pullFraction,
  dragging,
  lastHapticStep,
  committedAnim,
  committedSv,
  commitTarget,
  distance,
  spring,
  onCommit,
  onMiss,
}: AndroidOverdragParams): AndroidOverdragBinding {
  // Метрики списка. contentH стартует с Infinity: «край снизу» до первого
  // замера не наступает, «край сверху» (scrollY<=1) — наступает, если
  // вьюпорт уже измерен onLayout'ом.
  const scrollY = useSharedValue(0);
  const viewportH = useSharedValue(0);
  const contentH = useSharedValue(Infinity);
  // Якорь translationY, от которого считаем ход пальца; armed — палец уже
  // у края и ход копится.
  const anchorY = useSharedValue(0);
  const armed = useSharedValue(0);
  const shift = useSharedValue(0);

  // Только метрики: onBeginDrag/onEndDrag здесь нет намеренно — решение
  // принимает Pan, а гонка двух хендлеров за dragging дала бы ложные commit'ы.
  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollY.value = e.contentOffset.y;
      viewportH.value = e.layoutMeasurement.height;
      contentH.value = e.contentSize.height;
    },
  });

  const onLayout = useCallback((e: LayoutChangeEvent) => {
    viewportH.value = e.nativeEvent.layout.height;
  }, [viewportH]);
  const onContentSizeChange = useCallback((_w: number, h: number) => {
    contentH.value = h;
  }, [contentH]);

  const listGesture = useMemo<ComposedGesture | undefined>(() => {
    if (!IS_ANDROID) return undefined;
    const pan = Gesture.Pan()
      .maxPointers(1)
      .activeOffsetY([-PAN_ACTIVE_OFFSET_Y, PAN_ACTIVE_OFFSET_Y])
      .onStart((e) => {
        'worklet';
        armed.value = 0;
        shift.value = 0;
        if (!canPull()) {
          dragging.value = 0;
          return;
        }
        dragging.value = 1;
        lastHapticStep.value = -1;
        // Убивает бегущий withTiming(0) прошлого отпускания: иначе хвост
        // анимации перепишет прогресс поверх нового касания.
        pullFraction.value = 0;
        anchorY.value = e.translationY;
      })
      .onUpdate((e) => {
        'worklet';
        if (dragging.value !== 1) return;
        if (!canPull()) {
          armed.value = 0;
          pullFraction.value = 0;
          shift.value = 0;
          return;
        }
        // Не у края (докрутка, рост контента при пагинации) — прогресс
        // с нуля от нового края, якорь едет за пальцем.
        if (!isAtEdge(edge, scrollY.value, contentH.value, viewportH.value)) {
          armed.value = 0;
          anchorY.value = e.translationY;
          pullFraction.value = 0;
          shift.value = 0;
          return;
        }
        if (armed.value === 0) {
          armed.value = 1;
          anchorY.value = e.translationY;
        }
        let finger = fingerPull(edge, e.translationY, anchorY.value);
        // Откат пальца назад — перезаякориваем, чтобы прогресс не «залипал».
        if (finger < 0) {
          anchorY.value = e.translationY;
          finger = 0;
        }
        const overdrag = rubberBand(finger, viewportH.value);
        shift.value = contentShiftOf(edge, overdrag);
        pullFraction.value = pullFractionOf(overdrag, distance);
      })
      .onEnd(() => {
        'worklet';
        // Решение — только на успешное отпускание и только если тянули у
        // края: иначе BEGAN→FAILED тапа в ближайшие 260 мс после commit'а
        // читает хвост withTiming(pullFraction) и делает ложный exit/miss.
        if (dragging.value !== 1 || armed.value !== 1) return;
        const p = pullFraction.value;
        if (shouldCommit(p)) {
          runOnJS(onCommit)();
          if (committedSv.value !== commitTarget) {
            committedAnim.value = withSpring(commitTarget, spring);
          }
        } else if (shouldFireMiss(p)) {
          runOnJS(onMiss)();
        }
      })
      .onFinalize(() => {
        'worklet';
        // Отмена (второй палец, перехват каруселью, сворачивание) и обычное
        // отпускание — один и тот же сброс, без onCommit/onMiss.
        dragging.value = 0;
        armed.value = 0;
        pullFraction.value = withTiming(0, { duration: RESET_DURATION_MS });
        shift.value = withTiming(0, { duration: RESET_DURATION_MS });
      });
    // shouldCancelWhenOutside(false): палец при тяге уходит за край списка —
    // Native не должен отменяться и ронять весь Simultaneous.
    const native = Gesture.Native().shouldCancelWhenOutside(false);
    return Gesture.Simultaneous(pan, native);
    // Shared values и canPull стабильны на всё время жизни экрана; жест
    // пересобирается только когда меняются JS-колбэки.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onCommit, onMiss]);

  if (!IS_ANDROID) return {};
  return { listGesture, onScroll, shift, onLayout, onContentSizeChange };
}
