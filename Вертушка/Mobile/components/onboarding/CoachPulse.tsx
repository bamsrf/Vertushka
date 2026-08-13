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
 *
 * Две формы, и различаются они НЕ цветом, а повторяемостью:
 *   'pulse' — расходящееся кольцо. Годится для статичной цели;
 *   'glow'  — ровный ореол: проявился и держится, пока висит подсказка.
 * Повтор мозг читает как «непрочитанное уведомление». Если цель и так
 * пульсирует сама (кнопка радара с sonar'ом), второе пульсирующее кольцо
 * сливается с ней в одно впечатление — и постоянная индикация работы фичи
 * начинает читаться как незакрытый шаг онбординга. Поэтому таким целям —
 * ореол, который ни с каким уведомлением не спутать.
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
  /** Радиус кольца/ореола. Должен совпадать со скруглением цели. */
  radius?: number;
  /** Насколько подсветка выходит за границы цели. */
  inset?: number;
  /** См. шапку файла. По умолчанию 'pulse'. */
  variant?: 'pulse' | 'glow';
  style?: StyleProp<ViewStyle>;
}

export function CoachPulse({
  active,
  children,
  radius = 18,
  inset = 0,
  variant = 'pulse',
  style,
}: CoachPulseProps) {
  const pulse = useSharedValue(0);

  useEffect(() => {
    if (!active) {
      cancelAnimation(pulse);
      pulse.value = 0;
      return;
    }
    pulse.value =
      variant === 'glow'
        ? // Ореол не повторяется вовсе: проявился и держится. Именно
          // отсутствие повтора отличает «вот это место» от «непрочитанное».
          withTiming(1, { duration: 320, easing: Easing.out(Easing.cubic) })
        : withRepeat(
            withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }),
            -1,
            false,
          );
    return () => {
      cancelAnimation(pulse);
      pulse.value = 0;
    };
  }, [active, variant, pulse]);

  const ringStyle = useAnimatedStyle(() =>
    variant === 'glow'
      ? { opacity: pulse.value, transform: [{ scale: 1 }] }
      : {
          // Всплеск от 0 в конце цикла, чтобы кольцо не «схлопывалось» рывком.
          opacity: interpolate(pulse.value, [0, 0.15, 1], [0, 0.6, 0]),
          transform: [{ scale: interpolate(pulse.value, [0, 1], [1, 1.9]) }],
        },
  );

  return (
    <View style={style}>
      {active && (
        <Reanimated.View
          pointerEvents="none"
          style={[
            styles.ring,
            variant === 'glow' && styles.glow,
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
  glow: {
    // Плотнее кольца и с заливкой: ореол не двигается, поэтому берёт внимание
    // не движением, а весом. Заливка полупрозрачная — иконка цели читается.
    borderWidth: 2,
    backgroundColor: Colors.royalBlue + '1F',
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 10,
    elevation: 0,
  },
});
