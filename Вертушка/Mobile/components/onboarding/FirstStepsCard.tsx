/**
 * FirstStepsCard — чеклист новичка в шапке коллекции.
 *
 * Живёт первым блоком ScrollableHeader, над «Папками», поэтому:
 *   - виден сразу при входе в коллекцию;
 *   - уезжает при скролле вместе с папками и не занимает постоянного места
 *     в липкой шапке (там и так тесно: Выбрать / вид / ₽ / фильтр / сортировка);
 *   - ничего не перекрывает и не блокирует — в отличие от старого spotlight.
 *
 * Прогресс приходит из useFirstSteps и выводится из реальных данных, так что
 * импорт коллекции из Discogs закрывает первый пункт сам.
 */
import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import { useFirstSteps, type FirstStepKey } from '../../lib/onboardingProgress';
import { analytics } from '../../lib/analytics';
import { BorderRadius, Colors, Spacing, Typography } from '../../constants/theme';
import { ms } from '../../lib/responsive';

/** Сколько держать финальную строку «пройдено» перед самоуничтожением. */
const DONE_LINGER_MS = 2600;

interface FirstStepsCardProps {
  /**
   * Переопределение действия для отдельных пунктов. Нужно там, где маршрут —
   * это тот же экран: «Разложить по папкам» из самой коллекции никуда не ведёт,
   * и без override тап был бы пустым.
   */
  overrides?: Partial<Record<FirstStepKey, () => void>>;
}

