/**
 * Экран коллекции с переключателем Моё / Хочу
 */
import { useEffect, useCallback, useState } from 'react';
import { View, StyleSheet, Alert, TouchableOpacity, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../components/Header';
import { RecordGrid } from '../../components/RecordGrid';
import { SegmentedControl } from '../../components/ui';
import { useCollectionStore } from '../../lib/store';
import { api } from '../../lib/api';
import { CollectionItem, WishlistItem, CollectionTab } from '../../lib/types';
import { Colors, Spacing, Typography, BorderRadius } from '../../constants/theme';

const SEGMENTS: { key: CollectionTab; label: string }[] = [
  { key: 'collection', label: 'Моё' },
  { key: 'wishlist', label: 'Хочу' },
];

export default function CollectionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);

  const {
    activeTab,
    collectionItems,
    wishlistItems,
    isLoading,
    setActiveTab,
    fetchCollections,
    fetchCollectionItems,
    fetchWishlistItems,
    removeFromCollection,
    removeFromWishlist,
    moveToCollection,
  } = useCollectionStore();

  // Загрузка данных при монтировании
  useEffect(() => {
    fetchCollections().then(() => {
      fetchCollectionItems();
      fetchWishlistItems();
    });
  }, []);

  // Сброс режима выбора при смене вкладки
  useEffect(() => {
    setIsSelectionMode(false);
    setSelectedItems(new Set());
  }, [activeTab]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (activeTab === 'collection') {
        await fetchCollectionItems();
      } else {
        await fetchWishlistItems();
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [activeTab, fetchCollectionItems, fetchWishlistItems]);

  const handleRecordPress = (item: CollectionItem | WishlistItem) => {
    // Предпочитаем discogs_id для навигации, если он есть
    const recordId = item.record.discogs_id || item.record.id;
    router.push(`/record/${recordId}`);
  };

  const handleArtistPress = useCallback(async (artistName: string) => {
    try {
      // Ищем артиста по имени
      const response = await api.searchArtists(artistName, 1, 5);

      if (response.results.length > 0) {
        // Берем первый результат и переходим на страницу артиста
        const artist = response.results[0];
        router.push(`/artist/${artist.artist_id}`);
      } else {
        Alert.alert('Артист не найден', `Не удалось найти артиста "${artistName}"`);
      }
    } catch (error: any) {
      console.error('Ошибка поиска артиста:', error);
      Alert.alert('Ошибка', 'Не удалось найти артиста');
    }
  }, [router]);

  const handleRemoveFromCollection = async (item: CollectionItem) => {
    Alert.alert(
      'Удалить из коллекции?',
      `"${item.record.title}" будет удалена из вашей коллекции`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              // Передаем item.id (ID конкретного элемента CollectionItem)
              await removeFromCollection(item.id);
            } catch (error) {
              Alert.alert('Ошибка', 'Не удалось удалить из коллекции');
            }
          },
        },
      ]
    );
  };

  const handleRemoveFromWishlist = async (item: WishlistItem) => {
    Alert.alert(
      'Удалить из списка?',
      `"${item.record.title}" будет удалена из списка желаний`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              // Для вишлиста API ожидает WishlistItem.id, не record_id
              await removeFromWishlist(item.id);
            } catch (error) {
              Alert.alert('Ошибка', 'Не удалось удалить из списка');
            }
          },
        },
      ]
    );
  };

  const handleMoveToCollection = async (item: WishlistItem) => {
    Alert.alert(
      'Купил!',
      `Перенести "${item.record.title}" в коллекцию?`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Перенести',
          onPress: async () => {
            try {
              await moveToCollection(item.id);
              Alert.alert('Готово!', 'Пластинка добавлена в коллекцию');
            } catch (error) {
              Alert.alert('Ошибка', 'Не удалось перенести в коллекцию');
            }
          },
        },
      ]
    );
  };


  // Режим выбора
  const handleToggleSelectionMode = () => {
    setIsSelectionMode(!isSelectionMode);
    setSelectedItems(new Set());
  };

  const handleToggleItemSelection = (itemId: string) => {
    const newSelected = new Set(selectedItems);
    if (newSelected.has(itemId)) {
      newSelected.delete(itemId);
    } else {
      newSelected.add(itemId);
    }
    setSelectedItems(newSelected);
  };

  const handleSelectAll = () => {
    const data = (activeTab === 'collection' ? collectionItems : wishlistItems) as (CollectionItem | WishlistItem)[];
    if (selectedItems.size === data.length && data.length > 0) {
      setSelectedItems(new Set());
    } else {
      setSelectedItems(new Set(data.map((item) => item.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedItems.size === 0) return;

    const count = selectedItems.size;
    const itemType = activeTab === 'collection' ? 'коллекции' : 'списка желаний';

    Alert.alert(
      'Удалить выбранные?',
      `Будет удалено ${count} пластинок из ${itemType}`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              const itemsToDelete = Array.from(selectedItems);
              for (const itemId of itemsToDelete) {
                if (activeTab === 'collection') {
                  // Передаем itemId напрямую (ID элемента CollectionItem)
                  await removeFromCollection(itemId);
                } else {
                  await removeFromWishlist(itemId);
                }
              }
              setSelectedItems(new Set());
              setIsSelectionMode(false);
            } catch (error) {
              Alert.alert('Ошибка', 'Не удалось удалить выбранные пластинки');
            }
          },
        },
      ]
    );
  };

  const handleBulkMoveToCollection = async () => {
    if (selectedItems.size === 0 || activeTab !== 'wishlist') return;

    const count = selectedItems.size;

    Alert.alert(
      'Перенести в коллекцию?',
      `Будет перенесено ${count} пластинок в коллекцию`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Перенести',
          onPress: async () => {
            try {
              const itemsToMove = Array.from(selectedItems);
              for (const itemId of itemsToMove) {
                await moveToCollection(itemId);
              }
              setSelectedItems(new Set());
              setIsSelectionMode(false);
            } catch (error) {
              Alert.alert('Ошибка', 'Не удалось перенести пластинки');
            }
          },
        },
      ]
    );
  };


  const data = (activeTab === 'collection' ? collectionItems : wishlistItems) as (CollectionItem | WishlistItem)[];

  const SegmentHeader = (
    <View style={styles.segmentContainer}>
      <SegmentedControl
        segments={SEGMENTS}
        selectedKey={activeTab}
        onSelect={setActiveTab}
        disabled={isSelectionMode}
      />
    </View>
  );

  const rightAction = isSelectionMode ? (
    <TouchableOpacity style={styles.headerButton} onPress={handleToggleSelectionMode}>
      <Text style={styles.cancelButtonText}>Отмена</Text>
    </TouchableOpacity>
  ) : (
    <TouchableOpacity style={styles.headerButtonPrimary} onPress={handleToggleSelectionMode}>
      <Text style={styles.selectButtonText}>Выбрать</Text>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <Header title="Коллекция" rightAction={rightAction} />

      <RecordGrid
        data={data}
        onRecordPress={isSelectionMode ? undefined : handleRecordPress}
        onArtistPress={isSelectionMode ? undefined : handleArtistPress}
        onRemove={
          (activeTab === 'collection' ? handleRemoveFromCollection : handleRemoveFromWishlist) as any
        }
        showActions={false}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        emptyMessage={
          activeTab === 'collection'
            ? 'Ваша коллекция пуста.\nОтсканируйте или найдите пластинку, чтобы добавить.'
            : 'Список желаний пуст.\nДобавьте пластинки, которые хотите приобрести.'
        }
        ListHeaderComponent={isSelectionMode ? undefined : SegmentHeader}
        isSelectionMode={isSelectionMode}
        selectedItems={selectedItems}
        onToggleItemSelection={handleToggleItemSelection}
      />

      {/* Нижний подвал в режиме выбора */}
      {isSelectionMode && (
        <View
          style={[
            styles.selectionFooter,
            { paddingBottom: insets.bottom + Spacing.md },
          ]}
        >
          {activeTab === 'wishlist' && (
            <TouchableOpacity
              style={styles.footerButton}
              onPress={handleBulkMoveToCollection}
              disabled={selectedItems.size === 0}
            >
              <Ionicons
                name="arrow-forward-circle"
                size={24}
                color={selectedItems.size > 0 ? Colors.primary : Colors.textMuted}
              />
              <Text
                style={[
                  styles.footerButtonText,
                  selectedItems.size === 0 && styles.footerButtonTextDisabled,
                ]}
              >
                В коллекцию {selectedItems.size > 0 && `(${selectedItems.size})`}
              </Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[styles.footerButton, styles.footerButtonDelete]}
            onPress={handleBulkDelete}
            disabled={selectedItems.size === 0}
          >
            <Ionicons
              name="trash-outline"
              size={24}
              color={selectedItems.size > 0 ? Colors.error : Colors.textMuted}
            />
            <Text
              style={[
                styles.footerButtonText,
                selectedItems.size === 0 && styles.footerButtonTextDisabled,
              ]}
            >
              Удалить {selectedItems.size > 0 && `(${selectedItems.size})`}
            </Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  segmentContainer: {
    paddingBottom: Spacing.md,
  },
  headerButton: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  headerButtonPrimary: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.primary,
  },
  selectButtonText: {
    ...Typography.buttonSmall,
    color: Colors.background,
  },
  cancelButtonText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },
  selectionFooter: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    backgroundColor: Colors.background,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    paddingTop: Spacing.md,
    paddingHorizontal: Spacing.md,
    gap: Spacing.md,
  },
  footerButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  footerButtonDelete: {
    backgroundColor: Colors.surface,
  },
  footerButtonText: {
    ...Typography.buttonSmall,
    color: Colors.primary,
  },
  footerButtonTextDisabled: {
    color: Colors.textMuted,
  },
});
