/**
 * API клиент для Вертушка Backend
 */
import axios, { AxiosInstance, AxiosError } from 'axios';
import * as SecureStore from 'expo-secure-store';
import {
  AuthTokens,
  LoginRequest,
  RegisterRequest,
  User,
  VinylRecord,
  RecordSearchResponse,
  RecordSearchResult,
  Collection,
  CollectionItem,
  Wishlist,
  WishlistItem,
  SearchFilters,
  MasterSearchResponse,
  MasterRelease,
  MasterVersionsResponse,
  ReleaseSearchResponse,
  ArtistSearchResponse,
  Artist,
  ProfileShareSettings,
  PublicProfile,
  UserWithStats,
  UserPublic,
  WishlistPublicResponse,
  FeedItem,
  GiftBookingCreate,
  GiftBookingResponse,
  CoverScanResponse,
} from './types';

// API сервер
// Для локальной разработки с бэкендом на localhost:
const API_BASE_URL = __DEV__
  ? 'http://192.168.1.66:8000/api'  // Локальный IP для разработки (работает на симуляторе и физическом устройстве)
  : 'https://api.vinyl-vertushka.ru/api'; // Продакшен сервер

const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

// Retry конфигурация для 503 ошибок (Discogs rate limiting)
const MAX_RETRIES = 3;
const RETRY_DELAY = 1500; // 1.5 секунды между попытками

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

