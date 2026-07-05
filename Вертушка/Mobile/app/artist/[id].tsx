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
import { Icon } from '@/components/ui';
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

// Направление пагинации на сервере: только year-режимы. title сортируется клиентом.
const serverSortOrder = (mode: SortMode): 'asc' | 'desc' =>
  mode === 'year_desc' ? 'desc' : 'asc';

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
          <Icon name="close" size={14} color={Colors.background} style={styles.filterCloseIcon} />
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
  const [hasLoadError, setHasLoadError] = useState(false);
  const autoLoadAttemptsRef = useRef(0);
  const loadIdRef = useRef(0);
  // Cover-retry: бэкенд при заглушках запускает batch-прогрев обложек
  // (Search API → discogs_master_covers) — добираем их рефетчами страницы.
  const coverRetryRef = useRef<{ attempts: number; timer: ReturnType<typeof setTimeout> | null }>({
    attempts: 0,
    timer: null,
  });

  useEffect(() => {
    if (id) {
      loadArtist();
      loadMasters(true);
    }
    return () => {
      if (coverRetryRef.current.timer) clearTimeout(coverRetryRef.current.timer);
    };
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

  const loadMasters = async (reset: boolean = false, orderArg?: 'asc' | 'desc') => {
    if (!id) return;
    // Блокируем только подгрузку следующей страницы, reset-загрузки проходят всегда
    if (!reset && isLoadingMasters) return;

    const cursor = reset ? 1 : nextCursor;
    if (!cursor) return;

    const order = orderArg ?? serverSortOrder(sortMode);
    const currentLoadId = ++loadIdRef.current;
    setIsLoadingMasters(true);
    if (reset) setHasLoadError(false);

    try {
      setError(null);
      // Сервер пагинирует в направлении сортировки по году; клиент не пересортировывает.
      const data = await api.getArtistMasters(id, order, cursor, 100);

      // Игнорируем устаревший ответ (пользователь сменил сортировку/фильтр)
      if (loadIdRef.current !== currentLoadId) return;

      if (reset) {
        setMasters(data.results);
      } else {
        setMasters((prev) => {
          const keyOf = (m: MasterSearchResult) => m.master_id || m.main_release_id;
          const existingIds = new Set(prev.map(keyOf));
          const newMasters = data.results.filter(m => !existingIds.has(keyOf(m)));
          return [...prev, ...newMasters];
        });
      }
      setHasMore(data.has_more ?? false);
      setNextCursor(data.next_cursor ?? null);

      // Счётчик ретраев — per page-load: раньше был глобальным на экран, и
      // пролистав 5 страниц юзер оставлял страницы 2-5 без единого ретрая.
      coverRetryRef.current.attempts = 0;
      if (coverRetryRef.current.timer) clearTimeout(coverRetryRef.current.timer);
      if (data.results.some((m) => !m.cover_image_url)) {
        scheduleCoverRetry(cursor, order, currentLoadId);
      }
    } catch (err) {
      if (loadIdRef.current !== currentLoadId) return;
      console.error('Ошибка загрузки релизов:', err);
      setError('Не удалось загрузить релизы артиста');
      if (!reset) setHasLoadError(true);
    } finally {
      if (loadIdRef.current === currentLoadId) {
        setIsLoadingMasters(false);
      }
    }
  };

  const scheduleCoverRetry = (maxPage: number, order: 'asc' | 'desc', forLoadId: number) => {
    // 4 попытки до ~50с: batch-прогрев больших артистов (5 Search-вызовов
    // через общее окно лимита) может занять десятки секунд.
    if (coverRetryRef.current.attempts >= 4) return;
    const delay = [4000, 8000, 15000, 25000][coverRetryRef.current.attempts];
    coverRetryRef.current.attempts += 1;
    if (coverRetryRef.current.timer) clearTimeout(coverRetryRef.current.timer);
    coverRetryRef.current.timer = setTimeout(async () => {
      if (!id || loadIdRef.current !== forLoadId) return;
      try {
        // Рефетчим ВСЕ загруженные страницы (урок versions-экрана): юзер мог
        // пролистать несколько, заглушки остаются на любой из них.
        const keyOf = (m: MasterSearchResult) => m.master_id || m.main_release_id;
        const freshByKey = new Map<string, MasterSearchResult>();
        for (let p = 1; p <= maxPage; p += 1) {
          const fresh = await api.getArtistMasters(id, order, p, 100);
          if (loadIdRef.current !== forLoadId) return;
          fresh.results.forEach((m) => freshByKey.set(keyOf(m), m));
        }
        let stillUncovered = false;
        setMasters((prev) => prev.map((m) => {
          if (m.cover_image_url) return m;
          const f = freshByKey.get(keyOf(m));
          if (f?.cover_image_url) return { ...m, cover_image_url: f.cover_image_url };
          if (freshByKey.has(keyOf(m))) stillUncovered = true;
          return m;
        }));
        if (stillUncovered) scheduleCoverRetry(maxPage, order, forLoadId);
      } catch {
        // Тихо: ретрай обложек не должен показывать ошибки
      }
    }, delay);
  };

  const handleSortChange = (newMode: SortMode) => {
    const directionChanged = serverSortOrder(newMode) !== serverSortOrder(sortMode);
    setSortMode(newMode);
    setShowSortMenu(false);
    // Смена направления year → перезагрузить с page 1 в новом порядке.
    // title сортируется клиентом поверх загруженного, без перезагрузки.
    if (directionChanged) {
      setNextCursor(1);
      loadMasters(true, serverSortOrder(newMode));
    }
  };

  const handleLoadMore = useCallback(() => {
    if (hasMore && !isLoadingMasters && !hasLoadError) {
      loadMasters();
    }
  }, [hasMore, isLoadingMasters, hasLoadError]);

  const handleMasterPress = useCallback((master: MasterSearchResult) => {
    // Release-only айтем (нет master-группировки на Discogs) приходит с пустым
    // master_id → открываем карточку релиза напрямую по main_release_id
    // (discogs release id, [id].tsx резолвит через getRecordByDiscogsId).
    if (!master.master_id) {
      router.push(`/record/${master.main_release_id}`);
      return;
    }
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

    // year_asc/year_desc: порядок уже задан сервером (пагинация в направлении).
    // title: сортируем клиентом поверх загруженного набора.
    if (sortMode === 'title') {
      return filtered.sort((a, b) => a.title.localeCompare(b.title, 'ru'));
    }
    return filtered;
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

  // Сброс счётчика авто-подгрузки и ошибки при смене фильтра
  useEffect(() => {
    autoLoadAttemptsRef.current = 0;
    setHasLoadError(false);
  }, [activeFilter]);

  // Используем первое изображение в полном разрешении
  const imageUrl = artist?.images && artist.images.length > 0 ? artist.images[0] : undefined;

  const renderItem = useCallback(({ item }: { item: MasterSearchResult }) => (
    <MasterRecordCard item={item} onPress={handleMasterPress} />
  ), [handleMasterPress]);

  // Release-only айтемы приходят с пустым master_id → ключуем по main_release_id,
  // иначе все '' схлопываются в один ключ (React: duplicate key '.$=').
  const keyExtractor = useCallback(
    (item: MasterSearchResult) => item.master_id || item.main_release_id,
    [],
  );

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
            <Icon name="person-outline" size={100} color={Colors.textMuted} />
          </View>
        )}
      </View>

      {/* Информация об артисте */}
      <View style={styles.infoSection}>
        <Text style={styles.artistName}>{artist?.name.replace(/\s*\(\d+\)$/, '') ?? ''}</Text>
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
              <Icon name="swap-vertical-outline" size={18} color={Colors.royalBlue} />
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
                  <Icon name="checkmark" size={16} color={Colors.royalBlue} />
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
          <TouchableOpacity
            style={styles.loadMoreButton}
            onPress={() => { setHasLoadError(false); loadMasters(); }}
            activeOpacity={0.7}
          >
            <Text style={styles.loadMoreButtonText}>Загрузить ещё</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }, [isLoadingMasters, hasMore]);

  const listEmpty = useMemo(() => {
    if (isLoadingMasters) return null;
    const isEmptyProfile = !error && !activeFilter && masters.length === 0 && !hasMore;
    return (
      <View style={styles.emptyContainer}>
        <Icon
          name={error ? 'cloud-offline-outline' : isEmptyProfile ? 'person-remove-outline' : 'musical-notes-outline'}
          size={48}
          color={error ? Colors.error : Colors.textMuted}
        />
        <Text style={styles.emptyText}>
          {error || (activeFilter ? 'Нет релизов в этой категории' : isEmptyProfile ? 'Релизы не найдены' : 'Релизы не найдены')}
        </Text>
        {isEmptyProfile && (
          <Text style={styles.emptySubText}>
            Возможно, это псевдоним артиста без отдельных релизов
          </Text>
        )}
        {error && (
          <TouchableOpacity
            style={styles.retryButton}
            onPress={() => { setError(null); loadMasters(masters.length === 0); }}
            activeOpacity={0.7}
          >
            <Icon name="refresh" size={18} color={Colors.royalBlue} />
            <Text style={styles.retryText}>Повторить</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  }, [isLoadingMasters, error, activeFilter, masters.length, hasMore]);

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
          <Icon name="alert-circle-outline" size={64} color={Colors.error} />
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
  emptySubText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
    marginTop: Spacing.xs,
    textAlign: 'center',
    paddingHorizontal: Spacing.xl,
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
