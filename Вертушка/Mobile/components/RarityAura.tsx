/**
 * Rarity highlighting for vinyl records — card-as-signal tiers.
 *
 * Active tiers:
 *   canon       → slate graphite, double border glow 5s (Discogs editorial pick)
 *   collectible → emerald, double layer pulse 6s (price>=$50 + scarce + low have)
 *   limited     → cold platinum violet, pulse 4s
 *   hot         → hot ember, pulse 2s + heat-haze halo on cover
 *
 * Closed tiers (kept in types for backward compat with backend):
 *   first_press — too heuristic without matrix/runout inspection
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

export type RarityTier = 'canon' | 'collectible' | 'limited' | 'hot';
export type RarityContext =
  | 'collection'
  | 'wishlist'
  | 'search'
  | 'profile'
  | 'detail';

export interface RarityFlags {
  is_first_press?: boolean | null;  // closed tier — backend may still send, ignored here
  is_canon?: boolean | null;
  is_collectible?: boolean | null;
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
  collectible: {
    id: 'collectible',
    label: 'Коллекционка',
    longLabel: 'Дорогая (≥$50), почти не продаётся, мало у кого есть',
    palette: ['#3F8E6F', '#1F5C4D', '#0E2E26'],
    auraOuter: 'rgba(31, 92, 77, 0.55)',
    auraInner: 'rgba(63, 142, 111, 0.85)',
    edge: ['#3F8E6F', '#1F5C4D', '#0E2E26'],
    iconColor: '#3F8E6F',
    iconGlow: 'rgba(63, 142, 111, 0.95)',
    textColor: '#1F5C4D',
    mood: 'pulse · 6s',
  },
  canon: {
    id: 'canon',
    label: 'Канон',
    longLabel: 'Каноническое издание мастер-релиза по версии Discogs',
    palette: ['#8B95A8', '#5A6B7D', '#2E3844'],
    auraOuter: 'rgba(90, 107, 125, 0.5)',
    auraInner: 'rgba(139, 149, 168, 0.75)',
    edge: ['#8B95A8', '#5A6B7D', '#2E3844'],
    iconColor: '#6B7C8E',
    iconGlow: 'rgba(107, 124, 142, 0.85)',
    textColor: '#3F4E5E',
    mood: 'border glow · 5s',
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
 * `collection` hides `hot` (demand is irrelevant when you already own it).
 * Priority: collectible → canon → limited → hot.
 *
 * Collectible (price + scarcity + rarity combo) is the strongest objective signal,
 * so it wins over canon (Discogs editorial pick).
 */
export function pickRarityTier(
  flags: RarityFlags | null | undefined,
  context: RarityContext = 'search',
): RarityTier | null {
  if (!flags) return null;
  if (flags.is_collectible) return 'collectible';
  if (flags.is_canon) return 'canon';
  if (flags.is_limited) return 'limited';
  if (flags.is_hot && context !== 'collection') return 'hot';
  return null;
}

/**
 * Return all applicable tiers (used on the detail screen, no context filtering).
 */
export function allRarityTiers(flags: RarityFlags | null | undefined): RarityTier[] {
  if (!flags) return [];
  const tiers: RarityTier[] = [];
  if (flags.is_collectible) tiers.push('collectible');
  if (flags.is_canon) tiers.push('canon');
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
 * Collectible aura: deep emerald double-layer pulse on a 6s cycle.
 * Slower than limited (4s) and hot (2s) — reads as "contained value, museum piece"
 * rather than "active demand". Two layers: deep outer halo + close border-glow.
 */
function CollectibleAura({ radius = 16 }: { radius?: number }) {
  const tokens = RARITY_TIERS.collectible;
  const t = useSharedValue(0);

  useEffect(() => {
    t.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 3000, easing: Easing.inOut(Easing.ease) }),
        withTiming(0, { duration: 3000, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [t]);

  const outerStyle = useAnimatedStyle(() => ({
    shadowRadius: 18 + 12 * t.value,
    shadowOpacity: 0.45 + 0.45 * t.value,
  }));
  const borderStyle = useAnimatedStyle(() => ({
    borderWidth: 1.5 + 0.5 * t.value,
    borderColor: `rgba(63, 142, 111, ${0.55 + 0.4 * t.value})`,
  }));

  return (
    <>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.collectibleHalo,
          {
            borderRadius: radius + 4,
            shadowColor: tokens.palette[1],
            shadowOffset: { width: 0, height: 0 },
            elevation: 12,
          },
          outerStyle,
        ]}
      />
      <Animated.View
        pointerEvents="none"
        style={[
          styles.collectibleBorder,
          { borderRadius: radius },
          borderStyle,
        ]}
      />
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

/**
 * Canon: thin double-layered border that pulses on a 5s cycle. RN не
 * поддерживает CSS inset box-shadow напрямую — эмулируем двумя слоями:
 * внутренний border (animated) + внешний glow shadow.
 * Without rotation or sweep — strict, "editorial pick" feeling.
 */
function CanonBorderGlow({ radius = 16 }: { radius?: number }) {
  const tokens = RARITY_TIERS.canon;
  const t = useSharedValue(0);

  useEffect(() => {
    t.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 2500, easing: Easing.inOut(Easing.ease) }),
        withTiming(0, { duration: 2500, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
  }, [t]);

  // Inset border: animated borderWidth and borderColor opacity
  const innerStyle = useAnimatedStyle(() => {
    const width = 1.5 + 0.5 * t.value;
    const alpha = 0.5 + 0.35 * t.value;
    return {
      borderWidth: width,
      borderColor: `rgba(139,149,168,${alpha})`,
    };
  });

  // Outer glow: animated shadowRadius + opacity
  const outerStyle = useAnimatedStyle(() => {
    const radiusGlow = 16 + 12 * t.value;
    const opacity = 0.35 + 0.35 * t.value;
    return {
      shadowRadius: radiusGlow,
      shadowOpacity: opacity,
    };
  });

  return (
    <>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.canonOuterGlow,
          {
            borderRadius: radius,
            shadowColor: tokens.palette[0],
            shadowOffset: { width: 0, height: 0 },
            elevation: 8,
          },
          outerStyle,
        ]}
      />
      <Animated.View
        pointerEvents="none"
        style={[
          styles.canonInnerBorder,
          { borderRadius: radius },
          innerStyle,
        ]}
      />
    </>
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
      {tier === 'collectible' && <CollectibleAura radius={radius} />}
      {tier === 'canon' && <CanonBorderGlow radius={radius} />}
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

  // Canon: editorial double border
  canonOuterGlow: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  canonInnerBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },

  // Collectible: emerald double layer
  collectibleHalo: {
    position: 'absolute',
    top: -4,
    left: -4,
    right: -4,
    bottom: -4,
  },
  collectibleBorder: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
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
