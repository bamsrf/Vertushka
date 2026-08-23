/**
 * Тур по карточке релиза — единственный сценарий онбординга, где объяснений
 * подряд больше одного.
 *
 * Почему здесь исключение из правила «одна подсказка за сессию». Обычные
 * подсказки (lib/coachMarks.ts) объясняют РАЗНЫЕ экраны, и одна за запуск —
 * защита от навязчивости. Карточка релиза — наоборот: пять незнакомых блоков
 * на одном экране, и по одному за сессию человек разбирался бы неделю.
 * Поэтому здесь короткая последовательность, но ровно один раз за всё время.
 *
 * Форма та же, что и у остальных подсказок: карточка встаёт в поток прямо
 * НАД блоком, который объясняет, а сам блок обводится ореолом (CoachPulse).
 * Никаких измерений и оверлеев — подсказка не может промахнуться мимо цели,
 * потому что стоит с ней в одной колонке.
 *
 * Состав шагов зависит от релиза: у пластинки без истории цен нет графика, у
 * релиза без мастера — «других версий». Показываем только то, что человек
 * реально видит, иначе тур обещает блоки, которых на экране нет.
 */
import { useCallback, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { useAuthStore } from './store';
import { analytics } from './analytics';
import { markCoachMarkAcknowledged, type CoachMarkKey } from './coachMarks';

/**
 * Радара здесь нет намеренно: его кнопка живёт в фиксированной нижней панели,
 * а не в потоке страницы, и подсказка «встань над блоком» для неё невозможна.
 * Радар объясняет своя подсказка из каталога, на вишлисте.
 */
export type RecordTourKey = 'price' | 'offers' | 'history' | 'versions';

export interface RecordTourStep {
  key: RecordTourKey;
  title: string;
  body: string;
  icon: string;
}

/**
 * Порядок — сверху вниз по экрану. Тур ведёт человека по странице в том же
 * направлении, в котором он её и так листает; прыжки вверх-вниз заставляли бы
 * искать блок глазами.
 */
export const RECORD_TOUR_STEPS: RecordTourStep[] = [
  {
    key: 'price',
    title: 'Примерная стоимость',
    body: 'Столько такие же пластинки стоят на Discogs сейчас. Это ориентир, а не ценник: конкретный экземпляр зависит от состояния.',
    icon: 'currency-rub',
  },
  {
    key: 'offers',
    title: 'Где купить',
    body: 'Живые предложения магазинов: наличие и цена на эту минуту. Нажми на магазин, чтобы открыть его страницу.',
    icon: 'business-outline',
  },
  {
    key: 'history',
    title: 'Как менялась цена',
    body: 'График показывает, дорожала пластинка или дешевела, и отмечает исторический минимум, с которым удобно сравнить текущую цену.',
    icon: 'pricetag-outline',
  },
  {
    key: 'versions',
    title: 'Другие версии',
    body: 'Один альбом переиздают десятки раз: разные годы, страны, цвет винила. Здесь все издания этого релиза.',
    icon: 'grid-outline',
  },
];

const STEP_BY_KEY = new Map(RECORD_TOUR_STEPS.map((s) => [s.key, s]));

/**
 * Шаги тура, у которых есть двойник в каталоге контекстных подсказок.
 *
 * Двойники нужны сами по себе: тур одноразовый, и если первый открытый релиз
 * был без переизданий, про «другие версии» человек не узнал бы никогда. Но
 * когда тур блок УЖЕ объяснил, повторять то же самое отдельной подсказкой
 * незачем — поэтому на старте тура двойники помечаются подтверждёнными.
 */
const TOUR_TWINS: Partial<Record<RecordTourKey, CoachMarkKey>> = {
  offers: 'offer-price',
  versions: 'other-versions',
};

const storageKey = (userId: string) => `@vertushka:record_tour:${userId}`;

/**
 * Меньше двух блоков — не тур, а одинокая подсказка поверх и без того
 * понятного экрана. Такому релизу объяснения не нужны: человек увидит их на
 * следующем, где блоков больше.
 */
const MIN_STEPS = 2;

interface RecordTourState {
  /** Для какого аккаунта прочитан флаг. */
  hydratedFor: string | null;
  loaded: boolean;
  /** Тур уже пройден или пропущен — больше не показываем никогда. */
  done: boolean;
  /** Ключи блоков текущего экрана, в порядке следования. */
  queue: RecordTourKey[];
  index: number;

  hydrate: (userId: string) => Promise<void>;
  start: (queue: RecordTourKey[]) => void;
  advance: () => void;
  finish: (reason: 'done' | 'skip') => void;
  reset: () => Promise<void>;
}

const useRecordTourStore = create<RecordTourState>((set, get) => ({
  hydratedFor: null,
  loaded: false,
  done: true,
  queue: [],
  index: 0,

  hydrate: async (userId) => {
    if (get().hydratedFor === userId) return;
    // Слот занимаем сразу: карточку релиза можно открыть из нескольких мест,
    // и два маунта подряд не должны читать хранилище дважды.
    set({ hydratedFor: userId, loaded: false, done: true });
    try {
      const raw = await AsyncStorage.getItem(storageKey(userId));
      set({ loaded: true, done: raw === '1' });
    } catch {
      // Не прочитали — считаем пройденным. Показать тур повторно тому, кто его
      // уже видел, хуже, чем не показать: экран остаётся полностью рабочим.
      set({ loaded: true, done: true });
    }
  },

  start: (queue) => {
    const s = get();
    if (!s.loaded || s.done || s.queue.length > 0) return;
    if (queue.length < MIN_STEPS) return;
    set({ queue, index: 0 });
    analytics.recordTourStarted(queue.length);

    // Блоки, которые объяснит тур, не должны потом объясняться повторно
    // отдельными подсказками из каталога.
    const userId = useAuthStore.getState().user?.id;
    if (userId) {
      for (const key of queue) {
        const twin = TOUR_TWINS[key];
        if (twin) void markCoachMarkAcknowledged(userId, twin);
      }
    }
  },

  advance: () => {
    const { index, queue } = get();
    if (index + 1 >= queue.length) {
      get().finish('done');
      return;
    }
    set({ index: index + 1 });
  },

  finish: (reason) => {
    const { queue, index } = get();
    if (queue.length === 0) return;
    analytics.recordTourFinished(reason, index + 1, queue.length);
    set({ done: true, queue: [], index: 0 });
    const userId = useAuthStore.getState().user?.id;
    if (userId) void AsyncStorage.setItem(storageKey(userId), '1').catch(() => {});
  },

  reset: async () => {
    set({ done: false, queue: [], index: 0 });
    const userId = useAuthStore.getState().user?.id;
    if (!userId) return;
    try {
      await AsyncStorage.removeItem(storageKey(userId));
    } catch {
      // Молча: в этой сессии тур уже разблокирован.
    }
  },
}));

/** Пройден ли тур — для экрана «Как это работает». */
export const useRecordTourDone = () => useRecordTourStore((s) => s.done);

/** Вернуть тур из «Как это работает». */
export const resetRecordTour = () => useRecordTourStore.getState().reset();

export interface RecordTourApi {
  /** Идёт ли тур прямо сейчас — по нему глушатся обычные подсказки экрана. */
  active: boolean;
  /** Показывать ли подсказку у этого блока. */
  isAt: (key: RecordTourKey) => boolean;
  step: RecordTourStep | null;
  /** «2 из 4» для счётчика в карточке. */
  position: string;
  /** Последний шаг — у кнопки меняется подпись. */
  isLast: boolean;
  next: () => void;
  skip: () => void;
}

/**
 * @param available ключи блоков, которые реально отрисованы для этого релиза,
 *        в порядке сверху вниз. Массив пересобирается на каждом рендере, поэтому
 *        внутрь эффекта уходит его строковая подпись, а не сама ссылка.
 * @param ready состав блоков окончательный. До этого стартовать нельзя: офферы
 *        и история цен грузятся асинхронно, и очередь, собранная раньше времени,
 *        потеряла бы шаги — переcобрать её уже нечем, тур одноразовый.
 */
export function useRecordTour(available: RecordTourKey[], ready: boolean): RecordTourApi {
  const userId = useAuthStore((s) => s.user?.id);
  const loaded = useRecordTourStore((s) => s.loaded);
  const done = useRecordTourStore((s) => s.done);
  const queue = useRecordTourStore((s) => s.queue);
  const index = useRecordTourStore((s) => s.index);
  const hydrate = useRecordTourStore((s) => s.hydrate);
  const start = useRecordTourStore((s) => s.start);
  const advance = useRecordTourStore((s) => s.advance);
  const finish = useRecordTourStore((s) => s.finish);

  useEffect(() => {
    if (userId) void hydrate(userId);
  }, [userId, hydrate]);

  const signature = available.join(',');
  useEffect(() => {
    if (!ready || !loaded || done || !signature) return;
    start(signature.split(',') as RecordTourKey[]);
  }, [ready, loaded, done, signature, start]);

  // Экран ушёл, пока шёл тур: очередь надо снять, иначе следующая карточка
  // релиза откроется с подсказкой посередине чужого набора блоков.
  useEffect(
    () => () => {
      const s = useRecordTourStore.getState();
      if (s.queue.length > 0) s.finish('skip');
    },
    [],
  );

  const activeKey = queue[index] ?? null;

  return {
    active: queue.length > 0,
    isAt: useCallback((key: RecordTourKey) => activeKey === key, [activeKey]),
    step: activeKey ? STEP_BY_KEY.get(activeKey) ?? null : null,
    position: queue.length > 0 ? `${index + 1} из ${queue.length}` : '',
    isLast: queue.length > 0 && index === queue.length - 1,
    next: advance,
    skip: () => finish('skip'),
  };
}
