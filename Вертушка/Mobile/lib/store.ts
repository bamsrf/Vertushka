/**
 * Zustand Store для Вертушка
 */
import { create } from 'zustand';
import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api } from './api';
import {
  User,
  VinylRecord,
  RecordSearchResult,
  Collection,
  CollectionItem,
  CollectionStats,
  WishlistItem,
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
} from './types';

const getSearchHistoryKey = () => {
  const userId = useAuthStore.getState().user?.id;
  return userId ? `@vertushka:search_history:${userId}` : '@vertushka:search_history';
};
const MAX_HISTORY_ITEMS = 20;
const ONBOARDING_KEY = '@vertushka:onboarding_complete';

// ==================== Onboarding Store ====================

interface OnboardingState {
  hasSeenWelcome: boolean;
  tourStep: number | null;
  isReady: boolean;

  checkOnboarding: () => Promise<void>;
  completeWelcome: () => Promise<void>;
  startTour: () => void;
  nextStep: () => void;
  skipTour: () => Promise<void>;
  completeTour: () => Promise<void>;
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  hasSeenWelcome: true,
  tourStep: null,
  isReady: false,

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

  nextStep: () => {
    const { tourStep } = get();
    if (tourStep !== null && tourStep < 2) {
      set({ tourStep: tourStep + 1 });
    }
  },

  skipTour: async () => {
    set({ tourStep: null });
    try {
      await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
    }
  },

  completeTour: async () => {
    set({ tourStep: null });
    try {
      await AsyncStorage.setItem(ONBOARDING_KEY, 'true');
    } catch (error) {
      console.error('Failed to save onboarding state:', error);
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
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: async () => {
    await api.logout();
    set({ user: null, isAuthenticated: false });
  },

  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const token = await api.getToken();
      if (token) {
        const user = await api.getMe();
        set({ user, isAuthenticated: true, isLoading: false });
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
      const hasFilters = !!(filters.format || filters.country || filters.year);

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
        api.searchArtists(query, 1, 10),
      ]);

      const searchResult = {
        results: releasesResponse.results,
        totalResults: releasesResponse.total,
        hasMore: releasesResponse.results.length < releasesResponse.total,
        artistResults: artistsResponse.results,
        totalArtistResults: artistsResponse.total,
        hasMoreArtists: artistsResponse.results.length < artistsResponse.total,
      };

      useCacheStore.getState().setSearch(cacheKey, searchResult);

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
      const hasFilters = !!(filters.format || filters.country || filters.year);

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
  wishlistItems: WishlistItem[];
  isLoading: boolean;
  stats: CollectionStats | null;
  isLoadingStats: boolean;
  sortBy: 'added_at' | 'price_desc' | 'price_asc';

  // Actions
  setActiveTab: (tab: CollectionTab) => void;
  fetchCollections: () => Promise<void>;
  fetchCollectionItems: () => Promise<void>;
  fetchWishlistItems: () => Promise<void>;
  fetchStats: () => Promise<void>;
  setSortBy: (sort: 'added_at' | 'price_desc' | 'price_asc') => void;
  addToCollection: (discogsId: string) => Promise<void>;
  addToWishlist: (discogsId: string) => Promise<void>;
  removeFromCollection: (itemId: string, skipRefetch?: boolean) => Promise<void>;
  removeFromWishlist: (itemId: string, skipRefetch?: boolean) => Promise<void>;
  moveToCollection: (wishlistItemId: string) => Promise<void>;

  // Folder actions
  createFolder: (name: string) => Promise<Collection>;
  renameFolder: (id: string, name: string) => Promise<void>;
  deleteFolder: (id: string) => Promise<void>;
  addItemsToFolder: (folderId: string, collectionItemIds: string[]) => Promise<void>;
}

export const useCollectionStore = create<CollectionState>((set, get) => ({
  activeTab: 'collection',
  collections: [],
  defaultCollection: null,
  folders: [],
  collectionItems: [],
  wishlistItems: [],
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
      const items = await api.getCollectionItems(defaultCollection.id, sortBy);
      set({ collectionItems: items, isLoading: false });
    } catch (error) {
      set({ isLoading: false });
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
  },

  addToWishlist: async (discogsId) => {
    if (!discogsId) {
      throw new Error('Не указан ID пластинки');
    }
    await api.addToWishlist(discogsId);
    useCacheStore.getState().invalidateAll();
    await get().fetchWishlistItems();
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
            Alert.alert('Ошибка', `Не удалось удалить из папки "${folder.name}"`);
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
    if (!skipRefetch) await get().fetchWishlistItems();
  },

  moveToCollection: async (wishlistItemId) => {
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
  },

  createFolder: async (name) => {
    const collection = await api.createCollection({ name });
    await get().fetchCollections();
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

}));

// ==================== Scanner Store ====================

interface ScannerState {
  scanMode: ScanMode;
  scannedBarcode: string | null;
  scanResults: RecordSearchResult[];
  recognizedInfo: { artist: string; album: string } | null;
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
  isScanning: false,
  isLoading: false,

  setScanMode: (mode) => set({ scanMode: mode, scanResults: [], recognizedInfo: null, scannedBarcode: null }),

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
        isLoading: false,
      });
    } catch (error) {
      set({ isLoading: false, scanResults: [], recognizedInfo: null });
      throw error;
    }
  },

  clearScan: () => set({ scannedBarcode: null, scanResults: [], recognizedInfo: null }),
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
  followUser: (userId: string) => Promise<void>;
  unfollowUser: (userId: string) => Promise<void>;
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
    await api.followUser(userId);
    await get().fetchFollowing();
  },

  unfollowUser: async (userId) => {
    await api.unfollowUser(userId);
    await get().fetchFollowing();
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
