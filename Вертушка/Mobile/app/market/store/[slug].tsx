/**
 * /market/store/[slug] — полная витрина одного магазина в Маркете.
 *
 * Layout:
 *   Back-arrow (← Маркет) + header (StoreLogo 64 + название + метрики)
 *   MarketSearchInput (поиск ВНУТРИ магазина)
 *   FormatChips (Все / Винил / CD / Кассеты)
 *   Sticky пагинированная сетка 2 колонки с in_stock-листингами магазина
 *
 * Фон — market-палитра (без magic transition — мы уже «в маркете»).
 *
 * Источник: docs/plans/MARKET_AND_PRICE_DRAWER.md §1.12 + screens-market.jsx
 * (ScreenStorePage из Design Claude handoff).
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  FlatList,
  Image,
  Keyboard,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import MaskedView from '@react-native-masked-view/masked-view';

import { Icon } from '@/components/ui';
import { api, resolveMediaUrl } from '../../../lib/api';
import { MarketPalette } from '../../../constants/theme';
import { ms } from '../../../lib/responsive';
import type {
  MarketSearchItem,
  MarketStoreInfo,
  MarketFormatFilter,
} from '../../../lib/types';

import MarketBackground from '../../../components/market/MarketBackground';
import StoreLogo, { getStoreName } from '../../../components/market/StoreLogo';
import MarketSearchInput from '../../../components/market/MarketSearchInput';
import FormatChips from '../../../components/market/FormatChips';
import MiniPriceBadge from '../../../components/MiniPriceBadge';

const PAGE_SIZE = 30;

export default function StorePage() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { slug: rawSlug } = useLocalSearchParams<{ slug: string }>();
  const slug = String(rawSlug ?? '');

  const [storeInfo, setStoreInfo] = useState<MarketStoreInfo | null>(null);
  const [items, setItems] = useState<MarketSearchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);

  const [searchValue, setSearchValue] = useState('');
  // debouncedQuery — отдельный от searchValue, обновляется через 400ms тишины.
  // Без этого useEffect re-fetch'ил после каждого keystroke → setLoading(true)
  // → FlatList re-renderил → keyboard dismiss. Юзер не мог дописать слово.
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [format, setFormat] = useState<MarketFormatFilter | 'all'>('all');
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebouncedQuery(searchValue.trim());
    }, 400);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchValue]);

  // Загружаем метаданные магазина — фильтруем из общего getMarketStores'а.
  useEffect(() => {
    let cancelled = false;
    api.getMarketStores(0).then((stores) => {
      if (cancelled) return;
      const found = stores.find((s) => s.slug === slug) ?? null;
      setStoreInfo(found);
    }).catch(() => {
      /* fallback на slug из registry */
    });
    return () => { cancelled = true; };
  }, [slug]);

  // Загружаем листинги при mount + при изменении фильтров/debounced поиска.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setOffset(0);
    api.getStoreAll(slug, {
      q: debouncedQuery.length >= 2 ? debouncedQuery : undefined,
      format: format === 'all' ? null : format,
      sort: 'price_asc',
      limit: PAGE_SIZE,
      offset: 0,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res);
        setHasMore(res.length === PAGE_SIZE);
        setOffset(res.length);
      })
      .catch(() => { if (!cancelled) setItems([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [slug, format, debouncedQuery]);

  const loadMore = async () => {
    if (loadingMore || !hasMore || loading) return;
    setLoadingMore(true);
    try {
      const more = await api.getStoreAll(slug, {
        q: debouncedQuery.length >= 2 ? debouncedQuery : undefined,
        format: format === 'all' ? null : format,
        sort: 'price_asc',
        limit: PAGE_SIZE,
        offset,
      });
      setItems((cur) => [...cur, ...more]);
      setHasMore(more.length === PAGE_SIZE);
      setOffset((cur) => cur + more.length);
    } finally {
      setLoadingMore(false);
    }
  };

  const displayName = storeInfo?.name ?? getStoreName(slug) ?? slug;
  const subtitle = useMemo(() => {
    if (!storeInfo) return '';
    const avgRub = storeInfo.avg_price_rub != null
      ? Math.round(Number(storeInfo.avg_price_rub))
      : null;
    const parts = [
      `В наличии · ${formatCount(storeInfo.in_stock_count)} пластинок`,
    ];
    if (avgRub) parts.push(`ср. цена ${formatCount(avgRub)} ₽`);
    return parts.join(' · ');
  }, [storeInfo]);

  const renderHeader = () => (
    <SafeAreaView edges={['top']} style={styles.headerWrap}>
      {/* Back-arrow row */}
      <View style={styles.backRow}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel="Назад к Маркету"
          style={styles.backBtn}
        >
          <Icon name="caret-left" size={18} color="onBrand" />
        </Pressable>
        <Text style={styles.backLabel}>← Маркет</Text>
      </View>

      {/* Store header */}
      <View style={styles.storeRow}>
        <StoreLogo slug={slug} size={64} radius={14} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={styles.storeName} numberOfLines={1}>
            {displayName}
          </Text>
          {!!subtitle && (
            <Text style={styles.storeMeta} numberOfLines={2}>
              {subtitle}
            </Text>
          )}
          {storeInfo && storeInfo.new_today_count > 0 && (
            <View style={styles.newTodayRow}>
              <Icon name="sparkle" size={10} color="accent" />
              <Text style={styles.newTodayText}>
                +{storeInfo.new_today_count} за последние 24 ч
              </Text>
            </View>
          )}
        </View>
      </View>

      {/* Search + chips */}
      <View style={{ marginTop: 18 }}>
        <MarketSearchInput
          value={searchValue}
          onChangeText={setSearchValue}
          placeholder={`Найти в ${displayName}…`}
          onSubmit={Keyboard.dismiss}
        />
        <FormatChips value={format} onChange={setFormat} />
      </View>
    </SafeAreaView>
  );

  const renderItem = ({ item }: { item: MarketSearchItem }) => (
    <Pressable
      style={styles.card}
      onPress={() => router.push(`/record/${item.discogs_id ?? item.record_id}` as any)}
      accessibilityRole="button"
    >
      <View style={styles.coverWrap}>
        {item.cover_image_url ? (
          <Image source={{ uri: resolveMediaUrl(item.cover_image_url) ?? item.cover_image_url ?? '' }} style={styles.cover} resizeMode="cover" />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]} />
        )}
      </View>
      <View style={styles.cardText}>
        <Text style={styles.artist} numberOfLines={1}>
          {item.artist.toUpperCase()}
        </Text>
        <Text style={styles.title} numberOfLines={2}>
          {item.title}
        </Text>
        <View style={styles.metaRow}>
          {item.year != null && <Text style={styles.metaText}>{item.year}</Text>}
          {item.year != null && item.format_type && <View style={styles.metaDot} />}
          {item.format_type && (
            <Text style={styles.metaText} numberOfLines={1}>{item.format_type}</Text>
          )}
        </View>
        <View style={{ marginTop: 6 }}>
          <MiniPriceBadge price={Number(item.min_price_rub)} size={11} color="#FFFFFF" />
        </View>
      </View>
    </Pressable>
  );

  return (
    <View style={styles.root}>
      <MarketBackground forcedMode="market" />

      {/* Top safe-area blur strip — закрывает контент под статус-баром
          при скролле. zIndex выше FlatList. Нижний край размыт в
          прозрачность через MaskedView — без резкой линии-среза. */}
      <MaskedView
        style={[styles.topSafeBlur, { height: insets.top + 24 }]}
        pointerEvents="none"
        maskElement={
          <LinearGradient
            colors={['#000', '#000', 'transparent']}
            locations={[0, 0.6, 1]}
            style={{ flex: 1 }}
          />
        }
      >
        <BlurView intensity={24} tint="dark" style={{ flex: 1 }} />
        <LinearGradient
          colors={['rgba(14,7,38,0.55)', 'rgba(14,7,38,0)']}
          locations={[0, 1]}
          style={StyleSheet.absoluteFill}
        />
      </MaskedView>

      {/* Header ВНЕ FlatList — иначе re-render списка на каждый refetch
          re-mount'ает MarketSearchInput → клавиатура дисмиссится на
          каждой букве. Header stick'ается сверху, FlatList скроллится
          под ним. */}
      {renderHeader()}

      <FlatList
        data={items}
        renderItem={renderItem}
        keyExtractor={(it, index) => `${it.record_id}_${index}`}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          loading ? null : (
            <Pressable style={styles.empty} onPress={Keyboard.dismiss}>
              <Text style={styles.emptyText}>
                {searchValue.length >= 2
                  ? `Ничего не найдено по «${searchValue}»`
                  : 'В магазине пока нет товаров с выбранным фильтром'}
              </Text>
            </Pressable>
          )
        }
        ListFooterComponent={
          loadingMore ? <Text style={styles.footerLoading}>Загружаем ещё…</Text> : null
        }
        onEndReached={loadMore}
        onEndReachedThreshold={0.4}
        showsVerticalScrollIndicator={false}
        // keyboardShouldPersistTaps="always" — иначе тап по карточке при
        // открытой клавиатуре сначала её закрывает, а только потом срабатывает.
        // keyboardDismissMode="on-drag" — драг списка прячет клавиатуру.
        // Re-render списка на refetch не дисмиссит focus, потому что debouncedQuery
        // обновляется только через 400ms тишины (см. useEffect выше).
        keyboardShouldPersistTaps="always"
        keyboardDismissMode="on-drag"
      />
    </View>
  );
}

