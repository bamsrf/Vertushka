/**
 * Dev-превью hero-блока ачивок. НЕ входит в продовую навигацию: роут открывается
 * только вручную (/dev-hero-preview) и в проде рендерит заглушку.
 *
 * Зачем: посмотреть переход на новый уровень и темы ступеней, не поднимая
 * бэкенд и не накручивая реальному аккаунту ачивки до порога. Рендерится тот же
 * компонент AchievementsHero, что и на боевом экране, — превью проверяет
 * настоящий код, а не отдельную имитацию.
 */
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { AchievementsHero } from '../components/AchievementsHero';
import { LEVELS } from '../lib/archetype';
import { Colors, Spacing } from '../constants/theme';
import type {
  AchievementItem,
  AchievementTierKey,
  MyAchievementsResponse,
} from '../lib/types';

const TIER_META: Record<AchievementTierKey, { weight: number; label: string; color: string }> = {
  legend: { weight: 100, label: 'Легенда', color: '#1A1A1A' },
  epic: { weight: 30, label: 'Эпическая', color: '#6E5BC6' },
  rare: { weight: 10, label: 'Редкая', color: '#E27BB0' },
  notable: { weight: 3, label: 'Заметная', color: '#2A4BD7' },
  simple: { weight: 1, label: 'Простая', color: '#5C7AE8' },
};

const PIN_SLUGS = ['b5_keeper', 'd4_japanese_x10', 'e2_70s', 'b2_collector', 'a1_first_record'];

/** Набирает ачивки жадно по весам, чтобы получить ровно заданный XP. */
function mockData(score: number): MyAchievementsResponse {
  const items: AchievementItem[] = [];
  let left = score;
  let n = 0;

  for (const tier of ['legend', 'epic', 'rare', 'notable', 'simple'] as AchievementTierKey[]) {
    const meta = TIER_META[tier];
    while (left >= meta.weight) {
      left -= meta.weight;
      items.push({
        code: `mock_${tier}_${n}`,
        title_ru: `Мок-ачивка ${n + 1}`,
        description_ru: null,
        flavor_ru: null,
        icon_slug: PIN_SLUGS[n % PIN_SLUGS.length],
        series: 'foundation',
        tier: { key: tier, label_ru: meta.label, color_hex: meta.color },
        is_hidden: false,
        is_meta: false,
        is_unlocked: true,
        unlocked_at: new Date(Date.now() - n * 86400_000).toISOString(),
        progress: 1,
        progress_target: 1,
      });
      n += 1;
    }
  }

  return {
    total: 89,
    unlocked: items.length,
    random_unlocked: 2,
    series: [
      {
        key: 'foundation',
        title_ru: 'Основание',
        description_ru: '',
        icon_emoji: '💿',
        total: 89,
        unlocked: items.length,
        items,
      },
    ],
  };
}

const STORAGE_KEY = 'achievements:last_level_key';

export default function DevHeroPreview() {
  // Стартуем на «Эхо» (30 XP) — там же, где сейчас реальный аккаунт на скрине.
  const [score, setScore] = useState(45);
  const [nonce, setNonce] = useState(0);
  const [note, setNote] = useState('Уровень: Эхо · 45 XP');

  const remount = useCallback(() => setNonce((v) => v + 1), []);

  /** Записывает «последний виденный» уровень и поднимает XP выше порога. */
  const playLevelUp = useCallback(
    async (fromIdx: number) => {
      const from = LEVELS[fromIdx];
      const to = LEVELS[fromIdx + 1];
      if (!to) return;
      await AsyncStorage.setItem(STORAGE_KEY, from.key);
      // XP чуть выше порога новой ступени — прогресс-бар начнёт почти с нуля.
      setScore(to.threshold + Math.round((LEVELS[fromIdx + 2]?.threshold ?? to.threshold + 50) - to.threshold) / 4);
      setNote(`Переход: ${from.label} → ${to.label}`);
      remount();
    },
    [remount],
  );

  const showLevel = useCallback(
    async (idx: number) => {
      const lvl = LEVELS[idx];
      await AsyncStorage.setItem(STORAGE_KEY, lvl.key);
      const next = LEVELS[idx + 1];
      setScore(lvl.threshold + Math.round(((next?.threshold ?? lvl.threshold + 100) - lvl.threshold) * 0.45));
      setNote(`Уровень: ${lvl.label}`);
      remount();
    },
    [remount],
  );

  if (!__DEV__) {
    return (
      <View style={styles.stub}>
        <Text>Dev-only</Text>
      </View>
    );
  }

  const data = mockData(score);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <AchievementsHero key={nonce} data={data} extraRandom={[]} />

      <Text style={styles.note}>{note}</Text>

      <Text style={styles.section}>Сыграть повышение</Text>
      <View style={styles.row}>
        {LEVELS.slice(0, -1).map((lvl, idx) => (
          <TouchableOpacity
            key={lvl.key}
            style={[styles.btn, styles.btnAccent]}
            onPress={() => playLevelUp(idx)}
          >
            <Text style={styles.btnText}>
              {lvl.label} → {LEVELS[idx + 1].label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <Text style={styles.section}>Показать ступень (без анимации перехода)</Text>
      <View style={styles.row}>
        {LEVELS.map((lvl, idx) => (
          <TouchableOpacity key={lvl.key} style={styles.btn} onPress={() => showLevel(idx)}>
            <Text style={styles.btnText}>{lvl.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.background },
  content: { paddingBottom: 64 },
  stub: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  note: {
    marginTop: Spacing.md,
    marginHorizontal: Spacing.md,
    fontSize: 13,
    color: Colors.textSecondary,
  },
  section: {
    marginTop: Spacing.lg,
    marginHorizontal: Spacing.md,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    color: Colors.textSecondary,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: Spacing.sm,
    marginHorizontal: Spacing.md,
  },
  btn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: 'rgba(0,0,0,0.06)',
  },
  btnAccent: { backgroundColor: 'rgba(232,90,42,0.15)' },
  btnText: { fontSize: 13, fontWeight: '600', color: Colors.text },
});
