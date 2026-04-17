/**
 * Экран детальной информации об артисте
 */
import { useEffect, useState, useRef, useMemo, useCallback, memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  TouchableOpacity,
  Animated,
  Pressable,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../components/Header';
import { RecordCard } from '../../components/RecordCard';
import { api } from '../../lib/api';
import { useCacheStore } from '../../lib/store';
import { Artist, MasterSearchResult } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

type ReleaseFilter = 'album' | 'ep' | 'single';
type SortMode = 'year_desc' | 'year_asc' | 'title';

const FILTERS: { key: ReleaseFilter; label: string }[] = [
  { key: 'album', label: 'Альбомы' },
  { key: 'ep', label: 'EP' },
  { key: 'single', label: 'Синглы' },
];

const SORT_OPTIONS: { key: SortMode; label: string }[] = [
  { key: 'year_asc', label: 'Сначала старые' },
  { key: 'year_desc', label: 'Сначала новые' },
  { key: 'title', label: 'По названию' },
];

const matchesFilter = (master: MasterSearchResult, filter: ReleaseFilter): boolean => {
  if (!master.release_type) return filter === 'album';
  return master.release_type === filter;
};

type FilterChipProps = {
  label: string;
  isActive: boolean;
  onPress: () => void;
};

function FilterChip({ label, isActive, onPress }: FilterChipProps) {
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const colorAnim = useRef(new Animated.Value(isActive ? 1 : 0)).current;

  useEffect(() => {
    Animated.spring(colorAnim, {
      toValue: isActive ? 1 : 0,
      tension: 80,
      friction: 9,
      useNativeDriver: false,
    }).start();
  }, [isActive]);

  const backgroundColor = colorAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [Colors.background, Colors.royalBlue],
  });

  const textColor = colorAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [Colors.royalBlue, Colors.background],
  });

  const handlePressIn = () => {
    Animated.spring(scaleAnim, {
      toValue: 0.93,
      tension: 300,
      friction: 10,
      useNativeDriver: false,
    }).start();
  };

  const handlePressOut = () => {
    Animated.spring(scaleAnim, {
      toValue: 1,
      tension: 200,
      friction: 8,
      useNativeDriver: false,
    }).start();
  };

  return (
    <Pressable onPress={onPress} onPressIn={handlePressIn} onPressOut={handlePressOut}>
      <Animated.View
        style={[
          styles.filterChip,
          { backgroundColor, transform: [{ scale: scaleAnim }] },
        ]}
      >
        <Animated.Text style={[styles.filterChipText, { color: textColor }]}>
          {label}
        </Animated.Text>
        {isActive && (
          <Ionicons name="close" size={14} color={Colors.background} style={styles.filterCloseIcon} />
        )}
      </Animated.View>
    </Pressable>
  );
}

const MasterRecordCard = memo(function MasterRecordCard({
  item,
  onPress,
}: {
  item: MasterSearchResult;
  onPress: (master: MasterSearchResult) => void;
}) {
  const handlePress = useCallback(() => onPress(item), [item, onPress]);
  return <RecordCard record={item} onPress={handlePress} />;
});

