/**
 * Экран мастер-релиза
 */
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../../components/Header';
import { api } from '../../../lib/api';
import { MasterRelease, Track } from '../../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../../constants/theme';

export default function MasterScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [master, setMaster] = useState<MasterRelease | null>(null);
  const [versionsCount, setVersionsCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadMaster();
    loadVersionsCount();
  }, [id]);

  const loadMaster = async () => {
    if (!id) return;

    setIsLoading(true);
    setError(null);

    const MAX_RETRIES = 2;
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const data = await api.getMaster(id);
        setMaster(data);
        setIsLoading(false);
        return;
      } catch (err: any) {
        const is503 = err?.response?.status === 503;
        if (is503 && attempt < MAX_RETRIES) {
          await new Promise(resolve => setTimeout(resolve, 1500));
          continue;
        }
        console.error('Error loading master:', err);
        setError('Не удалось загрузить мастер-релиз');
        setIsLoading(false);
        return;
      }
    }
  };

  const loadVersionsCount = async () => {
    if (!id) return;

    try {
      const response = await api.getMasterVersions(id, 1, 1);
      setVersionsCount(response.total);
    } catch (err) {
      console.error('Error loading versions count:', err);
    }
  };

  const handleAllVersionsPress = () => {
    router.push(`/master/${id}/versions`);
  };

  const handleArtistPress = () => {
    if (master?.artist_id) {
      router.push(`/artist/${master.artist_id}`);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.container}>
        <Header title="Мастер-релиз" showBack />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
        </View>
      </View>
    );
  }

  if (error || !master) {
    return (
      <View style={styles.container}>
        <Header title="Мастер-релиз" showBack />
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle-outline" size={64} color={Colors.error} />
          <Text style={styles.errorText}>{error || 'Мастер-релиз не найден'}</Text>
          {error && (
            <TouchableOpacity style={styles.retryButton} onPress={loadMaster} activeOpacity={0.7}>
              <Text style={styles.retryButtonText}>Повторить</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  }

  const imageUrl = master.cover_image_url;

  return (
    <View style={styles.container}>
      <Header
        title="Мастер-релиз"
        showBack
      />

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + Spacing.lg },
        ]}
      >
        {/* Обложка */}
        <View style={styles.coverContainer}>
          {imageUrl ? (
            <Image
              source={imageUrl}
              style={styles.cover}
              contentFit="cover"
              cachePolicy="disk"
            />
          ) : (
            <View style={styles.coverPlaceholder}>
              <Ionicons name="disc-outline" size={100} color={Colors.textMuted} />
            </View>
          )}
        </View>

        {/* Название альбома */}
        <View style={styles.info}>
          <Text style={styles.title}>{master.title}</Text>
        </View>

        {/* Блок артиста */}
        <TouchableOpacity
          style={styles.artistCard}
          onPress={handleArtistPress}
          activeOpacity={master.artist_id ? 0.7 : 1}
          disabled={!master.artist_id}
        >
          {master.artist_thumb_image_url ? (
            <Image
              source={master.artist_thumb_image_url}
              style={styles.artistAvatar}
              contentFit="cover"
              cachePolicy="disk"
            />
          ) : (
            <View style={styles.artistAvatarPlaceholder}>
              <Ionicons name="person" size={24} color={Colors.textMuted} />
            </View>
          )}
          <Text style={styles.artistName}>{master.artist}</Text>
        </TouchableOpacity>

        {/* First Released */}
        {master.year && (
          <View style={styles.firstReleasedSection}>
            <Text style={styles.firstReleasedLabel}>First Released</Text>
            <Text style={styles.firstReleasedYear}>{master.year}</Text>
          </View>
        )}

        {/* Кнопка просмотра всех версий */}
        <TouchableOpacity
          style={styles.allVersionsButton}
          onPress={handleAllVersionsPress}
          activeOpacity={0.7}
        >
          <View style={styles.allVersionsContent}>
            <Text style={styles.allVersionsTitle}>Все версии</Text>
            {versionsCount > 0 && (
              <Text style={styles.allVersionsCount}>({versionsCount})</Text>
            )}
          </View>
          <Ionicons name="chevron-forward" size={24} color={Colors.text} />
        </TouchableOpacity>

        {/* Genres */}
        {master.genres && master.genres.length > 0 && (
          <View style={styles.genresSection}>
            <Text style={styles.sectionTitle}>Genres:</Text>
            <View style={styles.genresContainer}>
              {master.genres.map((genre, index) => (
                <View key={index} style={styles.genreTag}>
                  <Text style={styles.genreText}>{genre}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Styles */}
        {master.styles && master.styles.length > 0 && (
          <View style={styles.stylesSection}>
            <Text style={styles.sectionTitle}>Стили:</Text>
            <Text style={styles.stylesText}>{master.styles.join(', ')}</Text>
          </View>
        )}

        {/* Треклист */}
        {master.tracklist && master.tracklist.length > 0 && (
          <View style={styles.tracklistSection}>
            <Text style={styles.sectionTitle}>Треклист</Text>
            {master.tracklist.map((track, index) => (
              <View key={index} style={styles.trackRow}>
                <Text style={styles.trackPosition}>{track.position || index + 1}</Text>
                <Text style={styles.trackTitle} numberOfLines={1}>
                  {track.title}
                </Text>
                {track.duration ? (
                  <Text style={styles.trackDuration}>{track.duration}</Text>
                ) : null}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.surface,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.surface,
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    padding: Spacing.xl,
  },
  errorText: {
    ...Typography.body,
    color: Colors.error,
    marginTop: Spacing.md,
    textAlign: 'center',
  },
  retryButton: {
    marginTop: Spacing.lg,
    backgroundColor: Colors.royalBlue,
    paddingHorizontal: Spacing.xl,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.md,
  },
  retryButtonText: {
    ...Typography.body,
    color: Colors.background,
    fontWeight: '600',
  },
  scrollContent: {
    padding: Spacing.md,
  },
  coverContainer: {
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  cover: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.surface,
  },
  coverPlaceholder: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  info: {
    marginBottom: Spacing.md,
  },
  title: {
    ...Typography.h2,
    color: Colors.text,
  },
  artistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    padding: Spacing.sm,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  artistAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
  },
  artistAvatarPlaceholder: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: Colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  artistName: {
    ...Typography.body,
    color: Colors.text,
    fontWeight: '500',
    flex: 1,
  },
  firstReleasedSection: {
    marginBottom: Spacing.md,
  },
  firstReleasedLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginBottom: 2,
  },
  firstReleasedYear: {
    ...Typography.h3,
    color: Colors.text,
  },
  sectionTitle: {
    ...Typography.body,
    color: Colors.text,
    fontWeight: '600',
    marginBottom: Spacing.xs,
  },
  genresSection: {
    marginTop: Spacing.md,
  },
  genresContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.xs,
  },
  genreTag: {
    backgroundColor: Colors.textSecondary,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    borderRadius: BorderRadius.sm,
  },
  genreText: {
    ...Typography.caption,
    color: Colors.background,
  },
  stylesSection: {
    marginTop: Spacing.md,
  },
  stylesText: {
    ...Typography.body,
    color: Colors.textMuted,
  },
  tracklistSection: {
    marginTop: Spacing.md,
  },
  trackRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  trackPosition: {
    ...Typography.caption,
    color: Colors.textMuted,
    width: 30,
  },
  trackTitle: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  trackDuration: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginLeft: Spacing.sm,
  },
  allVersionsButton: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.sm,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  allVersionsContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  allVersionsTitle: {
    ...Typography.body,
    color: Colors.text,
    fontWeight: '500',
  },
  allVersionsCount: {
    ...Typography.body,
    color: Colors.textMuted,
  },
});
