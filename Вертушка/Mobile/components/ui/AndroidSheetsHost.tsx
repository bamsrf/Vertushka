/**
 * AndroidSheetsHost — единая точка монтирования Android-замен нативных
 * iOS-диалогов: `PromptSheet` (вместо `Alert.prompt`) и `OptionsSheet`
 * (вместо `ActionSheetIOS`). Монтируется один раз в `app/_layout.tsx`.
 *
 * На iOS ничего не рендерит — там остаются нативные диалоги (Q6), и в
 * дереве iOS не появляется ни одного лишнего узла.
 */
import React from 'react';
import { Platform } from 'react-native';
import { PromptSheetHost } from './PromptSheet';
import { OptionsSheetHost } from './OptionsSheet';

export function AndroidSheetsHost() {
  if (Platform.OS !== 'android') return null;
  return (
    <>
      <PromptSheetHost />
      <OptionsSheetHost />
    </>
  );
}
