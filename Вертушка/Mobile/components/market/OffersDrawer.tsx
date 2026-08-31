/**
 * OffersDrawer — компактная панель с топ-3 офферами, раскрывается при swipe-left
 * по карточке вишлиста.
 *
 * Структура:
 *   - Header: «Сравнить цены» 13pt/700w + HotStockTag inStockMulti size=sm
 *   - Список 3 строк: лого магазина 28dp + название + цена + caret-right
 *   - Footer: «+N ещё в магазинах →» (тап → OffersBottomSheet с полным списком)
 *
 * НЕ wrap в Swipeable сам — это делает родитель (WishlistRowWithOffers).
 * Просто отрисовывается как `renderRightActions` Swipeable'а.
 *
 * Источник: screens-drawer-a.jsx (OffersDrawer атом) +
 *           docs/plans/market/MARKET_AND_PRICE_DRAWER.md §2.2.
 */
import React from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { Icon } from '../ui/Icon';
import HotStockTag, { formatPrice } from '../HotStockTag';
import StoreLogo, { getStoreName } from './StoreLogo';
import { ms } from '../../lib/responsive';

export interface DrawerOffer {
  /** listing.id из БД — для affiliate-tracking POST /offers/{id}/click. */
  listingId: string;
  storeSlug: string;
  /** Override имени, если slug нет в реестре. */
  storeName?: string;
  priceRub: number;
}

interface OffersDrawerProps {
  /** Топ-3 по цене (asc). Если оффера больше — остальное в bottom-sheet. */
  topOffers: readonly DrawerOffer[];
  /** Сколько ВСЕГО офферов (для footer'а «+N ещё»). */
  totalCount: number;
  onOfferPress: (offer: DrawerOffer) => void;
  /** Тап «+N ещё» — открывает OffersBottomSheet с полным списком. */
  onSeeAllPress: () => void;
  width?: number;
  style?: StyleProp<ViewStyle>;
}

export function OffersDrawer({
  topOffers,
  totalCount,
  onOfferPress,
  onSeeAllPress,
  width = 280,
  style,
}: OffersDrawerProps) {
  const minPrice = topOffers.length > 0
    ? Math.min(...topOffers.map((o) => o.priceRub))
    : 0;
  const extraCount = Math.max(0, totalCount - topOffers.length);

  return (
    <View style={[styles.container, { width }, style]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Сравнить цены</Text>
        <View style={{ flex: 1 }} />
        <HotStockTag
          variant="inStockMulti"
          price={minPrice}
          size="sm"
          showArrow={false}
          showShadow={false}
        />
      </View>

      {/* Offers list */}
      <View style={styles.list}>
        {topOffers.map((offer) => (
          <Pressable
            key={offer.listingId}
            onPress={() => onOfferPress(offer)}
            style={({ pressed }) => [
              styles.row,
              pressed && styles.rowPressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Купить в ${offer.storeName ?? getStoreName(offer.storeSlug) ?? offer.storeSlug} за ${formatPrice(offer.priceRub)}`}
          >
            <StoreLogo slug={offer.storeSlug} size={28} radius={6} />
            <Text style={styles.storeName} numberOfLines={1}>
              {offer.storeName ?? getStoreName(offer.storeSlug) ?? offer.storeSlug}
            </Text>
            <Text style={styles.price}>{formatPrice(offer.priceRub)}</Text>
            <Icon name="caret-right" size={14} color="onBrand" style={{ opacity: 0.5 }} />
          </Pressable>
        ))}
      </View>

      {/* «+N ещё» footer */}
      {extraCount > 0 && (
        <Pressable
          onPress={onSeeAllPress}
          style={({ pressed }) => [
            styles.seeAll,
            pressed && styles.rowPressed,
          ]}
          accessibilityRole="button"
          accessibilityLabel={`Ещё ${extraCount} вариантов в магазинах`}
        >
          <Text style={styles.seeAllText}>+{extraCount} ещё в магазинах</Text>
          <Icon name="arrow-right" size={13} color="accent" />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: 'rgba(11,20,56,0.96)',
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 24,
    elevation: 8,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(255,255,255,0.10)',
    backgroundColor: 'rgba(255,255,255,0.04)',
  },
  headerTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(13),
    fontWeight: '700',
    color: '#FFFFFF',
    includeFontPadding: false,
  },
  list: {
    paddingVertical: 4,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  rowPressed: {
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  storeName: {
    flex: 1,
    fontFamily: 'Inter_600SemiBold',
    fontSize: ms(12.5),
    fontWeight: '600',
    color: '#FFFFFF',
    includeFontPadding: false,
  },
  price: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(13.5),
    fontWeight: '700',
    color: '#FFFFFF',
    fontVariant: ['tabular-nums'],
    includeFontPadding: false,
  },
  seeAll: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(255,255,255,0.10)',
  },
  seeAllText: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(11.5),
    fontWeight: '700',
    color: '#FFD9C8',
    includeFontPadding: false,
  },
});

export default OffersDrawer;
