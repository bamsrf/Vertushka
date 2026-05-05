/**
 * API клиент для Вертушка Backend
 */
import axios, { AxiosInstance, AxiosError } from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
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
  CollectionStats,
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
  PublicProfileRecord,
  UserWithStats,
  UserPublic,
  WishlistPublicResponse,
  FeedItem,
  GiftBookingCreate,
  GiftBookingResponse,
  GiftGivenItem,
  GiftReceivedItem,
  CoverScanResponse,
  NotificationSettings,
  SuggestResponse,
  AppleSignInRequest,
  GoogleSignInRequest,
} from './types';

// API сервер
// Dev URL берётся из app.json extra.devApiUrl — меняй там, не здесь
const API_BASE_URL = __DEV__
  ? (Constants.expoConfig?.extra?.devApiUrl ?? 'http://localhost:8000/api')
  : 'https://api.vinyl-vertushka.ru/api';

// Базовый URL сервера (без /api) для резолва относительных путей (аватарки и т.д.)
const SERVER_BASE_URL = API_BASE_URL.replace(/\/api$/, '');

/** Превращает относительный путь (/uploads/...) в полный URL */
export function resolveMediaUrl(path: string | undefined | null): string | undefined {
  if (!path) return undefined;
  if (path.startsWith('http')) return path;
  return `${SERVER_BASE_URL}${path}`;
}

/**
 * Возвращает лучший доступный URL обложки для отображения.
 * Приоритет: cover_url (локальный кэш бэкенда) → cover_image_url → thumb_image_url
 */
export function getCoverUrl(
  record: { cover_url?: string; cover_image_url?: string; thumb_image_url?: string } | null | undefined
): string | undefined {
  if (!record) return undefined;
  if (record.cover_url) return resolveMediaUrl(record.cover_url);
  return record.cover_image_url || record.thumb_image_url || undefined;
}

const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

