/**
 * Просьба оценить приложение в сторе.
 *
 * Окно рисует система (`SKStoreReviewController` на iOS, In-App Review на
 * Android) — ни текста, ни кнопок, ни дизайна у нас тут нет и быть не может:
 * гайдлайн App Store 1.1.7 требует системный API и запрещает самодельные
 * пре-промпты вроде «Нравится? → Да, в стор / Нет, напишите нам». Поэтому весь
 * продуктовый выбор здесь ровно один — КОГДА позвать, и он целиком в этом файле.
 *
 * Почему так строго с показами. Apple показывает окно максимум 3 раза за 365
 * дней на устройство, юзер мог выключить его в Настройках вообще, а колбэка о
 * результате нет: `requestReview()` возвращает void и врёт молчанием — мы не
 * знаем ни показалось ли окно, ни поставили ли звезду. Показы невозвратные,
 * значит тратить их можно только на пик, а «не знаю» всегда трактуем как
 * «не просить» (fail-closed) — в отличие от remoteConfig, где fail-open.
 *
 * Гейт двухчастный: аккаунт созрел (все пороги ниже) И момент эмоциональный
 * (за это отвечает вызывающая сторона — см. AchievementUnlockHost).
 *
 * Флаг `review_prompt` в /api/config — рубильник без релиза: если окно полезет
 * не там, его гасят одним PUT в админке.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { analytics } from './analytics';
import { useRemoteConfigStore } from './remoteConfig';
import { useAuthStore, useCollectionStore } from './store';

/** Момент, из которого пришла просьба. Уезжает в аналитику. */
export type ReviewTrigger = 'achievement' | 'scan' | 'gift';

const LAUNCH_DAYS_KEY = 'review:launch-days';
const ASKS_KEY = 'review:asks';

const DAY_MS = 24 * 60 * 60 * 1000;

/** Аккаунту меньше недели — человек ещё не понял, нравится ли ему. */
const MIN_ACCOUNT_AGE_DAYS = 7;
/**
 * Три РАЗНЫХ дня с запуском, а не три запуска. Три запуска бывают за один
 * вечер знакомства с приложением и не значат ничего; три дня — это привычка.
 */
const MIN_LAUNCH_DAYS = 3;
/** Ниже этого коллекция ещё не «своя»: оценивать нечего. */
const MIN_COLLECTION_SIZE = 10;
/** Пауза между нашими попытками. Внутри лимита Apple (3/год) с запасом. */
const MIN_DAYS_BETWEEN_ASKS = 90;
/** Свой потолок ниже Apple'вского: два отказа за год — это уже ответ. */
const MAX_ASKS_PER_YEAR = 2;
/**
 * Тишина после холодного старта. Окно, прилетевшее в первые секунды, накрывает
 * экран раньше, чем человек успел посмотреть, куда попал, — и читается как
 * «приложение просит, ещё ничего не дав».
 */
const QUIET_AFTER_LAUNCH_MS = 15_000;

/** Модуль грузится вместе с бандлом — это и есть момент старта приложения. */
const launchedAt = Date.now();

/**
 * В этой сессии что-то сломалось. Просить оценку после краша — лучший способ
 * получить одну звезду. Флаг живёт только в памяти: новая сессия — чистый лист.
 */
let sessionSpoiled = false;

/**
 * Просьба уже в полёте. Гейты асинхронные (AsyncStorage), и два триггера,
 * сошедшихся в одном кадре, успели бы оба пройти проверку потолка до того, как
 * первый из них его увеличит, — и окно запрашивалось бы дважды.
 */
let asking = false;

type StoreReviewModule = typeof import('expo-store-review');

let storeReview: StoreReviewModule | null = null;

/**
 * Ленивый импорт нативного модуля — как в lib/analytics.ts: в Expo Go и на web
 * его нет, и всё обязано тихо стать no-op, а не уронить экран.
 */
function loadStoreReview(): StoreReviewModule | null {
  if (storeReview) return storeReview;
  try {
    storeReview = require('expo-store-review');
  } catch {
    return null;
  }
  return storeReview;
}

/** Пометить сессию испорченной: краш экрана, фатальная ошибка. */
export function noteBadExperience(): void {
  sessionSpoiled = true;
}

/**
 * Сегодняшняя дата по МЕСТНОМУ времени, YYYY-MM-DD.
 *
 * Не `toISOString()`: он отдаёт UTC, и у человека в UTC+3 «новый день» для
 * счётчика наступал бы в три часа ночи — вечерний и следующий утренний запуск
 * склеивались бы в один день, а ночной раскалывался бы надвое.
 */
function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

interface LaunchDays {
  /** Сколько разных календарных дней приложение открывали. */
  count: number;
  /** Последний засчитанный день, YYYY-MM-DD. */
  last: string;
}

async function readJson<T>(key: string): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/**
 * Засчитать день запуска. Зовётся один раз на холодном старте из _layout.
 * Повторный вызов в тот же день ничего не меняет — счётчик считает дни.
 */
export async function noteAppLaunch(): Promise<void> {
  const day = today();
  const stored = await readJson<LaunchDays>(LAUNCH_DAYS_KEY);
  if (stored?.last === day) return;
  const next: LaunchDays = { count: (stored?.count ?? 0) + 1, last: day };
  try {
    await AsyncStorage.setItem(LAUNCH_DAYS_KEY, JSON.stringify(next));
  } catch {
    // Не смогли записать — просто не дозреем до просьбы. Это безопасный исход.
  }
}

