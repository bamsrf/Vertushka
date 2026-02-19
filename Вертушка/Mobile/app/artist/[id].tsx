/**
 * Экран детальной информации об артисте
 */
import { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
  Animated,
  Pressable,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../components/Header';
import { RecordCard } from '../../components/RecordCard';
import { api } from '../../lib/api';
import { Artist, MasterSearchResult } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

type ReleaseFilter = 'album' | 'ep' | 'single';

const FILTERS: { key: ReleaseFilter; label: string }[] = [
  { key: 'album', label: 'Альбомы' },
  { key: 'ep', label: 'EP' },
  { key: 'single', label: 'Синглы' },
];

const matchesFilter = (master: MasterSearchResult, filter: ReleaseFilter): boolean => {
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

export default function ArtistDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [artist, setArtist] = useState<Artist | null>(null);
  const [masters, setMasters] = useState<MasterSearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMasters, setIsLoadingMasters] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalMasters, setTotalMasters] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [activeFilter, setActiveFilter] = useState<ReleaseFilter | null>(null);

  useEffect(() => {
    if (id) {
      loadArtist();
      loadMasters(1);
    }
  }, [id]);

  const loadArtist = async () => {
    if (!id) return;

    setIsLoading(true);
    setError(null);

    try {
      const data = await api.getArtist(id);
      setArtist(data);
    } catch (err) {
      console.error('Ошибка загрузки артиста:', err);
      setError('Не удалось загрузить информацию об артисте');
      Alert.alert('Ошибка', 'Не удалось загрузить информацию об артисте');
    } finally {
      setIsLoading(false);
    }
  };

  const loadMasters = async (pageNum: number) => {
    if (!id || isLoadingMasters) return;

    setIsLoadingMasters(true);

    try {
      const data = await api.getArtistMasters(id, pageNum, 20);

      const newMasters = pageNum === 1
        ? data.results
        : [...masters, ...data.results];

      setMasters(newMasters);
      setTotalMasters(data.total);
      setHasMore(newMasters.length < data.total);
      setPage(pageNum);
    } catch (err) {
      console.error('Ошибка загрузки релизов:', err);
      Alert.alert('Ошибка', 'Не удалось загрузить релизы артиста');
    } finally {
      setIsLoadingMasters(false);
    }
  };

  const handleLoadMore = () => {
    if (hasMore && !isLoadingMasters) {
      loadMasters(page + 1);
    }
  };

  const handleMasterPress = (master: MasterSearchResult) => {
    router.push(`/master/${master.master_id}`);
  };

  const handleFilterPress = (filter: ReleaseFilter) => {
    setActiveFilter(activeFilter === filter ? null : filter);
  };

  const filteredMasters = activeFilter
    ? masters.filter((m) => matchesFilter(m, activeFilter))
    : masters;

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

  // Используем первое изображение в полном разрешении
  const imageUrl = artist.images && artist.images.length > 0 ? artist.images[0] : undefined;

  return (
    <View style={styles.container}>
      <Header title="Артист" showBack />

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + Spacing.xl },
        ]}
        showsVerticalScrollIndicator={false}
        onScroll={({ nativeEvent }) => {
          const { layoutMeasurement, contentOffset, contentSize } = nativeEvent;
          const isCloseToBottom = layoutMeasurement.height + contentOffset.y >= contentSize.height - 100;
          if (isCloseToBottom) {
            handleLoadMore();
          }
        }}
        scrollEventThrottle={400}
      >
        {/* Изображение артиста */}
        <View style={styles.imageContainer}>
          {imageUrl ? (
            <Image
              source={{ uri: imageUrl }}
              style={styles.image}
              resizeMode="cover"
            />
          ) : (
            <View style={styles.placeholderImage}>
              <Ionicons name="person-outline" size={100} color={Colors.textMuted} />
            </View>
          )}
        </View>

        {/* Информация об артисте */}
        <View style={styles.infoSection}>
          <Text style={styles.artistName}>{artist.name}</Text>
        </View>

        {/* Релизы артиста */}
        <View style={styles.releasesSection}>
          <Text style={styles.sectionTitle}>Релизы</Text>

          {/* Фильтры */}
          <View style={styles.filtersRow}>
            {FILTERS.map((f) => (
              <FilterChip
                key={f.key}
                label={f.label}
                isActive={activeFilter === f.key}
                onPress={() => handleFilterPress(f.key)}
              />
            ))}
          </View>

          <View style={styles.releasesGrid}>
            {filteredMasters.map((master) => (
              <RecordCard
                key={master.master_id}
                record={master}
                onPress={() => handleMasterPress(master)}
              />
            ))}
          </View>

          {isLoadingMasters && (
            <View style={styles.loadMoreContainer}>
              <ActivityIndicator size="small" color={Colors.royalBlue} />
              <Text style={styles.loadMoreText}>Загрузка релизов...</Text>
            </View>
          )}

          {!hasMore && filteredMasters.length > 0 && (
            <Text style={styles.endText}>Все релизы загружены</Text>
          )}

          {filteredMasters.length === 0 && !isLoadingMasters && (
            <View style={styles.emptyContainer}>
              <Ionicons name="musical-notes-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>
                {activeFilter ? 'Нет релизов в этой категории' : 'Релизы не найдены'}
              </Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollView: {
    flex: 1,
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
  releasesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
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
  },
});
