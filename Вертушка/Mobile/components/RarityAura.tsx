/**
 * Rarity highlighting for vinyl records — three tiers as card-as-signal.
 * Design source: rarity_design / Rare Records.html (tier-system.jsx).
 *
 * Tiers:
 *   first_press → heritage gold, shimmer ring 8s + diagonal cover blink every 10s
 *   limited     → cold platinum violet, pulse 4s
 *   hot         → hot ember, pulse 2s + heat-haze halo on cover
 *
 * No icon markers — pure color and animation.
 */
import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

export type RarityTier = 'first_press' | 'limited' | 'hot';
export type RarityContext =
  | 'collection'
  | 'wishlist'
  | 'search'
  | 'profile'
  | 'detail';

export interface RarityFlags {
  is_first_press?: boolean | null;
  is_limited?: boolean | null;
  is_hot?: boolean | null;
}

interface TierTokens {
  id: RarityTier;
  label: string;
  longLabel: string;
  palette: [string, string, string];
  auraOuter: string;
  auraInner: string;
  edge: [string, string, string];
  iconColor: string;
  iconGlow: string;
  textColor: string;
  mood: string;
}

export const RARITY_TIERS: Record<RarityTier, TierTokens> = {
  first_press: {
    id: 'first_press',
    label: '1-й пресс',
    longLabel: 'Канонический первый пресс мастер-релиза',
    palette: ['#F4D27A', '#B8860B', '#6B4423'],
    auraOuter: 'rgba(184, 134, 11, 0.55)',
    auraInner: 'rgba(244, 210, 122, 0.85)',
    edge: ['#F4D27A', '#B8860B', '#6B4423'],
    iconColor: '#D9A441',
    iconGlow: 'rgba(244, 210, 122, 0.9)',
    textColor: '#8A6314',
    mood: 'shimmer · 8s',
  },
  limited: {
    id: 'limited',
    label: 'Лимитка',
    longLabel: 'Специальное издание',
    palette: ['#C0C0D8', '#6B4DCE', '#2A1F4E'],
    auraOuter: 'rgba(107, 77, 206, 0.55)',
    auraInner: 'rgba(192, 192, 216, 0.85)',
    edge: ['#C0C0D8', '#6B4DCE', '#2A1F4E'],
    iconColor: '#7A5FE0',
    iconGlow: 'rgba(140, 110, 230, 0.9)',
    textColor: '#5A40B2',
    mood: 'pulse · 4s',
  },
  hot: {
    id: 'hot',
    label: 'Популярно',
    longLabel: 'Высокий спрос на Discogs',
    palette: ['#FFB347', '#FF5E3A', '#B22222'],
    auraOuter: 'rgba(255, 94, 58, 0.62)',
    auraInner: 'rgba(255, 179, 71, 0.95)',
    edge: ['#FFB347', '#FF5E3A', '#B22222'],
    iconColor: '#FF6B3D',
    iconGlow: 'rgba(255, 94, 58, 0.95)',
    textColor: '#C73A1B',
    mood: 'pulse · 2s',
  },
};

/**
 * Pick the single most important tier for a card given context.
 * `collection` hides `hot` (cult/demand is irrelevant when you already own it).
 * Priority: first_press → limited → hot.
 */
export function pickRarityTier(
  flags: RarityFlags | null | undefined,
  context: RarityContext = 'search',
): RarityTier | null {
  if (!flags) return null;
  if (flags.is_first_press) return 'first_press';
  if (flags.is_limited) return 'limited';
  if (flags.is_hot && context !== 'collection') return 'hot';
  return null;
}

/** Return all applicable tiers (used on the detail screen, no context filtering). */
export function allRarityTiers(flags: RarityFlags | null | undefined): RarityTier[] {
  if (!flags) return [];
  const tiers: RarityTier[] = [];
  if (flags.is_first_press) tiers.push('first_press');
  if (flags.is_limited) tiers.push('limited');
  if (flags.is_hot) tiers.push('hot');
  return tiers;
}

// ─── Aura primitives ─────────────────────────────────────────

interface AuraProps {
  tier: RarityTier;
  radius?: number;
}

