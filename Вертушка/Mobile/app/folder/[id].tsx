/**
 * Экран содержимого папки — список пластинок + rename/delete
 */
import { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../components/Header';
import { RecordGrid } from '../../components/RecordGrid';
import { ActionSheet, ActionSheetAction } from '../../components/ui';
import { AddRecordsModal } from '../../components/AddRecordsModal';
import { FolderPickerModal } from '../../components/FolderPickerModal';
import { api } from '../../lib/api';
import { useCollectionStore } from '../../lib/store';
import { Collection, CollectionItem } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

export default function FolderScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [folder, setFolder] = useState<Collection | null>(null);
  const [items, setItems] = useState<CollectionItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showOptions, setShowOptions] = useState(false);
  const [showAddRecords, setShowAddRecords] = useState(false);
  const [showFolderPicker, setShowFolderPicker] = useState(false);

  // Selection mode
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());

  const { renameFolder, deleteFolder, fetchCollections, collectionItems, fetchCollectionItems } = useCollectionStore();

  const loadFolder = useCallback(async () => {
    if (!id) return;
    try {
      const collection = await api.getCollection(id);
      setFolder(collection);
      setItems(collection.items || []);
    } catch {
      Alert.alert('Ошибка', 'Не удалось загрузить папку');
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

  const handleRecordPress = (item: CollectionItem) => {
    const recordId = item.record.discogs_id || item.record.id;
    router.push(`/record/${recordId}?folderId=${id}&folderItemId=${item.id}`);
  };

  const handleRename = () => {
    if (!folder) return;
    Alert.prompt(
      'Переименовать папку',
      'Введите новое название',
      async (name) => {
        if (!name?.trim()) return;
        try {
          await renameFolder(folder.id, name.trim());
          setFolder({ ...folder, name: name.trim() });
        } catch {
          Alert.alert('Ошибка', 'Не удалось переименовать папку');
        }
      },
      'plain-text',
      folder.name,
    );
  };

  const handleDelete = () => {
    if (!folder) return;
    Alert.alert(
      'Удалить папку?',
      `Папка "${folder.name}" будет удалена. Пластинки останутся в вашей коллекции.`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteFolder(folder.id);
              router.back();
            } catch {
              Alert.alert('Ошибка', 'Не удалось удалить папку');
            }
          },
        },
      ],
    );
  };

  const handleRemoveItem = async (item: CollectionItem) => {
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
              await api.removeFromCollection(folder.id, item.id);
              setItems(prev => prev.filter(i => i.id !== item.id));
              setFolder(prev => prev ? { ...prev, items_count: prev.items_count - 1 } : prev);
              await fetchCollections();
            } catch {
              Alert.alert('Ошибка', 'Не удалось убрать из папки');
            }
          },
        },
      ],
    );
  };

  // Selection mode handlers
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
                await api.removeFromCollection(folder.id, itemId);
              }
              setItems(prev => prev.filter(i => !selectedItems.has(i.id)));
              setFolder(prev => prev ? { ...prev, items_count: prev.items_count - itemsToRemove.length } : prev);
              setSelectedItems(new Set());
              setIsSelectionMode(false);
              await fetchCollections();
            } catch {
              Alert.alert('Ошибка', 'Не удалось убрать пластинки');
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

      // Загружаем целевую папку, чтобы не дублировать
      const targetFolder = await api.getCollection(targetFolderId);
      const existingInTarget = new Set(
        (targetFolder.items || []).map((i: CollectionItem) => i.record_id)
      );

      // Добавляем только те, которых нет в целевой папке
      const toAdd = itemsToMove.filter(i => !existingInTarget.has(i.record_id));
      await Promise.all(toAdd.map(item => api.addRecordToFolder(targetFolderId, item.record_id)));

      // Убираем из текущей папки
      await Promise.all(itemsToMove.map(item => api.removeFromCollection(folder.id, item.id)));

      setSelectedItems(new Set());
      setIsSelectionMode(false);
      await loadFolder();
      await fetchCollections();
    } catch {
      Alert.alert('Ошибка', 'Не удалось переместить пластинки');
    }
  };

  const handleOpenAddRecords = async () => {
    // Убедимся что коллекция загружена
    if (collectionItems.length === 0) {
      await fetchCollectionItems();
    }
    setShowAddRecords(true);
  };

  const handleAddSelectedRecords = async (collectionItemIds: string[]) => {
    if (!folder) return;

    // Вычисляем record_id уже в папке
    const existingRecordIds = new Set(items.map(i => i.record_id));

    // Получаем record_id из выбранных items коллекции, дедуплицируя по record_id
    const seen = new Set<string>();
    const toAdd = collectionItems.filter(item => {
      if (!collectionItemIds.includes(item.id)) return false;
      if (existingRecordIds.has(item.record_id)) return false;
      if (seen.has(item.record_id)) return false;
      seen.add(item.record_id);
      return true;
    });

    await Promise.all(toAdd.map(item => api.addRecordToFolder(folder.id, item.record_id)));

    // Обновляем папку и счётчики
    await loadFolder();
    await fetchCollections();
  };

  const getOptionsActions = (): ActionSheetAction[] => [
    {
      label: 'Добавить пластинки',
      icon: 'add-circle-outline',
      onPress: handleOpenAddRecords,
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
          <Ionicons name="alert-circle-outline" size={64} color={Colors.textMuted} />
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
          <Ionicons name="ellipsis-horizontal" size={24} color={Colors.textSecondary} />
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

      <RecordGrid
        data={items}
        cardVariant="expanded"
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
      />

      {/* Selection footer */}
      {isSelectionMode && (
        <View style={styles.selectionFooter}>
          <TouchableOpacity
            style={styles.footerButton}
            onPress={() => setShowFolderPicker(true)}
            disabled={selectedItems.size === 0}
          >
            <Ionicons
              name="folder-outline"
              size={24}
              color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
            />
            <Text
              style={[
                styles.footerButtonText,
                selectedItems.size === 0 && styles.footerButtonTextDisabled,
              ]}
            >
              В папку {selectedItems.size > 0 && `(${selectedItems.size})`}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.footerButton, styles.footerButtonDelete]}
            onPress={handleBulkRemove}
            disabled={selectedItems.size === 0}
          >
            <Ionicons
              name="close-circle-outline"
              size={24}
              color={selectedItems.size > 0 ? Colors.error : Colors.textMuted}
            />
            <Text
              style={[
                styles.footerButtonTextDelete,
                selectedItems.size === 0 && styles.footerButtonTextDisabled,
              ]}
            >
              Убрать {selectedItems.size > 0 && `(${selectedItems.size})`}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      <ActionSheet
        visible={showOptions}
        actions={getOptionsActions()}
        onClose={() => setShowOptions(false)}
      />

      <AddRecordsModal
        visible={showAddRecords}
        onClose={() => setShowAddRecords(false)}
        existingRecordIds={new Set(items.map(i => i.record_id))}
        onAdd={handleAddSelectedRecords}
      />

      <FolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleMoveToFolder}
        selectedRecordIds={items
          .filter(i => selectedItems.has(i.id))
          .map(i => i.record_id)}
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
  selectionFooter: {
    position: 'absolute',
    bottom: 40,
    left: 16,
    right: 16,
    flexDirection: 'row',
    backgroundColor: Colors.glassBg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.md,
    paddingHorizontal: Spacing.md,
    gap: Spacing.md,
    borderRadius: BorderRadius.md,
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
    color: Colors.royalBlue,
  },
  footerButtonTextDelete: {
    ...Typography.buttonSmall,
    color: Colors.error,
  },
  footerButtonTextDisabled: {
    color: Colors.textMuted,
  },
});
