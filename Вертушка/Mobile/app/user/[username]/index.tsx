/**
 * Профиль другого пользователя — внутриприложный вид.
 *
 * Логика:
 * - Сверху шапка: аватар + @username + custom_title + bio + ачивки + стоимость коллекции
 * - Ниже — как личная вкладка коллекции: segmented «В наличии / Вишлист», формат-фильтры, grid/list
 * - Бронь подарка из вишлиста доступна только если ты подписан (is_following === true).
 * - В модалке брони имя/email берутся из учётки автоматически — спрашиваем только сообщение.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
  TextInput,
  RefreshControl,
  Keyboard,
  TouchableWithoutFeedback,
  KeyboardAvoidingView,
  Platform,
  Animated,
  Easing,
  Pressable,
  Dimensions,
  Share,
  ActionSheetIOS,
  Alert,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  useSharedValue,
  withTiming,
  withDelay,
  useDerivedValue,
  runOnJS,
  Easing as REasing,
} from 'react-native-reanimated';
import { api, resolveMediaUrl } from '../../../lib/api';
import { useAuthStore, useFollowStore } from '../../../lib/store';
import { useMessagesStore } from '../../../lib/messagesStore';
import { ms } from '../../../lib/responsive';
import {
  PublicProfile,
  PublicProfileRecord,
  WishlistPublicItem,
  WishlistPublicResponse,
} from '../../../lib/types';
import { toast } from '../../../lib/toast';
import { cleanArtistName } from '../../../lib/format';
import { AchievementsBlock } from '../../../components/AchievementsBlock';
import { ArchetypeChip } from '../../../components/ArchetypeChip';
import { RecordCard } from '../../../components/RecordCard';
import { SegmentedControl } from '../../../components/ui';
import { ZoomableRecordGrid } from '../../../components/ZoomableRecordGrid';
import { CollectionItem, WishlistItem, VinylRecord, Collection } from '../../../lib/types';

type ProfileTab = 'collection' | 'wishlist';
type ViewMode = 'grid' | 'list';
type FormatFilter = 'all' | 'vinyl' | 'cd' | 'cassette' | 'box_set';
type SortMode = 'added_desc' | 'added_asc' | 'title';

const FORMAT_OPTIONS: { id: FormatFilter; label: string; match: string[] }[] = [
  { id: 'all', label: 'Все форматы', match: [] },
  { id: 'vinyl', label: 'Винил', match: ['vinyl', 'lp', '12"', '10"', '7"', 'album'] },
  { id: 'cd', label: 'CD', match: ['cd'] },
  { id: 'cassette', label: 'Кассета', match: ['cassette'] },
  { id: 'box_set', label: 'Бокс-сет', match: ['box set', 'box-set', 'boxset'] },
];

const SORT_OPTIONS: { id: SortMode; label: string }[] = [
  { id: 'added_desc', label: 'Новые → старые' },
  { id: 'added_asc', label: 'Старые → новые' },
  { id: 'title', label: 'По названию' },
];

const PP = {
  ivory: '#F4EEE6',
  ivorySoft: '#F0EBE2',
  ivoryDeep: '#ECE6DC',
  pearl: '#F7F4EE',
  cobalt: '#3A4BE0',
  cobaltBright: '#4E5BFF',
  periwinkle: '#9AA8FF',
  lavender: '#C9B8FF',
  blush: '#F6C7D0',
  sky: '#BDD4FF',
  ink: '#1B1D26',
  slate: '#6B7080',
  mute: '#9096A6',
  hairline: 'rgba(27,29,38,0.08)',
  whiteSoft: 'rgba(255,255,255,0.6)',
};

const SCREEN_W = Dimensions.get('window').width;
const GRID_GAP = 12;
const GRID_PADDING = 20;
const GRID_COLS = 3;
const CARD_W = Math.floor((SCREEN_W - GRID_PADDING * 2 - GRID_GAP * (GRID_COLS - 1)) / GRID_COLS);

function formatRub(value: number) {
  return Math.round(value).toLocaleString('ru-RU').replace(/,/g, ' ');
}

// Русская плюрализация: [1, 2-4, 5+] → одна / две / пять
function pluralRu(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n) % 100;
  const n1 = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}

/**
 * Хук плавного бегущего счётчика — порт логики из /collection/value.
 * Возвращает текущий display-string. Анимация на UI-thread через reanimated.
 */
function useAnimatedCount(target: number): string {
  const progress = useSharedValue(0);
  const [display, setDisplay] = useState('0');

  useEffect(() => {
    progress.value = 0;
    progress.value = withDelay(
      120,
      withTiming(1, { duration: 1400, easing: REasing.out(REasing.cubic) }),
    );
  }, [target, progress]);

  useDerivedValue(() => {
    const v = Math.round(progress.value * target);
    runOnJS(setDisplay)(v.toLocaleString('ru-RU').replace(/,/g, ' '));
  });

  return display;
}

/**
 * Адаптер: `PublicProfileRecord` → CollectionItem-shape для ZoomableRecordGrid.
 * Карточка использует только поля из record (year/title/artist/cover/rarity flags) —
 * остальное (collection_id, condition и т.д.) для отображения не нужно.
 */
function toZoomItem(r: PublicProfileRecord): CollectionItem {
  return {
    id: r.id,
    collection_id: 'public',
    record_id: r.id,
    record: r as unknown as VinylRecord,
    added_at: r.added_at || new Date().toISOString(),
  };
}

/**
 * Карточка стоимости коллекции — большой плавный счётчик + delta-pill за месяц.
 */