export function FirstStepsCard({ overrides }: FirstStepsCardProps = {}) {
  const router = useRouter();
  const {
    steps,
    doneCount,
    total,
    visible,
    allDone,
    nextStepKey,
    expanded,
    toggleExpanded,
    dismiss,
  } = useFirstSteps();

  const fill = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fill, {
      toValue: total === 0 ? 0 : doneCount / total,
      duration: 420,
      easing: Easing.bezier(0.22, 0.61, 0.36, 1),
      // width в процентах нативный драйвер не умеет.
      useNativeDriver: false,
    }).start();
  }, [doneCount, total, fill]);

  // Все пункты закрыты — показываем финальную строку и убираем карточку сами.
  useEffect(() => {
    if (!visible || !allDone) return;
    const handle = setTimeout(dismiss, DONE_LINGER_MS);
    return () => clearTimeout(handle);
  }, [visible, allDone, dismiss]);

  if (!visible) return null;

  const widthStyle = {
    width: fill.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }),
  };

  if (allDone) {
    return (
      <View style={styles.card}>
        <View style={styles.doneRow}>
          <Icon name="checkmark-circle" size={20} color={Colors.success} />
          <Text style={styles.doneText}>Первые шаги пройдены</Text>
        </View>
      </View>
    );
  }

  const handleStepPress = (key: FirstStepKey, route: string) => {
    Haptics.selectionAsync();
    analytics.onboardingStepTap(key);
    const override = overrides?.[key];
    if (override) {
      override();
      return;
    }
    router.push(route as never);
  };

  return (
    <View style={styles.card}>
      <Pressable
        style={styles.header}
        onPress={() => {
          Haptics.selectionAsync();
          toggleExpanded();
        }}
        accessibilityRole="button"
        accessibilityLabel={expanded ? 'Свернуть первые шаги' : 'Развернуть первые шаги'}
      >
        <Text style={styles.title}>Первые шаги</Text>

        {/* В свёрнутом виде прогресс-бар переезжает в строку заголовка —
            карточка ужимается до одной строки, но остаётся читаемой. */}
        {!expanded && (
          <View style={styles.inlineBar}>
            <Animated.View style={[styles.barFill, widthStyle]} />
          </View>
        )}

        <Text style={styles.counter}>
          {doneCount}/{total}
        </Text>
        <Icon
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color={Colors.textMuted}
        />
        <Pressable
          onPress={dismiss}
          hitSlop={10}
          style={styles.close}
          accessibilityRole="button"
          accessibilityLabel="Скрыть первые шаги"
        >
          <Icon name="close" size={16} color={Colors.textMuted} />
        </Pressable>
      </Pressable>

      {expanded && (
        <>
          <View style={styles.bar}>
            <Animated.View style={[styles.barFill, widthStyle]} />
          </View>

          <View style={styles.steps}>
            {steps.map((step) => {
              // «Зачем» раскрыт только у ближайшего невыполненного шага: пять
              // подписей разом превращают карточку в стену текста, а объяснение
              // нужно ровно тому пункту, который человек делает следующим.
              const showWhy = step.key === nextStepKey;
              return (
                <Pressable
                  key={step.key}
                  style={[styles.step, showWhy && styles.stepNext]}
                  onPress={step.done ? undefined : () => handleStepPress(step.key, step.route)}
                  disabled={step.done}
                  accessibilityRole={step.done ? 'text' : 'button'}
                  accessibilityLabel={showWhy ? `${step.label}. ${step.why}` : step.label}
                  accessibilityState={{ checked: step.done }}
                >
                  {/* Пустой кружок рисуем вьюхой, а не иконкой: в библиотеке нет
                      outline-эллипса, а неизвестное имя падает в fallback 'plus'. */}
                  {step.done ? (
                    <Icon name="checkmark-circle" size={18} color={Colors.success} />
                  ) : (
                    <View style={[styles.stepDot, showWhy && styles.stepDotNext]} />
                  )}

                  <View style={styles.stepTextWrap}>
                    <Text
                      style={[
                        styles.stepLabel,
                        step.done && styles.stepLabelDone,
                        showWhy && styles.stepLabelNext,
                      ]}
                    >
                      {step.label}
                    </Text>
                    {showWhy && <Text style={styles.stepWhy}>{step.why}</Text>}
                  </View>

                  {!step.done && (
                    <Icon name="chevron-forward" size={14} color={Colors.textMuted} />
                  )}
                </Pressable>
              );
            })}
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  title: {
    ...Typography.body,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
  },
  inlineBar: {
    flex: 1,
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
  },
  counter: {
    ...Typography.caption,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.royalBlue,
    // Без flex:1 в развёрнутом состоянии счётчик прижался бы к заголовку.
    marginLeft: 'auto',
  },
  close: {
    marginLeft: Spacing.xs,
  },
  bar: {
    height: 4,
    borderRadius: 2,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
    marginTop: Spacing.sm,
  },
  barFill: {
    height: '100%',
    borderRadius: 2,
    backgroundColor: Colors.royalBlue,
  },
  steps: {
    marginTop: Spacing.sm,
    gap: 2,
  },
  step: {
    flexDirection: 'row',
    // flex-start, а не center: у следующего шага две строки, и кружок должен
    // держаться заголовка, а не уезжать в середину блока.
    alignItems: 'flex-start',
    gap: Spacing.sm,
    paddingVertical: Spacing.sm - 2,
  },
  stepNext: {
    // Лёгкая подложка вместо жирной рамки: она отмечает «делай это сейчас»,
    // но не спорит с прогресс-баром за внимание.
    backgroundColor: Colors.royalBlue + '0A',
    borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.sm,
    marginHorizontal: -Spacing.sm + 2,
    paddingVertical: Spacing.sm,
  },
  stepDot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 1.5,
    borderColor: Colors.border,
    // Компенсируем разницу высоты строки, чтобы кружок встал по центру текста.
    marginTop: 1,
  },
  stepDotNext: {
    borderColor: Colors.royalBlue,
  },
  stepTextWrap: {
    flex: 1,
  },
  stepLabel: {
    ...Typography.body,
    fontSize: ms(14),
    color: Colors.text,
  },
  stepLabelNext: {
    fontFamily: 'Inter_600SemiBold',
  },
  stepWhy: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: 3,
  },
  stepLabelDone: {
    color: Colors.textMuted,
    textDecorationLine: 'line-through',
  },
  doneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.xs,
  },
  doneText: {
    ...Typography.body,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
  },
});
