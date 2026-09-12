/**
 * AndroidEdgeSwipeBack — Android-only свайп «назад» с любого места экрана
 * (аналог iOS full-screen swipe).
 *
 * Зачем: в react-native-screens 4.26 `gestureEnabled` / `fullScreenGestureEnabled`
 * помечены `@platform ios`. На Android native-stack умеет только predictive
 * back, а он живёт на системной жестовой навигации. У владельца телефон с
 * 3-кнопочной панелью — системного жеста нет вовсе, со stack-экрана можно
 * уйти только кнопкой в шапке или системной «Назад».
 *
 * Как устроено: Pan-жест RNGH на обёртке всего Stack, без hitSlop. Тапы и
 * скроллы под ним идут как обычно, пока жест не активировался
 * (`activeOffsetX` вправо). `failOffsetX` отдаёт движение влево,
 * `failOffsetY` — вертикальные скроллы. Почему пороги не ломают
 * горизонтальные карусели и свайп-строки — в lib/edgeSwipeBack.ts.
 *
 * Движение: экран идёт за пальцем 1:1 целиком на UI-потоке (shared value в
 * onUpdate + useAnimatedStyle, без runOnJS). Прыжок на порог активации
 * компенсируется: translationX в момент onStart запоминается и вычитается.
 * Слева от уезжающего экрана — фон приложения с тёмной подложкой, которая
 * светлеет по мере прогресса (как затемнение нижнего экрана в iOS-стеке).
 *
 * Commit (дотянул до COMMIT_FRACTION ширины или швырнул): экран доезжает за
 * край окна withTiming, и только по завершении шлём «Назад». Чтобы
 * native-stack не проиграл поверх свой slide (экран вернулся бы на 0 и уехал
 * второй раз), перед pop поднимаем флаг `useSwipeBackPopStore` — `_layout.tsx`
 * на Android переключает `screenOptions.animation` в 'none' ровно на этот
 * pop. Порядок гарантирован через useEffect: «Назад» эмулируем только после
 * коммита рендера с новыми options. После смены маршрута сдвиг сбрасываем в
 * 0 (иначе следующий экран отрендерится уехавшим) и флаг опускаем — кнопка
 * «Назад» и push продолжают ездить нативным slide_from_right.
 * Если маршрут не сменился за POP_FALLBACK_MS — «Назад» съел оверлей
 * (useAndroidBackClose): экран возвращаем на место.
 *
 * Куда уходим: не `router.back()` напрямую, а эмуляция системной «Назад»
 * через тот же `hardwareBackPress`, на который подписаны `useAndroidBackClose`
 * (шиты/оверлеи) и expo-router (pop навигации). Приоритет получается ровно
 * как у физической кнопки: открытый шит закрывается, экран остаётся.
 * Гард `router.canGoBack()` обязателен: если ни один подписчик не вернул
 * true, RN зовёт `exitApp()`.
 *
 * Куда жест не дотягивается: gorhom-модалки рендерятся в PortalHost
 * провайдера (выше и вне обёртки), RN `<Modal>` — отдельное окно. Свайп по
 * ним ничего не делает, но и экран под ними не выпадает.
 *
 * iOS: прозрачный passthrough — там работает нативный жест native-stack.
 */
import { ReactNode, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  DeviceEventEmitter,
  Platform,
  StyleSheet,
  useWindowDimensions,
  View,
} from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { usePathname, useRouter, useSegments } from 'expo-router';
import { Colors } from '../constants/theme';
import {
  ACTIVE_OFFSET_X,
  backdropOpacity,
  CANCEL_DURATION_MS,
  COMMIT_DURATION_MS,
  FAIL_OFFSET_X,
  FAIL_OFFSET_Y,
  followShift,
  isEdgeSwipeEnabledForSegment,
  POP_FALLBACK_MS,
  shouldCommitSwipeBack,
  swipeProgress,
  useSwipeBackPopStore,
} from '../lib/edgeSwipeBack';

const EASE_OUT = Easing.out(Easing.cubic);

interface AndroidEdgeSwipeBackProps {
  children: ReactNode;
}

export function AndroidEdgeSwipeBack({ children }: AndroidEdgeSwipeBackProps) {
  // Platform.OS — константа на всё время жизни процесса, поэтому ветвление
  // на разные компоненты не нарушает rules-of-hooks и не меняет дерево iOS.
  if (Platform.OS !== 'android') return <>{children}</>;
  return <EdgeSwipeHost>{children}</EdgeSwipeHost>;
}