function ValueCard({
  valueRub,
  monthlyDelta,
}: {
  valueRub: number;
  monthlyDelta: number | null | undefined;
}) {
  const display = useAnimatedCount(valueRub);
  return (
    <View style={styles.valueCard}>
      <Text style={styles.valueLabel}>Стоимость коллекции</Text>
      <Text style={styles.valueAmount}>
        {display} <Text style={styles.valueCurrency}>₽</Text>
      </Text>
      {monthlyDelta != null ? (
        <View style={styles.deltaPill}>
          <Icon
            name={monthlyDelta >= 0 ? 'arrow-up' : 'arrow-down'}
            size={11}
            color={PP.cobalt}
          />
          <Text style={styles.deltaText}>
            {monthlyDelta >= 0 ? '+' : ''}{formatRub(monthlyDelta)} ₽ за месяц
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function priceLabel(record: PublicProfileRecord): string | null {
  if (!record.estimated_price_median) return null;
  return `~$${Math.round(record.estimated_price_median)}`;
}

/* ---------------- VIEW TOGGLE + FORMAT FILTER ---------------- */
function ViewToggle({ value, onChange }: { value: ViewMode; onChange: (v: ViewMode) => void }) {
  return (
    <View style={styles.viewToggle}>
      {(['grid', 'list'] as ViewMode[]).map((m) => {
        const active = m === value;
        return (
          <TouchableOpacity
            key={m}
            onPress={() => onChange(m)}
            style={[styles.viewToggleBtn, active && styles.viewToggleBtnActive]}
          >
            <Icon
              name={m === 'grid' ? 'grid-outline' : 'list-outline'}
              size={15}
              color={active ? PP.cobalt : PP.mute}
            />
          </TouchableOpacity>
        );
      })}
    </View>
  );
}



/* ---------------- SCREEN ---------------- */
export default function UserProfileScreen() {
  const { username } = useLocalSearchParams<{ username: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user: currentUser } = useAuthStore();
  const { followUser, unfollowUser, cancelFollowRequest } = useFollowStore();

  const [pubProfile, setPubProfile] = useState<PublicProfile | null>(null);
  const [wishlist, setWishlist] = useState<WishlistPublicResponse | null>(null);
  const [following, setFollowing] = useState(false);
  const [requestPending, setRequestPending] = useState(false);
  const [isPrivateProfile, setIsPrivateProfile] = useState(false);
  const [, setFollowersCount] = useState(0);
  const [profileUserId, setProfileUserId] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<ProfileTab>('collection');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [formatFilter, setFormatFilter] = useState<FormatFilter>('all');
  const [sortMode, setSortMode] = useState<SortMode>('added_desc');
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [showSortMenu, setShowSortMenu] = useState(false);
  const filterMenuAnim = useRef(new Animated.Value(0)).current;
  const sortMenuAnim = useRef(new Animated.Value(0)).current;
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isFollowLoading, setIsFollowLoading] = useState(false);

  const [bookingItem, setBookingItem] = useState<WishlistPublicItem | null>(null);
  const [bookingMessage, setBookingMessage] = useState('');
  const [isBooking, setIsBooking] = useState(false);

  // Папки чужого юзера — публичный список через api.getUserCollection
  const [folders, setFolders] = useState<Collection[]>([]);

  const isOwn = currentUser?.username === username;

  const load = useCallback(async () => {
    if (!username) {
      // Без username страница смысла не имеет — не оставляем вечный спиннер.
      setIsLoading(false);
      return;
    }
    try {
      // Оба запроса терпимы к ошибке: публичный профиль — opt-in и может быть
      // не активирован (404), но базовый профиль через getUserByUsername есть
      // у любого активного пользователя. Не роняем экран из-за 404 share.
      const [pub, userMeta] = await Promise.all([
        api.getPublicProfile(username).catch(() => null),
        api.getUserByUsername(username).catch(() => null),
      ]);

      if (!pub && !userMeta) {
        toast.error('Профиль не найден');
        router.back();
        return;
      }

      // Публичный профиль активирован — берём его. Иначе синтезируем
      // минимальный профиль из метаданных пользователя (вариант A: graceful
      // degrade), чтобы можно было открыть карточку, подписаться и написать.
      setPubProfile(
        pub ??
          (userMeta
            ? {
                username: userMeta.username,
                display_name: userMeta.display_name,
                avatar_url: userMeta.avatar_url,
                bio: userMeta.bio,
                collection_count: userMeta.collection_count,
                wishlist_count: 0,
                followers_count: userMeta.followers_count,
                show_collection: false,
                show_wishlist: false,
                show_record_year: true,
                show_record_label: true,
                show_record_format: true,
                show_record_prices: false,
                highlights: [],
                collection: [],
                recent_additions: [],
                new_releases: [],
              }
            : null),
      );
      if (userMeta) {
        setProfileUserId(userMeta.id);
        setFollowing(userMeta.is_following);
        setFollowersCount(userMeta.followers_count);
        setRequestPending(userMeta.follow_request_status === 'pending');
        setIsPrivateProfile(!!userMeta.is_private_profile);

        // Параллельно подтянуть папки (свой эндпоинт — getUserCollection возвращает массив папок)
        api
          .getUserCollection(userMeta.id, 1, 1)
          .then((res) => {
            // Берём только метаданные папок — items не нужны на главном экране
            setFolders(
              res.map((c) => ({
                id: c.id,
                user_id: c.user_id,
                name: c.name,
                description: c.description,
                sort_order: c.sort_order,
                items_count: c.items_count,
                created_at: c.created_at,
                updated_at: c.updated_at,
              })),
            );
          })
          .catch(() => setFolders([]));
      }
    } catch {
      toast.error('Профиль не найден');
      router.back();
    } finally {
      setIsLoading(false);
    }
  }, [username, router]);

  const loadWishlist = useCallback(async () => {
    if (!username) return;
    try {
      const data = await api.getUserWishlistByUsername(username);
      setWishlist(data);
    } catch {
      setWishlist(null);
    }
  }, [username]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (pubProfile && activeTab === 'wishlist' && !wishlist) loadWishlist();
  }, [pubProfile, activeTab, wishlist, loadWishlist]);

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await load();
    if (activeTab === 'wishlist') await loadWishlist();
    setIsRefreshing(false);
  }, [load, loadWishlist, activeTab]);

  const handleFollow = useCallback(async () => {
    if (!profileUserId) return;
    setIsFollowLoading(true);
    try {
      if (following) {
        // Отписаться
        await unfollowUser(profileUserId);
        setFollowing(false);
        setFollowersCount((c) => Math.max(0, c - 1));
        return;
      }
      if (requestPending) {
        // Отменить запрос
        await cancelFollowRequest(profileUserId);
        setRequestPending(false);
        toast.success('Запрос отменён');
        return;
      }
      // Подписаться / отправить запрос
      const result = await followUser(profileUserId);
      if (result.status === 'followed' || result.status === 'already_following') {
        setFollowing(true);
        setFollowersCount((c) => c + 1);
      } else if (result.status === 'requested' || result.status === 'already_requested') {
        setRequestPending(true);
        toast.success('Запрос отправлен', 'Ждём подтверждения от пользователя');
      }
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось');
    } finally {
      setIsFollowLoading(false);
    }
  }, [profileUserId, following, requestPending, followUser, unfollowUser, cancelFollowRequest]);

  /**
   * Меню действий по кнопке «Вы подписаны ⋯» — пока единственный пункт «Отписаться».
   * iOS — ActionSheetIOS, Android — Alert.
   */
  const handleFollowMenu = useCallback(() => {
    if (!profileUserId) return;
    const doUnfollow = async () => {
      setIsFollowLoading(true);
      try {
        await unfollowUser(profileUserId);
        setFollowing(false);
        setFollowersCount((c) => Math.max(0, c - 1));
      } catch (error: any) {
        toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось');
      } finally {
        setIsFollowLoading(false);
      }
    };

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          title: `@${pubProfile?.username ?? ''}`,
          options: ['Отписаться', 'Отмена'],
          cancelButtonIndex: 1,
          destructiveButtonIndex: 0,
          userInterfaceStyle: 'light',
        },
        (idx) => {
          if (idx === 0) doUnfollow();
        },
      );
    } else {
      Alert.alert(
        `@${pubProfile?.username ?? ''}`,
        undefined,
        [
          { text: 'Отписаться', style: 'destructive', onPress: doUnfollow },
          { text: 'Отмена', style: 'cancel' },
        ],
      );
    }
  }, [profileUserId, unfollowUser, pubProfile?.username]);

  /**
   * Кнопка «Написать» — открывает/создаёт диалог с пользователем и переходит в тред.
   * Если у получателя приватный профиль и нет взаимной подписки — бекенд вернёт 403,
   * показываем понятный toast.
   */
  const handleMessage = useCallback(async () => {
    if (!profileUserId) return;
    if (!currentUser) {
      router.push('/(auth)/register');
      return;
    }
    try {
      const conv = await useMessagesStore.getState().openOrCreate(profileUserId);
      router.push(`/messages/${conv.id}` as any);
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось открыть чат');
    }
  }, [profileUserId, currentUser, router]);

  const handleShare = useCallback(async () => {
    try {
      await Share.share({ message: `https://vinyl-vertushka.ru/@${username}` });
    } catch {}
  }, [username]);

  // Возвращает true, если действие выполнено (modal открыт / редирект на auth / показан toast).
  // false — caller должен сам выбрать fallback (например, открыть детальную карточки).
  const tryOpenBooking = useCallback(
    (item: WishlistPublicItem | null, reserved: boolean): boolean => {
      if (!item || reserved || isOwn) return false;
      if (!currentUser) {
        router.push('/(auth)/register');
        return true;
      }
      if (!following) {
        toast.info('Подпишитесь', 'Бронь подарков доступна подписчикам');
        return true;
      }
      setBookingItem(item);
      return true;
    },
    [currentUser, following, isOwn, router]
  );

  const isBookingRef = useRef(false);
  const handleBookGift = useCallback(async () => {
    if (!bookingItem || !currentUser) return;
    if (isBookingRef.current) return;
    isBookingRef.current = true;
    setIsBooking(true);
    try {
      const gifterName = (currentUser.display_name?.trim() || currentUser.username || '').trim();
      const gifterEmail = (currentUser.email || '').trim();
      if (!gifterName || !gifterEmail) {
        toast.error('Не удалось забронировать', 'Заполните имя и email в своём профиле');
        return;
      }
      await api.bookGift({
        wishlist_item_id: bookingItem.id,
        gifter_name: gifterName,
        gifter_email: gifterEmail,
        gifter_message: bookingMessage.trim() || undefined,
      });
      toast.success('Готово!', 'Бронь на 60 дней. Подтверждение отправлено на email.');
      setBookingItem(null);
      setBookingMessage('');
      await loadWishlist();
    } catch (error: any) {
      toast.error('Ошибка', error?.response?.data?.detail || 'Не удалось забронировать');
    } finally {
      setIsBooking(false);
      isBookingRef.current = false;
    }
  }, [bookingItem, bookingMessage, currentUser, loadWishlist]);

  const collectionValueRub = pubProfile?.collection_value_rub;
  const monthlyDelta = pubProfile?.monthly_value_delta_rub;

  const wishlistItems = wishlist?.items || [];

  const baseCollection: PublicProfileRecord[] = pubProfile?.collection ?? [];
  // Прокидываем added_at у элемента вишлиста в record, чтобы сортировка работала единообразно
  const baseWishlist: PublicProfileRecord[] = wishlistItems.map((it) => ({
    ...it.record,
    is_booked: it.is_booked,
    added_at: it.added_at ?? it.record.added_at ?? null,
  }));

  const applyFilter = useCallback(
    (records: PublicProfileRecord[]) => {
      if (formatFilter === 'all') return records;
      const opt = FORMAT_OPTIONS.find((o) => o.id === formatFilter);
      if (!opt) return records;
      return records.filter((r) => {
        if (!r.format_type) return false;
        const f = r.format_type.toLowerCase();
        return opt.match.some((token) => f.includes(token));
      });
    },
    [formatFilter]
  );

  const applySort = useCallback(
    (records: PublicProfileRecord[]) => {
      const arr = [...records];
      const ts = (s?: string | null) => (s ? Date.parse(s) : 0);
      if (sortMode === 'added_desc') {
        arr.sort((a, b) => ts(b.added_at) - ts(a.added_at));
      } else if (sortMode === 'added_asc') {
        arr.sort((a, b) => {
          const av = a.added_at ? ts(a.added_at) : Number.POSITIVE_INFINITY;
          const bv = b.added_at ? ts(b.added_at) : Number.POSITIVE_INFINITY;
          return av - bv;
        });
      } else if (sortMode === 'title') {
        arr.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'ru'));
      }
      return arr;
    },
    [sortMode]
  );

  const gridData = useMemo(
    () => applySort(applyFilter(activeTab === 'collection' ? baseCollection : baseWishlist)),
    [applyFilter, applySort, activeTab, baseCollection, baseWishlist]
  );

  // ---- dropdown menu toggles (filter / sort) — два эксклюзивных меню
  const animateMenu = useCallback((anim: Animated.Value, open: boolean) => {
    Animated.timing(anim, {
      toValue: open ? 1 : 0,
      duration: 220,
      easing: Easing.bezier(0.22, 0.7, 0.18, 1),
      useNativeDriver: false,
    }).start();
  }, []);

  const handleToggleFilterMenu = useCallback(() => {
    const next = !showFilterMenu;
    setShowFilterMenu(next);
    animateMenu(filterMenuAnim, next);
    if (next && showSortMenu) {
      setShowSortMenu(false);
      animateMenu(sortMenuAnim, false);
    }
  }, [showFilterMenu, showSortMenu, animateMenu, filterMenuAnim, sortMenuAnim]);

  const handleToggleSortMenu = useCallback(() => {
    const next = !showSortMenu;
    setShowSortMenu(next);
    animateMenu(sortMenuAnim, next);
    if (next && showFilterMenu) {
      setShowFilterMenu(false);
      animateMenu(filterMenuAnim, false);
    }
  }, [showSortMenu, showFilterMenu, animateMenu, sortMenuAnim, filterMenuAnim]);

  const handleSelectFilter = useCallback(
    (id: FormatFilter) => {
      setFormatFilter(id);
      setShowFilterMenu(false);
      animateMenu(filterMenuAnim, false);
    },
    [animateMenu, filterMenuAnim]
  );

  const handleSelectSort = useCallback(
    (id: SortMode) => {
      setSortMode(id);
      setShowSortMenu(false);
      animateMenu(sortMenuAnim, false);
    },
    [animateMenu, sortMenuAnim]
  );

  const activeFormatLabel = FORMAT_OPTIONS.find((o) => o.id === formatFilter)?.label || 'Все форматы';

  // ВАЖНО: все хуки (useCallback/useMemo/etc.) объявляются ДО любых early-return,
  // иначе React падает с "Rendered more hooks than during the previous render"
  // когда профиль грузится (первый рендер — без хуков ниже, второй — с ними).
  const isWishlistTab = activeTab === 'wishlist';

  const handleCardPress = useCallback(
    (r: PublicProfileRecord) => {
      if (isWishlistTab && !isOwn) {
        // Match по record.id + fallback по discogs_id — защита от ID-дрейфа,
        // когда одна и та же пластинка попала к двум юзерам разными путями.
        const item =
          wishlistItems.find(
            (w) =>
              w.record.id === r.id ||
              (!!w.record.discogs_id && w.record.discogs_id === r.discogs_id),
          ) ?? null;
        const reserved = !!r.is_booked;
        if (item && !reserved) {
          const handled = tryOpenBooking(item, reserved);
          if (handled) return;
        }
      }
      router.push(`/record/${r.id}`);
    },
    [isWishlistTab, wishlistItems, isOwn, tryOpenBooking, router],
  );

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={PP.cobalt} />
      </View>
    );
  }

  if (!pubProfile) return null;

  const initials = pubProfile.username.slice(0, 2).toLowerCase();

  const renderListOrEmpty = () => {
    if (gridData.length === 0) {
      return (
        <Text style={styles.empty}>
          {activeTab === 'collection' ? 'Коллекция пуста' : 'Вишлист пуст'}
        </Text>
      );
    }
    // List-режим — обычные карточки в одну колонку.
    return (
      <View style={styles.list}>
        {gridData.map((r, idx) => (
          <RecordCard
            key={r.id + idx}
            record={r}
            variant="list"
            isBooked={isWishlistTab && !!r.is_booked}
            rarityContext={isWishlistTab ? 'wishlist' : 'collection'}
            onPress={() => handleCardPress(r)}
          />
        ))}
      </View>
    );
  };

  const showStickyCTA = !currentUser;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Soft tinted background */}
      <View style={StyleSheet.absoluteFill}>
        <View style={[StyleSheet.absoluteFill, { backgroundColor: '#F5F0EA' }]} />
        <LinearGradient
          colors={['rgba(154,168,255,0.55)', 'rgba(154,168,255,0.12)', 'transparent']}
          start={{ x: 1, y: 0 }} end={{ x: 0.2, y: 0.6 }}
          style={StyleSheet.absoluteFill}
          pointerEvents="none"
        />
        <LinearGradient
          colors={['rgba(189,212,255,0.45)', 'rgba(189,212,255,0.08)', 'transparent']}
          start={{ x: 0, y: 0 }} end={{ x: 0.7, y: 0.5 }}
          style={StyleSheet.absoluteFill}
          pointerEvents="none"
        />
      </View>

      {/* Top bar — минимальный */}
      <View style={styles.topbar}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn}>
          <Icon name="chevron-back" size={22} color={PP.ink} />
        </TouchableOpacity>
        <View style={{ flex: 1 }} />
        <TouchableOpacity onPress={handleShare} style={styles.iconBtn}>
          <Icon name="share-outline" size={18} color={PP.ink} />
        </TouchableOpacity>
      </View>

      {/* В grid-режиме используем ZoomableRecordGrid (с pinch-зумом, как в коллекции),
          ListHeaderComponent = headerContent. В list-режиме и при пустом гриде — обычный ScrollView. */}
      {(() => {
        const headerContent = (
          <>
        {/* HERO — Instagram-style: крупный аватар слева + 3 столбца статов справа */}
        <View style={styles.hero}>
          <View style={styles.heroTop}>
            <View style={styles.avatarShadow}>
              <LinearGradient
                colors={[PP.blush, PP.lavender, PP.periwinkle, PP.sky]}
                style={styles.avatarRing}
              >
                <View style={styles.avatarInner}>
                  {pubProfile.avatar_url ? (
                    <Image
                      source={resolveMediaUrl(pubProfile.avatar_url)}
                      style={{ width: '100%', height: '100%', borderRadius: 60 }}
                      cachePolicy="disk"
                    />
                  ) : (
                    <Text style={styles.avatarInitials}>{initials}</Text>
                  )}
                </View>
              </LinearGradient>
            </View>
            <View style={styles.heroStatsRow}>
              <View style={styles.heroStatItem}>
                <Text style={styles.heroStatNum}>{pubProfile.collection_count}</Text>
                <Text style={styles.heroStatLbl} numberOfLines={1}>
                  в наличии
                </Text>
              </View>
              <View style={styles.heroStatItem}>
                <Text style={styles.heroStatNum}>{pubProfile.wishlist_count}</Text>
                <Text style={styles.heroStatLbl} numberOfLines={1}>
                  в вишлисте
                </Text>
              </View>
              <View style={styles.heroStatItem}>
                <Text style={styles.heroStatNum}>{pubProfile.followers_count}</Text>
                <Text style={styles.heroStatLbl} numberOfLines={1}>
                  подписчики
                </Text>
              </View>
            </View>
          </View>

          {/* Identity: @ник + имя + bio */}
          <View style={styles.identityBlock}>
            <Text style={styles.username} numberOfLines={1}>@{pubProfile.username}</Text>
            {pubProfile.display_name ? (
              <Text style={styles.displayName} numberOfLines={1}>{pubProfile.display_name}</Text>
            ) : null}
            <View style={{ marginTop: 6, alignItems: 'flex-start' }}>
              <ArchetypeChip username={pubProfile.username} />
            </View>
            {pubProfile.custom_title ? (
              <Text style={styles.customTitle} numberOfLines={2}>{pubProfile.custom_title}</Text>
            ) : null}
            {pubProfile.bio ? (
              <Text style={styles.bio} numberOfLines={3}>{pubProfile.bio}</Text>
            ) : null}
          </View>

          {/* Follow-блок: до подписки — одна кнопка; после — «Вы подписаны ⋯» + «Написать» */}
          {!isOwn && profileUserId ? (
            following ? (
              <View style={styles.followRow}>
                <TouchableOpacity
                  style={[styles.followBtn, styles.followBtnActive, styles.followBtnFlex]}
                  onPress={handleFollowMenu}
                  disabled={isFollowLoading}
                  activeOpacity={0.85}
                >
                  {isFollowLoading ? (
                    <ActivityIndicator size="small" color={PP.cobalt} />
                  ) : (
                    <>
                      <Icon name="checkmark" size={16} color={PP.cobalt} />
                      <Text style={[styles.followTxt, styles.followTxtActive]}>Вы подписаны</Text>
                      <Icon name="ellipsis-horizontal" size={16} color={PP.cobalt} />
                    </>
                  )}
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.followBtn, styles.messageBtn]}
                  onPress={handleMessage}
                  activeOpacity={0.85}
                >
                  <Icon name="chatbubble-outline" size={16} color={PP.cobalt} />
                  <Text style={[styles.followTxt, styles.followTxtActive]}>Написать</Text>
                </TouchableOpacity>
              </View>
            ) : (() => {
              const iconName = requestPending
                ? 'time-outline'
                : (isPrivateProfile ? 'lock-closed-outline' : 'person-add-outline');
              const label = requestPending
                ? 'Запрос отправлен'
                : (isPrivateProfile ? 'Запросить подписку' : 'Подписаться');
              const isAlt = requestPending;
              return (
                <TouchableOpacity
                  style={[styles.followBtn, isAlt && styles.followBtnActive]}
                  onPress={handleFollow}
                  disabled={isFollowLoading}
                >
                  {isFollowLoading ? (
                    <ActivityIndicator size="small" color={isAlt ? PP.cobalt : '#fff'} />
                  ) : (
                    <>
                      <Icon name={iconName as any} size={16} color={isAlt ? PP.cobalt : '#fff'} />
                      <Text style={[styles.followTxt, isAlt && styles.followTxtActive]}>
                        {label}
                      </Text>
                    </>
                  )}
                </TouchableOpacity>
              );
            })()
          ) : null}

          {/* Карточка стоимости коллекции — плавный счётчик */}
          {collectionValueRub != null ? (
            <ValueCard
              valueRub={collectionValueRub}
              monthlyDelta={monthlyDelta}
            />
          ) : null}
        </View>

        {/* Achievements */}
        <View style={styles.achievementsWrap}>
          <AchievementsBlock username={username} />
        </View>

        {/* Segmented + toolbar — стабильная позиция (НЕ зависит от активного таба).
            Раньше BookingHint/Folders рендерились выше и при переключении
            таба «прыгал» segment + toolbar. Теперь они ниже toolbar'а. */}
        <View style={styles.segmentedWrap}>
          <SegmentedControl
            segments={[
              { key: 'collection', label: 'В наличии' },
              { key: 'wishlist', label: 'Вишлист' },
            ]}
            selectedKey={activeTab}
            onSelect={setActiveTab}
          />
        </View>

        {/* Toolbar: format filter + sort + counter + view toggle.
            Counter заполняет середину — нет «дыры» между кнопками. */}
        <View style={styles.toolbar}>
          <TouchableOpacity
            activeOpacity={0.85}
            style={[styles.toolbarBtn, formatFilter !== 'all' && styles.toolbarBtnActive]}
            onPress={handleToggleFilterMenu}
          >
            <Icon
              name="options-outline"
              size={16}
              color={formatFilter !== 'all' ? '#fff' : PP.cobalt}
            />
            {formatFilter !== 'all' ? (
              <Text style={styles.toolbarBtnActiveTxt}>{activeFormatLabel}</Text>
            ) : null}
          </TouchableOpacity>

          <TouchableOpacity
            activeOpacity={0.85}
            style={styles.toolbarBtn}
            onPress={handleToggleSortMenu}
          >
            <Icon name="swap-vertical-outline" size={16} color={PP.cobalt} />
          </TouchableOpacity>

          <Text style={styles.toolbarCount} numberOfLines={1}>
            {gridData.length} {pluralRu(gridData.length, ['пластинка', 'пластинки', 'пластинок'])}
          </Text>
          <ViewToggle value={viewMode} onChange={setViewMode} />
        </View>

        {/* Filter dropdown */}
        <Animated.View
          pointerEvents={showFilterMenu ? 'auto' : 'none'}
          style={{
            opacity: filterMenuAnim,
            maxHeight: filterMenuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 320] }),
            overflow: 'hidden',
            paddingHorizontal: GRID_PADDING,
            marginTop: 8,
          }}
        >
          <View style={styles.dropdownCard}>
            {FORMAT_OPTIONS.map((o) => {
              const active = formatFilter === o.id;
              return (
                <TouchableOpacity
                  key={o.id}
                  style={[styles.dropdownItem, active && styles.dropdownItemActive]}
                  onPress={() => handleSelectFilter(o.id)}
                >
                  <Text style={[styles.dropdownItemTxt, active && styles.dropdownItemTxtActive]}>
                    {o.label}
                  </Text>
                  {active ? <Icon name="checkmark" size={16} color={PP.cobalt} /> : null}
                </TouchableOpacity>
              );
            })}
          </View>
        </Animated.View>

        {/* Sort dropdown */}
        <Animated.View
          pointerEvents={showSortMenu ? 'auto' : 'none'}
          style={{
            opacity: sortMenuAnim,
            maxHeight: sortMenuAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 240] }),
            overflow: 'hidden',
            paddingHorizontal: GRID_PADDING,
            marginTop: 8,
          }}
        >
          <View style={styles.dropdownCard}>
            {SORT_OPTIONS.map((o) => {
              const active = sortMode === o.id;
              return (
                <TouchableOpacity
                  key={o.id}
                  style={[styles.dropdownItem, active && styles.dropdownItemActive]}
                  onPress={() => handleSelectSort(o.id)}
                >
                  <Text style={[styles.dropdownItemTxt, active && styles.dropdownItemTxtActive]}>
                    {o.label}
                  </Text>
                  {active ? <Icon name="checkmark" size={16} color={PP.cobalt} /> : null}
                </TouchableOpacity>
              );
            })}
          </View>
        </Animated.View>

        {/* Booking hint — компактная одна строка вместо тяжёлой карточки.
            Под toolbar'ом, не сдвигает sticky-зону при переключении таба. */}
        {activeTab === 'wishlist' && !isOwn ? (
          <View style={styles.bookingHint}>
            <Text style={styles.bookingHintInline}>
              🔒 Анонимно  ·  🎁 60 дней  ·  ⏰ Напомним за 7
            </Text>
            {!following ? (
              <Text style={styles.bookingHintSub}>
                Подпишитесь, чтобы бронировать подарки
              </Text>
            ) : null}
          </View>
        ) : null}

        {/* Папки (только в режиме «В наличии»). Под toolbar'ом — не сдвигает
            sticky-зону при переключении таба. */}
        {activeTab === 'collection' && folders.length > 0 ? (
          <View style={styles.foldersSection}>
            <Text style={styles.foldersSectionTitle}>Папки</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.foldersScroll}
            >
              {folders.map((folder) => (
                <TouchableOpacity
                  key={folder.id}
                  activeOpacity={0.85}
                  style={styles.folderCard}
                  onPress={() =>
                    router.push({
                      pathname: '/folder/[id]',
                      params: { id: folder.id, ownerUsername: username ?? '' },
                    } as any)
                  }
                >
                  <View style={styles.folderImage}>
                    <Icon name="folder" size={28} color={PP.cobalt} />
                  </View>
                  <Text style={styles.folderName} numberOfLines={1}>{folder.name}</Text>
                  <Text style={styles.folderCount}>{folder.items_count} пл.</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        ) : null}

          </>
        );

        if (viewMode === 'grid' && gridData.length > 0) {
          return (
            <ZoomableRecordGrid
              data={gridData.map(toZoomItem)}
              ListHeaderComponent={headerContent}
              onRecordPress={(it) =>
                handleCardPress((it.record as unknown) as PublicProfileRecord)
              }
              isRefreshing={isRefreshing}
              onRefresh={handleRefresh}
              rarityContext={isWishlistTab ? 'wishlist' : 'collection'}
              contentBottomPad={showStickyCTA ? 140 : 32}
            />
          );
        }
        return (
          <ScrollView
            showsVerticalScrollIndicator={false}
            contentContainerStyle={{ paddingBottom: showStickyCTA ? 140 : 32 }}
            refreshControl={
              <RefreshControl
                refreshing={isRefreshing}
                onRefresh={handleRefresh}
                tintColor={PP.cobalt}
              />
            }
          >
            {headerContent}
            {renderListOrEmpty()}
          </ScrollView>
        );
      })()}

      {/* Sticky CTA — только для неавторизованных deep-link юзеров */}
      {showStickyCTA ? (
        <View pointerEvents="box-none" style={[styles.ctaWrap, { paddingBottom: insets.bottom + 12 }]}>
          <LinearGradient
            pointerEvents="none"
            colors={['rgba(244,238,230,0)', 'rgba(244,238,230,0.85)', 'rgba(244,238,230,1)']}
            style={styles.ctaFade}
          />
          <TouchableOpacity
            activeOpacity={0.9}
            style={styles.cta}
            onPress={() => router.push('/(auth)/register')}
          >
            <Icon name="add-circle-outline" size={18} color="#fff" />
            <Text style={styles.ctaTxt}>Создать свой профиль</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* Booking modal — без полей имени/email (берём из учётки) */}
      <Modal
        visible={!!bookingItem}
        transparent
        animationType="slide"
        onRequestClose={() => setBookingItem(null)}
      >
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <TouchableWithoutFeedback onPress={Keyboard.dismiss}>
            <View style={{ flex: 1 }} />
          </TouchableWithoutFeedback>
          <View style={[styles.modalContent, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.modalHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Забронировать как подарок</Text>
              <TouchableOpacity onPress={() => setBookingItem(null)}>
                <Icon name="close" size={22} color={PP.ink} />
              </TouchableOpacity>
            </View>
            {bookingItem ? (
              <View style={styles.modalRecRow}>
                <View style={styles.modalRecCover}>
                  {bookingItem.record.cover_image_url ? (
                    <Image
                      source={resolveMediaUrl(bookingItem.record.cover_image_url)}
                      style={{ width: 56, height: 56 }}
                      cachePolicy="disk"
                    />
                  ) : (
                    <LinearGradient
                      colors={[PP.lavender, PP.sky]}
                      style={{ width: 56, height: 56 }}
                    />
                  )}
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text numberOfLines={1} style={styles.cardArtist}>
                    {cleanArtistName(bookingItem.record.artist)}
                  </Text>
                  <Text numberOfLines={2} style={styles.modalRecTitle}>
                    {bookingItem.record.title}
                  </Text>
                </View>
              </View>
            ) : null}
            <Text style={styles.modalInfo}>
              Бронь анонимная — владелец увидит только метку «Забронировано». Срок 60 дней.
              За 7 дней до истечения мы напомним на email. Если подарок не вручён — бронь
              освободится автоматически.
            </Text>
            <TextInput
              style={[styles.input, styles.textarea]}
              placeholder="Сообщение владельцу (необязательно)"
              placeholderTextColor={PP.mute}
              value={bookingMessage}
              onChangeText={setBookingMessage}
              multiline
            />
            <TouchableOpacity
              style={[styles.confirmBtn, isBooking && { opacity: 0.55 }]}
              onPress={handleBookGift}
              disabled={isBooking}
            >
              {isBooking ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.confirmBtnTxt}>Подтвердить · бронь на 60 дней</Text>
              )}
            </TouchableOpacity>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: PP.ivory },
  center: { alignItems: 'center', justifyContent: 'center' },

  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: GRID_PADDING,
    paddingVertical: 8,
  },
  iconBtn: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: PP.whiteSoft,
    borderWidth: 1, borderColor: PP.hairline,
  },

  /* HERO — Instagram-style */
  hero: {
    paddingHorizontal: GRID_PADDING,
    paddingTop: 4,
    paddingBottom: 8,
  },
  heroTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 20,
  },
  avatarShadow: {
    shadowColor: PP.periwinkle,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.55,
    shadowRadius: 16,
    elevation: 10,
  },
  avatarRing: { width: 90, height: 90, borderRadius: 45, padding: 3 },
  avatarInner: {
    flex: 1, borderRadius: 60, backgroundColor: PP.pearl,
    alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  avatarInitials: { color: PP.cobalt, fontWeight: '600', fontSize: 22 },

  /* 3 столбца статов справа от аватара (как в Instagram) */
  heroStatsRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
  },
  heroStatItem: { alignItems: 'center', flex: 1 },
  heroStatNum: { fontSize: ms(18), fontWeight: '700', color: PP.ink, letterSpacing: -0.2 },
  heroStatLbl: { fontSize: ms(10.5), color: PP.mute, marginTop: 3, letterSpacing: 0.1, textAlign: 'center' },

  /* Identity (ник, имя, bio) под шапкой */
  identityBlock: {
    marginTop: 14,
  },
  username: { fontSize: ms(18), fontWeight: '700', color: PP.ink, letterSpacing: -0.3 },
  displayName: { fontSize: ms(14), color: PP.slate, marginTop: 2, fontWeight: '500' },
  customTitle: { fontSize: ms(12), color: PP.slate, marginTop: 6 },
  bio: { fontSize: ms(13), color: PP.ink, marginTop: 6, lineHeight: ms(18) },

  /* Follow buttons (одиночная и двойная пара) */
  followRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 14,
    marginBottom: 4,
  },
  followBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginTop: 14, marginBottom: 4,
    backgroundColor: PP.cobalt, borderRadius: 12, paddingVertical: 11,
    paddingHorizontal: 14,
  },
  followBtnFlex: { flex: 1, marginTop: 0, marginBottom: 0 },
  followBtnActive: {
    backgroundColor: PP.whiteSoft, borderWidth: 1, borderColor: 'rgba(58,75,224,0.25)',
  },
  messageBtn: {
    backgroundColor: PP.whiteSoft,
    borderWidth: 1, borderColor: 'rgba(58,75,224,0.25)',
    marginTop: 0, marginBottom: 0,
  },
  followTxt: { color: '#fff', fontWeight: '600', fontSize: ms(14) },
  followTxtActive: { color: PP.cobalt },

  /* Карточка стоимости коллекции */
  valueCard: {
    marginTop: 16,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: 18,
    borderWidth: 1, borderColor: PP.hairline,
    paddingHorizontal: 18, paddingVertical: 16,
    shadowColor: PP.ink,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
  },
  valueLabel: {
    fontSize: 10, color: PP.slate, textTransform: 'uppercase', letterSpacing: 0.8,
    fontWeight: '500',
  },
  valueAmount: {
    fontSize: ms(32), fontWeight: '700', color: PP.ink, marginTop: 6, letterSpacing: -0.5,
  },
  valueCurrency: { fontSize: ms(18), color: PP.slate, fontWeight: '500' },
  deltaPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: 12, paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.6)',
    borderWidth: 1, borderColor: 'rgba(58,75,224,0.12)',
    alignSelf: 'flex-start',
  },
  deltaText: { fontSize: 11, color: PP.cobalt, fontWeight: '500' },

  /* Achievements wrapper */
  achievementsWrap: {
    paddingHorizontal: GRID_PADDING,
    marginTop: 18,
  },

  /* Booking hint — компактная плашка одной строкой */
  bookingHint: {
    marginHorizontal: GRID_PADDING,
    marginTop: 14,
    marginBottom: 6,
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: 10,
    backgroundColor: 'rgba(255,255,255,0.55)',
    borderWidth: 1, borderColor: PP.hairline,
  },
  bookingHintInline: {
    fontSize: ms(11.5),
    color: PP.slate,
    fontWeight: '500',
    letterSpacing: 0.1,
    textAlign: 'center',
  },
  bookingHintSub: {
    fontSize: ms(11), color: PP.cobalt, fontWeight: '600',
    marginTop: 6, paddingTop: 6,
    borderTopWidth: 1, borderTopColor: PP.hairline,
    textAlign: 'center',
  },

  /* Folders */
  foldersSection: {
    marginTop: 14,
    marginBottom: 6,
  },
  foldersSectionTitle: {
    fontSize: ms(13),
    fontWeight: '700',
    color: PP.ink,
    paddingHorizontal: GRID_PADDING,
    marginBottom: 10,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  foldersScroll: {
    paddingHorizontal: GRID_PADDING,
    gap: 12,
  },
  folderCard: {
    width: 96,
    alignItems: 'center',
  },
  folderImage: {
    width: 96,
    height: 96,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.7)',
    borderWidth: 1,
    borderColor: PP.hairline,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
  },
  folderName: {
    fontSize: ms(12.5),
    color: PP.ink,
    fontWeight: '600',
    textAlign: 'center',
  },
  folderCount: {
    fontSize: ms(10.5),
    color: PP.mute,
    marginTop: 2,
  },

  /* Segmented wrapper — отделён от achievements воздухом сверху */
  segmentedWrap: {
    marginTop: 22,
    paddingHorizontal: GRID_PADDING,
  },

  /* Toolbar — плотно под сегментом (общая пара controls) */
  toolbar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: GRID_PADDING,
    marginTop: 10,
    gap: 8,
  },
  toolbarCount: {
    fontSize: ms(12),
    color: PP.mute,
    fontWeight: '600',
    letterSpacing: 0.3,
    flex: 1,
    textAlign: 'left',
    marginLeft: 4,
  },
  toolbarBtn: {
    // 36×36 + radius 18 — те же размеры, что и в (tabs)/collection.tsx
    // (styles.filterButton), чтобы нижний тулбар чужого профиля визуально
    // совпадал со своим.
    height: 36,
    paddingHorizontal: 10,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.55)',
    borderWidth: 1, borderColor: PP.hairline,
    alignItems: 'center', justifyContent: 'center',
    flexDirection: 'row', gap: 6,
    minWidth: 36,
  },
  toolbarBtnActive: {
    backgroundColor: PP.cobalt,
    borderColor: PP.cobalt,
    paddingHorizontal: 12,
  },
  toolbarBtnActiveTxt: { color: '#fff', fontSize: ms(12), fontWeight: '700' },

  /* Dropdown menu (filter / sort) */
  dropdownCard: {
    backgroundColor: '#fff',
    borderRadius: 14,
    borderWidth: 1, borderColor: PP.hairline,
    padding: 4,
    shadowColor: PP.ink,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
  },
  dropdownItem: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingVertical: 11,
    borderRadius: 10,
  },
  dropdownItemActive: {
    backgroundColor: 'rgba(58,75,224,0.08)',
  },
  dropdownItemTxt: { fontSize: ms(13.5), color: PP.ink, fontWeight: '500' },
  dropdownItemTxtActive: { color: PP.cobalt, fontWeight: '700' },

  viewToggle: {
    // Высота 36 = filterBtn/sortBtn высота → ровный ряд в toolbar.
    flexDirection: 'row',
    height: 36,
    backgroundColor: 'rgba(255,255,255,0.55)',
    borderRadius: 18,
    borderWidth: 1, borderColor: PP.hairline,
    padding: 2, gap: 2,
  },
  viewToggleBtn: {
    width: 32, height: 30, borderRadius: 15,
    alignItems: 'center', justifyContent: 'center',
  },
  viewToggleBtnActive: { backgroundColor: '#fff', borderWidth: 1, borderColor: 'rgba(58,75,224,0.20)' },

  /* Grid — 2 колонки, выровнено с RecordCard (Spacing.md = 16) */
  grid: {
    flexDirection: 'row', flexWrap: 'wrap',
    paddingHorizontal: 16,
    paddingTop: 16, paddingBottom: 8,
    gap: 16,
    rowGap: 20,
  },
  cardArtist: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: 9, letterSpacing: 0.6, color: PP.cobalt, fontWeight: '600',
  },

  /* List */
  list: {
    paddingHorizontal: 16,
    paddingTop: 16, paddingBottom: 8,
    gap: 10,
  },

  empty: {
    width: '100%', textAlign: 'center', color: PP.mute, fontSize: ms(14), paddingVertical: 60,
  },

  /* Sticky CTA — только для гостей */
  ctaWrap: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    alignItems: 'center',
    paddingTop: 36, paddingHorizontal: GRID_PADDING,
  },
  ctaFade: {
    position: 'absolute', left: 0, right: 0, top: 0, bottom: 0,
  },
  cta: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: PP.cobalt,
    paddingHorizontal: 22, paddingVertical: 13,
    borderRadius: 999,
    shadowColor: PP.cobalt, shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.45, shadowRadius: 18,
    elevation: 8,
  },
  ctaTxt: { color: '#fff', fontWeight: '700', fontSize: ms(14), letterSpacing: 0.2 },

  /* Modal */
  modalOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(27,29,38,0.32)' },
  modalContent: {
    backgroundColor: PP.pearl, borderTopLeftRadius: 28, borderTopRightRadius: 28,
    paddingHorizontal: 22, paddingTop: 12,
  },
  modalHandle: {
    alignSelf: 'center', width: 40, height: 4, borderRadius: 2,
    backgroundColor: 'rgba(27,29,38,0.14)', marginBottom: 12,
  },
  modalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 10,
  },
  modalTitle: { fontSize: ms(18), fontWeight: '700', color: PP.ink, letterSpacing: -0.3 },
  modalRecRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingVertical: 10,
    borderTopWidth: 1, borderTopColor: PP.hairline,
    borderBottomWidth: 1, borderBottomColor: PP.hairline,
    marginBottom: 12,
  },
  modalRecCover: {
    width: 56, height: 56, borderRadius: 10, overflow: 'hidden',
    backgroundColor: PP.lavender,
  },
  modalRecTitle: { fontSize: ms(14), color: PP.ink, fontWeight: '700', marginTop: 2 },
  modalInfo: { fontSize: ms(12.5), color: PP.slate, lineHeight: ms(18), marginBottom: 12 },
  input: {
    height: 46, paddingHorizontal: 14, borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderWidth: 1, borderColor: PP.hairline,
    fontSize: ms(14), color: PP.ink,
    marginBottom: 10,
  },
  textarea: { height: 80, paddingTop: 12, textAlignVertical: 'top' },
  confirmBtn: {
    marginTop: 8, height: 50, borderRadius: 14,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: PP.cobalt,
    shadowColor: PP.cobalt, shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.45, shadowRadius: 14,
  },
  confirmBtnTxt: { color: '#fff', fontWeight: '700', fontSize: ms(14) },
});
