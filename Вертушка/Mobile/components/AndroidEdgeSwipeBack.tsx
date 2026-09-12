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
 * (`activeOffsetX(25)` вправо). `failOffsetX(-10)` отдаёт движение влево,
 * `failOffsetY(±15)` — вертикальные скроллы.
 *
 * Почему не ломает горизонтальные карусели и свайп-строки (проверено по
 * android/ RNGH 2.32):
 *  - Нативный RN ScrollView/FlatList (horizontal) при драге на системном
 *    touch-slop (~8dp) зовёт `requestDisallowInterceptTouchEvent(true)`;
 *    RNGestureHandlerRootView перехватывает это и через
 *    `tryCancelAllHandlers` отменяет все ещё не активные жесты — наш в
 *    том числе. Карусель всегда успевает первой (8 < 25).
 *  - Свои Gesture.Pan (строки сообщений/вишлиста/уведомлений, AutoRail,
 *    ThresholdSheet, ReanimatedSwipeable) активируются на 6–12dp; в
 *    оркестраторе первый активировавшийся отменяет остальных, независимо
 *    от вложенности (`makeActive` → `shouldHandlerBeCancelledBy`).
 *  Итог: там, где под пальцем есть горизонтальный скролл/свайп, он и
 *  выигрывает; свайп «назад» ловится с остального экрана. Никаких реестров
 *  и `manualActivation` не нужно — приоритет задаётся порогами.
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
import { ReactNode, useCallback, useMemo } from 'react';
import { DeviceEventEmitter, Platform, StyleSheet } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useRouter, useSegments } from 'expo-router';
import {
  ACTIVE_OFFSET_X,
  FAIL_OFFSET_X,
  FAIL_OFFSET_Y,
  followShift,
  isEdgeSwipeEnabledForSegment,
  shouldCommitSwipeBack,
} from '../lib/edgeSwipeBack';

const RESET_DURATION_MS = 160;

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
  const enabled = isEdgeSwipeEnabledForSegment(segments[0]);
  const shift = useSharedValue(0);

  const emulateHardwareBack = useCallback(() => {
    if (!router.canGoBack()) return;
    DeviceEventEmitter.emit('hardwareBackPress', {});
  }, [router]);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .enabled(enabled)
        .maxPointers(1)
        .activeOffsetX(ACTIVE_OFFSET_X)
        .failOffsetX(-FAIL_OFFSET_X)
        .failOffsetY([-FAIL_OFFSET_Y, FAIL_OFFSET_Y])
        .onUpdate((e) => {
          shift.value = followShift(e.translationX);
        })
        .onEnd((e) => {
          if (!shouldCommitSwipeBack(e)) return;
          // Сброс мгновенный: нативная анимация pop не должна стартовать
          // из сдвинутого состояния.
          shift.value = 0;
          runOnJS(emulateHardwareBack)();
        })
        .onFinalize(() => {
          // Покрывает и отмену жеста, и «не дотянул»: контент плавно
          // возвращается на место. После commit это no-op (уже 0).
          shift.value = withTiming(0, { duration: RESET_DURATION_MS });
        }),
    [enabled, emulateHardwareBack, shift],
  );

  const style = useAnimatedStyle(() => ({
    transform: [{ translateX: shift.value }],
  }));

  return (
    <GestureDetector gesture={pan}>
      <Animated.View style={[styles.host, style]}>{children}</Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  host: { flex: 1 },
});
