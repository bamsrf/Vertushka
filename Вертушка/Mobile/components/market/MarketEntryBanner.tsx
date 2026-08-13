/**
 * MarketEntryBanner — вход в Маркет из профиля.
 *
 * Тёмный market-градиент с медленным переливом цветов: три слоя
 * LinearGradient из MarketPalette лежат стопкой, верхние два кросс-фейдятся
 * по общему phase-драйверу (0 → 2 → 0). Анимировать сами `colors` у
 * LinearGradient нельзя — expo-linear-gradient пересобирает нативный слой на
 * каждый кадр, поэтому перелив делается через opacity, которая живёт на
 * UI-потоке.
 *
 * ВАЖНО: анимация стартует на focus и отменяется на blur (useFocusEffect).
 * Иначе она крутится в фоне на каждом экране приложения и греет телефон.
 */
import { useCallback } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import Reanimated, {
  Easing,
  cancelAnimation,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';
import { useFocusEffect } from 'expo-router';

import { Icon } from '../ui/Icon';
import { MarketPalette, Spacing, Typography } from '../../constants/theme';

const AnimatedGradient = Reanimated.createAnimatedComponent(LinearGradient);

// Полный цикл перелива. Медленно намеренно: баннер должен «дышать», а не
// мигать — быстрый цикл читается как ошибка рендера.
const CYCLE_MS = 6000;

interface MarketEntryBannerProps {
  onPress: () => void;
}

export function MarketEntryBanner({ onPress }: MarketEntryBannerProps) {
  const phase = useSharedValue(0);

  useFocusEffect(
    useCallback(() => {
      phase.value = withRepeat(
        withTiming(2, { duration: CYCLE_MS, easing: Easing.inOut(Easing.sin) }),
        -1,
        true
      );
      return () => {
        // Экран ушёл из фокуса — глушим таймер и возвращаем базовый кадр.
        cancelAnimation(phase);
        phase.value = 0;
      };
    }, [phase])
  );

  const midStyle = useAnimatedStyle(() => ({
    opacity: interpolate(phase.value, [0, 1, 2], [0, 1, 0]),
  }));

  const lateStyle = useAnimatedStyle(() => ({
    opacity: interpolate(phase.value, [0, 1, 2], [0, 0, 1]),
  }));

  return (
    <TouchableOpacity
      activeOpacity={0.85}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="Перейти в Маркет"
      style={styles.banner}
    >
      {/* Базовый слой — виден всегда, чтобы под кросс-фейдом никогда не
          просвечивал белый фон профиля. */}
      <LinearGradient
        colors={[MarketPalette.void, MarketPalette.indigo, MarketPalette.violet]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <AnimatedGradient
        colors={[MarketPalette.plum, MarketPalette.magenta, MarketPalette.cobalt]}
        start={{ x: 0, y: 1 }}
        end={{ x: 1, y: 0 }}
        style={[StyleSheet.absoluteFill, midStyle]}
        pointerEvents="none"
      />
      <AnimatedGradient
        colors={[MarketPalette.darkVoid, MarketPalette.cobalt, MarketPalette.peach]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[StyleSheet.absoluteFill, lateStyle]}
        pointerEvents="none"
      />

      <View style={styles.content}>
        <View style={styles.iconWrap}>
          <Icon name="disc" size={24} color="accent" weight="duotone" />
        </View>
        <View style={styles.text}>
          <Text style={styles.title}>Маркет</Text>
          <Text style={styles.subtitle}>
            Пластинки из магазинов — цены, наличие, доставка
          </Text>
        </View>
        <Icon name="chevron-forward" size={18} color={MarketPalette.chrome.textDim} />
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  banner: {
    // Блок широкий и тёмный — на светлом профиле обычные углы читаются
    // острыми даже на большом радиусе. Спасает не столько радиус, сколько
    // borderCurve: 'continuous' — это apple'овский squircle, у которого нет
    // резкого стыка дуги с прямой стороной (iOS 13+/RN 0.71+; на Android
    // проп игнорируется, остаётся просто крупный радиус).
    borderRadius: 30,
    borderCurve: 'continuous',
    marginBottom: Spacing.xl,
    borderWidth: 1,
    borderColor: MarketPalette.chrome.borderSoft,
    // overflow:hidden — иначе absoluteFill-градиенты вылезут за скругления.
    overflow: 'hidden',
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.lg,
    paddingHorizontal: Spacing.lg,
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: MarketPalette.chrome.fill,
    borderWidth: 1,
    borderColor: MarketPalette.chrome.borderSoft,
  },
  text: {
    flex: 1,
  },
  title: {
    ...Typography.h3,
    color: MarketPalette.chrome.textPrimary,
    marginBottom: 2,
  },
  subtitle: {
    ...Typography.caption,
    color: MarketPalette.chrome.textSecondary,
  },
});
