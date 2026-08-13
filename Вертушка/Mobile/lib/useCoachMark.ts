/**
 * Хук показа контекстной подсказки. См. lib/coachMarks.ts про правила.
 *
 * Использование:
 *   const tip = useCoachMark('radar', wishlistItems.length > 0);
 *   {tip.visible && <CoachTip meta={tip.meta} onDismiss={tip.dismiss} />}
 *
 * `enabled` — это условие РАЗБЛОКИРОВКИ фичи, а не «показать сейчас».
 * Всё остальное (был ли уже показ, кто выиграл слот сессии) хук решает сам:
 * он подаёт заявку в арбитраж, и победителя выбирает `priority` из каталога,
 * а не порядок объявления хуков в компоненте.
 */
import { useCallback, useEffect, useState } from 'react';
import { useAuthStore } from './store';
import { analytics } from './analytics';
import {
  CoachMarkKey,
  getCoachMark,
  isSessionSlotTaken,
  loadSeenCoachMarks,
  markCoachMarkSeen,
  releaseSessionSlot,
  requestCoachMark,
} from './coachMarks';

interface UseCoachMarkResult {
  visible: boolean;
  meta: ReturnType<typeof getCoachMark>;
  dismiss: () => void;
}

export function useCoachMark(key: CoachMarkKey, enabled: boolean): UseCoachMarkResult {
  const userId = useAuthStore((s) => s.user?.id);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!enabled || !userId || visible) return;
    // Слот уже занят другой подсказкой — эта дождётся следующего запуска.
    if (isSessionSlotTaken()) return;

    let cancelled = false;
    (async () => {
      const seen = await loadSeenCoachMarks(userId);
      if (cancelled || seen.has(key)) return;

      const won = await requestCoachMark(key);
      if (!won) return;
      if (cancelled) {
        // Экран ушёл, пока шёл арбитраж. Слот выигран, но показать некому —
        // возвращаем его, иначе сессия останется вообще без подсказки.
        releaseSessionSlot();
        return;
      }

      analytics.onboardingHintShown(key);
      setVisible(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [enabled, userId, key, visible]);

  const dismiss = useCallback(() => {
    setVisible(false);
    if (userId) void markCoachMarkSeen(userId, key);
  }, [userId, key]);

  return { visible, meta: getCoachMark(key), dismiss };
}
