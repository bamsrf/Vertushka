/**
 * SwipeTab — вертикальный gradient-«язычок» на правом краю карточки вишлиста.
 *
 * Дефолтная ширина 4dp, в pulse-режиме плавно расширяется до 14dp с
 * двумя стрелками влево (сверху и снизу) и вертикальным текстом «СРАВНИТЬ».
 * Стрелки изолированы в SVG-слое — НЕ зависят от writing-mode, направление
 * гарантировано (фикс из chat1.md iteration 3).
 *
 * Используется внутри WishlistRowWithOffers. Pulse играет один раз при
 * первом mount вишлиста (управляется через `useMarketStore.hasSeenSwipeHint`).
 *
 * Источник: screens-drawer-a.jsx (SwipeTab атом) + chat1.md итерации 2/3
 * по стрелкам + docs/plans/market/MARKET_AND_PRICE_DRAWER.md §2.1.
 */
import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { LinearGradient } from 'expo-linear-gradient';

import { Icon } from '../ui/Icon';
import { Gradients } from '../../constants/theme';

interface SwipeTabProps {
  /** Если true — играет 1 pulse (расширение до 14dp, glow, появление текста). */
  pulse?: boolean;
  /** Дефолтная ширина в покое (без pulse). */
  baseWidth?: number;
  /** Ширина в pulse-режиме. */
  pulseWidth?: number;
}

const PULSE_DURATION = 320;

export function SwipeTab({
  pulse = false,
  baseWidth = 4,
  pulseWidth = 14,
}: SwipeTabProps) {
  const widthSV = useSharedValue<number>(pulse ? pulseWidth : baseWidth);
  const glowSV = useSharedValue<number>(pulse ? 1 : 0);

  useEffect(() => {
    widthSV.value = withTiming(pulse ? pulseWidth : baseWidth, {
      duration: PULSE_DURATION,
      easing: Easing.out(Easing.cubic),
    });
    glowSV.value = withTiming(pulse ? 1 : 0, {
      duration: PULSE_DURATION,
    });
  }, [pulse, pulseWidth, baseWidth, widthSV, glowSV]);

  const containerStyle = useAnimatedStyle(() => ({
    width: widthSV.value,
    shadowOpacity: 0.50 * glowSV.value,
    shadowRadius: 18 * glowSV.value,
  }));

  // Текст «СРАВНИТЬ» виден только в pulse-режиме.
  const contentStyle = useAnimatedStyle(() => ({
    opacity: glowSV.value,
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[styles.container, containerStyle]}
    >
      <LinearGradient
        colors={Gradients.hotStock}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={styles.gradient}
      >
        {/* Pulse-режим: 2 стрелки влево + вертикальный текст */}
        <Animated.View style={[styles.pulseContent, contentStyle]}>
          <Icon name="arrow-left" size={10} color="onBrand" />
          <Text style={styles.verticalLabel}>
            {'С\nР\nА\nВ\nН\nИ\nТ\nЬ'}
          </Text>
          <Icon name="arrow-left" size={10} color="onBrand" />
        </Animated.View>
      </LinearGradient>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 12,
    right: 0,
    bottom: 12,
    borderTopLeftRadius: 4,
    borderBottomLeftRadius: 4,
    overflow: 'hidden',
    // Glow — управляется через shadowRadius / shadowOpacity в Animated
    shadowColor: '#E85A2A',
    shadowOffset: { width: -2, height: 0 },
  },
  gradient: {
    flex: 1,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 6,
    paddingBottom: 4,
  },
  pulseContent: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 4,
    paddingBottom: 4,
  },
  verticalLabel: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: 9,
    fontWeight: '800',
    color: '#FFFFFF',
    letterSpacing: 1.4,
    textAlign: 'center',
    includeFontPadding: false,
    // Вертикальное расположение через \n в JSX-строке выше — гарантирует что
    // «С Р А В Н И Т Ь» сверху-вниз, а не повёрнутый текст через rotation.
    lineHeight: 11,
  },
});

export default SwipeTab;