/** Метки времени наших попыток за последний год, старые отброшены. */
async function readRecentAsks(): Promise<number[]> {
  const stored = await readJson<number[]>(ASKS_KEY);
  if (!Array.isArray(stored)) return [];
  const yearAgo = Date.now() - 365 * DAY_MS;
  return stored.filter((t) => typeof t === 'number' && t > yearAgo);
}

async function recordAsk(recent: number[]): Promise<void> {
  try {
    await AsyncStorage.setItem(ASKS_KEY, JSON.stringify([...recent, Date.now()]));
  } catch {
    // Запись не удалась — потолок перестанет работать. Лучше перестраховаться
    // и считать попытку состоявшейся, чем просить снова на следующей ачивке.
    sessionSpoiled = true;
  }
}

/**
 * Размер коллекции без единого запроса — из того, что стор уже загрузил.
 * `null` = не знаем; на этом гейте это значит «не просим».
 */
function collectionSize(): number | null {
  const state = useCollectionStore.getState();
  // ownedRecordIds — полный сет владения (все коллекции и папки), в отличие от
  // collectionItems, где лежит только первая страница.
  if (state.ownedIdsLoaded) return state.ownedRecordIds.size;
  if (state.stats) return state.stats.total_records;
  return null;
}

function accountAgeDays(): number | null {
  const createdAt = useAuthStore.getState().user?.created_at;
  if (!createdAt) return null;
  const ms = Date.parse(createdAt);
  if (Number.isNaN(ms)) return null;
  return (Date.now() - ms) / DAY_MS;
}

/**
 * Почему не спросили — строкой. `null` = все условия сошлись.
 *
 * Причина существует ради `__DEV__`-лога: гейтов девять, срабатывает обычно
 * один, и без имени виновника отладка превращается в расстановку console.log
 * по всему файлу. В прод-сборке строка никуда не уходит.
 */
async function findBlocker(): Promise<string | null> {
  if (sessionSpoiled) return 'сессия испорчена (краш или неудачная запись)';
  if (Date.now() - launchedAt < QUIET_AFTER_LAUNCH_MS) return 'слишком рано после старта';
  if (!useRemoteConfigStore.getState().isEnabled('review_prompt')) return 'флаг review_prompt выключен';
  if (!useAuthStore.getState().isAuthenticated) return 'не авторизован';

  const age = accountAgeDays();
  if (age === null) return 'возраст аккаунта неизвестен';
  if (age < MIN_ACCOUNT_AGE_DAYS) return `аккаунту ${Math.floor(age)} дн. из ${MIN_ACCOUNT_AGE_DAYS}`;

  const size = collectionSize();
  if (size === null) return 'размер коллекции неизвестен';
  if (size < MIN_COLLECTION_SIZE) return `в коллекции ${size} из ${MIN_COLLECTION_SIZE}`;

  const launchDays = await readJson<LaunchDays>(LAUNCH_DAYS_KEY);
  const days = launchDays?.count ?? 0;
  if (days < MIN_LAUNCH_DAYS) return `дней с запуском ${days} из ${MIN_LAUNCH_DAYS}`;

  const recent = await readRecentAsks();
  if (recent.length >= MAX_ASKS_PER_YEAR) return `уже просили ${recent.length} раза за год`;
  const lastAsk = recent[recent.length - 1];
  if (lastAsk && Date.now() - lastAsk < MIN_DAYS_BETWEEN_ASKS * DAY_MS) {
    return `прошлая просьба была ${Math.floor((Date.now() - lastAsk) / DAY_MS)} дн. назад`;
  }
  return null;
}

/**
 * Позвать системное окно оценки, если сошлись все условия.
 *
 * Молчит почти всегда — это норма, а не ошибка. Ничего не возвращает и никогда
 * не бросает: вызывающий момент (закрытие ачивки, удачный скан) не должен ни
 * ждать результата, ни знать о существовании гейтов.
 */
export async function maybeAskForReview(trigger: ReviewTrigger): Promise<void> {
  if (asking) return;
  asking = true;
  try {
    const blocker = await findBlocker();
    if (blocker) {
      if (__DEV__) console.log(`[Review] ${trigger} — не просим: ${blocker}`);
      return;
    }

    // Не `module`: Metro оборачивает файл в функцию с параметром `module`,
    // и локальная переменная с тем же именем его затеняет.
    const sdk = loadStoreReview();
    if (!sdk) {
      if (__DEV__) console.log(`[Review] ${trigger} — нет нативного модуля (Expo Go?)`);
      return;
    }
    if (!(await sdk.isAvailableAsync())) {
      if (__DEV__) console.log(`[Review] ${trigger} — платформа не умеет in-app review`);
      return;
    }

    // Порядок важен: сначала запись, потом показ. Между ними нельзя падать —
    // иначе попытка не засчитается и следующая ачивка позовёт окно снова.
    const recent = await readRecentAsks();
    await recordAsk(recent);
    await sdk.requestReview();

    // Результат нам не вернут (см. шапку файла) — событие фиксирует ПОПЫТКУ.
    // Успех меряется косвенно: число попыток против прироста оценок в ASC.
    analytics.ratePromptRequested({
      trigger,
      collection_size: collectionSize() ?? 0,
      account_age_days: Math.floor(accountAgeDays() ?? 0),
    });
    if (__DEV__) console.log(`[Review] ${trigger} — окно запрошено`);
  } catch {
    // Просьба оценить — не та функциональность, из-за которой что-то падает.
  } finally {
    asking = false;
  }
}
