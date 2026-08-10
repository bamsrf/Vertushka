/**
 * MarketMain — переиспользуемый контент Маркета.
 *
 * Один и тот же компонент рендерится:
 *   • в стэндалоне /market (route);
 *   • как нижний слой в (tabs)/search (layer composition с curtain'ой).
 *
 * Не рендерит ни фон, ни curtain — это забота parent'а. Внутри:
 *   • Загрузка списка магазинов и search-результатов.
 *   • AnimatedFlatList: в шапке — MarketSection (поиск, фильтры, карусели), в
 *     data — сетка результатов с бесконечной подгрузкой (useMarketPagination).
 *
 * parent передаёт `onScroll` для overdrag-detection (top → exit, bottom не
 * используется) и `paddingTop` для выравнивания заголовка МАРКЕТ с
 * соответствующим местом в Поиске.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, Keyboard, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import Animated, {
  Extrapolation,
  interpolate,
  useAnimatedStyle,
  type SharedValue,
} from 'react-native-reanimated';

import { Icon } from '../ui/Icon';
import { analytics } from '../../lib/analytics';
import { api, resolveMediaUrl } from '../../lib/api';
import { STORES_TTL_MS, useMarketStore } from '../../lib/marketStore';
import type { MarketSearchItem, MarketFilters, MarketFacetsResponse } from '../../lib/types';
import { EMPTY_MARKET_FILTERS, hasActiveFilters } from '../../lib/types';

import { useMarketPagination } from '../../lib/useMarketPagination';
import MarketSection, { type MarketStoreData } from './MarketSection';
import MarketResultCard, { marketGridStyles } from './MarketResultCard';

const AnimatedFlatList = Animated.createAnimatedComponent(FlatList);

// Стабильная ссылка на пустой список: `[]` инлайном создавал бы новый массив
// на каждый рендер и заставлял FlatList пересобирать ячейки впустую.
const NO_ITEMS: MarketSearchItem[] = [];

interface MarketMainProps {
  /** Reanimated scroll handler от parent'а (для overdrag-curtain'ы). */
  onScroll?: any;
  /** Активный ли FlatList сейчас (можно скроллить). */
  scrollEnabled?: boolean;
  /** Padding сверху списка — выравнивание заголовка под status-bar или ПОИСК. */
  paddingTop: number;
  /**
   * 0..1 — текущий pull-down progress сверху Маркета (overdrag).
   * Если передан — рендерится exit-hint с progress-баром НАД заголовком
   * МАРКЕТ (через negative margin, чтобы не толкать heading вниз).
   * Hint видим только во время pull'а.
   */
  pullFraction?: SharedValue<number>;
}

// ─── Exit hint ─────────────────────────────────────────────────────────
function MarketExitHint({ pullFraction }: { pullFraction: SharedValue<number> }) {
  const hintStyle = useAnimatedStyle(() => {
    const p = Math.min(1, pullFraction.value);
    return {
      // Маркер появляется чуть позже первого касания, чтобы не моргал при
      // случайных микро-скроллах.
      opacity: interpolate(p, [0, 0.15, 1], [0, 1, 1], Extrapolation.CLAMP),
      transform: [
        // На 100% pull'а блок чуть приподнимается — тактильный отклик
        // «готово, можно отпускать».
        { scale: interpolate(p, [0, 1], [0.96, 1], Extrapolation.CLAMP) },
      ],
    };
  });

  const fillStyle = useAnimatedStyle(() => ({
    transform: [{ scaleX: Math.min(1, pullFraction.value) }],
  }));

  return (
    <Animated.View pointerEvents="none" style={[hintStyles.anchor]}>
      <Animated.View style={[hintStyles.card, hintStyle]}>
        <View style={hintStyles.row}>
          <Icon name="chevron-down" size={16} color="onBrand" style={{ opacity: 0.85 }} />
          <Text style={hintStyles.text}>
            Потяни вниз, чтобы вернуться в <Text style={hintStyles.brand}>Поиск</Text>
          </Text>
        </View>
        <View style={hintStyles.progressTrack}>
          <Animated.View style={[hintStyles.progressFill, fillStyle]} />
        </View>
      </Animated.View>
    </Animated.View>
  );
}

const HINT_HEIGHT = 56;
// Gap между hint card'ом и МАРКЕТ heading'ом — чтобы плашка не прилипала
// вплотную к заголовку, дышит.
const HINT_GAP = 14;

