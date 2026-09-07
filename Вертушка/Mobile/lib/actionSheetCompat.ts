/**
 * showActionSheet — кроссплатформенный `ActionSheetIOS.showActionSheetWithOptions`
 * (B6, решение Q6).
 *
 * iOS: буквально прежний вызов с теми же аргументами — нативный action sheet.
 * Android: bottom sheet `OptionsSheet` со списком без лимита в три кнопки
 * (прежний фолбэк `Alert.alert` прятал «Пожаловаться»/«Заблокировать» в чате).
 *
 * Сигнатура и семантика колбэка — как у `ActionSheetIOS`: индекс пункта;
 * закрытие без выбора отдаёт `cancelButtonIndex`.
 */
import { ActionSheetIOS, type ActionSheetIOSOptions, Platform } from 'react-native';
import { presentOptionsSheet } from '../components/ui/OptionsSheet';

export type { ActionSheetIOSOptions as ActionSheetOptions };

export function showActionSheet(
  options: ActionSheetIOSOptions,
  callback: (buttonIndex: number) => void,
): void {
  if (Platform.OS === 'ios') {
    ActionSheetIOS.showActionSheetWithOptions(options, callback);
    return;
  }
  presentOptionsSheet(options, callback);
}
