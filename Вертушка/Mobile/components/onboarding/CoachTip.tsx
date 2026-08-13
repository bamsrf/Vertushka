/**
 * CoachTip — базовая форма контекстной подсказки: карточка в потоке экрана.
 *
 * Никакого dim-оверлея и никакой привязки к координатам подсвечиваемого
 * элемента. Карточка ставится рядом с тем, что объясняет, средствами обычной
 * вёрстки — поэтому не может «промахнуться» и не ломается от анимаций.
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
      <View style={styles.row}>
        <View style={styles.iconWrap}>
          <Icon name={meta.icon} size={20} color={Colors.royalBlue} />
        </View>
        <View style={styles.text}>
          <Text style={styles.title}>{meta.title}</Text>
          <Text style={styles.body}>{meta.body}</Text>
        </View>
        <Pressable
          onPress={onDismiss}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Понятно"
        >
          <Icon name="close" size={16} color={Colors.textMuted} />
        </Pressable>
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
          <Icon name="chevron-forward" size={14} color={Colors.royalBlue} />
        </Pressable>
      )}
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
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm + 2,
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.royalBlue + '14',
  },
  text: {
    flex: 1,
  },
  title: {
    ...Typography.body,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.text,
    marginBottom: 2,
  },
  body: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    alignSelf: 'flex-start',
    marginTop: Spacing.sm,
    marginLeft: 36 + Spacing.sm + 2,
  },
  actionText: {
    ...Typography.caption,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.royalBlue,
  },
});