const hintStyles = StyleSheet.create({
  // Anchor — занимает HINT_HEIGHT + HINT_GAP и одновременно «вытягивает» себя
  // наверх через negative margin: net layout-эффект = 0, МАРКЕТ heading не
  // сдвигается. Card сидит сверху (flex-start), padding снизу даёт зазор от
  // следующего за anchor'ом контента (заголовка МАРКЕТ).
  anchor: {
    height: HINT_HEIGHT + HINT_GAP,
    marginTop: -(HINT_HEIGHT + HINT_GAP),
    marginHorizontal: 16,
    paddingBottom: HINT_GAP,
    justifyContent: 'flex-end',
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.10)',
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.18)',
    paddingVertical: 10,
    paddingHorizontal: 14,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  text: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: 'rgba(255,255,255,0.85)',
    letterSpacing: 0.1,
  },
  brand: {
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    fontWeight: '700',
  },
  progressTrack: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  progressFill: {
    position: 'absolute',
    top: 0,
    left: 0,
    bottom: 0,
    width: '100%',
    backgroundColor: '#FFFFFF',
    // @ts-ignore transformOrigin поддерживается RN 0.71+
    transformOrigin: 'left',
  },
});

export function MarketMain({ onScroll, scrollEnabled = true, paddingTop, pullFraction }: MarketMainProps) {
  const router = useRouter();

  // Карусели магазинов — в marketStore (in-memory кэш переживает remount
  // экрана /market, рендер мгновенный; re-fetch тихо в фоне по TTL).
  const marketStores = useMarketStore((s) => s.stores);
  const setMarketStores = useMarketStore((s) => s.setStores);
  const [marketSearch, setMarketSearch] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [filters, setFilters] = useState<MarketFilters>(EMPTY_MARKET_FILTERS);
  const [facets, setFacets] = useState<MarketFacetsResponse | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Знаменатель воронки Маркета: без него market_record_open и offer_click не с
  // чем сравнивать. Mount-only — компонент живёт и в /market, и слоем в Поиске,
  // так что это «Маркет показан», а не «переход по роуту».
  useEffect(() => {
    analytics.viewMarket();
  }, []);

  // Фасеты (доступные жанры/особенности со счётчиками) — грузим один раз при
  // маунте. Ошибку глотаем: FilterBar просто не покажет жанр/особенности.
  useEffect(() => {
    let cancelled = false;
    api.getMarketFacets()
      .then((res) => { if (!cancelled) setFacets(res); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebouncedQuery(marketSearch.trim());
    }, 400);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [marketSearch]);

  useEffect(() => {
    // Кэш свежий — пропускаем fetch, рендерим то что есть. Читаем через
    // getState(): эффект mount-only, подписка на эти поля тут не нужна.
    const cached = useMarketStore.getState();
    const fresh =
      cached.storesFetchedAt !== null &&
      Date.now() - cached.storesFetchedAt < STORES_TTL_MS;
    if (fresh && cached.stores.length > 0) return;

    let cancelled = false;
    (async () => {
      try {
        const stores = await api.getMarketStores(1);
        const carousels: (MarketStoreData | null)[] = await Promise.all(
          stores.map(async (store) => {
            try {
              const items = await api.getStoreListings(store.slug, { limit: 15, sort: 'newest' });
              return {
                slug: store.slug,
                name: store.name,
                totalCount: store.in_stock_count,
                items: items.map((it) => ({
                  id: it.record_id,
                  artist: it.artist,
                  title: it.title,
                  year: it.year ?? null,
                  format: it.format_type ?? null,
                  coverUrl: it.cover_image_url ? resolveMediaUrl(it.cover_image_url) ?? null : null,
                  priceRub: Number(it.min_price_rub),
                })),
              } as MarketStoreData;
            } catch { return null; }
          }),
        );
        if (!cancelled) {
          setMarketStores(carousels.filter((c): c is MarketStoreData => c !== null && c.items.length > 0));
        }
      } catch { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const isSearchActive = useMemo(() => {
    return debouncedQuery.length >= 2 || hasActiveFilters(filters);
  }, [debouncedQuery, filters]);

  // Сериализуем фильтры в стабильный ключ — иначе новый объект filters на
  // каждый рендер сбрасывал бы пагинацию.
  const filtersKey = useMemo(
    () => `${filters.format}|${[...filters.genres].sort().join(',')}|${[...filters.features].sort().join(',')}`,
    [filters],
  );
  const effectiveQuery = debouncedQuery.length >= 2 ? debouncedQuery : '';

  const fetchSearchPage = useCallback(
    (offset: number, limit: number) =>
      api.searchMarket({
        q: effectiveQuery || undefined,
        format: filters.format === 'all' ? null : filters.format,
        genres: filters.genres,
        features: filters.features,
        sort: 'price_asc',
        limit,
        offset,
      }),
    [effectiveQuery, filters],
  );

  const {
    items: searchItems,
    loading: searchLoading,
    loadingMore,
    reachedEnd,
    loadMore,
  } = useMarketPagination({
    enabled: isSearchActive,
    resetKey: `${effectiveQuery}|${filtersKey}`,
    fetchPage: fetchSearchPage,
  });

  const handleStorePress = useCallback((slug: string) => {
    analytics.viewMarketStore(slug);
    router.push(`/market/store/${slug}` as any);
  }, [router]);
  const handleItemPress = useCallback((item: { id: string }) => {
    analytics.marketRecordOpen({ record_ref: item.id, from: 'market' });
    router.push(`/record/${item.id}` as any);
  }, [router]);
  const handleSearchItemPress = useCallback((item: MarketSearchItem) => {
    const ref = item.discogs_id ?? item.record_id;
    analytics.marketRecordOpen({ record_ref: ref, from: 'market' });
    router.push(`/record/${ref}` as any);
  }, [router]);

  const renderSearchItem = useCallback(
    ({ item }: { item: MarketSearchItem }) => (
      <MarketResultCard item={item} onPress={handleSearchItemPress} showStore />
    ),
    [handleSearchItemPress],
  );

  return (
    <AnimatedFlatList
      // Результаты живут в data (а не в шапке) — только так FlatList знает
      // длину списка и дёргает onEndReached для подгрузки следующей страницы.
      // Когда фильтров нет, сетка пуста и виден обычный состав Маркета.
      data={(isSearchActive ? searchItems : NO_ITEMS) as any}
      keyExtractor={(item: any) => (item as MarketSearchItem).record_id}
      renderItem={renderSearchItem as any}
      numColumns={2}
      columnWrapperStyle={marketGridStyles.row}
      contentContainerStyle={{ paddingBottom: 120 }}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      scrollEnabled={scrollEnabled}
      onScroll={onScroll}
      scrollEventThrottle={16}
      bounces
      alwaysBounceVertical
      overScrollMode="always"
      onEndReached={isSearchActive ? loadMore : undefined}
      onEndReachedThreshold={0.6}
      ListEmptyComponent={
        isSearchActive ? (
          <View style={styles.searchState}>
            {searchLoading ? (
              <ActivityIndicator size="small" color="rgba(255,255,255,0.65)" />
            ) : (
              <Text style={styles.searchStateText}>
                {effectiveQuery
                  ? `Ничего не найдено по «${effectiveQuery}»`
                  : 'Под выбранными фильтрами ничего нет в наличии'}
              </Text>
            )}
          </View>
        ) : null
      }
      ListFooterComponent={
        isSearchActive && searchItems.length > 0 ? (
          <View style={styles.footer}>
            {loadingMore && <ActivityIndicator size="small" color="rgba(255,255,255,0.55)" />}
            {reachedEnd && !loadingMore && (
              <Text style={styles.footerText}>Это всё, что сейчас в наличии</Text>
            )}
          </View>
        ) : null
      }
      ListHeaderComponent={
        <View style={{ paddingTop }}>
          {/* Exit-hint выше МАРКЕТ heading. Сидит на negative margin —
              layout не сдвигает. Видимый только при overdrag сверху. */}
          {pullFraction && <MarketExitHint pullFraction={pullFraction} />}
          {marketStores.length > 0 && (
            <MarketSection
              stores={isSearchActive ? [] : marketStores}
              searchValue={marketSearch}
              onSearchChange={setMarketSearch}
              onSearchSubmit={Keyboard.dismiss}
              filters={filters}
              onFiltersChange={setFilters}
              facets={facets}
              totalStores={marketStores.length}
              totalItems={marketStores.reduce((sum, s) => sum + s.totalCount, 0)}
              onStorePress={handleStorePress}
              onItemPress={(item) => handleItemPress(item)}
              headerPaddingTop={0}
            />
          )}
          {marketStores.length === 0 && (
            <View style={styles.empty}>
              <Text style={styles.emptyText}>
                Магазины ещё не подключены или временно недоступны
              </Text>
            </View>
          )}
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  searchState: {
    paddingHorizontal: 24,
    paddingVertical: 32,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 120,
  },
  searchStateText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: 'rgba(255,255,255,0.68)',
    textAlign: 'center',
  },
  footer: {
    paddingVertical: 20,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24,
  },
  footerText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 12,
    color: 'rgba(255,255,255,0.45)',
  },
  empty: {
    paddingHorizontal: 32,
    paddingVertical: 80,
    alignItems: 'center',
  },
  emptyText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: 'rgba(255,255,255,0.65)',
    textAlign: 'center',
  },
});

export default MarketMain;
