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
 *
 * `place` — отдельно от `enabled`, потому что это разные вопросы. `enabled`
 * отвечает «дорос ли человек до фичи» (12 пластинок для зума), `place` —
 * «есть ли цель на экране прямо сейчас» (мы на вкладке коллекции, а не на
 * вишлисте). Ручной показ из «Как это работает» игнорирует `enabled`, но не
 * `place`: показать подсказку про сетку поверх вишлиста — значит указать
 * кольцом в чужой элемент.
 */
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useAuthStore } from './store';
import { analytics } from './analytics';
import {
  CoachMarkKey,
  consumeForcedCoachMark,
  getCoachMark,
  getCoachMarkRevision,
  isForcedCoachMark,
  isSessionSlotTaken,
  isSuppressed,
  loadCoachMarkStates,
  markCoachMarkAcknowledged,
  markCoachMarkShown,
  markSessionSlot,
  releaseSessionSlot,
  requestCoachMark,
  subscribeCoachMarks,
} from './coachMarks';
import { clearCoachSpotlight, setCoachSpotlight } from './coachSpotlight';

interface UseCoachMarkResult {
  visible: boolean;
  meta: ReturnType<typeof getCoachMark>;
  dismiss: () => void;
}

export function useCoachMark(
  key: CoachMarkKey,
  enabled: boolean,
  place: boolean = true,
): UseCoachMarkResult {
  const userId = useAuthStore((s) => s.user?.id);
  // Правила показа живут в модуле, а не в пропсах: без подписки сброс из
  // настроек не двигал ни одной зависимости эффекта, и подсказка не
  // возвращалась, пока экран не пересоздадут.
  const revision = useSyncExternalStore(
    subscribeCoachMarks,
    getCoachMarkRevision,
    () => 0,
  );
  const [visible, setVisible] = useState(false);
  /**
   * Зажигал ли подсветку именно ЭТОТ экземпляр хука. Один ключ может жить на
   * двух экранах (market — коллекция и карточка релиза), и без отметки
   * размонтирование одного гасило бы подсветку, зажжённую другим.
   */
  const ownsSpotlight = useRef(false);
  const group = getCoachMark(key).group ?? 'app';

  useEffect(() => {
    if (!userId || visible || !place) return;
    const forced = isForcedCoachMark(key);
    if (!forced) {
      if (!enabled) return;
      // Слот СВОЕЙ группы уже занят — эта подсказка дождётся следующего запуска.
      // Группы независимы: подсказка карточки релиза не конкурирует с подсказкой
      // коллекции, иначе первая не показалась бы почти никогда.
      if (isSessionSlotTaken(group)) return;
    }

    let cancelled = false;
    (async () => {
      const states = await loadCoachMarkStates(userId);
      // Лимит показов ручной запрос не касается: человек только что нажал
      // «Показать» и ждёт результата, а не объяснения, что лимит исчерпан.
      if (cancelled || (!forced && isSuppressed(states.get(key), key))) return;

      // Пауза перед заявкой, а не перед показом: пока идёт задержка, слот
      // остаётся свободным, и подсказка соседнего экрана не блокируется зря.
      // Ручной показ не ждёт: пауза нужна против неожиданности, а этот показ
      // человек запросил сам.
      const delay = forced ? 0 : getCoachMark(key).delayMs;
      if (delay) {
        await new Promise((resolve) => setTimeout(resolve, delay));
        if (cancelled) return;
      }

      if (forced) {
        // Забираем запрос ровно один раз: два экрана с одним ключом (market
        // живёт и в коллекции, и в карточке) иначе показали бы обе карточки.
        if (!consumeForcedCoachMark(key)) return;
        if (cancelled) return;
        // Слот занимаем и здесь: автоподсказка поверх запрошенной вручную —
        // это две карточки на экране одновременно.
        markSessionSlot(group);
      } else {
        const won = await requestCoachMark(key);
        if (!won) return;
        if (cancelled) {
          // Экран ушёл, пока шёл арбитраж. Слот выигран, но показать некому —
          // возвращаем его, иначе сессия останется вообще без подсказки.
          releaseSessionSlot(group);
          return;
        }
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
  }, [enabled, place, userId, key, visible, group, revision]);

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
