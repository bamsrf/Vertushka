/**
 * /market/store/[slug] — полная витрина одного магазина в Маркете.
 *
 * Layout:
 *   Back-arrow (← Маркет) + header (StoreLogo 64 + название + метрики)
 *   MarketSearchInput (поиск ВНУТРИ магазина)
 *   FilterBar (Формат / Жанр / Особенности) — тот же набор, что на общей
 *     витрине, но фасеты считаются по складу ЭТОГО магазина
 *   Sticky пагинированная сетка 2 колонки с in_stock-листингами магазина
 *
 * Фон — market-палитра (без magic transition — мы уже «в маркете»).
 *
 * Источник: docs/plans/MARKET_AND_PRICE_DRAWER.md §1.12 + screens-market.jsx
 * (ScreenStorePage из Design Claude handoff).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
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
import { analytics } from '../../../lib/analytics';
import { api } from '../../../lib/api';
import { MarketPalette } from '../../../constants/theme';
import { ms } from '../../../lib/responsive';
import { useMarketPagination } from '../../../lib/useMarketPagination';
import type {
  MarketSearchItem,
  MarketStoreInfo,
  MarketFilters,
  MarketFacetsResponse,
} from '../../../lib/types';
import { EMPTY_MARKET_FILTERS, hasActiveFilters } from '../../../lib/types';

import MarketBackground from '../../../components/market/MarketBackground';
import StoreLogo, { getStoreName } from '../../../components/market/StoreLogo';
import MarketSearchInput from '../../../components/market/MarketSearchInput';
import FilterBar from '../../../components/market/FilterBar';
import MarketResultCard, { marketGridStyles } from '../../../components/market/MarketResultCard';

export default function StorePage() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { slug: rawSlug } = useLocalSearchParams<{ slug: string }>();
  const slug = String(rawSlug ?? '');

  const [storeInfo, setStoreInfo] = useState<MarketStoreInfo | null>(null);

  const [searchValue, setSearchValue] = useState('');
  // debouncedQuery — отдельный от searchValue, обновляется через 400ms тишины.
  // Без этого useEffect re-fetch'ил после каждого keystroke → setLoading(true)
  // → FlatList re-renderил → keyboard dismiss. Юзер не мог дописать слово.
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [filters, setFilters] = useState<MarketFilters>(EMPTY_MARKET_FILTERS);
  const [facets, setFacets] = useState<MarketFacetsResponse | null>(null);
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

  const effectiveQuery = debouncedQuery.length >= 2 ? debouncedQuery : '';
  const filtersKey = useMemo(
    () => `${filters.format}|${[...filters.genres].sort().join(',')}|${[...filters.features].sort().join(',')}`,
    [filters],
  );

  // Фасеты считаем по складу ЭТОГО магазина — иначе на витрине появлялись бы
  // чипы жанров, которых у него нет, и тап по ним вёл бы в пустоту. Активные
  // фильтры передаём туда же: счётчик показывает пересечение с уже выбранным,
  // а не собственный объём чипа.
  //
  // setFacets(null) только при смене магазина: на смене фильтров это схлопнуло
  // бы ряд чипов до спиннера прямо под пальцем.
  useEffect(() => {
    setFacets(null);
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    api.getMarketFacets(slug, {
      q: effectiveQuery || undefined,
      format: filters.format === 'all' ? null : filters.format,
      genres: filters.genres,
      features: filters.features,
    })
      .then((res) => { if (!cancelled) setFacets(res); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [slug, filtersKey, effectiveQuery]);

  const fetchPage = useCallback(
    (offset: number, limit: number) =>
      api.getStoreAll(slug, {
        q: effectiveQuery || undefined,
        format: filters.format === 'all' ? null : filters.format,
        genres: filters.genres,
        features: filters.features,
        sort: 'price_asc',
        limit,
        offset,
      }),
    [slug, effectiveQuery, filters],
  );

  const { items, loading, loadingMore, reachedEnd, loadMore } = useMarketPagination({
    // Витрина магазина показывает товар всегда — даже без фильтров.
    enabled: true,
    resetKey: `${slug}|${effectiveQuery}|${filtersKey}`,
    fetchPage,
  });

  const handleItemPress = useCallback(
    (item: MarketSearchItem) => {
      const ref = item.discogs_id ?? item.record_id;
      // from='market_store' отделяет «пришёл из витрины магазина» от «искал по
      // всему Маркету»: у этих двух путей разная конверсия в переход.
      analytics.marketRecordOpen({ record_ref: ref, from: 'market_store' });
      router.push(`/record/${ref}?from=market_store` as any);
    },
    [router],
  );

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
        <FilterBar filters={filters} onChange={setFilters} facets={facets} />
      </View>
    </SafeAreaView>
  );

  // showStore выключен: магазин уже назван в шапке экрана, дублировать его
  // лого и имя в каждой карточке — лишний шум.
  const renderItem = ({ item }: { item: MarketSearchItem }) => (
    <MarketResultCard item={item} onPress={handleItemPress} />
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
        keyExtractor={(it) => it.record_id}
        numColumns={2}
        columnWrapperStyle={marketGridStyles.row}
        contentContainerStyle={marketGridStyles.content}
        ListEmptyComponent={
          loading ? (
            <View style={styles.empty}>
              <ActivityIndicator size="small" color="rgba(255,255,255,0.65)" />
            </View>
          ) : (
            <Pressable style={styles.empty} onPress={Keyboard.dismiss}>
              <Text style={styles.emptyText}>
                {effectiveQuery
                  ? `Ничего не найдено по «${effectiveQuery}»`
                  : hasActiveFilters(filters)
                    ? 'В этом магазине нет товаров под выбранными фильтрами'
                    : 'В магазине пока нет товаров в наличии'}
              </Text>
            </Pressable>
          )
        }
        ListFooterComponent={
          items.length > 0 ? (
            <View style={styles.footer}>
              {loadingMore && <ActivityIndicator size="small" color="rgba(255,255,255,0.55)" />}
              {reachedEnd && !loadingMore && (
                <Text style={styles.footerText}>Это всё, что сейчас в наличии</Text>
              )}
            </View>
          ) : null
        }
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
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
  // Top safe-area blur strip — закрывает scrollable контент под статус-баром
  // когда юзер скроллит вниз. Иначе текст карточек наезжает на 9:41/wifi.
  topSafeBlur: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    zIndex: 50,
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
  footer: {
    paddingVertical: 20,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 24,
  },
  footerText: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(12),
    color: 'rgba(255,255,255,0.45)',
  },
});
