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
 * Фон, плашка и акценты зависят от ступени архетипа — см. levelTheme.ts.
 * При входе на экран: волны на фоне идут от центра, ползунок заполняется,
 * а если уровень вырос — плашка со старым статусом уезжает влево и справа
 * приезжает новая (см. useLevelUpReveal).
 *
 * Источник дизайна: Design/style-pack-achievements/07_pin_design/screens/
 * MainScreen.jsx (компонент Hero).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { AchievementPin } from './AchievementPin';
import { Capsule } from './achievement-mockup/Capsule';
import { GoldCorners } from './achievement-mockup/GoldCorners';
import { GrainOverlay } from './achievement-mockup/GrainOverlay';
import { WavesBg } from './achievement-mockup/WavesBg';
import { GlowDot } from './achievement-mockup/GlowDot';
import { Sparkle } from './achievement-mockup/Sparkle';
import { levelTheme, type LevelTheme } from './achievement-mockup/levelTheme';
import {
  M_GOLD_RIM_SOFT,
  M_IVORY,
  M_IVORY_DIM,
  M_IVORY_MUTED,
  M_NAVY,
  M_NAVY_MID,
} from './achievement-mockup/palette';
import { Spacing, BorderRadius } from '../constants/theme';
import { isCompact, ms, s as scaleSize } from '../lib/responsive';
import { rarestUnlocked } from '../lib/achievementHelpers';
import { computeArchetype, LEVELS } from '../lib/archetype';
import { useLevelUpReveal } from '../lib/useLevelUpReveal';
import type { AchievementItem, MyAchievementsResponse } from '../lib/types';

/** Сдвиг плашки за край карточки при перелистывании статуса. */
const CHIP_TRAVEL = 180;
/** Гнездо пина. На узких экранах ужимаем: фиксированные 132 pt съедали
 *  колонку со счётчиком, и «19/72» оставалось меньше 30 pt. */
const GNEZDO = Math.round(scaleSize(132));
const DISC = GNEZDO - 16;

/** Максимальный кегль счётчика; реальный подбирается под ширину колонки. */
const COUNT_SIZE_MAX = 52;
/** Зазор у слэша, px с каждой стороны. Пробелами не задаём: пробел в
 *  RubikMonoOne шириной почти в символ и растаскивает «19/72». */
const COUNT_SEP_GAP = 2;
/** Размер ореола под маркером прогресса. */
const MARKER_GLOW = 44;

interface Props {
  data: MyAchievementsResponse;
  extraRandom?: AchievementItem[];
  username?: string | null;
  /** Пришли по пушу «новый уровень» — отыграть переход принудительно. */
  forceLevelUp?: boolean;
}