class ApiClient {
  private client: AxiosInstance;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 60000, // 60 секунд — бэкенд может долго запрашивать Discogs API
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use(async (config) => {
      const token = await this.getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Интерцептор для обработки ошибок и автообновления токена
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as any;

        // Retry логика для 503 ошибок (Discogs rate limiting)
        if (error.response?.status === 503) {
          const retryCount = originalRequest._retryCount || 0;

          if (retryCount < MAX_RETRIES) {
            originalRequest._retryCount = retryCount + 1;
            await sleep(RETRY_DELAY * (retryCount + 1));
            return this.client(originalRequest);
          }
        }

        // Если 401 и это не запрос на refresh — пробуем обновить токен
        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.isRefreshing) {
            // Ждём пока токен обновится
            return new Promise((resolve) => {
              this.refreshSubscribers.push((token: string) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                resolve(this.client(originalRequest));
              });
            });
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            const newToken = await this.refreshToken();
            if (newToken) {
              this.refreshSubscribers.forEach((callback) => callback(newToken));
              this.refreshSubscribers = [];
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
              return this.client(originalRequest);
            }
          } catch {
            // Refresh не удался — разлогиниваем
            await this.removeTokens();
          } finally {
            this.isRefreshing = false;
          }
        }
        
        return Promise.reject(error);
      }
    );
  }

  // ==================== Token Management ====================

  async getToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      return null;
    }
  }

  async setToken(token: string): Promise<void> {
    await SecureStore.setItemAsync(TOKEN_KEY, token);
  }

  async getRefreshToken(): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
    } catch {
      return null;
    }
  }

  async setRefreshToken(token: string): Promise<void> {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token);
  }

  async setTokens(accessToken: string, refreshToken: string): Promise<void> {
    await this.setToken(accessToken);
    await this.setRefreshToken(refreshToken);
  }

  async removeTokens(): Promise<void> {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  }

  async removeToken(): Promise<void> {
    await this.removeTokens();
  }

  private async refreshToken(): Promise<string | null> {
    const refreshToken = await this.getRefreshToken();
    if (!refreshToken) return null;

    try {
      const response = await axios.post<AuthTokens>(`${API_BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken,
      });
      
      await this.setTokens(response.data.access_token, response.data.refresh_token || refreshToken);
      return response.data.access_token;
    } catch {
      return null;
    }
  }

  // ==================== Auth ====================

  async login(data: LoginRequest): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/login', {
      email: data.email,
      password: data.password,
    });
    
    // Сохраняем оба токена
    await this.setTokens(response.data.access_token, response.data.refresh_token || '');
    return response.data;
  }

  async register(data: RegisterRequest): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/register', data);
    
    // Сохраняем оба токена сразу после регистрации
    await this.setTokens(response.data.access_token, response.data.refresh_token || '');
    return response.data;
  }

  async logout(): Promise<void> {
    await this.removeToken();
  }

  async getMe(): Promise<User> {
    const response = await this.client.get<User>('/users/me');
    return response.data;
  }

  async updateMe(data: { display_name?: string; bio?: string }): Promise<User> {
    const response = await this.client.put<User>('/users/me', data);
    return response.data;
  }

  // ==================== Records ====================

  async searchRecords(
    query: string,
    filters?: SearchFilters,
    page = 1,
    perPage = 20
  ): Promise<RecordSearchResponse> {
    const params: { [key: string]: any } = {
      q: query,
      page,
      per_page: perPage,
    };

    if (filters?.artist) params.artist = filters.artist;
    if (filters?.year) params.year = filters.year;
    if (filters?.label) params.label = filters.label;

    const response = await this.client.get<RecordSearchResponse>('/records/search', { params });
    return response.data;
  }

  async scanBarcode(barcode: string): Promise<RecordSearchResult[]> {
    const response = await this.client.post<RecordSearchResult[]>(
      '/records/scan/barcode',
      null,
      { params: { barcode } }
    );
    return response.data;
  }

  async scanCover(imageBase64: string): Promise<CoverScanResponse> {
    const response = await this.client.post<CoverScanResponse>(
      '/records/scan/cover/',
      { image_base64: imageBase64 }
    );
    return response.data;
  }

  async getRecord(id: string): Promise<VinylRecord> {
    const response = await this.client.get<VinylRecord>(`/records/${id}`);
    return response.data;
  }

  async getRecordByDiscogsId(discogsId: string): Promise<VinylRecord> {
    const response = await this.client.get<VinylRecord>(`/records/discogs/${discogsId}`);
    return response.data;
  }

  // ==================== Masters ====================

  async searchMasters(
    query: string,
    page = 1,
    perPage = 20
  ): Promise<MasterSearchResponse> {
    const params = {
      q: query,
      page,
      per_page: perPage,
    };

    const response = await this.client.get<MasterSearchResponse>('/records/masters/search', { params });
    return response.data;
  }

  async getMaster(masterId: string): Promise<MasterRelease> {
    const response = await this.client.get<MasterRelease>(`/records/masters/${masterId}`);
    return response.data;
  }

  async getMasterVersions(
    masterId: string,
    page = 1,
    perPage = 50
  ): Promise<MasterVersionsResponse> {
    const params = {
      page,
      per_page: perPage,
    };

    const response = await this.client.get<MasterVersionsResponse>(
      `/records/masters/${masterId}/versions`,
      { params }
    );
    return response.data;
  }

  async searchReleases(
    query: string,
    filters?: SearchFilters,
    page = 1,
    perPage = 20
  ): Promise<ReleaseSearchResponse> {
    const params: { [key: string]: any } = {
      q: query,
      page,
      per_page: perPage,
    };

    if (filters?.format) params.format = filters.format;
    if (filters?.country) params.country = filters.country;
    if (filters?.year) params.year = filters.year;

    const response = await this.client.get<ReleaseSearchResponse>('/records/releases/search', { params });
    return response.data;
  }

  // ==================== Artists ====================

  async searchArtists(
    query: string,
    page = 1,
    perPage = 20
  ): Promise<ArtistSearchResponse> {
    const params = {
      q: query,
      page,
      per_page: perPage,
    };

    const response = await this.client.get<ArtistSearchResponse>('/records/artists/search', { params });
    return response.data;
  }

  async getArtist(artistId: string): Promise<Artist> {
    const response = await this.client.get<Artist>(`/records/artists/${artistId}`);
    return response.data;
  }

  async getArtistReleases(
    artistId: string,
    page = 1,
    perPage = 50
  ): Promise<ReleaseSearchResponse> {
    const params = {
      page,
      per_page: perPage,
    };

    const response = await this.client.get<ReleaseSearchResponse>(
      `/records/artists/${artistId}/releases`,
      { params }
    );
    return response.data;
  }

  async getArtistMasters(
    artistId: string,
    page = 1,
    perPage = 50
  ): Promise<MasterSearchResponse> {
    const params = {
      page,
      per_page: perPage,
    };

    const response = await this.client.get<MasterSearchResponse>(
      `/records/artists/${artistId}/masters`,
      { params }
    );
    return response.data;
  }

  // ==================== Collections ====================

  async getCollections(): Promise<Collection[]> {
    const response = await this.client.get<Collection[]>('/collections/');
    return response.data;
  }

  async createCollection(data: { name: string; description?: string }): Promise<Collection> {
    const response = await this.client.post<Collection>('/collections/', data);
    return response.data;
  }

  async getCollection(id: string): Promise<Collection> {
    const response = await this.client.get<Collection>(`/collections/${id}`);
    return response.data;
  }

  async getCollectionItems(collectionId: string): Promise<CollectionItem[]> {
    // Бэкенд возвращает коллекцию с items внутри через GET /collections/{id}
    const collection = await this.getCollection(collectionId);
    return collection.items || [];
  }

  async addToCollection(
    collectionId: string,
    discogsId: string,
    data?: { condition?: string; notes?: string; purchase_price?: number }
  ): Promise<CollectionItem> {
    const response = await this.client.post<CollectionItem>(
      `/collections/${collectionId}/items`,
      { discogs_id: discogsId, ...data }
    );
    return response.data;
  }

  async removeFromCollection(collectionId: string, itemId: string): Promise<void> {
    await this.client.delete(`/collections/${collectionId}/items/${itemId}`);
  }

  // ==================== Wishlists ====================

  async getWishlist(): Promise<Wishlist> {
    const response = await this.client.get<Wishlist>('/wishlists/');
    return response.data;
  }

  async getWishlistItems(): Promise<WishlistItem[]> {
    // Бэкенд возвращает wishlist с items внутри через GET /wishlists
    const wishlist = await this.getWishlist();
    return wishlist.items || [];
  }

  async addToWishlist(
    discogsId: string,
    data?: { priority?: number; notes?: string }
  ): Promise<WishlistItem> {
    const response = await this.client.post<WishlistItem>('/wishlists/items', {
      discogs_id: discogsId,
      ...data,
    });
    return response.data;
  }

  async addToWishlistByRecordId(
    recordId: string,
    data?: { priority?: number; notes?: string }
  ): Promise<WishlistItem> {
    const response = await this.client.post<WishlistItem>('/wishlists/items', {
      record_id: recordId,
      ...data,
    });
    return response.data;
  }

  async removeFromWishlist(itemId: string): Promise<void> {
    // Бэкенд использует /wishlists/records/{item_id}
    await this.client.delete(`/wishlists/records/${itemId}`);
  }

  async moveToCollection(wishlistItemId: string, collectionId: string): Promise<CollectionItem> {
    const response = await this.client.post<CollectionItem>(
      `/wishlists/items/${wishlistItemId}/move-to-collection`,
      { collection_id: collectionId }
    );
    return response.data;
  }

  async getPublicWishlistUrl(): Promise<{ share_token: string; share_url: string }> {
    const response = await this.client.post<{ share_token: string; share_url: string }>('/wishlists/generate-link');
    return response.data;
  }

  // ==================== Public Profile ====================

  async getProfileSettings(): Promise<ProfileShareSettings> {
    const response = await this.client.get<ProfileShareSettings>('/profile/settings');
    return response.data;
  }

  async updateProfileSettings(data: Partial<ProfileShareSettings>): Promise<ProfileShareSettings> {
    const response = await this.client.put<ProfileShareSettings>('/profile/settings', data);
    return response.data;
  }

  async updateProfileHighlights(recordIds: string[]): Promise<ProfileShareSettings> {
    const response = await this.client.put<ProfileShareSettings>('/profile/highlights', {
      record_ids: recordIds,
    });
    return response.data;
  }

  async getPublicProfile(username: string): Promise<PublicProfile> {
    const response = await this.client.get<PublicProfile>(`/profile/public/${username}`);
    return response.data;
  }

  // ==================== Users (by username) ====================

  async getUserByUsername(username: string): Promise<UserWithStats> {
    const response = await this.client.get<UserWithStats>(`/users/by-username/${username}`);
    return response.data;
  }

  async getUserWishlistByUsername(username: string): Promise<WishlistPublicResponse> {
    const response = await this.client.get<WishlistPublicResponse>(`/users/by-username/${username}/wishlist/`);
    return response.data;
  }

  async followUser(userId: string): Promise<void> {
    await this.client.post(`/users/${userId}/follow`);
  }

  async unfollowUser(userId: string): Promise<void> {
    await this.client.delete(`/users/${userId}/follow`);
  }

  async searchUsers(
    query: string,
    page = 1,
    perPage = 20
  ): Promise<UserWithStats[]> {
    const params = { q: query, page, per_page: perPage };
    const response = await this.client.get<UserWithStats[]>('/users/search', { params });
    return response.data;
  }

  async getUserCollection(
    userId: string,
    page = 1,
    perPage = 50
  ): Promise<Collection[]> {
    const params = { page, per_page: perPage };
    const response = await this.client.get<Collection[]>(`/users/${userId}/collection`, { params });
    return response.data;
  }

  async getFollowing(page = 1, perPage = 20): Promise<UserPublic[]> {
    const params = { page, per_page: perPage };
    const response = await this.client.get<UserPublic[]>('/users/me/following', { params });
    return response.data;
  }

  async getFollowers(page = 1, perPage = 20): Promise<UserPublic[]> {
    const params = { page, per_page: perPage };
    const response = await this.client.get<UserPublic[]>('/users/me/followers', { params });
    return response.data;
  }

  async getFeed(page = 1, perPage = 20): Promise<FeedItem[]> {
    const params = { page, per_page: perPage };
    const response = await this.client.get<FeedItem[]>('/users/feed', { params });
    return response.data;
  }

  // ==================== Folders ====================

  async addRecordToFolder(collectionId: string, recordId: string): Promise<CollectionItem> {
    const response = await this.client.post<CollectionItem>(
      `/collections/${collectionId}/items`,
      { record_id: recordId }
    );
    return response.data;
  }

  async renameCollection(id: string, name: string): Promise<Collection> {
    const response = await this.client.put<Collection>(`/collections/${id}`, { name });
    return response.data;
  }

  async deleteCollection(id: string): Promise<void> {
    await this.client.delete(`/collections/${id}`);
  }

  // ==================== Gift Booking ====================

  async bookGift(data: GiftBookingCreate): Promise<GiftBookingResponse> {
    const response = await this.client.post<GiftBookingResponse>('/gifts/book', data);
    return response.data;
  }
}

export const api = new ApiClient();
export default api;
