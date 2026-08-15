/**
 * Клиентский обнаружитель новых ачивок.
 *
 * Бэкенд эмитит ачивки в фоне (emit_event swallow'ит ошибки и не возвращает
 * данные в HTTP-ответе). Чтобы показывать unlock-анимацию, после каждого
 * действия пользователя, которое может что-то открыть, мы:
 *
 * 1. Помним последний известный набор unlocked codes в памяти.
 * 2. После действия дёргаем `detectAchievementUnlocks()` — он тянет /me,
 *    считает diff и эмитит новые коды в `notifyAchievementUnlocked()`.
 *
 * Кэш живёт только в памяти процесса — при перезапуске приложения
 * первый refresh инициализирует базу без анимации (не показываем при
 * холодном старте).
 */
import { api } from './api';
import {
  notifyAchievementUnlocked,
  resetCelebratedAchievements,
} from '../components/AchievementUnlockOverlay';
import type { MyAchievementsResponse } from './types';

let _knownUnlocked: Set<string> | null = null;
let _initInflight: Promise<void> | null = null;

function extractUnlocked(data: MyAchievementsResponse): Set<string> {
  const s = new Set<string>();
  for (const series of data.series) {
    for (const item of series.items) {
      if (item.is_unlocked) s.add(item.code);
    }
  }
  return s;
}

/** Однократная инициализация кэша при логине. После этого `detect*` будет
 *  показывать только реальные новые анлоки. */
export async function initAchievementsCache(): Promise<void> {
  if (_initInflight) return _initInflight;
  _initInflight = (async () => {
    try {
      const data = await api.getMyAchievements();
      const unlocked = extractUnlocked(data);
      // Для рандомных тоже учтём (они отдельным endpoint'ом приходят полностью)
      try {
        const random = await api.getMyRandomUnlocked();
        for (const it of random.items) unlocked.add(it.code);
      } catch {
        // тихо
      }
      _knownUnlocked = unlocked;
    } catch {
      _knownUnlocked = new Set();
    } finally {
      _initInflight = null;
    }
  })();
  return _initInflight;
}

/** Сбросить кэш — например, при выходе из аккаунта. */
export function resetAchievementsCache(): void {
  _knownUnlocked = null;
  resetCelebratedAchievements();
}

/** Проверить новые анлоки и показать overlay. Безопасно вызывать после любого
 *  действия — если ничего не открылось, ничего не покажется. */
export async function detectAchievementUnlocks(): Promise<void> {
  try {
    // Если кэша ещё нет — инициализируем тихо, чтобы не показывать всё
    // открытое ранее как «свежее».
    if (_knownUnlocked === null) {
      await initAchievementsCache();
      return;
    }

    const data = await api.getMyAchievements();
    const nowSet = extractUnlocked(data);

    // Рандомные приходят отдельно
    try {
      const random = await api.getMyRandomUnlocked();
      for (const it of random.items) nowSet.add(it.code);
    } catch {
      // тихо
    }

    const newCodes: string[] = [];
    for (const code of nowSet) {
      if (!_knownUnlocked.has(code)) newCodes.push(code);
    }

    _knownUnlocked = nowSet;

    if (newCodes.length > 0) {
      notifyAchievementUnlocked(newCodes);
    }
  } catch {
    // Тихо — не должны падать в основном UI-флоу.
  }
}
