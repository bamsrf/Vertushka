/**
 * NotificationSwipe — свайп-влево для удаления уведомления.
 *
 * Паттерн «ТЯНИ» как у вишлистов, но flavor=delete и баннер скрыт до тяги:
 *
 *   ┌──────────────────────────────┬─────────┐
 *   │ Контент строки (едет влево)   │ 🗑 удал. │  ← красный баннер, прибит right:0,
 *   └──────────────────────────────┴─────────┘    width = |dragX| (при rest = 0).
 *
 * Решает два бага legacy `Swipeable`:
 *  1. Тап после частичного свайпа больше НЕ проваливается в новость — Gesture.Pan
 *     с activeOffsetX перехватывает движение, а чистый тап (без сдвига) уходит
 *     в дочерний Touchable. На реальном свайпе responder отбирается у Touchable.
 *  2. Доведённый до конца свайп удаляет и НЕ открывает — навигация привязана
 *     только к tap-ветке, а delete вызывается из onEnd жеста.
 *
 * Иконка корзины — в полную высоту, без scale-анимации.
 */
import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { Icon } from '../ui';
import { Colors, Spacing } from '../../constants/theme';

interface NotificationSwipeProps {
  children: React.ReactNode;
  onDelete: () => void;
  style?: StyleProp<ViewStyle>;
}

const FULL_WIDTH = 88; // полная ширина баннера удаления при open
const OPEN_RATIO = 0.5; // протянул > половины → удаляем
const VELOCITY_OPEN = -650;
const ACTIVE_OFFSET = 12;
const FAIL_OFFSET_Y = 14;

export function NotificationSwipe({ children, onDelete, style }: NotificationSwipeProps) {
  // dragX: 0 (rest) → -FULL_WIDTH (open). Двигает контент И растит баннер.
  const dragX = useSharedValue(0);
  const startX = useSharedValue(0);

  const triggerDelete = useCallback(() => {
    onDelete();
  }, [onDelete]);

  const panGesture = Gesture.Pan()
    .activeOffsetX([-ACTIVE_OFFSET, ACTIVE_OFFSET])
    .failOffsetY([-FAIL_OFFSET_Y, FAIL_OFFSET_Y])
    .onStart(() => {
      startX.value = dragX.value;
    })
    .onUpdate((e) => {
      const next = startX.value + e.translationX;
      if (next > 0) {
        dragX.value = next * 0.12; // правый overscroll — упруго, без раскрытия
      } else if (next < -FULL_WIDTH) {
        dragX.value = -FULL_WIDTH - (next + FULL_WIDTH) * 0.4;
      } else {
        dragX.value = next;
      }
    })
    .onEnd((e) => {
      const shouldDelete = dragX.value < -FULL_WIDTH * OPEN_RATIO || e.velocityX < VELOCITY_OPEN;
      if (shouldDelete) {
        dragX.value = withTiming(-FULL_WIDTH, { duration: 160, easing: Easing.out(Easing.cubic) });
        runOnJS(triggerDelete)();
      } else {
        dragX.value = withTiming(0, { duration: 200, easing: Easing.out(Easing.cubic) });
      }
    });

  const contentStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: dragX.value }],
  }));

  const bannerStyle = useAnimatedStyle(() => ({
    width: Math.max(0, -dragX.value),
  }));

  return (
    <GestureDetector gesture={panGesture}>
      <View style={[styles.wrap, style]}>
        <Animated.View style={contentStyle}>{children}</Animated.View>

        <Animated.View style={[styles.banner, bannerStyle]} pointerEvents="box-none">
          <Pressable onPress={triggerDelete} style={styles.bannerPress} accessibilityLabel="Удалить">
            <Icon name="trash" size={22} color={Colors.background} />
          </Pressable>
        </Animated.View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
    overflow: 'hidden',
  },
  banner: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    backgroundColor: Colors.error,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  bannerPress: {
    width: FULL_WIDTH,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default NotificationSwipe;
