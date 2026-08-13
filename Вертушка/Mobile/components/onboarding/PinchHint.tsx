/**
 * PinchHint — подсказка про pinch-to-zoom сетки коллекции.
 *
 * Единственная подсказка, которую нельзя объяснить текстом в списке: жест надо
 * показать. Два кружка съезжаются к центру и разъезжаются обратно — петля
 * играет трижды и гаснет.
 *
 * Позиционируется absoluteFill внутри контейнера сетки, БЕЗ измерения
 * координат: родитель сам задаёт область. Не перехватывает касания
 * (pointerEvents="none" на всём, кроме кнопки «Понятно»), поэтому не мешает
 * скроллить и не ломается, если пользователь начал жест раньше.
 */
import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import { Colors, BorderRadius, Spacing, Typography } from '../../constants/theme';

const LOOPS = 3;
const HALF_CYCLE_MS = 900;
/** Насколько кружки разъезжаются от центра. */
const SPREAD = 34;

interface PinchHintProps {
  onDismiss: () => void;
}

export function PinchHint({ onDismiss }: PinchHintProps) {
  const spread = useRef(new Animated.Value(1)).current;
  const fade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const pulse = Animated.sequence([
      Animated.timing(spread, {
        toValue: 0,
        duration: HALF_CYCLE_MS,
        easing: Easing.inOut(Easing.quad),
        useNativeDriver: true,
      }),
      Animated.timing(spread, {
        toValue: 1,
        duration: HALF_CYCLE_MS,
        easing: Easing.inOut(Easing.quad),
        useNativeDriver: true,
      }),
    ]);

    const anim = Animated.sequence([
      Animated.timing(fade, {
        toValue: 1,
        duration: 240,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
      Animated.loop(pulse, { iterations: LOOPS }),
      Animated.timing(fade, {
        toValue: 0,
        duration: 320,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }),
    ]);

    anim.start(({ finished }) => {
      // Доиграла до конца — считаем подсказку показанной и закрываем сами.
      if (finished) onDismiss();
    });

    return () => {
      // Уход с экрана в середине петли: без stop анимация продолжает крутиться
      // в фоне и греет телефон (тот же класс проблем, что в MarketEntryBanner).
      anim.stop();
    };
  }, [spread, fade, onDismiss]);

  const left = {
    transform: [
      { translateX: spread.interpolate({ inputRange: [0, 1], outputRange: [0, -SPREAD] }) },
    ],
  };
  const right = {
    transform: [
      { translateX: spread.interpolate({ inputRange: [0, 1], outputRange: [0, SPREAD] }) },
    ],
  };

  return (
    <Animated.View
      style={[StyleSheet.absoluteFill, styles.root, { opacity: fade }]}
      pointerEvents="box-none"
    >
      <View style={styles.plate} pointerEvents="box-none">
        <View style={styles.dots} pointerEvents="none">
          <Animated.View style={[styles.dot, left]} />
          <Animated.View style={[styles.dot, right]} />
        </View>
        <Text style={styles.title}>Сожми двумя пальцами</Text>
        <Text style={styles.body}>Вся полка поместится на один экран</Text>
        <Pressable
          onPress={onDismiss}
          hitSlop={10}
          style={styles.gotIt}
          accessibilityRole="button"
        >
          <Text style={styles.gotItText}>Понятно</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: {
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 20,
  },
  plate: {
    alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.lg,
    borderRadius: BorderRadius.xl,
    backgroundColor: 'rgba(10, 11, 59, 0.86)',
  },
  dots: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 44,
    marginBottom: Spacing.sm,
  },
  dot: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(255,255,255,0.9)',
    marginHorizontal: 3,
  },
  title: {
    ...Typography.body,
    fontFamily: 'Inter_600SemiBold',
    color: '#fff',
  },
  body: {
    ...Typography.caption,
    color: 'rgba(255,255,255,0.75)',
    marginTop: 2,
  },
  gotIt: {
    marginTop: Spacing.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm - 2,
    borderRadius: BorderRadius.full,
    backgroundColor: 'rgba(255,255,255,0.16)',
  },
  gotItText: {
    ...Typography.caption,
    fontFamily: 'Inter_600SemiBold',
    color: '#fff',
  },
});
