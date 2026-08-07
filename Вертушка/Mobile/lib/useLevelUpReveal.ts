/**
 * useLevelUpReveal — «повышение отыгрывается ровно один раз».
 *
 * Уровень считается на клиенте из открытых ачивок, поэтому момент перехода
 * ловим сравнением с последним показанным ключом в AsyncStorage. Пока анимация
 * не отыграна, hero показывает СТАРУЮ ступень (`shownKey`) — иначе юзер входит
 * на экран, где новый статус уже стоит, и «повышать» нечего.
 *
 * Пуш ведёт на /achievements?levelup=1 — тогда `force` заставляет отыграть
 * переход даже если ключ уже записан (например, экран открывали до пуша).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { LEVELS } from './archetype';

const STORAGE_KEY = 'achievements:last_level_key';

export interface LevelUpReveal {
  /** Ключ уровня, который сейчас должен рисовать hero. */
  shownKey: string;
  /** Идёт ли переход прямо сейчас (для запуска анимаций). */
  isRevealing: boolean;
  /** Вызывается анимацией в момент подмены плашки. */
  commit: () => void;
}

function isKnownLevel(key: string | null): boolean {
  return !!key && LEVELS.some((l) => l.key === key);
}

export function useLevelUpReveal(
  currentKey: string,
  { force = false, enabled = true }: { force?: boolean; enabled?: boolean } = {},
): LevelUpReveal {
  const [shownKey, setShownKey] = useState(currentKey);
  const [isRevealing, setIsRevealing] = useState(false);
  // Однократность в пределах монтирования: без этого повторный рендер с тем же
  // currentKey перезапускал бы переход.
  const handled = useRef(false);

  useEffect(() => {
    // Чужой профиль: ступень не наша, и записывать её в сторадж нельзя —
    // иначе своё повышение потом «уже отыграно».
    if (!enabled) return;
    let cancelled = false;

    (async () => {
      let stored: string | null = null;
      try {
        stored = await AsyncStorage.getItem(STORAGE_KEY);
      } catch {
        // Хранилище недоступно — просто не отыгрываем переход.
      }
      if (cancelled) return;

      const currentIdx = LEVELS.findIndex((l) => l.key === currentKey);

      // Первый заход (или мусор в сторадже): фиксируем уровень молча.
      if (!isKnownLevel(stored)) {
        try {
          await AsyncStorage.setItem(STORAGE_KEY, currentKey);
        } catch {
          /* не критично */
        }
        return;
      }

      const storedIdx = LEVELS.findIndex((l) => l.key === stored);
      const grew = storedIdx >= 0 && currentIdx > storedIdx;

      // force без реального роста (тап по пушу на уже засчитанном уровне):
      // показываем переход с предыдущей ступени, чтобы тап не привёл в никуда.
      const from = grew ? stored! : LEVELS[Math.max(0, currentIdx - 1)].key;
      if (!grew && (!force || currentIdx === 0)) return;
      if (handled.current) return;

      handled.current = true;
      setShownKey(from);
      setIsRevealing(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [currentKey, force, enabled]);

  const commit = useCallback(() => {
    setShownKey(currentKey);
    setIsRevealing(false);
    AsyncStorage.setItem(STORAGE_KEY, currentKey).catch(() => {});
  }, [currentKey]);

  return { shownKey, isRevealing, commit };
}
