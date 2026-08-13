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
 */
import { useSyncExternalStore } from 'react';
import type { CoachMarkKey } from './coachMarks';

let activeKey: CoachMarkKey | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function setCoachSpotlight(key: CoachMarkKey | null) {
  if (activeKey === key) return;
  activeKey = key;
  emit();
}

/** Снять спотлайт, только если он всё ещё «наш». */
export function clearCoachSpotlight(key: CoachMarkKey) {
  if (activeKey !== key) return;
  activeKey = null;
  emit();
}

/**
 * Подсвечивать ли элемент с этим ключом прямо сейчас. Цель вызывает хук у
 * себя и оборачивается в <CoachPulse active={...}>.
 */
export function useCoachSpotlight(key: CoachMarkKey): boolean {
  return useSyncExternalStore(
    subscribe,
    () => activeKey === key,
    () => false,
  );
}
