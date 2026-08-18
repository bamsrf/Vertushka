/**
 * CoachPulse — подсветка элемента, который объясняет активная подсказка.
 *
 * Обёртка ничего не измеряет и не позиционируется в окне: подсветка рисуется
 * absolute внутри самой цели, поэтому всегда совпадает с ней — этим и
 * отличается от старого spotlight-тура с measureInWindow.
 *
 * Анимация живёт только пока active=true (подсказка на экране) и снимается
 * через cancelAnimation — фоновых таймеров после закрытия не остаётся.
 *
 * Две части, и работают они по-разному.
 *
 * ОСНОВА — рамка с заливкой, которая дышит: цвет наливается и уходит по
 * циклу. Она есть у обеих форм и не гаснет никогда, пока висит подсказка.
 * Раньше её не было, и у 'pulse' между волнами цель оставалась вовсе
 * неотмеченной: смотришь на статичный кадр — и не понимаешь, о каком именно
 * блоке речь. Дыхание решает и вторую задачу: движение видно боковым зрением,
 * поэтому цель находится взглядом, а не поиском.
 *
 * ВОЛНА — расходящееся кольцо поверх основы, только у 'pulse'. Повтор мозг
 * читает как «непрочитанное уведомление». Если цель и так пульсирует сама
 * (кнопка радара с sonar'ом), волна сливается с её собственной анимацией — и
 * постоянная индикация работы фичи начинает читаться как незакрытый шаг
 * онбординга. Таким целям — 'glow', то есть одна дышащая основа без волны.
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
  /** Радиус рамки. Должен совпадать со скруглением цели. */
  radius?: number;
  /** Насколько подсветка выходит за границы цели. */
  inset?: number;
  /**
   * Поправка по сторонам, поверх `inset`. Нужна, когда обёрнутый элемент несёт
   * собственные внешние отступы: обёртка их учитывает, и рамка без поправки
   * обводила бы не сам блок, а блок вместе с его margin'ами.
   *
   * Положительное значение раздвигает подсветку наружу, отрицательное —
   * втягивает внутрь ровно на величину чужого отступа.
   */
  edges?: { top?: number; right?: number; bottom?: number; left?: number };
  /** См. шапку файла. По умолчанию 'pulse'. */
  variant?: 'pulse' | 'glow';
  style?: StyleProp<ViewStyle>;
}

/** Полный вдох-выдох рамки. Медленно — быстрое мигание читается как ошибка. */
const BREATH_MS = 1500;

export function CoachPulse({
  active,
  children,
  radius = 18,
  inset = 0,
  edges,
  variant = 'pulse',
  style,
}: CoachPulseProps) {
  const breathe = useSharedValue(0);
  const wave = useSharedValue(0);

  useEffect(() => {
    if (!active) {
      cancelAnimation(breathe);
      cancelAnimation(wave);
      breathe.value = 0;
      wave.value = 0;
      return;
    }
    // reverse=true, а не рестарт с нуля: цвет должен уходить так же плавно,
    // как наливался. С рестартом получается моргание.
    breathe.value = withRepeat(
      withTiming(1, { duration: BREATH_MS, easing: Easing.inOut(Easing.quad) }),
      -1,
      true,
    );
    if (variant === 'pulse') {
      wave.value = withRepeat(
        withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }),
        -1,
        false,
      );
    }
    return () => {
      cancelAnimation(breathe);
      cancelAnimation(wave);
      breathe.value = 0;
      wave.value = 0;
    };
  }, [active, variant, breathe, wave]);

  // Не с нуля: в самой тусклой фазе рамка всё равно видна, иначе на статичном
  // кадре цель снова теряется — ровно то, из-за чего это и переделано.
  const baseStyle = useAnimatedStyle(() => ({
    opacity: interpolate(breathe.value, [0, 1], [0.45, 1]),
  }));

  const waveStyle = useAnimatedStyle(() => ({
    // Всплеск от 0 в конце цикла, чтобы кольцо не «схлопывалось» рывком.
    opacity: interpolate(wave.value, [0, 0.15, 1], [0, 0.55, 0]),
    transform: [{ scale: interpolate(wave.value, [0, 1], [1, 1.9]) }],
  }));

  const box = {
    borderRadius: radius,
    top: -(inset + (edges?.top ?? 0)),
    left: -(inset + (edges?.left ?? 0)),
    right: -(inset + (edges?.right ?? 0)),
    bottom: -(inset + (edges?.bottom ?? 0)),
  };

  return (
    <View style={style}>
      {active && (
        <>
          <Reanimated.View
            pointerEvents="none"
            style={[styles.base, box, baseStyle]}
          />
          {variant === 'pulse' && (
            <Reanimated.View
              pointerEvents="none"
              style={[styles.wave, box, waveStyle]}
            />
          )}
        </>
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: Colors.royalBlue,
    // Заливка полупрозрачная — содержимое цели должно читаться сквозь неё.
    backgroundColor: Colors.royalBlue + '1F',
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.45,
    shadowRadius: 10,
    elevation: 0,
  },
  wave: {
    position: 'absolute',
    borderWidth: 1.5,
    borderColor: Colors.royalBlue,
  },
});
