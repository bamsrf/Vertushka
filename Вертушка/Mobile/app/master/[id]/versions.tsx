/**
 * Страница со списком всех версий мастер-релиза
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Header } from '../../../components/Header';
import { VersionCard } from '../../../components/VersionCard';
import { api } from '../../../lib/api';
import { toast } from '../../../lib/toast';
import { MasterVersion } from '../../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../../constants/theme';

type FormatFilter = 'all' | 'vinyl' | 'cd' | 'cassette' | 'box_set';

const FORMAT_OPTIONS: { key: FormatFilter; label: string; match: string[] }[] = [
  { key: 'all', label: 'Все', match: [] },
  { key: 'vinyl', label: 'Винил', match: ['Vinyl', 'LP', '12"', '10"', '7"'] },
  { key: 'cd', label: 'CD', match: ['CD'] },
  { key: 'cassette', label: 'Кассета', match: ['Cassette'] },
  { key: 'box_set', label: 'Бокс-сет', match: ['Box Set'] },
];

export default function VersionsScreen() {
  const { id, title, artist, year, cover } = useLocalSearchParams<{
    id: string;
    title?: string;
    artist?: string;
    year?: string;
    cover?: string;
  }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [versions, setVersions] = useState<MasterVersion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(0);
  const [activeFilter, setActiveFilter] = useState<FormatFilter>('all');
  // Retry для обложек: сервер обогащает enriched-кэш фоном (вызов Discogs),
  // занимает ~5-8с. Перезапрашиваем страницу 1 несколько раз с нарастающей
  // задержкой, пока не появятся обложки. nginx local-first ответ отдаёт с
  // no-store, поэтому retry доходит до бэка, а не до кэша.
  const COVER_RETRY_DELAYS = [3000, 4000, 6000, 8000];
  const coverRetryAttempt = useRef(0);
  const coverRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    coverRetryAttempt.current = 0;
    loadVersions();
    return () => {
      if (coverRetryTimer.current) clearTimeout(coverRetryTimer.current);
    };
  }, [id]);

  const loadVersions = async (pageNum = 1) => {
    if (!id) return;
    if (pageNum > 1 && isLoading) return;

    setIsLoading(true);

    try {
      const response = await api.getMasterVersions(id, pageNum, 50);
      const existingLength = pageNum === 1 ? 0 : versions.length;

      if (pageNum === 1) {
        setVersions(response.results);
        setTotal(response.total);

        // Если ни у одной версии нет обложки — значит пришли из дампа без cover.
        // Планируем следующий retry: фоновый _enrich_covers_from_api заполнит
        // Redis-кэш thumb'ами через несколько секунд.
        // enriched-ответ покрывает обложками почти все версии; local-first —
        // лишь те, что уже видели (часто 0-1). Retry'им пока покрыта меньшая
        // часть, чтобы не остановиться на частичном local-first ответе.
        const coveredCount = response.results.filter(
          (v) => v.cover_image_url || v.thumb_image_url
        ).length;
        // Ретраим пока есть хоть одна версия без обложки: бэк добирает stragglers
        // через get_release (~10с) и пишет enriched — следующий retry их подхватит.
        const allCovered = coveredCount >= response.results.length;
        if (!allCovered && coverRetryAttempt.current < COVER_RETRY_DELAYS.length) {
          const delay = COVER_RETRY_DELAYS[coverRetryAttempt.current];
          coverRetryAttempt.current += 1;
          coverRetryTimer.current = setTimeout(() => loadVersions(1), delay);
        }
      } else {
        // Дедуп по release_id: enriched-пагинация может вернуть на стр. N версию,
        // уже отданную на стр. N-1 → дубль ключа в FlatList ("two children with
        // the same key"). Фильтруем уже виденные перед append.
        setVersions((prev) => {
          const seen = new Set(prev.map((v) => v.release_id));
          const fresh = response.results.filter((v) => !seen.has(v.release_id));
          return [...prev, ...fresh];
        });
      }
      setPage(pageNum);
      setHasMore(existingLength + response.results.length < response.total);
    } catch (err) {
      console.error('Error loading versions:', err);
      toast.error('Не удалось загрузить версии');
    } finally {
      setIsLoading(false);
    }
  };

  const loadMoreVersions = () => {
    if (hasMore && !isLoading) {
      loadVersions(page + 1);
    }
  };

  const handleVersionPress = (version: MasterVersion) => {
    router.push({
      pathname: `/record/${version.release_id}`,
      params: {
        previewTitle: version.title || title || '',
        previewArtist: artist || '',
        previewCover: version.cover_image_url || version.thumb_image_url || version.cover_url || cover || '',
        previewYear: version.year?.toString() || year || '',
      },
    });
  };

  const filteredVersions = useMemo(() => {
    if (activeFilter === 'all') return versions;
    const option = FORMAT_OPTIONS.find((o) => o.key === activeFilter);
    if (!option) return versions;
    return versions.filter((v) => {
      const majorFmts = (v.major_formats || []).map((f) => f.toLowerCase());
      const fmtStr = (v.format || '').toLowerCase();
      return option.match.some(
        (m) => majorFmts.includes(m.toLowerCase()) || fmtStr.includes(m.toLowerCase())
      );
    });
  }, [versions, activeFilter]);

  const filteredCount = activeFilter === 'all' ? total : filteredVersions.length;

  return (
    <View style={styles.container}>
      <Header
        title={`Все версии (${filteredCount})`}
        showBack
      />

      <View style={styles.filterBar}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filterScroll}
        >
          {FORMAT_OPTIONS.map((option) => {
            const isActive = activeFilter === option.key;
            return (
              <TouchableOpacity
                key={option.key}
                style={[styles.filterChip, isActive && styles.filterChipActive]}
                onPress={() => setActiveFilter(option.key)}
                activeOpacity={0.7}
              >
                <Text style={[styles.filterChipText, isActive && styles.filterChipTextActive]}>
                  {option.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      <FlatList
        data={filteredVersions}
        keyExtractor={(item) => item.release_id}
        renderItem={({ item }) => (
          <VersionCard
            version={item}
            onPress={() => handleVersionPress(item)}
          />
        )}
        onEndReached={loadMoreVersions}
        onEndReachedThreshold={0.5}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyContainer}>
              <Icon name="disc-outline" size={64} color={Colors.textMuted} />
              <Text style={styles.emptyText}>
                {activeFilter === 'all' ? 'Версии не найдены' : 'Нет версий в этом формате'}
              </Text>
            </View>
          ) : null
        }
        ListFooterComponent={
          isLoading ? (
            <View style={styles.loadingMore}>
              <ActivityIndicator size="small" color={Colors.royalBlue} />
            </View>
          ) : null
        }
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: insets.bottom + Spacing.lg },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.surface,
  },
  filterBar: {
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    backgroundColor: Colors.surface,
  },
  filterScroll: {
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  filterChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: BorderRadius.full,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterChipActive: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  filterChipText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },
  filterChipTextActive: {
    color: '#FFFFFF',
  },
  listContent: {
    padding: Spacing.md,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xl * 2,
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    marginTop: Spacing.md,
  },
  loadingMore: {
    paddingVertical: Spacing.md,
    alignItems: 'center',
  },
});
