/**
 * MarketSection — главная композиция раздела «Маркет».
 *
 * Собирает в одно целое:
 *   MarketHeader (hero) + MarketSearchInput + FormatChips + N StoreCarousel'ов.
 *
 * Используется:
 *   - В (tabs)/search.tsx как нижняя половина экрана (после Discogs-секций).
 *     Поверх — двухслойный MarketBackground с magic-transition.
 *   - На /market/store/[slug].tsx как часть полной витрины магазина
 *     (через `storeFilter` пропс, рендерим только один StoreCarousel).
 *
 * Поиск и чипы — controlled state, родитель решает что делать с query/format.
 * Тап на магазин или карточку — поднимаем наружу через onStorePress/onItemPress.
 *
 * Источник: screens-market.jsx (ScreenMarketFull композиция) +
 *           docs/plans/MARKET_AND_PRICE_DRAWER.md §1.6-1.9.
 */
import React from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import MarketHeader from './MarketHeader';
import MarketSearchInput from './MarketSearchInput';
import FilterBar from './FilterBar';
import type { MarketFilters, MarketFacetsResponse } from '../../lib/types';
import StoreCarousel from './StoreCarousel';
import { type MarketCarouselCardData } from './MarketCarouselCard';

export interface MarketStoreData {
  slug: string;
  name?: string;
  totalCount: number;
  items: readonly MarketCarouselCardData[];
}

interface MarketSectionProps {
  stores: readonly MarketStoreData[];

  // Controlled inputs
  searchValue: string;
  onSearchChange: (v: string) => void;
  onSearchSubmit?: () => void;

  filters: MarketFilters;
  onFiltersChange: (f: MarketFilters) => void;
  /** Доступные жанры/особенности из /market/facets (null → ещё грузится). */
  facets: MarketFacetsResponse | null;

  // Метрики (для subtitle: «N магазинов · M шт.»). Если не передано —
  // считаем из stores.
  totalStores?: number;
  totalItems?: number;

  // Actions
  onStorePress?: (slug: string) => void;
  onItemPress?: (item: MarketCarouselCardData, storeSlug: string) => void;

  /** Top padding hero header (под safe-area). Default 70. */
  headerPaddingTop?: number;

  style?: StyleProp<ViewStyle>;
}

export function MarketSection({
  stores,
  searchValue,
  onSearchChange,
  onSearchSubmit,
  filters,
  onFiltersChange,
  facets,
  totalStores,
  totalItems,
  onStorePress,
  onItemPress,
  headerPaddingTop,
  style,
}: MarketSectionProps) {
  const resolvedStoreCount = totalStores ?? stores.length;
  const resolvedItemCount =
    totalItems ?? stores.reduce((sum, s) => sum + s.totalCount, 0);

  const subtitle = `В наличии сейчас · ${pluralize(resolvedStoreCount, 'магазин', 'магазина', 'магазинов')} · ${formatCount(resolvedItemCount)} шт.`;

  return (
    <View style={style}>
      <MarketHeader
        mode="hero"
        subtitle={subtitle}
        paddingTop={headerPaddingTop}
      />

      <View style={styles.controls}>
        <MarketSearchInput
          value={searchValue}
          onChangeText={onSearchChange}
          onSubmit={onSearchSubmit}
        />
        <FilterBar filters={filters} onChange={onFiltersChange} facets={facets} />
      </View>

      {stores.map((store, idx) => (
        <React.Fragment key={store.slug}>
          {idx > 0 && <View style={styles.divider} />}
          <StoreCarousel
            storeSlug={store.slug}
            storeName={store.name}
            totalCount={store.totalCount}
            items={store.items}
            onStorePress={
              onStorePress ? () => onStorePress(store.slug) : undefined
            }
            onItemPress={
              onItemPress
                ? (item) => onItemPress(item, store.slug)
                : undefined
            }
          />
        </React.Fragment>
      ))}
    </View>
  );
}

// ────────────────────────────────────────────────────────────────────────

function formatCount(n: number): string {
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

function pluralize(n: number, one: string, few: string, many: string): string {
  const n10 = n % 10;
  const n100 = n % 100;
  let word: string;
  if (n10 === 1 && n100 !== 11) word = one;
  else if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) word = few;
  else word = many;
  return `${formatCount(n)} ${word}`;
}

const styles = StyleSheet.create({
  controls: {
    marginTop: 16,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(255,255,255,0.10)',
    marginHorizontal: 20,
    marginVertical: 8,
  },
});

export default MarketSection;