export default function ArtistDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const cache = useCacheStore();

  const [artist, setArtist] = useState<Artist | null>(null);
  const [masters, setMasters] = useState<MasterSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMasters, setIsLoadingMasters] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<ReleaseFilter | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>('year_asc');
  const [showSortMenu, setShowSortMenu] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const autoLoadAttemptsRef = useRef(0);
  const loadIdRef = useRef(0);

  useEffect(() => {
    if (id) {
      loadArtist();
      loadMasters(true);
    }
  }, [id]);

  const loadArtist = async () => {
    if (!id) return;

    const cached = cache.getArtist(id);
    if (cached) {
      setArtist(cached);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.getArtist(id);
      cache.setArtist(id, data);
      setArtist(data);
    } catch (err) {
      console.error('Ошибка загрузки артиста:', err);
      setError('Не удалось загрузить информацию об артисте');
    } finally {
      setIsLoading(false);
    }
  };

  const loadMasters = async (reset: boolean = false) => {
    if (!id) return;
    // Блокируем только подгрузку следующей страницы, reset-загрузки проходят всегда
    if (!reset && isLoadingMasters) return;

    const cursor = reset ? 1 : nextCursor;
    if (!cursor) return;

    const currentLoadId = ++loadIdRef.current;
    setIsLoadingMasters(true);

    try {
      setError(null);
      // Всегда грузим asc с сервера; клиент сортирует через filteredMasters useMemo
      const data = await api.getArtistMasters(id, 'asc', cursor, 100);

      // Игнорируем устаревший ответ (пользователь сменил сортировку/фильтр)
      if (loadIdRef.current !== currentLoadId) return;

      if (reset) {
        setMasters(data.results);
      } else {
        setMasters((prev) => {
          const existingIds = new Set(prev.map(m => m.master_id));
          const newMasters = data.results.filter(m => !existingIds.has(m.master_id));
          return [...prev, ...newMasters];
        });
      }
      setHasMore(data.has_more ?? false);
      setNextCursor(data.next_cursor ?? null);
    } catch (err) {
      if (loadIdRef.current !== currentLoadId) return;
      console.error('Ошибка загрузки релизов:', err);
      setError('Не удалось загрузить релизы артиста');
    } finally {
      if (loadIdRef.current === currentLoadId) {
        setIsLoadingMasters(false);
      }
    }
  };

  const handleSortChange = (newMode: SortMode) => {
    // Все режимы сортировки обрабатываются клиентски через filteredMasters useMemo
    setSortMode(newMode);
    setShowSortMenu(false);
  };

  const handleLoadMore = useCallback(() => {
    if (hasMore && !isLoadingMasters) {
      loadMasters();
    }
  }, [hasMore, isLoadingMasters]);

  const handleMasterPress = useCallback((master: MasterSearchResult) => {
    router.push({
      pathname: `/master/${master.master_id}`,
      params: {
        title: master.title,
        artist: master.artist,
        year: master.year?.toString() || '',
        cover: master.cover_image_url || '',
      },
    });
  }, []);

  const handleFilterPress = (filter: ReleaseFilter) => {
    setActiveFilter(activeFilter === filter ? null : filter);
  };

  const filteredMasters = useMemo(() => {
    const filtered = activeFilter
      ? masters.filter((m) => matchesFilter(m, activeFilter))
      : [...masters];

    const yearSort = (a: MasterSearchResult, b: MasterSearchResult, desc: boolean) => {
      const ay = a.year ?? null;
      const by = b.year ?? null;
      if (ay === null && by === null) return 0;
      if (ay === null) return 1;  // без года — в конец
      if (by === null) return -1;
      return desc ? by - ay : ay - by;
    };

    switch (sortMode) {
      case 'year_desc':
        return filtered.sort((a, b) => yearSort(a, b, true));
      case 'year_asc':
        return filtered.sort((a, b) => yearSort(a, b, false));
      case 'title':
        return filtered.sort((a, b) => a.title.localeCompare(b.title, 'ru'));
    }
  }, [masters, activeFilter, sortMode]);

  // Авто-подгрузка: если после фильтрации мало результатов, но ещё есть данные на сервере
  useEffect(() => {
    if (
      activeFilter &&
      filteredMasters.length < 6 &&
      hasMore &&
      !isLoadingMasters &&
      autoLoadAttemptsRef.current < 3
    ) {
      autoLoadAttemptsRef.current += 1;
      loadMasters();
    }
  }, [activeFilter, filteredMasters.length, hasMore, isLoadingMasters]);

  // Сброс счётчика авто-подгрузки при смене фильтра
  useEffect(() => {
    autoLoadAttemptsRef.current = 0;
  }, [activeFilter]);

  // Используем первое изображение в полном разрешении
  const imageUrl = artist?.images && artist.images.length > 0 ? artist.images[0] : undefined;

  const renderItem = useCallback(({ item }: { item: MasterSearchResult }) => (
    <MasterRecordCard item={item} onPress={handleMasterPress} />
  ), [handleMasterPress]);

  const keyExtractor = useCallback((item: MasterSearchResult) => item.master_id, []);

  const listHeader = useMemo(() => (
    <>
      {/* Изображение артиста */}
      <View style={styles.imageContainer}>
        {imageUrl ? (
          <Image
            source={imageUrl}
            style={styles.image}
            contentFit="cover"
            cachePolicy="disk"
          />
        ) : (
          <View style={styles.placeholderImage}>
            <Ionicons name="person-outline" size={100} color={Colors.textMuted} />
          </View>
        )}
      </View>

      {/* Информация об артисте */}
      <View style={styles.infoSection}>
        <Text style={styles.artistName}>{artist?.name ?? ''}</Text>
      </View>

      {/* Релизы артиста */}
      <View style={styles.releasesSection}>
        <Text style={styles.sectionTitle}>Релизы</Text>

        {/* Фильтры + сортировка */}
        <View style={styles.filtersRow}>
          {FILTERS.map((f) => (
            <FilterChip
              key={f.key}
              label={f.label}
              isActive={activeFilter === f.key}
              onPress={() => handleFilterPress(f.key)}
            />
          ))}
          <View style={{ marginLeft: 'auto' }}>
            <TouchableOpacity
              style={styles.sortButton}
              onPress={() => setShowSortMenu(!showSortMenu)}
              activeOpacity={0.7}
            >
              <Ionicons name="swap-vertical-outline" size={18} color={Colors.royalBlue} />
            </TouchableOpacity>
          </View>
        </View>

        {/* Меню сортировки */}
        {showSortMenu && (
          <View style={styles.sortMenu}>
            {SORT_OPTIONS.map((option) => (
              <TouchableOpacity
                key={option.key}
                style={[styles.sortOption, sortMode === option.key && styles.sortOptionActive]}
                onPress={() => handleSortChange(option.key)}
              >
                <Text style={[styles.sortOptionText, sortMode === option.key && styles.sortOptionTextActive]}>
                  {option.label}
                </Text>
                {sortMode === option.key && (
                  <Ionicons name="checkmark" size={16} color={Colors.royalBlue} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}
      </View>
    </>
  ), [imageUrl, artist?.name, activeFilter, showSortMenu, sortMode]);

  const listFooter = useMemo(() => {
    if (!hasMore && !isLoadingMasters) return null;
    return (
      <View style={styles.loadMoreContainer}>
        {isLoadingMasters ? (
          <>
            <ActivityIndicator size="small" color={Colors.royalBlue} />
            <Text style={styles.loadMoreText}>Загрузка релизов...</Text>
          </>
        ) : (
          <TouchableOpacity style={styles.loadMoreButton} onPress={handleLoadMore} activeOpacity={0.7}>
            <Text style={styles.loadMoreButtonText}>Загрузить ещё</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }, [isLoadingMasters, hasMore, handleLoadMore]);

  const listEmpty = useMemo(() => {
    if (isLoadingMasters) return null;
    return (
      <View style={styles.emptyContainer}>
        <Ionicons
          name={error ? 'cloud-offline-outline' : 'musical-notes-outline'}
          size={48}
          color={error ? Colors.error : Colors.textMuted}
        />
        <Text style={styles.emptyText}>
          {error || (activeFilter ? 'Нет релизов в этой категории' : 'Релизы не найдены')}
        </Text>
        {error && (
          <TouchableOpacity
            style={styles.retryButton}
            onPress={() => { setError(null); loadMasters(masters.length === 0); }}
            activeOpacity={0.7}
          >
            <Ionicons name="refresh" size={18} color={Colors.royalBlue} />
            <Text style={styles.retryText}>Повторить</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }, [isLoadingMasters, error, activeFilter, masters.length]);

  if (isLoading) {
    return (
      <View style={styles.container}>
        <Header title="Артист" showBack />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
          <Text style={styles.loadingText}>Загрузка...</Text>
        </View>
      </View>
    );
  }

  if (error || !artist) {
    return (
      <View style={styles.container}>
        <Header title="Артист" showBack />
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle-outline" size={64} color={Colors.error} />
          <Text style={styles.errorText}>{error || 'Артист не найден'}</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Header title="Артист" showBack />

      <FlatList
        data={filteredMasters}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        numColumns={2}
        columnWrapperStyle={styles.columnWrapper}
        ListHeaderComponent={listHeader}
        ListFooterComponent={listFooter}
        ListEmptyComponent={listEmpty}
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.5}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + Spacing.xl },
        ]}
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={true}
        maxToRenderPerBatch={10}
        windowSize={5}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollContent: {
    paddingBottom: Spacing.xl,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginTop: Spacing.md,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.xl,
  },
  errorText: {
    ...Typography.body,
    color: Colors.error,
    textAlign: 'center',
    marginTop: Spacing.md,
  },
  imageContainer: {
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: Colors.surface,
    alignSelf: 'center',
    marginTop: Spacing.xl,
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholderImage: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  infoSection: {
    padding: Spacing.lg,
    alignItems: 'center',
  },
  artistName: {
    ...Typography.h1,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    ...Typography.h3,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  releasesSection: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.lg,
  },
  filtersRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
    marginBottom: Spacing.md,
  },
  filterChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: Colors.royalBlue,
    gap: 4,
  },
  filterChipText: {
    ...Typography.bodySmall,
    fontWeight: '500',
  },
  filterCloseIcon: {
    marginLeft: 2,
  },
  sortButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },
  sortMenu: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    padding: Spacing.xs,
    marginBottom: Spacing.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  sortOption: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    justifyContent: 'space-between' as const,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.sm,
  },
  sortOptionActive: {
    backgroundColor: Colors.surface,
  },
  sortOptionText: {
    ...Typography.bodySmall,
    color: Colors.text,
  },
  sortOptionTextActive: {
    color: Colors.royalBlue,
    fontFamily: 'Inter_600SemiBold',
  },
  columnWrapper: {
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    gap: Spacing.md,
  },
  loadMoreContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    padding: Spacing.md,
  },
  loadMoreText: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginLeft: Spacing.sm,
  },
  endText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
    padding: Spacing.md,
  },
  emptyContainer: {
    alignItems: 'center',
    padding: Spacing.xl,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    marginTop: Spacing.sm,
    textAlign: 'center',
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginTop: Spacing.md,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  retryText: {
    ...Typography.bodySmall,
    color: Colors.royalBlue,
    fontFamily: 'Inter_600SemiBold',
  },
  loadMoreButton: {
    alignSelf: 'center',
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.lg,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    marginBottom: Spacing.md,
  },
  loadMoreButtonText: {
    ...Typography.bodySmall,
    color: Colors.royalBlue,
    fontFamily: 'Inter_600SemiBold',
  },
});
