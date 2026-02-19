/**
 * FolderPickerModal — поп-ап выбора папки
 * Горизонтальный скролл карточек + кнопка создания новой папки
 */
import { useState } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Image,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useCollectionStore } from '../lib/store';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

const folderPlaceholder = require('../assets/images/folder-placeholder.png');

interface FolderPickerModalProps {
  visible: boolean;
  onClose: () => void;
  onSelectFolder: (folderId: string) => void;
}

export function FolderPickerModal({ visible, onClose, onSelectFolder }: FolderPickerModalProps) {
  const { folders, createFolder } = useCollectionStore();
  const [isCreating, setIsCreating] = useState(false);

  const handleCreateFolder = () => {
    Alert.prompt(
      'Новая папка',
      'Введите название папки',
      async (name) => {
        if (!name?.trim()) return;
        setIsCreating(true);
        try {
          const folder = await createFolder(name.trim());
          setIsCreating(false);
          onSelectFolder(folder.id);
        } catch {
          setIsCreating(false);
          Alert.alert('Ошибка', 'Не удалось создать папку');
        }
      },
      'plain-text',
    );
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={onClose}>
        <View style={styles.sheet} onStartShouldSetResponder={() => true}>
          {/* Header */}
          <View style={styles.header}>
            <Text style={styles.title}>Выбрать папку</Text>
            <TouchableOpacity onPress={onClose} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
              <Ionicons name="close" size={24} color={Colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Folder cards */}
          {isCreating ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="small" color={Colors.royalBlue} />
            </View>
          ) : (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.scrollContent}
            >
              {/* New folder button */}
              <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateFolder}>
                <View style={styles.newFolderIcon}>
                  <Ionicons name="add" size={32} color={Colors.textMuted} />
                </View>
                <Text style={styles.folderName} numberOfLines={1}>Новая</Text>
              </TouchableOpacity>

              {folders.map(folder => (
                <TouchableOpacity
                  key={folder.id}
                  style={styles.folderCard}
                  onPress={() => onSelectFolder(folder.id)}
                >
                  <Image source={folderPlaceholder} style={styles.folderImage} />
                  <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                  <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: Colors.overlay,
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.lg,
    borderTopRightRadius: BorderRadius.lg,
    paddingBottom: Spacing.xl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
  },
  title: {
    ...Typography.h4,
    color: Colors.deepNavy,
  },
  loadingContainer: {
    height: 130,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollContent: {
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  folderCard: {
    width: 100,
    alignItems: 'center',
    gap: Spacing.xs,
  },
  newFolderCard: {
    width: 100,
    alignItems: 'center',
    gap: Spacing.xs,
  },
  newFolderIcon: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  folderImage: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  folderName: {
    ...Typography.caption,
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
    textAlign: 'center',
  },
  folderCount: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontSize: 11,
  },
});
