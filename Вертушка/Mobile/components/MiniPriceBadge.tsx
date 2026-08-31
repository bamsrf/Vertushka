/**
 * MiniPriceBadge — облегчённая версия `HotStockTag` без gradient-pill.
 *
 * Используется в плотных горизонтальных каруселях Маркета (витрина магазина
 * — см. docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.9 и atoms.jsx из Design
 * Claude handoff). В таких каруселях 15-20 карточек идут в ряд, и полный
 * pill был бы избыточен — пользователь уже понимает контекст из заголовка
 * секции «В НАЛИЧИИ СЕЙЧАС».
 *
 * Компоновка: ◉ (disc duotone, цвет ember) + цена N+2pt mono.
 *
 * Источник правды для формата цены — `formatPrice` в HotStockTag.tsx
 * (NBSP-разделители тысяч, фиксированный «₽»).
 */
import React from 'react';
import { Text, View, StyleSheet, type StyleProp, type ViewStyle } from 'react-native';

import { Icon } from './ui/Icon';
import { formatPrice } from './HotStockTag';

interface MiniPriceBadgeProps {
  /** Цена в рублях. Округляется до целого. */
  price: number;
  /**
   * Размер диск-иконки в pt. Цена будет на +2pt больше (спека atoms.jsx).
   * Default 11 — соответствует мета-строке в маркет-карточке (108×108 обложка).
   */
  size?: number;
  /**
   * Цвет цены. Default '#FFFFFF' — для market-фона / dark overlay.
   * На светлом фоне (карточка в обычной карусели) передавать '#0E121C'.
   */
  color?: string;
  style?: StyleProp<ViewStyle>;
}

export function MiniPriceBadge({
  price,
  size = 11,
  color = '#FFFFFF',
  style,
}: MiniPriceBadgeProps) {
  return (
    <View style={[styles.row, style]}>
      <Icon
        name="disc"
        size={size}
        color="accent"   // accent.ember через wrapper resolve по теме
        weight="duotone"
      />
      <Text
        style={[styles.price, { fontSize: size + 2, color }]}
        numberOfLines={1}
      >
        {formatPrice(price)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    alignSelf: 'flex-start',
  },
  price: {
    fontFamily: 'Inter_700Bold',
    fontWeight: '700',
    letterSpacing: -0.2,
    fontVariant: ['tabular-nums'],
    includeFontPadding: false,
  },
});

export default MiniPriceBadge;
