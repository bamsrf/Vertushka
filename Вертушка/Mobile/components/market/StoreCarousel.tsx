/**
 * StoreCarousel — витрина одного магазина в Маркете.
 *
 * Структура:
 *   - Header: StoreLogo + название + кол-во + caret-right (тап → полный магазин).
 *   - Horizontal scroll: 15-20 MarketCarouselCard'ов из этого магазина.
 *   - Terminal card «Все N →» в конце (тоже ведёт на полный магазин).
 *
 * Источник: screens-market.jsx (StoreCarousel атом) +
 *           docs/plans/MARKET_AND_PRICE_DRAWER.md §1.9.
 */
import React from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { Icon } from '../ui/Icon';
import { MarketPalette } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import StoreLogo, { getStoreName } from './StoreLogo';
import MarketCarouselCard, { type MarketCarouselCardData } from './MarketCarouselCard';

interface StoreCarouselProps {
  storeSlug: string;
  /** Override имени, если slug нет в STORE_REGISTRY. */
  storeName?: string;
  /** Всего в магазине in_stock (для header'а и terminal-карточки). */
  totalCount: number;
  /** Карточки для отрисовки. Обычно 15-20. */
  items: readonly MarketCarouselCardData[];
  /** Tap на header магазина или на terminal-карточку — открывает полный магазин. */
  onStorePress?: () => void;
  /** Tap на конкретную карточку — открывает /record/[id]. */
  onItemPress?: (item: MarketCarouselCardData) => void;
  style?: StyleProp<ViewStyle>;
}

export function StoreCarousel({
  storeSlug,
  storeName,
  totalCount,
  items,
  onStorePress,
  onItemPress,
  style,
}: StoreCarouselProps) {
  const displayName = storeName ?? getStoreName(storeSlug) ?? storeSlug;

  return (
    <View style={[styles.container, style]}>
      {/* Header */}
      <Pressable
        onPress={onStorePress}
        hitSlop={6}
        style={styles.header}
        accessibilityRole="button"
        accessibilityLabel={`${displayName}, ${totalCount} пластинок в наличии. Открыть полную витрину.`}
      >
        <StoreLogo slug={storeSlug} size={44} radius={10} />
        <View style={styles.headerText}>
          <Text style={styles.storeName} numberOfLines={1}>
            {displayName}
          </Text>
          <Text style={styles.storeMeta} numberOfLines={1}>
            {formatCount(totalCount)} пластинок
          </Text>
        </View>
        <Text style={styles.headerRight} numberOfLines={1}>
          В наличии · {formatCount(totalCount)}
        </Text>
        <Icon name="caret-right" size={14} color="onBrand" style={{ opacity: 0.65 }} />
      </Pressable>

      {/* Horizontal scroll */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {items.map((item) => (
          <MarketCarouselCard
            key={item.id}
            data={item}
            onPress={onItemPress ? () => onItemPress(item) : undefined}
          />
        ))}

        {/* Terminal «Все N →» card — тоже ведёт на полный магазин */}
        {onStorePress && (
          <Pressable
            onPress={onStorePress}
            accessibilityRole="button"
            accessibilityLabel={`Все ${totalCount} пластинок ${displayName}`}
            style={styles.terminalCard}
          >
            <Text style={styles.terminalCount}>{formatCount(totalCount)}</Text>
            <Text style={styles.terminalLabel}>пластинок</Text>
            <Text style={styles.terminalCta}>Все →</Text>
          </Pressable>
        )}
      </ScrollView>
    </View>
  );
}

function formatCount(n: number): string {
  // 5218 → "5 218" (NBSP)
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

const styles = StyleSheet.create({
  container: {
    marginTop: 8,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 12,
  },
  headerText: {
    flex: 1,
    minWidth: 0,
  },
  storeName: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(15),
    fontWeight: '700',
    color: MarketPalette.chrome.textPrimary,
    letterSpacing: -0.1,
    lineHeight: ms(17),
    includeFontPadding: false,
  },
  storeMeta: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(10.5),
    color: 'rgba(255,255,255,0.6)',
    marginTop: 2,
    includeFontPadding: false,
  },
  headerRight: {
    fontFamily: 'Inter_700Bold',
    fontSize: 10,
    color: 'rgba(255,255,255,0.5)',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
    includeFontPadding: false,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 12,
    gap: 12,
  },
  // Terminal card «Все N →»
  terminalCard: {
    width: 132,
    height: 132,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: 'rgba(255,255,255,0.16)',
    borderRadius: 12,
  },
  terminalCount: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(22),
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: -0.4,
    marginBottom: 2,
    includeFontPadding: false,
  },
  terminalLabel: {
    fontFamily: 'Inter_400Regular',
    fontSize: 10,
    color: 'rgba(255,255,255,0.70)',
    marginBottom: 8,
    includeFontPadding: false,
  },
  terminalCta: {
    fontFamily: 'Inter_700Bold',
    fontSize: 11,
    fontWeight: '700',
    color: '#FFD9C8', // emberSoft
    includeFontPadding: false,
  },
});

export default StoreCarousel;
