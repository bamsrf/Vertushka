/**
 * /dev/market-demo — самостоятельный экран для visual-QA Маркета.
 *
 * Mock-data, не зависит от backend. Демонстрирует:
 *   - magic-transition фона при скролле (Discogs-мир → market-мир)
 *   - Hot Stock pill во всех 6 состояниях (на верхнем секшене как showcase)
 *   - MarketSection полностью (header + поиск + чипы + витрины 3 магазинов)
 *   - Curtain-affordance больше не на этом demo-стенде
 *   - Sticky compact header который кросс-фейдится поверх hero
 *
 * Ссылка для открытия (после релоада Metro):
 *   exp://...:8081/--/dev/market-demo  (или через DevSettings.reload + ручная навигация)
 *
 * Этот файл рассчитан только на dev-сборки. В prod-навигации не светится —
 * экспортируется только default Screen для file-based routing.
 */
import React, { useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  useAnimatedScrollHandler,
  useSharedValue,
} from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import MarketBackground, {
  TRANSITION_END_Y,
} from '../../components/market/MarketBackground';
import MarketSection, {
  type MarketStoreData,
} from '../../components/market/MarketSection';
import HotStockTag from '../../components/HotStockTag';
import { type MarketCarouselCardData } from '../../components/market/MarketCarouselCard';
import { type MarketFilters, EMPTY_MARKET_FILTERS } from '../../lib/types';

// ────────────────────────────────────────────────────────────────────────
// Mock data — реальные обложки берём из Discogs CDN (пока нет своих).
// ────────────────────────────────────────────────────────────────────────

const MOCK_ITEMS_KOROBKA: MarketCarouselCardData[] = [
  { id: 'k1', artist: 'Khruangbin',  title: 'Mordechai',           year: 2020, format: 'LP',   priceRub: 4990, coverUrl: null },
  { id: 'k2', artist: 'King Krule',  title: 'Man Alive!',           year: 2020, format: 'LP',   priceRub: 5290, coverUrl: null },
  { id: 'k3', artist: 'Tame Impala', title: 'Currents',             year: 2015, format: '2xLP', priceRub: 6490, coverUrl: null },
  { id: 'k4', artist: 'Mac DeMarco', title: 'Salad Days',           year: 2014, format: 'LP',   priceRub: 4390, coverUrl: null },
  { id: 'k5', artist: 'Pink Floyd',  title: 'The Dark Side',        year: 1973, format: 'LP',   priceRub: 7990, coverUrl: null },
];

const MOCK_ITEMS_PLASTINKA: MarketCarouselCardData[] = [
  { id: 'p1', artist: 'Radiohead',   title: 'In Rainbows',          year: 2007, format: 'LP',   priceRub: 5490, coverUrl: null },
  { id: 'p2', artist: 'Daft Punk',   title: 'Random Access',        year: 2013, format: '2xLP', priceRub: 8990, coverUrl: null },
  { id: 'p3', artist: 'Frank Ocean', title: 'Blonde',               year: 2016, format: '2xLP', priceRub: 6790, coverUrl: null },
];

const MOCK_ITEMS_VINYL_RU: MarketCarouselCardData[] = [
  { id: 'v1', artist: 'Kendrick Lamar', title: 'DAMN.',             year: 2017, format: 'LP',   priceRub: 5590, coverUrl: null },
  { id: 'v2', artist: 'FKA twigs',      title: 'MAGDALENE',         year: 2019, format: 'LP',   priceRub: 5990, coverUrl: null },
  { id: 'v3', artist: 'Beach House',    title: 'Bloom',             year: 2012, format: '2xLP', priceRub: 4790, coverUrl: null },
  { id: 'v4', artist: 'Bon Iver',       title: 'i,i',               year: 2019, format: 'LP',   priceRub: 5190, coverUrl: null },
];

const MOCK_STORES: MarketStoreData[] = [
  { slug: 'korobkavinyla', totalCount: 5218, items: MOCK_ITEMS_KOROBKA },
  { slug: 'plastinka_com', totalCount: 186,  items: MOCK_ITEMS_PLASTINKA },
  { slug: 'vinyl_ru',      totalCount: 1042, items: MOCK_ITEMS_VINYL_RU },
];

