/**
 * AchievementsBlock — компактный виджет на профиле.
 *
 * Что показывает:
 * - Заголовок «Ачивки» + счётчик «X / Y»
 * - Превью топ-3 свежих + плашка «❓ Сюрпризы N» если есть открытые рандомные
 * - CTA «Все →»
 *
 * Поведение:
 * - На своём профиле передаём `username=null` → дергаем `getMyAchievements()`.
 * - На чужом профиле — `username='username'` → `getAchievementsByUsername()`.
 * - Тап на блок → navigate в `/achievements` (свой) или `/user/<u>/achievements`.
 */
import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../lib/api';
import { Colors, Spacing, BorderRadius, Typography } from '../constants/theme';
import { ms } from '../lib/responsive';
import { AchievementPin } from './AchievementPin';
import type { AchievementItem, MyAchievementsResponse } from '../lib/types';

interface Props {
  /** null/undefined → свой профиль */
  username?: string | null;
  /** Компактный режим для маленьких карточек */
  compact?: boolean;
}

export function AchievementsBlock({ username, compact = false }: Props) {
  const router = useRouter();
  const [data, setData] = useState<MyAchievementsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const resp = username
          ? await api.getAchievementsByUsername(username)
          : await api.getMyAchievements();
        if (!cancelled) setData(resp);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [username]);

  const handleOpen = () => {
    if (username) {
      router.push({ pathname: '/user/[username]/achievements', params: { username } });
    } else {
      router.push('/achievements');
    }
  };

  if (loading) {
    return (
      <View style={[styles.card, compact && styles.cardCompact]}>
        <View style={styles.headerRow}>
          <Text style={styles.title}>🏆 Ачивки</Text>
        </View>
        <View style={styles.loaderRow}>
          <ActivityIndicator />
        </View>
      </View>
    );
  }

  if (!data) {
    return null;
  }

  const recent = collectRecent(data.series, 3);

  return (
    <TouchableOpacity onPress={handleOpen} activeOpacity={0.7} style={[styles.card, compact && styles.cardCompact]}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>🏆 Ачивки</Text>
        <View style={styles.headerRight}>
          <Text style={styles.counter}>
            {data.unlocked} / {data.total}
          </Text>
          <Ionicons name="chevron-forward" size={18} color={Colors.textMuted} />
        </View>
      </View>

      <View style={styles.pinsRow}>
        {recent.length === 0 ? (
          <Text style={styles.emptyText}>
            {username ? 'У пользователя пока нет открытых ачивок.' : 'Добавь пластинку — откроется первая ачивка.'}
          </Text>
        ) : (
          recent.map((it) => (
            <View key={it.code} style={styles.pinCell}>
              <AchievementPin item={it} size={72} />
              <Text numberOfLines={1} style={styles.pinLabel}>
                {it.title_ru || ''}
              </Text>
            </View>
          ))
        )}
      </View>

      {data.random_unlocked > 0 && (
        <View style={styles.surpriseRow}>
          <Text style={styles.surpriseText}>
            🥚 Пасхалки: открыто {data.random_unlocked}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

function collectRecent(series: MyAchievementsResponse['series'], limit: number): AchievementItem[] {
  const all: AchievementItem[] = [];
  for (const s of series) {
    for (const it of s.items) {
      if (it.is_unlocked) all.push(it);
    }
  }
  all.sort((a, b) => {
    const at = a.unlocked_at ? Date.parse(a.unlocked_at) : 0;
    const bt = b.unlocked_at ? Date.parse(b.unlocked_at) : 0;
    return bt - at;
  });
  return all.slice(0, limit);
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.md,
    marginBottom: Spacing.md,
  },
  cardCompact: {
    paddingVertical: Spacing.sm,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  title: {
    fontSize: ms(17),
    fontWeight: '700',
    color: Colors.text,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  counter: {
    fontSize: ms(14),
    color: Colors.textMuted,
    fontWeight: '500',
  },
  pinsRow: {
    flexDirection: 'row',
    gap: 16,
    paddingVertical: Spacing.xs,
  },
  pinCell: {
    alignItems: 'center',
    width: 88,
  },
  pinLabel: {
    marginTop: 6,
    fontSize: ms(12),
    color: Colors.text,
    textAlign: 'center',
  },
  emptyText: {
    color: Colors.textMuted,
    fontSize: ms(14),
    flex: 1,
    paddingVertical: Spacing.sm,
  },
  surpriseRow: {
    marginTop: Spacing.sm,
    paddingTop: Spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.border,
  },
  surpriseText: {
    fontSize: ms(13),
    color: Colors.textSecondary,
    fontWeight: '500',
  },
  loaderRow: {
    paddingVertical: Spacing.md,
    alignItems: 'center',
  },
});
