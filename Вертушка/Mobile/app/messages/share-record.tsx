/**
 * Bottom-sheet выбора пластинки для шары в диалог.
 *
 * Источники:
 * - «Моя коллекция» — CollectionItem с локальным UUID record.id, отправляем сразу.
 * - «Поиск» — RecordSearchResult с discogs_id; перед отправкой резолвим
 *   discogs_id → локальный record.id через api.getRecordByDiscogsId.
 *
 * После выбора кладём запись в messagesStore.pendingAttach и делаем
 * router.back() — экран треда подхватит выбор через подписку на стор.
 * (Раньше был router.replace с params — он создавал второй экран треда
 * поверх первого, и чаты наслаивались.)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon, SegmentedControl } from '@/components/ui';
import { Colors, Spacing, BorderRadius } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import { api, getCoverUrl } from '../../lib/api';
import { useAuthStore, useCollectionStore } from '../../lib/store';
import { useMessagesStore } from '../../lib/messagesStore';
import { toast } from '../../lib/toast';
import { cleanArtistName } from '../../lib/format';
import type {
  CollectionItem,
  PublicProfileRecord,
  RecordSearchResult,
  VinylRecord,
  WishlistPublicItem,
} from '../../lib/types';

type Source = 'collection' | 'search' | 'wishlist';

const DEBOUNCE_MS = 350;

export default function ShareRecordScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { conversationId, partnerUsername } = useLocalSearchParams<{
    conversationId?: string;
    partnerUsername?: string;
  }>();

  const SEGMENTS: { key: Source; label: string }[] = partnerUsername
    ? [
        { key: 'collection', label: 'Коллекция' },
        { key: 'wishlist', label: 'Вишлист' },
        { key: 'search', label: 'Поиск' },
      ]
    : [
        { key: 'collection', label: 'Коллекция' },
        { key: 'search', label: 'Поиск' },
      ];

  const collectionItems = useCollectionStore((s) => s.collectionItems);
  const fetchCollectionItems = useCollectionStore((s) => s.fetchCollectionItems);
  const isLoadingCollection = useCollectionStore((s) => s.isLoading);

  const [source, setSource] = useState<Source>('collection');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<RecordSearchResult[]>([]);
  const [isLoadingSearch, setIsLoadingSearch] = useState(false);
  const [isPicking, setIsPicking] = useState(false);
  const [wishlistItems, setWishlistItems] = useState<WishlistPublicItem[]>([]);
  const [isLoadingWishlist, setIsLoadingWishlist] = useState(false);
  const [wishlistError, setWishlistError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (source !== 'wishlist' || !partnerUsername) return;
    if (wishlistItems.length > 0 || isLoadingWishlist) return;
    setIsLoadingWishlist(true);
    setWishlistError(null);
    api
      .getUserWishlistByUsername(partnerUsername)
      .then((resp) => {
        setWishlistItems(resp.items || []);
      })
      .catch((e: any) => {
        const detail = e?.response?.data?.detail;
        setWishlistError(
          typeof detail === 'string'
            ? detail
            : 'Вишлист недоступен или скрыт',
        );
      })
      .finally(() => setIsLoadingWishlist(false));
  }, [source, partnerUsername, wishlistItems.length, isLoadingWishlist]);

  useEffect(() => {
    if (collectionItems.length === 0) fetchCollectionItems().catch(() => {});
  }, [collectionItems.length, fetchCollectionItems]);

  useEffect(() => {
    if (source !== 'search') return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setIsLoadingSearch(true);
      try {
        const data = await api.searchRecords(query.trim());
        setResults(data.results);
      } catch {
        setResults([]);
      } finally {
        setIsLoadingSearch(false);
      }
    }, DEBOUNCE_MS);
  }, [query, source]);

  const returnToThread = useCallback(
    (record: VinylRecord) => {
      if (!conversationId) return;
      useMessagesStore.getState().setPendingAttach(conversationId, {
        id: record.id,
        title: record.title,
        artist: cleanArtistName(record.artist) || record.artist,
        year: record.year ?? null,
        cover_image_url: record.cover_image_url ?? null,
        cover_url: null,
      });
      router.back();
    },
    [conversationId, router],
  );

  const pickFromCollection = useCallback(
    (item: CollectionItem) => {
      if (!conversationId) return;
      returnToThread(item.record);
    },
    [conversationId, returnToThread],
  );

  const pickFromSearch = useCallback(
    async (sr: RecordSearchResult) => {
      if (!conversationId || isPicking) return;
      setIsPicking(true);
      try {
        const full = await api.getRecordByDiscogsId(sr.discogs_id);
        returnToThread(full);
      } catch {
        toast.error('Не удалось добавить', 'Попробуйте позже');
      } finally {
        setIsPicking(false);
      }
    },
    [conversationId, isPicking, returnToThread],
  );

  const pickFromWishlist = useCallback(
    (rec: PublicProfileRecord) => {
      if (!conversationId) return;
      // У PublicProfileRecord локальный record.id — UUID, его можно отдавать
      // напрямую в attached_record_id без резолва через discogs_id.
      returnToThread({
        id: rec.id,
        title: rec.title,
        artist: rec.artist,
        year: rec.year ?? null,
        cover_image_url: rec.cover_image_url ?? null,
      } as VinylRecord);
    },
    [conversationId, returnToThread],
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn}>
          <Icon name="x" size={20} color={Colors.text} />
        </TouchableOpacity>
        <Text style={styles.title}>Прикрепить пластинку</Text>
        <View style={{ width: 36 }} />
      </View>

      <SegmentedControl
        segments={SEGMENTS}
        selectedKey={source}
        onSelect={setSource}
        style={styles.segmented}
      />

      {source === 'search' ? (
        <View style={styles.searchWrap}>
          <Icon name="magnifying-glass" size={16} color={Colors.textMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder="Название, артист…"
            placeholderTextColor={Colors.textMuted}
            value={query}
            onChangeText={setQuery}
            autoCapitalize="none"
          />
        </View>
      ) : null}

      {source === 'collection' ? (
        isLoadingCollection ? (
          <ActivityIndicator
            size="small"
            color={Colors.royalBlue}
            style={{ marginTop: Spacing.lg }}
          />
        ) : (
          <FlatList
            data={collectionItems}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <RecordRow
                cover={getCoverUrl(item.record)}
                title={item.record.title}
                artist={item.record.artist}
                year={item.record.year}
                onPress={() => pickFromCollection(item)}
              />
            )}
            ListEmptyComponent={
              <Text style={styles.empty}>Коллекция пуста</Text>
            }
            contentContainerStyle={styles.list}
          />
        )
      ) : source === 'wishlist' ? (
        isLoadingWishlist ? (
          <ActivityIndicator
            size="small"
            color={Colors.royalBlue}
            style={{ marginTop: Spacing.lg }}
          />
        ) : wishlistError ? (
          <Text style={styles.empty}>{wishlistError}</Text>
        ) : (
          <FlatList
            data={wishlistItems}
            keyExtractor={(item) => item.id}
            renderItem={({ item }) => (
              <RecordRow
                cover={item.record.cover_image_url || item.record.cover_url}
                title={item.record.title}
                artist={item.record.artist}
                year={item.record.year}
                onPress={() => pickFromWishlist(item.record)}
              />
            )}
            ListEmptyComponent={
              <Text style={styles.empty}>В вишлисте пусто</Text>
            }
            ListHeaderComponent={
              partnerUsername ? (
                <Text style={styles.wishlistHint}>
                  Из вишлиста @{partnerUsername} — поделитесь тем, что он ищет
                </Text>
              ) : null
            }
            contentContainerStyle={styles.list}
          />
        )
      ) : isLoadingSearch ? (
        <ActivityIndicator
          size="small"
          color={Colors.royalBlue}
          style={{ marginTop: Spacing.lg }}
        />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item) => item.discogs_id}
          renderItem={({ item }) => (
            <RecordRow
              cover={getCoverUrl(item)}
              title={item.title}
              artist={item.artist}
              year={item.year}
              onPress={() => pickFromSearch(item)}
            />
          )}
          ListEmptyComponent={
            query.trim() ? (
              <Text style={styles.empty}>Ничего не нашли</Text>
            ) : null
          }
          contentContainerStyle={styles.list}
        />
      )}

      {isPicking ? (
        <View style={styles.overlay}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
        </View>
      ) : null}
    </View>
  );
}

function RecordRow({
  cover,
  title,
  artist,
  year,
  onPress,
}: {
  cover?: string;
  title: string;
  artist: string;
  year?: number | null;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity activeOpacity={0.7} style={styles.row} onPress={onPress}>
      <View style={styles.coverWrap}>
        {cover ? (
          <Image source={cover} style={styles.cover} cachePolicy="disk" />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]}>
            <Icon name="disc" size={20} color={Colors.textMuted} />
          </View>
        )}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.rowTitle} numberOfLines={1}>
          {title}
        </Text>
        <Text style={styles.rowSub} numberOfLines={1}>
          {cleanArtistName(artist) || artist}
          {year ? ` · ${year}` : ''}
        </Text>
      </View>
      <Icon name="arrow-right" size={16} color={Colors.textMuted} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },

  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: 8,
    gap: Spacing.sm,
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  title: { flex: 1, fontSize: ms(16), fontWeight: '700', color: Colors.text, textAlign: 'center' },

  segmented: { marginHorizontal: Spacing.md, marginVertical: Spacing.sm },

  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  searchInput: { flex: 1, fontSize: ms(14), color: Colors.text },

  list: { paddingHorizontal: Spacing.md, paddingBottom: 60 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: 10,
  },
  coverWrap: {
    width: 48,
    height: 48,
    borderRadius: 6,
    overflow: 'hidden',
    backgroundColor: Colors.surface,
  },
  cover: { width: 48, height: 48 },
  coverPlaceholder: { alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: ms(14), fontWeight: '600', color: Colors.text },
  rowSub: { fontSize: ms(12), color: Colors.textMuted, marginTop: 2 },

  empty: {
    fontSize: ms(13),
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.lg,
  },
  wishlistHint: {
    fontSize: ms(12),
    color: Colors.textMuted,
    marginBottom: Spacing.sm,
    paddingHorizontal: 6,
    fontStyle: 'italic',
  },
  overlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(255,255,255,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
