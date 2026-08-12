/**
 * Аналитика — провайдер-агностик обёртка.
 * Провайдер по умолчанию — Amplitude, инициализируется в _layout.tsx через initAmplitude().
 * Импорт нативного SDK ленивый: в Expo Go модуль просто отсутствует и аналитика становится no-op.
 */

import type { ClickSource } from './types';

type AnalyticsProvider = {
  track: (event: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string, properties?: Record<string, unknown>) => void;
  reset: () => void;
};

let provider: AnalyticsProvider | null = null;

export function setAnalyticsProvider(p: AnalyticsProvider) {
  provider = p;
}

export async function initAmplitude(apiKey: string): Promise<void> {
  if (!apiKey) return;
  let Amplitude: any;
  try {
    Amplitude = require('@amplitude/analytics-react-native');
  } catch {
    return; // Expo Go или модуль не собран — пропускаем
  }
  await Amplitude.init(apiKey, undefined, {
    // Проект заведён в EU-регионе. Без serverZone SDK шлёт в US-endpoint,
    // и события не появляются в дашборде вообще — без единой ошибки в логах.
    serverZone: 'EU',
    trackingOptions: { ipAddress: false, adid: false, dma: false, carrier: false },
  }).promise;
  setAnalyticsProvider({
    track: (event, properties) => {
      Amplitude.track(event, properties);
    },
    identify: (userId, properties) => {
      Amplitude.setUserId(userId);
      if (properties) {
        const id = new Amplitude.Identify();
        for (const [k, v] of Object.entries(properties)) {
          id.set(k, v as never);
        }
        Amplitude.identify(id);
      }
    },
    reset: () => {
      Amplitude.reset();
    },
  });
}

function track(event: string, properties?: Record<string, unknown>) {
  const delivered = provider !== null;
  provider?.track(event, properties);
  if (__DEV__) {
    // Лог обязан отражать судьбу события, а не факт вызова. Пока провайдер не
    // поднят (нет ключа, Expo Go, init ещё в полёте), track() молча всё
    // выбрасывает — и лог без этой пометки при отладке «почему в Amplitude
    // пусто» врёт в самый неподходящий момент.
    console.log(`[Analytics]${delivered ? '' : ' (dropped)'} ${event}`, properties ?? '');
  }
}

export const analytics = {
  // --- Жизненный цикл ---
  /** Холодный старт. Знаменатель всех воронок и основа для retention. */
  appOpened: () => track('app_opened'),

  // --- Auth ---
  register: () => track('register'),
  login: (method: 'email' | 'apple' | 'google' | 'discogs') => track('login', { method }),
  logout: () => {
    track('logout');
    provider?.reset();
  },
  identify: (userId: string) => provider?.identify(userId),

  // --- Scanner ---
  scanBarcode: (found: boolean) => track('scan_barcode', { found }),
  scanCover: (found: boolean) => track('scan_cover', { found }),

  // --- Collection & Wishlist ---
  /**
   * Импорт коллекции из Discogs — activation-метрика №1.
   *
   * Главный барьер первого использования: «надо руками добавить 500 пластинок».
   * Кто прошёл импорт — получил ценность сразу, и его retention надо смотреть
   * отдельно от тех, кто добавлял вручную.
   */
  importCompleted: (params: { imported: number; skipped: number; total: number }) =>
    track('import_completed', params),

  addToCollection: (discogsId: string) => track('add_to_collection', { discogs_id: discogsId }),
  /** discogs_id опционален по той же причине, что и в [viewRecord]. */
  removeFromCollection: (discogsId?: string | null) =>
    track('remove_from_collection', discogsId ? { discogs_id: discogsId } : {}),
  addToWishlist: (discogsId: string) => track('add_to_wishlist', { discogs_id: discogsId }),

  // --- Search ---
  /**
   * Сырой текст запроса НЕ отправляем.
   *
   * Поисковые запросы — это «Search History» в терминах App Privacy: отдельная
   * категория, которую пришлось бы декларировать в анкете ASC и в
   * privacyManifests. Для воронки «искал → нашёл → добавил» достаточно длины
   * запроса и числа результатов, а лишняя категория сбора данных не нужна ни
   * нам, ни пользователю.
   */
  search: (query: string, resultsCount?: number) =>
    track('search', {
      query_length: query.trim().length,
      ...(resultsCount !== undefined && { results_count: resultsCount }),
    }),

  // --- Content ---
  /**
   * discogs_id опционален: у store-native и добавленных вручную пластинок его
   * нет. Просмотр всё равно был — событие шлём, а свойство опускаем, иначе во
   * внутренний id под именем discogs_id утечёт мусор и сегменты по нему
   * перестанут сходиться.
   */
  viewRecord: (discogsId?: string | null) =>
    track('view_record', discogsId ? { discogs_id: discogsId } : {}),

  /**
   * Просмотр мастер-релиза — самый частый переход из выдачи поиска.
   *
   * Событие отдельное от view_record намеренно: мастер и релиз — разные
   * сущности. У мастера сотня версий и нет ни цены, ни наличия; они есть
   * только у конкретного релиза. Смешав их в одном событии, мы бы уже не
   * смогли разделить «посмотрел альбом вообще» и «дошёл до конкретного
   * прессинга, который можно купить» — а это два разных намерения.
   */
  viewMaster: (masterId: string) => track('view_master', { master_id: masterId }),
  viewArtist: (artistId: string) => track('view_artist', { artist_id: artistId }),

  // --- Social ---
  followUser: (targetUserId: string) => track('follow_user', { target_user_id: targetUserId }),
  bookGift: (recordId: string) => track('book_gift', { record_id: recordId }),

  // --- Offers (магазины) ---
  viewOffers: (discogsId: string, count: number) =>
    track('view_offers', { discogs_id: discogsId, count }),
  /**
   * Уход в магазин — последний шаг воронки и главная монетизационная метрика.
   *
   * `source` обязателен: без него все переходы сливаются в одно число, и нельзя
   * ответить, что именно работает — Маркет, карточки пластинок или ценники в
   * вишлисте. Тот же source уезжает в `offer_clicks.source` на бэкенде, чтобы
   * отчёт магазину и продуктовая воронка считались по одной разбивке.
   *
   * `discogs_id` опционален: свайп-ценник знает листинг, но не запись.
   */
  offerClick: (params: {
    listing_id: string;
    store_slug: string;
    price_rub: number;
    source: ClickSource;
    discogs_id?: string;
  }) => track('offer_click', params),

  // --- Market (воронка до перехода в магазин) ---
  /** Открыли витрину Маркета. Знаменатель для market_record_open. */
  viewMarket: () => track('view_market'),
  /** Открыли страницу конкретного магазина из Маркета. */
  viewMarketStore: (storeSlug: string) => track('view_market_store', { store_slug: storeSlug }),
  /**
   * Тап на пластинку внутри Маркета → карточка записи.
   *
   * Промежуточный шаг, без которого воронка обрывается: раньше был виден только
   * финальный offer_click, и понять, теряем мы людей на витрине или уже на
   * карточке, было невозможно.
   */
  marketRecordOpen: (params: { record_ref: string; from: 'market' | 'market_store' }) =>
    track('market_record_open', params),
};
