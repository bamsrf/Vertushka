/**
 * Экран содержимого папки вишлиста — список пластинок + rename/delete
 * Папка — это тег: WishlistItem остаётся источником правды, бронь не страдает
 */
import { useEffect, useState, useCallback } from 'react';
import * as Haptics from 'expo-haptics';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Icon } from '@/components/ui';
import { Header } from '../../components/Header';
import { RecordGrid } from '../../components/RecordGrid';
import { ZoomableRecordGrid } from '../../components/ZoomableRecordGrid';
import { ActionSheet, ActionSheetAction } from '../../components/ui';
import { AddWishlistItemsModal } from '../../components/AddWishlistItemsModal';
import { WishlistFolderPickerModal } from '../../components/WishlistFolderPickerModal';
import { api } from '../../lib/api';
import { useCollectionStore } from '../../lib/store';
import { WishlistFolder, WishlistItem } from '../../lib/types';
import { Colors, Typography, Spacing } from '../../constants/theme';
import { toast } from '../../lib/toast';
import { promptText } from '../../lib/promptCompat';

import { SelectionFooter } from '../../components/SelectionFooter';
export default function WishlistFolderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [folder, setFolder] = useState<WishlistFolder | null>(null);
  const [items, setItems] = useState<WishlistItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [showAddItems, setShowAddItems] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);

  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  const {
    renameWishlistFolder,
    deleteWishlistFolder,
    addItemsToWishlistFolder,
    fetchWishlistFolders,
    wishlistItems,
    fetchWishlistItems,
  } = useCollectionStore();

  const loadFolder = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.getWishlistFolder(id);
      setFolder(data);
      setItems(data.items || []);
    } catch {
      toast.error('Не удалось загрузить папку');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadFolder();
  }, [loadFolder]);

  useFocusEffect(
    useCallback(() => {
      if (!isLoading) {
        loadFolder();
      }
    }, [loadFolder])
  );

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await loadFolder();
    setIsRefreshing(false);
  }, [loadFolder]);

  const handleRecordPress = (item: WishlistItem) => {
    const recordId = item.record.discogs_id || item.record.id;
    router.push(`/record/${recordId}`);
  };

  const handleRename = async () => {
    if (!folder) return;
    const name = await promptText({
      title: 'Переименовать папку',
      message: 'Введите новое название',
      defaultValue: folder.name,
    });
    if (!name?.trim()) return;
    try {
      await renameWishlistFolder(folder.id, name.trim());
      setFolder({ ...folder, name: name.trim() });
    } catch {
      toast.error('Не удалось переименовать папку');
    }
  };

  const handleDelete = () => {
    if (!folder) return;
    Alert.alert(
      'Удалить папку?',
      `Папка "${folder.name}" будет удалена. Пластинки останутся в вашем вишлисте.`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteWishlistFolder(folder.id);
              router.back();
            } catch {
              toast.error('Не удалось удалить папку');
            }
          },
        },
      ],
    );
  };

  const handleRemoveItem = async (item: WishlistItem) => {
    if (!folder) return;
    Alert.alert(
      'Убрать из папки?',
      `"${item.record.title}" будет убрана из папки "${folder.name}"`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Убрать',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.removeItemFromWishlistFolder(folder.id, item.id);
              setItems(prev => prev.filter(i => i.id !== item.id));
              setFolder(prev => prev ? { ...prev, items_count: prev.items_count - 1 } : prev);
              await fetchWishlistFolders();
            } catch {
              toast.error('Не удалось убрать из папки');
            }
          },
        },
      ],
    );
  };

  const handleToggleSelectionMode = () => {
    setIsSelectionMode(!isSelectionMode);
    setSelectedItems(new Set());
  };

  const handleLongPressItem = (itemId: string) => {
    if (!isSelectionMode) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      setIsSelectionMode(true);
      setSelectedItems(new Set([itemId]));
    }
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

  const handleBulkRemove = async () => {
    if (!folder || selectedItems.size === 0) return;

    Alert.alert(
      'Убрать из папки?',
      `${selectedItems.size} пластинок будет убрано из папки`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Убрать',
          style: 'destructive',
          onPress: async () => {
            try {
              const itemsToRemove = Array.from(selectedItems);
              for (const itemId of itemsToRemove) {
                await api.removeItemFromWishlistFolder(folder.id, itemId);
              }
              setItems(prev => prev.filter(i => !selectedItems.has(i.id)));
              setFolder(prev => prev ? { ...prev, items_count: prev.items_count - itemsToRemove.length } : prev);
              setSelectedItems(new Set());
              setIsSelectionMode(false);
              await fetchWishlistFolders();
            } catch {
              toast.error('Не удалось убрать пластинки');
            }
          },
        },
      ],
    );
  };

  const handleMoveToFolder = async (targetFolderId: string) => {
    if (!folder) return;
    setShowFolderPicker(false);

    try {
      const itemsToMove = items.filter(i => selectedItems.has(i.id));

      await addItemsToWishlistFolder(targetFolderId, itemsToMove.map(i => i.id));
      await Promise.all(
        itemsToMove.map(item => api.removeItemFromWishlistFolder(folder.id, item.id))
      );

      setSelectedItems(new Set());
      setIsSelectionMode(false);
      await loadFolder();
      await fetchWishlistFolders();
    } catch {
      toast.error('Не удалось переместить пластинки');
    }
  };

  const handleOpenAddItems = async () => {
    if (wishlistItems.length === 0) {
      await fetchWishlistItems();
    }
    setShowAddItems(true);
  };

  const handleAddSelectedItems = async (wishlistItemIds: string[]) => {
    if (!folder) return;
    await addItemsToWishlistFolder(folder.id, wishlistItemIds);
    await loadFolder();
  };

  const getOptionsActions = (): ActionSheetAction[] => [
    {
      label: 'Добавить пластинки',
      icon: 'add-circle-outline',
      onPress: handleOpenAddItems,
    },
    {
      label: 'Переименовать папку',
      icon: 'pencil-outline',
      onPress: handleRename,
    },
    {
      label: 'Удалить папку',
      icon: 'trash-outline',
      onPress: handleDelete,
      destructive: true,
    },
  ];

  if (isLoading) {
    return (
      <View style={styles.container}>
        <Header title="Папка" showBack showProfile={false} />
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
        </View>
      </View>
    );
  }

  if (!folder) {
    return (
      <View style={styles.container}>
        <Header title="Ошибка" showBack showProfile={false} />
        <View style={styles.centered}>
          <Icon name="alert-circle-outline" size={64} color={Colors.textMuted} />
          <Text style={styles.errorText}>Папка не найдена</Text>
        </View>
      </View>
    );
  }

  const FolderHeader = (
    <View style={styles.headerContent}>
      <View style={styles.titleRow}>
        <Text style={styles.folderTitle}>{folder.name}</Text>
        <TouchableOpacity
          style={styles.optionsButton}
          onPress={() => setShowOptions(true)}
        >
          <Icon name="ellipsis-horizontal" size={24} color={Colors.textSecondary} />
        </TouchableOpacity>
      </View>
      <Text style={styles.itemCount}>
        {folder.items_count} {folder.items_count === 1 ? 'пластинка' : 'пл.'}
      </Text>

      {!isSelectionMode && items.length > 0 && (
        <TouchableOpacity style={styles.selectButton} onPress={handleToggleSelectionMode}>
          <Text style={styles.selectButtonText}>Выбрать</Text>
        </TouchableOpacity>
      )}

      {isSelectionMode && (
        <TouchableOpacity style={styles.cancelButton} onPress={handleToggleSelectionMode}>
          <Text style={styles.cancelButtonText}>Отмена</Text>
        </TouchableOpacity>
      )}
    </View>
  );

  return (
    <View style={styles.container}>
      <Header title="" showBack showProfile={false} />

      {items.length > 0 ? (
        <ZoomableRecordGrid
          data={items}
          rarityContext="wishlist"
          onRecordPress={isSelectionMode ? undefined : (item) => handleRecordPress(item as WishlistItem)}
          onLongPress={handleLongPressItem}
          isSelectionMode={isSelectionMode}
          selectedItems={selectedItems}
          onToggleItemSelection={handleToggleItemSelection}
          isRefreshing={isRefreshing}
          onRefresh={handleRefresh}
          ListHeaderComponent={FolderHeader}
        />
      ) : (
        <RecordGrid
          data={items}
          cardVariant="expanded"
          rarityContext="wishlist"
          onRecordPress={isSelectionMode ? undefined : handleRecordPress}
          onRemove={handleRemoveItem}
          showActions={false}
          isLoading={false}
          isRefreshing={isRefreshing}
          onRefresh={handleRefresh}
          emptyMessage="В этой папке пока нет пластинок."
          ListHeaderComponent={FolderHeader}
          isSelectionMode={isSelectionMode}
          selectedItems={selectedItems}
          onToggleItemSelection={handleToggleItemSelection}
          onLongPressItem={handleLongPressItem}
        />
      )}

      {isSelectionMode && (
        <SelectionFooter
          bottom={40}
          selectedCount={selectedItems.size}
          actions={[
            {
              key: 'move',
              icon: 'folder-outline',
              label: 'В папку',
              onPress: () => setShowFolderPicker(true),
            },
            {
              key: 'remove',
              icon: 'close-circle-outline',
              label: 'Убрать',
              onPress: handleBulkRemove,
              destructive: true,
            },
          ]}
        />
      )}

      <ActionSheet
        visible={showOptions}
        actions={getOptionsActions()}
        onClose={() => setShowOptions(false)}
      />

      <AddWishlistItemsModal
        visible={showAddItems}
        onClose={() => setShowAddItems(false)}
        existingWishlistItemIds={new Set(items.map(i => i.id))}
        onAdd={handleAddSelectedItems}
      />

      <WishlistFolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleMoveToFolder}
        selectedWishlistItemIds={items
          .filter(i => selectedItems.has(i.id))
          .map(i => i.id)}
        excludeFolderId={folder?.id}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.lg,
  },
  errorText: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginTop: Spacing.md,
  },
  headerContent: {
    paddingBottom: Spacing.md,
  },
  titleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.xs,
  },
  folderTitle: {
    ...Typography.h1,
    color: Colors.deepNavy,
    flex: 1,
  },
  optionsButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  itemCount: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    marginBottom: Spacing.md,
  },
  selectButton: {
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: 20,
    backgroundColor: Colors.surface,
  },
  selectButtonText: {
    ...Typography.buttonSmall,
    color: Colors.royalBlue,
  },
  cancelButton: {
    alignSelf: 'flex-start',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: 20,
    backgroundColor: Colors.surface,
  },
  cancelButtonText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },
});
