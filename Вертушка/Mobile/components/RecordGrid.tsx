/**
 * Сетка пластинок
 */
import React, { memo, useEffect, useRef } from 'react';
import {
  FlatList,
  StyleSheet,
  View,
  Text,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';

// Animated.FlatList — нужно для useAnimatedScrollHandler из родителя
// (Маркет в (tabs)/search.tsx, см. MARKET_AND_PRICE_DRAWER.md §1.3).
const AnimatedFlatList = Animated.createAnimatedComponent(FlatList);
import { Icon } from '@/components/ui';
import { LinearGradient } from 'expo-linear-gradient';
import { RecordCard } from './RecordCard';
import { RecordSearchResult, VinylRecord, CollectionItem, WishlistItem, MasterSearchResult, ReleaseSearchResult } from '../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Gradients, Shadows } from '../constants/theme';
import { RarityContext } from './RarityAura';

export interface EmptyAction {
  label: string;
  icon: string;
  onPress: () => void;
}

type RecordItem = RecordSearchResult | VinylRecord | CollectionItem | WishlistItem | MasterSearchResult | ReleaseSearchResult;

interface RecordGridProps<T extends RecordItem = RecordItem> {
  data: T[];
  onRecordPress?: (record: T) => void;
  onArtistPress?: (artistName: string) => void;
  onAddToCollection?: (record: T) => void;
  onAddToWishlist?: (record: T) => void;
  onRemove?: (record: T) => void;
  showActions?: boolean;
  isLoading?: boolean;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  onEndReached?: () => void;
  emptyMessage?: string;
  emptyTitle?: string;
  emptyIcon?: string;
  emptyActions?: EmptyAction[];
  ListHeaderComponent?: React.ReactElement;
  isSelectionMode?: boolean;
  selectedItems?: Set<string>;
  onToggleItemSelection?: (itemId: string) => void;
  onLongPressItem?: (itemId: string) => void;
  cardVariant?: 'compact' | 'expanded' | 'list';
  numColumns?: number;
  /** Доп. нижний паддинг контента (напр. под sticky-CTA). */
  contentBottomPad?: number;
  /** Drives rarity tier selection — `collection` hides "Популярно". */
  rarityContext?: RarityContext;
  /**
   * Optional onScroll — нужен для magic-transition фона в search.tsx.
   * Передаётся результат useAnimatedScrollHandler из родителя.
   * Тип `any` чтобы не таскать сюда AnimatedScrollHandler-тайпинги Reanimated.
   */
  onScroll?: any;
  scrollEventThrottle?: number;
  /**
   * Контейнер для функции scrollToTop. Родитель кладёт сюда ref и потом
   * вызывает `scrollToTopRef.current?.()` — например, из external scroll-to-top affordance.
   * Не используем forwardRef из-за TS-сложностей с дженериками.
   */
  scrollToTopRef?: React.MutableRefObject<(() => void) | null>;
  /**
   * Тот же паттерн что scrollToTopRef, но для произвольного offset.
   * Используется в search.tsx для «Смотреть все →» в карусели маркета:
   * родитель измеряет y-позицию MarketSection и просит RecordGrid
   * проскроллить туда с анимацией.
   */
  scrollToOffsetRef?: React.MutableRefObject<((offset: number, animated?: boolean) => void) | null>;
  /**
   * Per-record HotStock summary map (discogs_id → {variant, price}).
   * Передаётся из родителя после `api.getOffersSummary([...discogs_ids])`.
   * RecordGrid пробрасывает каждой карточке через RecordCard.hotStock prop.
   */
  hotStockMap?: Map<string, { variant: any; price: number } | null>;
  /**
   * Опциональный wrapper вокруг каждой строки (например, Swipeable для wishlist).
   * Получает item и уже отрендеренный RecordCard, возвращает обёрнутый ReactElement.
   * Используется в collection.tsx wishlist+list для swipe-to-offers паттерна.
   */
  rowWrapper?: (item: T, child: React.ReactElement) => React.ReactElement;
  /**
   * Wishlist tile/list badge-режим — см. RecordCard.useOfferBadge.
   * Включает corner-плашку «В ПРОДАЖЕ»/«ЕСТЬ АНАЛОГ» + рамку для expanded
   * и AltBadge для altVersion в list.
   */
  useOfferBadge?: boolean;
}

function RecordGridComponent<T extends RecordItem = RecordItem>({
  data,
  onRecordPress,
  onArtistPress,
  onAddToCollection,
  onAddToWishlist,
  onRemove,
  showActions = false,
  isLoading = false,
  isRefreshing = false,
  onRefresh,
  onEndReached,
  emptyMessage = 'Пластинок пока нет',
  emptyTitle,
  emptyIcon,
  emptyActions,
  ListHeaderComponent,
  isSelectionMode = false,
  selectedItems = new Set(),
  onToggleItemSelection,
  onLongPressItem,
  cardVariant = 'expanded',
  numColumns = 2,
  contentBottomPad,
  rarityContext = 'search',
  onScroll,
  scrollEventThrottle = 16,
  scrollToTopRef,
  scrollToOffsetRef,
  hotStockMap,
  rowWrapper,
  useOfferBadge = false,
}: RecordGridProps<T>) {
  // Internal ref для scrollToOffset вызова (search.tsx, market navigation).
  // Populate переданного scrollToTopRef один раз на mount.
  const listRef = useRef<FlatList<T>>(null);
  useEffect(() => {
    if (!scrollToTopRef) return;
    scrollToTopRef.current = () => {
      listRef.current?.scrollToOffset({ offset: 0, animated: true });
    };
    return () => {
      if (scrollToTopRef) scrollToTopRef.current = null;
    };
  }, [scrollToTopRef]);
  // Аналогично для произвольного offset (используется search.tsx «Смотреть все»).
  useEffect(() => {
    if (!scrollToOffsetRef) return;
    scrollToOffsetRef.current = (offset, animated = true) => {
      listRef.current?.scrollToOffset({ offset, animated });
    };
    return () => {
      if (scrollToOffsetRef) scrollToOffsetRef.current = null;
    };
  }, [scrollToOffsetRef]);
  // Извлекаем запись из разных типов
  const getRecord = (item: RecordItem): RecordSearchResult | VinylRecord | MasterSearchResult | ReleaseSearchResult => {
    if ('record' in item) {
      return item.record;
    }
    return item;
  };

  const renderItem = ({ item, index }: { item: T; index: number }) => {
    const record = getRecord(item);
    const itemId = 'id' in item ? item.id : '';
    const isSelected = isSelectionMode && selectedItems.has(itemId);
    const isBooked = 'is_booked' in item && item.is_booked === true;

    const card = (
      <RecordCard
        record={record}
        variant={cardVariant}
        onPress={onRecordPress ? () => onRecordPress(item) : undefined}
        onArtistPress={onArtistPress}
        onAddToCollection={
          onAddToCollection ? () => onAddToCollection(item) : undefined
        }
        onAddToWishlist={
          onAddToWishlist ? () => onAddToWishlist(item) : undefined
        }
        onRemove={onRemove ? () => onRemove(item) : undefined}
        showActions={showActions && !isSelectionMode}
        isSelectionMode={isSelectionMode}
        isSelected={isSelected}
        onToggleSelection={
          onToggleItemSelection && itemId
            ? () => onToggleItemSelection(itemId)
            : undefined
        }
        onLongPress={
          onLongPressItem && itemId
            ? () => onLongPressItem(itemId)
            : undefined
        }
        isBooked={isBooked}
        rarityContext={rarityContext}
        noRarityAura={numColumns >= 2}
        hotStock={
          hotStockMap && 'discogs_id' in record && record.discogs_id
            ? hotStockMap.get(record.discogs_id) ?? undefined
            : undefined
        }
        useOfferBadge={useOfferBadge}
      />
    );

    const wrapped = rowWrapper ? rowWrapper(item, card) : card;

    return (
      <Animated.View entering={FadeInUp.delay(index * 50).duration(300)}>
        {wrapped}
      </Animated.View>
    );
  };

  const renderEmpty = () => {
    if (isLoading || !emptyMessage) return null;

    const hasRich = !!(emptyTitle || emptyIcon || (emptyActions && emptyActions.length > 0));

    if (!hasRich) {
      return (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>{emptyMessage}</Text>
        </View>
      );
    }

    return (
      <View style={styles.emptyContainer}>
        {emptyIcon && (
          <View style={styles.emptyIconRing}>
            <Icon name={emptyIcon} size={36} color={Colors.royalBlue} />
          </View>
        )}
        {emptyTitle && <Text style={styles.emptyTitle}>{emptyTitle}</Text>}
        <Text style={styles.emptyText}>{emptyMessage}</Text>
        {emptyActions && emptyActions.length > 0 && (
          <View style={styles.emptyActions}>
            {emptyActions.map((action, i) => {
              const isPrimary = i === 0;
              if (isPrimary) {
                return (
                  <TouchableOpacity
                    key={action.label}
                    onPress={action.onPress}
                    activeOpacity={0.85}
                  >
                    <LinearGradient
                      colors={Gradients.blue as [string, string]}
                      start={{ x: 0, y: 0 }}
                      end={{ x: 1, y: 0 }}
                      style={[styles.emptyPrimaryBtn, Shadows.sm]}
                    >
                      <Icon name={action.icon} size={18} color={Colors.background} />
                      <Text style={styles.emptyPrimaryText}>{action.label}</Text>
                    </LinearGradient>
                  </TouchableOpacity>
                );
              }
              return (
                <TouchableOpacity
                  key={action.label}
                  style={styles.emptySecondaryBtn}
                  onPress={action.onPress}
                  activeOpacity={0.7}
                >
                  <Icon name={action.icon} size={18} color={Colors.royalBlue} />
                  <Text style={styles.emptySecondaryText}>{action.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  const renderFooter = () => {
    if (!isLoading || data.length === 0) return null;
    
    return (
      <View style={styles.footer}>
        <ActivityIndicator color={Colors.royalBlue} />
      </View>
    );
  };

  const keyExtractor = (item: T, index: number) => {
    if ('id' in item) return item.id;
    const record = getRecord(item);
    if ('discogs_id' in record && record.discogs_id) return record.discogs_id;
    if ('master_id' in record && record.master_id) return record.master_id;
    if ('release_id' in record && record.release_id) return record.release_id;
    return index.toString();
  };

  return (
    <AnimatedFlatList
      ref={listRef as any}
      data={data}
      renderItem={renderItem as any}
      keyExtractor={keyExtractor as any}
      numColumns={numColumns}
      columnWrapperStyle={numColumns > 1 ? styles.row : undefined}
      contentContainerStyle={[
        styles.container,
        contentBottomPad != null && { paddingBottom: contentBottomPad },
      ]}
      // Transparent — чтобы absolute MarketBackground в родителе search.tsx
      // был виден сквозь FlatList. Без этого FlatList перекрывает фон белым
      // и magic-transition не виден визуально.
      style={styles.transparent}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      ListHeaderComponent={ListHeaderComponent}
      ListEmptyComponent={renderEmpty}
      ListFooterComponent={renderFooter}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.5}
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      refreshControl={
        onRefresh ? (
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={Colors.royalBlue}
          />
        ) : undefined
      }
    />
  );
}

const styles = StyleSheet.create({
  container: {
    padding: Spacing.md,
    paddingTop: Spacing.sm,
  },
  transparent: {
    backgroundColor: 'transparent',
  },
  row: {
    justifyContent: 'space-between',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.xxl,
    gap: Spacing.sm,
  },
  emptyIconRing: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  emptyTitle: {
    ...Typography.h3,
    color: Colors.text,
    textAlign: 'center',
    letterSpacing: -0.5,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
    maxWidth: 320,
  },
  emptyActions: {
    flexDirection: 'row',
    gap: Spacing.sm,
    marginTop: Spacing.lg,
    flexWrap: 'wrap',
    justifyContent: 'center',
  },
  emptyPrimaryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 14,
    borderRadius: BorderRadius.full,
  },
  emptyPrimaryText: {
    ...Typography.bodyBold,
    color: Colors.background,
    fontSize: 15,
  },
  emptySecondaryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    paddingHorizontal: Spacing.lg,
    paddingVertical: 14,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptySecondaryText: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
    fontSize: 15,
  },
  footer: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
});

export const RecordGrid = memo(RecordGridComponent) as typeof RecordGridComponent;
export default RecordGrid;
