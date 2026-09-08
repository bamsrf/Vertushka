/**
 * Text / TextInput с clamp'ом системного font-scale (M3 в ANDROID_PORT_PLAN).
 *
 * Прежний `clampSystemFontScale()` писал `maxFontSizeMultiplier` в
 * `Text.defaultProps` — на RN 0.86 / React 19 это no-op: `defaultProps` у
 * function-компонентов больше не читается. Клэмпа не было ни на одной
 * платформе; iOS это прощал (там редко ставят 130%), Android — нет.
 *
 * Эти два компонента — те же RN `Text`/`TextInput`, только с дефолтным
 * `maxFontSizeMultiplier = MAX_FONT_SCALE`. Явный проп в месте вызова
 * перебивает дефолт. Ref пробрасывается на нативный компонент, поэтому
 * `useRef<TextInput>().current?.focus()` и `Animated.createAnimatedComponent`
 * работают как раньше.
 *
 * Подставляются вместо RN-экспортов через alias в `metro.config.js` — в
 * коде приложения по-прежнему `import { Text } from 'react-native'`, без
 * правки 120 файлов. Этот файл alias'ом НЕ накрывается (иначе цикл), потому
 * импортирует настоящий RN.
 *
 * При 100% системного масштаба визуал не меняется: множитель ≤ 1.15 —
 * это потолок, а не коэффициент.
 */
import React, { forwardRef } from 'react';
import {
  Platform,
  Text as RNText,
  TextInput as RNTextInput,
  type TextInputProps,
  type TextProps,
} from 'react-native';
import { MAX_FONT_SCALE } from './maxFontScale';

/**
 * Пока только Android. На iOS клэмпа не было ни в одном отгруженном билде
 * (1.0.0 — тот же no-op через defaultProps), и включение = видимое изменение
 * для людей с «Размером текста» выше 115% — это отдельное решение, а не часть
 * Android-порта (ANDROID_PORT_PLAN §2). Включить на iOS = убрать гвард.
 */
const DEFAULT_MAX_FONT_SCALE = Platform.OS === 'android' ? MAX_FONT_SCALE : undefined;

export const Text = forwardRef<React.ElementRef<typeof RNText>, TextProps>(function ScaledText(
  props,
  ref,
) {
  return <RNText ref={ref} maxFontSizeMultiplier={DEFAULT_MAX_FONT_SCALE} {...props} />;
});

export const TextInput = forwardRef<React.ElementRef<typeof RNTextInput>, TextInputProps>(
  function ScaledTextInput(props, ref) {
    return <RNTextInput ref={ref} maxFontSizeMultiplier={DEFAULT_MAX_FONT_SCALE} {...props} />;
  },
);