class ApiClient {
  private client: AxiosInstance;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string) => void)[] = [];
  private inflightRequests = new Map<string, Promise<any>>();

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

    // Retry interceptor для 503/429
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as any;
        const status = error.response?.status;

        if ((status === 503 || status === 429) && !originalRequest._retryCount) {
          originalRequest._retryCount = 0;
        }

        if ((status === 503 || status === 429) && originalRequest._retryCount < 3) {
          originalRequest._retryCount += 1;
          const retryAfter = status === 429
            ? parseInt(String(error.response?.headers?.['retry-after'] || '5'), 10) * 1000
            : Math.pow(2, originalRequest._retryCount - 1) * 1000;

          await new Promise((resolve) => setTimeout(resolve, retryAfter));
          return this.client(originalRequest);
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

  /**
   * Дедупликация GET-запросов: если запрос с теми же параметрами уже в полёте,
   * возвращаем промис первого запроса вместо создания нового.
   */
  private deduplicatedGet<T>(url: string, config?: { params?: Record<string, any> }): Promise<T> {
    const key = url + (config?.params ? '?' + JSON.stringify(config.params) : '');
    const existing = this.inflightRequests.get(key);
    if (existing) return existing;

    const promise = this.client.get<T>(url, config)
      .then((res) => {
        this.inflightRequests.delete(key);
        return res.data;
      })
      .catch((err) => {
        this.inflightRequests.delete(key);
        throw err;
      });

    this.inflightRequests.set(key, promise);
    return promise;
  }

  // ==================== Auth ====================

  async login(data: LoginRequest): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/login', {
      login: data.login,
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

  async appleSignIn(data: AppleSignInRequest): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/apple', data);
    await this.setTokens(response.data.access_token, response.data.refresh_token || '');
    return response.data;
  }

  async googleSignIn(data: GoogleSignInRequest): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/google', data);
    await this.setTokens(response.data.access_token, response.data.refresh_token || '');
    return response.data;
  }

  async forgotPassword(email: string): Promise<void> {
    await this.client.post('/auth/forgot-password/', { email });
  }

  async verifyResetCode(email: string, code: string): Promise<string> {
    const response = await this.client.post<{ reset_token: string }>('/auth/verify-reset-code/', { email, code });
    return response.data.reset_token;
  }

  async resetPassword(resetToken: string, newPassword: string): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/reset-password/', {
      reset_token: resetToken,
      new_password: newPassword,
    });
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

  async updateMe(data: { username?: string; display_name?: string; bio?: string }): Promise<User> {
    const response = await this.client.put<User>('/users/me', data);
    return response.data;
  }

  async checkUsername(username: string): Promise<{ available: boolean; reason?: string }> {
    const response = await this.client.get<{ available: boolean; reason?: string }>(
      `/users/check-username/${encodeURIComponent(username)}`
    );
    return response.data;
  }

  // ==================== Avatar ====================

  async uploadAvatar(uri: string): Promise<{ avatar_url: string }> {
    const formData = new FormData();
    formData.append('file', {
      uri,
      name: 'avatar.jpg',
      type: 'image/jpeg',
    } as any);

    const response = await this.client.post<User>('/users/me/avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return { avatar_url: response.data.avatar_url || '' };
  }

  async deleteAvatar(): Promise<void> {
    await this.client.delete('/users/me/avatar');
  }

  // ==================== Account Deletion ====================

  async deleteMyAccount(): Promise<{ message: string; scheduled_purge_at: string }> {
    const response = await this.client.delete<{ message: string; scheduled_purge_at: string }>('/users/me');
    return response.data;
  }

  // ==================== Notifications ====================

  async savePushToken(token: string): Promise<void> {
    await this.client.put('/users/me/push-token', { push_token: token });
  }

  async getNotificationSettings(): Promise<NotificationSettings> {
    const response = await this.client.get<NotificationSettings>('/users/me/notification-settings');
    return response.data;
  }

  async updateNotificationSettings(data: Partial<NotificationSettings>): Promise<NotificationSettings> {
    const response = await this.client.put<NotificationSettings>('/users/me/notification-settings', data);
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

    return this.deduplicatedGet<RecordSearchResponse>('/records/search', { params });
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
    return this.deduplicatedGet<VinylRecord>(`/records/${id}`);
  }

  async getRecordByDiscogsId(discogsId: string): Promise<VinylRecord> {
    return this.deduplicatedGet<VinylRecord>(`/records/discogs/${discogsId}`);
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

    return this.deduplicatedGet<MasterSearchResponse>('/records/masters/search', { params });
  }

  async getMaster(masterId: string): Promise<MasterRelease> {
    return this.deduplicatedGet<MasterRelease>(`/records/masters/${masterId}`);
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

    return this.deduplicatedGet<MasterVersionsResponse>(`/records/masters/${masterId}/versions`, { params });
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

    return this.deduplicatedGet<ReleaseSearchResponse>('/records/releases/search', { params });
  }

  // ==================== Artists ====================

  async suggest(query: string, limit = 8): Promise<SuggestResponse> {
    return this.deduplicatedGet<SuggestResponse>('/records/suggest', {
      params: { q: query, limit },
    });
  }

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

    return this.deduplicatedGet<ArtistSearchResponse>('/records/artists/search', { params });
  }

  async getArtist(artistId: string): Promise<Artist> {
    return this.deduplicatedGet<Artist>(`/records/artists/${artistId}`);
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

    return this.deduplicatedGet<ReleaseSearchResponse>(`/records/artists/${artistId}/releases`, { params });
  }

  async getArtistMasters(
    artistId: string,
    sortOrder: 'asc' | 'desc' = 'asc',
    cursor: number = 1,
    perPage: number = 20,
  ): Promise<MasterSearchResponse> {
    return this.deduplicatedGet<MasterSearchResponse>(`/records/artists/${artistId}/masters`, {
      params: { sort_order: sortOrder, page: cursor, per_page: perPage },
    });
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

  async getCollectionItems(
    collectionId: string,
    sortBy: string = 'added_at',
    page: number = 1,
    perPage: number = 30
  ): Promise<{ items: CollectionItem[]; hasMore: boolean }> {
    const response = await this.client.get<Collection>(`/collections/${collectionId}`, {
      params: { sort_by: sortBy, page, per_page: perPage },
    });
    const items = response.data.items || [];
    return { items, hasMore: items.length === perPage };
  }

  async getCollectionStats(collectionId: string): Promise<CollectionStats> {
    const response = await this.client.get<CollectionStats>(`/collections/${collectionId}/stats`);
    return response.data;
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

  async getWishlistShareInfo(): Promise<{ share_token: string; share_url: string }> {
    const response = await this.client.get<{ share_token: string; share_url: string }>('/wishlists/share-info');
    return response.data;
  }

  async regenerateWishlistShareToken(): Promise<{ share_token: string; share_url: string }> {
    const response = await this.client.post<{ share_token: string; share_url: string }>('/wishlists/regenerate-share-token');
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

  async getNewReleases(limit = 12): Promise<PublicProfileRecord[]> {
    const response = await this.client.get<PublicProfileRecord[]>(
      `/profile/public/new-releases`,
      { params: { limit } }
    );
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

  // ==================== Export ====================

  async exportCollectionCSV(): Promise<string> {
    const response = await this.client.get('/export/collection.csv', {
      responseType: 'text',
      headers: { Accept: 'text/csv' },
    });
    return response.data;
  }

  async exportWishlistCSV(): Promise<string> {
    const response = await this.client.get('/export/wishlist.csv', {
      responseType: 'text',
      headers: { Accept: 'text/csv' },
    });
    return response.data;
  }

  // ==================== Gift Booking ====================

  async bookGift(data: GiftBookingCreate): Promise<GiftBookingResponse> {
    const response = await this.client.post<GiftBookingResponse>('/gifts/book', data);
    return response.data;
  }

  async getMyGivenGifts(): Promise<GiftGivenItem[]> {
    const response = await this.client.get<GiftGivenItem[]>('/gifts/me/given');
    return response.data;
  }

  async cancelGiftBooking(bookingId: string, cancelToken: string): Promise<void> {
    await this.client.put(`/gifts/${bookingId}/cancel`, null, {
      params: { cancel_token: cancelToken },
    });
  }

  async getMyReceivedGifts(): Promise<GiftReceivedItem[]> {
    const response = await this.client.get<GiftReceivedItem[]>('/gifts/me/received');
    return response.data;
  }

  async completeGiftBooking(bookingId: string): Promise<void> {
    await this.client.put(`/gifts/me/received/${bookingId}/complete`);
  }
}

export const api = new ApiClient();
export default api;
