/**
 * Хук показа контекстной подсказки. См. lib/coachMarks.ts про правила.
 *
 * Использование:
 *   const tip = useCoachMark('radar', wishlistItems.length > 0);
 *   {tip.visible && <CoachTip meta={tip.meta} onDismiss={tip.dismiss} />}
 *
 * `enabled` — это условие РАЗБЛОКИРОВКИ фичи, а не «показать сейчас».
 * Всё остальное (сколько раз уже показывали, кто выиграл слот сессии) хук
 * решает сам: он подаёт заявку в арбитраж, и победителя выбирает `priority`
 * из каталога, а не порядок объявления хуков в компоненте.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuthStore } from './store';
import { analytics } from './analytics';
import {
  CoachMarkKey,
  getCoachMark,
  isSessionSlotTaken,
  isSuppressed,
  loadCoachMarkStates,
  markCoachMarkAcknowledged,
  markCoachMarkShown,
  releaseSessionSlot,
  requestCoachMark,
} from './coachMarks';
import { clearCoachSpotlight, setCoachSpotlight } from './coachSpotlight';

interface UseCoachMarkResult {
  visible: boolean;
  meta: ReturnType<typeof getCoachMark>;
  dismiss: () => void;
}

export function useCoachMark(key: CoachMarkKey, enabled: boolean): UseCoachMarkResult {
  const userId = useAuthStore((s) => s.user?.id);
  const [visible, setVisible] = useState(false);
  /**
   * Зажигал ли подсветку именно ЭТОТ экземпляр хука. Один ключ может жить на
   * двух экранах (market — коллекция и карточка релиза), и без отметки
   * размонтирование одного гасило бы подсветку, зажжённую другим.
   */
  const ownsSpotlight = useRef(false);

  useEffect(() => {
    if (!enabled || !userId || visible) return;
    // Слот уже занят другой подсказкой — эта дождётся следующего запуска.
    if (isSessionSlotTaken()) return;

    let cancelled = false;
    (async () => {
      const states = await loadCoachMarkStates(userId);
      if (cancelled || isSuppressed(states.get(key))) return;

      const won = await requestCoachMark(key);
      if (!won) return;
      if (cancelled) {
        // Экран ушёл, пока шёл арбитраж. Слот выигран, но показать некому —
        // возвращаем его, иначе сессия останется вообще без подсказки.
        releaseSessionSlot();
        return;
      }

      analytics.onboardingHintShown(key);
      // Показ засчитываем сразу, а не при закрытии: иначе тот, кто уходит с
      // экрана свайпом, получал бы одну и ту же подсказку при каждом запуске
      // бесконечно — она никогда не помечалась показанной.
      void markCoachMarkShown(userId, key);
      // Одновременно с карточкой зажигаем цель: текст называет фичу,
      // подсветка показывает, где она физически лежит.
      ownsSpotlight.current = true;
      setCoachSpotlight(key);
      setVisible(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, userId, key, visible]);

  // Экран ушёл, а подсказка была видима — гасим цель, иначе подсветка осталась
  // бы висеть при следующем возврате на экран.
  useEffect(
    () => () => {
      if (!ownsSpotlight.current) return;
      ownsSpotlight.current = false;
      clearCoachSpotlight(key);
    },
    [key],
  );

  const dismiss = useCallback(() => {
    setVisible(false);
    if (ownsSpotlight.current) {
      ownsSpotlight.current = false;
      clearCoachSpotlight(key);
    }
    // Явное подтверждение: больше не показываем, независимо от счётчика.
    if (userId) void markCoachMarkAcknowledged(userId, key);
  }, [userId, key]);

  return { visible, meta: getCoachMark(key), dismiss };
}