/**
 * First-press shimmer: a slowly counter-rotating golden gradient ring around the card.
 * Implemented by clipping a rotating LinearGradient inside an outer container, while
 * the actual card content (opaque, white) sits on top and masks the inside, leaving
 * only the rim visible.
 */
function ShimmerAura({ tier, radius = 16 }: AuraProps) {
  const tokens = RARITY_TIERS[tier];
  const rotation = useSharedValue(0);

  useEffect(() => {
    rotation.value = withRepeat(
      withTiming(-360, { duration: 8000, easing: Easing.linear }),
      -1,
      false,
    );
  }, [rotation]);

  const rotateStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  return (
    <>
      {/* Внешний цветной shadow для глубокого свечения вокруг карточки */}
      <View
        pointerEvents="none"
        style={[
          styles.auraRingOuter,
          {
            borderRadius: radius + 3,
            shadowColor: tokens.palette[1],
            shadowOpacity: 0.95,
            shadowRadius: 28,
            shadowOffset: { width: 0, height: 0 },
            elevation: 14,
          },
        ]}
      />
      {/* Кольцо с вращающимся золотым шиммером */}
      <View
        pointerEvents="none"
        style={[
          styles.auraRing,
          {
            borderRadius: radius + 6,
            shadowColor: tokens.palette[0],
            shadowOpacity: 0.85,
            shadowRadius: 12,
            shadowOffset: { width: 0, height: 4 },
            elevation: 10,
          },
        ]}
      >
        <View
          style={[StyleSheet.absoluteFill, styles.auraClip, { borderRadius: radius + 6 }]}
          pointerEvents="none"
        >
          <Animated.View style={[styles.auraRotator, rotateStyle]} pointerEvents="none">
            <LinearGradient
              colors={[
                tokens.palette[0],
                tokens.palette[1],
                tokens.palette[0],
                tokens.palette[1] + 'cc',
                tokens.palette[0],
                tokens.palette[1],
                tokens.palette[0] + 'cc',
                tokens.palette[1],
              ] as readonly [string, string, ...string[]]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
          </Animated.View>
        </View>
      </View>
    </>
  );
}

/**
 * Pulse aura: a static-colored glow whose opacity oscillates.
 * 4s for `limited` (subtle breath), 2s for `hot` (active, intense).
 */
function PulseAura({ tier, radius = 16 }: AuraProps) {
  const tokens = RARITY_TIERS[tier];
  const isHot = tier === 'hot';
  const min = isHot ? 0.4 : 0.5;
  const max = isHot ? 1.0 : 0.9;
  const half = (isHot ? 2000 : 4000) / 2;

  const opacity = useSharedValue(min);

  useEffect(() => {
    opacity.value = withRepeat(
      withSequence(
        withTiming(max, { duration: half, easing: Easing.inOut(Easing.ease) }),
        withTiming(min, { duration: half, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [opacity, min, max, half]);

  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <>
      {/* Глубокий цветной halo */}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.auraPulseDeep,
          {
            borderRadius: radius + 4,
            shadowColor: tokens.palette[1],
            shadowOpacity: 0.95,
            shadowRadius: isHot ? 32 : 26,
            shadowOffset: { width: 0, height: 0 },
            elevation: 14,
          },
          animStyle,
        ]}
      />
      {/* Близкий border-glow */}
      <Animated.View
        pointerEvents="none"
        style={[
          styles.auraPulse,
          {
            borderRadius: radius,
            shadowColor: tokens.palette[1],
            shadowOpacity: 0.85,
            shadowRadius: 14,
            shadowOffset: { width: 0, height: 0 },
            elevation: 10,
            borderWidth: 2,
            borderColor: tokens.palette[1] + 'aa',
          },
          animStyle,
        ]}
      />
    </>
  );
}

// ─── Cover-internal effects ───────────────────────────────────

interface CoverEffectProps {
  tier: RarityTier;
  /** Cover radius in pixels (matches the cover's own borderRadius). */
  radius?: number;
}

/**
 * First-press only: a soft warm light blink that sweeps diagonally across
 * the cover roughly once every 10 seconds.
 */
function CoverBlink({ radius = 0 }: { radius?: number }) {
  const t = useSharedValue(0);

  useEffect(() => {
    t.value = withRepeat(
      withSequence(
        withTiming(0, { duration: 0 }),
        withTiming(1, { duration: 10000, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [t]);

  const animStyle = useAnimatedStyle(() => {
    // 0 → 0.85 invisible; 0.85 → 1.0 sweeps from -120% to 220%
    const v = t.value;
    const swept = v < 0.85 ? -1.2 : -1.2 + ((v - 0.85) / 0.15) * 3.4;
    const opacity = v < 0.85 || v > 0.99 ? 0 : 1;
    return {
      opacity,
      transform: [{ translateX: swept * 100 }, { skewX: '-18deg' }],
    };
  });

  return (
    <View
      pointerEvents="none"
      style={[
        styles.coverEffectClip,
        { borderRadius: radius },
      ]}
    >
      <Animated.View style={[styles.coverBlink, animStyle]} pointerEvents="none">
        <LinearGradient
          colors={[
            'rgba(255,247,180,0)',
            'rgba(255,242,160,0.95)',
            'rgba(255,247,180,0)',
          ] as const}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={StyleSheet.absoluteFill}
        />
      </Animated.View>
    </View>
  );
}

/**
 * Hot only: a soft red halo at the inner edges of the cover, breathing on a
 * 2-second cycle. Approximates CSS inset shadow with overlaid edge gradients.
 */
function HeatHaze({ radius = 0 }: { radius?: number }) {
  // RN не поддерживает inset box-shadow и mixBlendMode: 'screen' — компенсируем
  // более насыщенными альфами, чтобы эффект не терялся на светлом фоне.
  const opacity = useSharedValue(0.6);

  useEffect(() => {
    opacity.value = withRepeat(
      withSequence(
        withTiming(0.95, { duration: 1000, easing: Easing.inOut(Easing.ease) }),
        withTiming(0.6, { duration: 1000, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [opacity]);

  const animStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.coverEffectClip,
        { borderRadius: radius },
        animStyle,
      ]}
    >
      {/* Inset-glow approximation: солидный цветной бордер + 4 направленные засветки от краёв внутрь. */}
      <View
        style={[
          StyleSheet.absoluteFill,
          {
            borderRadius: radius,
            borderWidth: 4,
            borderColor: 'rgba(255, 80, 40, 0.85)',
          },
        ]}
      />
      <LinearGradient
        colors={['rgba(255, 94, 58, 0.85)', 'transparent'] as const}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 0.45 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['transparent', 'rgba(178, 34, 34, 0.85)'] as const}
        start={{ x: 0.5, y: 0.55 }}
        end={{ x: 0.5, y: 1 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['rgba(255, 94, 58, 0.7)', 'transparent'] as const}
        start={{ x: 0, y: 0.5 }}
        end={{ x: 0.4, y: 0.5 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['transparent', 'rgba(255, 94, 58, 0.7)'] as const}
        start={{ x: 0.6, y: 0.5 }}
        end={{ x: 1, y: 0.5 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
    </Animated.View>
  );
}

// ─── Public components ───────────────────────────────────────

interface RarityAuraProps {
  tier: RarityTier | null;
  radius?: number;
  /** When true, also paints a 3px tier-gradient strip along the left edge (LIST variant). */
  leftEdge?: boolean;
  style?: StyleProp<ViewStyle>;
  children: React.ReactNode;
}

/**
 * Wraps a card with the tier-specific aura. When `tier` is null this is a
 * zero-cost passthrough so non-rare cards pay nothing.
 */
export function RarityAura({
  tier,
  radius = 16,
  leftEdge = false,
  style,
  children,
}: RarityAuraProps) {
  if (!tier) return <View style={style}>{children}</View>;
  const tokens = RARITY_TIERS[tier];

  return (
    <View style={[{ position: 'relative', borderRadius: radius }, style]}>
      {tier === 'first_press' && <ShimmerAura tier={tier} radius={radius} />}
      {(tier === 'limited' || tier === 'hot') && <PulseAura tier={tier} radius={radius} />}
      {children}
      {leftEdge && (
        <View
          pointerEvents="none"
          style={[
            styles.leftEdge,
            { borderTopLeftRadius: radius, borderBottomLeftRadius: radius },
          ]}
        >
          <LinearGradient
            colors={tokens.edge}
            start={{ x: 0.5, y: 0 }}
            end={{ x: 0.5, y: 1 }}
            style={StyleSheet.absoluteFill}
          />
        </View>
      )}
    </View>
  );
}

interface TierCoverEffectsProps {
  tier: RarityTier | null;
  radius?: number;
}

/** Place inside a cover container to add tier-specific in-cover effects. */
export function TierCoverEffects({ tier, radius = 0 }: TierCoverEffectsProps) {
  if (!tier) return null;
  if (tier === 'first_press') return <CoverBlink radius={radius} />;
  if (tier === 'hot') return <HeatHaze radius={radius} />;
  return null;
}

interface TierLabelProps {
  tier: RarityTier;
  size?: number;
  style?: StyleProp<ViewStyle>;
}

/** Color-only inline label for the metadata row. No background, no border. */
export function TierLabel({ tier, size = 11 }: TierLabelProps) {
  const tokens = RARITY_TIERS[tier];
  return (
    <Text
      numberOfLines={1}
      style={{
        fontSize: size,
        fontFamily: 'Inter_700Bold',
        color: tokens.textColor,
        letterSpacing: 0.4,
      }}
    >
      {tokens.label}
    </Text>
  );
}

interface TierFeatureBlockProps {
  tier: RarityTier;
}

/** Feature-card row used in the "Особенности" section on the record detail screen. */
export function TierFeatureBlock({ tier }: TierFeatureBlockProps) {
  const tokens = RARITY_TIERS[tier];
  const radius = 14;

  return (
    <RarityAura tier={tier} radius={radius} leftEdge style={styles.featureWrap}>
      <View style={[styles.featureCard, { borderRadius: radius }]}>
        <View
          style={[
            styles.featureDot,
            {
              backgroundColor: tokens.iconColor,
              shadowColor: tokens.iconColor,
            },
          ]}
        />
        <View style={styles.featureBody}>
          <Text style={[styles.featureTitle, { color: tokens.textColor }]}>
            {tokens.label}
          </Text>
          <Text style={styles.featureSubtitle}>{tokens.longLabel}</Text>
        </View>
      </View>
    </RarityAura>
  );
}

const styles = StyleSheet.create({
  // Aura layers — positioned absolutely behind card content
  auraRingOuter: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  auraRing: {
    position: 'absolute',
    top: -6,
    left: -6,
    right: -6,
    bottom: -6,
  },
  auraClip: {
    overflow: 'hidden',
  },
  auraRotator: {
    position: 'absolute',
    top: '-50%',
    left: '-50%',
    width: '200%',
    height: '200%',
  },
  auraPulse: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  auraPulseDeep: {
    position: 'absolute',
    top: -4,
    left: -4,
    right: -4,
    bottom: -4,
  },

  // Cover-internal effects
  coverEffectClip: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    overflow: 'hidden',
  },
  coverBlink: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    width: '40%',
  },

  // Left edge accent (LIST)
  leftEdge: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
    overflow: 'hidden',
  },

  // Detail page feature block
  featureWrap: {
    marginBottom: 0,
  },
  featureCard: {
    backgroundColor: '#FFFFFF',
    paddingVertical: 14,
    paddingLeft: 22,
    paddingRight: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  featureDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    shadowOpacity: 0.95,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 0 },
    elevation: 4,
  },
  featureBody: {
    flex: 1,
    minWidth: 0,
  },
  featureTitle: {
    fontSize: 14,
    fontFamily: 'Inter_700Bold',
    marginBottom: 2,
  },
  featureSubtitle: {
    fontSize: 12.5,
    fontFamily: 'Inter_400Regular',
    color: '#5A5F8A',
    lineHeight: 17,
  },
});

export type { TierTokens };
