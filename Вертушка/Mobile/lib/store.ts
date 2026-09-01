/**
 * Zustand Store для Вертушка
 */
import { create } from 'zustand';
import { toast } from './toast';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';
import { analytics } from './analytics';
import { useMessagesStore } from './messagesStore';
import { useNotificationsStore } from './notificationsStore';
import {
  initAchievementsCache,
  resetAchievementsCache,
  detectAchievementUnlocks,
  detectAchievementUnlocksDebounced,
} from './achievementsBus';

// ==================== In-flight action deduplication ====================
/**
 * Защита от двойных тапов на пользовательские мутации (добавить в коллекцию,
 * забронировать и т.п.). Ключ = "<action>:<id>". Пока действие летит — повторные
 * вызовы с тем же ключом возвращают тот же Promise, не плодят дубль-запросов
 * к бэкенду.
 */
const inFlightActions = new Map<string, Promise<unknown>>();

/**
 * Если бэк опознал в добавленной пластинке забронированный подарок — кладём
 * кандидата в стор, GiftMatchModal покажет вопрос «вам её подарили?».
 * Ничего не решаем сами: master/fuzzy-совпадение — гипотеза, а не факт.
 */
function captureGiftMatch(
  item: CollectionItem,
  set: (partial: { pendingGiftMatch: PendingGiftMatch }) => void
): void {
  if (!item.gift_match) return;
  set({
    pendingGiftMatch: {
      match: item.gift_match,
      collectionItemId: item.id,
      addedRecord: item.record,
    },
  });
}

function dedupeAction<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = inFlightActions.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const promise = fn().finally(() => {
    inFlightActions.delete(key);
  });
  inFlightActions.set(key, promise);
  return promise;
}

// ==================== Freshness / deferred refetch ====================
/**
 * TTL свежести коллекции/вишлиста для фокус-рефетчей. Тот же принцип, что у
 * кэша поиска ниже (CacheStore + TTL.search): пока данные моложе TTL — экраны
 * читают стор и не трогают сеть. Мутации либо сами рефетчат (и обновляют
 * метку), либо явно её сбрасывают.
 */
const COLLECTION_FRESH_TTL_MS = 5 * 60 * 1000;

/**
 * Один отложенный рефетч на серию мутаций: каждое добавление передёргивает
 * таймер, и 20 сканов подряд дают ОДИН refetch коллекции+вишлиста вместо 20
 * пар запросов. Данные до сверки держит оптимистичный локальный апдейт.
 */
let collectionRefetchTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleCollectionRefetch(delayMs = 2000): void {
  if (collectionRefetchTimer) clearTimeout(collectionRefetchTimer);
  collectionRefetchTimer = setTimeout(() => {
    collectionRefetchTimer = null;
    const s = useCollectionStore.getState();
    s.fetchCollectionItems().catch(() => {});
    s.fetchWishlistItems().catch(() => {});
  }, delayMs);
}

/**
 * Оптимистично вписывает добавленный элемент в стор: бэк уже вернул его
 * целиком, поэтому список (сорт по added_at desc → в начало) и сеты владения
 * можно обновить без немедленного полного рефетча. Сверку с сервером сделает
 * scheduleCollectionRefetch().
 */
function applyOptimisticCollectionAdd(item: CollectionItem): void {
  useCollectionStore.setState((s) => {
    const ownedDiscogsIds = new Set(s.ownedDiscogsIds);
    const ownedRecordIds = new Set(s.ownedRecordIds);
    if (item.record.discogs_id) ownedDiscogsIds.add(String(item.record.discogs_id));
    if (item.record_id) ownedRecordIds.add(String(item.record_id));
    return {
      collectionItems: [item, ...s.collectionItems.filter((i) => i.id !== item.id)],
      ownedDiscogsIds,
      ownedRecordIds,
    };
  });
}
import {
  User,
  VinylRecord,
  RecordSearchResult,
  Collection,
  CollectionItem,
  CollectionStats,
  WishlistItem,
  WishlistNotifyMode,
  WishlistCondition,
  WishlistFolder,
  CollectionTab,
  SearchFilters,
  MasterSearchResult,
  MasterSearchResponse,
  MasterRelease,
  ReleaseSearchResult,
  ArtistSearchResult,
  Artist,
  ProfileShareSettings,
  UserWithStats,
  UserPublic,
  FeedItem,
  ScanMode,
  SuggestResponse,
  GiftGivenItem,
  GiftReceivedItem,
  GiftMatchInfo,
} from './types';

/**
 * Опознанный подарок, ожидающий подтверждения пользователя.
 * `collectionItemId` — уже созданный элемент коллекции (подаренная версия),
 * `addedRecord` — что именно отсканировали, `match` — бронь и версия из вишлиста.
 */
export interface PendingGiftMatch {
  match: GiftMatchInfo;
  collectionItemId: string;
  addedRecord: VinylRecord;
}

const getSearchHistoryKey = () => {
  const userId = useAuthStore.getState().user?.id;
  return userId ? `@vertushka:search_history:${userId}` : '@vertushka:search_history';
};
const MAX_HISTORY_ITEMS = 20;
// Легаси-ключ: до перехода на per-user онбординг флаг был один на устройство,
// поэтому второй аккаунт на том же телефоне онбординг не видел. Читаем его
// только для миграции уже установленных приложений.
const ONBOARDING_KEY_LEGACY = '@vertushka:onboarding_complete';
const onboardingKey = (userId: string | null) =>
  userId ? `@vertushka:onboarding_complete:${userId}` : ONBOARDING_KEY_LEGACY;

// ==================== Onboarding Store ====================

/**
 * Онбординг = welcome-карусель (один раз на аккаунт) и ничего больше.
 *
 * Пошаговый spotlight-тур убран намеренно: он держался на measureInWindow
 * с таймерами 60/280/600 мс после навигации, и любая анимация, не уложившаяся
 * в это окно, оставляла рамку висеть в пустоте. Плюс он подсвечивал папки,
 * ценность коллекции и мультивыбор на ПУСТОМ аккаунте, где ими нельзя
 * воспользоваться.
 *
 * Вместо него два механизма, которые ничего не измеряют:
 *   - lib/onboardingProgress.ts — чеклист «Первые шаги» в коллекции;
 *   - lib/useCoachMark.ts       — контекстные подсказки по факту разблокировки.
 */
interface OnboardingState {
  hasSeenWelcome: boolean;
  isReady: boolean;
  /** id аккаунта, для которого прочитан флаг: чтобы не гонять AsyncStorage вхолостую. */
  loadedForUserId: string | null;

  checkOnboarding: (userId: string | null) => Promise<void>;
  completeWelcome: () => Promise<void>;
  resetOnboarding: () => Promise<void>;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  hasSeenWelcome: true,
  isReady: false,
  loadedForUserId: null,

