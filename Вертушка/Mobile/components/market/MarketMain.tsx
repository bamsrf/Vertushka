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
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  Platform,
  StyleSheet,
  Text,
  View,
  type LayoutChangeEvent,
} from 'react-native';
import { useRouter } from 'expo-router';
import { GestureDetector, type ComposedGesture, type GestureType } from 'react-native-gesture-handler';
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
import type {
  MarketSearchItem,
  MarketFilters,
  MarketFacetsResponse,
  MarketReleaseScope,
} from '../../lib/types';
import { EMPTY_MARKET_FILTERS, hasActiveFilters } from '../../lib/types';

import { useMarketPagination } from '../../lib/useMarketPagination';
import { useBottomContentInset } from '../../lib/useBottomContentInset';
import MarketSection, { type MarketStoreData } from './MarketSection';
import MarketResultCard, { marketGridStyles } from './MarketResultCard';
import {
  MarketReleaseMissModal,
  MarketReleaseScopeBar,
} from './MarketReleaseScope';

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
  /**
   * Пришли с карточки релиза по кнопке «В Маркет» — витрина сужена до этой
   * пластинки. Читается на каждом рендере, а не запоминается на монтировании:
   * экран /market единственный на весь стек и переиспользуется (router.navigate
   * из OffersBlock поднимает живой инстанс), так что запомненный проп навсегда
   * закрепил бы пластинку первого захода за всеми следующими.
   */
  releaseScope?: MarketReleaseScope | null;
  /**
   * Android-overdrag выхода (lib/useAndroidOverdrag.ts): RNGH-жест
   * (Pan ∥ Native) вокруг списка. Без пропа дерево прежнее — iOS его не
   * передаёт.
   */
  listGesture?: ComposedGesture | GestureType;
  /**
   * Знаковый translateY шапки при pull-down (rubberBand хода пальца). На
   * Android contentOffset выше нуля не уходит, и MarketExitHint (сидит на
   * marginTop −70 над заголовком) остался бы под кромкой — двигаем шапку
   * сами. Применяется только когда проп задан.
   */
  headerShift?: SharedValue<number>;
  /** Метрики списка для overdrag'а до первого onScroll. */
  onListLayout?: (e: LayoutChangeEvent) => void;
  onContentSizeChange?: (w: number, h: number) => void;
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