function EdgeSwipeHost({ children }: AndroidEdgeSwipeBackProps) {
  const router = useRouter();
  const segments = useSegments();
  const pathname = usePathname();
  const { width } = useWindowDimensions();
  const enabled = isEdgeSwipeEnabledForSegment(segments[0]);

  const shift = useSharedValue(0);
  const origin = useSharedValue(0);
  // Пока экран уехал и ждёт pop — новые касания не двигают сдвиг.
  const locked = useSharedValue(false);

  const popWithoutAnimation = useSwipeBackPopStore((s) => s.popWithoutAnimation);
  const setPopWithoutAnimation = useSwipeBackPopStore((s) => s.setPopWithoutAnimation);
  const pendingPop = useRef(false);
  const fallbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearFallback = useCallback(() => {
    if (fallbackTimer.current === null) return;
    clearTimeout(fallbackTimer.current);
    fallbackTimer.current = null;
  }, []);

  const releaseScreen = useCallback(
    (animated: boolean) => {
      clearFallback();
      pendingPop.current = false;
      locked.value = false;
      shift.value = animated ? withTiming(0, { duration: CANCEL_DURATION_MS, easing: EASE_OUT }) : 0;
      setPopWithoutAnimation(false);
    },
    [clearFallback, locked, setPopWithoutAnimation, shift],
  );

  // Экран уехал за край: просим _layout убрать нативную анимацию у pop.
  const requestPop = useCallback(() => {
    if (!router.canGoBack()) {
      releaseScreen(true);
      return;
    }
    pendingPop.current = true;
    setPopWithoutAnimation(true);
  }, [releaseScreen, router, setPopWithoutAnimation]);

  // Эффект родителя Stack бежит после коммита, в котором Stack получил
  // animation: 'none' — только теперь pop безопасен.
  useEffect(() => {
    if (!popWithoutAnimation || !pendingPop.current) return;
    DeviceEventEmitter.emit('hardwareBackPress', {});
    clearFallback();
    fallbackTimer.current = setTimeout(() => {
      if (pendingPop.current) releaseScreen(true);
    }, POP_FALLBACK_MS);
  }, [popWithoutAnimation, clearFallback, releaseScreen]);

  // Маршрут сменился — pop прошёл. Следующий экран должен стоять на 0.
  useEffect(() => {
    if (pendingPop.current) releaseScreen(false);
  }, [pathname, releaseScreen]);

  useEffect(() => clearFallback, [clearFallback]);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .enabled(enabled)
        .maxPointers(1)
        .activeOffsetX(ACTIVE_OFFSET_X)
        .failOffsetX(-FAIL_OFFSET_X)
        .failOffsetY([-FAIL_OFFSET_Y, FAIL_OFFSET_Y])
        .onStart((e) => {
          if (locked.value) return;
          origin.value = e.translationX;
        })
        .onUpdate((e) => {
          if (locked.value) return;
          shift.value = followShift(e.translationX, origin.value);
        })
        .onEnd((e) => {
          if (locked.value) return;
          if (!shouldCommitSwipeBack(e, width)) return;
          locked.value = true;
          shift.value = withTiming(
            width,
            { duration: COMMIT_DURATION_MS, easing: EASE_OUT },
            (finished) => {
              if (finished) runOnJS(requestPop)();
            },
          );
        })
        .onFinalize(() => {
          // Отмена жеста или «не дотянул»: контент плавно возвращается.
          // После commit сдвиг заперт — не трогаем.
          if (locked.value) return;
          shift.value = withTiming(0, { duration: CANCEL_DURATION_MS, easing: EASE_OUT });
        }),
    [enabled, locked, origin, requestPop, shift, width],
  );

  const contentStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: shift.value }],
  }));

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: backdropOpacity(swipeProgress(shift.value, width)),
  }));

  return (
    <GestureDetector gesture={pan}>
      <View style={styles.host}>
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, styles.backdrop, backdropStyle]}
        />
        <Animated.View style={[styles.content, contentStyle]}>{children}</Animated.View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  host: { flex: 1, backgroundColor: Colors.background },
  backdrop: { backgroundColor: '#000' },
  content: { flex: 1 },
});
