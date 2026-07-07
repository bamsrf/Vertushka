/**
 * Zustand Store для Вертушка
 */
import { create } from 'zustand';
import { toast } from './toast';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';
import { analytics } from './analytics';
import { useMessagesStore } from './messagesStore';
import {
  initAchievementsCache,
  resetAchievementsCache,
  detectAchievementUnlocks,
} from './achievementsBus';

// ==================== In-flight action deduplication ====================
/**
 * Защита от двойных тапов на пользовательские мутации (добавить в коллекцию,
 * забронировать и т.п.). Ключ = "<action>:<id>". Пока действие летит — повторные
 * вызовы с тем же ключом возвращают тот же Promise, не плодят дубль-запросов
 * к бэкенду.
 */
const inFlightActions = new Map<string, Promise<unknown>>();

function dedupeAction<T>(key: string, fn: () => Promise<T>): Promise<T> {
  const existing = inFlightActions.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const promise = fn().finally(() => {
    inFlightActions.delete(key);
  });
  inFlightActions.set(key, promise);
  return promise;
}
import {
  User,
  VinylRecord,
  RecordSearchResult,
  Collection,
  CollectionItem,
  CollectionStats,
  WishlistItem,
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
} from './types';

const getSearchHistoryKey = () => {
  const userId = useAuthStore.getState().user?.id;
  return userId ? `@vertushka:search_history:${userId}` : '@vertushka:search_history';
};
const MAX_HISTORY_ITEMS = 20;
const ONBOARDING_KEY = '@vertushka:onboarding_complete';

// ==================== Onboarding Store ====================

export const TOUR_STEP_COUNT = 10;

export type TourTargetKey =
  | 'tab-search'
  | 'tab-index'
  | 'tab-collection'
  | 'scan-segments'
  | 'search-filters'
  | 'collection-view-toggle'
  | 'collection-record-card'
  | 'collection-folders'
  | 'collection-value'
  | 'profile-share';

export interface TargetLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface OnboardingState {
  hasSeenWelcome: boolean;
  tourStep: number | null;
  isReady: boolean;
  tourTargets: Partial<Record<TourTargetKey, TargetLayout>>;

  checkOnboarding: () => Promise<void>;
  completeWelcome: () => Promise<void>;
  startTour: () => void;
  nextStep: () => void;
  setTourStep: (step: number) => void;
  skipTour: () => Promise<void>;
  completeTour: () => Promise<void>;
  setTourTarget: (key: TourTargetKey, layout: TargetLayout) => void;
  resetOnboarding: () => Promise<void>;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  hasSeenWelcome: true,
  tourStep: null,
  isReady: false,
  tourTargets: {},

  checkOnboarding: async () => {
    try {
      const value = await AsyncStorage.getItem(ONBOARDING_KEY);
      set({ hasSeenWelcome: value === 'true', isReady: true });
    } catch {
      set({ hasSeenWelcome: true, isReady: true });
    }
  },

  completeWelcome: async () => {
    set({ hasSeenWelcome: true });
    try {
      await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
    }
  },

  startTour: () => set({ tourStep: 0 }),

  setTourStep: (step) => set({ tourStep: step }),

  nextStep: () => {
    const { tourStep } = get();
    if (tourStep !== null && tourStep < TOUR_STEP_COUNT - 1) {
      set({ tourStep: tourStep + 1 });
    }
  },

  skipTour: async () => {
    set({ tourStep: null, hasSeenWelcome: true });
    try {
      await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
    }
  },

  completeTour: async () => {
    set({ tourStep: null, hasSeenWelcome: true });
    try {
      await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
    }
  },

  setTourTarget: (key, layout) => set((state) => ({
    tourTargets: { ...state.tourTargets, [key]: layout },
  })),

  resetOnboarding: async () => {
    set({ hasSeenWelcome: false, tourStep: null, tourTargets: {} });
    try {
      await AsyncStorage.removeItem(ONBOARDING_KEY);
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
      analytics.identify(user.id);
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
      analytics.identify(user.id);
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
      analytics.identify(user.id);
      analytics.register();
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  loginWithApple: async (data) => {
    set({ isLoading: true });
    try {
      await api.appleSignIn(data);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify(user.id);
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
      await api.googleSignIn({ id_token: idToken });
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify(user.id);
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
      await api.exchangeDiscogsTicket(ticket);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      analytics.identify(user.id);
      analytics.login('discogs');
      initAchievementsCache().catch(() => {});
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: async () => {
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
        analytics.identify(user.id);
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
  fetchStats: () => Promise<void>;
  setSortBy: (sort: 'added_at' | 'price_desc' | 'price_asc') => void;
  addToCollection: (discogsId: string) => Promise<void>;
  addToCollectionByRecordId: (recordId: string) => Promise<void>;
  // Добавить релиз + перекрыть обложку своим фото (UserRecordPhoto.is_primary).
  addToCollectionWithPhoto: (opts: { discogsId?: string; recordId?: string; photoUri: string }) => Promise<void>;
  addToWishlist: (discogsId: string) => Promise<void>;
  addToWishlistByRecordId: (recordId: string) => Promise<void>;
  removeFromCollection: (itemId: string, skipRefetch?: boolean) => Promise<void>;
  removeFromWishlist: (itemId: string, skipRefetch?: boolean) => Promise<void>;
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
      set({ collectionItems: items, collectionPage: 1, collectionHasMore: hasMore, isLoading: false });
      // Полный сет владения держим в синхроне с любым refetch коллекции.
      get().fetchOwnedIds();
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
      set({ wishlistItems: items, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  addToCollection: async (discogsId) => {
    return dedupeAction(`addToCollection:${discogsId}`, async () => {
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

      await api.addToCollection(defaultCollection.id, discogsId);
      // Инвалидируем кэш поиска — счётчики коллекции могли измениться
      useCacheStore.getState().invalidateAll();

      await Promise.all([
        fetchCollectionItems(),
        fetchWishlistItems()
      ]);
      // Возможные анлоки: A1, B*, R_* (числовые/самореферентные)
      detectAchievementUnlocks();
    });
  },

  addToCollectionByRecordId: async (recordId) => {
    return dedupeAction(`addToCollectionByRecordId:${recordId}`, async () => {
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
      await api.addToCollectionByRecordId(defaultCollection.id, recordId);
      useCacheStore.getState().invalidateAll();
      await Promise.all([fetchCollectionItems(), fetchWishlistItems()]);
      detectAchievementUnlocks();
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
      // Возможные анлоки: A2
      detectAchievementUnlocks();
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
      detectAchievementUnlocks();
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

    if (!skipRefetch) await get().fetchCollectionItems();
  },

  removeFromWishlist: async (itemId, skipRefetch = false) => {
    await api.removeFromWishlist(itemId);
    useCacheStore.getState().invalidateAll();
    if (!skipRefetch) {
      await Promise.all([
        get().fetchWishlistItems(),
        get().fetchWishlistFolders(),
      ]);
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

  addItemsToFolder: async (folderId, collectionItemIds) => {
    const { collectionItems } = get();
    const items = collectionItems.filter(item => collectionItemIds.includes(item.id));
    await Promise.all(
      items.map(item => api.addRecordToFolder(folderId, item.record_id))
    );
    await get().fetchCollections();
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
  clearScan: () => void;
}

export const useScannerStore = create<ScannerState>((set) => ({
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
      // Возможен анлок A4 «Распахнул» при is_active=true
      if (settings.is_active && !prev?.is_active) {
        detectAchievementUnlocks();
      }
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
