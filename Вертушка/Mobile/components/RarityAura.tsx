/**
 * Rarity highlighting for vinyl records — card-as-signal tiers.
 *
 * Active tiers:
 *   collectible → heritage gold, rotating shimmer 8s (price>=$100 + scarce + low have)
 *   limited     → cold platinum violet, pulse 4s
 *   hot         → hot ember, pulse 2s + heat-haze halo on cover
 *
 * Closed tiers (kept in types for backward compat with backend, ignored in UI):
 *   first_press — too heuristic without matrix/runout inspection
 *   canon       — Discogs editorial pick, не несёт ценности отдельно от других флагов
 */
import React, { useEffect } from 'react';
import { View, Text, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { useAnimationsEnabled } from '../lib/useAnimationGate';

export type RarityTier = 'collectible' | 'limited' | 'hot';
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
    longLabel: 'Дорогая (≥$100), почти не продаётся, мало у кого есть',
    palette: ['#F4D27A', '#B8860B', '#6B4423'],
    auraOuter: 'rgba(184, 134, 11, 0.55)',
    auraInner: 'rgba(244, 210, 122, 0.80)',
    edge: ['#F4D27A', '#B8860B', '#6B4423'],
    iconColor: '#B8860B',
    iconGlow: 'rgba(184, 134, 11, 0.9)',
    textColor: '#8A6314',
    mood: 'shimmer · 8s',
  },
  limited: {
    id: 'limited',
    label: 'Лимитка',
    longLabel: 'Специальное издание',
    palette: ['#C0C0D8', '#6B4DCE', '#2A1F4E'],
    auraOuter: 'rgba(107, 77, 206, 0.55)',
    auraInner: 'rgba(192, 192, 216, 0.80)',
    edge: ['#C0C0D8', '#6B4DCE', '#2A1F4E'],
    iconColor: '#7A5FE0',
    iconGlow: 'rgba(140, 110, 230, 0.85)',
    textColor: '#5A40B2',
    mood: 'pulse · 4s',
  },
  hot: {
    id: 'hot',
    label: 'Популярно',
    longLabel: 'Высокий спрос на Discogs',
    palette: ['#FFB347', '#FF5E3A', '#B22222'],
    auraOuter: 'rgba(255, 94, 58, 0.62)',
    auraInner: 'rgba(255, 179, 71, 0.85)',
    edge: ['#FFB347', '#FF5E3A', '#B22222'],
    iconColor: '#FF6B3D',
    iconGlow: 'rgba(255, 94, 58, 0.9)',
    textColor: '#C73A1B',
    mood: 'pulse · 2s',
  },
};

/**
 * Pick the single most important tier for a card given context.
 * `collection` hides `hot` (demand is irrelevant when you already own it).
 * Priority: collectible → limited → hot.
 *
 * Только один тир за раз — чтобы карточки не превращались в кашу из нескольких сигналов.
 */
export function pickRarityTier(
  flags: RarityFlags | null | undefined,
  context: RarityContext = 'search',
): RarityTier | null {
  if (!flags) return null;
  if (flags.is_collectible) return 'collectible';
  if (flags.is_limited) return 'limited';
  if (flags.is_hot && context !== 'collection') return 'hot';
  return null;
}

/**
 * Single-tier helper for the detail screen (no context filtering).
 * Возвращаем массив только чтобы не ломать call sites — но всегда максимум один элемент,
 * чтобы блок «Особенности» показывал ровно одну плашку, без наложения сигналов.
 */
export function allRarityTiers(flags: RarityFlags | null | undefined): RarityTier[] {
  const tier = pickRarityTier(flags, 'detail');
  return tier ? [tier] : [];
}

// ─── Aura primitives ─────────────────────────────────────────

interface AuraProps {
  tier: RarityTier;
  radius?: number;
}

