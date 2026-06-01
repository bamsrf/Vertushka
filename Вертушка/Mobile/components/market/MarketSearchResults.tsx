/**
 * MarketSearchResults — сетка 2 колонки результатов поиска в Маркете.
 *
 * Используется в (tabs)/search.tsx когда юзер ввёл что-то в MarketSearchInput
 * или выбрал ненулевой FormatChip. Перебивает StoreCarousel-композицию.
 *
 * Состояния:
 *   - loading: лёгкий ActivityIndicator
 *   - empty:   подсказка «Ничего не найдено по «xxx»»
 *   - results: 2-колонная сетка карточек с обложкой/артистом/ценой/магазином
 *
 * Источник: MARKET_AND_PRICE_DRAWER.md §1.8.
 */
import React from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { MarketPalette } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import { resolveMediaUrl } from '../../lib/api';
import MiniPriceBadge from '../MiniPriceBadge';
import StoreLogo, { getStoreName } from './StoreLogo';
import type { MarketSearchItem } from '../../lib/types';

interface MarketSearchResultsProps {
  loading: boolean;
  query: string;
  items: readonly MarketSearchItem[];
  onItemPress: (item: MarketSearchItem) => void;
  style?: StyleProp<ViewStyle>;
}

export function MarketSearchResults({
  loading,
  query,
  items,
  onItemPress,
  style,
}: MarketSearchResultsProps) {
  if (loading) {
    return (
      <View style={[styles.center, style]}>
        <ActivityIndicator size="small" color="rgba(255,255,255,0.65)" />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={[styles.center, style]}>
        <Text style={styles.emptyText}>
          {query.trim().length >= 2
            ? `Ничего не найдено по «${query.trim()}»`
            : 'Для выбранного формата ничего нет в наличии'}
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.grid, style]}>
      {items.map((item) => (
        <Pressable
          key={item.record_id}
          style={styles.card}
          onPress={() => onItemPress(item)}
          accessibilityRole="button"
          accessibilityLabel={`${item.artist} — ${item.title}, ${Number(item.min_price_rub)} рублей`}
        >
          <View style={styles.coverWrap}>
            {item.cover_image_url ? (
              <Image
                source={{ uri: resolveMediaUrl(item.cover_image_url) ?? item.cover_image_url }}
                style={styles.cover}
                resizeMode="cover"
              />
            ) : (
              <View style={[styles.cover, styles.coverPlaceholder]} />
            )}
            {/* Бейдж магазина в углу: лого 18dp, видно сразу из какого магазина */}
            <View style={styles.storeBadge}>
              <StoreLogo
                slug={item.cheapest_store_slug ?? ''}
                size={18}
                radius={4}
              />
            </View>
          </View>
          <View style={styles.textBlock}>
            <Text style={styles.artist} numberOfLines={1}>
              {item.artist.toUpperCase()}
            </Text>
            <Text style={styles.title} numberOfLines={2}>
              {item.title}
            </Text>
            <View style={styles.metaRow}>
              <Text style={styles.meta} numberOfLines={1}>
                {item.year ? `${item.year}` : ''}
                {item.year && item.format_type ? ' · ' : ''}
                {item.format_type ?? ''}
              </Text>
            </View>
            <View style={styles.priceRow}>
              <MiniPriceBadge price={Number(item.min_price_rub)} size={11} color="#FFFFFF" />
              {item.stores_with_stock > 1 && (
                <Text style={styles.storesNote}>
                  в {item.stores_with_stock} магазинах
                </Text>
              )}
            </View>
            {item.cheapest_store_slug && (
              <Text style={styles.storeName} numberOfLines={1}>
                {getStoreName(item.cheapest_store_slug) ?? item.cheapest_store_slug}
              </Text>
            )}
          </View>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    paddingHorizontal: 24,
    paddingVertical: 32,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 120,
  },
  emptyText: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(13),
    color: 'rgba(255,255,255,0.68)',
    textAlign: 'center',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 8,
    gap: 8,
  },
  card: {
    // 2 колонки: 50% минус половина gap (4dp) минус padding (12dp с каждой стороны → 24/2)
    width: '48%',
    marginBottom: 14,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 14,
    overflow: 'hidden',
    padding: 8,
  },
  coverWrap: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 10,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.06)',
    position: 'relative',
  },
  cover: { width: '100%', height: '100%' },
  coverPlaceholder: { backgroundColor: 'rgba(255,255,255,0.10)' },
  storeBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: 6,
    padding: 2,
  },
  textBlock: {
    marginTop: 8,
  },
  artist: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 9,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.65)',
    letterSpacing: 0.3,
    marginBottom: 2,
  },
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(12),
    fontWeight: '700',
    color: '#FFFFFF',
    lineHeight: ms(15),
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 4,
  },
  meta: {
    fontFamily: 'Inter_400Regular',
    fontSize: 10,
    color: 'rgba(255,255,255,0.55)',
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 6,
  },
  storesNote: {
    fontFamily: 'Inter_400Regular',
    fontSize: 9.5,
    color: 'rgba(255,255,255,0.50)',
  },
  storeName: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 10,
    color: '#FFD9C8',
    marginTop: 4,
  },
});

export default MarketSearchResults;
