/**
 * AddRecordsModal — выбор пластинок из коллекции для добавления в папку
 * Показывает все пластинки коллекции, уже добавленные — с галочкой и неактивны
 */
import { useState } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { toast } from '../lib/toast';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useCollectionStore } from '../lib/store';
import { CollectionItem } from '../lib/types';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface AddRecordsModalProps {
  visible: boolean;
  onClose: () => void;
  existingRecordIds: Set<string>;
  onAdd: (collectionItemIds: string[]) => Promise<void>;
}

export function AddRecordsModal({
  visible,
  onClose,
  existingRecordIds,
  onAdd,
}: AddRecordsModalProps) {
  const { collectionItems, fetchCollectionItems, isLoading } = useCollectionStore();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isAdding, setIsAdding] = useState(false);
  const insets = useSafeAreaInsets();

  const handleToggle = (itemId: string) => {
    const next = new Set(selectedIds);
    if (next.has(itemId)) {
      next.delete(itemId);
    } else {
      next.add(itemId);
    }
    setSelectedIds(next);
  };

  const handleAdd = async () => {
    if (selectedIds.size === 0) return;
    setIsAdding(true);
    try {
      await onAdd(Array.from(selectedIds));
      setSelectedIds(new Set());
      onClose();
    } catch {
      toast.error('Не удалось добавить пластинки');
    } finally {
      setIsAdding(false);
    }
  };

  const handleClose = () => {
    setSelectedIds(new Set());
    onClose();
  };

  const renderItem = ({ item }: { item: CollectionItem }) => {
    const isInFolder = existingRecordIds.has(item.record_id);
    const isSelected = selectedIds.has(item.id);
    const coverUrl = item.record.cover_image_url || item.record.thumb_image_url;

    return (
      <TouchableOpacity
        style={[styles.row, isInFolder && styles.rowDisabled]}
        onPress={() => {
          if (!isInFolder) handleToggle(item.id);
        }}
        activeOpacity={isInFolder ? 1 : 0.7}
      >
        {coverUrl ? (
          <Image source={coverUrl} style={styles.cover} contentFit="cover" cachePolicy="disk" />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]}>
            <Ionicons name="disc-outline" size={20} color={Colors.textMuted} />
          </View>
        )}

        <View style={styles.info}>
          <Text
            style={[styles.recordTitle, isInFolder && styles.textDisabled]}
            numberOfLines={1}
          >
            {item.record.title}
          </Text>
          <Text
            style={[styles.recordArtist, isInFolder && styles.textDisabled]}
            numberOfLines={1}
          >
            {item.record.artist}
          </Text>
        </View>

        <View style={styles.checkContainer}>
          {isInFolder ? (
            <View style={styles.inFolderBadge}>
              <Ionicons name="checkmark" size={14} color={Colors.textMuted} />
            </View>
          ) : (
            <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
              {isSelected && <Ionicons name="checkmark" size={14} color={Colors.background} />}
            </View>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={handleClose}
    >
      <View style={[styles.container, { paddingTop: insets.top }]}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            onPress={handleClose}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
          >
            <Ionicons name="close" size={24} color={Colors.textSecondary} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Добавить пластинки</Text>
          <View style={{ width: 24 }} />
        </View>

        {/* List */}
        {isLoading ? (
          <View style={styles.centered}>
            <ActivityIndicator size="large" color={Colors.royalBlue} />
          </View>
        ) : collectionItems.length === 0 ? (
          <View style={styles.centered}>
            <Ionicons name="disc-outline" size={48} color={Colors.textMuted} />
            <Text style={styles.emptyText}>Коллекция пуста</Text>
          </View>
        ) : (
          <FlatList
            data={collectionItems}
            keyExtractor={(item) => item.id}
            renderItem={renderItem}
            extraData={existingRecordIds}
            contentContainerStyle={styles.list}
            onRefresh={fetchCollectionItems}
            refreshing={isLoading}
          />
        )}

        {/* Footer */}
        <View style={[styles.footer, { paddingBottom: insets.bottom + Spacing.md }]}>
          <TouchableOpacity
            style={[
              styles.addButton,
              (selectedIds.size === 0 || isAdding) && styles.addButtonDisabled,
            ]}
            onPress={handleAdd}
            disabled={selectedIds.size === 0 || isAdding}
          >
            {isAdding ? (
              <ActivityIndicator size="small" color={Colors.background} />
            ) : (
              <Text style={styles.addButtonText}>
                {selectedIds.size > 0
                  ? `Добавить (${selectedIds.size})`
                  : 'Выберите пластинки'}
              </Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.surface,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.md,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
  },
  list: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.sm,
    paddingBottom: Spacing.lg,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: Colors.surface,
  },
  rowDisabled: {
    opacity: 0.45,
  },
  cover: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
  },
  coverPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  info: {
    flex: 1,
    gap: 2,
  },
  recordTitle: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
  },
  recordArtist: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  textDisabled: {
    color: Colors.textMuted,
  },
  checkContainer: {
    width: 28,
    alignItems: 'center',
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: Colors.textMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxSelected: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  inFolderBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footer: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: Colors.surface,
  },
  addButton: {
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.md,
    alignItems: 'center',
  },
  addButtonDisabled: {
    backgroundColor: Colors.surface,
  },
  addButtonText: {
    ...Typography.button,
    color: Colors.background,
  },
});