  checkOnboarding: async (userId) => {
    if (get().loadedForUserId === userId && get().isReady) return;
    try {
      let value = await AsyncStorage.getItem(onboardingKey(userId));

      // Миграция: у аккаунта своего флага ещё нет, но на устройстве лежит
      // легаси-ключ — значит этот человек онбординг уже проходил. Переносим,
      // чтобы апдейт приложения не показал карусель повторно.
      //
      // Ключ ПОТРЕБЛЯЕТСЯ: первый аккаунт его забирает, дальше он удаляется.
      // Без этого условие срабатывало на любой аккаунт без своего флага —
      // включая только что зарегистрированный. На устройстве, где онбординг
      // когда-либо проходили, каждый новый пользователь наследовал «уже
      // видел» и попадал сразу в сканер, минуя карусель целиком.
      if (userId) {
        if (value === null) {
          const legacy = await AsyncStorage.getItem(ONBOARDING_KEY_LEGACY);
          if (legacy === 'true') {
            value = 'true';
            await AsyncStorage.setItem(onboardingKey(userId), 'true');
          }
        }
        // Ключ убираем ВСЕГДА, а не только когда миграция сработала. Если у
        // аккаунта уже есть свой флаг, ветка выше не выполняется — и легаси
        // остаётся на устройстве навсегда, отдавая «уже видел» каждому
        // следующему новому аккаунту. Ровно этот случай и наблюдался.
        await AsyncStorage.removeItem(ONBOARDING_KEY_LEGACY);
      }

      set({ hasSeenWelcome: value === 'true', isReady: true, loadedForUserId: userId });
    } catch {
      // Не смогли прочитать — считаем, что онбординг пройден. Показать карусель
      // тому, кто её уже видел, хуже, чем не показать новичку: новичка подхватит
      // чеклист «Первые шаги».
      set({ hasSeenWelcome: true, isReady: true, loadedForUserId: userId });
    }
  },

  completeWelcome: async () => {
    set({ hasSeenWelcome: true });
    try {
      const userId = useAuthStore.getState().user?.id ?? null;
      await AsyncStorage.setItem(onboardingKey(userId), 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
    }
  },

  resetOnboarding: async () => {
    set({ hasSeenWelcome: false });
    try {
      const userId = useAuthStore.getState().user?.id ?? null;
      await AsyncStorage.removeItem(onboardingKey(userId));
    } catch (error) {
      console.error('Failed to reset onboarding state:', error);
    }
  },
}));

