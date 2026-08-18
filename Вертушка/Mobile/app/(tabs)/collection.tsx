/**
 * Экран коллекции — Editorial Gradient Edition
 * Переключатель Моё / Хочу, editorial заголовок, expanded cards
 */
import { useEffect, useCallback, useState, useRef, useMemo } from 'react';
import { View, StyleSheet, Alert, TouchableOpacity, Text, Animated, ScrollView, LayoutAnimation, UIManager, Platform, Easing } from 'react-native';
import { toast } from '../../lib/toast';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { RadarIcon } from '../../components/RadarIcon';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { AnimatedGradientText } from '../../components/AnimatedGradientText';
import { ProfileAvatarButton } from '../../components/ProfileAvatarButton';
import { GradientText } from '../../components/GradientText';
import { RecordGrid } from '../../components/RecordGrid';
import { ZoomableRecordGrid } from '../../components/ZoomableRecordGrid';
import { FolderPickerModal } from '../../components/FolderPickerModal';
import { WishlistFolderPickerModal } from '../../components/WishlistFolderPickerModal';
import { SegmentedControl } from '../../components/ui';
import { useCollectionStore, useAuthStore } from '../../lib/store';
import { FirstStepsCard } from '../../components/onboarding/FirstStepsCard';
import { CoachTip } from '../../components/onboarding/CoachTip';
import { CoachPulse } from '../../components/onboarding/CoachPulse';
import { useCoachSpotlight } from '../../lib/coachSpotlight';
import { PinchHint } from '../../components/onboarding/PinchHint';
import { useCoachMark } from '../../lib/useCoachMark';
import { ms } from '../../lib/responsive';
import { api, resolveMediaUrl, recordPreviewParams } from '../../lib/api';
import { analytics } from '../../lib/analytics';
import { countPull } from '../../lib/eggTracker';
import { CollectionItem, WishlistItem, CollectionTab, RecordOffersSummary, Offer } from '../../lib/types';
import { Colors, Spacing, Typography, BorderRadius, Gradients, Shadows } from '../../constants/theme';
import { summaryToHotStock, type ResolvedHotStock } from '../../components/HotStockTag';
import WishlistListSwipe from '../../components/market/WishlistListSwipe';
import OffersBottomSheet, { type OffersBottomSheetRef } from '../../components/market/OffersBottomSheet';
import { type OfferDetailData } from '../../components/market/OfferDetailCard';
import { Linking } from 'react-native';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

function getFormatDisplayInfo(format?: string): { label: string; verb: string } {
  if (!format) return { label: 'Винил', verb: 'добавлен' };
  const f = format.toLowerCase();
  if (f.includes('cassette')) return { label: 'Кассета', verb: 'добавлена' };
  if (f.includes('box set')) return { label: 'Бокс-сет', verb: 'добавлен' };
  if (f.includes('cd')) return { label: 'CD', verb: 'добавлен' };
  return { label: 'Винил', verb: 'добавлен' };
}

const folderPlaceholder = require('../../assets/images/folder-placeholder.png');

const SEGMENTS: { key: CollectionTab; label: string }[] = [
  { key: 'collection', label: 'В наличии' },
  { key: 'wishlist', label: 'Вишлист' },
];

type ViewMode = 'grid' | 'list';

type FormatFilter = 'all' | 'vinyl' | 'cd' | 'cassette' | 'box_set';
type SortMode = 'added_desc' | 'added_asc' | 'title';

const SORT_OPTIONS: { key: SortMode; label: string }[] = [
  { key: 'added_desc', label: 'Новые → старые' },
  { key: 'added_asc', label: 'Старые → новые' },
  { key: 'title', label: 'По названию' },
];

const FORMAT_OPTIONS: { key: FormatFilter; label: string; match: string[] }[] = [
  { key: 'all', label: 'Все форматы', match: [] },
  { key: 'vinyl', label: 'Винил', match: ['Vinyl', 'LP', '12"', '10"', '7"'] },
  { key: 'cd', label: 'CD', match: ['CD'] },
  { key: 'cassette', label: 'Кассета', match: ['Cassette'] },
  { key: 'box_set', label: 'Бокс-сет', match: ['Box Set'] },
];

