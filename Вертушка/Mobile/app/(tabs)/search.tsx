/**
 * Экран поиска по Discogs
 */
import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  View,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  Pressable,
  Alert,
  Text,
  Modal,
  ScrollView,
  Animated,
  KeyboardAvoidingView,
  Platform,
  LayoutAnimation,
  Dimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams, useFocusEffect } from 'expo-router';
import Reanimated, {
  Extrapolation,
  interpolate,
  runOnJS,
  useAnimatedScrollHandler,
  useAnimatedStyle,
  useDerivedValue,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import { AnimatedGradientText } from '../../components/AnimatedGradientText';
import { RecordGrid } from '../../components/RecordGrid';
import { AutoRail } from '../../components/AutoRail';
import { Section } from '../../components/Section';
import { useSearchStore, useCollectionStore, useUserSearchStore, useAuthStore, useSuggestStore } from '../../lib/store';
import { useTourTarget } from '../../lib/useTourTarget';
import { ms } from '../../lib/responsive';
import { analytics } from '../../lib/analytics';
import { api, resolveMediaUrl } from '../../lib/api';
import { MasterSearchResult, ReleaseSearchResult, ArtistSearchResult, UserWithStats, PublicProfileRecord, MarketCarouselItem } from '../../lib/types';
import { MiniPriceBadge } from '../../components/MiniPriceBadge';
import MarketBackground from '../../components/market/MarketBackground';
import MarketMain from '../../components/market/MarketMain';
import { useMarketStore } from '../../lib/marketStore';
import { Colors, Typography, Spacing, BorderRadius, Gradients } from '../../constants/theme';
import { toast } from '../../lib/toast';
import { cleanArtistName } from '../../lib/format';

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

// Маппинг форматов для отображения на русском
const FORMAT_OPTIONS = [
  { value: undefined, label: 'Все' },
  { value: 'Vinyl', label: 'Винил' },
  { value: 'CD', label: 'CD' },
  { value: 'Cassette', label: 'Кассета' },
  { value: 'Box Set', label: 'Бокс-сет' },
  { value: 'File', label: 'Цифровой' },
];

// Основные страны (показываются по умолчанию)
const MAIN_COUNTRIES = [
  { value: undefined, label: 'Все' },
  { value: 'US', label: 'США' },
  { value: 'UK', label: 'Великобритания' },
  { value: 'Germany', label: 'Германия' },
  { value: 'Japan', label: 'Япония' },
  { value: 'Russia', label: 'Россия' },
];

// Все страны (показываются при нажатии "Показать все")
const ALL_COUNTRIES = [
  ...MAIN_COUNTRIES,
  { value: 'France', label: 'Франция' },
  { value: 'Italy', label: 'Италия' },
  { value: 'Netherlands', label: 'Нидерланды' },
  { value: 'Canada', label: 'Канада' },
  { value: 'Australia', label: 'Австралия' },
  { value: 'Sweden', label: 'Швеция' },
  { value: 'Spain', label: 'Испания' },
  { value: 'Brazil', label: 'Бразилия' },
  { value: 'Poland', label: 'Польша' },
  { value: 'Belgium', label: 'Бельгия' },
  { value: 'Austria', label: 'Австрия' },
  { value: 'Denmark', label: 'Дания' },
  { value: 'Finland', label: 'Финляндия' },
  { value: 'Norway', label: 'Норвегия' },
  { value: 'Greece', label: 'Греция' },
  { value: 'Portugal', label: 'Португалия' },
  { value: 'Czechoslovakia', label: 'Чехословакия' },
  { value: 'Yugoslavia', label: 'Югославия' },
  { value: 'USSR', label: 'СССР' },
];

// Опции года (декады)
const YEAR_OPTIONS = [
  { value: undefined, label: 'Все годы' },
  { value: '2020s', label: '2020-е', min: 2020, max: 2029 },
  { value: '2010s', label: '2010-е', min: 2010, max: 2019 },
  { value: '2000s', label: '2000-е', min: 2000, max: 2009 },
  { value: '1990s', label: '1990-е', min: 1990, max: 1999 },
  { value: '1980s', label: '1980-е', min: 1980, max: 1989 },
  { value: '1970s', label: '1970-е', min: 1970, max: 1979 },
  { value: '1960s', label: '1960-е', min: 1960, max: 1969 },
  { value: '1950s', label: '1950-е и ранее', min: 0, max: 1959 },
];

export default function SearchScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  // Query-param focus=market: после navigation из OffersBlock CTA нужно
  // сразу проскроллить к Маркет-секции, а не показать пустой Поиск.
  const { focus } = useLocalSearchParams<{ focus?: string }>();
  const { user } = useAuthStore();
  const filtersTarget = useTourTarget('search-filters');
  const [searchInput, setSearchInput] = useState('');
  const [inputFocused, setInputFocused] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showAllCountries, setShowAllCountries] = useState(false);
  const [selectedDecade, setSelectedDecade] = useState<string | undefined>(undefined);

  // Временные фильтры для модалки (применяются только при закрытии)
  const [tempFilters, setTempFilters] = useState<{ format?: string; country?: string; year?: number; year_min?: number; year_max?: number }>({});

  // Защита от спама: cooldown кнопки поиска 500ms
  const lastSearchTime = useRef(0);
  // Debounce loadMore: 300ms
  const loadMoreTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Анимация для модала фильтров
  const overlayOpacity = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(300)).current;

  const {
    query,
    results,
    artistResults,
    filters,
    isLoading,
    hasMore,
    searchHistory,
    correctedQuery,
    search,
    loadMore,
    clearResults,
    setFilters,
    clearFilters,
    loadHistory,
    addToHistory,
    removeFromHistory,
    clearHistory,
  } = useSearchStore();

  const [showAllArtists, setShowAllArtists] = useState(false);
  const [topArtistImgError, setTopArtistImgError] = useState(false);
  const [secondaryImgErrors, setSecondaryImgErrors] = useState<Set<string>>(new Set());

  const { suggestions, fetchSuggestions, clear: clearSuggestions } = useSuggestStore();
  const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { addToCollection, addToWishlist, isOwned } = useCollectionStore();

  const {
    results: userResults,
    isLoading: isUserSearchLoading,
    search: searchUsers,
    clearResults: clearUserResults,
  } = useUserSearchStore();

  // Режим поиска пользователей: запрос начинается с @
  const isUserSearch = searchInput.startsWith('@');

  // Открытие модалки фильтров
  const openFilters = useCallback(() => {
    // Загружаем текущие фильтры во временный стейт
    setTempFilters(filters);

    // Восстанавливаем выбранную декаду по year_min/year_max (или legacy year)
    if (filters.year_min != null && filters.year_max != null) {
      const decade = YEAR_OPTIONS.find((option) =>
        option.value && 'min' in option && option.min === filters.year_min && option.max === filters.year_max
      );
      setSelectedDecade(decade?.value);
    } else if (filters.year) {
      const decade = YEAR_OPTIONS.find((option) =>
        option.value && 'min' in option && filters.year! >= option.min! && filters.year! <= option.max!
      );
      setSelectedDecade(decade?.value);
    } else {
      setSelectedDecade(undefined);
    }

    setShowFilters(true);
    Animated.parallel([
      Animated.timing(overlayOpacity, {
        toValue: 1,
        duration: 250,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 300,
        useNativeDriver: true,
      }),
    ]).start();
  }, [overlayOpacity, slideAnim, filters]);

  // Закрытие модалки фильтров с применением фильтров
  const closeFilters = useCallback(async () => {
    // Применяем временные фильтры к основному стору
    setFilters(tempFilters);

    Animated.parallel([
      Animated.timing(overlayOpacity, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.timing(slideAnim, {
        toValue: 300,
        duration: 250,
        useNativeDriver: true,
      }),
    ]).start(() => {
      setShowFilters(false);
    });

    // Применяем фильтры к поиску
    if (searchInput.trim()) {
      await search(searchInput.trim());
    }
  }, [overlayOpacity, slideAnim, tempFilters, setFilters, searchInput, search]);

  // Загружаем историю при монтировании и при смене пользователя
  useEffect(() => {
    loadHistory();
  }, [loadHistory, user?.id]);

  // Новинки (свежие релизы Discogs) для домашнего экрана Поиска
  const [newReleases, setNewReleases] = useState<PublicProfileRecord[]>([]);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.getNewReleases(24)
      .then((items) => { if (!cancelled) setNewReleases(items); })
      .catch(() => { /* silent: блок просто не появится */ });
    return () => { cancelled = true; };
  }, []);

  // OFFERS_UX.md Фича 4 — «Маркет» в поиске. Карусель новинок в продаже
  // из подключённых магазинов. На бэке (`/api/market/new-arrivals`) уже
  // дедуплицируется по записи: один товар = одна обложка.
  const [marketItems, setMarketItems] = useState<MarketCarouselItem[]>([]);
  useEffect(() => {
    let cancelled = false;
    api.getMarketFeed(24)
      .then((items) => { if (!cancelled) setMarketItems(items); })
      .catch(() => { /* silent: блок просто не появится — нет данных или ошибка */ });
    return () => { cancelled = true; };
  }, []);

  // Маппинг MarketCarouselItem → PublicProfileRecord для AutoRail.
  // AutoRail знает только эту форму, а мета-строку с ценой мы рендерим
  // через `itemBadgeRenderer` (см. использование AutoRail ниже).
  const marketAsProfileRecords: PublicProfileRecord[] = marketItems.map((m) => ({
    id: m.record_id,
    title: m.title,
    artist: m.artist,
    year: m.year ?? undefined,
    format_type: m.format_type ?? undefined,
    cover_image_url: m.cover_image_url ?? undefined,
    price_currency: 'RUB',
    discogs_id: m.discogs_id ?? null,
  }));

  // Карта record_id → цена, чтобы renderer мог быстро найти цену по карточке.
  const marketPriceByRecordId = new Map(
    marketItems.map((m) => [m.record_id, Number(m.min_price_rub)]),
  );

  // ──────────────────────────────────────────────────────────────────
  // МАРКЕТ — раздел «потайной двери» ниже Discogs-секций
  // (docs/plans/MARKET_AND_PRICE_DRAWER.md §1).
  // ──────────────────────────────────────────────────────────────────

  const scrollToTopRef = useRef<(() => void) | null>(null);
  const scrollToOffsetRef = useRef<((offset: number, animated?: boolean) => void) | null>(null);

  // committed — Маркет-слой сейчас активен (in-place layer composition,
  // без навигации). Меняется через onCommit/onExit overdrag-жеста.
  //
  // Initial value читается из persisted marketStore: если юзер закрыл
  // приложение или ушёл с таба, будучи в Маркете — сюда же и возвращается.
  // Сброс происходит ТОЛЬКО через явный exit-жест (pull-down сверху Маркета).
  const initialCommitted = useMarketStore.getState().committed;
  const [committed, setCommitted] = useState(initialCommitted);
  const committedSv = useSharedValue(initialCommitted ? 1 : 0);
  useEffect(() => {
    committedSv.value = committed ? 1 : 0;
  }, [committed, committedSv]);

  const setMarketCommitted = useMarketStore((s) => s.setCommitted);

  // committedAnim 0..1 — ЕДИНСТВЕННЫЙ параметр визуальной анимации перехода.
  // НЕ управляется жестом напрямую: жест только триггерит spring до 0 или 1
  // на release. Так слой не «прокручивается пальцем», а сам приезжает.
  const committedAnim = useSharedValue(initialCommitted ? 1 : 0);
  // pullFraction 0..1 — текущее «насколько глубоко юзер тянет ПРЯМО СЕЙЧАС».
  // Используется только для haptic-лесенки и фейда CTA-лейбла. К слою не
  // привязан вообще: лейбл фейдится по pullFraction, слой движется по
  // committedAnim. Это и даёт «жест триггерит, страница автоматом встаёт».
  const pullFraction = useSharedValue(0);
  const dragging = useSharedValue(0);
  const lastHapticStep = useSharedValue(-1);
  const committingRef = useRef(false);

  useFocusEffect(
    useCallback(() => {
      // На focus сбрасываем ТОЛЬКО transient gesture-state (палец+haptic).
      // Persistent committed-режим НЕ трогаем: юзер должен оставаться в
      // Маркете после возврата с /market/store/[slug], с другого таба или
      // после reopen'а приложения. Выход из Маркета — только через явный
      // exit-жест (pull-down).
      pullFraction.value = 0;
      lastHapticStep.value = -1;
      committingRef.current = false;
    }, [pullFraction, lastHapticStep]),
  );

  // ?focus=market — auto-commit (slide-up без жеста).
  useEffect(() => {
    if (focus !== 'market') return;
    setCommitted(true);
    committedAnim.value = withSpring(1, {
      damping: 22, stiffness: 200, mass: 0.7, overshootClamping: true,
    });
  }, [focus, committedAnim]);

  useEffect(() => {
    setMarketCommitted(committed);
  }, [committed, setMarketCommitted]);

  // ─── Haptic ramp ────────────────────────────────────────────────────
  const fireTick = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  }, []);
  const fireCommitHaptic = useCallback(() => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
  }, []);
  const fireMiss = useCallback(() => {
    Haptics.selectionAsync().catch(() => {});
  }, []);

  useDerivedValue(() => {
    if (dragging.value === 0) return;
    const p = pullFraction.value;
    let step = 0;
    if (p >= 1) step = 3;
    else if (p >= 0.66) step = 2;
    else if (p >= 0.33) step = 1;
    if (step > lastHapticStep.value) {
      lastHapticStep.value = step;
      if (step === 3) runOnJS(fireCommitHaptic)();
      else if (step > 0) runOnJS(fireTick)();
    } else if (step < lastHapticStep.value) {
      lastHapticStep.value = step;
    }
  });

  // ─── Commit / Exit (JS-only, вызываются из worklet через runOnJS) ───
  const triggerCommit = useCallback(() => {
    if (committingRef.current) return;
    committingRef.current = true;
    setCommitted(true);
    setTimeout(() => { committingRef.current = false; }, 500);
  }, []);
  const triggerExit = useCallback(() => {
    if (committingRef.current) return;
    committingRef.current = true;
    setCommitted(false);
    setTimeout(() => { committingRef.current = false; }, 500);
  }, []);

  // Сброс скролла Поиска при выходе из Маркета. Делаем через useEffect
  // (а не внутри triggerExit), потому что:
  //   • triggerExit зовётся через runOnJS из worklet'а — иногда scrollToOffset
  //     не успевает приклеиться, если FlatList в этот момент перерисовывается.
  //   • useEffect гарантированно срабатывает ПОСЛЕ React commit'а
  //     setCommitted(false), когда дерево уже стабильно.
  //   • requestAnimationFrame даёт ещё один кадр на устаканивание layout'а.
  //   • Используем И scrollToOffsetRef И scrollToTopRef для надёжности —
  //     если один не подцепился, другой сработает.
  const prevCommittedRef = useRef(initialCommitted);
  useEffect(() => {
    const wasCommitted = prevCommittedRef.current;
    prevCommittedRef.current = committed;
    if (wasCommitted && !committed) {
      requestAnimationFrame(() => {
        scrollToOffsetRef.current?.(0, false);
        scrollToTopRef.current?.();
      });
    }
  }, [committed]);

  const COMMIT_DISTANCE = 110;
  const EXIT_COMMIT_DISTANCE = 110;
  const SPRING_CONFIG = { damping: 22, stiffness: 200, mass: 0.7, overshootClamping: true };
  const homeGate = useSharedValue(0);

  // Search-side: overdrag в самом низу → pullFraction. На release при ≥1
  // флипаем committed=true и стартуем spring committedAnim → 1. СЛОЙ САМ
  // приезжает; жест его не двигает.
  const onScrollSearch = useAnimatedScrollHandler({
    onScroll: (e) => {
      if (homeGate.value === 0) return;
      if (committedSv.value === 1) return;
      if (dragging.value === 0) return;
      const y = e.contentOffset.y;
      const maxY = Math.max(0, e.contentSize.height - e.layoutMeasurement.height);
      const overdrag = Math.max(0, y - maxY);
      pullFraction.value = Math.min(1.25, overdrag / COMMIT_DISTANCE);
    },
    onBeginDrag: () => {
      if (homeGate.value === 0 || committedSv.value === 1) return;
      dragging.value = 1;
      lastHapticStep.value = -1;
    },
    onEndDrag: () => {
      if (homeGate.value === 0 || committedSv.value === 1) return;
      dragging.value = 0;
      if (pullFraction.value >= 1) {
        // Threshold crossed → flip state + start auto-slide.
        runOnJS(triggerCommit)();
        committedAnim.value = withSpring(1, SPRING_CONFIG);
        pullFraction.value = withTiming(0, { duration: 260 });
      } else {
        if (pullFraction.value > 0.2) runOnJS(fireMiss)();
        pullFraction.value = withTiming(0, { duration: 260 });
      }
    },
  });

  // Market-side: overdrag в самом верху → pullFraction. На release при ≥1
  // флипаем committed=false и стартуем spring committedAnim → 0.
  const onScrollMarket = useAnimatedScrollHandler({
    onScroll: (e) => {
      if (committedSv.value === 0) return;
      if (dragging.value === 0) return;
      const overdrag = Math.max(0, -e.contentOffset.y);
      pullFraction.value = Math.min(1.25, overdrag / EXIT_COMMIT_DISTANCE);
    },
    onBeginDrag: () => {
      if (committedSv.value === 0) return;
      dragging.value = 1;
      lastHapticStep.value = -1;
    },
    onEndDrag: () => {
      if (committedSv.value === 0) return;
      dragging.value = 0;
      if (pullFraction.value >= 1) {
        runOnJS(triggerExit)();
        committedAnim.value = withSpring(0, SPRING_CONFIG);
        pullFraction.value = withTiming(0, { duration: 260 });
      } else {
        if (pullFraction.value > 0.2) runOnJS(fireMiss)();
        pullFraction.value = withTiming(0, { duration: 260 });
      }
    },
  });

  // ─── Layer animated style: только Market layer движется ────────────
  const SCREEN_H = Dimensions.get('window').height;

  const marketLayerStyle = useAnimatedStyle(() => {
    const c = committedAnim.value;
    return {
      transform: [{ translateY: (1 - c) * SCREEN_H }],
    };
  });

  // CTA-блок — больше не фейдится. Юзер видит как прогресс-бар внутри
  // блока наполняется по мере pull'а. Subtle scale-up на 100% — тактильный
  // отклик «готово, можно отпускать».
  const curtainLabelStyle = useAnimatedStyle(() => {
    const p = Math.min(1, pullFraction.value);
    return {
      transform: [
        { scale: interpolate(p, [0, 1], [1, 1.02], Extrapolation.CLAMP) },
      ],
    };
  });

  // Fill-полоска: scaleX от 0 (нет pull'а) до 1 (commit-порог).
  const ctaProgressFillStyle = useAnimatedStyle(() => {
    return {
      transform: [{ scaleX: Math.min(1, pullFraction.value) }],
    };
  });

  const handleNewReleasePick = useCallback((r: PublicProfileRecord) => {
    router.push(`/record/${r.id}`);
  }, [router]);

  const handleMarketPick = useCallback((r: PublicProfileRecord) => {
    // Карусельная запись = matched_record_id, открываем по нему детальную.
    router.push(`/record/${r.id}`);
  }, [router]);

  const handleMarketShowAll = useCallback(() => {
    // «Смотреть все →» — тот же auto-slide что и при overdrag-commit'е.
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    setCommitted(true);
    committedAnim.value = withSpring(1, {
      damping: 22, stiffness: 200, mass: 0.7, overshootClamping: true,
    });
  }, [committedAnim]);

  const handleSearch = useCallback(async () => {
    const trimmed = searchInput.trim();
    if (!trimmed) return;

    const now = Date.now();
    if (now - lastSearchTime.current < 500) return;
    lastSearchTime.current = now;

    clearSuggestions();
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    setShowAllArtists(false);
    setTopArtistImgError(false);
    setSecondaryImgErrors(new Set());

    try {
      analytics.search(trimmed, 0);
      if (trimmed.startsWith('@')) {
        // Режим поиска пользователей — ищем без @
        const userQuery = trimmed.slice(1).trim();
        if (userQuery.length > 0) {
          clearResults();
          await searchUsers(userQuery);
        }
      } else {
        const [recordsResult, usersResult] = await Promise.allSettled([
          search(trimmed),
          searchUsers(trimmed),
        ]);
        // Показываем ошибку только если оба запроса упали
        if (recordsResult.status === 'rejected' && usersResult.status === 'rejected') {
          const error = recordsResult.reason;
          const message = error?.response?.status === 503
            ? 'Сервис временно недоступен. Попробуйте позже.'
            : error?.message || 'Ошибка при поиске';
          toast.error('Ошибка', message);
        }
        return;
      }
    } catch (error: any) {
      const message = error?.response?.status === 503
        ? 'Сервис временно недоступен. Попробуйте позже.'
        : error?.message || 'Ошибка при поиске';
      toast.error('Ошибка', message);
    }
  }, [searchInput, search, searchUsers, clearResults, clearSuggestions]);

  const handleClear = useCallback(() => {
    setSearchInput('');
    clearResults();
    clearUserResults();
    clearFilters();
    clearSuggestions();
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    setTempFilters({});
    setSelectedDecade(undefined);
    setShowAllArtists(false);
  }, [clearResults, clearFilters, clearSuggestions]);

  // Проверка активных фильтров
  const hasActiveFilters = !!(filters.format || filters.country || filters.year);

  // Проверка активных временных фильтров (для модалки)
  const hasTempFilters = !!(tempFilters.format || tempFilters.country || tempFilters.year || tempFilters.year_min != null || tempFilters.year_max != null || selectedDecade);

  // Автосброс фильтров при изменении поискового запроса
  const handleSearchInputChange = useCallback((text: string) => {
    // Переключение между режимами: очищаем неактуальные результаты
    const wasUserSearch = searchInput.startsWith('@');
    const willBeUserSearch = text.startsWith('@');

    if (wasUserSearch && !willBeUserSearch) {
      clearUserResults();
    } else if (!wasUserSearch && willBeUserSearch) {
      clearResults();
      clearFilters();
    }

    // Если пользователь начинает вводить новый запрос и были активные фильтры - сбрасываем их
    if (!willBeUserSearch && text !== searchInput && (filters.format || filters.country || filters.year)) {
      clearFilters();
    }
    setSearchInput(text);

    // Автодополнение с debounce 400ms
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    if (text.length >= 2 && !text.startsWith('@')) {
      suggestTimer.current = setTimeout(() => fetchSuggestions(text), 400);
    } else {
      clearSuggestions();
    }
  }, [searchInput, filters.format, filters.country, filters.year, clearFilters, clearResults, clearUserResults, fetchSuggestions, clearSuggestions]);

  const handleHistoryItemPress = useCallback(async (historyQuery: string) => {
    setShowHistory(false);
    setSearchInput(historyQuery);
    setShowAllArtists(false);
    setTopArtistImgError(false);
    setSecondaryImgErrors(new Set());
    try {
      if (historyQuery.startsWith('@')) {
        const userQuery = historyQuery.slice(1).trim();
        if (userQuery.length > 0) {
          clearResults();
          await searchUsers(userQuery);
        }
      } else {
        const [recordsResult, usersResult] = await Promise.allSettled([
          search(historyQuery),
          searchUsers(historyQuery),
        ]);
        if (recordsResult.status === 'rejected' && usersResult.status === 'rejected') {
          const error = recordsResult.reason;
          const message = error?.response?.status === 503
            ? 'Сервис временно недоступен. Попробуйте позже.'
            : error?.message || 'Ошибка при поиске';
          toast.error('Ошибка', message);
        }
        return;
      }
    } catch (error: any) {
      const message = error?.response?.status === 503
        ? 'Сервис временно недоступен. Попробуйте позже.'
        : error?.message || 'Ошибка при поиске';
      toast.error('Ошибка', message);
    }
  }, [search, searchUsers, clearResults]);

  const handleRemoveHistoryItem = useCallback((historyQuery: string) => {
    removeFromHistory(historyQuery);
  }, [removeFromHistory]);

  const handleClearHistory = useCallback(() => {
    Alert.alert(
      'Очистить историю',
      'Вы уверены, что хотите удалить всю историю поиска?',
      [
        { text: 'Отмена', style: 'cancel' },
        { text: 'Очистить', style: 'destructive', onPress: clearHistory },
      ]
    );
  }, [clearHistory]);

  const handleHistoryExpandToggle = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setHistoryExpanded((v) => !v);
  }, []);

  const handleBlur = useCallback(() => {
    // showHistory намеренно не сбрасываем — список остаётся интерактивным
  }, []);

  const handleRecordPress = (record: MasterSearchResult | ReleaseSearchResult) => {
    // Если это MasterSearchResult - переходим на страницу мастера
    if ('master_id' in record) {
      router.push({
        pathname: `/master/${record.master_id}`,
        params: {
          title: record.title,
          artist: record.artist,
          year: record.year?.toString() || '',
          cover: record.cover_image_url || '',
        },
      });
    } else if ('release_id' in record) {
      // Если это ReleaseSearchResult - переходим на страницу релиза
      router.push(`/record/${record.release_id}`);
    }
  };

  const handleAddToCollection = async (record: MasterSearchResult | ReleaseSearchResult) => {
    const discogsId = 'main_release_id' in record ? record.main_release_id : record.release_id;

    const alreadyInCollection = isOwned({ discogsId });

    const doAdd = async () => {
      try {
        await addToCollection(discogsId);
        const format = 'format' in record ? record.format : undefined;
        const fmt = getFormatDisplayInfo(format);
        toast.success('Готово!', `"${record.title}" ${fmt.verb} в коллекцию`);
      } catch (error: any) {
        const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в коллекцию';
        toast.error('Ошибка', message);
      }
    };

    if (alreadyInCollection) {
      Alert.alert(
        'Уже в коллекции',
        `«${record.title}» уже есть в вашей коллекции. Добавить ещё одну копию?`,
        [
          { text: 'Отмена', style: 'cancel' },
          { text: 'Добавить', onPress: doAdd },
        ]
      );
    } else {
      await doAdd();
    }
  };

  const handleAddToWishlist = async (record: MasterSearchResult | ReleaseSearchResult) => {
    try {
      const discogsId = 'main_release_id' in record ? record.main_release_id : record.release_id;
      await addToWishlist(discogsId);
      const format = 'format' in record ? record.format : undefined;
      const fmt = getFormatDisplayInfo(format);
      toast.success('Готово!', `"${record.title}" ${fmt.verb} в список желаний`);
    } catch (error: any) {
      const message = error?.response?.data?.detail || error?.message || 'Не удалось добавить в список желаний';
      toast.error('Ошибка', message);
    }
  };

  const handleArtistPress = (artist: ArtistSearchResult) => {
    router.push(`/artist/${artist.artist_id}`);
  };

  const handleUserPress = (user: UserWithStats) => {
    router.push(`/user/${user.username}`);
  };

  // Поиск артиста по имени и переход на его страницу
  const handleArtistNamePress = useCallback(async (artistName: string) => {
    try {
      const response = await api.searchArtists(artistName, 1, 1);
      if (response.results.length > 0) {
        router.push(`/artist/${response.results[0].artist_id}`);
      } else {
        toast.info('Не найдено', `Артист "${artistName}" не найден`);
      }
    } catch (error) {
      console.error('Error searching artist:', error);
      toast.error('Ошибка', 'Не удалось найти артиста');
    }
  }, [router]);

  // Обновление временных фильтров без закрытия модалки
  const updateTempFilter = useCallback((key: 'format' | 'country' | 'year', value: string | number | undefined) => {
    setTempFilters(prev => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  // Очистка всех временных фильтров (применится при закрытии модалки)
  const handleClearAllFilters = useCallback(() => {
    setTempFilters({});
    setSelectedDecade(undefined);
  }, []);

  // Домашний экран Поиска: ввод пустой, результатов нет — рендерим секции (история + новинки)
  const isHomeView = searchInput === '' && results.length === 0 && artistResults.length === 0;
  // Синхронизируем JS-флаг с worklet-gate, чтобы overdrag-commit срабатывал
  // только в home-view (не в результатах поиска).
  useEffect(() => {
    homeGate.value = isHomeView ? 1 : 0;
    if (!isHomeView) pullFraction.value = 0;
  }, [isHomeView, homeGate, pullFraction]);
  // История появляется только после взаимодействия с полем (showHistory выставляется в onFocus)
  const shouldShowHistory = isHomeView && showHistory && searchHistory.length > 0;

  const visibleArtists = showAllArtists ? artistResults : artistResults.slice(0, 3);

  const HISTORY_PREVIEW_LIMIT = 5;
  const visibleHistory = historyExpanded
    ? searchHistory
    : searchHistory.slice(0, HISTORY_PREVIEW_LIMIT);
  const historyOverflow = searchHistory.length - HISTORY_PREVIEW_LIMIT;

  const HomeSections = isHomeView ? (
    <View style={{ marginTop: 16 }}>
      {shouldShowHistory && (
        <Section
          id="search-history"
          title="Вы искали ранее"
          collapsible
          rightAction={
            <TouchableOpacity onPress={handleClearHistory}>
              <Text style={styles.clearHistoryButton}>Очистить</Text>
            </TouchableOpacity>
          }
        >
          <View style={styles.historyContainer}>
            {visibleHistory.map((item, index) => (
              <View key={`${item}-${index}`} style={styles.historyItem}>
                <Pressable
                  style={styles.historyItemButton}
                  onPress={() => handleHistoryItemPress(item)}
                  hitSlop={6}
                >
                  <Icon name="time-outline" size={18} color={Colors.periwinkle} />
                  <Text style={styles.historyItemText}>{item}</Text>
                </Pressable>
                <Pressable
                  onPress={() => handleRemoveHistoryItem(item)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Icon name="close" size={18} color={Colors.textMuted} />
                </Pressable>
              </View>
            ))}
            {historyOverflow > 0 && (
              <Pressable
                onPress={handleHistoryExpandToggle}
                hitSlop={8}
                style={styles.historyExpandButton}
              >
                <Text style={styles.historyExpandText}>
                  {historyExpanded ? 'Свернуть' : `Показать ещё (${historyOverflow})`}
                </Text>
                <Icon
                  name={historyExpanded ? 'chevron-up' : 'chevron-down'}
                  size={16}
                  color={Colors.royalBlue}
                />
              </Pressable>
            )}
          </View>
        </Section>
      )}

      {newReleases.length > 0 && (
        <Section id="search-new-releases">
          <AutoRail
            title="Новинки"
            subtitle="Свежие релизы · Discogs"
            titleColor={Colors.royalBlue}
            items={newReleases}
            showYear
            onPick={handleNewReleasePick}
          />
        </Section>
      )}

      {/*
        OFFERS_UX.md Фича 4 — карусель «В наличии сейчас».
        Тот же AutoRail-паттерн что и Новинки Discogs выше, но мета-строка с
        ценой (через `itemBadgeRenderer`) вместо ♥-want-count. Кнопка
        «Смотреть все →» сейчас показывает toast — до реализации Фичи 3
        (чип-фильтр «В продаже»).
      */}
      {marketAsProfileRecords.length > 0 && (
        <Section id="search-market-arrivals">
          <AutoRail
            title="В наличии сейчас"
            subtitle={`Магазины${marketItems.length ? ` · ${marketItems.length}` : ''}`}
            titleColor={Colors.royalBlue}
            items={marketAsProfileRecords}
            onPick={handleMarketPick}
            headerActionLabel="Смотреть все →"
            onHeaderActionPress={handleMarketShowAll}
            itemBadgeRenderer={(r) => {
              const price = marketPriceByRecordId.get(r.id);
              // Тёмный текст — карусель живёт на светлом search-фоне.
              // White text был нечитабельным.
              return price ? <MiniPriceBadge price={price} color="#0E121C" /> : null;
            }}
          />
        </Section>
      )}

      {/* Curtain CTA — юзер прокручивает сюда, видит подсказку с
          progress-баром, продолжая тянуть → bar заполняется → на 100%
          haptic-success → release → auto-slide-in. */}
      <Reanimated.View style={[styles.searchHintBlock, curtainLabelStyle]}>
        <View style={styles.searchHintRow}>
          <Icon name="chevron-down" size={20} color={Colors.royalBlue} />
          <Text style={styles.searchHintText}>
            Прокрути вниз, чтобы попасть в <Text style={styles.searchHintBrand}>Маркет</Text>
          </Text>
        </View>
        {/* Progress-бар внизу CTA. Полностью заполнен на 100% pull'а. */}
        <View style={styles.searchHintProgressTrack} pointerEvents="none">
          <Reanimated.View style={[styles.searchHintProgressFill, ctaProgressFillStyle]} />
        </View>
      </Reanimated.View>
    </View>
  ) : null;

  const FilterModal = showFilters ? (
    <Modal
      visible={showFilters}
      transparent
      animationType="none"
      onRequestClose={closeFilters}
    >
      <View style={styles.modalContainer}>
        <Animated.View
          style={[styles.modalOverlay, { opacity: overlayOpacity }]}
        >
          <TouchableOpacity style={styles.modalOverlayPressable} onPress={closeFilters} activeOpacity={1} />
        </Animated.View>
        <Animated.View
          style={[
            styles.modalContent,
            { transform: [{ translateY: slideAnim }] }
          ]}
        >
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Фильтры</Text>
            <TouchableOpacity onPress={closeFilters}>
              <Icon name="close" size={24} color={Colors.text} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalBody}>
            {/* Формат */}
            <Text style={styles.filterLabel}>Формат</Text>
            <View style={styles.filterOptions}>
              {FORMAT_OPTIONS.map((option) => {
                const isSelected = option.value === undefined ? !tempFilters.format : tempFilters.format === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => updateTempFilter('format', option.value)}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Страна */}
            <View style={styles.filterLabelRow}>
              <Text style={styles.filterLabel}>Страна</Text>
              <TouchableOpacity onPress={() => setShowAllCountries(!showAllCountries)}>
                <Text style={styles.showAllButton}>
                  {showAllCountries ? 'Скрыть' : 'Показать все'}
                </Text>
              </TouchableOpacity>
            </View>
            <View style={styles.filterOptions}>
              {(showAllCountries ? ALL_COUNTRIES : MAIN_COUNTRIES).map((option) => {
                const isSelected = option.value === undefined ? !tempFilters.country : tempFilters.country === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => updateTempFilter('country', option.value)}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Год (декады) */}
            <Text style={styles.filterLabel}>Год издания</Text>
            <View style={styles.filterOptions}>
              {YEAR_OPTIONS.map((option) => {
                const isSelected = option.value === undefined ? !selectedDecade : selectedDecade === option.value;
                return (
                  <TouchableOpacity
                    key={option.label}
                    style={[styles.filterOption, isSelected && styles.filterOptionSelected]}
                    onPress={() => {
                      setSelectedDecade(option.value);
                      // Декада → year_min/year_max. Backend пробрасывает в Discogs как lucene-range.
                      const range = option.value && 'min' in option
                        ? { year_min: option.min, year_max: option.max }
                        : { year_min: undefined, year_max: undefined };
                      setTempFilters(prev => ({
                        ...prev,
                        year: undefined,
                        year_min: range.year_min,
                        year_max: range.year_max,
                      }));
                    }}
                  >
                    <Text style={[styles.filterOptionText, isSelected && styles.filterOptionTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Кнопка очистки */}
            {hasTempFilters && (
              <TouchableOpacity
                style={styles.clearFiltersButton}
                onPress={handleClearAllFilters}
              >
                <Text style={styles.clearFiltersText}>Очистить все фильтры</Text>
              </TouchableOpacity>
            )}
          </ScrollView>
        </Animated.View>
      </View>
    </Modal>
  ) : null;

  const handleProfilePress = useCallback(() => {
    router.push('/profile');
  }, [router]);

  const SearchHeader = (
    <View style={styles.searchContainer}>
      {/* Title row + avatar */}
      <View style={styles.topRow}>
        <AnimatedGradientText style={Typography.heroTitle}>Поиск</AnimatedGradientText>
        <Pressable
          style={styles.profileButton}
          onPress={handleProfilePress}
          hitSlop={12}
        >
          {user?.avatar_url ? (
            <Image source={resolveMediaUrl(user.avatar_url)} style={styles.avatar} cachePolicy="disk" />
          ) : (
            <LinearGradient
              colors={[Colors.royalBlue, Colors.periwinkle]}
              style={styles.avatarPlaceholder}
            >
              <Icon name="disc" size={20} color={Colors.background} />
            </LinearGradient>
          )}
        </Pressable>
      </View>

      {/* Search input — pill style */}
      <View style={styles.searchRow}>
        <View style={[styles.searchInputContainer, inputFocused && styles.searchInputFocused]}>
          <Icon name="search" size={20} color={Colors.royalBlue} />
          <TextInput
            style={styles.searchInput}
            value={searchInput}
            onChangeText={handleSearchInputChange}
            placeholder={isUserSearch ? "Имя пользователя..." : "Артист, альбом или @username"}
            placeholderTextColor={Colors.textMuted}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
            onFocus={() => { setInputFocused(true); setShowHistory(true); }}
            onBlur={() => { handleBlur(); setInputFocused(false); }}
            autoCapitalize="none"
            autoCorrect={false}
          />
          {searchInput.length > 0 && (
            <TouchableOpacity onPress={handleClear}>
              <Icon name="close-circle" size={20} color={Colors.textMuted} />
            </TouchableOpacity>
          )}
        </View>
        {!isUserSearch && (
          <TouchableOpacity
            ref={filtersTarget.ref}
            onLayout={filtersTarget.onLayout}
            collapsable={false}
            style={[styles.filterButton, hasActiveFilters && styles.filterButtonActive]}
            onPress={openFilters}
          >
            <Icon name="options-outline" size={20} color={hasActiveFilters ? Colors.background : Colors.text} />
          </TouchableOpacity>
        )}
      </View>

      {/* Dropdown с автодополнением */}
      {suggestions && (suggestions.artists.length > 0 || suggestions.masters.length > 0) && (
        <View style={styles.suggestDropdown}>
          {suggestions.artists.map((artist) => (
            <TouchableOpacity
              key={artist.artist_id}
              style={styles.suggestItem}
              onPress={() => {
                clearSuggestions();
                addToHistory(artist.name);
                router.push(`/artist/${artist.artist_id}`);
              }}
              activeOpacity={0.7}
            >
              {artist.thumb ? (
                <Image source={artist.thumb} style={styles.suggestThumb} contentFit="cover" cachePolicy="disk" />
              ) : (
                <View style={[styles.suggestThumb, styles.suggestThumbPlaceholder]}>
                  <Icon name="person-outline" size={16} color={Colors.textMuted} />
                </View>
              )}
              <View style={styles.suggestInfo}>
                <Text style={styles.suggestName} numberOfLines={1}>{cleanArtistName(artist.name)}</Text>
                <Text style={styles.suggestType}>Артист</Text>
              </View>
              <Icon name="arrow-forward-outline" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          ))}
          {suggestions.masters.map((master) => (
            <TouchableOpacity
              key={master.master_id}
              style={styles.suggestItem}
              onPress={() => {
                clearSuggestions();
                addToHistory(`${master.artist} ${master.title}`.trim());
                router.push({
                  pathname: `/master/${master.master_id}`,
                  params: {
                    title: master.title,
                    artist: master.artist,
                    year: master.year?.toString() || '',
                    cover: master.cover_image_url || '',
                  },
                });
              }}
              activeOpacity={0.7}
            >
              {master.thumb ? (
                <Image source={master.thumb} style={styles.suggestThumb} contentFit="cover" cachePolicy="disk" />
              ) : (
                <View style={[styles.suggestThumb, styles.suggestThumbPlaceholder]}>
                  <Icon name="disc-outline" size={16} color={Colors.textMuted} />
                </View>
              )}
              <View style={styles.suggestInfo}>
                <Text style={styles.suggestName} numberOfLines={1}>{master.title}</Text>
                <Text style={styles.suggestType} numberOfLines={1}>{cleanArtistName(master.artist)}{master.year ? ` · ${master.year}` : ''}</Text>
              </View>
              <Icon name="arrow-forward-outline" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          ))}
        </View>
      )}

      {HomeSections}
    </View>
  );

  // Рендер списка пользователей (общий для обоих режимов)
  const renderUserList = (users: UserWithStats[], limit?: number) => {
    const displayUsers = limit ? users.slice(0, limit) : users;
    return displayUsers.map((u) => (
      <TouchableOpacity
        key={u.id}
        style={styles.userCard}
        onPress={() => handleUserPress(u)}
        activeOpacity={0.8}
      >
        <View style={styles.userImageContainer}>
          {u.avatar_url ? (
            <Image
              source={resolveMediaUrl(u.avatar_url)}
              style={styles.topArtistImage}
              contentFit="cover"
              cachePolicy="disk"
            />
          ) : (
            <View style={styles.userPlaceholder}>
              <Icon name="person" size={24} color={Colors.textMuted} />
            </View>
          )}
        </View>
        <View style={styles.userInfo}>
          <Text style={styles.userLabel}>@{u.username}</Text>
          <Text style={styles.userName} numberOfLines={1}>
            {u.display_name || u.username}
          </Text>
        </View>
        <Text style={styles.userStatText}>{u.collection_count} пластинок</Text>
      </TouchableOpacity>
    ));
  };

  const HeaderContent = isUserSearch ? (
    // Режим поиска пользователей (@)
    <View>
      {SearchHeader}

      {userResults.length > 0 && (
        <View>
          <Text style={styles.sectionTitle}>Пользователи</Text>
          {renderUserList(userResults)}
        </View>
      )}

      {isUserSearchLoading && userResults.length === 0 && (
        <View style={styles.loadingContainer}>
          <Text style={styles.loadingText}>Поиск пользователей...</Text>
        </View>
      )}

      {!isUserSearchLoading && userResults.length === 0 && searchInput.length > 1 && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Пользователь не найден
          </Text>
        </View>
      )}

      {searchInput === '@' && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Введите имя пользователя после @
          </Text>
        </View>
      )}
    </View>
  ) : (
    // Обычный режим поиска
    <View>
      {SearchHeader}

      {correctedQuery && (
        <View style={styles.correctionBanner}>
          <Text style={styles.correctionBannerText}>
            Показаны результаты для:{' '}
            <Text style={styles.correctionBannerBold}>{correctedQuery}</Text>
          </Text>
        </View>
      )}

      {artistResults.length > 0 && (
        <View>
          {/* Первый артист — крупная gradient-карточка */}
          <TouchableOpacity
            onPress={() => handleArtistPress(artistResults[0])}
            activeOpacity={0.8}
          >
            <LinearGradient
              colors={Gradients.blue as [string, string]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.topArtistCard}
            >
              <View style={styles.topArtistImageContainer}>
                {!topArtistImgError && (artistResults[0].cover_image_url || artistResults[0].thumb_image_url) ? (
                  <Image
                    source={artistResults[0].cover_image_url || artistResults[0].thumb_image_url}
                    style={styles.topArtistImage}
                    contentFit="cover"
                    cachePolicy="disk"
                    onError={() => setTopArtistImgError(true)}
                  />
                ) : (
                  <View style={styles.topArtistPlaceholder}>
                    <Icon name="person-outline" size={32} color="rgba(255,255,255,0.7)" />
                  </View>
                )}
              </View>
              <View style={styles.topArtistInfo}>
                <Text style={styles.topArtistLabel}>Артист</Text>
                <Text style={styles.topArtistName} numberOfLines={1}>{cleanArtistName(artistResults[0].name)}</Text>
              </View>
            </LinearGradient>
          </TouchableOpacity>

          {/* Остальные артисты — компактный список */}
          {visibleArtists.slice(1).map((artist) => (
            <TouchableOpacity
              key={artist.artist_id}
              style={styles.secondaryArtistCard}
              onPress={() => handleArtistPress(artist)}
              activeOpacity={0.8}
            >
              <View style={styles.topArtistImageContainer}>
                {!secondaryImgErrors.has(artist.artist_id) && (artist.cover_image_url || artist.thumb_image_url) ? (
                  <Image
                    source={artist.cover_image_url || artist.thumb_image_url}
                    style={styles.topArtistImage}
                    contentFit="cover"
                    cachePolicy="disk"
                    onError={() => setSecondaryImgErrors(prev => new Set([...prev, artist.artist_id]))}
                  />
                ) : (
                  <View style={[styles.topArtistPlaceholder, styles.secondaryArtistPlaceholder]}>
                    <Icon name="person-outline" size={24} color={Colors.textMuted} />
                  </View>
                )}
              </View>
              <View style={styles.topArtistInfo}>
                <Text style={styles.secondaryArtistLabel}>Артист</Text>
                <Text style={styles.secondaryArtistName} numberOfLines={1}>{cleanArtistName(artist.name)}</Text>
              </View>
            </TouchableOpacity>
          ))}

          {/* Кнопка "Ещё X артистов" */}
          {!showAllArtists && artistResults.length > 3 && (
            <TouchableOpacity
              style={styles.showMoreArtistsButton}
              onPress={() => setShowAllArtists(true)}
              activeOpacity={0.7}
            >
              <Text style={styles.showMoreArtistsText}>
                Ещё {artistResults.length - 3} артистов
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Пользователи */}
      {userResults.length > 0 && (
        <View>
          <Text style={styles.sectionTitle}>Пользователи</Text>
          {renderUserList(userResults, 3)}
        </View>
      )}

      {results.length > 0 && (
        <Text style={styles.sectionTitle}>Релизы</Text>
      )}

      {isLoading && results.length === 0 && artistResults.length === 0 && (
        <View style={styles.loadingContainer}>
          <Text style={styles.loadingText}>Загрузка...</Text>
        </View>
      )}

      {!isLoading && results.length === 0 && artistResults.length === 0 && query && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyText}>
            Ничего не найдено. Попробуйте изменить запрос.
          </Text>
        </View>
      )}

      {/* Empty-state «Введите название» — перенесли в HomeSections выше
          (между «Новинками» и Маркетом), чтобы не торчало за tab-bar'ом. */}
    </View>
  );

  return (
    <View style={styles.container}>
      {/* Слой Поиска (нижний). Не движется — статичен. Полностью покрывается
          Маркет-слоем когда тот наезжает сверху. */}
      <View
        pointerEvents={committed ? 'none' : 'auto'}
        style={StyleSheet.absoluteFill}
      >
        {/* Фон Поиска */}
        <MarketBackground forcedMode="search" />

        <KeyboardAvoidingView
          style={[styles.flex, { paddingTop: insets.top, backgroundColor: 'transparent' }]}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <RecordGrid
            data={isUserSearch ? [] : results}
            onRecordPress={handleRecordPress}
            onArtistPress={handleArtistNamePress}
            onAddToCollection={handleAddToCollection}
            onAddToWishlist={handleAddToWishlist}
            showActions
            isLoading={isUserSearch ? false : isLoading}
            onEndReached={!isUserSearch && hasMore ? () => {
              if (loadMoreTimer.current) clearTimeout(loadMoreTimer.current);
              loadMoreTimer.current = setTimeout(loadMore, 300);
            } : undefined}
            emptyMessage=""
            ListHeaderComponent={HeaderContent}
            cardVariant="compact"
            onScroll={onScrollSearch}
            scrollToTopRef={scrollToTopRef}
            scrollToOffsetRef={scrollToOffsetRef}
          />

          {FilterModal}
        </KeyboardAvoidingView>
      </View>

      {/* Слой Маркета (верхний). При committedAnim=0 целиком под экраном
          (translateY=SCREEN_H). На commit'е сам spring'ом приезжает к 0,
          накрывая Поиск. У слоя свой собственный MarketBackground — никакого
          cross-fade с Поиском, чистый slide-up. */}
      <Reanimated.View
        pointerEvents={committed ? 'auto' : 'none'}
        style={[StyleSheet.absoluteFill, marketLayerStyle]}
      >
        <MarketBackground forcedMode="market" />
        <MarketMain
          onScroll={onScrollMarket}
          scrollEnabled={committed}
          paddingTop={insets.top + 8}
          pullFraction={pullFraction}
        />
      </Reanimated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    // Background — ТОЛЬКО MarketBackground (двухслойный absolute fill).
    // Без явного backgroundColor на container — иначе он перекроет market-layer.
    // Базовый разогрев цвета (#FAFBFF) уже залит внутри SearchBgStatic при alpha=1.
  },
  flex: {
    flex: 1,
  },
  // Curtain CTA — юзер скроллит сюда, продолжает тянуть → progress внизу
  // блока наполняется до 100% → commit запускает in-place slide-up Маркет-
  // слоя. overflow:hidden — чтобы fill-bar не вылезал из rounded corners.
  searchHintBlock: {
    marginHorizontal: Spacing.md,
    marginTop: Spacing.lg,
    marginBottom: Spacing.md,
    paddingVertical: 14,
    paddingHorizontal: 14,
    backgroundColor: 'rgba(59, 75, 245, 0.06)',
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: 'rgba(59, 75, 245, 0.10)',
    overflow: 'hidden',
  },
  searchHintRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  searchHintText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    lineHeight: 16,
  },
  searchHintBrand: {
    fontFamily: 'Inter_700Bold',
    color: Colors.royalBlue,
    fontWeight: '700',
  },
  // Тонкий progress track внизу CTA, absolute — без влияния на layout.
  searchHintProgressTrack: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 3,
    backgroundColor: 'rgba(59, 75, 245, 0.10)',
  },
  searchHintProgressFill: {
    position: 'absolute',
    top: 0,
    left: 0,
    bottom: 0,
    width: '100%',
    backgroundColor: Colors.royalBlue,
    // @ts-ignore transformOrigin поддерживается RN 0.71+
    transformOrigin: 'left',
  },
  searchContainer: {
    paddingBottom: Spacing.md,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  profileButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: Colors.lavender,
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
  },
  searchInputContainer: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F5F5F7',
    borderRadius: 26,
    paddingHorizontal: Spacing.md,
    height: 52,
    gap: Spacing.sm,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  searchInputFocused: {
    borderColor: Colors.royalBlue,
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    fontSize: ms(16),
    color: Colors.text,
    padding: 0,
    margin: 0,
    textAlignVertical: 'center',
  },
  filterButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#F5F5F7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterButtonActive: {
    backgroundColor: Colors.royalBlue,
  },
  historyContainer: {
    marginTop: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
  },
  historyHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.sm,
  },
  historyTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  clearHistoryButton: {
    ...Typography.caption,
    color: Colors.royalBlue,
  },
  historyItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  historyItemButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  historyItemText: {
    ...Typography.body,
    color: Colors.text,
    flex: 1,
  },
  historyExpandButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: Spacing.sm + 2,
    marginTop: 2,
  },
  historyExpandText: {
    ...Typography.caption,
    color: Colors.royalBlue,
    fontWeight: '600',
  },
  modalContainer: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalOverlayPressable: {
    flex: 1,
  },
  modalContent: {
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  modalTitle: {
    ...Typography.h3,
    color: Colors.text,
  },
  modalBody: {
    padding: Spacing.lg,
  },
  filterLabel: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginBottom: Spacing.sm,
    marginTop: Spacing.md,
  },
  filterLabelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.md,
    marginBottom: Spacing.sm,
  },
  showAllButton: {
    ...Typography.caption,
    color: Colors.royalBlue,
  },
  filterOptions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  filterOption: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterOptionSelected: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  filterOptionText: {
    ...Typography.body,
    color: Colors.text,
  },
  filterOptionTextSelected: {
    color: Colors.background,
    fontWeight: '600',
  },
  clearFiltersButton: {
    marginTop: Spacing.xl,
    padding: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
  },
  clearFiltersText: {
    ...Typography.body,
    color: Colors.error,
    fontWeight: '600',
  },
  sectionTitle: {
    ...Typography.h2,
    color: Colors.text,
    marginBottom: Spacing.md,
  },
  topArtistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
  },
  topArtistImageContainer: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 3,
    borderColor: '#FFFFFF',
    overflow: 'hidden',
  },
  topArtistImage: {
    width: '100%',
    height: '100%',
  },
  topArtistPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  topArtistInfo: {
    flex: 1,
    marginLeft: Spacing.md,
  },
  topArtistLabel: {
    ...Typography.caption,
    color: 'rgba(255,255,255,0.7)',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  topArtistName: {
    fontSize: ms(22),
    fontFamily: 'Inter_700Bold',
    color: '#FFFFFF',
    marginTop: 2,
  },
  suggestDropdown: {
    marginTop: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  suggestItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    gap: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  suggestThumb: {
    width: 36,
    height: 36,
    borderRadius: BorderRadius.sm,
  },
  suggestThumbPlaceholder: {
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  suggestInfo: {
    flex: 1,
    minWidth: 0,
  },
  suggestName: {
    ...Typography.bodyBold,
    color: Colors.text,
    fontSize: ms(14),
  },
  suggestType: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  correctionBanner: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    borderLeftWidth: 3,
    borderLeftColor: Colors.royalBlue,
  },
  correctionBannerText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  correctionBannerBold: {
    fontWeight: '700',
    color: Colors.text,
  },
  secondaryArtistCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
  },
  secondaryArtistPlaceholder: {
    backgroundColor: Colors.surface,
  },
  secondaryArtistLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  secondaryArtistName: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginTop: 2,
  },
  showMoreArtistsButton: {
    alignItems: 'center',
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.md,
  },
  showMoreArtistsText: {
    ...Typography.body,
    color: Colors.royalBlue,
    fontWeight: '600',
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.sm,
  },
  userImageContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    overflow: 'hidden',
    backgroundColor: Colors.background,
  },
  userPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.background,
  },
  userInfo: {
    flex: 1,
    marginLeft: Spacing.md,
  },
  userLabel: {
    ...Typography.caption,
    color: Colors.textMuted,
    letterSpacing: 0.3,
  },
  userName: {
    ...Typography.bodyBold,
    color: Colors.text,
    marginTop: 2,
  },
  userStatText: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginRight: Spacing.xs,
  },
  loadingContainer: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  loadingText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  emptyContainer: {
    padding: Spacing.xl,
    alignItems: 'center',
  },
  emptyText: {
    ...Typography.body,
    color: Colors.textMuted,
    textAlign: 'center',
  },
});
