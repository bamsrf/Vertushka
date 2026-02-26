/**
 * Экран коллекции — Editorial Gradient Edition
 * Переключатель Моё / Хочу, editorial заголовок, expanded cards
 */
import { useEffect, useCallback, useState, useRef } from 'react';
import { View, StyleSheet, Alert, TouchableOpacity, Text, Animated, ScrollView, Image, LayoutAnimation, UIManager, Platform } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AnimatedGradientText } from '../../components/AnimatedGradientText';
import { GradientText } from '../../components/GradientText';
import { RecordGrid } from '../../components/RecordGrid';
import { FolderPickerModal } from '../../components/FolderPickerModal';
import { SegmentedControl } from '../../components/ui';
import { useCollectionStore, useAuthStore } from '../../lib/store';
import { api } from '../../lib/api';
import { CollectionItem, WishlistItem, CollectionTab } from '../../lib/types';
import { Colors, Spacing, Typography, BorderRadius, Gradients, Shadows } from '../../constants/theme';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

const folderPlaceholder = require('../../assets/images/folder-placeholder.png');

const SEGMENTS: { key: CollectionTab; label: string }[] = [
  { key: 'collection', label: 'В наличии' },
  { key: 'wishlist', label: 'Вишлист' },
];

type ViewMode = 'grid' | 'list';

type FormatFilter = 'all' | 'vinyl' | 'cd' | 'cassette' | 'box_set';

const FORMAT_OPTIONS: { key: FormatFilter; label: string; match: string[] }[] = [
  { key: 'all', label: 'Все форматы', match: [] },
  { key: 'vinyl', label: 'Винил', match: ['Vinyl', 'LP', '12"', '10"', '7"'] },
  { key: 'cd', label: 'CD', match: ['CD'] },
  { key: 'cassette', label: 'Кассета', match: ['Cassette'] },
  { key: 'box_set', label: 'Бокс-сет', match: ['Box Set'] },
];

