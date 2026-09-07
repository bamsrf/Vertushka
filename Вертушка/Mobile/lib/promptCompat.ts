/**
 * promptText — кроссплатформенный `Alert.prompt` (B5, решение Q6).
 *
 * iOS: буквально прежний вызов `Alert.prompt(title, message, cb, 'plain-text',
 * defaultValue)` — нативный диалог с системными «Отмена»/«OK», нулевой диф.
 * Отмена в этой форме колбэк не зовёт, поэтому промис просто остаётся
 * висеть; ссылок на него никто не держит, и он уходит с GC — ровно как раньше
 * замыкание колбэка.
 * Android: bottom sheet `PromptSheet` (`Alert.prompt` там не существует и
 * молча ничего не делает).
 *
 * Резолвится введённой строкой или `null`. Обрезку и проверку на пустоту
 * делает вызывающий код — как и раньше с `Alert.prompt`.
 */
import { Alert, Platform } from 'react-native';
import { presentPromptSheet, type PromptSheetOptions } from '../components/ui/PromptSheet';

export type PromptTextOptions = PromptSheetOptions;

export function promptText(opts: PromptTextOptions): Promise<string | null> {
  if (Platform.OS === 'ios') {
    return new Promise((resolve) => {
      Alert.prompt(
        opts.title,
        opts.message,
        (value) => resolve(value ?? null),
        'plain-text',
        opts.defaultValue,
      );
    });
  }
  return presentPromptSheet(opts);
}