export function AchievementsHero({
  data,
  extraRandom = [],
  username,
  forceLevelUp = false,
}: Props) {
  const rarest = rarestUnlocked(data, extraRandom);
  const archetype = computeArchetype(data);

  // Пока переход не отыгран, рисуем старую ступень целиком: и плашку, и фон.
  const { shownKey, isRevealing, commit } = useLevelUpReveal(archetype.key, {
    force: forceLevelUp,
    enabled: !username,
  });
  const theme = levelTheme(shownKey);
  const shownLevel = useMemo(
    () => LEVELS.find((l) => l.key === shownKey) ?? LEVELS[0],
    [shownKey],
  );
  const isOldLevel = shownKey !== archetype.key;

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

  // ── Ползунок ─────────────────────────────────────────────────────────────
  // Обычный вход: 0 → текущий процент. Повышение: сначала добиваем старую
  // ступень до 100% (это и есть причина повышения), потом сбрасываем и
  // заполняем новую.
  const progress = useRef(new Animated.Value(0)).current;
  const targetPct = archetype.progressPct;

  useEffect(() => {
    if (isRevealing) return;
    Animated.timing(progress, {
      toValue: targetPct,
      duration: 900,
      delay: 120,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [isRevealing, targetPct, progress]);

  // ── Перелистывание плашки статуса ────────────────────────────────────────
  const chipX = useRef(new Animated.Value(0)).current;
  const chipOpacity = useRef(new Animated.Value(1)).current;

  // Фон новой ступени проступает сквозь старый, а не подменяется кадром:
  // держим уходящую тему поверх и гасим её за 450 мс.
  const [fadingTheme, setFadingTheme] = useState<LevelTheme | null>(null);
  const themeFade = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!isRevealing) return;

    const seq = Animated.sequence([
      // 1. Добиваем старую ступень до конца.
      Animated.timing(progress, {
        toValue: 1,
        duration: 900,
        delay: 250,
        easing: Easing.inOut(Easing.cubic),
        useNativeDriver: false,
      }),
      // 2. Старая плашка уходит влево.
      Animated.parallel([
        Animated.timing(chipX, {
          toValue: -CHIP_TRAVEL,
          duration: 320,
          easing: Easing.in(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(chipOpacity, {
          toValue: 0,
          duration: 260,
          easing: Easing.linear,
          useNativeDriver: true,
        }),
      ]),
    ]);

    seq.start(({ finished }) => {
      if (!finished) return;
      // 3. Подменяем уровень. Плашка и акценты переключаются кадром (плашка в
      //    этот момент за краем карточки, бар обнулён), фон — переливом.
      setFadingTheme(theme);
      themeFade.setValue(1);
      Animated.timing(themeFade, {
        toValue: 0,
        duration: 450,
        easing: Easing.inOut(Easing.quad),
        useNativeDriver: true,
      }).start(() => setFadingTheme(null));

      commit();
      progress.setValue(0);
      chipX.setValue(CHIP_TRAVEL);
      // 4. Новая плашка приезжает справа, ползунок набирает новый прогресс.
      Animated.parallel([
        Animated.spring(chipX, {
          toValue: 0,
          damping: 14,
          stiffness: 140,
          mass: 0.9,
          useNativeDriver: true,
        }),
        Animated.timing(chipOpacity, {
          toValue: 1,
          duration: 240,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(progress, {
          toValue: targetPct,
          duration: 900,
          delay: 200,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: false,
        }),
      ]).start();
    });

    return () => seq.stop();
    // commit/targetPct стабильны на время перехода; перезапуск по ним не нужен.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRevealing]);

  // ── Звёздочки ────────────────────────────────────────────────────────────
  // Два loop'а с разным периодом и фазой, чтобы блики не мигали синхронно.
  const sparkleTopT = useRef(new Animated.Value(0)).current;
  const sparkleBottomT = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const pulse = (v: Animated.Value, duration: number, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(v, {
            toValue: 1,
            duration,
            delay,
            easing: Easing.inOut(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(v, {
            toValue: 0,
            duration,
            easing: Easing.inOut(Easing.quad),
            useNativeDriver: true,
          }),
        ]),
      );
    const a = pulse(sparkleTopT, 1400, 0);
    const b = pulse(sparkleBottomT, 1900, 500);
    a.start();
    b.start();
    return () => {
      a.stop();
      b.stop();
    };
  }, [sparkleTopT, sparkleBottomT]);

  const sparkleTopScale = sparkleTopT.interpolate({
    inputRange: [0, 1],
    outputRange: [0.75, 1.25],
  });
  const sparkleTopOpacity = sparkleTopT.interpolate({
    inputRange: [0, 1],
    outputRange: [0.5, 1],
  });
  const sparkleBottomScale = sparkleBottomT.interpolate({
    inputRange: [0, 1],
    outputRange: [0.7, 1.15],
  });
  const sparkleBottomOpacity = sparkleBottomT.interpolate({
    inputRange: [0, 1],
    outputRange: [0.4, 0.95],
  });

  // ── Пульс маркера прогресса ──────────────────────────────────────────────
  // Точка на шкале дышит: ореол расходится и гаснет, сама точка чуть
  // подрастает. Это «ты сейчас здесь» — единственная живая метка на линии.
  const dotPulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(dotPulse, {
          toValue: 1,
          duration: 1100,
          easing: Easing.out(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.timing(dotPulse, {
          toValue: 0,
          duration: 900,
          easing: Easing.in(Easing.quad),
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [dotPulse]);

  // ВАЖНО: масштаб только ВНИЗ, максимум ровно 1. SVG растрируется в свой
  // исходный размер, и scale > 1 растягивает готовый растр — отсюда лесенка на
  // кромке ореола. Рисуем сразу в максимальном размере и ужимаем.
  const glowStyle = {
    opacity: dotPulse.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1] }),
    transform: [
      { scale: dotPulse.interpolate({ inputRange: [0, 1], outputRange: [0.6, 1] }) },
    ],
  };
  const dotStyle = {
    transform: [
      { scale: dotPulse.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1] }) },
    ],
  };

  // Кегль считаем от РЕАЛЬНО измеренной ширины колонки, а не от порогов по
  // числу цифр: колонка = ширина экрана минус гнездо пина и отступы, и на
  // узких телефонах «19 / 72» при 52 pt не влезало — хвост срезало краем.
  const [colWidth, setColWidth] = useState(0);
  const countSize = useMemo(() => {
    const big = String(displayCount).length;
    const small = String(data.total).length;
    // Ширина знака RubikMonoOne ≈ 0.78 кегля; слэш уже. Малые цифры и слэш
    // идут на 0.7 кегля — те же множители, что в разметке ниже.
    const units = 0.78 * big + 0.7 * (0.78 * small + 0.62);
    const room = colWidth - 2 * COUNT_SEP_GAP - 2;
    // До первого onLayout берём заведомо влезающий кегль, иначе первый
    // кадр успевает мигнуть срезанным хвостом.
    if (room <= 0) return 44;
    return Math.max(24, Math.min(COUNT_SIZE_MAX, Math.floor(room / units)));
  }, [colWidth, displayCount, data.total]);

  const progressWidth = progress.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });
  const progressLeft = progressWidth;

  // Во время перехода подпись под баром говорит о старой ступени, иначе
  // «45 / 75 XP до Волны» соседствует с плашкой «Волна» — противоречие.
  const progressCaption = isOldLevel
    ? `Ступень пройдена · ${archetype.score} XP`
    : archetype.nextLabel
      ? `${archetype.score} / ${archetype.nextThreshold} XP до «${archetype.nextLabel}»`
      : `Все ступени пройдены · ${archetype.score} XP`;

  return (
    <View style={[styles.wrap, { borderColor: theme.rim }]}>
      {/* Двойной gradient: основной fade ступени + тёплый radial из угла */}
      <LinearGradient
        colors={theme.bg}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <LinearGradient
        colors={theme.glow}
        start={{ x: 1, y: 1 }}
        end={{ x: 0, y: 0 }}
        style={StyleSheet.absoluteFill}
      />
      {/* Уходящая ступень поверх новой — гаснет, давая переливание фона. */}
      {fadingTheme ? (
        <Animated.View
          style={[StyleSheet.absoluteFill, { opacity: themeFade }]}
          pointerEvents="none"
        >
          <LinearGradient
            colors={fadingTheme.bg}
            start={{ x: 0, y: 0 }}
            end={{ x: 0, y: 1 }}
            style={StyleSheet.absoluteFill}
          />
          <LinearGradient
            colors={fadingTheme.glow}
            start={{ x: 1, y: 1 }}
            end={{ x: 0, y: 0 }}
            style={StyleSheet.absoluteFill}
          />
        </Animated.View>
      ) : null}
      <WavesBg opacity={theme.grooveOpacity} />
      <GrainOverlay opacity={0.07} />
      <GoldCorners />

      {/* Main row — pin-gnezdo + колонка «плашка / цифры / подпись» */}
      <View style={styles.mainRow}>
        <View style={styles.gnezdoWrap}>
          {/* Velvet halo */}
          <View style={[styles.gnezdoHalo, { backgroundColor: theme.halo }]} />
          {/* Inner disc with rim */}
          <View
            style={[
              styles.gnezdoDisc,
              { borderColor: theme.chipBorder, backgroundColor: theme.discBg },
            ]}
          >
            {rarest ? (
              <AchievementPin item={rarest} size={isCompact ? 72 : 96} />
            ) : (
              <View style={styles.gnezdoEmpty}>
                <Text style={styles.gnezdoEmptyText}>?</Text>
              </View>
            )}
          </View>
          {/* Sparkle над пином — блик, живёт своей жизнью */}
          <Animated.View
            style={[
              styles.sparkleTop,
              { opacity: sparkleTopOpacity, transform: [{ scale: sparkleTopScale }] },
            ]}
          >
            <Sparkle size={14} color={theme.accent} />
          </Animated.View>
          <Animated.View
            style={[
              styles.sparkleBottom,
              { opacity: sparkleBottomOpacity, transform: [{ scale: sparkleBottomScale }] },
            ]}
          >
            <Sparkle size={9} color={theme.accent} />
          </Animated.View>
        </View>

        <View
          style={styles.counterWrap}
          onLayout={(e) => setColWidth(e.nativeEvent.layout.width)}
        >
          {/* Плашка ступени стоит над цифрами и делит с ними левый край —
              правый блок читается одним столбиком. */}
          <Animated.View
            style={[
              styles.archChip,
              {
                backgroundColor: theme.chipBg,
                borderColor: theme.chipBorder,
                transform: [{ translateX: chipX }],
                opacity: chipOpacity,
              },
            ]}
          >
            <View
              style={[
                styles.archDot,
                { backgroundColor: theme.accent, borderColor: theme.chipBorder },
              ]}
            />
            <Text
              style={[styles.archText, { color: theme.chipFg }]}
              numberOfLines={1}
              adjustsFontSizeToFit
              minimumFontScale={0.75}
            >
              Архетип · {shownLevel.label}
            </Text>
          </Animated.View>

          {/* Три отдельных Text вместо adjustsFontSizeToFit: он ужимал бы
              каждый по отдельности и ломал общую базовую линию. Кегль общий,
              посчитан выше под измеренную ширину колонки. */}
          <View style={styles.counterRow}>
            <Text style={[styles.countBig, { fontSize: countSize }]} numberOfLines={1}>
              {displayCount}
            </Text>
            <Text
              style={[
                styles.countSep,
                { color: theme.accent, fontSize: countSize * 0.7 },
              ]}
              numberOfLines={1}
            >
              /
            </Text>
            <Text
              style={[styles.countSmall, { fontSize: countSize * 0.7 }]}
              numberOfLines={1}
            >
              {data.total}
            </Text>
          </View>
          <Text style={styles.counterCaption}>
            {username ? `@${username}` : 'АЧИВОК ОТКРЫТО'}
          </Text>
        </View>
      </View>

      {/* Flavor */}
      <Text style={styles.flavor} numberOfLines={2}>
        «{shownLevel.flavor}»
      </Text>

      {/* Progress bar к следующему уровню + маркер-точка */}
      <View style={styles.progressBlock}>
        <View style={styles.progressTrack}>
          <Animated.View
            style={[
              styles.progressFill,
              { width: progressWidth, backgroundColor: theme.accent, shadowColor: theme.accent },
            ]}
          />
          {/*
            Маркер собран из двух вложенных слоёв НАМЕРЕННО: позиция едет через
            `left` в процентах (это JS-драйвер), а пульс — через transform/opacity
            (нативный драйвер). На одной View их смешивать нельзя, RN ругается
            «Style property 'left' is not supported by native animated module».
          */}
          <Animated.View style={[styles.markerLayer, { left: progressLeft }]} pointerEvents="none">
            <Animated.View style={[styles.markerGlow, glowStyle]}>
              <GlowDot size={MARKER_GLOW} color={theme.accent} />
            </Animated.View>
            <Animated.View
              style={[
                styles.progressDot,
                {
                  backgroundColor: theme.accent,
                  borderColor: theme.discBg,
                },
                dotStyle,
              ]}
            />
          </Animated.View>
        </View>
        <Text style={styles.progressText}>{progressCaption}</Text>
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
  archChip: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    maxWidth: '100%',
    marginBottom: 8,
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: M_IVORY,
    borderRadius: 999,
    borderWidth: 1,
  },
  archDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 1,
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
    marginTop: Spacing.sm,
  },
  gnezdoWrap: {
    width: GNEZDO,
    height: GNEZDO,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gnezdoHalo: {
    position: 'absolute',
    width: GNEZDO,
    height: GNEZDO,
    borderRadius: GNEZDO / 2,
  },
  gnezdoDisc: {
    width: DISC,
    height: DISC,
    borderRadius: DISC / 2,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: M_NAVY_MID,
    borderWidth: 2,
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
    color: M_IVORY,
    fontFamily: 'RubikMonoOne-Regular',
    letterSpacing: -1,
  },
  countSep: {
    opacity: 0.85,
    fontFamily: 'RubikMonoOne-Regular',
    marginHorizontal: COUNT_SEP_GAP,
  },
  countSmall: {
    color: M_IVORY_MUTED,
    fontFamily: 'RubikMonoOne-Regular',
  },
  counterCaption: {
    marginTop: 4,
    textAlign: 'left',
    alignSelf: 'stretch',
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
    backgroundColor: 'rgba(244,238,230,0.12)',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
    shadowOpacity: 0.7,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 0 },
  },
  markerLayer: {
    position: 'absolute',
    width: MARKER_GLOW,
    height: MARKER_GLOW,
    marginLeft: -MARKER_GLOW / 2,
    // Центрируем по высоте дорожки (6 px).
    top: 3 - MARKER_GLOW / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  markerGlow: {
    position: 'absolute',
  },
  progressDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 2,
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
