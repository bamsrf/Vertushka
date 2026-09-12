/**
 * AndroidEdgeSwipeBack — Android-only свайп «назад» от левого края.
 *
 * Зачем: в react-native-screens 4.26 `gestureEnabled` / `fullScreenGestureEnabled`
 * помечены `@platform ios`. На Android native-stack умеет только predictive
 * back, а он живёт на системной жестовой навигации. У владельца телефон с
 * 3-кнопочной панелью — системного жеста нет вовсе, со stack-экрана можно
 * уйти только кнопкой в шапке или системной «Назад».
 *
 * Как устроено: не невидимая полоса поверх контента (она перекрыла бы левую
 * половину кнопки «назад» в шапке и таргеты в карточках), а Pan-жест на
 * обёртке всего Stack с `hitSlop({ left: 0, width: EDGE_WIDTH })` — RNGH сам
 * ограничивает распознавание полосой у края, а тапы и скроллы под ней идут
 * как обычно, пока жест не активировался. `failOffsetY` отдаёт вертикальные
 * скроллы; горизонтальные карусели живут своей жизнью везде, кроме самой
 * полосы (там жест приоритетнее — так же, как iOS-овский edge-swipe).
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
  EDGE_WIDTH,
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
        .hitSlop({ left: 0, width: EDGE_WIDTH })
        .activeOffsetX(ACTIVE_OFFSET_X)
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
