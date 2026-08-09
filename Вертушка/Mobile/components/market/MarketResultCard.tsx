/**
 * MarketResultCard — карточка пластинки в сетке результатов Маркета.
 *
 * Одна карточка на два экрана:
 *   • общая витрина (MarketMain) — `showStore` включён: бейдж лого в углу
 *     обложки, «в N магазинах» и название самого дешёвого магазина;
 *   • витрина магазина (/market/store/[slug]) — `showStore` выключен: магазин
 *     и так известен из шапки, дублировать его в каждой карточке — шум.
 *
 * Раньше это были две почти одинаковые реализации (MarketSearchResults + инлайн
 * renderItem на экране магазина) и они успели разъехаться по вёрстке. Один
 * компонент + `marketGridStyles` держат сетки идентичными.
 *
 * Сетка — FlatList numColumns={2}: ширина 48% (50% минус половина gap'а 8dp),
 * НЕ flex:1 — иначе при нечётном количестве последняя карточка растянется
 * на всю ширину.
 */
import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { ms } from '../../lib/responsive';
import { resolveMediaUrl } from '../../lib/api';
import MiniPriceBadge from '../MiniPriceBadge';
import StoreLogo, { getStoreName } from './StoreLogo';
import type { MarketSearchItem } from '../../lib/types';

interface MarketResultCardProps {
  item: MarketSearchItem;
  onPress: (item: MarketSearchItem) => void;
  /** Показывать бейдж/название магазина. Нужно только на общей витрине. */
  showStore?: boolean;
}

export function MarketResultCard({ item, onPress, showStore = false }: MarketResultCardProps) {
  const cover = item.cover_image_url
    ? resolveMediaUrl(item.cover_image_url) ?? item.cover_image_url
    : null;

  return (
    <Pressable
      style={styles.card}
      onPress={() => onPress(item)}
      accessibilityRole="button"
      accessibilityLabel={`${item.artist} — ${item.title}, ${Number(item.min_price_rub)} рублей`}
    >
      <View style={styles.coverWrap}>
        {cover ? (
          <Image source={{ uri: cover }} style={styles.cover} resizeMode="cover" />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]} />
        )}
        {showStore && !!item.cheapest_store_slug && (
          <View style={styles.storeBadge}>
            <StoreLogo slug={item.cheapest_store_slug} size={18} radius={4} />
          </View>
        )}
      </View>

      <View style={styles.textBlock}>
        <Text style={styles.artist} numberOfLines={1}>
          {item.artist.toUpperCase()}
        </Text>
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <View style={styles.metaRow}>
          {item.year != null && <Text style={styles.meta}>{item.year}</Text>}
          {item.year != null && !!item.format_type && <View style={styles.metaDot} />}
          {!!item.format_type && (
            <Text style={styles.meta} numberOfLines={1}>{item.format_type}</Text>
          )}
        </View>
        <View style={styles.priceRow}>
          <MiniPriceBadge price={Number(item.min_price_rub)} size={11} color="#FFFFFF" />
          {showStore && item.stores_with_stock > 1 && (
            <Text style={styles.storesNote}>в {item.stores_with_stock} магазинах</Text>
          )}
        </View>
        {showStore && !!item.cheapest_store_slug && (
          <Text style={styles.storeName} numberOfLines={1}>
            {getStoreName(item.cheapest_store_slug) ?? item.cheapest_store_slug}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

/** Стили сетки для FlatList numColumns={2} — общие для обеих витрин. */
export const marketGridStyles = StyleSheet.create({
  row: {
    paddingHorizontal: 12,
    justifyContent: 'flex-start',
    gap: 8,
  },
  content: {
    paddingBottom: 60,
  },
});

const styles = StyleSheet.create({
  card: {
    width: '48%',
    marginBottom: 12,
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
  textBlock: { marginTop: 8 },
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
  metaDot: {
    width: 2, height: 2, borderRadius: 1,
    backgroundColor: 'rgba(255,255,255,0.40)',
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

export default MarketResultCard;
