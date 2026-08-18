/**
 * Текущая ступень пользователя — один источник на всё приложение.
 *
 * Зачем store, а не запрос по месту. Уровень нужен UI за пределами экрана
 * ачивок: им красятся иконки папок, а папок в горизонтальном скролле бывает
 * десяток. `ArchetypeChip` тянет `/achievements/me` сам на каждый монтаж —
 * повторить это на каждой папке значит устроить залп одинаковых запросов.
 * Здесь ступень лежит в памяти, а компоненты только читают.
 *
 * Кто обновляет. Никто отдельно: значение снимается с тех ответов
 * `/achievements/me`, которые `achievementsBus` и так запрашивает — при входе
 * (`initAchievementsCache`) и после каждого действия, способного что-то
 * открыть (`detectAchievementUnlocks`). Ровно в этот момент ступень и может
 * смениться, так что лишней сети повышение уровня не стоит.
 *
 * Ступень считается на клиенте из открытых ачивок — см. `computeArchetype`.
 * Зеркало правил на бэкенде: Backend/app/services/achievements/levels.py.
 */
import { create } from 'zustand';

import { computeArchetype, LEVELS } from './archetype';
import type { MyAchievementsResponse } from './types';

/** До первого ответа сервера считаем, что юзер на стартовой ступени. */
const DEFAULT_LEVEL_KEY = LEVELS[0].key;

interface LevelState {
  levelKey: string;
}

const useLevelStore = create<LevelState>(() => ({ levelKey: DEFAULT_LEVEL_KEY }));

/** Ключ текущей ступени с подпиской на обновления. */
export function useCurrentLevelKey(): string {
  return useLevelStore((s) => s.levelKey);
}

/** Ключ текущей ступени без подписки — для не-React кода. */
export function getCurrentLevelKey(): string {
  return useLevelStore.getState().levelKey;
}

/** Снять ступень с ответа `/achievements/me`. */
export function setCurrentLevelFrom(data: MyAchievementsResponse): void {
  try {
    useLevelStore.setState({ levelKey: computeArchetype(data).key });
  } catch {
    // Битый ответ не должен ронять вызывающий флоу: остаёмся на прежней ступени.
  }
}

/** Сброс при выходе из аккаунта — иначе следующий юзер увидит чужой цвет. */
export function resetCurrentLevel(): void {
  useLevelStore.setState({ levelKey: DEFAULT_LEVEL_KEY });
}
