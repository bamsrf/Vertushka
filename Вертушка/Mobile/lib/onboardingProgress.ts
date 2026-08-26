/**
 * «Первые шаги» — чеклист новичка в коллекции.
 *
 * Ключевое решение: прогресс ВЫВОДИТСЯ из реальных данных, а не копится в
 * отдельных флагах. Поэтому человек, импортировавший 200 пластинок из Discogs,
 * сразу видит закрытый первый пункт, а не фальшивый ноль. Исключение — факт
 * отправки ссылки на профиль: системный share-лист не сообщает, чем всё
 * кончилось, поэтому ловим намерение. Хранится он на сервере
 * (profile_shares.shared_at, оттуда же растёт ачивка A4 «Распахнул»), а
 * локальный флаг остаётся кэшем на случай оффлайна.
 *
 * ВАЖНО про реактивность. Пункты читаются из zustand-сторов и обновляются
 * сами. Флаг «поделился» когда-то жил в useState, заполнялся один раз в
 * useEffect — и шаг не закрывался, пока карточку не перемонтирует переключение
 * вкладки. Поэтому всё состояние чеклиста тоже лежит в сторе: любой источник
 * правды, от которого зависит пункт, обязан быть реактивным.
 *
 * Обратная связь. Шаги закрываются на других экранах (профиль, поиск,
 * настройки Discogs), где карточки не видно. Поэтому есть глобальный
 * наблюдатель initFirstStepsWatcher: он ловит переход пункта в «сделано» и
 * показывает тост там, где человек находится в этот момент.
 *
 * Карточка не блокирует и не перекрывает интерфейс: она живёт в потоке
 * ScrollableHeader коллекции и уезжает вместе с блоком папок.
 */
import { useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { useAuthStore, useCollectionStore } from './store';
import type { SpotlightKey } from './coachSpotlight';
import { api } from './api';
import { detectAchievementUnlocks } from './achievementsBus';
import { analytics } from './analytics';
import { toast } from './toast';
import type { User } from './types';

export type FirstStepKey =
  | 'first-record'
  | 'discogs-import'
  | 'profile'
  | 'wishlist'
  | 'folders'
  | 'share';

export interface FirstStep {
  key: FirstStepKey;
  label: string;
  /**
   * Зачем этот шаг. Показывается только у ближайшего невыполненного пункта —
   * иначе карточка разрастается в стену текста, а объяснение нужно ровно
   * тому шагу, который человек делает следующим.
   */
  why: string;
  /** Куда ведёт тап по невыполненному пункту. */
  route: string;
  /** Что подсветить на целевом экране — если словами место не объяснить. */
  spotlight?: SpotlightKey;
  /**
   * Предложение, а не задание. Такой пункт не входит в счётчик и в прогресс-бар,
   * не может стать «следующим шагом» и не мешает чеклисту закрыться целиком.
   *
   * Нужно ровно для Discogs: аккаунт там есть далеко не у всех, и пункт в общем
   * знаменателе превращал «подключи чужой сервис» в условие, без которого
   * онбординг не считается пройденным.
   */
  optional?: boolean;
  done: boolean;
}

const dismissKey = (userId: string) => `@vertushka:first_steps_dismissed:${userId}`;
const sharedKey = (userId: string) => `@vertushka:first_steps_shared:${userId}`;
const opensKey = (userId: string) => `@vertushka:first_steps_opens:${userId}`;

/** После стольких ЗАПУСКОВ приложения карточка по умолчанию свёрнута в строку. */
const EXPANDED_OPENS = 3;

/**
 * Порог, до которого предлагаем импорт из Discogs. Выше него человек уже
 * набивает коллекцию своим способом, и предложение «перенести всё разом»
 * выглядит как непрошеный совет.
 */
const DISCOGS_OFFER_BELOW = 10;

// ==================== Стор флагов ====================

interface FirstStepsFlagsState {
  /** Для какого аккаунта прочитаны флаги — защита от гонки при смене юзера. */
  hydratedFor: string | null;
  loaded: boolean;
  /**
   * Сетевые источники правды (статус Discogs, факт шаринга) уже ответили.
   * Отдельно от loaded: карточку рисуем сразу по локальным флагам, а вот
   * базовую линию наблюдателя до ответа сети снимать нельзя — шаг, который
   * закрылся месяц назад, приехал бы тостом «Шаг пройден» на ровном месте.
   */
  netSettled: boolean;
  dismissed: boolean;
  shared: boolean;
  expanded: boolean;
  /**
   * null — статус Discogs ещё не known (или запрос упал). В этом случае шаг
   * не показываем вовсе: лучше промолчать, чем предложить подключить уже
   * подключённое.
   */
  discogsConnected: boolean | null;
  /**
   * Счётчик запусков инкрементится один раз за сессию, а не на каждый маунт:
   * карточка размонтируется при уходе на «Вишлист» и монтируется обратно, и
   * без флага три переключения таба выглядели бы как три запуска.
   */
  opensCounted: boolean;

  hydrate: (userId: string) => Promise<void>;
  markShared: (userId: string) => Promise<void>;
  syncShared: (userId: string) => Promise<void>;
  dismiss: (userId: string) => void;
  toggleExpanded: () => void;
}

const useFirstStepsFlags = create<FirstStepsFlagsState>((set, get) => ({
  hydratedFor: null,
  loaded: false,
  netSettled: false,
  dismissed: true,
  shared: false,
  expanded: true,
  discogsConnected: null,
  opensCounted: false,

  hydrate: async (userId) => {
    if (get().hydratedFor === userId) return;
    // Занимаем слот сразу, чтобы параллельные маунты не читали хранилище дважды.
    // Заодно обнуляем данные прошлого аккаунта: иначе до конца чтения чеклист
    // показывал бы чужие галочки, а наблюдатель принял бы их за свежие.
    set({
      hydratedFor: userId,
      loaded: false,
      netSettled: false,
      shared: false,
      dismissed: true,
      discogsConnected: null,
    });
    try {
      const [[, isDismissed], [, isShared], [, opensRaw]] = await AsyncStorage.multiGet([
        dismissKey(userId),
        sharedKey(userId),
        opensKey(userId),
      ]);

      const stored = Number(opensRaw ?? '0');
      const alreadyCounted = get().opensCounted;
      const opens = alreadyCounted ? stored : stored + 1;
      if (!alreadyCounted) {
        void AsyncStorage.setItem(opensKey(userId), String(opens));
      }

      set({
        loaded: true,
        opensCounted: true,
        dismissed: isDismissed === '1',
        shared: isShared === '1',
        // Первые запуски — развёрнута, дальше сворачивается сама: тому, кто её
        // проигнорировал, она перестаёт мозолить глаза, но не пропадает.
        expanded: opens <= EXPANDED_OPENS,
      });
    } catch {
      set({ loaded: true });
    }

    // Сетевое — отдельно и не блокируя остальное: чеклист не должен падать
    // из-за недоступного бэкенда. Оба запроса параллельно, чтобы не
    // растягивать гидратацию на два round-trip'а.
    await Promise.all([
      (async () => {
        try {
          const status = await api.getDiscogsStatus();
          set({ discogsConnected: Boolean(status?.connected) });
        } catch {
          set({ discogsConnected: null });
        }
      })(),
      get().syncShared(userId),
    ]);
    set({ netSettled: true });
  },

  markShared: async (userId) => {
    if (get().shared) return;
    set({ shared: true });
    try {
      await AsyncStorage.setItem(sharedKey(userId), '1');
    } catch {
      // Молча: пункт останется открытым, это не ломает сценарий.
    }
  },

  /**
   * Свести факт «поделился ссылкой» с сервером — в обе стороны.
   *
   * Вниз: локальный флаг живёт в AsyncStorage одного устройства, после
   * переустановки или на втором телефоне шаг открывался заново.
   *
   * Вверх: у тех, кто делился ссылкой на старых сборках, флаг остался
   * только на устройстве — сервер о них не знает, и ачивка A4 «Распахнул»
   * им бы не досталась. Один POST закрывает и то, и другое.
   */
  syncShared: async (userId) => {
    try {
      const settings = await api.getProfileSettings();
      if (settings?.shared_at) {
        if (!get().shared) {
          set({ shared: true });
          void AsyncStorage.setItem(sharedKey(userId), '1').catch(() => {});
        }
        return;
      }
      if (get().shared) await api.markProfileShared();
    } catch {
      // Сеть отвалилась — останется локальный флаг, синхронизируемся позже.
    }
  },

  dismiss: (userId) => {
    set({ dismissed: true });
    void AsyncStorage.setItem(dismissKey(userId), '1').catch(() => {});
  },

  toggleExpanded: () => set((s) => ({ expanded: !s.expanded })),
}));

// ==================== Публичные отметки ====================

/**
 * Отметить «поделился профилем» — из share-листа и из копирования ссылки.
 *
 * Локально закрывает шаг чеклиста, на сервере ставит profile_shares.shared_at
 * и двигает ачивку A4 «Распахнул»: раньше она висела на тумблере публичности,
 * а он у всех включён с регистрации — переключать было нечего.
 */
export async function markProfileShared() {
  const userId = useAuthStore.getState().user?.id;
  if (!userId) return;
  // Тост покажет наблюдатель — здесь только факт.
  await useFirstStepsFlags.getState().markShared(userId);
  try {
    await api.markProfileShared();
    // Оверлей анлока — сразу после действия, пока человек ещё на профиле.
    await detectAchievementUnlocks();
  } catch {
    // Молча: локальный флаг уже стоит, а на сервер попробуем в другой раз.
  }
}

/**
 * Синхронизировать статус Discogs — зовётся из настроек, где он и меняется.
 * Без этого шаг чеклиста узнал бы о подключении только в следующую сессию.
 */
export function setDiscogsConnected(connected: boolean) {
  useFirstStepsFlags.setState({ discogsConnected: connected });
}

/**
 * Вернуть закрытый крестиком чеклист. Зовётся из «Как это работает» —
 * без этого дверь была в одну сторону: скрыл карточку и потерял навсегда.
 */
export async function restoreFirstSteps() {
  const userId = useAuthStore.getState().user?.id;
  if (!userId) return;
  useFirstStepsFlags.setState({ dismissed: false, expanded: true });
  try {
    await AsyncStorage.removeItem(dismissKey(userId));
  } catch {
    // Молча: в этой сессии карточка уже вернулась.
  }
}

/** Скрыт ли чеклист сейчас — чтобы «Как это работает» не предлагал лишнего. */
export const useFirstStepsDismissed = () => useFirstStepsFlags((s) => s.dismissed);

// ==================== Сборка шагов ====================

interface StepsInput {
  user: User | null;
  recordCount: number;
  wishlistCount: number;
  folderCount: number;
  shared: boolean;
  discogsConnected: boolean | null;
}

/**
 * Чистая функция: используется и хуком карточки, и глобальным наблюдателем.
 * Держать логику в одном месте обязательно — иначе тост и галочка разъедутся.
 */
function buildSteps(input: StepsInput): FirstStep[] {
  const { user, recordCount, wishlistCount, folderCount, shared, discogsConnected } = input;

  const steps: FirstStep[] = [
    {
      key: 'first-record',
      label: 'Добавить первую пластинку',
      why: 'Сканируй штрихкод, ищи по каталогу Discogs или перенеси всю коллекцию разом.',
      route: '/(tabs)',
      done: recordCount > 0,
    },
  ];

  // Импорт предлагаем только тем, кому он ещё полезен: пустая полка и
  // неподключённый аккаунт. Уже подключённым пункт остаётся, но закрытым —
  // исчезающий из чеклиста пункт читается как баг.
  if (discogsConnected === true || (discogsConnected === false && recordCount < DISCOGS_OFFER_BELOW)) {
    steps.push({
      key: 'discogs-import',
      label: 'Перенести коллекцию из Discogs',
      why: 'Если ведёшь коллекцию там, заберём всё разом, и вручную добавлять не придётся.',
      route: '/settings/discogs',
      optional: true,
      done: discogsConnected === true,
    });
  }

  steps.push(
    {
      key: 'profile',
      label: 'Добавить имя и аватар',
      // Требуем оба поля намеренно: раньше шаг закрывался по «имя ИЛИ аватар
      // ИЛИ описание», и у входа через Google он был закрыт с нулевого дня —
      // человек не понимал, что вообще сделал.
      why: 'Аватар меняется карандашиком на самом профиле, а имя в «Редактировать профиль».',
      // Не '/settings/edit-profile': там имя и юзернейм, но аватара нет вовсе —
      // человек попадал на экран, где половину шага сделать физически нельзя.
      // Профиль содержит и то, и другое, а карандашик подсвечиваем.
      route: '/profile',
      spotlight: 'profile-avatar',
      done: Boolean(user?.display_name && user?.avatar_url),
    },
    {
      key: 'wishlist',
      label: 'Собрать вишлист',
      why: 'Из него работают Радар и Маркет, и из него же друзья выбирают подарок.',
      route: '/(tabs)/search',
      done: wishlistCount > 0,
    },
    {
      key: 'folders',
      label: 'Разложить по папкам',
      why: 'Раскладывай по своей логике: жанры, эпохи, «на продажу». Папки живут над сеткой.',
      route: '/(tabs)/collection',
      done: folderCount > 0,
    },
    {
      key: 'share',
      label: 'Поделиться профилем',
      why: 'Скопируй ссылку или отправь её, и друзья забронируют подарок из вишлиста.',
      route: '/profile',
      spotlight: 'profile-share',
      done: shared,
    },
  );

  return steps;
}

/** Снимок входных данных из всех сторов — один источник для хука и наблюдателя. */
function currentInput(): StepsInput {
  const { user } = useAuthStore.getState();
  const collection = useCollectionStore.getState();
  const flags = useFirstStepsFlags.getState();
  return {
    user,
    // total_records надёжнее длины collectionItems: список постраничный, а
    // после импорта из Discogs первая страница может ещё не приехать.
    recordCount: collection.stats?.total_records ?? collection.collectionItems.length,
    wishlistCount: collection.wishlistItems.length,
    folderCount: collection.folders.length,
    shared: flags.shared,
    discogsConnected: flags.discogsConnected,
  };
}

// ==================== Наблюдатель прогресса ====================

let watcherStarted = false;
/**
 * Базовая линия: набор шагов, закрытых на момент первого замера. Всё, что
 * закрылось до неё, — это состояние аккаунта, а не заслуга текущей сессии,
 * и тостов по нему быть не должно.
 */
let baseline: Set<FirstStepKey> | null = null;
/** Чья это линия. Смена аккаунта на устройстве обязана её обнулить. */
let baselineUserId: string | null = null;

function evaluateProgress() {
  const flags = useFirstStepsFlags.getState();
  // До загрузки флагов состав шагов неполон (нет shared, нет Discogs) —
  // замер по нему дал бы ложную базовую линию и залп тостов следом.
  // netSettled — то же самое про серверные источники: они доезжают позже
  // локальных, и снятая до них линия объявляет старые шаги «пройденными».
  if (!flags.loaded || !flags.netSettled) return;

  const userId = useAuthStore.getState().user?.id ?? null;
  if (userId !== baselineUserId) {
    // Другой аккаунт: его закрытые шаги — не достижение текущей сессии.
    baseline = null;
    baselineUserId = userId;
  }

  const doneNow = new Set(buildSteps(currentInput()).filter((s) => s.done).map((s) => s.key));

  if (baseline === null) {
    baseline = doneNow;
    return;
  }

  for (const key of doneNow) {
    if (baseline.has(key)) continue;
    baseline.add(key);
    analytics.onboardingStepDone(key);
    // Закрывшему чеклист напоминание не нужно — он от него отказался.
    if (!flags.dismissed) {
      toast.success('Шаг пройден', stepToastLabel(key));
    }
  }
}

function stepToastLabel(key: FirstStepKey): string {
  const step = buildSteps(currentInput()).find((s) => s.key === key);
  return step?.label ?? 'Первые шаги';
}

/**
 * Подписка на сторы, из которых выводится прогресс. Вызывается один раз из
 * корневого layout: шаги закрываются на экранах, где карточки не видно, и без
 * глобального наблюдателя действие выглядит как «ничего не произошло».
 */
export function initFirstStepsWatcher() {
  if (watcherStarted) return;
  watcherStarted = true;
  useCollectionStore.subscribe(evaluateProgress);
  useAuthStore.subscribe(evaluateProgress);
  useFirstStepsFlags.subscribe(evaluateProgress);
}

// ==================== Хук карточки ====================

export interface FirstStepsState {
  steps: FirstStep[];
  doneCount: number;
  total: number;
  /** Показывать ли карточку вообще. */
  visible: boolean;
  /** Все пункты закрыты — карточка показывает финальную строку и самоуничтожается. */
  allDone: boolean;
  /** Ключ ближайшего невыполненного шага — у него раскрыт текст «зачем». */
  nextStepKey: FirstStepKey | null;
  /** Развёрнута или свёрнута в одну строку. */
  expanded: boolean;
  toggleExpanded: () => void;
  dismiss: () => void;
}

export function useFirstSteps(): FirstStepsState {
  const userId = useAuthStore((s) => s.user?.id);
  const user = useAuthStore((s) => s.user);
  const collectionItems = useCollectionStore((s) => s.collectionItems);
  const wishlistItems = useCollectionStore((s) => s.wishlistItems);
  const folders = useCollectionStore((s) => s.folders);
  const stats = useCollectionStore((s) => s.stats);

  const loaded = useFirstStepsFlags((s) => s.loaded);
  const dismissed = useFirstStepsFlags((s) => s.dismissed);
  const shared = useFirstStepsFlags((s) => s.shared);
  const expanded = useFirstStepsFlags((s) => s.expanded);
  const discogsConnected = useFirstStepsFlags((s) => s.discogsConnected);
  const hydrate = useFirstStepsFlags((s) => s.hydrate);
  const toggleExpanded = useFirstStepsFlags((s) => s.toggleExpanded);
  const dismissFlag = useFirstStepsFlags((s) => s.dismiss);

  useEffect(() => {
    if (userId) void hydrate(userId);
  }, [userId, hydrate]);

  const steps = buildSteps({
    user,
    recordCount: stats?.total_records ?? collectionItems.length,
    wishlistCount: wishlistItems.length,
    folderCount: folders.length,
    shared,
    discogsConnected,
  });

  // Счётчик, прогресс-бар и «следующий шаг» считаются только по обязательным
  // пунктам: необязательные — предложение, а не долг, и держать чеклист
  // незакрытым они не должны.
  const required = steps.filter((s) => !s.optional);
  const doneCount = required.filter((s) => s.done).length;

  return {
    steps,
    doneCount,
    total: required.length,
    // Пока не прочитали хранилище — не показываем: мигание карточки на старте
    // выглядит как баг рендера.
    visible: loaded && !dismissed,
    allDone: doneCount === required.length,
    nextStepKey: required.find((s) => !s.done)?.key ?? null,
    expanded,
    toggleExpanded,
    dismiss: () => {
      if (userId) dismissFlag(userId);
    },
  };
}
