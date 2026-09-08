/**
 * useAndroidBackClose — системная кнопка «Назад» закрывает оверлей, а не
 * уводит с экрана.
 *
 * Зачем: на Android `BackHandler` по умолчанию делает pop навигации. Всё, что
 * нарисовано поверх экрана без RN `<Modal>` (шиты `@gorhom/bottom-sheet`,
 * кастомные absolute-оверлеи), кнопку не перехватывает — юзер жмёт «Назад»,
 * шит остаётся, а экран под ним исчезает.
 *
 * RN `<Modal>` с `onRequestClose` этот хук НЕ нужен: Dialog ловит клавишу сам.
 *
 * iOS: no-op (`BackHandler` там — заглушка, подписка не создаётся).
 * Подписка живёт только пока `isOpen === true`, поэтому закрытый шит не
 * съедает «Назад» у экрана.
 */
import { useEffect } from 'react';
import { BackHandler, Platform } from 'react-native';

export function useAndroidBackClose(isOpen: boolean, close: () => void): void {
  useEffect(() => {
    if (Platform.OS !== 'android' || !isOpen) return;
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      close();
      return true;
    });
    return () => sub.remove();
  }, [isOpen, close]);
}