function formatCount(n: number): string {
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: MarketPalette.void,
  },
  listContent: {
    paddingBottom: 60,
  },
  headerWrap: {
    paddingHorizontal: 0,
    paddingBottom: 8,
  },
  backRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 20,
    marginBottom: 18,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 9999,
    backgroundColor: 'rgba(255,255,255,0.10)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: MarketPalette.chrome.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backLabel: {
    fontFamily: 'Inter_700Bold',
    fontSize: 11,
    fontWeight: '700',
    color: MarketPalette.chrome.textMuted,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  storeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    paddingHorizontal: 20,
  },
  storeName: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: ms(22),
    fontWeight: '800',
    color: MarketPalette.chrome.textPrimary,
    letterSpacing: -0.4,
    lineHeight: ms(24),
  },
  storeMeta: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(11.5),
    color: 'rgba(255,255,255,0.65)',
    marginTop: 4,
  },
  newTodayRow: {
    marginTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  newTodayText: {
    fontFamily: 'Inter_700Bold',
    fontSize: 10.5,
    color: '#FFD9C8',
  },
  row: {
    paddingHorizontal: 12,
    justifyContent: 'flex-start',
    gap: 8,
  },
  card: {
    // НЕ flex:1 — иначе FlatList с numColumns=2 при odd count last item
    // растягивает карточку на всю ширину. Фиксированный 48% (50% минус половина gap).
    width: '48%',
    marginBottom: 12,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: 14,
    overflow: 'hidden',
    padding: 8,
  },
  // Top safe-area blur strip — закрывает scrollable контент под статус-баром
  // когда юзер скроллит вниз. Иначе текст карточек наезжает на 9:41/wifi.
  topSafeBlur: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    zIndex: 50,
  },
  coverWrap: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 10,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.06)',
  },
  cover: { width: '100%', height: '100%' },
  coverPlaceholder: { backgroundColor: 'rgba(255,255,255,0.10)' },
  cardText: {
    marginTop: 8,
  },
  artist: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 9,
    fontWeight: '600',
    color: 'rgba(255,255,255,0.65)',
    letterSpacing: 0.3,
    marginBottom: 2,
  },
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(12),
    fontWeight: '700',
    color: '#FFFFFF',
    lineHeight: ms(15),
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 4,
  },
  metaText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 10,
    color: 'rgba(255,255,255,0.55)',
  },
  metaDot: {
    width: 2, height: 2, borderRadius: 1,
    backgroundColor: 'rgba(255,255,255,0.40)',
  },
  empty: {
    paddingHorizontal: 32,
    paddingVertical: 64,
    alignItems: 'center',
  },
  emptyText: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(14),
    color: 'rgba(255,255,255,0.70)',
    textAlign: 'center',
  },
  footerLoading: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(12),
    color: 'rgba(255,255,255,0.55)',
    textAlign: 'center',
    paddingVertical: 16,
  },
});
