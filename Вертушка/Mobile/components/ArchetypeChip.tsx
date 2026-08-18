/**
 * ArchetypeChip — маленький chip с уровнем коллекционера под аватаркой/ником.
 *
 * V3: уровень из XP-лестницы «Физика звука» (см. lib/archetype.ts), цвет —
 * с ленты айдентики (LEVEL_PALETTE), вариант под светлую поверхность.
 * Если уровень = «Тишь» (стартовый) и `hideRookie=true` — ничего не рисуем.
 */
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View, ViewStyle, StyleProp } from 'react-native';
import { api } from '../lib/api';
import { computeArchetype, ArchetypeInfo } from '../lib/archetype';
import { levelPalette } from './achievement-mockup/levelTheme';
import type { MyAchievementsResponse } from '../lib/types';

interface Props {
  /** null/undefined → текущий юзер */
  username?: string | null;
  /** Не рисовать chip, если уровень = «Тишь» (default true) */
  hideRookie?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function ArchetypeChip({ username, hideRookie = true, style }: Props) {
  const [archetype, setArchetype] = useState<ArchetypeInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data: MyAchievementsResponse = username
          ? await api.getAchievementsByUsername(username)
          : await api.getMyAchievements();
        if (cancelled) return;
        setArchetype(computeArchetype(data));
      } catch {
        if (!cancelled) setArchetype(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [username]);

  if (!archetype) return null;
  if (hideRookie && archetype.key === 'silence') return null;

  // Цвет ступени с ленты айдентики, а не тира ачивки: у «Обертона» тир rare, и
  // chip получал розовый TIER_AURA — розовым по светло-розовому, мимо палитры и
  // мимо читаемости. Пара soft/softInk подобрана под светлый фон профиля.
  const tone = levelPalette(archetype.key);

  return (
    <View
      style={[
        styles.chip,
        {
          borderColor: tone.softBorder,
          backgroundColor: tone.soft,
        },
        style,
      ]}
    >
      <Text style={[styles.label, { color: tone.softInk }]}>
        {archetype.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  label: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
});
