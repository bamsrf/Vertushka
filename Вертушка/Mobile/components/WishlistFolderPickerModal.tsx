/**
 * WishlistFolderPickerModal — поп-ап выбора папки в вишлисте
 * Горизонтальный скролл карточек + кнопка создания новой папки
 * Показывает галочку на папках, где уже лежат выбранные WishlistItem'ы
 */
import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  Animated,
  Easing,
} from 'react-native';
import { toast } from '../lib/toast';
import { Icon } from '@/components/ui';
import { useCollectionStore } from '../lib/store';
import { api } from '../lib/api';
import { FolderIcon } from './FolderIcon';
import { Colors, Spacing, Typography, BorderRadius } from '../constants/theme';

interface WishlistFolderPickerModalProps {
  visible: boolean;
  onClose: () => void;
  onSelectFolder: (folderId: string) => void;
  /** id WishlistItem'ов, которые добавляем/переносим — для галочки на папках */
  selectedWishlistItemIds?: string[];
  /** ID папки, которую скрыть из списка (текущая папка при переносе) */
  excludeFolderId?: string;
}

export function WishlistFolderPickerModal({
  visible,
  onClose,
  onSelectFolder,
  selectedWishlistItemIds,
  excludeFolderId,
}: WishlistFolderPickerModalProps) {
  const { wishlistFolders, createWishlistFolder } = useCollectionStore();
  const [isCreating, setIsCreating] = useState(false);
  const [folderItemIds, setFolderItemIds] = useState<Record<string, Set<string>>>({});

  // Кастомная анимация: фон фейдится, лист выезжает снизу.
  // animationType="slide" тянул вместе с листом и затемнение — выглядело коряво.
  const [mounted, setMounted] = useState(visible);
  const progress = useRef(new Animated.Value(0)).current;
  const sheetHeight = useRef(0);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(progress, {
        toValue: 1,
        duration: 260,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }).start();
    } else if (mounted) {
      Animated.timing(progress, {
        toValue: 0,
        duration: 200,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (finished) setMounted(false);
      });
    }
  }, [visible]);

  const visibleFolders = wishlistFolders.filter(f => f.id !== excludeFolderId);

  useEffect(() => {
    if (!visible || !selectedWishlistItemIds?.length || visibleFolders.length === 0) return;

    let cancelled = false;

    Promise.all(
      visibleFolders.map(async folder => {
        try {
          const data = await api.getWishlistFolder(folder.id);
          return {
            id: folder.id,
            itemIds: new Set((data.items || []).map(i => i.id)),
          };
        } catch {
          return { id: folder.id, itemIds: new Set<string>() };
        }
      })
    ).then(results => {
      if (cancelled) return;
      const map: Record<string, Set<string>> = {};
      results.forEach(r => { map[r.id] = r.itemIds; });
      setFolderItemIds(map);
    });

    return () => { cancelled = true; };
  }, [visible, wishlistFolders.length]);

  useEffect(() => {
    if (!visible) setFolderItemIds({});
  }, [visible]);

  const folderHasSelected = (folderId: string): boolean => {
    if (!selectedWishlistItemIds?.length) return false;
    const itemIds = folderItemIds[folderId];
    if (!itemIds) return false;
    return selectedWishlistItemIds.some(id => itemIds.has(id));
  };

  const handleCreateFolder = () => {
    Alert.prompt(
      'Новая папка',
      'Введите название папки',
      async (name) => {
        if (!name?.trim()) return;
        setIsCreating(true);
        try {
          const folder = await createWishlistFolder(name.trim());
          setIsCreating(false);
          onSelectFolder(folder.id);
        } catch {
          setIsCreating(false);
          toast.error('Не удалось создать папку');
        }
      },
      'plain-text',
    );
  };

  const translateY = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [sheetHeight.current || 400, 0],
  });

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={onClose}
    >
      <Animated.View style={[styles.overlay, { opacity: progress }]}>
        <TouchableOpacity style={styles.overlayTouch} activeOpacity={1} onPress={onClose} />
        <Animated.View
          style={[styles.sheet, { transform: [{ translateY }] }]}
          onStartShouldSetResponder={() => true}
          onLayout={(e) => { sheetHeight.current = e.nativeEvent.layout.height; }}
        >
          <View style={styles.header}>
            <Text style={styles.title}>Выбрать папку</Text>
            <TouchableOpacity onPress={onClose} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
              <Icon name="close" size={24} color={Colors.textSecondary} />
            </TouchableOpacity>
          </View>

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
              <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateFolder}>
                <FolderIcon size={80} variant="new" />
                <Text style={styles.folderName} numberOfLines={1}>Новая</Text>
              </TouchableOpacity>

              {visibleFolders.map(folder => {
                const hasOverlap = folderHasSelected(folder.id);
                return (
                  <TouchableOpacity
                    key={folder.id}
                    style={styles.folderCard}
                    onPress={() => onSelectFolder(folder.id)}
                  >
                    <View style={styles.imageWrapper}>
                      <FolderIcon
                        size={80}
                        variant={folder.items_count > 0 ? 'filled' : 'empty'}
                      />
                      {hasOverlap && (
                        <View style={styles.checkBadge}>
                          <Icon name="checkmark" size={10} color={Colors.background} />
                        </View>
                      )}
                    </View>
                    <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                    <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          )}
        </Animated.View>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: Colors.overlay,
    justifyContent: 'flex-end',
  },
  overlayTouch: {
    ...StyleSheet.absoluteFillObject,
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
  imageWrapper: {
    position: 'relative',
    width: 80,
    height: 80,
  },
  checkBadge: {
    position: 'absolute',
    top: 5,
    right: 5,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
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