export function MarketMain({
  onScroll,
  scrollEnabled = true,
  paddingTop,
  pullFraction,
  releaseScope: incomingScope = null,
  listGesture: incomingGesture,
  headerShift: incomingShift,
  onListLayout,
  onContentSizeChange,
}: MarketMainProps) {
  // Только Android: iOS-дерево не меняется, даже если пропы передали.
  const listGesture = Platform.OS === 'android' ? incomingGesture : undefined;
  const headerShift = Platform.OS === 'android' ? incomingShift : undefined;
  const headerShiftStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: headerShift ? headerShift.value : 0 }],
  }));
  // Маркет-слой живёт и в табе Поиска (под пилюлей GlassTabBar), и стековым
  // экраном /market — клиренс считаем под пилюлю в обоих случаях (iOS: 120).
  const listBottomPad = useBottomContentInset({ tabBar: true, extra: 32 });
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

  // Сужение живёт в пропе, а в состоянии — только отказ от него: ключ захода,
  // который человек уже закрыл. Держать здесь копию самого сужения нельзя —
  // экран переиспользуется, и копия пережила бы переход с другой карточки.
  const [clearedVisitKey, setClearedVisitKey] = useState<string | null>(null);
  const [missVisible, setMissVisible] = useState(false);

  const releaseScope =
    incomingScope && incomingScope.visitKey !== clearedVisitKey ? incomingScope : null;

  // Событие шлём здесь, а не внутри апдейтера setState: React волен вызвать
  // апдейтер дважды (StrictMode, конкурентный рендер), и каждый сброс
  // считался бы за два.
  const clearReleaseScope = useCallback((reason: 'chip' | 'search' | null) => {
    if (!releaseScope) return;
    if (reason) analytics.marketReleaseReset({ reason });
    setClearedVisitKey(releaseScope.visitKey);
    setMissVisible(false);
  }, [releaseScope]);

  // view_market отсюда НЕ шлётся, хотя место напрашивается. Слой Маркета в
  // (tabs)/search смонтирован всегда — он просто уведён за нижний край экрана
  // и ждёт занавеса. Событие на mount'е считало бы каждое открытие таба
  // Поиска заходом в Маркет, а знаменатель воронки был бы завышен настолько,
  // что market_record_open к нему не с чем сравнивать. Шлют точки входа —
  // см. MarketEntry в lib/analytics.ts.

  // Свой запрос вытесняет сужение по релизу. Оставить их вместе нельзя:
  // плашка обещает «показываем только эту пластинку», строка поиска — «ищем
  // то, что набрали», и вместе они дают пустую выдачу без внятной причины.
  // Гонимся не за debounce, а за первым же символом: плашка обязана исчезнуть
  // одновременно с началом набора, иначе полсекунды врёт.
  const handleSearchChange = useCallback((value: string) => {
    setMarketSearch(value);
    if (value.trim().length > 0) clearReleaseScope('search');
  }, [clearReleaseScope]);

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
    return debouncedQuery.length >= 2 || hasActiveFilters(filters) || releaseScope !== null;
  }, [debouncedQuery, filters, releaseScope]);

  // Сериализуем фильтры в стабильный ключ — иначе новый объект filters на
  // каждый рендер сбрасывал бы пагинацию.
  const filtersKey = useMemo(
    () => `${filters.format}|${[...filters.genres].sort().join(',')}|${[...filters.features].sort().join(',')}`,
    [filters],
  );
  const effectiveQuery = debouncedQuery.length >= 2 ? debouncedQuery : '';

  // Фасеты (доступные жанры/особенности со счётчиками). Перезапрашиваем на
  // каждое изменение фильтров: счётчики считаются с учётом уже выбранного, и
  // рядом с включённым «Цветным винилом» регги честно показывает 14, а не свои
  // 342. Порядок чипов бэк держит по объёму склада, а не по текущему числу,
  // поэтому ряд не переставляется под пальцем.
  //
  // Ошибку глотаем и СТАРЫЕ фасеты не сбрасываем: моргнувшая сеть не должна
  // схлопывать ряд чипов — юзер потеряет из-под пальца то, что уже выбрал.
  useEffect(() => {
    let cancelled = false;
    api.getMarketFacets(undefined, {
      q: effectiveQuery || undefined,
      format: filters.format === 'all' ? null : filters.format,
      genres: filters.genres,
      features: filters.features,
    })
      .then((res) => { if (!cancelled) setFacets(res); })
      .catch(() => {});
    return () => { cancelled = true; };
    // filtersKey/effectiveQuery — стабильные строки: объект filters новый на
    // каждый рендер и вызывал бы бесконечный перезапрос.
  }, [filtersKey, effectiveQuery]);

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
        releaseRecord: releaseScope?.recordId ?? null,
      }),
    [effectiveQuery, filters, releaseScope],
  );

  const {
    items: searchItems,
    loading: searchLoading,
    loadingMore,
    reachedEnd,
    failed: searchFailed,
    loadMore,
  } = useMarketPagination({
    enabled: isSearchActive,
    resetKey: `${effectiveQuery}|${filtersKey}|${releaseScope?.visitKey ?? ''}`,
    fetchPage: fetchSearchPage,
  });

  // Шаг воронки между «зашёл в Маркет» и «открыл карточку». Ловим ПЕРЕХОД
  // searchLoading true→false, а не просто «загрузка закончилась»: эффект
  // useMarketPagination объявлен выше по коду и на рендере со сменой запроса
  // ставит loading=true уже ПОСЛЕ того, как этот эффект прочитал старое false.
  // Условие «не грузимся» пропустило бы тот кадр и отправило results_count
  // прошлой выдачи — то есть почти всегда ноль, ровно ту цифру, ради которой
  // событие и заводится.
  //
  // Догрузка страниц крутит loadingMore, а не loading, поэтому второго события
  // на тот же поиск не будет. Быстрый доввод символов не даёт loading упасть
  // между запросами — уезжает один поиск, финальный.
  const prevSearchLoading = useRef(false);
  useEffect(() => {
    const wasLoading = prevSearchLoading.current;
    prevSearchLoading.current = searchLoading;
    if (!isSearchActive || searchLoading || !wasLoading) return;
    // Сужение по релизу — не поиск: запрос пустой, фильтров нет, и в воронке
    // market_search эти заходы выглядели бы как «искал и ничего не нашёл»,
    // завышая долю неудачных поисков нулями, которых человек не набирал.
    if (releaseScope) {
      // Упавший запрос молчит: сказать «этой пластинки нет» из-за моргнувшей
      // сети значит соврать ровно тем способом, который фича и убирает. И в
      // аналитику такой заход не идёт — он ничей исход.
      if (searchFailed) return;
      const empty = searchItems.length === 0;
      analytics.marketReleaseScope({
        outcome: empty ? 'empty' : 'in_stock',
        results_count: searchItems.length,
      });
      // Объяснение показываем ровно один раз на сужение: повторный показ
      // ловил бы человека при каждом возврате на экран.
      if (empty) setMissVisible(true);
      return;
    }
    analytics.marketSearch({
      query_length: effectiveQuery.length,
      has_filters: hasActiveFilters(filters),
      results_count: searchItems.length,
    });
    // filters читаем через замыкание ради hasActiveFilters — в deps лежит его
    // сериализованный filtersKey, объект filters новый на каждый рендер.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isSearchActive, searchLoading, effectiveQuery, filtersKey,
    searchItems.length, releaseScope, searchFailed,
  ]);

  // Нашёлся ли сам прессинг, с карточки которого пришли, — или в выдаче стоят
  // только другие издания альбома. Молча показать не ту версию значит
  // подменить ответ на вопрос «где ВОТ ЭТА»: плашка обязана это назвать.
  const exactInStock = useMemo(
    () => !!releaseScope && searchItems.some((it) => it.record_id === releaseScope.recordId),
    [releaseScope, searchItems],
  );

  // Снимаем сужение без события: исход этого захода уже уехал в
  // market_release_scope, и второе событие на то же действие только раздувало
  // бы долю «сбросов».
  const dismissMiss = useCallback(() => clearReleaseScope(null), [clearReleaseScope]);

  const handleStorePress = useCallback((slug: string) => {
    analytics.viewMarketStore(slug);
    router.push(`/market/store/${slug}` as any);
  }, [router]);
  // `from=market` доезжает до кнопки «Купить» на карточке и попадает в
  // offer_clicks.source. Без него переход засчитывался бы как `record`, и
  // вклад Маркета в отчёте магазину был бы неотличим от прямых заходов.
  const handleItemPress = useCallback((item: { id: string }) => {
    analytics.marketRecordOpen({ record_ref: item.id, from: 'market' });
    router.push(`/record/${item.id}?from=market` as any);
  }, [router]);
  const handleSearchItemPress = useCallback((item: MarketSearchItem) => {
    const ref = item.discogs_id ?? item.record_id;
    analytics.marketRecordOpen({ record_ref: ref, from: 'market' });
    router.push(`/record/${ref}?from=market` as any);
  }, [router]);

  const renderSearchItem = useCallback(
    ({ item }: { item: MarketSearchItem }) => (
      <MarketResultCard item={item} onPress={handleSearchItemPress} showStore />
    ),
    [handleSearchItemPress],
  );

  const header = (
    <View style={{ paddingTop }}>
      {/* Exit-hint выше МАРКЕТ heading. Сидит на negative margin —
          layout не сдвигает. Видимый только при overdrag сверху. */}
      {pullFraction && <MarketExitHint pullFraction={pullFraction} />}
      {marketStores.length > 0 && (
        <MarketSection
          stores={isSearchActive ? [] : marketStores}
          searchValue={marketSearch}
          onSearchChange={handleSearchChange}
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
      {/* Плашка сужения — последней в шапке, вплотную к сетке: она
          объясняет именно её состав. Пока идёт первая загрузка, не
          рисуем: «именно этой версии нет» до ответа сервера — догадка. */}
      {releaseScope && !searchLoading && searchItems.length > 0 && (
        <MarketReleaseScopeBar
          scope={releaseScope}
          exactInStock={exactInStock}
          onReset={() => clearReleaseScope('chip')}
        />
      )}
    </View>
  );

  const list = (
    <AnimatedFlatList
      // Результаты живут в data (а не в шапке) — только так FlatList знает
      // длину списка и дёргает onEndReached для подгрузки следующей страницы.
      // Когда фильтров нет, сетка пуста и виден обычный состав Маркета.
      data={(isSearchActive ? searchItems : NO_ITEMS) as any}
      keyExtractor={(item: any) => (item as MarketSearchItem).record_id}
      renderItem={renderSearchItem as any}
      numColumns={2}
      columnWrapperStyle={marketGridStyles.row}
      contentContainerStyle={{ paddingBottom: listBottomPad }}
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
                {searchFailed
                  ? 'Не удалось загрузить. Проверьте связь и попробуйте ещё раз'
                  : releaseScope
                    ? `${releaseScope.artist} — ${releaseScope.title}: сейчас нет ни в одном магазине`
                    : effectiveQuery
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
      onLayout={onListLayout}
      onContentSizeChange={onContentSizeChange}
      ListHeaderComponent={
        headerShift ? <Animated.View style={headerShiftStyle}>{header}</Animated.View> : header
      }
    />
  );

  return (
    <>
      {listGesture ? <GestureDetector gesture={listGesture}>{list}</GestureDetector> : list}
      <MarketReleaseMissModal
        visible={missVisible}
        scope={releaseScope}
        onDismiss={dismissMiss}
      />
    </>
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
