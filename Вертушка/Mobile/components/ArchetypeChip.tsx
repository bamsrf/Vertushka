/**
 * ArchetypeChip — маленький chip с уровнем коллекционера под аватаркой/ником.
 *
 * V3: уровень из XP-лестницы «Физика звука» (см. lib/archetype.ts), цвет —
 * с ленты айдентики (LEVEL_PALETTE), вариант под светлую поверхность.
 * Если уровень = «Тишь» (стартовый) и `hideRookie=true` — ничего не рисуем.
 *
 * Свой уровень берём из `useCurrentLevelKey` — того же стора, что красит папки.
 * Раньше chip сам ходил в `/achievements/me` на монтировании, и это давало две
 * беды: лишний запрос на каждом открытии профиля и застывший цвет — экран
 * профиля живёт в стеке Expo Router, эффект больше не срабатывал, и после
 * повышения плашка оставалась старой до перезапуска. Стор обновляется из
 * ответов, которые `achievementsBus` и так запрашивает, так что плашка,
 * иконка уведомления и полка папок перекрашиваются одним движением.
 *
 * Чужой профиль (`username`) — по-прежнему запрос: чужой ступени в сторе нет.
 */
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View, ViewStyle, StyleProp } from 'react-native';
import { api } from '../lib/api';
import { computeArchetype, LEVELS } from '../lib/archetype';
import { useCurrentLevelKey } from '../lib/levelStore';
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
  const ownLevelKey = useCurrentLevelKey();
  const [foreignKey, setForeignKey] = useState<string | null>(null);

  useEffect(() => {
    if (!username) {
      setForeignKey(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data: MyAchievementsResponse = await api.getAchievementsByUsername(username);
        if (!cancelled) setForeignKey(computeArchetype(data).key);
      } catch {
        if (!cancelled) setForeignKey(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [username]);

  const levelKey = username ? foreignKey : ownLevelKey;
  if (!levelKey) return null;

  const level = LEVELS.find((l) => l.key === levelKey);
  if (!level) return null;
  if (hideRookie && level.key === 'silence') return null;

  // Цвет ступени с ленты айдентики, а не тира ачивки: у «Обертона» тир rare, и
  // chip получал розовый TIER_AURA — розовым по светло-розовому, мимо палитры и
  // мимо читаемости. Пара soft/softInk подобрана под светлый фон профиля.
  const tone = levelPalette(level.key);

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
      <Text style={[styles.label, { color: tone.softInk }]}>{level.label}</Text>
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
