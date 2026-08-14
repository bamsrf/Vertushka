/**
 * CoachTip — базовая форма контекстной подсказки: карточка в потоке экрана.
 *
 * Никакого dim-оверлея и никакой привязки к координатам подсвечиваемого
 * элемента. Карточка ставится рядом с тем, что объясняет, средствами обычной
 * вёрстки — поэтому не может «промахнуться» и не ломается от анимаций.
 *
 * Раскладка в три яруса, каждый на всю ширину карточки:
 *   1. иконка + заголовок + крестик;
 *   2. текст;
 *   3. маршрут до фичи и кнопка действия.
 *
 * Текст НЕ уводится в колонку под заголовок. Раньше он жил справа от иконки,
 * и левый край абзаца стоял на 46 px правее левого края карточки — при
 * переносе строк это читалось как случайный отступ, а не как выравнивание.
 */
import { useEffect, useRef } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';
import { Icon } from '@/components/ui';
import type { CoachMarkMeta } from '../../lib/coachMarks';
import { analytics } from '../../lib/analytics';
import { BorderRadius, Colors, Spacing, Typography } from '../../constants/theme';

interface CoachTipProps {
  meta: CoachMarkMeta;
  onDismiss: () => void;
  /** Необязательное действие: «Открыть Радар», «Создать папку» и т.п. */
  action?: { label: string; onPress: () => void };
}

export function CoachTip({ meta, onDismiss, action }: CoachTipProps) {
  const appear = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(appear, {
      toValue: 1,
      duration: 260,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [appear]);

  const style = {
    opacity: appear,
    transform: [
      { translateY: appear.interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) },
    ],
  };

  return (
    <Animated.View style={[styles.card, style]}>
      <View style={styles.header}>
        <View style={styles.iconWrap}>
          <Icon name={meta.icon} size={18} color={Colors.royalBlue} />
        </View>
        <Text style={styles.title}>{meta.title}</Text>
        <Pressable
          onPress={onDismiss}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Понятно"
        >
          <Icon name="close" size={16} color={Colors.textMuted} />
        </Pressable>
      </View>

      <Text style={styles.body}>{meta.body}</Text>

      {/* Маршрут до фичи — плашкой, а не строкой в абзаце: юзер возвращается
          к подсказке именно за «а где это», и ответ должен выделяться из
          текста, не читаясь при этом как кнопка. */}
      <View style={styles.footer}>
        <View style={styles.whereChip}>
          <Icon name="location-outline" size={11} color={Colors.royalBlue} />
          <Text style={styles.whereText} numberOfLines={2}>{meta.where}</Text>
        </View>

        {action && (
          <Pressable
            style={styles.action}
            onPress={() => {
              // Подсказка одноразовая: переход по действию — тоже её закрытие.
              analytics.onboardingHintAction(meta.key);
              onDismiss();
              action.onPress();
            }}
            accessibilityRole="button"
          >
            <Text style={styles.actionText}>{action.label}</Text>
            <Icon name="chevron-forward" size={13} color={Colors.background} />
          </Pressable>
        )}
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.md,
    padding: Spacing.md,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.royalBlue + '33',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.royalBlue + '14',
  },
  title: {
    ...Typography.body,
    flex: 1,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
  },
  body: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
  },
  footer: {
    flexDirection: 'row',
    // По нижнему краю: плашка маршрута может занять две строки, кнопка при
    // этом остаётся на одной линии с её последней строкой, а не уезжает вверх.
    alignItems: 'flex-end',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  whereChip: {
    flexShrink: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.royalBlue + '0F',
  },
  whereText: {
    ...Typography.caption,
    flexShrink: 1,
    fontSize: 12,
    lineHeight: 15,
    color: Colors.royalBlue,
  },
  action: {
    // Прижата к правому нижнему углу и залита: раньше это была голубая строчка
    // текста под абзацем — на фоне такого же голубого маршрута она не читалась
    // как то, на что нужно нажать.
    marginLeft: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.royalBlue,
  },
  actionText: {
    ...Typography.caption,
    fontFamily: 'Inter_600SemiBold',
    fontSize: 13,
    color: Colors.background,
  },
});
