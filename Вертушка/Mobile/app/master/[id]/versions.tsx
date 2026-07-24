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
import { takeVersionsPrefetch } from '../../../lib/versionsPrefetch';
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

  // Первая отрисовка из префетча мастер-экрана — список появляется в тот же
  // кадр, что и сам экран, без спиннера. Ниже loadVersions всё равно сходит на
  // бэк и перезапишет данные свежими (обложки/флаги могли долечиться).
  const prefetched = useMemo(() => (id ? takeVersionsPrefetch(id) : null), [id]);
  const [versions, setVersions] = useState<MasterVersion[]>(prefetched?.results ?? []);
  const [isLoading, setIsLoading] = useState(!prefetched);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [total, setTotal] = useState(prefetched?.total ?? 0);
  const [activeFilter, setActiveFilter] = useState<FormatFilter>('all');
  // Retry обложек: бэк добирает covers фоном (thumbs + get_release ~10-15с) и
  // пишет enriched-кэш. Перезапрашиваем КАЖДУЮ загруженную страницу — не только
  // первую: пагинация (page 2+) тоже приходит без части обложек (винил-репрессы
  // с пустым thumb), а старый retry дёргал только page 1, поэтому они навсегда
  // оставались закрывашками. Мёржим covers по release_id, пока на странице есть
  // непокрытые. nginx local-first отдаёт no-store → retry доходит до бэка.
  const COVER_RETRY_DELAYS = [3000, 4000, 6000, 8000];
  const coverRetryAttempts = useRef<Record<number, number>>({});
  const coverRetryTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    coverRetryAttempts.current = {};
    loadVersions(1, Boolean(prefetched));
    return () => {
      coverRetryTimers.current.forEach(clearTimeout);
      coverRetryTimers.current = [];
    };
  }, [id]);

  // Обновляет обложки уже загруженных версий по release_id, не трогая порядок,
  // длину списка и уже покрытые карточки.
  const mergeCovers = (results: MasterVersion[]) => {
    const byId = new Map(results.map((v) => [v.release_id, v] as const));
    setVersions((prev) =>
      prev.map((v) => {
        if (v.cover_image_url || v.thumb_image_url) return v;
        const u = byId.get(v.release_id);
        if (u && (u.cover_image_url || u.thumb_image_url)) {
          return { ...v, cover_image_url: u.cover_image_url, thumb_image_url: u.thumb_image_url };
        }
        return v;
      }),
    );
  };

  const scheduleCoverRetry = (pageNum: number, results: MasterVersion[]) => {
    const hasUncovered = results.some((v) => !(v.cover_image_url || v.thumb_image_url));
    const attempt = coverRetryAttempts.current[pageNum] ?? 0;
    if (!hasUncovered || attempt >= COVER_RETRY_DELAYS.length) return;
    coverRetryAttempts.current[pageNum] = attempt + 1;
    const timer = setTimeout(async () => {
      try {
        // fresh=true — ретрай обязан пробивать nginx-кэш: частичный ответ теперь
        // кэшируется на 60с (раньше был no-store), и без cache-buster'а ретрай
        // получил бы ту же версию с дырами вместо долеченной.
        const resp = await api.getMasterVersions(id, pageNum, 50, true);
        mergeCovers(resp.results);
        scheduleCoverRetry(pageNum, resp.results);
      } catch {
        /* covers подтянутся при следующем заходе */
      }
    }, COVER_RETRY_DELAYS[attempt]);
    coverRetryTimers.current.push(timer);
  };

  // silent — фоновое обновление поверх префетча: список уже на экране, спиннер
  // поверх него был бы регрессом ощущаемой скорости.
  const loadVersions = async (pageNum = 1, silent = false) => {
    if (!id) return;
    if (pageNum > 1 && isLoading) return;

    if (!silent) setIsLoading(true);

    try {
      const response = await api.getMasterVersions(id, pageNum, 50);
      const existingLength = pageNum === 1 ? 0 : versions.length;

      if (pageNum === 1) {
        setVersions(response.results);
        setTotal(response.total);
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
      // Догрузка обложек для ЭТОЙ страницы (page 1 и пагинация — одинаково).
      scheduleCoverRetry(pageNum, response.results);
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