/**
 * Collectible aura: rotating emerald gradient ring around the card on a 8s cycle.
 * Same mechanic as the closed `first_press` shimmer, but with the deep-emerald
 * collectible palette. Reads as "museum piece" — slow, deliberate, expensive.
 *
 * Implementation: outer shadow ring (visible glow) + inner clipped rotator
 * containing a multi-stop emerald gradient. The card body sits on top and masks
 * the inside of the ring, leaving only a thin animated rim visible.
 */
function CollectibleAura({ radius = 16 }: { radius?: number }) {
  const tokens = RARITY_TIERS.collectible;
  const rotation = useSharedValue(0);
  const animate = useAnimationsEnabled();

  useEffect(() => {
    if (!animate) {
      cancelAnimation(rotation);
      return;
    }
    // Сброс в 0 обязателен: withRepeat повторяет цикл от значения, с которого
    // стартовал. Гейт снимается на каждом уходе с экрана, и без сброса обод
    // после возврата крутил бы «остаток → -360 → прыжок назад» вместо круга.
    rotation.value = 0;
    rotation.value = withRepeat(
      withTiming(-360, { duration: 8000, easing: Easing.linear }),
      -1,
      false,
    );
    return () => cancelAnimation(rotation);
  }, [animate, rotation]);

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
            borderRadius: radius + 2,
            backgroundColor: 'rgba(184, 134, 11, 0.18)',
            shadowColor: tokens.palette[1],
            shadowOpacity: 0.6,
            shadowRadius: 18,
            shadowOffset: { width: 0, height: 0 },
            elevation: 10,
          },
        ]}
      />
      {/* Кольцо с вращающимся золотым шиммером */}
      <View
        pointerEvents="none"
        style={[
          styles.auraRing,
          {
            borderRadius: radius + 2,
            shadowColor: tokens.palette[0],
            shadowOpacity: 0.55,
            shadowRadius: 10,
            shadowOffset: { width: 0, height: 3 },
            elevation: 8,
          },
        ]}
      >
        <View
          style={[StyleSheet.absoluteFill, styles.auraClip, { borderRadius: radius + 2 }]}
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
  const opacity = useSharedValue(0.4);
  const animate = useAnimationsEnabled();

  useEffect(() => {
    if (!animate) {
      cancelAnimation(opacity);
      opacity.value = 0.4; // статичное состояние вместо застывшего полукадра
      return;
    }
    opacity.value = withRepeat(
      withSequence(
        withTiming(0.7, { duration: 1000, easing: Easing.inOut(Easing.ease) }),
        withTiming(0.4, { duration: 1000, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
    return () => cancelAnimation(opacity);
  }, [animate, opacity]);

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
            borderWidth: 3,
            borderColor: 'rgba(255, 80, 40, 0.55)',
          },
        ]}
      />
      <LinearGradient
        colors={['rgba(255, 94, 58, 0.55)', 'transparent'] as const}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 0.45 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['transparent', 'rgba(178, 34, 34, 0.55)'] as const}
        start={{ x: 0.5, y: 0.55 }}
        end={{ x: 0.5, y: 1 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['rgba(255, 94, 58, 0.45)', 'transparent'] as const}
        start={{ x: 0, y: 0.5 }}
        end={{ x: 0.4, y: 0.5 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={['transparent', 'rgba(255, 94, 58, 0.45)'] as const}
        start={{ x: 0.6, y: 0.5 }}
        end={{ x: 1, y: 0.5 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
    </Animated.View>
  );
}

/**
 * Collectible-only: a soft warm light blink that sweeps diagonally across
 * the cover roughly once every 10 seconds. Heritage gold colors — same effect
 * the closed first_press tier used (это и есть та "фишка с пластинки").
 */
function CoverBlink({ radius = 0 }: { radius?: number }) {
  const t = useSharedValue(0);
  const animate = useAnimationsEnabled();

  useEffect(() => {
    if (!animate) {
      cancelAnimation(t);
      t.value = 0; // блик невидим при v < 0.85 — гасим в прозрачную фазу
      return;
    }
    t.value = withRepeat(
      withSequence(
        withTiming(0, { duration: 0 }),
        withTiming(1, { duration: 10000, easing: Easing.inOut(Easing.ease) }),
      ),
      -1,
      false,
    );
    return () => cancelAnimation(t);
  }, [animate, t]);

  const animStyle = useAnimatedStyle(() => {
    // 0 → 0.85 invisible; 0.85 → 1.0 sweeps from -120% to 220% across the cover
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
      style={[styles.coverEffectClip, { borderRadius: radius }]}
    >
      <Animated.View style={[styles.coverBlink, animStyle]} pointerEvents="none">
        <LinearGradient
          colors={[
            'rgba(255,247,180,0)',
            'rgba(255,242,160,0.85)',
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

// ─── Public components ───────────────────────────────────────

interface RarityAuraProps {
  tier: RarityTier | null;
  radius?: number;
  style?: StyleProp<ViewStyle>;
  children: React.ReactNode;
}

/**
 * Wraps a card with the tier-specific signal:
 *   collectible   → animated golden ring around the entire card
 *   limited / hot → no visual aura (signal lives only in the inline TierLabel)
 *
 * One signal per tier — no double effect. When `tier` is null or non-collectible
 * this is a zero-cost passthrough so non-rare cards pay nothing.
 */
export function RarityAura({
  tier,
  radius = 16,
  style,
  children,
}: RarityAuraProps) {
  if (tier !== 'collectible') return <View style={style}>{children}</View>;

  return (
    <View style={[{ position: 'relative', borderRadius: radius }, style]}>
      <CollectibleAura radius={radius} />
      {children}
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
  if (tier === 'collectible') return <CoverBlink radius={radius} />;
  return null;
}

interface TierEdgeStripProps {
  tier: RarityTier | null;
  radius?: number;
}

/**
 * Vertical gradient strip on the card's left edge — the one signal shared by all
 * three tiers, so signals never fight (no competing rings/borders per tier).
 * Lives at x=0 over the cover's left edge, far from the text column, but still
 * scannable in a long version list. Colors come from the tier's 3-stop palette.
 *
 * Parent must have overflow:'hidden' + matching radius so the strip clips to the
 * rounded corners.
 */
export function TierEdgeStrip({ tier, radius = 0 }: TierEdgeStripProps) {
  if (!tier) return null;
  const tokens = RARITY_TIERS[tier];
  return (
    <LinearGradient
      pointerEvents="none"
      colors={tokens.edge}
      start={{ x: 0.5, y: 0 }}
      end={{ x: 0.5, y: 1 }}
      style={[styles.leftEdge, { borderTopLeftRadius: radius, borderBottomLeftRadius: radius }]}
    />
  );
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

/**
 * Feature-card row used in the "Особенности" section on the record detail screen.
 *
 * RarityAura handles the per-tier visual: collectible → animated ring, limited/hot → left strip.
 * Dot is anchored to the title line (alignSelf flex-start + marginTop), not vertically centered
 * to the whole row, so it reads as a marker right next to the tier name.
 */
export function TierFeatureBlock({ tier }: TierFeatureBlockProps) {
  const tokens = RARITY_TIERS[tier];
  const radius = 14;

  return (
    <RarityAura tier={tier} radius={radius} style={styles.featureWrap}>
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

  // Collectible: thin rotating shimmer ring around the card
  auraRingOuter: {
    position: 'absolute',
    top: -1,
    left: -1,
    right: -1,
    bottom: -1,
  },
  auraRing: {
    position: 'absolute',
    top: -2,
    left: -2,
    right: -2,
    bottom: -2,
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

  // Left edge accent (LIST) — shared tier signal on the card's left rim
  leftEdge: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 6,
    zIndex: 2,
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
    alignItems: 'flex-start',
    gap: 14,
  },
  featureDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    // Анхор к title: title fontSize=14, lineHeight≈17. Центр title ≈ 8.5px от верха.
    // Чтобы dot центр совпал — top = 8.5 - 5 = ~3.5
    marginTop: 4,
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