// ────────────────────────────────────────────────────────────────────────

export default function MarketDemoScreen() {
  const scrollY = useSharedValue(0);
  const scrollRef = useRef<Animated.ScrollView>(null);

  const [searchValue, setSearchValue] = useState('');
  const [filters, setFilters] = useState<MarketFilters>(EMPTY_MARKET_FILTERS);
  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollY.value = e.contentOffset.y;
    },
  });

  const hotStockShowcase = useMemo(
    () => (
      <View style={styles.showcase}>
        <Text style={styles.showcaseTitle}>Hot Stock pill — 6 состояний</Text>
        <View style={styles.showcaseRow}>
          <HotStockTag variant="inStock" price={4990} />
          <HotStockTag variant="inStockMulti" price={4890} />
          <HotStockTag variant="lastOne" price={5990} />
        </View>
        <View style={styles.showcaseRow}>
          <HotStockTag variant="altVersion" price={5490} />
          <HotStockTag variant="preorder" price={6490} />
        </View>
        <Text style={[styles.showcaseTitle, { marginTop: 24 }]}>3 размера (inStock)</Text>
        <View style={styles.showcaseRow}>
          <HotStockTag variant="inStock" price={4990} size="sm" />
          <HotStockTag variant="inStock" price={4990} size="md" />
          <HotStockTag variant="inStock" price={4990} size="lg" />
        </View>
      </View>
    ),
    [],
  );

  return (
    <View style={styles.root}>
      {/* Фон — двухслойный, anim driven by scrollY */}
      <MarketBackground scrollY={scrollY} />

      {/* Контент */}
      <Animated.ScrollView
        ref={scrollRef}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Top section — Discogs-мир (псевдо-карточки чтобы было что листать) */}
        <SafeAreaView edges={['top']}>
          <View style={styles.topSection}>
            <Text style={styles.topTitle}>ПОИСК</Text>
            <Text style={styles.topSubtitle}>
              Demo-экран Маркета · scroll down to enter the magic door
            </Text>
            {hotStockShowcase}
            <View style={styles.fakeRail}>
              <View style={styles.fakeCard} />
              <View style={styles.fakeCard} />
              <View style={styles.fakeCard} />
            </View>
            <View style={styles.fakeRail}>
              <View style={styles.fakeCard} />
              <View style={styles.fakeCard} />
              <View style={styles.fakeCard} />
            </View>
            <Text style={styles.hint}>↓ Листайте вниз, чтобы войти в Маркет</Text>
          </View>
        </SafeAreaView>

        {/* Spacer чтобы Маркет начался в transition-zone */}
        <View style={{ height: TRANSITION_END_Y - 100 }} />

        {/* Market section — magic transition уже сработал */}
        <MarketSection
          stores={MOCK_STORES}
          searchValue={searchValue}
          onSearchChange={setSearchValue}
          filters={filters}
          onFiltersChange={setFilters}
          facets={null}
          onStorePress={(slug) => console.log('store press', slug)}
          onItemPress={(item, slug) => console.log('item press', item.id, slug)}
        />

        <View style={{ height: 200 }} />
      </Animated.ScrollView>

    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#000', // safety, перекрывается фоном
  },
  scrollContent: {
    paddingBottom: 100,
  },
  topSection: {
    padding: 20,
  },
  topTitle: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: 28,
    fontWeight: '800',
    color: '#0E121C',
    letterSpacing: -0.6,
  },
  topSubtitle: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: '#6B7080',
    marginTop: 6,
    marginBottom: 24,
  },
  showcase: {
    padding: 18,
    borderRadius: 16,
    backgroundColor: 'rgba(11,20,56,0.04)',
    marginBottom: 18,
  },
  showcaseTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: 13,
    fontWeight: '700',
    color: '#0E121C',
    marginBottom: 12,
  },
  showcaseRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 8,
    alignItems: 'center',
  },
  fakeRail: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 16,
  },
  fakeCard: {
    width: 140,
    height: 140,
    borderRadius: 12,
    backgroundColor: 'rgba(91,106,245,0.10)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(91,106,245,0.20)',
  },
  hint: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: '#6B7080',
    marginTop: 20,
    textAlign: 'center',
  },
});
