/**
 * CoachPulse — пульсирующее кольцо вокруг элемента, который объясняет
 * активная контекстная подсказка.
 *
 * Обёртка ничего не измеряет и не позиционируется в окне: кольцо рисуется
 * absolute внутри самой цели, поэтому всегда совпадает с ней — этим и
 * отличается от старого spotlight-тура с measureInWindow.
 *
 * Анимация живёт только пока active=true (подсказка на экране) и снимается
 * через cancelAnimation — фоновых таймеров после закрытия не остаётся.
 */
import { useEffect } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Reanimated, {
  Easing,
  cancelAnimation,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { Colors } from '../../constants/theme';

interface CoachPulseProps {
  active: boolean;
  children: React.ReactNode;
  /** Радиус кольца. Должен совпадать со скруглением цели. */
  radius?: number;
  /** Насколько кольцо выходит за границы цели. */
  inset?: number;
  style?: StyleProp<ViewStyle>;
}

export function CoachPulse({
  active,
  children,
  radius = 18,
  inset = 0,
  style,
}: CoachPulseProps) {
  const pulse = useSharedValue(0);

  useEffect(() => {
    if (!active) {
      cancelAnimation(pulse);
      pulse.value = 0;
      return;
    }
    pulse.value = withRepeat(
      withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }),
      -1,
      false,
    );
    return () => {
      cancelAnimation(pulse);
      pulse.value = 0;
    };
  }, [active, pulse]);

  const ringStyle = useAnimatedStyle(() => ({
    // Всплеск от 0 в конце цикла, чтобы кольцо не «схлопывалось» рывком.
    opacity: interpolate(pulse.value, [0, 0.15, 1], [0, 0.6, 0]),
    transform: [{ scale: interpolate(pulse.value, [0, 1], [1, 1.9]) }],
  }));

  return (
    <View style={style}>
      {active && (
        <Reanimated.View
          pointerEvents="none"
          style={[
            styles.ring,
            { borderRadius: radius, top: -inset, left: -inset, right: -inset, bottom: -inset },
            ringStyle,
          ]}
        />
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  ring: {
    position: 'absolute',
    borderWidth: 1.5,
    borderColor: Colors.royalBlue,
  },
});
