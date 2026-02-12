/**
 * Экран детальной информации об артисте
 */
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../components/Header';
import { RecordCard } from '../../components/RecordCard';
import { api } from '../../lib/api';
import { Artist, MasterSearchResult } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

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

  if (isLoading) {
    return (
      <View style={styles.container}>
        <Header title="Артист" showBack />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.primary} />
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
          <Text style={styles.sectionTitle}>Релизы ({masters.length})</Text>

          <View style={styles.releasesGrid}>
            {masters.map((master) => (
              <RecordCard
                key={master.master_id}
                record={master}
                onPress={() => handleMasterPress(master)}
              />
            ))}
          </View>

          {isLoadingMasters && (
            <View style={styles.loadMoreContainer}>
              <ActivityIndicator size="small" color={Colors.primary} />
              <Text style={styles.loadMoreText}>Загрузка релизов...</Text>
            </View>
          )}

          {!hasMore && masters.length > 0 && (
            <Text style={styles.endText}>Все релизы загружены</Text>
          )}

          {masters.length === 0 && !isLoadingMasters && (
            <View style={styles.emptyContainer}>
              <Ionicons name="musical-notes-outline" size={48} color={Colors.textMuted} />
              <Text style={styles.emptyText}>Релизы не найдены</Text>
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
  profileContainer: {
    width: '100%',
    marginTop: Spacing.md,
  },
  sectionTitle: {
    ...Typography.h3,
    color: Colors.text,
    marginBottom: Spacing.sm,
  },
  profileText: {
    ...Typography.body,
    color: Colors.textSecondary,
    lineHeight: 22,
  },
  releasesSection: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.lg,
  },
  releasesGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginTop: Spacing.md,
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
