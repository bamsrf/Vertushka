/**
 * OfferBadge — corner-плашка для wishlist tile/list режима.
 *
 * Два состояния:
 *   - inStock — «В ПРОДАЖЕ», market-градиент cobalt → azure → peach, белый
 *               текст и dot, glow вокруг точки. Когда есть exact-match оффер.
 *   - alt     — «ЕСТЬ АНАЛОГ», navy → cobalt подложка (#0B1438 → #11225C),
 *               cobalt-soft текст #7B8FE8, кобальтовый dot с glow. Когда
 *               exact-match нет, но есть другой пресс/издание того же релиза.
 *
 * Геометрия (из handoff/screens-wishlist-grid-v3.jsx):
 *   - padding 4×8 dp (md) / 3×7 dp (sm)
 *   - radius 9 (md) / 8 (sm)
 *   - type: 9.5px / 800 / uppercase / ls 0.8
 *   - shadow: 0 2 8 alpha 0.30
 *
 * Frame-вспомогалка `TileFrameGradient` оборачивает обложку в gradient-рамку
 * с 2dp padding'ом (= толщина рамки). Цвет рамки — по kind, как на спек-листе:
 *   inStock → navy → cobalt → ember
 *   alt     → cobaltSoft → violet
 */
import React from 'react';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { androidShadow } from '@/constants/theme';

export type OfferBadgeKind = 'inStock' | 'alt';
export type OfferBadgeSize = 'sm' | 'md';

interface OfferBadgeProps {
  kind: OfferBadgeKind;
  size?: OfferBadgeSize;
  style?: StyleProp<ViewStyle>;
}

const SIZES: Record<OfferBadgeSize, {
  fs: number; padV: number; padH: number; gap: number; dot: number; ls: number; radius: number;
}> = {
  sm: { fs: 8.5, padV: 3, padH: 7,  gap: 4, dot: 5, ls: 0.7, radius: 8 },
  md: { fs: 9.5, padV: 4, padH: 8,  gap: 5, dot: 6, ls: 0.8, radius: 9 },
};

export function OfferBadge({ kind, size = 'md', style }: OfferBadgeProps) {
  const sz = SIZES[size];

  if (kind === 'inStock') {
    return (
      <LinearGradient
        colors={['#2D4FDB', '#5780F0', '#F4A06A']}
        locations={[0, 0.45, 1]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[
          styles.pill,
          {
            paddingVertical: sz.padV,
            paddingHorizontal: sz.padH,
            borderRadius: sz.radius,
            gap: sz.gap,
            shadowColor: '#2D4FDB',
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.3,
            shadowRadius: 8,
            elevation: 4,
          },
          style,
        ]}
      >
        <View
          style={{
            width: sz.dot,
            height: sz.dot,
            borderRadius: sz.dot / 2,
            backgroundColor: '#FFFFFF',
            shadowColor: '#FFFFFF',
            shadowOffset: { width: 0, height: 0 },
            shadowOpacity: 0.6,
            shadowRadius: 4,
            ...androidShadow({ color: '#FFFFFF', opacity: 0.6, radius: 4 }),
          }}
        />
        <Text style={[styles.label, { fontSize: sz.fs, letterSpacing: sz.ls, color: '#FFFFFF' }]}>
          {'В ПРОДАЖЕ'}
        </Text>
      </LinearGradient>
    );
  }

  // kind === 'alt'
  return (
    <LinearGradient
      colors={['#0B1438', '#11225C']}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[
        styles.pill,
        {
          paddingVertical: sz.padV,
          paddingHorizontal: sz.padH,
          borderRadius: sz.radius,
          gap: sz.gap,
          borderWidth: 0.5,
          borderColor: 'rgba(92, 122, 232, 0.35)',
          shadowColor: '#0B1438',
          shadowOffset: { width: 0, height: 2 },
          shadowOpacity: 0.45,
          shadowRadius: 8,
          elevation: 4,
        },
        style,
      ]}
    >
      <View
        style={{
          width: sz.dot,
          height: sz.dot,
          borderRadius: sz.dot / 2,
          overflow: 'hidden',
          shadowColor: '#5C7AE8',
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: 0.7,
          shadowRadius: 5,
          ...androidShadow({ color: '#5C7AE8', opacity: 0.7, radius: 5 }),
        }}
      >
        <LinearGradient
          colors={['#5C7AE8', '#2A4BD7']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={{ flex: 1 }}
        />
      </View>
      <Text style={[styles.label, { fontSize: sz.fs, letterSpacing: sz.ls, color: '#7B8FE8' }]}>
        {'ЕСТЬ АНАЛОГ'}
      </Text>
    </LinearGradient>
  );
}

// ── Tile frame ───────────────────────────────────────────────────────────
// Gradient-обводка вокруг обложки в tile-режиме. Передаёт сигнал «есть оффер»
// цветом рамки; плашка-OfferBadge даёт буквальную надпись.

interface TileFrameProps {
  kind: OfferBadgeKind;
  radius?: number; // внешний радиус обёртки. default 14 — на 2dp больше cover-radius
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

const FRAME_COLORS: Record<OfferBadgeKind, readonly [string, string, string]> = {
  inStock: ['#0E1A52', '#2A4BD7', '#E85A2A'] as const, // navy → cobalt → ember
  alt:     ['#5C7AE8', '#7B5BE6', '#7B5BE6'] as const, // cobaltSoft → violet (≡ дубль для 3-stop API)
};

// Glow вокруг рамки — мягкий tint в цвет акцента, без направленного offset.
const FRAME_GLOW: Record<OfferBadgeKind, { color: string; opacity: number; radius: number }> = {
  inStock: { color: '#E85A2A', opacity: 0.22, radius: 14 },
  alt:     { color: '#7B5BE6', opacity: 0.18, radius: 12 },
};

export function TileFrameGradient({ kind, radius = 14, children, style }: TileFrameProps) {
  const glow = FRAME_GLOW[kind];
  return (
    <LinearGradient
      colors={FRAME_COLORS[kind]}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={[
        {
          padding: 2,
          borderRadius: radius,
          shadowColor: glow.color,
          shadowOffset: { width: 0, height: 0 },
          shadowOpacity: glow.opacity,
          shadowRadius: glow.radius,
          elevation: 3,
        },
        style,
      ]}
    >
      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
  },
  label: {
    fontFamily: 'Inter_800ExtraBold',
    fontWeight: '800',
    textTransform: 'uppercase',
    includeFontPadding: false,
  },
});

export default OfferBadge;