export default function CollectionScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedItems, setSelectedItems] = useState<Set<string>>(new Set());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [activeFilter, setActiveFilter] = useState<FormatFilter>('all');
  const [activeSort, setActiveSort] = useState<SortMode>('added_desc');
  const modeAnim = useRef(new Animated.Value(0)).current;
  const menuAnim = useRef(new Animated.Value(0)).current;
  const viewIconAnim = useRef(new Animated.Value(0)).current; // 0 = grid, 1 = list
  const filterMenuAnim = useRef(new Animated.Value(0)).current; // 0 = closed, 1 = open
  const sortMenuAnim = useRef(new Animated.Value(0)).current;   // 0 = closed, 1 = open
  const radarPulse = useRef(new Animated.Value(0)).current;     // радар-кнопка sonar-loop
  const radarPulse2 = useRef(new Animated.Value(0)).current;    // второе кольцо (стаггер)
  const [radarMatchCount, setRadarMatchCount] = useState(0);
  // Счётчик удалений «по одной» за сессию — триггер подсказки про мультивыбор.
  const [soloRemovals, setSoloRemovals] = useState(0);

  const filterMenuOpen = useRef(false);
  const sortMenuOpen = useRef(false);

  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [showWishlistFolderPicker, setShowWishlistFolderPicker] = useState(false);
  const { user } = useAuthStore();

  const handleProfilePress = () => {
    router.push('/profile');
  };

  const {
    activeTab,
    collectionItems,
    collectionHasMore,
    isLoadingMore,
    wishlistItems,
    folders,
    wishlistFolders,
    isLoading,
    stats,
    setActiveTab,
    fetchCollections,
    fetchCollectionItems,
    loadMoreCollectionItems,
    fetchWishlistItems,
    fetchWishlistFolders,
    removeFromCollection,
    removeFromWishlist,
    moveToCollection,
    createFolder,
    addItemsToFolder,
    createWishlistFolder,
    addItemsToWishlistFolder,
  } = useCollectionStore();

  // record.id пластинок на радаре (subscribed) — для бейджа на карточках.
  const radarRecordIds = useMemo(
    () => new Set(wishlistItems.filter((w) => w.notify_mode === 'subscribed').map((w) => w.record.id)),
    [wishlistItems],
  );

  // Загрузка данных при монтировании
  useEffect(() => {
    fetchCollections().then(() => {
      fetchCollectionItems();
      fetchWishlistItems();
      fetchWishlistFolders();
    });
  }, []);

  // ─────────────────────────────────────────────────────────────────
  // Hot Stock pill для wishlist (OFFERS_UX.md §2 + MARKET_AND_PRICE_DRAWER.md §2.1).
  // При активном wishlist-tab тянем batch summary для всех 50-100 wishlist
  // items одним POST'ом. RecordGrid/ZoomableRecordGrid рендерит pill в
  // правом нижнем углу карточки. Тап на карточку → /record/[id] где
  // юзер видит полный OffersBlock (Phase A) + future OffersBottomSheet.
  // ─────────────────────────────────────────────────────────────────
  const [hotStockMap, setHotStockMap] = useState<Map<string, ResolvedHotStock | null>>(new Map());
  // Raw summary map нужен для list-swipe (показать min_price + stores_count)
  const [summaryMap, setSummaryMap] = useState<Map<string, RecordOffersSummary>>(new Map());
  // Bottom-sheet refs + state для открытия цен при свайпе по вишлист-строке
  const offersSheetRef = useRef<OffersBottomSheetRef>(null);
  const [buyingListingId, setBuyingListingId] = useState<string | undefined>(undefined);

  // Lazy fetch full offers (exact + alt-version по master_id) + open sheet
  const handleWishlistSwipeOpen = useCallback(async (wi: WishlistItem) => {
    const discogsId = wi.record?.discogs_id;
    if (!discogsId) {
      router.push(`/record/${wi.record.id}`);
      return;
    }
    try {
      // ВАЖНО: getOfferDetailsFull тянет и exact, и alt-version (другой
      // pressing того же master_id). getRecordOffers даёт только exact.
      const full = await api.getOfferDetailsFull(discogsId, true);
      const offers = full?.offers ?? [];
      if (offers.length === 0) {
        router.push(`/record/${discogsId}`);
        return;
      }
      // Fallback cover: если у конкретного offer нет image_url —
      // используем cover_image_url самой пластинки. Без этого в карточке
      // отображается серый квадрат (юзер именно об этом писал).
      const fallbackCover = wi.record.cover_image_url ?? undefined;
      const mapOffer = (o: typeof offers[number], isAlt: boolean): OfferDetailData & { recordDiscogsId?: string | null } => ({
        listingId: o.listing_id,
        storeSlug: o.store.slug,
        storeName: o.store.name,
        priceRub: Number(o.price_rub),
        format: o.format ?? undefined,
        vinylColor: o.vinyl_color ?? undefined,
        condition: o.condition ?? undefined,
        catalogNumber: o.catalog_number ?? undefined,
        // OfferDetailCard prop = coverUrl (НЕ coverImageUrl). Был баг —
        // серый квадрат в bottom-sheet, потому что неправильное имя поля.
        coverUrl: o.image_url ?? fallbackCover,
        artist: wi.record.artist,
        title: wi.record.title,
        isAlt,
        // Для onCardPress navigation: для alt-version листинга
        // record_discogs_id — это discogs_id ДРУГОГО пресса (не из вишлиста).
        recordDiscogsId: o.record_discogs_id ?? null,
      });
      // Album-level (другой пресс мастера ИЛИ неуверенный матч) → нижняя секция.
      // isAlt (2-й арг mapOffer) = навигация на другой пресс — только для
      // настоящего is_alt_version; album-той-же-записи покупается напрямую.
      const isAlbum = (o: Offer): boolean =>
        !!o.is_alt_version || o.pressing_match === 'album';
      const exact: OfferDetailData[] = offers
        .filter((o) => !isAlbum(o))
        .map((o) => mapOffer(o, false));
      const alt: OfferDetailData[] = offers
        .filter((o) => isAlbum(o))
        .map((o) => mapOffer(o, !!o.is_alt_version));
      const minPrice = exact[0]?.priceRub ?? alt[0]?.priceRub ?? 0;
      offersSheetRef.current?.present({
        artist: wi.record.artist,
        title: wi.record.title,
        minPriceRub: minPrice,
        exactOffers: exact,
        altOffers: alt,
      });
    } catch {
      // fallback на детальную если оферы упали
      router.push(`/record/${discogsId}`);
    }
  }, [router]);

  const handleBuyPress = useCallback(async (offer: OfferDetailData) => {
    setBuyingListingId(offer.listingId);
    analytics.offerClick({
      listing_id: offer.listingId,
      store_slug: offer.storeSlug,
      price_rub: offer.priceRub,
      source: 'wishlist_swipe',   // discogs_id свайп-ценнику неизвестен
    });
    let urlToOpen: string | null = null;
    try {
      const { url } = await api.trackOfferClick(offer.listingId, 'wishlist_swipe');
      urlToOpen = url;
    } catch {
      // backend упал — открываем без affiliate tracking
    }
    setBuyingListingId(undefined);
    if (urlToOpen) {
      try { await Linking.openURL(urlToOpen); } catch { /* ignore */ }
    }
  }, []);

  useEffect(() => {
    if (activeTab !== 'wishlist' || wishlistItems.length === 0) {
      setHotStockMap(new Map());
      setSummaryMap(new Map());
      return;
    }
    let cancelled = false;
    (async () => {
      // Собираем discogs_id из wishlist items (max 100 в одном запросе).
      const discogsIds = wishlistItems
        .map((wi) => wi.record?.discogs_id)
        .filter((id): id is string => !!id)
        .slice(0, 100);
      if (discogsIds.length === 0) return;
      try {
        const summary: Record<string, RecordOffersSummary> = await api.getOffersSummary(discogsIds);
        if (cancelled) return;
        const map = new Map<string, ResolvedHotStock | null>();
        const rawMap = new Map<string, RecordOffersSummary>();
        for (const [discogsId, s] of Object.entries(summary)) {
          map.set(discogsId, summaryToHotStock(s, { context: 'wishlist', isGrid: true }));
          rawMap.set(discogsId, s);
        }
        setHotStockMap(map);
        setSummaryMap(rawMap);
      } catch {
        /* silent — pill просто не появится при ошибке */
      }
    })();
    return () => { cancelled = true; };
  }, [activeTab, wishlistItems]);

  // Сброс режима выбора при смене вкладки
  useEffect(() => {
    setIsSelectionMode(false);
    setSelectedItems(new Set());
  }, [activeTab]);

  // Радар-кнопка: sonar-пульс (два кольца со стаггером). Перезапускаем при каждом
  // показе кнопки — иначе после размонтирования (уход с вишлиста) нативный луп
  // отрывается от вьюхи и по возвращении кольца застывают на одном кадре.
  useEffect(() => {
    if (activeTab !== 'wishlist' || isSelectionMode) return;
    const mk = (v: Animated.Value) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(v, { toValue: 1, duration: 2200, easing: Easing.out(Easing.quad), useNativeDriver: true }),
          Animated.timing(v, { toValue: 0, duration: 0, useNativeDriver: true }),
        ]),
      );
    radarPulse.setValue(0);
    radarPulse2.setValue(0);
    const l1 = mk(radarPulse);
    l1.start();
    let l2: Animated.CompositeAnimation | undefined;
    const t = setTimeout(() => {
      l2 = mk(radarPulse2);
      l2.start();
    }, 1100);
    return () => {
      clearTimeout(t);
      l1.stop();
      l2?.stop();
    };
  }, [activeTab, isSelectionMode, radarPulse, radarPulse2]);

  useEffect(() => {
    if (activeTab !== 'wishlist') return;
    api.getRadar().then((r) => setRadarMatchCount(r.match_count)).catch(() => {});
  }, [activeTab, wishlistItems]);

  // Анимация смены кнопки Выбрать ↔ Отмена + скрытие меню
  useEffect(() => {
    Animated.parallel([
      Animated.spring(modeAnim, {
        toValue: isSelectionMode ? 1 : 0,
        tension: 220,
        friction: 14,
        useNativeDriver: true,
      }),
      Animated.timing(menuAnim, {
        toValue: isSelectionMode ? 0 : 1,
        duration: 300,
        useNativeDriver: false, // height animation needs false
      }),
    ]).start();
  }, [isSelectionMode]);

  // Анимация иконки grid/list
  const handleToggleViewMode = () => {
    const next: ViewMode = viewMode === 'grid' ? 'list' : 'grid';
    Animated.timing(viewIconAnim, {
      toValue: next === 'list' ? 1 : 0,
      duration: 250,
      useNativeDriver: true,
    }).start();
    LayoutAnimation.configureNext(LayoutAnimation.create(
      300,
      LayoutAnimation.Types.easeInEaseOut,
      LayoutAnimation.Properties.opacity,
    ));
    setViewMode(next);
  };

  // useNativeDriver: false — нужен для анимации maxHeight
  const smoothCloseFilter = (cb?: () => void) => {
    Animated.timing(filterMenuAnim, {
      toValue: 0,
      duration: 220,
      useNativeDriver: false,
    }).start(() => {
      filterMenuOpen.current = false;
      cb?.();
    });
  };

  const smoothCloseSort = (cb?: () => void) => {
    Animated.timing(sortMenuAnim, {
      toValue: 0,
      duration: 220,
      useNativeDriver: false,
    }).start(() => {
      sortMenuOpen.current = false;
      cb?.();
    });
  };

  // Открытие/закрытие фильтр-меню с анимацией (закрывает sort, если открыт)
  const handleToggleFilterMenu = () => {
    if (filterMenuOpen.current) {
      smoothCloseFilter();
    } else {
      if (sortMenuOpen.current) smoothCloseSort();
      filterMenuOpen.current = true;
      Animated.spring(filterMenuAnim, {
        toValue: 1,
        tension: 280,
        friction: 22,
        useNativeDriver: false,
      }).start();
    }
  };

  const handleToggleSortMenu = () => {
    if (sortMenuOpen.current) {
      smoothCloseSort();
    } else {
      if (filterMenuOpen.current) smoothCloseFilter();
      sortMenuOpen.current = true;
      Animated.spring(sortMenuAnim, {
        toValue: 1,
        tension: 280,
        friction: 22,
        useNativeDriver: false,
      }).start();
    }
  };

  const handleSelectFilter = (filter: FormatFilter) => {
    smoothCloseFilter(() => setActiveFilter(filter));
  };

  const handleSelectSort = (sort: SortMode) => {
    smoothCloseSort(() => setActiveSort(sort));
  };

  const handleRefresh = useCallback(async () => {
    countPull();  // пасхалка «Заело»: 78 обновлений за сессию
    setIsRefreshing(true);
    try {
      if (activeTab === 'collection') {
        await fetchCollectionItems();
      } else {
        await fetchWishlistItems();
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [activeTab, fetchCollectionItems, fetchWishlistItems]);

  const handleRecordPress = (item: CollectionItem | WishlistItem) => {
    const recordId = item.record.discogs_id || item.record.id;
    // preview-параметры → мгновенная отрисовка карточки (обложка уже в
    // disk-кэше сетки, тот же full-res файл, качество не меняется).
    router.push({
      pathname: `/record/${recordId}` as any,
      params: recordPreviewParams(item.record),
    });
  };

  const handleArtistPress = useCallback(async (artistName: string) => {
    try {
      const response = await api.searchArtists(artistName, 1, 5);
      if (response.results.length > 0) {
        const artist = response.results[0];
        router.push(`/artist/${artist.artist_id}`);
      } else {
        toast.info('Артист не найден', `Не удалось найти артиста "${artistName}"`);
      }
    } catch (error: any) {
      console.error('Ошибка поиска артиста:', error);
      toast.error('Не удалось найти артиста');
    }
  }, [router]);

  const handleRemoveFromCollection = async (item: CollectionItem) => {
    Alert.alert(
      'Удалить из коллекции?',
      `"${item.record.title}" будет удалена из вашей коллекции`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromCollection(item.id);
              // Удаление по одной — сигнал, что человек не знает про мультивыбор.
              setSoloRemovals((n) => n + 1);
            } catch (error) {
              toast.error('Не удалось удалить из коллекции');
            }
          },
        },
      ]
    );
  };

  const handleRemoveFromWishlist = async (item: WishlistItem) => {
    const isBooked = !!item.is_booked;
    const title = isBooked ? 'Удалить пункт с активной бронью?' : 'Удалить из списка?';
    const message = isBooked
      ? `"${item.record.title}" уже бронирует другой человек. Если удалить — дарителю придёт уведомление, что подарок больше не нужен.`
      : `"${item.record.title}" будет удалена из списка желаний`;

    Alert.alert(
      title,
      message,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              await removeFromWishlist(item.id);
              setSoloRemovals((n) => n + 1);
            } catch (error) {
              toast.error('Не удалось удалить из списка');
            }
          },
        },
      ]
    );
  };

  const handleMoveToCollection = async (item: WishlistItem) => {
    Alert.alert(
      'Купил!',
      `Перенести "${item.record.title}" в коллекцию?`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Перенести',
          onPress: async () => {
            try {
              await moveToCollection(item.id);
              const fmt = getFormatDisplayInfo(item.record.format_type);
              toast.success(`${fmt.label} ${fmt.verb} в коллекцию`);
            } catch (error) {
              toast.error('Не удалось перенести в коллекцию');
            }
          },
        },
      ]
    );
  };

  // Режим выбора
  const handleToggleSelectionMode = () => {
    setIsSelectionMode(!isSelectionMode);
    setSelectedItems(new Set());
  };

  const handleLongPressItem = (itemId: string) => {
    if (!isSelectionMode) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      setIsSelectionMode(true);
      setSelectedItems(new Set([itemId]));
    }
  };

  const handleToggleItemSelection = (itemId: string) => {
    const newSelected = new Set(selectedItems);
    if (newSelected.has(itemId)) {
      newSelected.delete(itemId);
    } else {
      newSelected.add(itemId);
    }
    setSelectedItems(newSelected);
  };

  const handleSelectAll = () => {
    const data = (activeTab === 'collection' ? collectionItems : wishlistItems) as (CollectionItem | WishlistItem)[];
    if (selectedItems.size === data.length && data.length > 0) {
      setSelectedItems(new Set());
    } else {
      setSelectedItems(new Set(data.map((item) => item.id)));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedItems.size === 0) return;

    const count = selectedItems.size;
    const itemType = activeTab === 'collection' ? 'коллекции' : 'списка желаний';

    let bookedNote = '';
    if (activeTab === 'wishlist') {
      const bookedCount = wishlistItems
        .filter((w) => selectedItems.has(w.id))
        .filter((w) => w.is_booked)
        .length;
      if (bookedCount > 0) {
        bookedNote = `\n\n${bookedCount} из них уже бронируют — дарителям отправим уведомление об отмене.`;
      }
    }

    Alert.alert(
      'Удалить выбранные?',
      `Будет удалено ${count} пластинок из ${itemType}${bookedNote}`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            try {
              const itemsToDelete = Array.from(selectedItems);
              for (const itemId of itemsToDelete) {
                if (activeTab === 'collection') {
                  await removeFromCollection(itemId);
                } else {
                  await removeFromWishlist(itemId);
                }
              }
              setSelectedItems(new Set());
              setIsSelectionMode(false);
            } catch (error) {
              toast.error('Не удалось удалить выбранные пластинки');
            }
          },
        },
      ]
    );
  };

  const handleAddToFolder = async (folderId: string) => {
    try {
      // Определяем record_id для выбранных items
      const selectedCollectionItems = collectionItems.filter(item => selectedItems.has(item.id));

      // Загружаем папку, чтобы проверить что уже есть внутри
      const folderData = await api.getCollection(folderId);
      const existingRecordIds = new Set(
        (folderData.items || []).map((i: CollectionItem) => i.record_id)
      );

      // Фильтруем: только те, которых ещё нет в папке, дедуплицируя по record_id
      const seen = new Set<string>();
      const newItems = selectedCollectionItems.filter(item => {
        if (existingRecordIds.has(item.record_id)) return false;
        if (seen.has(item.record_id)) return false;
        seen.add(item.record_id);
        return true;
      });
      const duplicateCount = selectedCollectionItems.length - newItems.length;

      if (newItems.length === 0) {
        setShowFolderPicker(false);
        toast.info(
          'Уже в папке',
          duplicateCount === 1
            ? 'Эта пластинка уже находится в папке'
            : 'Все выбранные пластинки уже находятся в этой папке'
        );
        return;
      }

      await addItemsToFolder(folderId, newItems.map(item => item.id));
      setShowFolderPicker(false);
      setSelectedItems(new Set());
      setIsSelectionMode(false);

      if (duplicateCount > 0) {
        toast.success(`${newItems.length} пл. добавлено`, `${duplicateCount} уже были в папке — пропущены.`);
      }
    } catch {
      toast.error('Не удалось добавить в папку');
    }
  };

  const handleCreateFolder = () => {
    Alert.prompt(
      'Новая папка',
      'Введите название папки',
      async (name) => {
        if (!name?.trim()) return;
        await createFolder(name.trim());
      },
      'plain-text',
    );
  };

  const handleCreateWishlistFolder = () => {
    Alert.prompt(
      'Новая папка',
      'Введите название папки',
      async (name) => {
        if (!name?.trim()) return;
        try {
          await createWishlistFolder(name.trim());
        } catch {
          toast.error('Не удалось создать папку');
        }
      },
      'plain-text',
    );
  };

  const handleAddToWishlistFolder = async (folderId: string) => {
    try {
      const wishlistItemIds = wishlistItems
        .filter(item => selectedItems.has(item.id))
        .map(item => item.id);

      if (wishlistItemIds.length === 0) {
        setShowWishlistFolderPicker(false);
        return;
      }

      await addItemsToWishlistFolder(folderId, wishlistItemIds);
      setShowWishlistFolderPicker(false);
      setSelectedItems(new Set());
      setIsSelectionMode(false);
    } catch {
      toast.error('Не удалось добавить в папку');
    }
  };

  const handleBulkMoveToCollection = async () => {
    if (selectedItems.size === 0 || activeTab !== 'wishlist') return;

    const count = selectedItems.size;

    Alert.alert(
      'Перенести в коллекцию?',
      `Будет перенесено ${count} пластинок в коллекцию`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Перенести',
          onPress: async () => {
            try {
              const itemsToMove = Array.from(selectedItems);
              for (const itemId of itemsToMove) {
                await moveToCollection(itemId);
              }
              setSelectedItems(new Set());
              setIsSelectionMode(false);
            } catch (error) {
              toast.error('Не удалось перенести пластинки');
            }
          },
        },
      ]
    );
  };

  const rawData = (activeTab === 'collection' ? collectionItems : wishlistItems) as (CollectionItem | WishlistItem)[];

  // Фильтрация по формату
  const filtered = activeFilter === 'all' ? rawData : rawData.filter(item => {
    const formatType = (item.record.format_type || '').toLowerCase();
    const formatDesc = (item.record.format_description || '').toLowerCase();
    const matchWords = FORMAT_OPTIONS.find(f => f.key === activeFilter)?.match || [];
    return matchWords.some(w => {
      const wLower = w.toLowerCase();
      return formatType.includes(wLower) || formatDesc.includes(wLower);
    });
  });

  // Сортировка
  const data = (() => {
    const arr = [...filtered];
    const ts = (s?: string | null) => (s ? Date.parse(s) : 0);
    if (activeSort === 'added_desc') {
      arr.sort((a, b) => ts(b.added_at) - ts(a.added_at));
    } else if (activeSort === 'added_asc') {
      arr.sort((a, b) => {
        const av = a.added_at ? ts(a.added_at) : Number.POSITIVE_INFINITY;
        const bv = b.added_at ? ts(b.added_at) : Number.POSITIVE_INFINITY;
        return av - bv;
      });
    } else if (activeSort === 'title') {
      arr.sort((a, b) => (a.record.title || '').localeCompare(b.record.title || '', 'ru'));
    }
    return arr;
  })();

  const selectOpacity = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const selectScale = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0.85] });
  const cancelOpacity = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });
  const cancelScale = modeAnim.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] });

  // Анимация скрытия меню (segments + folders)
  const menuOpacity = menuAnim.interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, 0, 1] });

  // Анимация иконки view toggle
  const gridIconOpacity = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0] });
  const gridIconScale = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [1, 0.5] });
  const listIconOpacity = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 1] });
  const listIconScale = viewIconAnim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1] });

  const activeFilterLabel = FORMAT_OPTIONS.find(f => f.key === activeFilter)?.label || 'Все';

  // ==================== Контекстные подсказки ====================
  //
  // Каждая объясняет фичу в момент её разблокировки, а не «на входе». Порядок
  // объявления = приоритет: за запуск приложения показывается ровно одна
  // (лимит держит lib/coachMarks.ts), и достаётся он первому сработавшему.
  //
  // total_records, а не collectionItems.length: список постраничный, и после
  // импорта из Discogs первая страница может ещё не приехать.
  const recordCount = stats?.total_records ?? collectionItems.length;
  const isCollectionTab = activeTab === 'collection';

  // Второй аргумент — порог опыта, третий — «цель сейчас на экране». Порог
  // ручной показ из «Как это работает» обходит, вкладку — нет.
  const pinchTip = useCoachMark(
    'pinch-zoom',
    recordCount >= 12,
    isCollectionTab && viewMode === 'grid',
  );
  const foldersTip = useCoachMark(
    'folders',
    recordCount >= 15 && folders.length === 0,
    isCollectionTab,
  );
  const valueTip = useCoachMark('collection-value', recordCount >= 5, isCollectionTab);
  // Кольцо на кнопке ₽ в липкой шапке — она за пределами карточки подсказки,
  // поэтому связь между ними держится через спотлайт-ключ, а не через вёрстку.
  const valueSpotlight = useCoachSpotlight('collection-value');
  const foldersSpotlight = useCoachSpotlight('folders');
  const multiSelectSpotlight = useCoachSpotlight('multi-select');
  // Радару — 'glow', а не кольцо: у кнопки уже свой sonar. См. coachMarks.ts.
  const radarSpotlight = useCoachSpotlight('radar');
  const multiSelectTip = useCoachMark('multi-select', soloRemovals >= 2, isCollectionTab);
  const radarTip = useCoachMark('radar', wishlistItems.length > 0, !isCollectionTab);
  const marketTip = useCoachMark('market', wishlistItems.length >= 3, !isCollectionTab);
  const giftsTip = useCoachMark('gifts-incoming', wishlistItems.length > 0, !isCollectionTab);

  const ScrollableHeader = (
    <View style={styles.headerContainer}>
      {/* Чеклист новичка и контекстные подсказки. Живут в скроллящейся шапке,
          а не в липкой: та уже занята (Выбрать / вид / ₽ / фильтр / сортировка),
          и постоянно висящий блок съел бы высоту экрана. Здесь они уезжают
          вместе с папками. */}
      <Animated.View style={{ opacity: menuOpacity, maxHeight: menuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 900] }), overflow: 'hidden' }}>
        {activeTab === 'collection' && (
          <FirstStepsCard overrides={{ folders: handleCreateFolder }} />
        )}

        {/* Условие таба дублируется в рендере, а не только в enabled: подсказка
            уже могла стать видимой, и без этого она осталась бы висеть после
            переключения на соседнюю вкладку, где объясняет не то. */}
        {isCollectionTab && foldersTip.visible && (
          <CoachTip
            meta={foldersTip.meta}
            analyticsKey={foldersTip.meta.key}
            onDismiss={foldersTip.dismiss}
            action={{ label: 'Создать папку', onPress: handleCreateFolder }}
          />
        )}
        {isCollectionTab && valueTip.visible && (
          <CoachTip
            meta={valueTip.meta}
            analyticsKey={valueTip.meta.key}
            onDismiss={valueTip.dismiss}
            action={{ label: 'Посчитать', onPress: () => router.push('/collection/value') }}
          />
        )}
        {!isCollectionTab && radarTip.visible && (
          <CoachTip
            meta={radarTip.meta}
            analyticsKey={radarTip.meta.key}
            onDismiss={radarTip.dismiss}
            action={{ label: 'Открыть Радар', onPress: () => router.push('/radar' as any) }}
          />
        )}
        {!isCollectionTab && marketTip.visible && (
          <CoachTip
            meta={marketTip.meta}
            analyticsKey={marketTip.meta.key}
            onDismiss={marketTip.dismiss}
            action={{ label: 'Открыть Маркет', onPress: () => router.push('/market') }}
          />
        )}
        {!isCollectionTab && giftsTip.visible && (
          <CoachTip
            meta={giftsTip.meta}
            analyticsKey={giftsTip.meta.key}
            onDismiss={giftsTip.dismiss}
            action={{ label: 'Поделиться профилем', onPress: () => router.push('/profile') }}
          />
        )}
        {multiSelectTip.visible && (
          <CoachTip meta={multiSelectTip.meta}
            analyticsKey={multiSelectTip.meta.key} onDismiss={multiSelectTip.dismiss} />
        )}

        {/* Folders section (scrolls away) */}
        {activeTab === 'collection' && folders.length > 0 && (
          <View style={styles.foldersSection}>
            <Text style={styles.foldersSectionTitle}>Папки</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.foldersScroll}>
              <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateFolder}>
                <View style={styles.newFolderIcon}>
                  <Icon name="add" size={32} color={Colors.textMuted} />
                </View>
                <Text style={styles.newFolderText}>Новая</Text>
              </TouchableOpacity>
              {folders.map(folder => (
                <TouchableOpacity
                  key={folder.id}
                  style={styles.folderCard}
                  onPress={() => router.push(`/folder/${folder.id}` as any)}
                >
                  <Image source={folderPlaceholder} style={styles.folderImage} />
                  <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                  <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Подсказка про папки показывается ровно когда папок ещё нет, поэтому
            подсвечиваем заглушку, а не блок «Папки» — тот в этот момент не
            отрисован вовсе. */}
        {activeTab === 'collection' && folders.length === 0 && (
          <CoachPulse active={foldersSpotlight} radius={BorderRadius.md} inset={4}>
            <TouchableOpacity style={styles.createFirstFolder} onPress={handleCreateFolder}>
              <Icon name="folder-outline" size={20} color={Colors.textMuted} />
              <Text style={styles.createFirstFolderText}>Создать папку</Text>
            </TouchableOpacity>
          </CoachPulse>
        )}

        {activeTab === 'wishlist' && wishlistFolders.length > 0 && (
          <View style={styles.foldersSection}>
            <Text style={styles.foldersSectionTitle}>Папки</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.foldersScroll}>
              <TouchableOpacity style={styles.newFolderCard} onPress={handleCreateWishlistFolder}>
                <View style={styles.newFolderIcon}>
                  <Icon name="add" size={32} color={Colors.textMuted} />
                </View>
                <Text style={styles.newFolderText}>Новая</Text>
              </TouchableOpacity>
              {wishlistFolders.map(folder => (
                <TouchableOpacity
                  key={folder.id}
                  style={styles.folderCard}
                  onPress={() => router.push(`/wishlist-folder/${folder.id}` as any)}
                >
                  <Image source={folderPlaceholder} style={styles.folderImage} />
                  <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                  <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {activeTab === 'wishlist' && wishlistFolders.length === 0 && (
          <View>
            <TouchableOpacity style={styles.createFirstFolder} onPress={handleCreateWishlistFolder}>
              <Icon name="folder-outline" size={20} color={Colors.textMuted} />
              <Text style={styles.createFirstFolderText}>Создать папку</Text>
            </TouchableOpacity>
          </View>
        )}
      </Animated.View>
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Sticky: Коллекция → Сегменты → Тулбар */}
      <View style={styles.stickyToolbar}>
        {/* Title row: Коллекция + avatar */}
        <View style={styles.avatarRow}>
          <AnimatedGradientText style={Typography.heroTitle}>Коллекция</AnimatedGradientText>
          <ProfileAvatarButton onPress={handleProfilePress} />
        </View>

        {/* Segmented control (В наличии / Вишлист) */}
        <Animated.View style={{ opacity: menuOpacity, maxHeight: menuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 60] }), overflow: 'hidden' }}>
          <View style={styles.segmentContainer}>
            <SegmentedControl
              segments={SEGMENTS}
              selectedKey={activeTab}
              onSelect={setActiveTab}
              disabled={isSelectionMode}
            />
          </View>
        </Animated.View>

        {/* Toolbar row: Выбрать/Отмена + Grid/List + Filter */}
        <View style={styles.toolbarRow}>
          {/* Select / Cancel */}
          <View style={styles.headerButtonWrapper}>
            <Animated.View
              style={[styles.headerButtonAbsolute, { opacity: cancelOpacity, transform: [{ scale: cancelScale }] }]}
              pointerEvents={isSelectionMode ? 'auto' : 'none'}
            >
              <TouchableOpacity style={styles.cancelButton} onPress={handleToggleSelectionMode}>
                <Text style={styles.cancelButtonText}>Отмена</Text>
              </TouchableOpacity>
            </Animated.View>

            <Animated.View
              style={{ opacity: selectOpacity, transform: [{ scale: selectScale }] }}
              pointerEvents={isSelectionMode ? 'none' : 'auto'}
            >
              <CoachPulse active={multiSelectSpotlight} radius={20}>
                <TouchableOpacity onPress={handleToggleSelectionMode} activeOpacity={0.7}>
                  <LinearGradient
                    colors={Gradients.blue}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.selectButtonGradientBorder}
                  >
                    <View style={styles.selectButtonInner}>
                      <GradientText style={styles.selectButtonText}>Выбрать</GradientText>
                    </View>
                  </LinearGradient>
                </TouchableOpacity>
              </CoachPulse>
            </Animated.View>
          </View>

          {/* Grid / List toggle */}
          {!isSelectionMode && (
            <TouchableOpacity
              style={styles.viewToggleButton}
              onPress={handleToggleViewMode}
              activeOpacity={0.7}
            >
              <View style={styles.viewToggleIconContainer}>
                <Animated.View style={[styles.viewToggleIcon, { opacity: gridIconOpacity, transform: [{ scale: gridIconScale }] }]}>
                  <Icon name="grid-outline" size={18} color={Colors.royalBlue} />
                </Animated.View>
                <Animated.View style={[styles.viewToggleIcon, styles.viewToggleIconAbsolute, { opacity: listIconOpacity, transform: [{ scale: listIconScale }] }]}>
                  <Icon name="list-outline" size={18} color={Colors.royalBlue} />
                </Animated.View>
              </View>
            </TouchableOpacity>
          )}

          {/* Value button. Пока висит подсказка «Сколько стоит коллекция»,
              кнопка пульсирует — иначе текст называет ₽, а глазами её всё
              равно приходится искать среди пяти иконок шапки. */}
          {!isSelectionMode && activeTab === 'collection' && (
            <CoachPulse active={valueSpotlight} radius={18}>
              <TouchableOpacity
                style={styles.valueButton}
                onPress={() => router.push('/collection/value')}
                activeOpacity={0.7}
              >
                <Icon name="currency-rub" size={18} color={Colors.royalBlue} />
              </TouchableOpacity>
            </CoachPulse>
          )}

          {/* Filter button */}
          {!isSelectionMode && (
            <View>
              <TouchableOpacity
                style={[styles.filterButton, activeFilter !== 'all' && styles.filterButtonActive]}
                onPress={handleToggleFilterMenu}
                activeOpacity={0.7}
              >
                <Icon
                  name="options-outline"
                  size={18}
                  color={activeFilter !== 'all' ? Colors.background : Colors.royalBlue}
                />
                {activeFilter !== 'all' && (
                  <Text style={styles.filterButtonActiveText}>{activeFilterLabel}</Text>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* Sort button */}
          {!isSelectionMode && (
            <TouchableOpacity
              style={styles.filterButton}
              onPress={handleToggleSortMenu}
              activeOpacity={0.7}
            >
              <Icon name="swap-vertical-outline" size={18} color={Colors.royalBlue} />
            </TouchableOpacity>
          )}

          {/* Radar button — только на вишлисте, пульсирует, ведёт на экран радара */}
          {!isSelectionMode && activeTab === 'wishlist' && (
            <View style={styles.radarBtnWrap}>
              {[radarPulse, radarPulse2].map((v, i) => (
                <Animated.View
                  key={i}
                  pointerEvents="none"
                  style={[
                    styles.radarPulseRing,
                    {
                      opacity: v.interpolate({ inputRange: [0, 0.15, 1], outputRange: [0, 0.55, 0] }),
                      transform: [{ scale: v.interpolate({ inputRange: [0, 1], outputRange: [1, 2.6] }) }],
                    },
                  ]}
                />
              ))}
              {/* Ореол, а не кольцо: sonar выше уже пульсирует, и вторая
                  пульсация слилась бы с ним — постоянную индикацию работы
                  радара юзер начал бы читать как незакрытый шаг онбординга. */}
              <CoachPulse active={radarSpotlight} variant="glow" radius={22} inset={4}>
                <TouchableOpacity style={styles.radarButton} onPress={() => router.push('/radar' as any)} activeOpacity={0.85}>
                  <RadarIcon size={20} color="#fff" variant="on" />
                </TouchableOpacity>
              </CoachPulse>
              {radarMatchCount > 0 && (
                <View style={styles.radarBadge}>
                  <Text style={styles.radarBadgeTxt}>{radarMatchCount}</Text>
                </View>
              )}
            </View>
          )}
        </View>

        {/* Filter dropdown */}
        <Animated.View
          style={{
            maxHeight: filterMenuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 300] }),
            opacity: filterMenuAnim,
            overflow: 'hidden',
          }}
          pointerEvents="box-none"
        >
          <View style={styles.filterDropdown}>
            {FORMAT_OPTIONS.map(option => (
              <TouchableOpacity
                key={option.key}
                style={[styles.filterOption, activeFilter === option.key && styles.filterOptionActive]}
                onPress={() => handleSelectFilter(option.key)}
              >
                <Text style={[styles.filterOptionText, activeFilter === option.key && styles.filterOptionTextActive]}>
                  {option.label}
                </Text>
                {activeFilter === option.key && (
                  <Icon name="checkmark" size={18} color={Colors.royalBlue} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </Animated.View>

        {/* Sort dropdown */}
        <Animated.View
          style={{
            maxHeight: sortMenuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 240] }),
            opacity: sortMenuAnim,
            overflow: 'hidden',
          }}
          pointerEvents="box-none"
        >
          <View style={styles.filterDropdown}>
            {SORT_OPTIONS.map(option => (
              <TouchableOpacity
                key={option.key}
                style={[styles.filterOption, activeSort === option.key && styles.filterOptionActive]}
                onPress={() => handleSelectSort(option.key)}
              >
                <Text style={[styles.filterOptionText, activeSort === option.key && styles.filterOptionTextActive]}>
                  {option.label}
                </Text>
                {activeSort === option.key && (
                  <Icon name="checkmark" size={18} color={Colors.royalBlue} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </Animated.View>
      </View>

      <View style={styles.recordGridContainer}>
      {pinchTip.visible && <PinchHint onDismiss={pinchTip.dismiss} />}
      {viewMode === 'grid' && data.length > 0 ? (
        <ZoomableRecordGrid
          data={data as (CollectionItem | WishlistItem)[]}
          onRecordPress={isSelectionMode ? undefined : handleRecordPress}
          onLongPress={handleLongPressItem}
          isSelectionMode={isSelectionMode}
          selectedItems={selectedItems}
          onToggleItemSelection={handleToggleItemSelection}
          isRefreshing={isRefreshing}
          onRefresh={handleRefresh}
          onEndReached={activeTab === 'collection' && collectionHasMore && !isLoadingMore ? loadMoreCollectionItems : undefined}
          isLoadingMore={isLoadingMore}
          ListHeaderComponent={ScrollableHeader}
          rarityContext={activeTab === 'wishlist' ? 'wishlist' : 'collection'}
          hotStockMap={activeTab === 'wishlist' ? hotStockMap : undefined}
          useOfferBadge={activeTab === 'wishlist'}
          radarRecordIds={activeTab === 'wishlist' ? radarRecordIds : undefined}
        />
      ) : (
        <RecordGrid
          key={viewMode}
          data={data}
          cardVariant={viewMode === 'list' ? 'list' : 'expanded'}
          numColumns={viewMode === 'list' ? 1 : 2}
          rarityContext={activeTab === 'wishlist' ? 'wishlist' : 'collection'}
          hotStockMap={activeTab === 'wishlist' ? hotStockMap : undefined}
          useOfferBadge={activeTab === 'wishlist'}
          radarRecordIds={activeTab === 'wishlist' ? radarRecordIds : undefined}
          // Swipe-to-offers только в list-mode вишлиста: в grid-mode карточки
          // компактные и swipe конфликтовал бы с горизонтальным скроллом
          // ZoomableRecordGrid'а.
          rowWrapper={
            activeTab === 'wishlist' && viewMode === 'list' && !isSelectionMode
              ? (item, child) => {
                  const wi = item as WishlistItem;
                  const discogsId = wi.record?.discogs_id;
                  const summary = discogsId ? summaryMap.get(discogsId) : null;
                  const hasOffers = !!summary && summary.in_stock_count > 0;
                  return (
                    <WishlistListSwipe
                      hasOffers={hasOffers}
                      minPriceRub={summary?.min_price_rub != null ? Number(summary.min_price_rub) : null}
                      storesCount={summary?.stores_with_stock ?? 0}
                      onOpen={() => handleWishlistSwipeOpen(wi)}
                    >
                      {child}
                    </WishlistListSwipe>
                  );
                }
              : undefined
          }
          onRecordPress={isSelectionMode ? undefined : handleRecordPress}
          onArtistPress={isSelectionMode ? undefined : handleArtistPress}
          onRemove={
            (activeTab === 'collection' ? handleRemoveFromCollection : handleRemoveFromWishlist) as any
          }
          showActions={false}
          isLoading={isLoading}
          isRefreshing={isRefreshing}
          onRefresh={handleRefresh}
          onEndReached={activeTab === 'collection' && collectionHasMore && !isLoadingMore ? loadMoreCollectionItems : undefined}
          emptyTitle={
            activeTab === 'collection'
              ? 'Здесь будут твои пластинки'
              : 'Здесь будет вишлист'
          }
          emptyIcon={activeTab === 'collection' ? 'disc-outline' : 'heart-outline'}
          emptyMessage={
            activeTab === 'collection'
              ? 'Сканируй штрихкод или находи через поиск — пластинки приземлятся сюда'
              : 'Добавляй пластинки, которые хочешь приобрести — друзья смогут забронировать их в подарок'
          }
          emptyActions={
            activeTab === 'collection'
              ? [
                  { label: 'Сканировать', icon: 'scan-outline', onPress: () => router.push('/(tabs)') },
                  { label: 'Найти', icon: 'search-outline', onPress: () => router.push('/(tabs)/search') },
                ]
              : [
                  { label: 'Найти пластинку', icon: 'search-outline', onPress: () => router.push('/(tabs)/search') },
                ]
          }
          ListHeaderComponent={ScrollableHeader}
          isSelectionMode={isSelectionMode}
          selectedItems={selectedItems}
          onToggleItemSelection={handleToggleItemSelection}
          onLongPressItem={handleLongPressItem}
        />
      )}
      </View>

      {/* Нижний подвал в режиме выбора */}
      {isSelectionMode && (
        <View style={styles.selectionFooter}>
          {activeTab === 'wishlist' && (
            <TouchableOpacity
              style={styles.footerButton}
              onPress={handleBulkMoveToCollection}
              disabled={selectedItems.size === 0}
            >
              <Icon
                name="arrow-forward-circle"
                size={24}
                color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
              />
              <Text
                style={[
                  styles.footerButtonText,
                  selectedItems.size === 0 && styles.footerButtonTextDisabled,
                ]}
              >
                В коллекцию {selectedItems.size > 0 && `(${selectedItems.size})`}
              </Text>
            </TouchableOpacity>
          )}

          {activeTab === 'wishlist' && (
            <TouchableOpacity
              style={styles.footerButton}
              onPress={() => setShowWishlistFolderPicker(true)}
              disabled={selectedItems.size === 0}
            >
              <Icon
                name="folder-outline"
                size={24}
                color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
              />
              <Text
                style={[
                  styles.footerButtonText,
                  selectedItems.size === 0 && styles.footerButtonTextDisabled,
                ]}
              >
                В папку {selectedItems.size > 0 && `(${selectedItems.size})`}
              </Text>
            </TouchableOpacity>
          )}

          {activeTab === 'collection' && (
            <TouchableOpacity
              style={styles.footerButton}
              onPress={() => setShowFolderPicker(true)}
              disabled={selectedItems.size === 0}
            >
              <Icon
                name="folder-outline"
                size={24}
                color={selectedItems.size > 0 ? Colors.royalBlue : Colors.textMuted}
              />
              <Text
                style={[
                  styles.footerButtonText,
                  selectedItems.size === 0 && styles.footerButtonTextDisabled,
                ]}
              >
                В папку {selectedItems.size > 0 && `(${selectedItems.size})`}
              </Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[styles.footerButton, styles.footerButtonDelete]}
            onPress={handleBulkDelete}
            disabled={selectedItems.size === 0}
          >
            <Icon
              name="trash-outline"
              size={24}
              color={selectedItems.size > 0 ? Colors.error : Colors.textMuted}
            />
            <Text
              style={[
                styles.footerButtonText,
                selectedItems.size === 0 && styles.footerButtonTextDisabled,
              ]}
            >
              Удалить {selectedItems.size > 0 && `(${selectedItems.size})`}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      <FolderPickerModal
        visible={showFolderPicker}
        onClose={() => setShowFolderPicker(false)}
        onSelectFolder={handleAddToFolder}
        selectedRecordIds={collectionItems
          .filter(item => selectedItems.has(item.id))
          .map(item => item.record_id)}
      />

      <WishlistFolderPickerModal
        visible={showWishlistFolderPicker}
        onClose={() => setShowWishlistFolderPicker(false)}
        onSelectFolder={handleAddToWishlistFolder}
        selectedWishlistItemIds={wishlistItems
          .filter(item => selectedItems.has(item.id))
          .map(item => item.id)}
      />

      {/* OffersBottomSheet — открывается при свайпе влево в вишлист-list-mode.
          Не разворачиваем preemptively (BottomSheetModal лениво монтирует).
          MARKET_AND_PRICE_DRAWER.md §2.3. */}
      <OffersBottomSheet
        ref={offersSheetRef}
        onBuyPress={handleBuyPress}
        onCardPress={(offer) => {
          // Тап на корпус карточки — переход к детальной этого pressing'а.
          // Для alt-version это другой discogs_id (другой пресс того же мастера).
          const dst = (offer as OfferDetailData & { recordDiscogsId?: string | null }).recordDiscogsId;
          if (dst) {
            offersSheetRef.current?.dismiss();
            router.push(`/record/${dst}`);
          }
        }}
        buyingListingId={buyingListingId}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  recordGridContainer: {
    flex: 1,
  },
  stickyToolbar: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.sm,
    backgroundColor: Colors.background,
    zIndex: 1,
  },
  headerContainer: {
    paddingBottom: Spacing.sm,
  },
  avatarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: Spacing.sm,
  },
  toolbarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  segmentContainer: {
    paddingBottom: Spacing.sm,
  },

  // View toggle (grid/list)
  viewToggleButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIconContainer: {
    width: 18,
    height: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIcon: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  viewToggleIconAbsolute: {
    position: 'absolute',
  },

  // Value button
  valueButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
  },

  // Filter button
  filterButton: {
    height: 36,
    paddingHorizontal: 10,
    borderRadius: 18,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 4,
  },
  filterButtonActive: {
    backgroundColor: Colors.royalBlue,
  },
  radarBtnWrap: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radarPulseRing: {
    position: 'absolute',
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1.5,
    borderColor: Colors.royalBlue,
  },
  radarButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radarBadge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: 16,
    height: 16,
    paddingHorizontal: 4,
    borderRadius: 8,
    backgroundColor: Colors.success,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: Colors.background,
  },
  radarBadgeTxt: {
    fontSize: 10,
    fontWeight: '800',
    color: '#fff',
  },
  filterButtonActiveText: {
    ...Typography.caption,
    color: Colors.background,
    fontFamily: 'Inter_600SemiBold',
  },

  filterOverlayInHeader: {
    // пустой враппер — нужен только для перехвата тапа мимо dropdown
  },
  filterDropdown: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.md,
    padding: Spacing.xs,
    ...Shadows.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  filterOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.sm,
  },
  filterOptionActive: {
    backgroundColor: Colors.surface,
  },
  filterOptionText: {
    ...Typography.bodySmall,
    color: Colors.text,
  },
  filterOptionTextActive: {
    color: Colors.royalBlue,
    fontFamily: 'Inter_600SemiBold',
  },

  // Gradient border "Выбрать" button
  selectButtonGradientBorder: {
    borderRadius: 20,
    padding: 1.5,
  },
  selectButtonInner: {
    backgroundColor: Colors.background,
    borderRadius: 18.5,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
  },
  selectButtonText: {
    ...Typography.buttonSmall,
    fontFamily: 'Inter_600SemiBold',
  },

  // Cancel button
  cancelButton: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs + 2,
    borderRadius: 20,
    backgroundColor: Colors.surface,
  },
  cancelButtonText: {
    ...Typography.buttonSmall,
    color: Colors.textSecondary,
  },

  headerButtonWrapper: {
    alignItems: 'flex-start',
    justifyContent: 'center',
    minHeight: 36,
  },
  headerButtonAbsolute: {
    position: 'absolute',
    right: 0,
  },

  selectionFooter: {
    position: 'absolute',
    bottom: 96, // above floating tab bar (bottom:28 + height:60 + gap:8)
    left: 16,
    right: 16,
    flexDirection: 'row',
    backgroundColor: Colors.glassBg,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.md,
    paddingHorizontal: Spacing.md,
    gap: Spacing.md,
    borderRadius: BorderRadius.md,
  },
  footerButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.md,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  footerButtonDelete: {
    backgroundColor: Colors.surface,
  },
  footerButtonText: {
    ...Typography.buttonSmall,
    color: Colors.royalBlue,
  },
  footerButtonTextDisabled: {
    color: Colors.textMuted,
  },

  // Folders section
  foldersSection: {
    marginBottom: Spacing.sm,
  },
  foldersSectionTitle: {
    ...Typography.h4,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  foldersScroll: {
    gap: Spacing.sm,
  },
  folderCard: {
    width: 100,
    alignItems: 'center' as const,
    gap: Spacing.xs,
  },
  newFolderCard: {
    width: 100,
    alignItems: 'center' as const,
    gap: Spacing.xs,
  },
  newFolderIcon: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    justifyContent: 'center' as const,
    alignItems: 'center' as const,
  },
  newFolderText: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontFamily: 'Inter_600SemiBold',
  },
  folderImage: {
    width: 80,
    height: 80,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
  },
  folderName: {
    ...Typography.caption,
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
    textAlign: 'center' as const,
  },
  folderCount: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontSize: ms(11),
  },
  createFirstFolder: {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: Spacing.sm,
    paddingVertical: Spacing.sm,
    marginBottom: Spacing.sm,
  },
  createFirstFolderText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
});
