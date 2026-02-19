/**
 * Сетка пластинок
 */
import React from 'react';
import {
  FlatList,
  StyleSheet,
  View,
  Text,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';
import { RecordCard } from './RecordCard';
import { RecordSearchResult, VinylRecord, CollectionItem, WishlistItem, MasterSearchResult, ReleaseSearchResult } from '../lib/types';
import { Colors, Typography, Spacing } from '../constants/theme';

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
  ListHeaderComponent?: React.ReactElement;
  isSelectionMode?: boolean;
  selectedItems?: Set<string>;
  onToggleItemSelection?: (itemId: string) => void;
  cardVariant?: 'compact' | 'expanded';
}

export function RecordGrid<T extends RecordItem = RecordItem>({
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
  ListHeaderComponent,
  isSelectionMode = false,
  selectedItems = new Set(),
  onToggleItemSelection,
  cardVariant = 'expanded',
}: RecordGridProps<T>) {
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

    return (
      <Animated.View entering={FadeInUp.delay(index * 50).duration(300)}>
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
          isBooked={isBooked}
        />
      </Animated.View>
    );
  };

  const renderEmpty = () => {
    if (isLoading || !emptyMessage) return null;

    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyText}>{emptyMessage}</Text>
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
    <FlatList
      data={data}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      numColumns={2}
      columnWrapperStyle={styles.row}
      contentContainerStyle={styles.container}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      ListHeaderComponent={ListHeaderComponent}
      ListEmptyComponent={renderEmpty}
      ListFooterComponent={renderFooter}
      onEndReached={onEndReached}
      onEndReachedThreshold={0.5}
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
  row: {
    justifyContent: 'space-between',
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xxl,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
  },
  footer: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
});

export default RecordGrid;
