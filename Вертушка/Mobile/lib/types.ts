/**
 * TypeScript типы для Вертушка
 */

// ==================== User ====================

export interface User {
  id: string;
  email: string | null;  // null для аккаунтов через Discogs-логин
  username: string;
  display_name?: string;
  avatar_url?: string;
  bio?: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

export interface LoginRequest {
  login: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
}

export interface AppleSignInRequest {
  identity_token: string;
  authorization_code: string;
  user_identifier: string;
  email?: string | null;
  full_name?: string | null;
}

export interface GoogleSignInRequest {
  id_token: string;
}

// ==================== VinylRecord (Пластинка) ====================

export interface VinylRecord {
  id: string;
  /**
   * 'discogs' (default) — обычная запись из Discogs API.
   * 'store' — store-native: создана из листинга магазина, когда на Discogs нет.
   *           Виден в Маркете, но добавить в коллекцию/вишлист пока нельзя
   *           (см. бэкенд-guard в collections/wishlists POST).
   */
  source?: 'discogs' | 'store' | 'user';
  // user-record (§11): автор и статус модерации (модерация отменена → approved).
  created_by_user_id?: string | null;
  moderation_status?: string;
  discogs_id?: string;
  discogs_master_id?: string;
  title: string;
  artist: string;
  label?: string;
  catalog_number?: string;
  year?: number;
  country?: string;
  genre?: string;
  style?: string;
  format_type?: string;
  format_description?: string;
  vinyl_color_raw?: string;
  /** Цвет для показа (прототип/чип), уже разрешён бэком из реального оффера
   * этого релиза (exact > album), иначе Discogs-цвет. Приходит готовым в GET
   * записи — рисуем сразу, без второго запроса. Пусто → фолбэк на vinyl_color_raw. */
  display_vinyl_color?: string;
  barcode?: string;
  estimated_price_min?: number;
  estimated_price_max?: number;
  estimated_price_median?: number;
  price_currency: string;
  estimated_price_min_rub?: number;
  estimated_price_median_rub?: number;
  estimated_price_max_rub?: number;
  usd_rub_rate?: number;
  ru_markup?: number;
  price_source?:
    | 'marketplace_active'
    | 'marketplace_historical'
    | 'discogs_raw'
    | 'discogs_import_estimate';
  price_offers_count?: number;
  cover_image_url?: string;
  thumb_image_url?: string;
  cover_url?: string;
  blurhash?: string | null; // blur-плейсхолдер, пока грузится full-res
  artist_id?: string;
  artist_thumb_image_url?: string;
  tracklist?: Track[];
  // Rarity flags — see Mobile/components/RarityAura.tsx
  is_first_press?: boolean;
  is_canon?: boolean;
  is_collectible?: boolean;
  is_limited?: boolean;
  is_hot?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Track {
  position: string;
  title: string;
  duration?: string;
}

// ==================== Offers (предложения магазинов) ====================

export interface OfferStoreInfo {
  slug: string;
  name: string;
  logo_url?: string | null;
  rating: number;
}

export interface Offer {
  listing_id: string;
  store: OfferStoreInfo;
  price_rub: string; // Decimal приходит строкой
  condition?: string | null;
  vinyl_color?: string | null;
  format?: string | null;
  url: string;            // уже завёрнут в affiliate если применимо
  status: 'in_stock' | 'preorder';
  last_seen_at: string;   // ISO
  // Phase 5 fields — для OfferDetailCard в bottom-sheet (Backend Phase 6):
  catalog_number?: string | null;
  is_alt_version?: boolean;
  /** Уверенность что это ИМЕННО этот пресс ('exact') или просто тот же альбом
   * ('album' — fuzzy/низкая confidence/конфликт цвета). is_alt_version всегда
   * подразумевает 'album'. Mobile рисует 'album' в секции «пресс может
   * отличаться» + дисклеймер + увод в магазин. */
  pressing_match?: 'exact' | 'album';
  image_url?: string | null;
  /** discogs_id записи к которой матчен листинг. Может отличаться от
   * запроса при is_alt_version=true. Используется для navigation
   * к /record/{record_discogs_id} с alt-карточки в bottom-sheet. */
  record_discogs_id?: string | null;
}

// ==================== Market (Phase 1-6 backend wiring) ====================
//
// Соответствует Backend/app/schemas/offer.py.
// Используется в Mobile/components/market/* для HotStockTag, MarketSection,
// OffersBottomSheet и т.д.

/**
 * Аггрегат офферов на одну запись. Mobile вычисляет HotStockVariant правилами:
 *   - in_stock_count == 1 → 'inStock'
 *   - in_stock_count >= 2 → 'inStockMulti'
 *   - has_last_one → префикс 'lastOne'
 *   - in_stock_count == 0 && alt_version_count > 0 → 'altVersion'
 *   - in_stock_count == 0 && preorder_count > 0 → 'preorder'
 *   - всё ноль → 'none' (HotStockTag вернёт null)
 */
export interface RecordOffersSummary {
  in_stock_count: number;
  preorder_count: number;
  alt_version_count: number;
  min_price_rub: string | null;
  min_price_alt_rub: string | null;
  has_last_one: boolean;
  stores_with_stock: number;
}

export interface RecordOffersFullResponse {
  summary: RecordOffersSummary;
  offers: Offer[];
}

export interface MarketStoreInfo {
  slug: string;
  name: string;
  logo_url?: string | null;
  rating: number;
  in_stock_count: number;
  avg_price_rub?: string | null;
  new_today_count: number;
}

export interface MarketSearchItem {
  record_id: string;
  discogs_id?: string | null;
  artist: string;
  title: string;
  year?: number | null;
  format_type?: string | null;
  cover_image_url?: string | null;
  min_price_rub: string;
  stores_with_stock: number;
  cheapest_store_slug: string;
  first_seen_at: string;
}

export type MarketFormatFilter = 'vinyl' | 'cd' | 'cassette';
export type MarketSortMode = 'price_asc' | 'newest';

/** Одна опция фильтра со счётчиком доступных карточек (data-driven чипы). */
export interface MarketFacetItem {
  key: string;
  label: string;
  count: number;
}

/** Доступные фильтры Маркета со счётчиками (GET /market/facets). Только опции
 * с count > 0 — чтобы не рисовать пустые чипы. */
export interface MarketFacetsResponse {
  genres: MarketFacetItem[];
  features: MarketFacetItem[];
}

/** Полный набор активных фильтров Маркета. format — одиночный, genres/features —
 * мультивыбор (канонические ключи). */
export interface MarketFilters {
  format: MarketFormatFilter | 'all';
  genres: string[];
  features: string[];
}

/** Пустые фильтры — дефолт. Хелпер, чтобы не расходились инициализация/сброс. */
export const EMPTY_MARKET_FILTERS: MarketFilters = {
  format: 'all',
  genres: [],
  features: [],
};

/** Есть ли хоть один активный фильтр — для isSearchActive и кнопки сброса. */
export function hasActiveFilters(f: MarketFilters): boolean {
  return f.format !== 'all' || f.genres.length > 0 || f.features.length > 0;
}

export type OfferSort = 'price' | 'rating';

/**
 * Карточка для карусели «В наличии сейчас» на экране поиска
 * (OFFERS_UX.md Фича 4). Backend дедуплицирует по записи и отдаёт
 * самый дешёвый листинг — один товар = одна обложка в карусели.
 */
export interface MarketCarouselItem {
  record_id: string;
  discogs_id?: string | null;
  artist: string;
  title: string;
  year?: number | null;
  format_type?: string | null;
  cover_image_url?: string | null;
  min_price_rub: string;     // Decimal приходит строкой
  store_slug: string;        // для аналитики «откуда товар»
  first_seen_at: string;     // ISO
}

export interface RecordSearchResult {
  discogs_id: string;
  title: string;
  artist: string;
  label?: string;
  year?: number;
  country?: string;
  cover_image_url?: string;
  thumb_image_url?: string;
  cover_url?: string;
  format_type?: string;
  // Rarity flags — backfilled by backend from local DB / cheap on-the-fly parsing
  is_first_press?: boolean;
  is_canon?: boolean;
  is_collectible?: boolean;
  is_limited?: boolean;
  is_hot?: boolean;
  // Визуальная близость фото к обложке (косинус CLIP, 0..1) при скане по обложке
  match_score?: number | null;
}

export interface RecordSearchResponse {
  results: RecordSearchResult[];
  total: number;
  page: number;
  per_page: number;
}

// ==================== Suggest (автодополнение) ====================

export interface SuggestArtist {
  artist_id: string;
  name: string;
  thumb?: string;
}

export interface SuggestMaster {
  master_id: string;
  title: string;
  artist: string;
  year?: number;
  thumb?: string;
}

export interface SuggestResponse {
  artists: SuggestArtist[];
  masters: SuggestMaster[];
}

// ==================== Cover Scan ====================

export type ScanMode = 'barcode' | 'cover';

export interface CoverScanResponse {
  recognized_artist: string;
  recognized_album: string;
  results: RecordSearchResult[];
  confidence?: number | null;
  low_confidence?: boolean;
}

// ==================== User-submitted records ====================
// Пластинка, которой нет ни в Discogs, ни в Маркете — юзер добавляет вручную.
// См. docs/plans/USER_SUBMITTED_RECORDS.md.

export interface SpotifyAlbumCandidate {
  id: string;
  name: string;
  artist: string;
  year?: number | null;
  cover_url?: string | null;
  image_url?: string | null;
  tracks: TrackItem[];
}

export interface TrackItem {
  position?: string | null;
  title?: string | null;
  duration?: string | null;
}

export type PreflightStatus =
  | 'DUPLICATE'
  | 'LIKELY_DUPLICATE'
  | 'FOUND_IN_DISCOGS'
  | 'ALLOW_CREATE';

export interface PreflightResponse {
  status: PreflightStatus;
  match?: VinylRecord | null;
  discogs_id?: string | null;
  score?: number | null;
}

export interface UserRecordPayload {
  artist: string;
  title: string;
  year?: number | null;
  label?: string | null;
  catalog_number?: string | null;
  country?: string | null;
  format_type?: string | null;
  barcode?: string | null;
  spotify_album_id?: string | null;
  tracklist?: TrackItem[] | null;
  cover_photo_base64?: string | null;
  spine_photo_base64?: string | null;
}

// ==================== Master Releases ====================

export interface MasterSearchResult {
  master_id: string;
  title: string;
  artist: string;
  year?: number;
  main_release_id: string;
  cover_image_url?: string;
  thumb_image_url?: string;
  cover_url?: string;
  release_type?: string;
}

export interface MasterRelease {
  master_id: string;
  title: string;
  artist: string;
  artist_id?: string;
  artist_thumb_image_url?: string;
  year?: number;
  main_release_id: string;
  genres?: string[];
  styles?: string[];
  cover_image_url?: string;
  tracklist?: Track[];
}

export interface MasterVersion {
  release_id: string;
  title: string;
  label?: string;
  catalog_number?: string;
  country?: string;
  year?: number;
  format?: string;
  major_formats?: string[];
  thumb_image_url?: string;
  cover_image_url?: string;
  cover_url?: string;
  is_first_press?: boolean;
  is_canon?: boolean;
  is_collectible?: boolean;
  is_limited?: boolean;
  is_hot?: boolean;
}

export interface MasterSearchResponse {
  results: MasterSearchResult[];
  total: number;
  page: number;
  per_page: number;
  has_more?: boolean;
  next_cursor?: number | null;
}

export interface MasterVersionsResponse {
  results: MasterVersion[];
  total: number;
  page: number;
  per_page: number;
}

// ==================== Collection ====================

export interface Collection {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  sort_order: number;
  items_count: number;
  items?: CollectionItem[];
  created_at: string;
  updated_at: string;
}

export interface CollectionItem {
  id: string;
  collection_id: string;
  record_id: string;
  record: VinylRecord;
  condition?: string;
  notes?: string;
  purchase_price?: number;
  purchase_date?: string;
  estimated_price_rub?: number;
  added_at: string;
}

export interface CollectionStats {
  total_records: number;
  total_estimated_value_min: number | null;
  total_estimated_value_max: number | null;
  total_estimated_value_median: number | null;
  total_estimated_value_rub: number | null;
  usd_rub_rate: number | null;
  ru_markup: number;
  most_expensive: VinylRecord | null;
  most_expensive_price_rub: number | null;
  records_with_price: number;
  records_by_year: Record<number, number>;
  records_by_genre: Record<string, number>;
  oldest_record_year: number | null;
  newest_record_year: number | null;
}

// ==================== Wishlist ====================

export interface Wishlist {
  id: string;
  user_id: string;
  share_token?: string;
  is_public: boolean;
  show_gifter_names?: boolean;
  custom_message?: string;
  items?: WishlistItem[];
  created_at: string;
  updated_at: string;
}

export interface GiftBookingInfo {
  id: string;
  status: 'pending' | 'booked' | 'completed' | 'cancelled';
  booked_at: string;
}

export type WishlistNotifyMode = 'watched' | 'subscribed';
export type WishlistCondition = 'sealed' | 'mint' | 'vg_plus' | 'vg';
export type RadarStatus = 'match' | 'available' | 'alt' | 'absent';

export interface RadarAlt {
  record_id: string;
  title: string | null;
  cover_url: string | null;
  price_rub: number | null;
  year?: number | null;
  country?: string | null;
  format?: string | null;
  buy_url?: string | null;
}

export interface RadarItem {
  wishlist_item_id: string;
  record: VinylRecord;
  status: RadarStatus;
  lowest_price_rub: number | null;
  threshold_rub: number | null;
  conditions: WishlistCondition[] | null;
  accept_alt?: boolean;
  radius: number; // 0..1 доля внутри полосы статуса
  offers_count?: number;
  buy_url?: string | null;
  alt: RadarAlt | null;
}

export interface RadarResponse {
  items: RadarItem[];
  count: number;
  match_count: number;
  limit?: number;
}

export interface RadarEvent {
  status: RadarStatus | string;
  price_rub: number | null;
  store_name: string | null;
  created_at: string;
}

export interface RadarEventsResponse {
  events: RadarEvent[];
}

export interface PriceHistoryPoint {
  date: string; // YYYY-MM-DD
  min_price_rub: number | null;
  listings_count: number;
}

export interface PriceHistoryResponse {
  record_id: string;
  days: number;
  points: PriceHistoryPoint[];
  historical_low_rub: number | null;
}

export interface WishlistItem {
  id: string;
  wishlist_id: string;
  record_id: string;
  record: VinylRecord;
  priority?: number;
  notes?: string;
  is_booked?: boolean;
  gift_booking?: GiftBookingInfo | null;
  added_at: string;
  // Колокольчик: 'subscribed' → мгновенный push при появлении/падении цены.
  notify_mode?: WishlistNotifyMode;
  // Порог «уведомить, когда дешевле X ₽». null/undefined = любое появление.
  price_threshold_rub?: number | null;
  // Принятые грейды состояния для радара. null/undefined = любое.
  conditions?: WishlistCondition[] | null;
  // Юзер принял альт-прессинг как подходящий.
  accept_alt?: boolean;
}

export interface WishlistFolder {
  id: string;
  wishlist_id: string;
  name: string;
  sort_order: number;
  items_count: number;
  items?: WishlistItem[];
  created_at: string;
  updated_at: string;
}

// ==================== API Response ====================

export interface ApiError {
  detail: string;
  status_code?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// ==================== App State ====================

export type CollectionTab = 'collection' | 'wishlist';

// Статус пластинки в системе (взаимоисключающие состояния)
export type RecordStatus =
  | 'not_added'      // Нигде не добавлена
  | 'in_collection'  // В коллекции (может быть несколько копий)
  | 'in_wishlist';   // В вишлисте

export interface SearchFilters {
  artist?: string;
  year?: number;
  year_min?: number;
  year_max?: number;
  label?: string;
  genre?: string;
  format?: string;
  country?: string;
}

// ==================== Release Search (с фильтрами) ====================

export interface ReleaseSearchResult {
  release_id: string;
  title: string;
  artist: string;
  label?: string;
  catalog_number?: string;
  country?: string;
  year?: number;
  format?: string;
  cover_image_url?: string;
  thumb_image_url?: string;
  // Rarity flags — backfilled by backend from local DB / cheap on-the-fly parsing
  is_first_press?: boolean;
  is_canon?: boolean;
  is_collectible?: boolean;
  is_limited?: boolean;
  is_hot?: boolean;
}

export interface ReleaseSearchResponse {
  results: ReleaseSearchResult[];
  total: number;
  page: number;
  per_page: number;
}

// ==================== Artists ====================

export interface ArtistSearchResult {
  artist_id: string;
  name: string;
  cover_image_url?: string;
  thumb_image_url?: string;
}

export interface Artist {
  artist_id: string;
  name: string;
  profile?: string;
  images?: string[];
}

export interface ArtistSearchResponse {
  results: ArtistSearchResult[];
  total: number;
  page: number;
  per_page: number;
}

// ==================== Public Profile ====================

export interface ProfileShareSettings {
  is_active: boolean;
  is_private_profile: boolean;
  show_collection: boolean;
  show_wishlist: boolean;
  custom_title?: string;
  highlight_record_ids?: string[];
  show_record_year: boolean;
  show_record_label: boolean;
  show_record_format: boolean;
  show_record_prices: boolean;
  show_collection_value: boolean;
}

export interface PublicProfileRecord {
  id: string;
  title: string;
  artist: string;
  year?: number;
  label?: string;
  format_type?: string;
  cover_image_url?: string;
  thumb_image_url?: string;
  cover_url?: string;
  estimated_price_median?: number;
  price_currency: string;
  is_booked?: boolean;
  discogs_id?: string | null;
  discogs_master_id?: string | null;
  discogs_want?: number | null;
  discogs_have?: number | null;
  is_first_press?: boolean;
  is_canon?: boolean;
  is_collectible?: boolean;
  is_limited?: boolean;
  is_hot?: boolean;
  /** Дата добавления в коллекцию владельца — для сортировки */
  added_at?: string | null;
}

export interface PublicProfile {
  username: string;
  display_name?: string;
  avatar_url?: string;
  bio?: string;
  custom_title?: string;
  collection_count: number;
  wishlist_count: number;
  collection_value?: number;
  collection_value_rub?: number;
  monthly_value_delta_rub?: number | null;
  followers_count: number;
  show_collection: boolean;
  show_wishlist: boolean;
  show_record_year: boolean;
  show_record_label: boolean;
  show_record_format: boolean;
  show_record_prices: boolean;
  highlights: PublicProfileRecord[];
  collection: PublicProfileRecord[];
  recent_additions: PublicProfileRecord[];
  new_releases: PublicProfileRecord[];
}

export type FollowRequestStatus = 'none' | 'pending' | 'approved' | 'rejected';

export interface UserWithStats {
  id: string;
  username: string;
  display_name?: string;
  avatar_url?: string;
  bio?: string;
  created_at: string;
  followers_count: number;
  following_count: number;
  collection_count: number;
  is_following: boolean;
  /** Статус заявки на подписку от current_user — 'pending' если уже отправил */
  follow_request_status?: FollowRequestStatus;
  /** Профиль приватный — кнопка подписки создаёт заявку, а не follow */
  is_private_profile?: boolean;
}

export interface FollowRequestUser {
  id: string;
  username: string;
  display_name?: string;
  avatar_url?: string;
}

export interface FollowRequestItem {
  id: string;
  requester: FollowRequestUser;
  target: FollowRequestUser;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  resolved_at?: string | null;
}

export interface FollowActionResult {
  status: 'followed' | 'requested' | 'already_following' | 'already_requested';
  follow_request_id?: string | null;
}

export interface WishlistPublicItem {
  id: string;
  record: PublicProfileRecord;
  priority: number;
  notes?: string;
  is_booked: boolean;
  added_at?: string | null;
}

export interface WishlistPublicResponse {
  owner_name: string;
  owner_avatar?: string;
  custom_message?: string;
  items: WishlistPublicItem[];
  total_items: number;
}

// ==================== Gift Booking ====================

export interface GiftBookingCreate {
  wishlist_item_id: string;
  gifter_name: string;
  gifter_email: string;
  gifter_phone?: string;
  gifter_message?: string;
}

export interface GiftBookingResponse {
  id: string;
  wishlist_item_id: string;
  gifter_name: string;
  gifter_email: string;
  gifter_phone?: string;
  gifter_message?: string;
  status: 'pending' | 'booked' | 'completed' | 'cancelled';
  cancel_token: string;
  booked_at: string;
  record: PublicProfileRecord;
}

export interface GiftRecipientInfo {
  username: string;
  display_name?: string;
  avatar_url?: string;
}

export interface GiftGivenItem {
  id: string;
  status: 'booked' | 'completed';
  cancel_token: string;
  booked_at: string;
  completed_at?: string;
  record: PublicProfileRecord;
  for_user: GiftRecipientInfo;
}

export interface GiftReceivedItem {
  id: string;
  wishlist_item_id?: string | null;
  status: 'pending' | 'booked' | 'completed' | 'cancelled';
  booked_at: string;
  completed_at?: string;
  cancelled_at?: string;
  record: PublicProfileRecord;
}

// ==================== Notifications ====================

export interface NotificationSettings {
  notify_new_follower: boolean;
  notify_gift_booked: boolean;
  notify_gift_confirmed: boolean;
  notify_app_updates: boolean;
  notify_follow_request: boolean;
  notify_wishlist_in_stock: boolean;
  notify_achievement: boolean;
  notify_milestone: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string | null;  // "HH:MM"
  quiet_hours_end: string | null;    // "HH:MM"
}

export type NotificationType =
  | 'follow_request'
  | 'message_request'
  | 'new_follower'
  | 'gift_booked'
  | 'gift_confirmed'
  | 'wishlist_in_stock'
  | 'wishlist_in_stock_alt'
  | 'wishlist_price_drop'
  | 'achievement_unlocked'
  | 'milestone_unlocked'
  | 'digest_wishlist_in_stock';

export interface NotificationActor {
  id: string;
  username: string;
  display_name?: string | null;
  avatar_url?: string | null;
}

/**
 * data-полезная нагрузка для wishlist_in_stock после bump'а:
 * stores[] — все магазины, у которых пластинка появилась за окно дедупа,
 * store_count и min_price_rub пересчитываются на каждый bump.
 */
export interface WishlistInStockStore {
  slug?: string | null;
  name?: string | null;
  price_rub?: number | null;
  url?: string | null;
  listing_id?: string | null;
}

export interface NotificationItem {
  id: string;
  type: NotificationType;
  /** Ключ дедупликации одной «нити» (один record / одна ачивка). */
  dedup_key?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  data: Record<string, unknown>;
  created_at: string;
  /** Когда событие повторилось последний раз (на bump поднимается). */
  bumped_at: string;
  /** Сколько раз было свёрнуто. 1 = одиночное. */
  occurrences: number;
  /** Если задано — следующие алерты по тому же dedup_key не создаются до этой даты. */
  snoozed_until?: string | null;
  read_at?: string | null;
  actor?: NotificationActor | null;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  unread_count: number;
  next_cursor?: string | null;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export type SocialFeedType =
  | 'collection_add'
  | 'wishlist_add'
  | 'gift_completed'
  | 'friend_achievement'
  | 'friend_new_following';

export interface SocialFeedRecord {
  id: string;
  title: string;
  artist?: string | null;
  cover_url?: string | null;
}

export interface SocialFeedItem {
  type: SocialFeedType;
  actor: NotificationActor;
  created_at: string;
  record?: SocialFeedRecord | null;
  target_user?: NotificationActor | null;
  payload: Record<string, unknown>;
}

export interface SocialFeedResponse {
  items: SocialFeedItem[];
  next_cursor?: string | null;
}

// ==================== Social ====================

export interface UserPublic {
  id: string;
  username: string;
  display_name?: string;
  avatar_url?: string;
  bio?: string;
  created_at: string;
}

export interface FeedItem {
  type: 'collection_add';
  user: {
    id: string;
    username: string;
    display_name?: string;
    avatar_url?: string;
  };
  collection: {
    id: string;
    name: string;
  };
  record: {
    id: string;
    title: string;
    artist: string;
    year?: number;
    cover_image_url?: string;
  };
  added_at: string;
}

// ==================== Achievements ====================

export type AchievementTierKey = 'simple' | 'notable' | 'rare' | 'epic' | 'legend';
export type AchievementSeriesKey = 'foundation' | 'scale' | 'gifts' | 'community';

export interface AchievementTierInfo {
  key: AchievementTierKey;
  label_ru: string;
  color_hex: string;
}

export interface AchievementItem {
  code: string;
  /** null если ачивка скрытая и ещё не открыта (рендерим как «🥚 Пасхалка») */
  title_ru: string | null;
  description_ru: string | null;
  /** прошедшее время, показываем когда is_unlocked */
  description_done_ru?: string | null;
  flavor_ru?: string | null;
  icon_slug?: string | null;
  series: AchievementSeriesKey | 'random';
  tier: AchievementTierInfo;
  is_hidden: boolean;
  is_meta: boolean;
  is_unlocked: boolean;
  unlocked_at: string | null;
  progress: number;
  progress_target: number;
}

export interface AchievementSeriesItem {
  key: AchievementSeriesKey;
  title_ru: string;
  description_ru: string;
  icon_emoji: string;
  total: number;
  unlocked: number;
  items: AchievementItem[];
}

export interface MyAchievementsResponse {
  total: number;
  unlocked: number;
  random_unlocked: number;
  series: AchievementSeriesItem[];
}

export interface CatalogResponse {
  series: AchievementSeriesItem[];
  random_count: number;
}

export interface RandomUnlockedResponse {
  items: AchievementItem[];
}

export interface AchievementStats {
  code: string;
  total_users: number;
  unlocked_users: number;
  unlocked_pct: number;
}

// ==================== Remote config ====================

/**
 * Ответ GET /api/config — force-update gate и kill-switch фич.
 * См. Backend/app/api/app_config.py, docs/plans/APPSTORE_LAUNCH_PLAN.md §4.2.
 */
export interface AppConfig {
  min_supported_version: string;
  store_url: string;
  update_message: string;
  flags: Record<string, boolean>;
}
