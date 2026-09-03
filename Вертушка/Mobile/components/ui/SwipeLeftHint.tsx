/**
 * SwipeLeftHint — три шеврона «‹‹‹» с волной, бегущей справа налево.
 *
 * Ставится слева от элемента, который надо утянуть влево (винил-кноб в
 * ManualAddVinylToggle). Проблема, которую решает: раскрытую пилюлю люди жмут,
 * а не тянут, — статичная стрелка это не чинит, потому что её читают как
 * декор. Волна читается как направление: подсвечивается сначала ближний к
 * пальцу шеврон, затем следующий и следующий — глаз ведёт от кноба влево.
 *
 * Шевроны не «моргают» до нуля: в тусклой фазе они всё равно видны (0.22),
 * иначе на статичном кадре — например, на скриншоте или при reduce-motion —
 * подсказка исчезает целиком. Тот же приём, что в CoachPulse.
 *
 * Анимация живёт только пока active=true и снимается через cancelAnimation —
 * фоновых таймеров после сворачивания не остаётся.
 */
import { useEffect } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';

/** Сторона бокса под один шеврон; сам глиф внутри уже. */
const GLYPH = 13;
/** Наложение боксов: визуальный шаг между остриями. */
const OVERLAP = -4;
/**
 * Два, а не три: в пилюле ровно столько места, сколько остаётся от текста, и
 * третий шеврон съедал воздух между ними. Направление читается и по паре —
 * его задаёт волна, а не количество.
 */
const COUNT = 2;
/** Полный проход волны. Медленно — быстрая волна читается как «загрузка». */
const CYCLE_MS = 1500;
/** Отставание соседа по фазе: волна идёт справа налево. */
const LEAD = 0.15;

/** Ширина группы — нужна снаружи, чтобы отвести ей место в раскладке. */
export const SWIPE_HINT_WIDTH = COUNT * GLYPH + (COUNT - 1) * OVERLAP;

interface SwipeLeftHintProps {
  active: boolean;
  /** По умолчанию — цвет текста пилюли, чтобы подсказка не спорила с кнобом. */
  color?: string;
  style?: StyleProp<ViewStyle>;
}

interface ChevronProps {
  progress: SharedValue<number>;
  delay: number;
  color: string;
  /** Наложение на предыдущий шеврон; у первого в ряду отступа нет. */
  offset: number;
}

function Chevron({ progress, delay, color, offset }: ChevronProps) {
  const style = useAnimatedStyle(() => {
    // Фаза шеврона в цикле: +1 и %1 — чтобы отрицательная разница завернулась.
    const local = (progress.value - delay + 1) % 1;
    return {
      opacity: interpolate(local, [0, 0.1, 0.34, 1], [0.22, 1, 0.22, 0.22]),
      transform: [
        // Подсвеченный шеврон чуть подаётся влево — направление, а не мерцание.
        { translateX: interpolate(local, [0, 0.1, 0.34, 1], [0, -2.5, 0, 0]) },
        { scale: interpolate(local, [0, 0.1, 0.34, 1], [0.92, 1.08, 0.92, 0.92]) },
      ],
    };
  });

  return (
    <Animated.View style={[{ marginLeft: offset }, style]}>
      <Svg width={GLYPH} height={GLYPH} viewBox="0 0 14 14">
        <Path
          d="M9.4 2 L3.8 7 L9.4 12"
          stroke={color}
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </Svg>
    </Animated.View>
  );
}

export function SwipeLeftHint({ active, color = '#23244D', style }: SwipeLeftHintProps) {
  const progress = useSharedValue(0);

  useEffect(() => {
    if (!active) {
      cancelAnimation(progress);
      progress.value = 0;
      return;
    }
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(1, { duration: CYCLE_MS, easing: Easing.linear }),
      -1,
      false,
    );
    return () => {
      cancelAnimation(progress);
      progress.value = 0;
    };
  }, [active, progress]);

  return (
    <View style={[styles.row, style]} pointerEvents="none">
      {Array.from({ length: COUNT }, (_, i) => (
        <Chevron
          key={i}
          progress={progress}
          // Ближний к кнобу (правый) загорается первым.
          delay={(COUNT - 1 - i) * LEAD}
          color={color}
          offset={i === 0 ? 0 : OVERLAP}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
});
