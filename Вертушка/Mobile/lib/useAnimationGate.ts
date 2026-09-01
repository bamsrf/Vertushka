/**
 * Гейт для бесконечных анимаций.
 *
 * Проблема, которую он решает: Expo Router держит экраны смонтированными в
 * стеке. Ушёл с экрана — а его ауры, теги и градиенты продолжают крутиться на
 * GPU. В сетке коллекции таких анимаций десятки. Внешне это не лаги, а ровный
 * нагрев корпуса и разряд батареи, то есть самая частая жалоба в отзывах.
 *
 * Плюс уважаем системный Reduce Motion — это и доступность, и энергия.
 *
 * **Почему store, а не useEffect в каждом компоненте.** Гейт нужен на каждой
 * карточке сетки. Если бы каждая подписывалась на AppState и дёргала
 * AccessibilityInfo сама, полсотни карточек дали бы полсотни нативных
 * подписок — ровно та накладная нагрузка, которую мы убираем. Здесь одна
 * подписка на всё приложение, компоненты только читают.
 *
 * См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.4.
 */
import { AccessibilityInfo, AppState, AppStateStatus } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { create } from 'zustand';

interface AnimationGateState {
  appActive: boolean;
  reduceMotion: boolean;
}

const useGateStore = create<AnimationGateState>(() => ({
  appActive: AppState.currentState === 'active',
  reduceMotion: false,
}));

// Подписки живут всё время жизни процесса и намеренно не снимаются:
// приложение без них не работает, а отписываться некому и незачем.
AppState.addEventListener('change', (state: AppStateStatus) => {
  useGateStore.setState({ appActive: state === 'active' });
});

AccessibilityInfo.isReduceMotionEnabled()
  .then((reduceMotion) => useGateStore.setState({ reduceMotion }))
  .catch(() => {
    // Настройка недоступна — считаем, что движение разрешено.
  });

AccessibilityInfo.addEventListener('reduceMotionChanged', (reduceMotion: boolean) => {
  useGateStore.setState({ reduceMotion });
});

/**
 * Приложение на переднем плане — БЕЗ учёта Reduce Motion.
 *
 * Для лоадеров: они обязаны выглядеть живыми всегда, застывший спиннер
 * читается как «зависло». Тот же гейт нужен анимациям, которые сознательно
 * игнорируют Reduce Motion (бренд-вращение винила в VinylSpinner).
 */
export function useAppForeground(): boolean {
  return useGateStore((s) => s.appActive);
}

/**
 * Крутить ли анимации в компоненте, живущем ВНЕ экрана навигации
 * (оверлеи в root layout, модалки поверх всего).
 */
export function useAmbientAnimationsEnabled(): boolean {
  return useGateStore((s) => s.appActive && !s.reduceMotion);
}

/**
 * Крутить ли анимации в компоненте ВНУТРИ экрана навигации.
 *
 * Дополнительно гасит анимации на экранах, которые остались в стеке, но
 * сейчас не видны. Вызывать только из компонентов, отрисованных внутри
 * навигатора, — иначе `useIsFocused` бросит.
 */
export function useAnimationsEnabled(): boolean {
  const focused = useIsFocused();
  const ambient = useAmbientAnimationsEnabled();

  return focused && ambient;
}
