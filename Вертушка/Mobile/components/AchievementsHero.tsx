/**
 * AchievementsHero — V3 mockup-design.
 *
 * Полностью navy-блок с gradient backdrop, концентрическими «канавками» и
 * gold-rim. Структура:
 *   ┌─────────────────────────────────────────────┐
 *   │                          ⬤ Архетип · Тишь  │  top row
 *   │   [pin-gnezdo]    4 / 71                    │  main row
 *   │                   АЧИВОК ОТКРЫТО            │
 *   │ «Ты ещё не нажал на play. Но уже пришёл.»  │  flavor
 *   │ ▓▓▓▓▓░░░░░░  9 / 10 XP до «Шорох»          │  progress bar
 *   │ 🥚 Пасхалки · 1                             │  bottom row
 *   └─────────────────────────────────────────────┘
 *
 * Источник дизайна: Design/style-pack-achievements/07_pin_design/screens/
 * MainScreen.jsx (компонент Hero).
 */
import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { AchievementPin } from './AchievementPin';
import { Capsule } from './achievement-mockup/Capsule';
import { GoldCorners } from './achievement-mockup/GoldCorners';
import { GrainOverlay } from './achievement-mockup/GrainOverlay';
import { GroovesBg } from './achievement-mockup/GroovesBg';
import { Sparkle } from './achievement-mockup/Sparkle';
import {
  M_EMBER,
  M_GOLD,
  M_GOLD_HI,
  M_GOLD_RIM_SOFT,
  M_IVORY,
  M_IVORY_DIM,
  M_IVORY_MUTED,
  M_NAVY,
  M_NAVY_DEEP,
  M_NAVY_HIGH,
  M_NAVY_MID,
} from './achievement-mockup/palette';
import { Spacing, BorderRadius } from '../constants/theme';
import { ms } from '../lib/responsive';
import { rarestUnlocked } from '../lib/achievementHelpers';
import { computeArchetype } from '../lib/archetype';
import type { AchievementItem, MyAchievementsResponse } from '../lib/types';

interface Props {
  data: MyAchievementsResponse;
  extraRandom?: AchievementItem[];
  username?: string | null;
}

