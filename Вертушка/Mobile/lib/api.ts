/**
 * API клиент для Вертушка Backend
 */
import axios, { AxiosInstance, AxiosError } from 'axios';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import {
  AuthTokens,
  ClickSource,
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
  WishlistFolder,
  PriceHistoryResponse,
  RadarResponse,
  RadarEventsResponse,
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
  SpotifyAlbumCandidate,
  PreflightResponse,
  UserRecordPayload,
  NotificationSettings,
  NotificationListResponse,
  UnreadCountResponse,
  SocialFeedResponse,
  SuggestResponse,
  AppleSignInRequest,
  GoogleSignInRequest,
  MyAchievementsResponse,
  RandomUnlockedResponse,
  CatalogResponse,
  AchievementStats,
  FollowRequestItem,
  FollowActionResult,
  Offer,
  OfferSort,
  MarketCarouselItem,
  MarketStoreInfo,
  MarketSearchItem,
  MarketFormatFilter,
  MarketSortMode,
  MarketFacetsResponse,
  RecordOffersSummary,
  RecordOffersFullResponse,
  AppConfig,
  DiscogsImportResult,
  DiscogsPriceJobStatus,
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

/**
 * Порог «это мастер» в пикселях. Должен совпадать с
 * `Backend/app/services/cover_quality.MASTER_MIN_SIDE` — правило одно, просто
 * применяется по обе стороны: бэк не пускает мелкое в мастера, клиент не тянет
 * мелкое в full-size слот.
 */
const MASTER_MIN_SIDE = 500;

/**
 * Заведомо мелкая картинка? Размер читается из URL: imgproxy-сегменты
 * (`/w:150/h:150/` у Discogs), CAA `front-250`, iTunes `100x100bb`, Deezer
 * `250x250-...`. Неизвестная схема → false: рубить то, чего не разобрали,
 * значило бы терять покрытие (у CAA `/front` и у магазинных CDN размера в URL
 * нет вообще).
 */
export function isThumbGrade(url: string | undefined | null): boolean {
  if (!url) return false;
  const sides: number[] = [];
  for (const rx of [/(?:^|\/)w:(\d+)(?:\/|$)/g, /(?:^|\/)h:(\d+)(?:\/|$)/g, /\/(?:front|back|\d+)-(\d+)(?:\.\w+)?(?:\?|$)/g]) {
    for (const m of url.matchAll(rx)) sides.push(Number(m[1]));
  }
  for (const rx of [/\/(\d+)x(\d+)[a-z]*\.\w+(?:\?|$)/g, /\/images\/[a-z]+\/[0-9a-f]+\/(\d+)x(\d+)/g]) {
    for (const m of url.matchAll(rx)) sides.push(Number(m[1]), Number(m[2]));
  }
  const known = sides.filter((s) => s > 0);
  return known.length > 0 && Math.min(...known) < MASTER_MIN_SIDE;
}

/**
 * URL для full-size слота (герой карточки): только мастер-грейд.
 * В отличие от getCoverUrl НЕ падает на thumb_image_url — 150px-thumb Discogs
 * растянутый на 1170px давал ту самую пикселизацию, и он оставался навсегда,
 * потому что источник у него уже максимальный (размер внутри подписи HMAC).
 */
export function getMasterCoverUrl(
  record: { cover_url?: string; cover_image_url?: string } | null | undefined
): string | undefined {
  if (!record) return undefined;
  if (record.cover_url) return resolveMediaUrl(record.cover_url);
  if (record.cover_image_url && !isThumbGrade(record.cover_image_url)) {
    return record.cover_image_url;
  }
  return undefined;
}

/**
 * URL для плейсхолдер-тира: мелкая картинка, которую можно показать мгновенно,
 * пока грузится мастер. Именно так делает Discogs — в их RN-бандле рядом с
 * основной рецептурой `q:90/h:600/w:600` лежит дешёвая `q:40/h:300/w:400`.
 */
export function getPlaceholderCoverUrl(
  record: { thumb_image_url?: string; cover_image_url?: string } | null | undefined
): string | undefined {
  if (!record) return undefined;
  if (record.thumb_image_url) return record.thumb_image_url;
  if (record.cover_image_url && isThumbGrade(record.cover_image_url)) {
    return record.cover_image_url;
  }
  return undefined;
}

/**
 * Ступени ширины обложек. Клиент округляет свой запрос ВВЕРХ до ближайшей —
 * никогда вниз, иначе картинка растягивалась бы.
 *
 * Зачем ступени вместо точной ширины: ширина ячейки зависит от DPR устройства
 * (2x → 393, 3x → 590, планшет → своё), и каждая уникальная ширина создавала
 * отдельную запись в nginx covers_cache (capped 2 ГБ). Одна и та же обложка
 * лежала там в пяти-шести вариантах, вытесняя другие. Со ступенями вариантов
 * ровно два: 320 (мелкие ячейки) и 640 (крупные), плюс сам мастер на детали.
 *
 * Так же устроено у Discogs: в их RN-бандле зашиты ровно две рецептуры
 * (`h:600/w:600` и `h:300/w:400`), а не размер под конкретный экран — отсюда
 * высокий hit-rate их CDN.
 */
const COVER_LADDER = [320, 640] as const;

/**
 * Ресайз-URL обложки под нужную ширину в пикселях (imgproxy на бэке).
 * Берёт имя файла из нашей mirror-ссылки (…/covers/{name}.jpg или
 * …/uploads/covers/{name}.jpg) и строит {origin}/covers/w/{rung}/{name}.jpg,
 * где {rung} — ступень из COVER_LADDER, округлённая ВВЕРХ от запрошенной
 * ширины. Сервер режет мастер под неё на лету и никогда не апскейлит выше
 * мастера (enlarge=0 в nginx) ⇒ пикселей нет.
 *
 * Возвращает исходный URL без изменений, если это НЕ наша плоская обложка:
 * внешние Discogs/CDN, store-сабдиры (…/covers/store/…), относительные пути.
 */
export function sizedCoverUrl(
  url: string | undefined,
  widthPx: number
): string | undefined {
  if (!url) return url;
  // Имя файла обложки: только плоский …/covers/{name}.jpg (без '/' в имени).
  // Хвост `?v=…` (cache-bust по cover_cached_at, ставится в схемах на бэке)
  // ОБЯЗАН доехать до деривативного URL: зеркало перезаписывает мелкий мастер
  // лучшим источником, и без метки версии nginx отдавал бы старую нарезку из
  // 30-дневного кэша, а expo-image — старую картинку из своего disk-кэша.
  const m = url.match(/\/covers\/([A-Za-z0-9._-]+\.jpg)(\?[^#]*)?$/i);
  const name = m?.[1];
  const version = m?.[2] ?? '';
  if (!name) return url;
  const origin = url.match(/^(https?:\/\/[^/]+)/i)?.[1];
  if (!origin) return url;
  const rung = COVER_LADDER.find((r) => widthPx <= r);
  // Запрос крупнее последней ступени обслуживает сам мастер: он капнут 1000px,
  // поэтому дериватив w:1000 был бы его побайтовой копией — вторая запись в
  // covers_cache за те же пиксели.
  if (!rung) return url;
  return `${origin}/covers/w/${rung}/${name}${version}`;
}

/**
 * Preview-параметры для мгновенной отрисовки /record/[id] из уже известных
 * полей списка (заголовок/артист/обложка/год). Экран карточки рисует их сразу
 * (ветка hasPreview), пока грузится полный payload — тап больше не упирается в
 * спиннер. Защитный: кладёт только непустые ключи.
 *
 * Обложка разведена по двум тирам. `previewCover` — только мастер-грейд, идёт в
 * `source`. `previewThumb` — мелкий превью, идёт в `placeholder`: показывается
 * мгновенно и уступает место мастеру, вместо того чтобы залипнуть растянутым на
 * весь экран (так вели себя 150px-thumb'ы из списка версий).
 */
export function recordPreviewParams(
  record:
    | {
        title?: string | null;
        artist?: string | null;
        year?: number | string | null;
        cover_url?: string;
        cover_image_url?: string;
        thumb_image_url?: string;
        blurhash?: string | null;
      }
    | null
    | undefined
): Record<string, string> {
  if (!record) return {};
  const params: Record<string, string> = {};
  if (record.title) params.previewTitle = String(record.title);
  if (record.artist) params.previewArtist = String(record.artist);
  const cover = getMasterCoverUrl(record);
  if (cover) params.previewCover = cover;
  const thumb = getPlaceholderCoverUrl(record);
  if (thumb) params.previewThumb = thumb;
  if (record.year !== null && record.year !== undefined && record.year !== '') {
    params.previewYear = String(record.year);
  }
  if (record.blurhash) params.previewBlurhash = record.blurhash;
  return params;
}

/**
 * Кладёт жанры/особенности Маркета в query-params. Общий для `/market/search`
 * и `/market/stores/{slug}/all` — сериализация обязана совпадать, иначе один
 * и тот же набор чипов даёт разные результаты на общей витрине и в магазине.
 */
function applyMarketFilterParams(
  params: Record<string, string | number>,
  genres?: string[],
  features?: string[],
): void {
  // Жанры — comma-joined строкой (бэк сплитит): надёжнее array-сериализации.
  if (genres && genres.length > 0) params.genre = genres.join(',');
  // Особенности — отдельные bool-флаги, чтобы бэк-клаузы читались явно.
  if (features?.includes('colored')) params.colored = 'true';
  if (features?.includes('limited')) params.limited = 'true';
  if (features?.includes('new')) params.new = 'true';
}

const TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

class ApiClient {
  private client: AxiosInstance;
  private isRefreshing = false;
  private refreshSubscribers: ((token: string | null) => void)[] = [];
  private inflightRequests = new Map<string, Promise<any>>();
  /**
   * Колбэк, вызываемый когда refresh-токен невалиден и пользователь должен
   * быть разлогинен глобально. Регистрируется из useAuthStore чтобы избежать
   * циклических импортов.
   */
  public onAuthFailure: (() => void) | null = null;

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
            // Ждём пока токен обновится. Если refresh упадёт — резолвимся
            // с rejected promise, чтобы не висеть бесконечно.
            return new Promise((resolve, reject) => {
              this.refreshSubscribers.push((token: string | null) => {
                if (!token) {
                  reject(new Error('UnauthorizedError'));
                  return;
                }
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
            // refreshToken вернул null/undefined — трактуем как провал
            throw new Error('Refresh token returned no token');
          } catch {
            // Refresh не удался — разлогиниваем глобально
            await this.removeTokens();
            // Освобождаем все ожидающие запросы с ошибкой
            this.refreshSubscribers.forEach((cb) => cb(null));
            this.refreshSubscribers = [];
            // Сообщаем стору, чтобы тот сбросил auth-state и роутер увёл на login
            this.onAuthFailure?.();
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

        // Фича выключена рубильником — это не «сервису плохо», а осознанное
        // решение. Ретраи тут только мучают пользователя и долбят эндпоинт,
        // который мы только что погасили. См. Backend/app/api/app_config.py
        if (error.response?.headers?.['x-feature-disabled']) {
          return Promise.reject(error);
        }

        if ((status === 503 || status === 429) && !originalRequest._retryCount) {
          originalRequest._retryCount = 0;
        }

        if ((status === 503 || status === 429) && originalRequest._retryCount < 3) {
          originalRequest._retryCount += 1;
          const baseDelay = status === 429
            ? parseInt(String(error.response?.headers?.['retry-after'] || '5'), 10) * 1000
            : Math.pow(2, originalRequest._retryCount - 1) * 1000;
          // Джиттер ×(0.5..1.5): клиенты, поймавшие 503/429 одновременно
          // (деплой, пиковый залп), не возвращаются синхронной волной.
          const retryAfter = baseDelay * (0.5 + Math.random());

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
   * Принудительное обновление access-токена вне HTTP-интерцептора — для
   * WS-клиента, которому сервер закрыл соединение по протухшему токену.
   * Уважает тот же single-flight, что и интерцептор: если refresh уже летит,
   * просто ждём его результат.
   *
   * null НЕ означает «разлогинить»: refreshToken() глотает и сетевые ошибки,
   * поэтому принудительный logout здесь устроил бы выход из аккаунта на любом
   * обрыве сети. Решение о logout остаётся за 401-веткой интерцептора.
   */
  async ensureFreshAccessToken(): Promise<string | null> {
    if (this.isRefreshing) {
      return new Promise((resolve) => {
        this.refreshSubscribers.push((token) => resolve(token));
      });
    }
    this.isRefreshing = true;
    try {
      const newToken = await this.refreshToken();
      this.refreshSubscribers.forEach((cb) => cb(newToken));
      this.refreshSubscribers = [];
      return newToken;
    } finally {
      this.isRefreshing = false;
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

  /**
   * Восстановление soft-удалённого аккаунта в 30-дневном окне.
   * restoreToken приходит в заголовке X-Restore-Token при попытке
   * логина в удалённый аккаунт (403 account_deleted).
   */
  async restoreAccount(restoreToken: string): Promise<AuthTokens> {
    const response = await this.client.post<AuthTokens>('/auth/restore', {
      restore_token: restoreToken,
    });
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

  // ==================== Reports (UGC, App Store 1.2) ====================

  async reportContent(payload: {
    target_type: 'record' | 'user' | 'message';
    target_id: string;
    reason?: string;
  }): Promise<void> {
    await this.client.post('/reports/', payload);
  }

  // ==================== Notifications ====================

  async savePushToken(token: string): Promise<void> {
    await this.client.put('/users/me/push-token', { push_token: token });
  }

  /** Сброс push-токена на сервере (при логауте, пока auth ещё валиден). */
  async clearPushToken(): Promise<void> {
    await this.client.delete('/users/me/push-token');
  }

  async getNotificationSettings(): Promise<NotificationSettings> {
    const response = await this.client.get<NotificationSettings>('/users/me/notification-settings');
    return response.data;
  }

  async updateNotificationSettings(data: Partial<NotificationSettings>): Promise<NotificationSettings> {
    const response = await this.client.put<NotificationSettings>('/users/me/notification-settings', data);
    return response.data;
  }

  // ==================== Notifications feed (Ты/Подписки) ====================

  async getPersonalNotifications(
    cursor?: string | null,
    limit = 20,
  ): Promise<NotificationListResponse> {
    const params: Record<string, string | number> = { limit };
    if (cursor) params.cursor = cursor;
    const response = await this.client.get<NotificationListResponse>('/notifications/', { params });
    return response.data;
  }

  async getUnreadNotificationsCount(): Promise<number> {
    const response = await this.client.get<UnreadCountResponse>('/notifications/unread-count');
    return response.data.unread_count;
  }

  async markNotificationRead(id: string): Promise<number> {
    const response = await this.client.post<{ unread_count: number }>(`/notifications/${id}/read`);
    return response.data.unread_count;
  }

  async markAllNotificationsRead(): Promise<void> {
    await this.client.post('/notifications/read-all');
  }

  /** Батч «seen = read»: отметить прочитанными список видимых уведомлений. */
  async markNotificationsRead(ids: string[]): Promise<number> {
    const response = await this.client.post<{ unread_count: number }>('/notifications/read', {
      ids,
    });
    return response.data.unread_count;
  }

  async deleteNotification(id: string): Promise<void> {
    await this.client.delete(`/notifications/${id}`);
  }

  /** Отложить повторы по dedup_key этой нотификации на N дней. */
  async snoozeNotification(id: string, days: number): Promise<{ snoozed_until: string }> {
    const response = await this.client.post<{ snoozed_until: string }>(
      `/notifications/${id}/snooze`,
      { days },
    );
    return response.data;
  }

  async getSocialFeed(
    cursor?: string | null,
    limit = 20,
  ): Promise<SocialFeedResponse> {
    const params: Record<string, string | number> = { limit };
    if (cursor) params.cursor = cursor;
    const response = await this.client.get<SocialFeedResponse>('/notifications/social', { params });
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
    if (filters?.year_min != null) params.year_min = filters.year_min;
    if (filters?.year_max != null) params.year_max = filters.year_max;
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

  // ── User-submitted records (source='user') ──────────────────────────────
  // Дабл-чек: нет ли пластинки уже в Маркете/Discogs перед ручным созданием.
  async preflightRecord(payload: {
    artist: string;
    title: string;
    year?: number | null;
    barcode?: string | null;
    catalog?: string | null;
    format_type?: string | null;
  }): Promise<PreflightResponse> {
    const response = await this.client.post<PreflightResponse>(
      '/records/preflight/',
      payload
    );
    return response.data;
  }

  // Автозаполнение из Spotify (артист/альбом → кандидаты с треклистом).
  async spotifySearchAlbums(q: string): Promise<SpotifyAlbumCandidate[]> {
    const response = await this.client.get<{ results: SpotifyAlbumCandidate[] }>(
      '/records/spotify-search/',
      { params: { q } }
    );
    return response.data.results;
  }

  // Создать source='user' запись (фото base64 + поля). Возвращает запись.
  async createUserRecord(payload: UserRecordPayload): Promise<VinylRecord> {
    const response = await this.client.post<VinylRecord>(
      '/records/user/',
      payload
    );
    return response.data;
  }

  // Правка своей user-record (§11). Только автор, только source='user'.
  async updateUserRecord(
    id: string,
    payload: Partial<UserRecordPayload>
  ): Promise<VinylRecord> {
    const response = await this.client.patch<VinylRecord>(
      `/records/user/${id}`,
      payload
    );
    return response.data;
  }

  // ── Пользовательские фото элемента коллекции ────────────────────────────
  // Своё фото пластинки поверх обложки Discogs (UserRecordPhoto.is_primary).
  async uploadUserPhoto(
    collectionId: string,
    itemId: string,
    uri: string
  ): Promise<{ id: string; photo_url: string; is_primary: boolean }> {
    const formData = new FormData();
    formData.append('file', { uri, name: 'cover.jpg', type: 'image/jpeg' } as any);
    const response = await this.client.post<{ id: string; photo_url: string; is_primary: boolean }>(
      `/collections/${collectionId}/items/${itemId}/photos`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data;
  }

  async setPrimaryUserPhoto(
    collectionId: string,
    itemId: string,
    photoId: string
  ): Promise<void> {
    await this.client.patch(
      `/collections/${collectionId}/items/${itemId}/photos/${photoId}`,
      { is_primary: true }
    );
  }

  // Свои ручные релизы (для раздела «Мои релизы» в профиле). §11.
  async listMyUserRecords(): Promise<VinylRecord[]> {
    const response = await this.client.get<VinylRecord[]>('/records/user/mine');
    return response.data;
  }

  /**
   * Удалить свой ручной релиз (мягко: на бэке moderation_status='deleted').
   *
   * 409 `record_in_use` — релиз уже держит кто-то ещё, удалять нельзя; он
   * остаётся в «Моих релизах». Текст для юзера приходит в detail.message.
   */
  async deleteUserRecord(recordId: string): Promise<void> {
    await this.client.delete(`/records/user/${recordId}`);
  }

  async getRecordByDiscogsId(discogsId: string): Promise<VinylRecord> {
    return this.deduplicatedGet<VinylRecord>(`/records/discogs/${discogsId}`);
  }

  /**
   * Предложения магазинов для данной пластинки.
   * Возвращает только in_stock + preorder, со свежим last_seen_at (< 7 дней),
   * с уже завёрнутыми affiliate-ссылками (если у магазина есть программа).
   */
  async getRecordOffers(discogsId: string, sort: OfferSort = 'price'): Promise<Offer[]> {
    return this.deduplicatedGet<Offer[]>(`/records/${discogsId}/offers`, { params: { sort } });
  }

  /**
   * Свежие листинги для карусели «В наличии сейчас» на экране поиска
   * (OFFERS_UX.md Фича 4). Backend дедуплицирует по записи и отдаёт самый
   * дешёвый листинг — один товар = одна обложка в карусели.
   */
  async getMarketFeed(limit = 24): Promise<MarketCarouselItem[]> {
    return this.deduplicatedGet<MarketCarouselItem[]>('/market/new-arrivals', {
      params: { limit },
    });
  }

  // ==================== Маркет — раздел в search.tsx ====================
  //
  // Соответствуют Backend/app/api/market.py. Используются в
  // Mobile/components/market/* и (tabs)/search.tsx / market/store/[slug].

  /**
   * Витрина магазинов с метриками (in_stock_count / avg_price / new_today).
   * Backend дефолтно скрывает магазины с <5 in_stock — чтобы не было пустых
   * каруселей. См. MARKET_AND_PRICE_DRAWER.md §1.9.
   */
  async getMarketStores(minInStock = 5): Promise<MarketStoreInfo[]> {
    return this.deduplicatedGet<MarketStoreInfo[]>('/market/stores', {
      params: { min_in_stock: minInStock },
    });
  }

  /**
   * Карусель листингов одного магазина. До 50 на запрос. Дедупликация
   * на бэке — на одну запись отдаётся только самый дешёвый листинг этого
   * магазина (DISTINCT ON по matched_record_id).
   */
  async getStoreListings(
    slug: string,
    opts: { limit?: number; sort?: MarketSortMode } = {},
  ): Promise<MarketCarouselItem[]> {
    const { limit = 20, sort = 'newest' } = opts;
    return this.deduplicatedGet<MarketCarouselItem[]>(
      `/market/stores/${encodeURIComponent(slug)}/listings`,
      { params: { limit, sort } },
    );
  }

  /**
   * Полная витрина магазина (пагинация) — для экрана `/market/store/[slug]`.
   * Набор фильтров тот же, что у searchMarket (формат + жанры + особенности):
   * провалившись в магазин, юзер не теряет фильтрацию общей витрины.
   * limit max 100.
   */
  async getStoreAll(
    slug: string,
    opts: {
      q?: string;
      format?: MarketFormatFilter | null;
      genres?: string[];
      features?: string[];
      sort?: MarketSortMode;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<MarketSearchItem[]> {
    const { q, format, genres, features, sort = 'price_asc', limit = 50, offset = 0 } = opts;
    const params: Record<string, string | number> = { sort, limit, offset };
    if (q && q.trim().length >= 2) params.q = q.trim();
    if (format) params.format = format;
    applyMarketFilterParams(params, genres, features);
    return this.deduplicatedGet<MarketSearchItem[]>(
      `/market/stores/${encodeURIComponent(slug)}/all`,
      { params },
    );
  }

  /**
   * Глобальный поиск по in_stock-листингам всех магазинов. Дедупликация
   * по record_id (на одну запись — одна карточка с min_price + N магазинов).
   * Пустой `q` → возвращает new arrivals (зависит от sort).
   */
  async searchMarket(
    opts: {
      q?: string;
      format?: MarketFormatFilter | null;
      /** Ключи жанров (мульти). Отправляем строкой через запятую. */
      genres?: string[];
      /** Особенности (мульти): 'colored' | 'limited' | 'new'. */
      features?: string[];
      sort?: MarketSortMode;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<MarketSearchItem[]> {
    const { q, format, genres, features, sort = 'price_asc', limit = 50, offset = 0 } = opts;
    const params: Record<string, string | number> = { sort, limit, offset };
    if (q && q.trim().length >= 2) params.q = q.trim();
    if (format) params.format = format;
    applyMarketFilterParams(params, genres, features);
    return this.deduplicatedGet<MarketSearchItem[]>('/market/search', { params });
  }

  /**
   * Доступные фильтры Маркета (жанры + особенности) со счётчиками. Только
   * опции с count > 0 — Mobile рисует чипы строго по наличию.
   *
   * `storeSlug` сужает подсчёт до одного магазина — для экрана
   * /market/store/[slug], чтобы там не появлялись чипы жанров, которых у
   * этого магазина нет.
   */
  async getMarketFacets(storeSlug?: string): Promise<MarketFacetsResponse> {
    return this.deduplicatedGet<MarketFacetsResponse>('/market/facets', {
      params: storeSlug ? { store: storeSlug } : undefined,
    });
  }

  /**
   * Batch-аггрегат offers для сетки карточек (HotStockTag).
   * Mobile вызывает один раз на видимый набор discogs_ids (до 100), мапит
   * результат к карточкам и рендерит HotStockTag вариант.
   *
   * Возвращает map { discogs_id: RecordOffersSummary }. Записи без offers
   * могут отсутствовать в map'е (HotStockTag для них вернёт null).
   */
  async getOffersSummary(
    discogsIds: string[],
  ): Promise<Record<string, RecordOffersSummary>> {
    if (discogsIds.length === 0) return {};
    // Срезаем до 100 (бэк-валидация: max_length=100)
    const slice = discogsIds.slice(0, 100);
    const response = await this.client.post<Record<string, RecordOffersSummary>>(
      '/records/offers/summary',
      { discogs_ids: slice },
    );
    return response.data;
  }

  /**
   * Полные офферы (exact-match + alt-version) + summary одним response.
   * Для OffersBottomSheet «Все варианты» (Phase 5 OFFERS_UX.md §2.3).
   */
  async getOfferDetailsFull(
    discogsId: string,
    includeMasterVersions = true,
  ): Promise<RecordOffersFullResponse> {
    return this.deduplicatedGet<RecordOffersFullResponse>(
      `/records/${encodeURIComponent(discogsId)}/offers/full`,
      { params: { include_master_versions: includeMasterVersions } },
    );
  }

  /**
   * Полные офферы по record_id (UUID) — для store-native записей,
   * у которых discogs_id = null. Возвращает только exact-match
   * (alt-version'ы недоступны без master_id).
   */
  async getOfferDetailsFullByRecordId(
    recordId: string,
  ): Promise<RecordOffersFullResponse> {
    return this.deduplicatedGet<RecordOffersFullResponse>(
      `/records/by-id/${encodeURIComponent(recordId)}/offers/full`,
    );
  }

  /**
   * Phase A affiliate — регистрация клика «Купить» и получение финального URL
   * с subid для атрибуции. Если бэк недоступен — клиент падает на
   * offer.preview_url (только UTM, без affiliate и без клик-трекинга).
   */
  async trackOfferClick(
    listingId: string,
    source: ClickSource,
  ): Promise<{ click_id: string; url: string }> {
    const response = await this.client.post<{ click_id: string; url: string }>(
      `/offers/${listingId}/click`,
      { source },
    );
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

    return this.deduplicatedGet<MasterSearchResponse>('/records/masters/search', { params });
  }

  async getMaster(masterId: string): Promise<MasterRelease> {
    return this.deduplicatedGet<MasterRelease>(`/records/masters/${masterId}`);
  }

  /**
   * Версии мастер-релиза.
   *
   * fresh=true добавляет cache-buster `_r` — обязателен для cover-ретраев.
   * Бэк отдаёт частичный (дыры закрыты master-обложкой) ответ с max-age=60,
   * и без буста ретрай попал бы в nginx-кэш вместо долеченного ответа.
   * proxy_cache_key на проде включает $is_args$args, так что параметр
   * гарантированно разводит записи кэша.
   */
  async getMasterVersions(
    masterId: string,
    page = 1,
    perPage = 50,
    fresh = false
  ): Promise<MasterVersionsResponse> {
    const params: Record<string, string | number> = {
      page,
      per_page: perPage,
    };
    if (fresh) params._r = Date.now();

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
    if (filters?.year_min != null) params.year_min = filters.year_min;
    if (filters?.year_max != null) params.year_max = filters.year_max;

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
    // sort_order задаёт направление пагинации на бэке: desc = новые→старые,
    // asc = старые→новые. Кэш-ключ на бэке включает направление.
    return this.deduplicatedGet<MasterSearchResponse>(`/records/artists/${artistId}/masters`, {
      params: { page: cursor, per_page: perPage, sort_order: sortOrder },
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
    perPage: number = 30,
    excludeFoldered: boolean = false
  ): Promise<{ items: CollectionItem[]; hasMore: boolean }> {
    const response = await this.client.get<Collection>(`/collections/${collectionId}`, {
      params: { sort_by: sortBy, page, per_page: perPage, exclude_foldered: excludeFoldered },
    });
    const items = response.data.items || [];
    return { items, hasMore: items.length === perPage };
  }

  async getCollectionStats(collectionId: string): Promise<CollectionStats> {
    const response = await this.client.get<CollectionStats>(`/collections/${collectionId}/stats`);
    return response.data;
  }

  // Все id пластинок во всех коллекциях юзера — для надёжного дедупа,
  // не ограниченного page-1 collectionItems.
  async getOwnedIds(): Promise<{ discogs_ids: string[]; record_ids: string[] }> {
    const response = await this.client.get<{ discogs_ids: string[]; record_ids: string[] }>(
      '/collections/owned-ids'
    );
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

  // Добавить по UUID записи (для user-records и найденных дублей §10).
  async addToCollectionByRecordId(
    collectionId: string,
    recordId: string
  ): Promise<CollectionItem> {
    const response = await this.client.post<CollectionItem>(
      `/collections/${collectionId}/items`,
      { record_id: recordId }
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

  async updateWishlistItem(
    itemId: string,
    patch: Partial<Pick<WishlistItem, 'notify_mode' | 'price_threshold_rub' | 'threshold_pct' | 'conditions' | 'accept_alt' | 'priority' | 'notes'>> & {
      // «Нет» на аналоге: этот прессинг больше не предлагать.
      reject_alt_record_id?: string;
    },
  ): Promise<WishlistItem> {
    const response = await this.client.put<WishlistItem>(
      `/wishlists/records/${itemId}`,
      patch,
    );
    return response.data;
  }

  async getRadar(): Promise<RadarResponse> {
    const response = await this.client.get<RadarResponse>('/wishlists/radar');
    return response.data;
  }

  async getRadarEvents(itemId: string, limit = 20): Promise<RadarEventsResponse> {
    const response = await this.client.get<RadarEventsResponse>(
      `/wishlists/radar/events/${itemId}`,
      { params: { limit } },
    );
    return response.data;
  }

  async getPriceHistory(recordId: string, days = 90): Promise<PriceHistoryResponse> {
    const response = await this.client.get<PriceHistoryResponse>(
      `/records/${recordId}/price-history`,
      { params: { days } },
    );
    return response.data;
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

  // ==================== Wishlist Folders ====================

  async getWishlistFolders(): Promise<WishlistFolder[]> {
    const response = await this.client.get<WishlistFolder[]>('/wishlists/folders');
    return response.data;
  }

  async createWishlistFolder(name: string): Promise<WishlistFolder> {
    const response = await this.client.post<WishlistFolder>('/wishlists/folders', { name });
    return response.data;
  }

  async getWishlistFolder(id: string): Promise<WishlistFolder> {
    const response = await this.client.get<WishlistFolder>(`/wishlists/folders/${id}`);
    return response.data;
  }

  async renameWishlistFolder(id: string, name: string): Promise<WishlistFolder> {
    const response = await this.client.put<WishlistFolder>(`/wishlists/folders/${id}`, { name });
    return response.data;
  }

  async deleteWishlistFolder(id: string): Promise<void> {
    await this.client.delete(`/wishlists/folders/${id}`);
  }

  async addItemsToWishlistFolder(folderId: string, wishlistItemIds: string[]): Promise<WishlistFolder> {
    const response = await this.client.post<WishlistFolder>(
      `/wishlists/folders/${folderId}/items`,
      { wishlist_item_ids: wishlistItemIds }
    );
    return response.data;
  }

  async removeItemFromWishlistFolder(folderId: string, wishlistItemId: string): Promise<void> {
    await this.client.delete(`/wishlists/folders/${folderId}/items/${wishlistItemId}`);
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

  async followUser(userId: string): Promise<FollowActionResult> {
    const response = await this.client.post<FollowActionResult>(`/users/${userId}/follow`);
    return response.data;
  }

  async unfollowUser(userId: string): Promise<void> {
    await this.client.delete(`/users/${userId}/follow`);
  }

  // ---- Follow requests (приватные профили) ----

  async cancelFollowRequest(userId: string): Promise<void> {
    await this.client.delete(`/users/${userId}/follow-request`);
  }

  async getIncomingFollowRequests(): Promise<FollowRequestItem[]> {
    const response = await this.client.get<FollowRequestItem[]>('/users/me/follow-requests/incoming');
    return response.data;
  }

  async getOutgoingFollowRequests(): Promise<FollowRequestItem[]> {
    const response = await this.client.get<FollowRequestItem[]>('/users/me/follow-requests/outgoing');
    return response.data;
  }

  async getIncomingFollowRequestsCount(): Promise<number> {
    const response = await this.client.get<{ count: number }>(
      '/users/me/follow-requests/incoming/count'
    );
    return response.data.count;
  }

  async approveFollowRequest(requestId: string): Promise<FollowActionResult> {
    const response = await this.client.post<FollowActionResult>(
      `/users/me/follow-requests/${requestId}/approve`
    );
    return response.data;
  }

  async rejectFollowRequest(requestId: string): Promise<void> {
    await this.client.post(`/users/me/follow-requests/${requestId}/reject`);
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
    // Короткий timeout 15s — для UI-действия 60s слишком долго.
    // Если бэк подвис на отправке email — пользователь увидит ошибку быстро.
    await this.client.put(`/gifts/${bookingId}/cancel`, null, {
      params: { cancel_token: cancelToken },
      timeout: 15000,
    });
  }

  async getMyReceivedGifts(): Promise<GiftReceivedItem[]> {
    const response = await this.client.get<GiftReceivedItem[]>('/gifts/me/received');
    return response.data;
  }

  async completeGiftBooking(bookingId: string): Promise<void> {
    await this.client.put(`/gifts/me/received/${bookingId}/complete`, undefined, {
      timeout: 15000,
    });
  }

  // Подтверждение «да, эту пластинку мне подарили» после скана. Пластинка уже
  // в коллекции — бэк только закрывает бронь и убирает пункт из вишлиста.
  async completeGiftBookingWithRecord(
    bookingId: string,
    collectionItemId: string
  ): Promise<void> {
    await this.client.put(
      `/gifts/me/received/${bookingId}/complete-with-record`,
      undefined,
      { params: { collection_item_id: collectionItemId }, timeout: 15000 }
    );
  }

  // «Нет, это не подарок» — бронь остаётся, но больше не переспрашиваем.
  async dismissGiftMatch(bookingId: string): Promise<void> {
    await this.client.put(`/gifts/me/received/${bookingId}/dismiss-match`, undefined, {
      timeout: 15000,
    });
  }

  // ==================== Achievements ====================

  async getMyAchievements(): Promise<MyAchievementsResponse> {
    const { data } = await this.client.get<MyAchievementsResponse>('/achievements/me');
    return data;
  }

  async getMyRandomUnlocked(): Promise<RandomUnlockedResponse> {
    const { data } = await this.client.get<RandomUnlockedResponse>('/achievements/me/random');
    return data;
  }

  async getAchievementsCatalog(): Promise<CatalogResponse> {
    const { data } = await this.client.get<CatalogResponse>('/achievements/catalog');
    return data;
  }

  async getAchievementsByUsername(username: string): Promise<MyAchievementsResponse> {
    const { data } = await this.client.get<MyAchievementsResponse>(
      `/achievements/by-username/${encodeURIComponent(username)}`
    );
    return data;
  }

  /**
   * Сообщает бэкенду о жесте, следов которого нет в БД (открытие карточки цен
   * и т.п.). Ошибки глушим: ачивки не должны мешать основному сценарию.
   */
  async trackAchievementEvent(
    event: string,
    payload?: Record<string, unknown>,
  ): Promise<void> {
    try {
      await this.client.post('/achievements/events', { event, payload });
    } catch {
      // не критично
    }
  }

  async getAchievementStats(code: string): Promise<AchievementStats> {
    const { data } = await this.client.get<AchievementStats>(
      `/achievements/${encodeURIComponent(code)}/stats`
    );
    return data;
  }

  // Discogs OAuth (per-user токен)
  async getDiscogsStatus(): Promise<{ connected: boolean; username: string | null }> {
    const { data } = await this.client.get('/auth/discogs/status');
    return data;
  }

  async connectDiscogs(): Promise<{ authorize_url: string }> {
    const { data } = await this.client.post('/auth/discogs/connect');
    return data;
  }

  async disconnectDiscogs(): Promise<{ connected: boolean }> {
    const { data } = await this.client.delete('/auth/discogs');
    return data;
  }

  // Логин через Discogs (без JWT) — возвращает URL авторизации.
  async discogsLoginStart(): Promise<{ authorize_url: string }> {
    const { data } = await this.client.post('/auth/discogs/login');
    return data;
  }

  // Обмен one-time ticket из deep-link на JWT-пару. Сохраняет токены.
  async exchangeDiscogsTicket(ticket: string): Promise<AuthTokens> {
    const { data } = await this.client.post<AuthTokens>('/auth/discogs/exchange-ticket', { ticket });
    await this.setTokens(data.access_token, data.refresh_token || '');
    return data;
  }

  // One-time импорт коллекции из Discogs в основную коллекцию.
  //
  // Импорт фоновый: бэкенд отвечает 202 (status: 'started') сразу, ещё до
  // похода в Discogs — большая коллекция под лимитом 60/min качается минуты,
  // и держать это в открытом запросе нельзя. Прогресс и итог (imported/
  // skipped/total) — в поле `import` у getDiscogsImportStatus, там же следом
  // едет прогресс дозагрузки цен (Discogs отдаёт их только поштучно).
  async importDiscogsCollection(): Promise<DiscogsImportResult> {
    const { data } = await this.client.post('/collections/import/discogs');
    return data;
  }

  // Прогресс фонового импорта (поле `import`) и дозагрузки цен. Для поллинга.
  async getDiscogsImportStatus(): Promise<DiscogsPriceJobStatus> {
    const { data } = await this.client.get('/collections/import/discogs/status');
    return data;
  }

  /**
   * Remote config: force-update gate + kill-switch фич.
   * Таймаут укорочен до 8с — этот запрос стоит на пути холодного старта,
   * держать пользователя перед сплэшем минуту нельзя. Ошибку не глушим:
   * fail-open решает вызывающая сторона (см. lib/remoteConfig.ts).
   */
  async getAppConfig(): Promise<AppConfig> {
    const { data } = await this.client.get<AppConfig>('/config/', { timeout: 8000 });
    return data;
  }

}

/**
 * Текст ошибки из ответа бэка. `detail` бывает трёх видов: строка (обычные
 * HTTPException), объект с `message` (409-конфликты — там ещё код и контекст)
 * и массив pydantic-ошибок валидации. Разбирать надо все три: если брать
 * только строку, 409 «эта пластинка уже есть» превращается в безликое
 * «Попробуйте ещё раз».
 */
export function apiErrorText(e: any, fallback = 'Попробуйте ещё раз'): string {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    const msg = Array.isArray(detail) ? detail[0]?.msg : detail.message;
    if (typeof msg === 'string' && msg.trim()) return msg;
  }
  return fallback;
}

export const api = new ApiClient();
export default api;
