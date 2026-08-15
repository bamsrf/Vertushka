/**
 * Спотлайт контекстной подсказки — «где эта кнопка вообще находится».
 *
 * Текст подсказки называет фичу, но не показывает место: юзер читает «кнопка ₽
 * в шапке» и всё равно её ищет. Раньше место показывал spotlight-тур через
 * measureInWindow — и промахивался рамкой мимо цели (см. lib/coachMarks.ts).
 *
 * Здесь измерений нет вообще: пока подсказка видима, сам элемент рисует
 * вокруг себя пульсирующее кольцо. Он знает свою геометрию лучше любого
 * measure, поэтому промахнуться нечем.
 *
 * Активен максимум один ключ — ровно потому, что и подсказка за сессию одна.
 *
 * Ключи не только от подсказок: чеклист «Первые шаги» тоже указывает место
 * (шаг «Добавить имя и аватар» → карандашик на аватаре). Такие спотлайты
 * временные — гаснут по ttl, потому что закрывать их некому: карточки, у
 * которой есть крестик, рядом нет.
 */
import { useSyncExternalStore } from 'react';
import type { CoachMarkKey } from './coachMarks';

export type SpotlightKey = CoachMarkKey | 'profile-avatar';

let activeKey: SpotlightKey | null = null;
let ttlTimer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function setCoachSpotlight(key: SpotlightKey | null, opts?: { ttlMs?: number }) {
  if (ttlTimer) {
    clearTimeout(ttlTimer);
    ttlTimer = null;
  }
  if (activeKey !== key) {
    activeKey = key;
    emit();
  }
  // ttl перезапускается даже если ключ тот же: повторный тап по шагу должен
  // зажечь подсветку заново, а не доживать остаток прошлого таймера.
  if (key && opts?.ttlMs) {
    ttlTimer = setTimeout(() => {
      ttlTimer = null;
      if (activeKey !== key) return;
      activeKey = null;
      emit();
    }, opts.ttlMs);
  }
}

/** Снять спотлайт, только если он всё ещё «наш». */
export function clearCoachSpotlight(key: SpotlightKey) {
  if (activeKey !== key) return;
  if (ttlTimer) {
    clearTimeout(ttlTimer);
    ttlTimer = null;
  }
  activeKey = null;
  emit();
}

/**
 * Подсвечивать ли элемент с этим ключом прямо сейчас. Цель вызывает хук у
 * себя и оборачивается в <CoachPulse active={...}>.
 */
export function useCoachSpotlight(key: SpotlightKey): boolean {
  return useSyncExternalStore(
    subscribe,
    () => activeKey === key,
    () => false,
  );
}