export function AchievementsHero({ data, extraRandom = [], username }: Props) {
  const rarest = rarestUnlocked(data, extraRandom);
  const archetype = computeArchetype(data);

  // Анимированный counter
  const animatedCount = useRef(new Animated.Value(0)).current;
  const [displayCount, setDisplayCount] = useState(0);

  useEffect(() => {
    animatedCount.setValue(0);
    const listener = animatedCount.addListener(({ value }) => {
      setDisplayCount(Math.round(value));
    });
    Animated.timing(animatedCount, {
      toValue: data.unlocked,
      duration: 900,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    return () => animatedCount.removeListener(listener);
  }, [data.unlocked, animatedCount]);

  return (
    <View style={styles.wrap}>
      {/* Двойной gradient: основной navy fade + warm radial bottom-right */}
      <LinearGradient
        colors={[M_NAVY_HIGH, M_NAVY, M_NAVY_DEEP] as const}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <LinearGradient
        colors={['rgba(110,91,198,0.35)', 'rgba(110,91,198,0)'] as const}
        start={{ x: 1, y: 1 }}
        end={{ x: 0, y: 0 }}
        style={StyleSheet.absoluteFill}
      />
      <GroovesBg opacity={0.07} originX={350} originY={520} />
      <GrainOverlay opacity={0.07} />
      <GoldCorners />

      {/* Top row — архетип pill справа */}
      <View style={styles.topRow}>
        <View style={styles.archChip}>
          <View style={styles.archDot} />
          <Text style={styles.archText}>Архетип · {archetype.label}</Text>
        </View>
      </View>

      {/* Main row — pin-gnezdo + counter */}
      <View style={styles.mainRow}>
        <View style={styles.gnezdoWrap}>
          {/* Velvet halo */}
          <View style={styles.gnezdoHalo} />
          {/* Inner navy disc with gold rim */}
          <View style={styles.gnezdoDisc}>
            {rarest ? (
              <AchievementPin item={rarest} size={96} />
            ) : (
              <View style={styles.gnezdoEmpty}>
                <Text style={styles.gnezdoEmptyText}>?</Text>
              </View>
            )}
          </View>
          {/* Sparkle над пином — золотой блик */}
          <View style={styles.sparkleTop}>
            <Sparkle size={14} />
          </View>
          <View style={styles.sparkleBottom}>
            <Sparkle size={9} color="rgba(242,199,112,0.7)" />
          </View>
        </View>

        <View style={styles.counterWrap}>
          <View style={styles.counterRow}>
            <Text style={styles.countBig}>{displayCount}</Text>
            <Text style={styles.countSep}>/</Text>
            <Text style={styles.countSmall}>{data.total}</Text>
          </View>
          <Text style={styles.counterCaption}>
            {username ? `@${username}` : 'АЧИВОК ОТКРЫТО'}
          </Text>
        </View>
      </View>

      {/* Flavor */}
      <Text style={styles.flavor} numberOfLines={2}>
        «{archetype.flavor}»
      </Text>

      {/* Progress bar к следующему уровню + golden dot маркер */}
      <View style={styles.progressBlock}>
        <View style={styles.progressTrack}>
          <View
            style={[
              styles.progressFill,
              { width: `${Math.round(archetype.progressPct * 100)}%` },
            ]}
          />
          {archetype.nextLabel ? (
            <View
              style={[
                styles.progressDot,
                {
                  left: `${Math.round(archetype.progressPct * 100)}%`,
                },
              ]}
            />
          ) : null}
        </View>
        <Text style={styles.progressText}>
          {archetype.nextLabel
            ? `${archetype.score} / ${archetype.nextThreshold} XP до «${archetype.nextLabel}»`
            : `Все ступени пройдены · ${archetype.score} XP`}
        </Text>
      </View>

      {/* Bottom row — pasxalka + (optional) recent */}
      {data.random_unlocked > 0 && (
        <View style={styles.bottomRow}>
          <Capsule tone="ember" size="sm">{`🥚 Пасхалки · ${data.random_unlocked}`}</Capsule>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginHorizontal: Spacing.md,
    marginTop: Spacing.md,
    borderRadius: BorderRadius.xl,
    overflow: 'hidden',
    padding: Spacing.lg,
    borderWidth: 1,
    borderColor: M_GOLD_RIM_SOFT,
    minHeight: 260,
    backgroundColor: M_NAVY,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  archChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: M_IVORY,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: M_GOLD,
  },
  archDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: M_GOLD_HI,
    borderWidth: 1,
    borderColor: M_GOLD,
  },
  archText: {
    fontSize: 12,
    fontWeight: '700',
    color: M_NAVY,
    letterSpacing: 0.3,
  },
  mainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    marginTop: Spacing.md,
  },
  gnezdoWrap: {
    width: 132,
    height: 132,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gnezdoHalo: {
    position: 'absolute',
    width: 132,
    height: 132,
    borderRadius: 66,
    backgroundColor: M_EMBER,
    opacity: 0.25,
  },
  gnezdoDisc: {
    width: 116,
    height: 116,
    borderRadius: 58,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: M_NAVY_MID,
    borderWidth: 2,
    borderColor: M_GOLD,
  },
  gnezdoEmpty: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(244,238,230,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: M_GOLD_RIM_SOFT,
    borderStyle: 'dashed',
  },
  gnezdoEmptyText: {
    fontSize: 28,
    color: M_IVORY_DIM,
    fontWeight: '800',
  },
  counterWrap: {
    flex: 1,
    minWidth: 0,
  },
  counterRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  countBig: {
    fontSize: 56,
    lineHeight: 60,
    color: M_IVORY,
    fontFamily: 'RubikMonoOne-Regular',
    letterSpacing: -1,
  },
  countSep: {
    fontSize: 38,
    color: M_GOLD,
    opacity: 0.85,
    marginHorizontal: 4,
    fontFamily: 'RubikMonoOne-Regular',
  },
  countSmall: {
    fontSize: 38,
    color: M_IVORY_MUTED,
    fontFamily: 'RubikMonoOne-Regular',
  },
  counterCaption: {
    marginTop: 4,
    fontSize: 11,
    letterSpacing: 1.6,
    textTransform: 'uppercase',
    color: M_IVORY_MUTED,
    fontWeight: '600',
  },
  flavor: {
    marginTop: Spacing.md,
    fontSize: ms(13),
    color: M_IVORY_MUTED,
    fontStyle: 'italic',
    lineHeight: ms(18),
  },
  progressBlock: {
    marginTop: Spacing.sm,
  },
  progressTrack: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
    backgroundColor: 'rgba(244,238,230,0.12)',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: M_GOLD_HI,
    shadowColor: M_GOLD_HI,
    shadowOpacity: 0.7,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 0 },
  },
  progressDot: {
    position: 'absolute',
    width: 10,
    height: 10,
    borderRadius: 5,
    top: -2,
    marginLeft: -5,
    backgroundColor: M_GOLD_HI,
    borderWidth: 2,
    borderColor: M_NAVY,
    shadowColor: M_GOLD_HI,
    shadowOpacity: 0.9,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 0 },
  },
  sparkleTop: {
    position: 'absolute',
    top: 4,
    right: 18,
  },
  sparkleBottom: {
    position: 'absolute',
    bottom: 16,
    left: 10,
  },
  progressText: {
    marginTop: 6,
    fontSize: ms(11),
    fontWeight: '600',
    color: M_IVORY_MUTED,
    letterSpacing: 0.3,
  },
  bottomRow: {
    marginTop: Spacing.md,
    flexDirection: 'row',
    gap: 8,
  },
});