export default function CollectionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [activeFilter, setActiveFilter] = useState<FormatFilter>('all');
  const modeAnim = useRef(new Animated.Value(0)).current;
  const menuAnim = useRef(new Animated.Value(0)).current;
  const viewIconAnim = useRef(new Animated.Value(0)).current; // 0 = grid, 1 = list
  const filterMenuAnim = useRef(new Animated.Value(0)).current; // 0 = closed, 1 = open

  const filterMenuOpen = useRef(false);

  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const { user } = useAuthStore();

  const handleProfilePress = () => {
    router.push('/profile');
  };

  const {
    activeTab,
    collectionItems,
    wishlistItems,
    folders,
    isLoading,
    setActiveTab,
    fetchCollections,
    fetchCollectionItems,
    fetchWishlistItems,
    removeFromCollection,
    removeFromWishlist,
    moveToCollection,
    createFolder,
    addItemsToFolder,
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

  // Анимация смены кнопки Выбрать ↔ Отмена + скрытие меню
  useEffect(() => {
    Animated.parallel([
      Animated.spring(modeAnim, {
        toValue: isSelectionMode ? 1 : 0,
        tension: 220,
        friction: 14,
        useNativeDriver: true,
      }),
      Animated.timing(menuAnim, {
        toValue: isSelectionMode ? 0 : 1,
        duration: 300,
        useNativeDriver: false, // height animation needs false
      }),
    ]).start();
  }, [isSelectionMode]);

  // Анимация иконки grid/list
  const handleToggleViewMode = () => {
    const next: ViewMode = viewMode === 'grid' ? 'list' : 'grid';
    Animated.timing(viewIconAnim, {
      toValue: next === 'list' ? 1 : 0,
      duration: 250,
      useNativeDriver: true,
    }).start();
    LayoutAnimation.configureNext(LayoutAnimation.create(
      300,
      LayoutAnimation.Types.easeInEaseOut,
      LayoutAnimation.Properties.opacity,
    ));
    setViewMode(next);
  };

  // useNativeDriver: false — нужен для анимации maxHeight
  const smoothCloseFilter = (cb?: () => void) => {
    Animated.timing(filterMenuAnim, {
      toValue: 0,
      duration: 220,
      useNativeDriver: false,
    }).start(() => {
      filterMenuOpen.current = false;
      cb?.();
    });
  };

  // Открытие/закрытие фильтр-меню с анимацией
  const handleToggleFilterMenu = () => {
    if (filterMenuOpen.current) {
      smoothCloseFilter();
    } else {
      filterMenuOpen.current = true;
      Animated.spring(filterMenuAnim, {
        toValue: 1,
        tension: 280,
        friction: 22,
        useNativeDriver: false,
      }).start();
    }
  };

  const handleSelectFilter = (filter: FormatFilter) => {
    smoothCloseFilter(() => setActiveFilter(filter));
  };

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
    const recordId = item.record.discogs_id || item.record.id;
    router.push(`/record/${recordId}`);
  };

  const handleArtistPress = useCallback(async (artistName: string) => {
    try {
      const response = await api.searchArtists(artistName, 1, 5);
      if (response.results.length > 0) {
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
              const fmt = getFormatDisplayInfo(item.record.format_type);
              Alert.alert('Готово!', `${fmt.label} ${fmt.verb} в коллекцию`);
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

  const handleAddToFolder = async (folderId: string) => {
    try {
      // Определяем record_id для выбранных items
      const selectedCollectionItems = collectionItems.filter(item => selectedItems.has(item.id));

      // Загружаем папку, чтобы проверить что уже есть внутри
      const folderData = await api.getCollection(folderId);
      const existingRecordIds = new Set(
        (folderData.items || []).map((i: CollectionItem) => i.record_id)
      );

      // Фильтруем: только те, которых ещё нет в папке, дедуплицируя по record_id
      const seen = new Set<string>();
      const newItems = selectedCollectionItems.filter(item => {
        if (existingRecordIds.has(item.record_id)) return false;
        if (seen.has(item.record_id)) return false;
        seen.add(item.record_id);
        return true;
      });
      const duplicateCount = selectedCollectionItems.length - newItems.length;

      if (newItems.length === 0) {
        setShowFolderPicker(false);
        Alert.alert(
          'Уже в папке',
          duplicateCount === 1
            ? 'Эта пластинка уже находится в папке'
            : 'Все выбранные пластинки уже находятся в этой папке'
        );
        return;
      }

      await addItemsToFolder(folderId, newItems.map(item => item.id));
      setShowFolderPicker(false);
      setSelectedItems(new Set());
      setIsSelectionMode(false);

      if (duplicateCount > 0) {
        Alert.alert(
          'Готово',
          `${newItems.length} пл. добавлено. ${duplicateCount} уже были в папке — пропущены.`
        );
      }
    } catch {
      Alert.alert('Ошибка', 'Не удалось добавить в папку');
    }
  };

  const handleCreateFolder = () => {
    Alert.prompt(
      'Новая папка',
      'Введите название папки',
      async (name) => {
        if (!name?.trim()) return;
        await createFolder(name.trim());
      },
      'plain-text',
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

  const rawData = (activeTab === 'collection' ? collectionItems : wishlistItems) as (CollectionItem | WishlistItem)[];

  // Фильтрация по формату
  const data = activeFilter === 'all' ? rawData : rawData.filter(item => {
    const formatType = (item.record.format_type || '').toLowerCase();
    const formatDesc = (item.record.format_description || '').toLowerCase();
    const matchWords = FORMAT_OPTIONS.find(f => f.key === activeFilter)?.match || [];
    return matchWords.some(w => {
      const wLower = w.toLowerCase();
      return formatType.includes(wLower) || formatDesc.includes(wLower);
    });
  });

  const selectOpacity = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const selectScale = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0.85] });
  const cancelOpacity = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });
  const cancelScale = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] });

  // Анимация скрытия меню (segments + folders)
  const menuOpacity = menuAnim.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, 0, 1] });

  // Анимация иконки view toggle
  const gridIconOpacity = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const gridIconScale = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0.5] });
  const listIconOpacity = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });
  const listIconScale = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1] });

  const activeFilterLabel = FORMAT_OPTIONS.find(f => f.key === activeFilter)?.label || 'Все';

  const CollectionHeader = (
    <View style={styles.headerContainer}>
      {/* Title row: avatar */}
      <View style={styles.avatarRow}>
        <AnimatedGradientText style={Typography.heroTitle}>Коллекция</AnimatedGradientText>
        <TouchableOpacity style={styles.profileButton} onPress={handleProfilePress}>
          {user?.avatar_url ? (
            <Image source={{ uri: user.avatar_url }} style={styles.avatar} />
          ) : (
            <LinearGradient
              colors={[Colors.royalBlue, Colors.periwinkle] as [string, string]}
              style={styles.avatarPlaceholder}
            >
              <Ionicons name="disc" size={20} color={Colors.background} />
            </LinearGradient>
          )}
        </TouchableOpacity>
      </View>

      {/* Toolbar row: Выбрать/Отмена + Grid/List + Filter */}
      <View style={styles.toolbarRow}>
        {/* Select / Cancel */}
        <View style={styles.headerButtonWrapper}>
          <Animated.View
            style={[styles.headerButtonAbsolute, { opacity: cancelOpacity, transform: [{ scale: cancelScale }] }]}
            pointerEvents={isSelectionMode ? 'auto' : 'none'}
          >
            <TouchableOpacity style={styles.cancelButton} onPress={handleToggleSelectionMode}>
              <Text style={styles.cancelButtonText}>Отмена</Text>
            </TouchableOpacity>
          </Animated.View>

          <Animated.View
            style={{ opacity: selectOpacity, transform: [{ scale: selectScale }] }}
            pointerEvents={isSelectionMode ? 'none' : 'auto'}
          >
            <TouchableOpacity onPress={handleToggleSelectionMode} activeOpacity={0.7}>
              <LinearGradient
                colors={Gradients.blue}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={styles.selectButtonGradientBorder}
              >
                <View style={styles.selectButtonInner}>
                  <GradientText style={styles.selectButtonText}>Выбрать</GradientText>
                </View>
              </LinearGradient>
            </TouchableOpacity>
          </Animated.View>
        </View>

        {/* Grid / List toggle */}
        {!isSelectionMode && (
          <TouchableOpacity
            style={styles.viewToggleButton}
            onPress={handleToggleViewMode}
            activeOpacity={0.7}
          >
            <View style={styles.viewToggleIconContainer}>
              <Animated.View style={[styles.viewToggleIcon, { opacity: gridIconOpacity, transform: [{ scale: gridIconScale }] }]}>
                <Ionicons name="grid-outline" size={18} color={Colors.royalBlue} />
              </Animated.View>
              <Animated.View style={[styles.viewToggleIcon, styles.viewToggleIconAbsolute, { opacity: listIconOpacity, transform: [{ scale: listIconScale }] }]}>
                <Ionicons name="list-outline" size={18} color={Colors.royalBlue} />
              </Animated.View>
            </View>
          </TouchableOpacity>
        )}

        {/* Value button */}
        {!isSelectionMode && activeTab === 'collection' && (
          <TouchableOpacity
            style={styles.valueButton}
            onPress={() => router.push('/collection/value')}
            activeOpacity={0.7}
          >
            <Ionicons name="cash-outline" size={18} color={Colors.royalBlue} />
          </TouchableOpacity>
        )}

        {/* Filter button */}
        {!isSelectionMode && (
          <View>
            <TouchableOpacity
              style={[styles.filterButton, activeFilter !== 'all' && styles.filterButtonActive]}
              onPress={handleToggleFilterMenu}
              activeOpacity={0.7}
            >
              <Ionicons
                name="options-outline"
                size={18}
                color={activeFilter !== 'all' ? Colors.background : Colors.royalBlue}
              />
              {activeFilter !== 'all' && (
                <Text style={styles.filterButtonActiveText}>{activeFilterLabel}</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </View>

      {/* Animated menu: segments + folders */}
      <Animated.View style={{ opacity: menuOpacity, maxHeight: menuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 500] }), overflow: 'hidden' }}>
        {/* Segmented control */}
        <View style={styles.segmentContainer}>
          <SegmentedControl
            segments={SEGMENTS}
            selectedKey={activeTab}
            onSelect={setActiveTab}
            disabled={isSelectionMode}
          />
        </View>

        {/* Folders section */}
        {activeTab === 'collection' && folders.length > 0 && (
          <View style={styles.foldersSection}>
            <Text style={styles.foldersSectionTitle}>Папки</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.foldersScroll}>
              <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateFolder}>
                <View style={styles.newFolderIcon}>
                  <Ionicons name="add" size={32} color={Colors.textMuted} />
                </View>
                <Text style={styles.newFolderText}>Новая</Text>
              </TouchableOpacity>
              {folders.map(folder => (
                <TouchableOpacity
                  key={folder.id}
                  style={styles.folderCard}
                  onPress={() => router.push(`/folder/${folder.id}` as any)}
                >
                  <Image source={folderPlaceholder} style={styles.folderImage} />
                  <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                  <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Create first folder button */}
        {activeTab === 'collection' && folders.length === 0 && (
          <TouchableOpacity style={styles.createFirstFolder} onPress={handleCreateFolder}>
            <Ionicons name="folder-outline" size={20} color={Colors.textMuted} />
            <Text style={styles.createFirstFolderText}>Создать папку</Text>
          </TouchableOpacity>
        )}
      </Animated.View>

      {/* Filter dropdown — всегда в дереве, высота управляется анимацией */}
      <Animated.View
        style={{
          maxHeight: filterMenuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 300] }),
          opacity: filterMenuAnim,
          overflow: 'hidden',
        }}
        pointerEvents="box-none"
      >
        <View style={styles.filterDropdown}>
          {FORMAT_OPTIONS.map(option => (
            <TouchableOpacity
              key={option.key}
              style={[styles.filterOption, activeFilter === option.key && styles.filterOptionActive]}
              onPress={() => handleSelectFilter(option.key)}
            >
              <Text style={[styles.filterOptionText, activeFilter === option.key && styles.filterOptionTextActive]}>
                {option.label}
              </Text>
              {activeFilter === option.key && (
                <Ionicons name="checkmark" size={18} color={Colors.royalBlue} />
              )}
            </TouchableOpacity>
          ))}
        </View>
      </Animated.View>
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <RecordGrid
        key={viewMode}
        data={data}
        cardVariant={viewMode === 'list' ? 'list' : 'expanded'}
        numColumns={viewMode === 'list' ? 1 : 2}
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
        ListHeaderComponent={CollectionHeader}
        isSelectionMode={isSelectionMode}
        selectedItems={selectedItems}
        onToggleItemSelection={handleToggleItemSelection}
      />

      {/* Нижний подвал в режиме выбора */}
      {isSelectionMode && (
        <View style={styles.selectionFooter}>
          {activeTab === 'wishlist' && (
            <TouchableOpacity
              style={styles.footerButton}
              onPress={handleBulkMoveToCollection}
              disabled={selectedItems.size === 0}
            >
              <Ionicons
                name="arrow-forward-circle"
                size={24}
                color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
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

          {activeTab === 'collection' && (
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

      <FolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleAddToFolder}
        selectedRecordIds={collectionItems
          .filter(item => selectedItems.has(item.id))
          .map(item => item.record_id)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  headerContainer: {
    paddingBottom: Spacing.sm,
  },
  avatarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  profileButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: Colors.lavender,
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  toolbarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  segmentContainer: {
    paddingBottom: Spacing.sm,
  },

  // View toggle (grid/list)
  viewToggleButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIconContainer: {
    width: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIcon: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIconAbsolute: {
    position: 'absolute',
  },

  // Value button
  valueButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },

  // Filter button
  filterButton: {
    height: 36,
    paddingHorizontal: 10,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  filterButtonActive: {
    backgroundColor: Colors.royalBlue,
  },
  filterButtonActiveText: {
    ...Typography.caption,
    color: Colors.background,
    fontFamily: 'Inter_600SemiBold',
  },

  filterOverlayInHeader: {
    // пустой враппер — нужен только для перехвата тапа мимо dropdown
  },
  filterDropdown: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    padding: Spacing.xs,
    ...Shadows.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.sm,
  },
  filterOptionActive: {
    backgroundColor: Colors.surface,
  },
  filterOptionText: {
    ...Typography.bodySmall,
    color: Colors.text,
  },
  filterOptionTextActive: {
    color: Colors.royalBlue,
    fontFamily: 'Inter_600SemiBold',
  },

  // Gradient border "Выбрать" button
  selectButtonGradientBorder: {
    borderRadius: 20,
    padding: 1.5,
  },
  selectButtonInner: {
    backgroundColor: Colors.background,
    borderRadius: 18.5,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
  },
  selectButtonText: {
    ...Typography.buttonSmall,
    fontFamily: 'Inter_600SemiBold',
  },

  // Cancel button
  cancelButton: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: 20,
    backgroundColor: Colors.surface,
  },
  cancelButtonText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },

  headerButtonWrapper: {
    alignItems: 'flex-start',
    justifyContent: 'center',
    minHeight: 36,
  },
  headerButtonAbsolute: {
    position: 'absolute',
    right: 0,
  },

  selectionFooter: {
    position: 'absolute',
    bottom: 96, // above floating tab bar (bottom:28 + height:60 + gap:8)
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
  footerButtonTextDisabled: {
    color: Colors.textMuted,
  },

  // Folders section
  foldersSection: {
    marginBottom: Spacing.sm,
  },
  foldersSectionTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  foldersScroll: {
    gap: Spacing.sm,
  },
  folderCard: {
    width: 100,
    alignItems: 'center' as const,
    gap: Spacing.xs,
  },
  newFolderCard: {
    width: 100,
    alignItems: 'center' as const,
    gap: Spacing.xs,
  },
  newFolderIcon: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  newFolderText: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontFamily: 'Inter_600SemiBold',
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
    textAlign: 'center' as const,
  },
  folderCount: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontSize: 11,
  },
  createFirstFolder: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  createFirstFolderText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
});
