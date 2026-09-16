/**
 * MarketSearchInput — glass TextInput для поиска в Маркете.
 *
 * Внешний вид: BlurView 20 + 0.5pt rgba(white, 0.18) border + 12dp radius.
 * Иконка magnifying-glass 16pt слева, опциональный clear-button × справа.
 *
 * При фокусе — border контрастируется (0.4 alpha), плюс легкий 3px outer glow
 * через borderColor + shadow.
 *
 * Источник: screens-market.jsx из Design Claude handoff (MarketSearchInput
 * атом) + docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.7.
 */
import React, { useState } from 'react';
import {
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { BlurViewCompat } from '@/components/ui/BlurViewCompat';

import { Icon } from '../ui/Icon';
import { MarketPalette } from '../../constants/theme';

interface MarketSearchInputProps {
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  onSubmit?: () => void;
  onClear?: () => void;
  autoFocus?: boolean;
  style?: StyleProp<ViewStyle>;
  /** Forwarded to TextInput для управления keyboard / returnKeyType. */
  textInputProps?: Omit<TextInputProps, 'value' | 'onChangeText' | 'placeholder' | 'style'>;
}

export function MarketSearchInput({
  value,
  onChangeText,
  placeholder = 'Найти в магазинах…',
  onSubmit,
  onClear,
  autoFocus,
  style,
  textInputProps,
}: MarketSearchInputProps) {
  const [focused, setFocused] = useState(false);
  const hasValue = value.length > 0;

  const handleClear = () => {
    onChangeText('');
    onClear?.();
  };

  return (
    <BlurViewCompat
      intensity={20}
      tint="dark"
      style={[
        styles.container,
        {
          borderColor: focused
            ? 'rgba(255,255,255,0.40)'
            : MarketPalette.chrome.border,
        },
        focused && styles.focusGlow,
        style,
      ]}
    >
      <Icon
        name="magnifying-glass"
        size={16}
        color="onBrand"
        style={{ opacity: 0.7 }}
      />
      <TextInput
        {...textInputProps}
        value={value}
        onChangeText={onChangeText}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onSubmitEditing={onSubmit}
        autoFocus={autoFocus}
        placeholder={placeholder}
        placeholderTextColor="rgba(255,255,255,0.5)"
        selectionColor="#E85A2A"
        style={styles.input}
        {...PLACEHOLDER_LINE_PROPS}
        returnKeyType="search"
        accessibilityLabel="Поиск в Маркете"
      />
      {hasValue && (
        <Pressable
          onPress={handleClear}
          hitSlop={10}
          accessibilityRole="button"
          accessibilityLabel="Очистить поиск"
        >
          <Icon
            name="x"
            size={16}
            color="onBrand"
            style={{ opacity: 0.7 }}
          />
        </Pressable>
      )}
    </BlurViewCompat>
  );
}

/**
 * maxLines=1 у Android-EditText: длинный плейсхолдер («Найти в Kultura Record
 * Store…») иначе переносится по слову. ТОЛЬКО Android — на iOS проп НЕ инертен:
 * RN прокидывает numberOfLines и в iOS-ветку, оттуда он уходит в
 * paragraphAttributes.maximumNumberOfLines и участвует в ИЗМЕРЕНИИ инпута.
 * Именно так плейсхолдер в поиске на главной уехал вниз на ~9pt (PR #241) —
 * повторять эту ошибку здесь не будем.
 */
const PLACEHOLDER_LINE_PROPS =
  Platform.OS === 'android' ? ({ numberOfLines: 1 } as const) : ({} as const);

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 20,
    marginTop: 8,
    marginBottom: 12,
    paddingHorizontal: 14,
    // ВЫСОТА ОБЯЗАНА БЫТЬ ЯВНОЙ — иначе height: '100%' у инпута внутри
    // бессмыслен: процент резолвится только относительно ОПРЕДЕЛЁННОЙ высоты
    // родителя. Пока здесь стоял paddingVertical без height, родитель мерился
    // по ребёнку, а ребёнок просил процент от родителя; Yoga в такой ситуации
    // трактует процент как auto, и инпут получал высоту ровно по намеренной
    // строке — 18pt (проверено прогоном Yoga: пилюля 42pt, инпут 18pt).
    //
    // Такой впритык-коробки достаточно, чтобы UITextField обрезал строку: он
    // клипует содержимое по своим границам, и любое расхождение метрик шрифта
    // с намеренной высотой съедает низ глифов. Явная высота 44pt даёт инпуту
    // всю пилюлю, и вертикальным центрированием занимается сам UITextField —
    // ровно так устроен рабочий поиск на главной (search.tsx: height 52).
    height: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(255,255,255,0.08)',
    overflow: 'hidden',
  },
  focusGlow: {
    // 3px outer glow когда focused — соответствует boxShadow 0 0 0 3px rgba(white,0.10)
    // в исходном дизайне. RN shadow аппроксимирует через тень.
    shadowColor: '#FFFFFF',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.1,
    shadowRadius: 3,
    elevation: 0,
  },
  input: {
    flex: 1,
    minWidth: 0,
    // Явная высота вместо высоты «по измеренному тексту». Без неё положение
    // текста определяется тем, как RN намерил строку, а мерит он вместе с
    // плейсхолдером: на экране магазина тот длинный («Найти в Kultura Record
    // Store…»), и текст уезжал вниз относительно лупы. Инпут занимает всю
    // пилюлю и центрирует содержимое сам — от длины плейсхолдера и от
    // font-scale это больше не зависит.
    //
    // lineHeight намеренно НЕ ставим: на iOS он сдвигает базовую линию в
    // UITextField. Та же правка и по той же причине уже сделана в поиске на
    // главной (PR #241).
    height: '100%',
    fontFamily: 'Inter_500Medium',
    fontSize: 15,
    fontWeight: '500',
    color: MarketPalette.chrome.textPrimary,
    padding: 0, // зашитый padding TextInput'а на Android портит alignment
    includeFontPadding: false,
    textAlignVertical: 'center',
  },
});

export default MarketSearchInput;
