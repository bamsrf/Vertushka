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
  /**
   * Новый аккаунт. Шлётся из ЛЮБОГО пути регистрации, включая OAuth.
   *
   * `method` обязателен по той же причине, что и у [login]: раньше register
   * уходил только с email-формы, и приток через Apple/Google/Discogs не было
   * видно вообще — цифра занижалась молча, а второй шаг воронки активации
   * нечем было разбить. OAuth-эндпоинты и создают аккаунт, и логинят
   * существующий, поэтому «первый ли это вход» знает только бэкенд: он
   * отдаёт `is_new_user` в ответе с токенами.
   */
  register: (method: 'email' | 'apple' | 'google' | 'discogs') =>
    track('register', { method }),
  login: (method: 'email' | 'apple' | 'google' | 'discogs') => track('login', { method }),
  logout: () => {
    track('logout');
    provider?.reset();
  },
  /**
   * Связать анонимную сессию с аккаунтом и пометить, свой это человек или нет.
   *
   * `is_staff` шлём ВСЕГДА, включая false. Свойство, которое есть только у
   * части пользователей, в Amplitude фильтруется трёхзначно («true», «false»,
   * «не задано»), и когорта «не команда» тихо теряла бы всех, у кого поля нет.
   *
   * Вычитать в чартах нужно когортой, а не фильтром по свойству события:
   * до логина `identify` ещё не звучал, и события онбординга уходят без метки.
   * Когорта работает на уровне пользователя и накрывает его историю целиком —
   * Amplitude склеивает анонимное устройство с userId в момент identify.
   */
  identify: (params: { userId: string; isStaff?: boolean }) =>
    provider?.identify(params.userId, { is_staff: params.isStaff === true }),

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

  /**
   * Пластинка добавлена в коллекцию — главное действие продукта.
   *
   * Вызывается ИЗ СТОРА, а не с экранов. Путей добавления шесть (лента,
   * карточка релиза, поиск, ручное добавление, добавление с фото, сканер), и
   * пока событие висело на экранах, оно стояло ровно на одном из них: за две
   * недели живого приложения `add_to_collection` не пришёл ни разу. Стор —
   * единственное место, через которое проходят все шесть.
   *
   * `discogs_id` опционален: добавление по record_id (store-native и
   * user-submitted записи) его не знает. Пропущенное свойство честнее
   * подставленного мусора — см. [viewRecord].
   */
  addToCollection: (discogsId?: string | null) =>
    track('add_to_collection', discogsId ? { discogs_id: discogsId } : {}),
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

  // --- Подарки: жизненный цикл брони ---
  /**
   * Подарок дошёл до получателя — финал воронки book_gift → gift_completed.
   *
   * `via` разделяет два пути: ручная отметка «Получено!» в карточке подарка и
   * автоматическое подтверждение через модалку матчинга при сканировании. Без
   * этого свойства нельзя понять, окупается ли матчинг или люди всё равно
   * доходят до карточки руками.
   */
  giftCompleted: (params: { via: 'gift_screen' | 'match_modal'; discogs_id?: string | null }) =>
    track('gift_completed', {
      via: params.via,
      ...(params.discogs_id ? { discogs_id: params.discogs_id } : {}),
    }),

  /**
   * Даритель сам отменил бронь.
   *
   * Молчаливое истечение 60-дневной брони сюда НЕ попадает: срок сгорает на
   * сервере, приложение об этом не узнаёт. Долю протухших броней считать по
   * бэкенду — в воронке они будут выглядеть просто как недошедшие.
   */
  giftBookingCancelled: (discogsId?: string | null) =>
    track('gift_booking_cancelled', {
      by: 'gifter',
      ...(discogsId ? { discogs_id: discogsId } : {}),
    }),

  // --- Подарки: точность матчинга ---
  /**
   * Показали вопрос «вам её подарили?» — знаменатель точности алгоритма.
   *
   * `match_kind` обязателен: exact-совпадение и fuzzy/master — это разные по
   * надёжности гипотезы, и мерить их одной цифрой бессмысленно. Именно доля
   * подтверждений по каждому виду отвечает, можно ли доверять матчингу
   * настолько, чтобы однажды перестать спрашивать пользователя.
   *
   * gift_match_confirmed идёт в паре с gift_completed(via: 'match_modal') —
   * это не дубль: первое про качество алгоритма, второе про воронку подарка.
   */
  giftMatchShown: (matchKind: string) => track('gift_match_shown', { match_kind: matchKind }),
  giftMatchConfirmed: (matchKind: string) =>
    track('gift_match_confirmed', { match_kind: matchKind }),
  giftMatchDismissed: (matchKind: string) =>
    track('gift_match_dismissed', { match_kind: matchKind }),

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
   *
   * `store_slug` и `price_rub` тоже опциональны — шторка истории цен на радаре
   * несёт только id листинга. Пропущенное свойство честнее подставленного нуля:
   * ноль осел бы в средних чеках и тихо занизил их, а отсутствие поля видно
   * в фильтре. Если разбивка радара по магазинам понадобится — это правка
   * бэкенда, в RadarItem сейчас нет store_slug.
   */
  offerClick: (params: {
    listing_id: string;
    source: ClickSource;
    store_slug?: string;
    price_rub?: number;
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

  // --- Онбординг ---
  /**
   * Выбор на развилке «с чего начнём» в конце welcome-карусели.
   *
   * Главный срез активации: у `discogs_import` и `scan` принципиально разные
   * первые пять минут, и ретеншен по ним надо смотреть отдельно (см.
   * docs/plans/product/AMPLITUDE_DASHBOARDS.md §2).
   */
  onboardingStartChoice: (choice: 'scan' | 'discogs_import' | 'search' | 'explore') =>
    track('onboarding_start_choice', { choice }),

  /**
   * Показ контекстной подсказки. Вместе с onboarding_hint_action показывает,
   * какие формулировки реально доводят до фичи, а какие просто закрывают.
   */
  onboardingHintShown: (key: string) => track('onboarding_hint_shown', { key }),
  /** Тап по действию в подсказке («Открыть Радар», «Создать папку»). */
  onboardingHintAction: (key: string) => track('onboarding_hint_action', { key }),
  /** Тап по невыполненному пункту чеклиста «Первые шаги». */
  onboardingStepTap: (key: string) => track('onboarding_step_tap', { key }),
  /**
   * Тур по карточке релиза. Состав шагов зависит от релиза (у одного нет
   * истории цен, у другого — других версий), поэтому длина пишется явно:
   * без неё «дошёл до 3-го» ничего не значит.
   */
  recordTourStarted: (steps: number) => track('record_tour_started', { steps }),
  /**
   * Чем кончился тур. reason='done' — долистал до конца, 'skip' — закрыл
   * крестиком или ушёл с экрана. Пара (reached, steps) показывает, на каком
   * именно блоке люди перестают читать.
   */
  recordTourFinished: (reason: 'done' | 'skip', reached: number, steps: number) =>
    track('record_tour_finished', { reason, reached, steps }),
  /**
   * Пункт чеклиста закрылся. Отличается от step_tap: тап — это намерение,
   * а done — факт. Их разница по каждому шагу и показывает, где человек
   * пошёл делать и не дошёл.
   */
  onboardingStepDone: (key: string) => track('onboarding_step_done', { key }),
};
