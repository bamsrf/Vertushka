/**
 * MetaTrophyShelf — секция «Главные трофеи» (мета-ачивки из всех серий) на
 * экране ачивок. Кладётся между hero и обычными сериями. Порт MetaShelf
 * из MainScreen.jsx.
 */
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { AchievementPin } from './AchievementPin';
import { Capsule } from './achievement-mockup/Capsule';
import { GroovesBg } from './achievement-mockup/GroovesBg';
import {
  M_EMBER_GLOW,
  M_GOLD,
  M_GOLD_RIM_SOFT,
  M_IVORY,
  M_IVORY_DIM,
  M_NAVY,
  M_NAVY_DEEP,
  M_NAVY_MID,
} from './achievement-mockup/palette';
import { Spacing, BorderRadius, Colors } from '../constants/theme';
import { ms } from '../lib/responsive';
import type {
  AchievementItem,
  AchievementSeriesItem,
  MyAchievementsResponse,
} from '../lib/types';

interface MetaWithSeries {
  meta: AchievementItem;
  series: AchievementSeriesItem;
  nearComplete: boolean;
}

interface Props {
  data: MyAchievementsResponse;
  onPin: (item: AchievementItem) => void;
}

const NEAR_THRESHOLD = 0.75;

/** Ширина карточки в карусели и шаг снаппинга (карточка + зазор). */
const CARD_W = ms(148);
const CARD_GAP = 12;

function collectMetas(data: MyAchievementsResponse): MetaWithSeries[] {
  const out: MetaWithSeries[] = [];
  for (const series of data.series) {
    const meta = series.items.find((i) => i.is_meta);
    if (!meta) continue;
    const seriesProgress =
      series.total > 0 ? series.unlocked / series.total : 0;
    const nearComplete = !meta.is_unlocked && seriesProgress >= NEAR_THRESHOLD;
    out.push({ meta, series, nearComplete });
  }
  return out;
}

export function MetaTrophyShelf({ data, onPin }: Props) {
  const metas = collectMetas(data);
  if (metas.length === 0) return null;

  const total = metas.length;
  const unlocked = metas.filter((m) => m.meta.is_unlocked).length;

  return (
    <View style={styles.wrap}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Главные трофеи</Text>
          <Text style={styles.subtitle}>финал каждой серии</Text>
        </View>
        <Capsule tone="gold" size="md">{`${unlocked} / ${total}`}</Capsule>
      </View>

      {/* Карусель, а не сетка: девять трофеев столбиком занимали пол-экрана
          до первой серии. Лента режется по краю карточки (snapToInterval),
          следующая всегда выглядывает — видно, что список продолжается. */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.rail}
        contentContainerStyle={styles.railContent}
        snapToInterval={CARD_W + CARD_GAP}
        decelerationRate="fast"
        snapToAlignment="start"
      >
        {metas.map(({ meta, series, nearComplete }) => (
          <TouchableOpacity
            key={meta.code}
            style={[
              styles.card,
              nearComplete && styles.cardNear,
            ]}
            activeOpacity={0.85}
            onPress={() => onPin(meta)}
          >
            <GroovesBg opacity={0.04} originX={0} originY={400} />

            <Text
              style={[
                styles.cardKicker,
                { opacity: nearComplete ? 1 : 0.55 },
              ]}
              numberOfLines={1}
            >
              {series.title_ru.toUpperCase()}
            </Text>

            <View style={styles.cardPinWrap}>
              <AchievementPin item={meta} size={96} />
            </View>

            <View style={styles.cardFooter}>
              <Text
                style={[
                  styles.cardLabel,
                  !meta.is_unlocked && !nearComplete && { color: M_IVORY_DIM },
                ]}
                numberOfLines={1}
              >
                {meta.title_ru || '?'}
              </Text>
              {nearComplete ? (
                <Text style={styles.cardSubNear}>
                  ОСТАЛОСЬ {series.total - series.unlocked} АЧИВКИ
                </Text>
              ) : meta.is_unlocked ? (
                <Text style={styles.cardSubOpen}>ОТКРЫТО</Text>
              ) : (
                <Text style={styles.cardSubLocked}>ЗАПЕРТО</Text>
              )}
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginHorizontal: Spacing.md,
    marginTop: Spacing.md,
    marginBottom: Spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.md,
    paddingHorizontal: 4,
  },
  title: {
    fontSize: ms(19),
    fontWeight: '800',
    color: Colors.text,
    letterSpacing: -0.4,
  },
  subtitle: {
    fontSize: ms(12),
    color: Colors.textSecondary,
    marginTop: 2,
  },
  // Лента выходит за поля секции, чтобы карточки уезжали под самый край
  // экрана, а не упирались в отступ — иначе обрез выглядит как обрубок.
  rail: {
    marginHorizontal: -Spacing.md,
  },
  railContent: {
    paddingHorizontal: Spacing.md,
    // Воздух под ember-свечение карточки «вот-вот откроется»: без него
    // ScrollView обрезает тень по своей высоте.
    paddingVertical: 6,
    gap: CARD_GAP,
  },
  card: {
    width: CARD_W,
    aspectRatio: 0.82,
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    backgroundColor: M_NAVY,
    borderWidth: 1.5,
    borderColor: M_GOLD_RIM_SOFT,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  cardNear: {
    borderWidth: 2,
    borderColor: M_GOLD,
    shadowColor: M_EMBER_GLOW,
    shadowOpacity: 0.6,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 0 },
    elevation: 6,
  },
  cardKicker: {
    fontSize: 9,
    letterSpacing: 1.4,
    color: M_GOLD,
    fontWeight: '700',
    textAlign: 'center',
  },
  cardPinWrap: {
    marginVertical: 4,
  },
  cardFooter: {
    alignItems: 'center',
  },
  cardLabel: {
    fontSize: ms(14),
    fontWeight: '700',
    color: M_IVORY,
    textAlign: 'center',
    letterSpacing: -0.2,
  },
  cardSubLocked: {
    marginTop: 4,
    fontSize: 10,
    color: M_IVORY_DIM,
    fontWeight: '600',
    letterSpacing: 0.5,
  },
  cardSubOpen: {
    marginTop: 4,
    fontSize: 10,
    color: M_GOLD,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  cardSubNear: {
    marginTop: 4,
    fontSize: 10,
    color: M_GOLD,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});

// Suppress unused imports
const _kept = { M_NAVY_DEEP, M_NAVY_MID };
void _kept;