// ==================== Auth Store ====================

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  // Actions
  login: (login: string, password: string) => Promise<void>;
  restoreAccount: (restoreToken: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  loginWithApple: (data: import('./types').AppleSignInRequest) => Promise<void>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  loginWithDiscogs: (ticket: string) => Promise<void>;
  logout: () => Promise<void>;
  /**
   * Локальный logout без сетевого вызова. Используется когда refresh-токен
   * невалиден на сервере и долбиться запросом /logout бессмысленно.
   */
  forceLogout: () => void;
  checkAuth: () => Promise<void>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,

  login: async (login, password) => {
    set({ isLoading: true });
    try {
      await api.login({ login, password });
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      analytics.login('email');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  restoreAccount: async (restoreToken) => {
    set({ isLoading: true });
    try {
      await api.restoreAccount(restoreToken);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      analytics.login('email');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  register: async (email, username, password) => {
    set({ isLoading: true });
    try {
      // Регистрация сразу возвращает токен и сохраняет его
      await api.register({ email, username, password });
      // Получаем данные пользователя
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      analytics.register('email');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginWithApple: async (data) => {
    set({ isLoading: true });
    try {
      const tokens = await api.appleSignIn(data);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      // Первый вход через OAuth — это регистрация. Эндпоинт один и на
      // создание, и на возврат, поэтому различает их только бэкенд.
      if (tokens.is_new_user) analytics.register('apple');
      analytics.login('apple');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginWithGoogle: async (idToken) => {
    set({ isLoading: true });
    try {
      const tokens = await api.googleSignIn({ id_token: idToken });
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      // Первый вход через OAuth — это регистрация. Эндпоинт один и на
      // создание, и на возврат, поэтому различает их только бэкенд.
      if (tokens.is_new_user) analytics.register('google');
      analytics.login('google');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginWithDiscogs: async (ticket) => {
    set({ isLoading: true });
    try {
      const tokens = await api.exchangeDiscogsTicket(ticket);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify({ userId: user.id, isStaff: user.is_staff });
      // Первый вход через OAuth — это регистрация. Эндпоинт один и на
      // создание, и на возврат, поэтому различает их только бэкенд.
      if (tokens.is_new_user) analytics.register('discogs');
      analytics.login('discogs');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: async () => {
    // Сбрасываем push-токен на сервере ПОКА auth ещё валиден — иначе после
    // выхода на этот девайс продолжают лететь пуши старого аккаунта.
    await api.clearPushToken().catch(() => {});
    await api.logout();
    set({ user: null, isAuthenticated: false });
    analytics.logout();
    resetUserStores();
    resetAchievementsCache();
  },

  forceLogout: () => {
    set({ user: null, isAuthenticated: false, isLoading: false });
    analytics.logout();
    resetUserStores();
    resetAchievementsCache();
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const token = await api.getToken();
      if (token) {
        const user = await api.getMe();
        set({ user, isAuthenticated: true, isLoading: false });
        analytics.identify({ userId: user.id, isStaff: user.is_staff });
        initAchievementsCache().catch(() => {});
      } else {
        set({ isLoading: false });
      }
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },

  setUser: (user) => set({ user, isAuthenticated: !!user }),
}));

// ==================== Search Store ====================

interface SearchState {
  query: string;
  filters: SearchFilters;
  results: (MasterSearchResult | ReleaseSearchResult)[];
  artistResults: ArtistSearchResult[];
  isLoading: boolean;
  page: number;
  artistPage: number;
  totalResults: number;
  totalArtistResults: number;
  hasMore: boolean;
  hasMoreArtists: boolean;
  searchHistory: string[];
  correctedQuery: string | null;

  // Actions
  setQuery: (query: string) => void;
  setFilters: (filters: SearchFilters) => void;
  clearFilters: () => void;
  search: (query?: string) => Promise<void>;
  loadMore: () => Promise<void>;
  clearResults: () => void;
  loadHistory: () => Promise<void>;
  addToHistory: (query: string) => Promise<void>;
  removeFromHistory: (query: string) => Promise<void>;
  clearHistory: () => Promise<void>;
}

export const useSearchStore = create<SearchState>((set, get) => ({
  query: '',
  filters: {},
  results: [],
  artistResults: [],
  isLoading: false,
  page: 1,
  artistPage: 1,
  totalResults: 0,
  totalArtistResults: 0,
  hasMore: false,
  hasMoreArtists: false,
  searchHistory: [],
  correctedQuery: null,

  setQuery: (query) => set({ query }),

  setFilters: (filters) => set({ filters }),

  clearFilters: () => set({ filters: {} }),

  search: async (newQuery) => {
    const query = newQuery ?? get().query;
    if (!query.trim()) {
      set({ results: [], artistResults: [], totalResults: 0, totalArtistResults: 0, hasMore: false, hasMoreArtists: false });
      return;
    }

    set({ isLoading: true, query, page: 1, artistPage: 1 });
    try {
      const { filters } = get();
      const hasFilters = !!(filters.format || filters.country || filters.year || filters.year_min != null || filters.year_max != null);

      // Ключ кэша поиска
      const cacheKey = `${query}|${hasFilters ? JSON.stringify(filters) : ''}|1`;
      const cached = useCacheStore.getState().getSearch(cacheKey);

      if (cached) {
        set({
          results: cached.results,
          totalResults: cached.totalResults,
          hasMore: cached.hasMore,
          artistResults: cached.artistResults,
          totalArtistResults: cached.totalArtistResults,
          hasMoreArtists: cached.hasMoreArtists,
          correctedQuery: cached.correctedQuery ?? null,
          isLoading: false,
        });
        await get().addToHistory(query.trim());
        return;
      }

      // Универсальный поиск: делаем оба запроса параллельно
      const [releasesResponse, artistsResponse] = await Promise.all([
        hasFilters
          ? api.searchReleases(query, filters, 1)
          : api.searchMasters(query, 1),
        api.searchArtists(query, 1, 15),
      ]);

      // Определяем, было ли исправление запроса (fuzzy match Discogs)
      let correctedQuery: string | null = null;
      const topName = artistsResponse.results[0]?.name;
      if (topName) {
        const queryLower = query.toLowerCase().trim();
        const nameLower = topName.toLowerCase().trim();
        if (
          !nameLower.includes(queryLower) &&
          !queryLower.includes(nameLower) &&
          queryLower !== nameLower
        ) {
          correctedQuery = topName;
        }
      }

      const searchResult = {
        results: releasesResponse.results,
        totalResults: releasesResponse.total,
        hasMore: releasesResponse.results.length < releasesResponse.total,
        artistResults: artistsResponse.results,
        totalArtistResults: artistsResponse.total,
        hasMoreArtists: artistsResponse.results.length < artistsResponse.total,
        correctedQuery,
      };

      // Не кешируем пустую выдачу: при деградации Discogs бэкенд может отдать
      // пустой результат — закешировав, залипли бы на «ничего не найдено» весь TTL.
      if (searchResult.results.length > 0 || searchResult.artistResults.length > 0) {
        useCacheStore.getState().setSearch(cacheKey, searchResult);
      }

      set({
        ...searchResult,
        isLoading: false,
      });

      // Добавляем в историю после успешного поиска
      await get().addToHistory(query.trim());
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loadMore: async () => {
    const { query, filters, page, hasMore, isLoading, results } = get();
    if (!hasMore || isLoading) return;

    set({ isLoading: true });
    try {
      const nextPage = page + 1;
      const hasFilters = !!(filters.format || filters.country || filters.year || filters.year_min != null || filters.year_max != null);

      // Используем тот же тип поиска, что и в основном search
      const response = hasFilters
        ? await api.searchReleases(query, filters, nextPage)
        : await api.searchMasters(query, nextPage);

      set({
        results: [...results, ...response.results],
        page: nextPage,
        hasMore: results.length + response.results.length < response.total,
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  clearResults: () => set({
    results: [],
    artistResults: [],
    query: '',
    page: 1,
    artistPage: 1,
    totalResults: 0,
    totalArtistResults: 0,
    hasMore: false,
    hasMoreArtists: false,
    correctedQuery: null,
  }),

  loadHistory: async () => {
    try {
      const stored = await AsyncStorage.getItem(getSearchHistoryKey());
      if (stored) {
        const history = JSON.parse(stored) as string[];
        set({ searchHistory: history });
      }
    } catch (error) {
      console.error('Failed to load search history:', error);
    }
  },

  addToHistory: async (query) => {
    const { searchHistory } = get();

    // Убираем дубликаты (если запрос уже есть)
    const filtered = searchHistory.filter((item) => item !== query);

    // Добавляем в начало списка
    const newHistory = [query, ...filtered].slice(0, MAX_HISTORY_ITEMS);

    set({ searchHistory: newHistory });

    try {
      await AsyncStorage.setItem(getSearchHistoryKey(), JSON.stringify(newHistory));
    } catch (error) {
      console.error('Failed to save search history:', error);
    }
  },

  removeFromHistory: async (query) => {
    const { searchHistory } = get();
    const newHistory = searchHistory.filter((item) => item !== query);

    set({ searchHistory: newHistory });

    try {
      await AsyncStorage.setItem(getSearchHistoryKey(), JSON.stringify(newHistory));
    } catch (error) {
      console.error('Failed to update search history:', error);
    }
  },

  clearHistory: async () => {
    set({ searchHistory: [] });

    try {
      await AsyncStorage.removeItem(getSearchHistoryKey());
    } catch (error) {
      console.error('Failed to clear search history:', error);
    }
  },
}));

// ==================== Collection Store ====================

interface CollectionState {
  activeTab: CollectionTab;
  collections: Collection[];
  defaultCollection: Collection | null;
  folders: Collection[];
  collectionItems: CollectionItem[];
  collectionPage: number;
  collectionHasMore: boolean;
  isLoadingMore: boolean;
  // Полный сет владения (все коллекции, не только page 1) — для дедупа.
  ownedDiscogsIds: Set<string>;
  ownedRecordIds: Set<string>;
  /** Owned-ids уже загружались хоть раз — дальше сет поддерживают мутации. */
  ownedIdsLoaded: boolean;
  /** Момент последней успешной загрузки (0 = не загружено/инвалидировано). */
  collectionFetchedAt: number;
  wishlistFetchedAt: number;
  wishlistItems: WishlistItem[];
  wishlistFolders: WishlistFolder[];
  isLoading: boolean;
  stats: CollectionStats | null;
  isLoadingStats: boolean;
  sortBy: 'added_at' | 'price_desc' | 'price_asc';

  // Actions
  setActiveTab: (tab: CollectionTab) => void;
  fetchCollections: () => Promise<void>;
  fetchCollectionItems: () => Promise<void>;
  fetchOwnedIds: () => Promise<void>;
  isOwned: (opts: { discogsId?: string | null; recordId?: string | null }) => boolean;
  loadMoreCollectionItems: () => Promise<void>;
  fetchWishlistItems: () => Promise<void>;
  /**
   * Фокус-варианты fetch'ей: сеть трогают только если данные старше TTL
   * (COLLECTION_FRESH_TTL_MS) или инвалидированы мутацией. Экраны, которым
   * нужно «обновить при фокусе», зовут их вместо прямых fetch*.
   */
  ensureCollectionFresh: () => Promise<void>;
  ensureWishlistFresh: () => Promise<void>;
  fetchStats: () => Promise<void>;
  setSortBy: (sort: 'added_at' | 'price_desc' | 'price_asc') => void;
  // Подарок, который бэк опознал при добавлении в коллекцию: показываем поп-ап
  // «вам её подарили?». Держим в сторе, а не на экране, — добавить пластинку
  // можно из четырёх мест (скан, поиск, карточка релиза, ручное добавление).
  pendingGiftMatch: PendingGiftMatch | null;
  confirmGiftMatch: () => Promise<void>;
  dismissGiftMatch: () => Promise<void>;
  addToCollection: (discogsId: string) => Promise<void>;
  addToCollectionByRecordId: (recordId: string) => Promise<void>;
  // Добавить релиз + перекрыть обложку своим фото (UserRecordPhoto.is_primary).
  addToCollectionWithPhoto: (opts: { discogsId?: string; recordId?: string; photoUri: string }) => Promise<void>;
  addToWishlist: (discogsId: string) => Promise<void>;
  addToWishlistByRecordId: (recordId: string) => Promise<void>;
  removeFromCollection: (itemId: string, skipRefetch?: boolean) => Promise<void>;
  removeFromWishlist: (itemId: string, skipRefetch?: boolean) => Promise<void>;
  setWishlistNotifyMode: (itemId: string, mode: WishlistNotifyMode) => Promise<void>;
  setWishlistPriceThreshold: (itemId: string, value: number | null) => Promise<void>;
  setWishlistConditions: (itemId: string, conditions: WishlistCondition[] | null) => Promise<void>;
  setWishlistAcceptAlt: (itemId: string, value: boolean) => Promise<void>;
  // «Нет» на аналоге: больше не предлагать этот прессинг.
  rejectWishlistAlt: (itemId: string, recordId: string) => Promise<void>;
  // Единый PUT: подписать на радар + порог + состояние (для лимит-проверки бэка).
  saveWishlistRadar: (
    itemId: string,
    opts: {
      threshold: number | null;
      /** Задан → режим «дешевле обычного»; null → фиксированная сумма. */
      thresholdPct?: number | null;
      conditions: WishlistCondition[] | null;
    },
  ) => Promise<void>;
  // Убрать с радара: notify_mode='watched' + сброс порога одним PUT.
  removeWishlistRadar: (itemId: string) => Promise<void>;
  moveToCollection: (wishlistItemId: string) => Promise<void>;

  // Folder actions
  createFolder: (name: string) => Promise<Collection>;
  renameFolder: (id: string, name: string) => Promise<void>;
  deleteFolder: (id: string) => Promise<void>;
  addItemsToFolder: (folderId: string, collectionItemIds: string[]) => Promise<void>;

  // Wishlist folder actions
  fetchWishlistFolders: () => Promise<void>;
  createWishlistFolder: (name: string) => Promise<WishlistFolder>;
  renameWishlistFolder: (id: string, name: string) => Promise<void>;
  deleteWishlistFolder: (id: string) => Promise<void>;
  addItemsToWishlistFolder: (folderId: string, wishlistItemIds: string[]) => Promise<void>;
}

export const useCollectionStore = create<CollectionState>((set, get) => ({
  activeTab: 'collection',
  collections: [],
  defaultCollection: null,
  folders: [],
  collectionItems: [],
  ownedDiscogsIds: new Set<string>(),
  ownedRecordIds: new Set<string>(),
  ownedIdsLoaded: false,
  collectionFetchedAt: 0,
  wishlistFetchedAt: 0,
  collectionPage: 1,
  collectionHasMore: false,
  isLoadingMore: false,
  wishlistItems: [],
  wishlistFolders: [],
  isLoading: false,
  stats: null,
  isLoadingStats: false,
  sortBy: 'added_at',

  setActiveTab: (tab) => set({ activeTab: tab }),

  fetchCollections: async () => {
    set({ isLoading: true });
    try {
      const collections = await api.getCollections();
      const sortedCollections = [...collections].sort((a, b) => a.sort_order - b.sort_order);
      const defaultCollection = sortedCollections[0] || null;
      const folders = sortedCollections.filter(c => c.id !== defaultCollection?.id);
      set({ collections, defaultCollection, folders, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  fetchCollectionItems: async () => {
    const { defaultCollection, sortBy } = get();
    if (!defaultCollection) return;

    set({ isLoading: true });
    try {
      const { items, hasMore } = await api.getCollectionItems(defaultCollection.id, sortBy, 1);
      // Owned-ids грузим ОДИН раз (холодный старт), а не на каждый refetch
      // коллекции: дальше сет поддерживают сами мутации — optimistic add,
      // removeFromCollection и ownership-флоу (move, gift, импорт).
      if (!get().ownedIdsLoaded) get().fetchOwnedIds();
      set({
        collectionItems: items,
        collectionPage: 1,
        collectionHasMore: hasMore,
        isLoading: false,
        collectionFetchedAt: Date.now(),
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  fetchOwnedIds: async () => {
    try {
      const { discogs_ids, record_ids } = await api.getOwnedIds();
      set({
        ownedDiscogsIds: new Set(discogs_ids),
        ownedRecordIds: new Set(record_ids),
        ownedIdsLoaded: true,
      });
    } catch {
      // Тихо: дедуп — не критичный путь, не роняем загрузку коллекции.
    }
  },

  isOwned: ({ discogsId, recordId }) => {
    const { ownedDiscogsIds, ownedRecordIds, collectionItems } = get();
    if (discogsId && ownedDiscogsIds.has(String(discogsId))) return true;
    if (recordId && ownedRecordIds.has(String(recordId))) return true;
    // Fallback на page-1 (на случай, если owned-ids ещё не подгрузились/недоступны).
    return collectionItems.some(
      (item) =>
        (!!discogsId && item.record.discogs_id === String(discogsId)) ||
        (!!recordId && item.record.id === String(recordId))
    );
  },

  loadMoreCollectionItems: async () => {
    const { defaultCollection, sortBy, collectionPage, collectionHasMore, isLoadingMore, collectionItems } = get();
    if (!defaultCollection || !collectionHasMore || isLoadingMore) return;

    set({ isLoadingMore: true });
    try {
      const nextPage = collectionPage + 1;
      const { items, hasMore } = await api.getCollectionItems(defaultCollection.id, sortBy, nextPage);
      set({
        collectionItems: [...collectionItems, ...items],
        collectionPage: nextPage,
        collectionHasMore: hasMore,
        isLoadingMore: false,
      });
    } catch (error) {
      set({ isLoadingMore: false });
      throw error;
    }
  },

  fetchStats: async () => {
    const { defaultCollection } = get();
    if (!defaultCollection) return;

    set({ isLoadingStats: true });
    try {
      const stats = await api.getCollectionStats(defaultCollection.id);
      set({ stats, isLoadingStats: false });
    } catch (error) {
      set({ isLoadingStats: false });
      throw error;
    }
  },

  setSortBy: (sort) => {
    const prevSort = get().sortBy;
    set({ sortBy: sort });
    get().fetchCollectionItems().catch(() => {
      set({ sortBy: prevSort });
    });
  },

  fetchWishlistItems: async () => {
    set({ isLoading: true });
    try {
      const items = await api.getWishlistItems();
      set({ wishlistItems: items, isLoading: false, wishlistFetchedAt: Date.now() });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  ensureCollectionFresh: async () => {
    if (
      get().defaultCollection &&
      Date.now() - get().collectionFetchedAt < COLLECTION_FRESH_TTL_MS
    ) {
      return;
    }
    await get().fetchCollections();
    await get().fetchCollectionItems();
  },

  ensureWishlistFresh: async () => {
    if (Date.now() - get().wishlistFetchedAt < COLLECTION_FRESH_TTL_MS) return;
    await get().fetchWishlistItems();
  },

  setWishlistNotifyMode: async (itemId, mode) => {
    // Оптимистично: флипаем локально, откатываем при ошибке сети.
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId ? { ...wi, notify_mode: mode } : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, { notify_mode: mode });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  setWishlistPriceThreshold: async (itemId, value) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId ? { ...wi, price_threshold_rub: value } : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, { price_threshold_rub: value });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  setWishlistConditions: async (itemId, conditions) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId ? { ...wi, conditions } : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, { conditions });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  setWishlistAcceptAlt: async (itemId, value) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId ? { ...wi, accept_alt: value } : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, { accept_alt: value });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  rejectWishlistAlt: async (itemId, recordId) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId ? { ...wi, accept_alt: false } : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, { reject_alt_record_id: recordId });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  saveWishlistRadar: async (itemId, { threshold, thresholdPct = null, conditions }) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId
          ? {
              ...wi,
              notify_mode: 'subscribed',
              price_threshold_rub: threshold,
              threshold_pct: thresholdPct,
              conditions,
            }
          : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, {
        notify_mode: 'subscribed',
        price_threshold_rub: threshold,
        // Шлём всегда, в т.ч. null: только так бэк узнаёт о возврате к
        // фиксированной сумме — без поля в теле он сохранит прежний pct.
        threshold_pct: thresholdPct,
        conditions,
      });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  removeWishlistRadar: async (itemId) => {
    const prev = get().wishlistItems;
    set({
      wishlistItems: prev.map((wi) =>
        wi.id === itemId
          ? { ...wi, notify_mode: 'watched', price_threshold_rub: null, threshold_pct: null }
          : wi,
      ),
    });
    try {
      await api.updateWishlistItem(itemId, {
        notify_mode: 'watched',
        price_threshold_rub: null,
        threshold_pct: null,
      });
    } catch (error) {
      set({ wishlistItems: prev });
      throw error;
    }
  },

  pendingGiftMatch: null,

  confirmGiftMatch: async () => {
    const pending = get().pendingGiftMatch;
    if (!pending) return;
    // Закрываем поп-ап сразу: пластинка уже в коллекции, а бронь на сервере
    // идемпотентна — повторное подтверждение вернёт тот же completed.
    set({ pendingGiftMatch: null });
    analytics.giftMatchConfirmed(pending.match.match_kind);
    await api.completeGiftBookingWithRecord(
      pending.match.booking_id,
      pending.collectionItemId
    );
    // Подтверждённый матч закрывает бронь на сервере — для воронки подарка это
    // такое же завершение, как ручное «Получено!» в карточке.
    analytics.giftCompleted({
      via: 'match_modal',
      discogs_id: pending.addedRecord.discogs_id,
    });
    await get().fetchWishlistItems();
  },

  dismissGiftMatch: async () => {
    const pending = get().pendingGiftMatch;
    if (!pending) return;
    set({ pendingGiftMatch: null });
    // Событие шлём до сетевого вызова: отказ пользователя — факт независимо
    // от того, дошёл ли он до сервера.
    analytics.giftMatchDismissed(pending.match.match_kind);
    // Отказ не критичен: не дошёл — в худшем случае переспросим позже.
    try {
      await api.dismissGiftMatch(pending.match.booking_id);
    } catch (e) {
      console.warn('dismissGiftMatch failed', e);
    }
  },

  addToCollection: async (discogsId) => {
    return dedupeAction(`addToCollection:${discogsId}`, async () => {
      let { defaultCollection, collections } = get();

      if (!defaultCollection) {
        if (collections.length === 0) {
          await api.createCollection({ name: 'Моя коллекция' });
          await get().fetchCollections();
          defaultCollection = get().defaultCollection;
        }

        if (!defaultCollection) {
          throw new Error('Не удалось создать коллекцию');
        }
      }

      const added = await api.addToCollection(defaultCollection.id, discogsId);
      analytics.addToCollection(discogsId);
      captureGiftMatch(added, set);
      // Инвалидируем кэш поиска — счётчики коллекции могли измениться
      useCacheStore.getState().invalidateAll();

      // Бэк вернул элемент целиком — вписываем его в стор оптимистично, а
      // полную сверку (и вишлист, который бэк мог тронуть gift-матчем) делаем
      // одним отложенным рефетчем на всю серию добавлений: 20 сканов подряд =
      // 1 пара запросов, а не 20.
      applyOptimisticCollectionAdd(added);
      scheduleCollectionRefetch();
      // Возможные анлоки: A1, B*, R_* (числовые/самореферентные)
      detectAchievementUnlocksDebounced();
    });
  },

  addToCollectionByRecordId: async (recordId) => {
    return dedupeAction(`addToCollectionByRecordId:${recordId}`, async () => {
      let { defaultCollection, collections } = get();
      if (!defaultCollection) {
        if (collections.length === 0) {
          await api.createCollection({ name: 'Моя коллекция' });
          await get().fetchCollections();
          defaultCollection = get().defaultCollection;
        }
        if (!defaultCollection) {
          throw new Error('Не удалось создать коллекцию');
        }
      }
      const added = await api.addToCollectionByRecordId(defaultCollection.id, recordId);
      analytics.addToCollection(added.record?.discogs_id);
      captureGiftMatch(added, set);
      useCacheStore.getState().invalidateAll();
      applyOptimisticCollectionAdd(added);
      scheduleCollectionRefetch();
      detectAchievementUnlocksDebounced();
    });
  },

  addToCollectionWithPhoto: async ({ discogsId, recordId, photoUri }) => {
    return dedupeAction(`addWithPhoto:${discogsId ?? recordId}`, async () => {
      let { defaultCollection, collections, fetchCollectionItems, fetchWishlistItems } = get();
      if (!defaultCollection) {
        if (collections.length === 0) {
          await api.createCollection({ name: 'Моя коллекция' });
          await get().fetchCollections();
          defaultCollection = get().defaultCollection;
        }
        if (!defaultCollection) {
          throw new Error('Не удалось создать коллекцию');
        }
      }

      const item = discogsId
        ? await api.addToCollection(defaultCollection.id, discogsId)
        : await api.addToCollectionByRecordId(defaultCollection.id, recordId!);
      analytics.addToCollection(discogsId ?? item.record?.discogs_id);
      captureGiftMatch(item, set);
      // Сеты владения обновляем сразу: refetch ниже их больше не трогает.
      applyOptimisticCollectionAdd(item);

      // Фото не критично: релиз уже в коллекции — при сбое аплоада просто
      // останется обложка Discogs.
      try {
        const photo = await api.uploadUserPhoto(defaultCollection.id, item.id, photoUri);
        await api.setPrimaryUserPhoto(defaultCollection.id, item.id, photo.id);
      } catch (e) {
        console.warn('addToCollectionWithPhoto: photo upload failed', e);
      }

      useCacheStore.getState().invalidateAll();
      await Promise.all([fetchCollectionItems(), fetchWishlistItems()]);
      detectAchievementUnlocks();
    });
  },

  addToWishlist: async (discogsId) => {
    if (!discogsId) {
      throw new Error('Не указан ID пластинки');
    }
    return dedupeAction(`addToWishlist:${discogsId}`, async () => {
      await api.addToWishlist(discogsId);
      useCacheStore.getState().invalidateAll();
      await get().fetchWishlistItems();
      // Возможные анлоки: A2. Debounce: серия добавлений → один запрос ачивок.
      detectAchievementUnlocksDebounced();
    });
  },

  addToWishlistByRecordId: async (recordId) => {
    if (!recordId) {
      throw new Error('Не указан ID пластинки');
    }
    return dedupeAction(`addToWishlistByRecordId:${recordId}`, async () => {
      await api.addToWishlistByRecordId(recordId);
      useCacheStore.getState().invalidateAll();
      await get().fetchWishlistItems();
      detectAchievementUnlocksDebounced();
    });
  },

  removeFromCollection: async (itemId, skipRefetch = false) => {
    const { defaultCollection, collectionItems, folders } = get();

    if (!defaultCollection || !itemId) {
      throw new Error('Не указана коллекция или элемент');
    }

    // Находим record_id удаляемой пластинки, чтобы каскадно убрать из папок
    const removedItem = collectionItems.find(i => i.id === itemId);
    const recordId = removedItem?.record_id;

    // Удаляем из основной коллекции
    await api.removeFromCollection(defaultCollection.id, itemId);
    useCacheStore.getState().invalidateAll();
    // Парная метрика к add_to_collection: без неё чистый прирост коллекции
    // не посчитать, видно только валовые добавления.
    analytics.removeFromCollection(removedItem?.record.discogs_id);

    // Каскадно удаляем эту пластинку из всех папок
    if (recordId && folders.length > 0) {
      await Promise.all(
        folders.map(async (folder) => {
          try {
            const folderData = await api.getCollection(folder.id);
            const folderItem = (folderData.items || []).find(
              (i: CollectionItem) => i.record_id === recordId
            );
            if (folderItem) {
              await api.removeFromCollection(folder.id, folderItem.id);
            }
          } catch (error) {
            console.error(`Failed to remove from folder "${folder.name}":`, error);
            toast.error(`Не удалось удалить из папки "${folder.name}"`);
          }
        })
      );
      await get().fetchCollections();
    }

    // Сет владения после удаления пересчитать локально нельзя (page-1 не видит
    // остальные копии) — один дешёвый рефетч owned-ids вместо рефетча на
    // каждый фокус сканера.
    get().fetchOwnedIds();

    if (!skipRefetch) {
      await get().fetchCollectionItems();
    } else {
      // Инвалидация: caller сам управляет списком — следующий фокус-рефетч
      // не должен доверять протухшему стору.
      set({ collectionFetchedAt: 0 });
    }
  },

  removeFromWishlist: async (itemId, skipRefetch = false) => {
    await api.removeFromWishlist(itemId);
    useCacheStore.getState().invalidateAll();
    if (!skipRefetch) {
      await Promise.all([
        get().fetchWishlistItems(),
        get().fetchWishlistFolders(),
      ]);
    } else {
      set({ wishlistFetchedAt: 0 });
    }
  },

  moveToCollection: async (wishlistItemId) => {
    // dedupeAction: без него двойной тап шлёт move дважды — первый успех
    // (item перенесён+удалён), второй → 404 «Элемент не найден» на уже
    // удалённом item.
    return dedupeAction(`moveToCollection:${wishlistItemId}`, async () => {
      const { defaultCollection, fetchCollectionItems, fetchWishlistItems } = get();
      if (!defaultCollection) {
        throw new Error('Коллекция не найдена');
      }

      // Используем атомарный endpoint
      await api.moveToCollection(wishlistItemId, defaultCollection.id);

      // Обновляем оба списка
      await Promise.all([
        fetchCollectionItems(),
        fetchWishlistItems(),
      ]);
      // Перенос меняет владение — сет owned-ids сам этого не узнает.
      get().fetchOwnedIds();

      // Перенос в коллекцию может открыть C-серию (коллекционка/лимитка),
      // scale, genres, eras, geo. Бэкенд анлокает синхронно до ответа 200,
      // поэтому detect сразу видит новые коды → конфетти без задержки.
      detectAchievementUnlocks();
    });
  },

  createFolder: async (name) => {
    const collection = await api.createCollection({ name });
    await get().fetchCollections();
    // Возможные анлоки: A5 «Полка-двойник» (вторая коллекция вручную)
    detectAchievementUnlocks();
    return collection;
  },

  renameFolder: async (id, name) => {
    await api.renameCollection(id, name);
    await get().fetchCollections();
  },

  deleteFolder: async (id) => {
    await api.deleteCollection(id);
    await get().fetchCollections();
  },

  // Ключ намеренно БЕЗ folderId. Баг был ровно в том, что вторая пачка уезжала
  // в другую папку, пока первая ещё в полёте: 18.08.2026 те же 22 пластинки
  // легли в «Рок», а через 5 секунд 20 из них — в «Japanese». Ключ с folderId
  // такой параллельный вызов пропустил бы, так что лочим любое добавление.
  addItemsToFolder: async (folderId, collectionItemIds) => {
    return dedupeAction('addItemsToFolder', async () => {
      const { collectionItems } = get();
      const items = collectionItems.filter(item => collectionItemIds.includes(item.id));
      await Promise.all(
        items.map(item => api.addRecordToFolder(folderId, item.record_id))
      );
      await get().fetchCollections();
    });
  },

  fetchWishlistFolders: async () => {
    try {
      const folders = await api.getWishlistFolders();
      set({ wishlistFolders: folders });
    } catch (error) {
      console.error('Failed to fetch wishlist folders', error);
    }
  },

  createWishlistFolder: async (name) => {
    const folder = await api.createWishlistFolder(name);
    await get().fetchWishlistFolders();
    return folder;
  },

  renameWishlistFolder: async (id, name) => {
    await api.renameWishlistFolder(id, name);
    await get().fetchWishlistFolders();
  },

  deleteWishlistFolder: async (id) => {
    await api.deleteWishlistFolder(id);
    await get().fetchWishlistFolders();
  },

  addItemsToWishlistFolder: async (folderId, wishlistItemIds) => {
    await api.addItemsToWishlistFolder(folderId, wishlistItemIds);
    await get().fetchWishlistFolders();
  },

}));

// ==================== Scanner Store ====================

interface ScannerState {
  scanMode: ScanMode;
  scannedBarcode: string | null;
  scanResults: RecordSearchResult[];
  recognizedInfo: { artist: string; album: string } | null;
  lowConfidence: boolean;
  isScanning: boolean;
  isLoading: boolean;

  // Actions
  setScanMode: (mode: ScanMode) => void;
  setScannedBarcode: (barcode: string | null) => void;
  searchByBarcode: (barcode: string) => Promise<void>;
  searchByCover: (imageBase64: string) => Promise<void>;
  refreshScanCovers: () => Promise<void>;
  clearScan: () => void;
}

export const useScannerStore = create<ScannerState>((set, get) => ({
  scanMode: 'barcode',
  scannedBarcode: null,
  scanResults: [],
  recognizedInfo: null,
  lowConfidence: false,
  isScanning: false,
  isLoading: false,

  setScanMode: (mode) => set({ scanMode: mode, scanResults: [], recognizedInfo: null, lowConfidence: false, scannedBarcode: null }),

  setScannedBarcode: (barcode) => set({ scannedBarcode: barcode }),

  searchByBarcode: async (barcode) => {
    set({ isLoading: true, scannedBarcode: barcode });
    try {
      const results = await api.scanBarcode(barcode);
      set({ scanResults: results, isLoading: false });
    } catch (error) {
      set({ isLoading: false, scanResults: [] });
      throw error;
    }
  },

  // Cover-retry скана: бэкенд дописывает обложки в dump-индекс фоновым
  // прогревом через секунды после ответа. Повторяем запрос и вливаем ТОЛЬКО
  // обложки в существующие результаты — порядок и выбор юзера не трогаем.
  refreshScanCovers: async () => {
    const { scannedBarcode, scanResults } = get();
    if (!scannedBarcode) return;
    if (!scanResults.some((r) => !r.cover_image_url && !r.thumb_image_url)) return;
    try {
      const fresh = await api.scanBarcode(scannedBarcode);
      const freshById = new Map(
        fresh
          .filter((r) => r.discogs_id && (r.cover_image_url || r.thumb_image_url))
          .map((r) => [r.discogs_id, r])
      );
      if (freshById.size === 0) return;
      // Барокод мог смениться, пока летел запрос — не вливаем чужое
      if (get().scannedBarcode !== scannedBarcode) return;
      set({
        scanResults: get().scanResults.map((r) => {
          const f = freshById.get(r.discogs_id);
          return f && !r.cover_image_url && !r.thumb_image_url
            ? { ...r, cover_image_url: f.cover_image_url, thumb_image_url: f.thumb_image_url }
            : r;
        }),
      });
    } catch {
      // best effort: не вышло — карточки остаются с плейсхолдером
    }
  },

  searchByCover: async (imageBase64) => {
    set({ isLoading: true, recognizedInfo: null });
    try {
      const response = await api.scanCover(imageBase64);
      set({
        scanResults: response.results,
        recognizedInfo: {
          artist: response.recognized_artist,
          album: response.recognized_album,
        },
        lowConfidence: response.low_confidence ?? false,
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false, scanResults: [], recognizedInfo: null, lowConfidence: false });
      throw error;
    }
  },

  clearScan: () => set({ scannedBarcode: null, scanResults: [], recognizedInfo: null, lowConfidence: false }),
}));

// ==================== Profile Store ====================

interface ProfileState {
  settings: ProfileShareSettings | null;
  isLoading: boolean;
  isSaving: boolean;

  // Actions
  fetchSettings: () => Promise<void>;
  updateSettings: (data: Partial<ProfileShareSettings>) => Promise<void>;
  updateHighlights: (recordIds: string[]) => Promise<void>;
}

export const useProfileStore = create<ProfileState>((set, get) => ({
  settings: null,
  isLoading: false,
  isSaving: false,

  fetchSettings: async () => {
    set({ isLoading: true });
    try {
      const settings = await api.getProfileSettings();
      set({ settings, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  updateSettings: async (data) => {
    const prev = get().settings;
    // Optimistic update — Switch не будет дёргаться
    set({ settings: prev ? { ...prev, ...data } : null, isSaving: true });
    try {
      const settings = await api.updateProfileSettings(data);
      set({ settings, isSaving: false });
    } catch (error) {
      // Откат при ошибке
      set({ settings: prev, isSaving: false });
      throw error;
    }
  },

  updateHighlights: async (recordIds) => {
    set({ isSaving: true });
    try {
      const settings = await api.updateProfileHighlights(recordIds);
      set({ settings, isSaving: false });
    } catch (error) {
      set({ isSaving: false });
      throw error;
    }
  },
}));

// ==================== User Search Store ====================

interface UserSearchState {
  query: string;
  results: UserWithStats[];
  isLoading: boolean;
  page: number;
  hasMore: boolean;

  // Actions
  setQuery: (query: string) => void;
  search: (query?: string) => Promise<void>;
  loadMore: () => Promise<void>;
  clearResults: () => void;
}

export const useUserSearchStore = create<UserSearchState>((set, get) => ({
  query: '',
  results: [],
  isLoading: false,
  page: 1,
  hasMore: false,

  setQuery: (query) => set({ query }),

  search: async (newQuery) => {
    const query = newQuery ?? get().query;
    if (!query.trim() || query.trim().length < 2) {
      set({ results: [], hasMore: false });
      return;
    }

    set({ isLoading: true, query, page: 1 });
    try {
      const results = await api.searchUsers(query, 1);
      set({
        results,
        hasMore: results.length >= 20,
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loadMore: async () => {
    const { query, page, hasMore, isLoading, results } = get();
    if (!hasMore || isLoading) return;

    set({ isLoading: true });
    try {
      const nextPage = page + 1;
      const newResults = await api.searchUsers(query, nextPage);
      set({
        results: [...results, ...newResults],
        page: nextPage,
        hasMore: newResults.length >= 20,
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  clearResults: () => set({ results: [], query: '', page: 1, hasMore: false }),
}));

// ==================== Follow Store ====================

interface FollowState {
  following: UserPublic[];
  followers: UserPublic[];
  feed: FeedItem[];
  isLoadingFollowing: boolean;
  isLoadingFollowers: boolean;
  isLoadingFeed: boolean;
  feedPage: number;
  hasMoreFeed: boolean;

  // Actions
  fetchFollowing: () => Promise<void>;
  fetchFollowers: () => Promise<void>;
  followUser: (userId: string) => Promise<import('./types').FollowActionResult>;
  unfollowUser: (userId: string) => Promise<void>;
  cancelFollowRequest: (userId: string) => Promise<void>;
  fetchFeed: () => Promise<void>;
  loadMoreFeed: () => Promise<void>;
}

// ==================== Cache Store ====================

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

interface SearchCacheEntry {
  results: (MasterSearchResult | ReleaseSearchResult)[];
  artistResults: ArtistSearchResult[];
  totalResults: number;
  totalArtistResults: number;
  hasMore: boolean;
  hasMoreArtists: boolean;
  correctedQuery?: string | null;
}

interface CacheStore {
  releases: Record<string, CacheEntry<VinylRecord>>;
  artists: Record<string, CacheEntry<Artist>>;
  artistMasters: Record<string, CacheEntry<MasterSearchResponse>>;
  masters: Record<string, CacheEntry<MasterRelease>>;
  searches: Record<string, CacheEntry<SearchCacheEntry>>;

  getRelease: (id: string) => VinylRecord | null;
  setRelease: (id: string, data: VinylRecord) => void;
  getArtist: (id: string) => Artist | null;
  setArtist: (id: string, data: Artist) => void;
  getArtistMasters: (id: string) => MasterSearchResponse | null;
  setArtistMasters: (id: string, data: MasterSearchResponse) => void;
  getMaster: (id: string) => MasterRelease | null;
  setMaster: (id: string, data: MasterRelease) => void;
  getSearch: (key: string) => SearchCacheEntry | null;
  setSearch: (key: string, data: SearchCacheEntry) => void;
  invalidateAll: () => void;
}

const TTL = {
  release: 30 * 60 * 1000,     // 30 минут
  artist: 30 * 60 * 1000,      // 30 минут
  artistMasters: 5 * 60 * 1000, // 5 минут (первая страница)
  master: 30 * 60 * 1000,      // 30 минут
  search: 5 * 60 * 1000,       // 5 минут
};

const MAX_CACHE_ENTRIES = 100;

function isValid<T>(entry: CacheEntry<T> | undefined): boolean {
  if (!entry) return false;
  return Date.now() - entry.timestamp < entry.ttl;
}

function trimCache<T>(cache: Record<string, CacheEntry<T>>): Record<string, CacheEntry<T>> {
  const entries = Object.entries(cache);
  if (entries.length <= MAX_CACHE_ENTRIES) return cache;
  // Удаляем самые старые записи
  entries.sort((a, b) => a[1].timestamp - b[1].timestamp);
  return Object.fromEntries(entries.slice(entries.length - MAX_CACHE_ENTRIES));
}

export const useCacheStore = create<CacheStore>((set, get) => ({
  releases: {},
  artists: {},
  artistMasters: {},
  masters: {},
  searches: {},

  getRelease: (id) => {
    const entry = get().releases[id];
    return isValid(entry) ? entry.data : null;
  },
  setRelease: (id, data) => set((state) => ({
    releases: { ...state.releases, [id]: { data, timestamp: Date.now(), ttl: TTL.release } },
  })),

  getArtist: (id) => {
    const entry = get().artists[id];
    return isValid(entry) ? entry.data : null;
  },
  setArtist: (id, data) => set((state) => ({
    artists: { ...state.artists, [id]: { data, timestamp: Date.now(), ttl: TTL.artist } },
  })),

  getArtistMasters: (id) => {
    const entry = get().artistMasters[id];
    return isValid(entry) ? entry.data : null;
  },
  setArtistMasters: (id, data) => set((state) => ({
    artistMasters: { ...state.artistMasters, [id]: { data, timestamp: Date.now(), ttl: TTL.artistMasters } },
  })),

  getMaster: (id) => {
    const entry = get().masters[id];
    return isValid(entry) ? entry.data : null;
  },
  setMaster: (id, data) => set((state) => ({
    masters: { ...state.masters, [id]: { data, timestamp: Date.now(), ttl: TTL.master } },
  })),

  getSearch: (key) => {
    const entry = get().searches[key];
    return isValid(entry) ? entry.data : null;
  },
  setSearch: (key, data) => set((state) => ({
    searches: trimCache({ ...state.searches, [key]: { data, timestamp: Date.now(), ttl: TTL.search } }),
  })),

  invalidateAll: () => set({ releases: {}, artists: {}, artistMasters: {}, masters: {}, searches: {} }),
}));

// ==================== Suggest Store ====================

interface SuggestState {
  suggestions: SuggestResponse | null;
  isLoading: boolean;
  query: string;
  fetchSuggestions: (q: string) => Promise<void>;
  clear: () => void;
}

export const useSuggestStore = create<SuggestState>((set, get) => ({
  suggestions: null,
  isLoading: false,
  query: '',

  fetchSuggestions: async (q) => {
    if (q.length < 2 || q.startsWith('@')) {
      set({ suggestions: null, query: q });
      return;
    }
    if (q === get().query && get().suggestions) return;

    set({ isLoading: true, query: q });
    try {
      const data = await api.suggest(q);
      if (q === get().query) {
        set({ suggestions: data, isLoading: false });
      }
    } catch {
      set({ isLoading: false });
    }
  },

  clear: () => set({ suggestions: null, query: '' }),
}));

// ==================== Sections Store (collapse state) ====================

interface SectionsState {
  collapsedSections: Record<string, boolean>;
  toggleSection: (id: string) => void;
  initSection: (id: string, collapsed: boolean) => void;
}

export const useSectionsStore = create<SectionsState>((set, get) => ({
  collapsedSections: {},
  toggleSection: (id) =>
    set((state) => ({
      collapsedSections: {
        ...state.collapsedSections,
        [id]: !state.collapsedSections[id],
      },
    })),
  initSection: (id, collapsed) => {
    if (id in get().collapsedSections) return;
    set((state) => ({
      collapsedSections: { ...state.collapsedSections, [id]: collapsed },
    }));
  },
}));

export const useFollowStore = create<FollowState>((set, get) => ({
  following: [],
  followers: [],
  feed: [],
  isLoadingFollowing: false,
  isLoadingFollowers: false,
  isLoadingFeed: false,
  feedPage: 1,
  hasMoreFeed: false,

  fetchFollowing: async () => {
    set({ isLoadingFollowing: true });
    try {
      const following = await api.getFollowing();
      set({ following, isLoadingFollowing: false });
    } catch (error) {
      set({ isLoadingFollowing: false });
      throw error;
    }
  },

  fetchFollowers: async () => {
    set({ isLoadingFollowers: true });
    try {
      const followers = await api.getFollowers();
      set({ followers, isLoadingFollowers: false });
    } catch (error) {
      set({ isLoadingFollowers: false });
      throw error;
    }
  },

  followUser: async (userId) => {
    const result = await api.followUser(userId);
    // Список «подписки» обновляем только если реально создан Follow.
    // Для приватных профилей (status='requested') список не меняется.
    if (result.status === 'followed' || result.status === 'already_following') {
      await get().fetchFollowing();
      // Возможные анлоки: K1 (5 подписок), K7 mutual
      detectAchievementUnlocks();
    }
    // Только реально созданная подписка. 'requested' — это заявка в приватный
    // профиль, которую ещё могут отклонить, а 'already_following' — повторный
    // тап по уже нажатой кнопке; и то и другое надуло бы счётчик.
    if (result.status === 'followed') {
      analytics.followUser(userId);
    }
    return result;
  },

  unfollowUser: async (userId) => {
    await api.unfollowUser(userId);
    await get().fetchFollowing();
  },

  cancelFollowRequest: async (userId) => {
    await api.cancelFollowRequest(userId);
  },

  fetchFeed: async () => {
    set({ isLoadingFeed: true, feedPage: 1 });
    try {
      const feed = await api.getFeed(1);
      set({
        feed,
        feedPage: 1,
        hasMoreFeed: feed.length >= 20,
        isLoadingFeed: false,
      });
    } catch (error) {
      set({ isLoadingFeed: false });
      throw error;
    }
  },

  loadMoreFeed: async () => {
    const { feedPage, hasMoreFeed, isLoadingFeed, feed } = get();
    if (!hasMoreFeed || isLoadingFeed) return;

    set({ isLoadingFeed: true });
    try {
      const nextPage = feedPage + 1;
      const newItems = await api.getFeed(nextPage);
      set({
        feed: [...feed, ...newItems],
        feedPage: nextPage,
        hasMoreFeed: newItems.length >= 20,
        isLoadingFeed: false,
      });
    } catch (error) {
      set({ isLoadingFeed: false });
      throw error;
    }
  },
}));

// ==================== Gifts (бронирования) ====================

interface GiftStore {
  given: GiftGivenItem[];
  received: GiftReceivedItem[];
  isLoading: boolean;
  isLoaded: boolean;
  loadAll: () => Promise<void>;
  removeGiven: (id: string) => void;
  removeReceived: (id: string) => void;
}

export const useGiftStore = create<GiftStore>((set) => ({
  given: [],
  received: [],
  isLoading: false,
  isLoaded: false,

  loadAll: async () => {
    set({ isLoading: true });
    try {
      const [given, received] = await Promise.all([
        api.getMyGivenGifts(),
        api.getMyReceivedGifts(),
      ]);
      set({ given, received, isLoaded: true, isLoading: false });
    } catch {
      set({ isLoading: false });
    }
  },

  removeGiven: (id) => set((state) => ({ given: state.given.filter((g) => g.id !== id) })),
  removeReceived: (id) => set((state) => ({ received: state.received.filter((g) => g.id !== id) })),
}));

// ==================== Глобальный сброс stores при logout ====================
/**
 * Сбрасывает все user-specific stores к initial state. Используется при logout
 * (по кнопке) и forceLogout (по протуханию refresh-токена), чтобы под новым
 * пользователем не светились данные предыдущего.
 *
 * Не трогает useOnboardingStore (про UX, не про user data) и useAuthStore
 * (его сбрасывает сам caller — login/logout reducer).
 */
export function resetUserStores(): void {
  // Отложенный рефетч серии добавлений не должен пережить logout — иначе
  // выстрелит под новым (или уже отсутствующим) пользователем.
  if (collectionRefetchTimer) {
    clearTimeout(collectionRefetchTimer);
    collectionRefetchTimer = null;
  }
  useSearchStore.setState({
    query: '',
    filters: {},
    results: [],
    artistResults: [],
    isLoading: false,
    page: 1,
    artistPage: 1,
    totalResults: 0,
    totalArtistResults: 0,
    hasMore: false,
    hasMoreArtists: false,
    searchHistory: [],
    correctedQuery: null,
  });
  useCollectionStore.setState({
    activeTab: 'collection',
    collections: [],
    defaultCollection: null,
    folders: [],
    collectionItems: [],
    ownedDiscogsIds: new Set<string>(),
    ownedRecordIds: new Set<string>(),
    ownedIdsLoaded: false,
    collectionFetchedAt: 0,
    wishlistFetchedAt: 0,
    collectionPage: 1,
    collectionHasMore: false,
    isLoadingMore: false,
    wishlistItems: [],
    wishlistFolders: [],
    isLoading: false,
    stats: null,
    isLoadingStats: false,
    sortBy: 'added_at',
  });
  useScannerStore.setState({
    scanMode: 'barcode',
    scannedBarcode: null,
    scanResults: [],
    recognizedInfo: null,
    isScanning: false,
    isLoading: false,
  });
  useProfileStore.setState({ settings: null, isLoading: false, isSaving: false });
  useUserSearchStore.setState({
    query: '',
    results: [],
    isLoading: false,
    page: 1,
    hasMore: false,
  });
  useSuggestStore.setState({ suggestions: null, isLoading: false, query: '' });
  useSectionsStore.setState({ collapsedSections: {} });
  useFollowStore.setState({
    following: [],
    followers: [],
    feed: [],
    isLoadingFollowing: false,
    isLoadingFollowers: false,
    isLoadingFeed: false,
    feedPage: 1,
    hasMoreFeed: false,
  });
  useGiftStore.setState({ given: [], received: [], isLoading: false, isLoaded: false });
  useMessagesStore.getState().reset();
  useNotificationsStore.getState().reset();
  // Кэш Discogs — формально не user-specific, но безопаснее почистить
  useCacheStore.getState().invalidateAll();
}


// ==================== API ↔ Auth bridge ====================
// Регистрируем глобальный обработчик: когда refresh-токен невалиден,
// API клиент дёрнет это, и мы сбросим auth-state. RootLayout уже
// слушает isAuthenticated и сделает router.replace на /(auth)/login.
api.onAuthFailure = () => {
  useAuthStore.getState().forceLogout();
};
