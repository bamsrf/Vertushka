/**
 * Telegram-style контекст-меню для сообщения.
 *
 * Открывается по long-press на бабле и «вырастает» из места самого сообщения:
 * экран треда передаёт anchor (measureInWindow бабла), меню кладёт снапшот
 * в ту же точку, реакции пружинят над ним, действия — под ним. Если места
 * не хватает — колонка мягко сдвигается в пределы экрана. Без anchor
 * (fallback) — прежняя центрированная раскладка.
 *
 * Модалка с blur-backdrop, spring-in анимацией. Тап вне зоны меню — закрывает.
 */
import React, { useEffect } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  TouchableWithoutFeedback,
  StyleSheet,
  Pressable,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import { BlurView } from 'expo-blur';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { Colors, Spacing, BorderRadius } from '../../constants/theme';

export type MenuAction = {
  key: string;
  label: string;
  icon: string;
  destructive?: boolean;
  onPress: () => void;
};

export type MenuAnchor = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export const QUICK_REACTIONS = ['❤️', '🔥', '😂', '😮', '😢', '👍'] as const;

const REACTIONS_H = 52;
const ACTION_ROW_H = 48;
const ACTIONS_MAX_H = 300;
const GAP = 8;

interface Props {
  visible: boolean;
  isMine: boolean;
  anchor?: MenuAnchor | null;
  bubbleSnapshot: React.ReactNode;
  actions: MenuAction[];
  onClose: () => void;
  onReact?: (emoji: string) => void;
}

export function MessageContextMenu({
  visible,
  isMine,
  anchor,
  bubbleSnapshot,
  actions,
  onClose,
  onReact,
}: Props) {
  const { height: screenH } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const scale = useSharedValue(0.96);
  const opacity = useSharedValue(0);
  const reactionsPop = useSharedValue(0);

  // Почти критическое затухание: живо, но без «желе». Scale стартует близко
  // к 1 — масштаб с малых значений растрирует emoji (пикселизация).
  const CALM = { damping: 24, stiffness: 300, overshootClamping: true };

  useEffect(() => {
    if (visible) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
      scale.value = 0.96;
      opacity.value = 0;
      reactionsPop.value = 0;
      scale.value = withSpring(1, CALM);
      opacity.value = withTiming(1, { duration: 140 });
      reactionsPop.value = withDelay(50, withSpring(1, CALM));
    } else {
      scale.value = 0.96;
      opacity.value = 0;
      reactionsPop.value = 0;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, scale, opacity, reactionsPop]);

  const cardStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
    opacity: opacity.value,
  }));

  const reactionsStyle = useAnimatedStyle(() => ({
    opacity: reactionsPop.value,
    transform: [
      { scale: 0.92 + reactionsPop.value * 0.08 },
      { translateY: (1 - reactionsPop.value) * 6 },
    ],
  }));

  // Раскладка от якоря: снапшот стремится остаться на месте бабла,
  // колонка целиком зажимается в видимую область.
  let anchoredTop: number | null = null;
  if (anchor) {
    const actionsH = Math.min(actions.length * ACTION_ROW_H, ACTIONS_MAX_H);
    const estHeight = REACTIONS_H + GAP + anchor.height + GAP + actionsH;
    const idealTop = anchor.y - REACTIONS_H - GAP;
    const minTop = insets.top + 12;
    const maxTop = screenH - insets.bottom - 16 - estHeight;
    anchoredTop = Math.max(minTop, Math.min(idealTop, Math.max(minTop, maxTop)));
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <TouchableWithoutFeedback onPress={onClose}>
        <View
          style={[
            styles.backdrop,
            anchoredTop === null && styles.backdropCentered,
          ]}
        >
          <BlurView intensity={20} tint="dark" style={StyleSheet.absoluteFill} />
          <TouchableWithoutFeedback>
            <Animated.View
              style={[
                styles.card,
                isMine ? styles.cardMine : styles.cardOther,
                anchoredTop !== null && {
                  position: 'absolute',
                  top: anchoredTop,
                  left: Spacing.lg,
                  right: Spacing.lg,
                },
                cardStyle,
              ]}
            >
              <Animated.View style={[styles.reactionsRow, reactionsStyle]}>
                {QUICK_REACTIONS.map((emoji) => (
                  <Pressable
                    key={emoji}
                    style={({ pressed }) => [
                      styles.reactionBtn,
                      pressed && styles.reactionBtnPressed,
                    ]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
                      onReact?.(emoji);
                      onClose();
                    }}
                  >
                    <Text style={styles.reactionEmoji}>{emoji}</Text>
                  </Pressable>
                ))}
              </Animated.View>

              <View
                style={[
                  styles.bubbleSnapWrap,
                  isMine ? styles.bubbleSnapWrapMine : styles.bubbleSnapWrapOther,
                ]}
                pointerEvents="none"
              >
                {bubbleSnapshot}
              </View>

              <View
                style={[
                  styles.actions,
                  isMine ? styles.actionsMine : styles.actionsOther,
                ]}
              >
                <ScrollView
                  style={{ maxHeight: ACTIONS_MAX_H }}
                  bounces={false}
                  showsVerticalScrollIndicator={false}
                >
                  {actions.map((a, i) => (
                    <TouchableOpacity
                      key={a.key}
                      activeOpacity={0.6}
                      style={[
                        styles.actionRow,
                        i < actions.length - 1 && styles.actionRowDivider,
                      ]}
                      onPress={() => {
                        a.onPress();
                        onClose();
                      }}
                    >
                      <Text
                        style={[
                          styles.actionLabel,
                          a.destructive && styles.actionLabelDestructive,
                        ]}
                      >
                        {a.label}
                      </Text>
                      <Icon
                        name={a.icon}
                        size={18}
                        color={a.destructive ? '#E5484D' : Colors.text}
                      />
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            </Animated.View>
          </TouchableWithoutFeedback>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
  },
  backdropCentered: {
    justifyContent: 'center',
    paddingHorizontal: Spacing.lg,
  },
  card: {
    gap: GAP,
  },
  cardMine: { alignItems: 'flex-end' },
  cardOther: { alignItems: 'flex-start' },

  /* Reactions row */
  reactionsRow: {
    flexDirection: 'row',
    backgroundColor: Colors.background,
    borderRadius: 28,
    paddingHorizontal: 6,
    paddingVertical: 6,
    gap: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 8,
  },
  reactionBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reactionBtnPressed: {
    backgroundColor: Colors.surface,
    transform: [{ scale: 1.15 }],
  },
  reactionEmoji: { fontSize: 22 },

  /* Snapshot of the bubble (read-only) */
  bubbleSnapWrap: {
    maxWidth: '90%',
  },
  bubbleSnapWrapMine: { alignSelf: 'flex-end' },
  bubbleSnapWrapOther: { alignSelf: 'flex-start' },

  /* Actions menu */
  actions: {
    minWidth: 220,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 8,
  },
  actionsMine: { alignSelf: 'flex-end' },
  actionsOther: { alignSelf: 'flex-start' },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 13,
    minHeight: ACTION_ROW_H,
  },
  actionRowDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.divider,
  },
  actionLabel: { fontSize: 15, color: Colors.text, fontWeight: '500' },
  actionLabelDestructive: { color: '#E5484D' },
});
