/**
 * SwipeBackHint — подсказка про возврат назад свайпом вправо.
 *
 * Жест есть на каждом вложенном экране приложения и с любой точки экрана: на
 * iOS его везёт native-stack (`fullScreenGestureEnabled` в app/_layout.tsx),
 * на Android — свой Pan в components/AndroidEdgeSwipeBack.tsx. Про него не
 * знают: люди ищут стрелку в шапке на каждой странице, а на экранах, где
 * шапка уехала при скролле, застревают вовсе.
 *
 * Почему форма другая, чем у остальных жест-подсказок. Те двигают саму цель:
 * нудж пишет в ту же shared value, что и палец. Здесь цель — ЭКРАН, и на iOS
 * его тащит нативный стек, своей shared value нет. Двигать весь Stack ради
 * подсказки нельзя: трансформ на корневом контейнере ломает фиксированные
 * панели, клавиатуру и модалки. Поэтому подсказка рисует жест рядом с собой.
 *
 * Форма: пилюля у левого края, примерно на середине высоты — там, где палец
 * и начинает движение. Внутри бегущие вправо шевроны и одна короткая строка.
 * `pointerEvents="none"` — сквозь неё можно и нажимать, и свайпать; подсказка
 * физически не может перехватить тот жест, которому учит.
 *
 * Живёт 4 секунды и уходит сама. Крестика нет намеренно: закрывать
 * четырёхсекундную плашку — работа, которой человек не просил, а промах по
 * крестику на краю экрана как раз и запустил бы свайп.
 */
import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { SwipeLeftHint } from '../ui/SwipeLeftHint';
import { useReduceMotion } from '../../lib/useAnimationGate';
import { BorderRadius, Colors, Spacing, Typography } from '../../constants/theme';

/** Сколько плашка висит, прежде чем уйти сама. */
const LIFETIME_MS = 4000;
const FADE_IN_MS = 260;
const FADE_OUT_MS = 320;

/**
 * Доля высоты окна, на которой стоит пилюля. Чуть ниже середины: там
 * находится большой палец при обычном хвате, и там же не мешают ни шапка,
 * ни нижняя панель.
 */
const VERTICAL_ANCHOR = 0.55;

interface SwipeBackHintProps {
  /** Показывать. Решение принимает гейт жест-подсказок. */
  visible: boolean;
  /** Отыграла — сообщить гейту, что слот свободен. */
  onDone: () => void;
}

export function SwipeBackHint({ visible, onDone }: SwipeBackHintProps) {
  const insets = useSafeAreaInsets();
  const reduceMotion = useReduceMotion();
  const appear = useSharedValue(0);

  useEffect(() => {
    if (!visible) return;

    appear.value = withTiming(1, {
      duration: FADE_IN_MS,
      easing: Easing.out(Easing.cubic),
    });

    const hide = setTimeout(() => {
      appear.value = withTiming(0, {
        duration: FADE_OUT_MS,
        easing: Easing.in(Easing.cubic),
      });
    }, LIFETIME_MS);

    // Гейту сообщаем после того, как плашка успела раствориться: иначе слот
    // освободится раньше времени и на том же экране сразу заявится соседняя
    // подсказка, наложившись на уходящую.
    const done = setTimeout(onDone, LIFETIME_MS + FADE_OUT_MS);

    return () => {
      clearTimeout(hide);
      clearTimeout(done);
      appear.value = 0;
    };
  }, [visible, appear, onDone]);

  const style = useAnimatedStyle(() => ({
    opacity: appear.value,
    // Плашка сама выезжает вправо — то же направление, что и жест. Под
    // Reduce Motion выезда нет, остаётся проявление.
    transform: [{ translateX: reduceMotion ? 0 : (1 - appear.value) * -12 }],
  }));

  if (!visible) return null;

  return (
    <View style={styles.host} pointerEvents="none">
      <Animated.View
        style={[styles.pill, { marginTop: insets.top }, style]}
        accessibilityRole="text"
        accessibilityLabel="Чтобы вернуться назад, смахните экран вправо"
      >
        <SwipeLeftHint active direction="right" color={Colors.royalBlue} />
        <Text style={styles.text}>Смахни вправо — вернёшься назад</Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  host: {
    // Без StyleSheet.absoluteFillObject — его нет в RN 0.86, спред молча даёт
    // {} и оверлей теряет position:absolute (см. SDK_UPGRADE_CHECKLIST).
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    // Пилюля прижата к левому краю: жест начинается оттуда, и подсказка
    // стоит там, куда ляжет палец.
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
    paddingTop: `${VERTICAL_ANCHOR * 100}%`,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingVertical: Spacing.sm,
    paddingLeft: Spacing.sm,
    paddingRight: Spacing.md,
    marginLeft: Spacing.md,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.background,
    // Тень, а не рамка: плашка висит над произвольным контентом, и рамка на
    // тёмной обложке потерялась бы.
    shadowColor: Colors.royalBlue,
    shadowOpacity: 0.22,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
  text: {
    ...Typography.caption,
    color: Colors.text,
    fontWeight: '600',
  },
});
