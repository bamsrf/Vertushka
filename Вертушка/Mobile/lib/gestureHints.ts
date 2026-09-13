/**
 * Жест-подсказки — шестая поверхность онбординга.
 *
 * Чем отличается от контекстных подсказок (lib/coachMarks.ts). Те объясняют
 * ФИЧУ словами: карточка с заголовком, текстом и крестиком. Здесь объяснять
 * нечего — надо показать, что строка вообще двигается. Текст этого не делает:
 * «строку можно потянуть влево» человек читает и забывает, а сдвинувшаяся на
 * его глазах строка запоминается сразу. Поэтому подсказка тут не карточка, а
 * само движение цели: мы коротко тянем строку и отпускаем.
 *
 * Приём не новый — он уже дважды написан в проекте вручную:
 * `WishlistListSwipe` (авто-тизер вишлиста) и `ManualAddVinylToggle`
 * (шевроны у винил-кноба). Оба работают, но каждый со своей памятью: флаги
 * `hasSeenSwipeHint` / `hasSeenCurtainHint` лежат в marketStore, они общие на
 * устройство, а не на аккаунт, и гасятся фактом ПОКАЗА, а не тем, что человек
 * жест освоил. Этот модуль — тот же приём, но с общими правилами.
 *
 * Правила показа:
 *   - подсказка гаснет НАВСЕГДА, как только человек сделал жест сам
 *     (markGesturePerformed) — учить освоенному незачем;
 *   - пока не сделал, показываем максимум MAX_SHOWS раз за всё время;
 *   - не больше ОДНОЙ жест-подсказки за запуск приложения В СВОЁМ слоте.
 *
 * Слотов два, и это та же развилка, что у групп в coachMarks. Подсказка про
 * возврат назад живёт на КАЖДОМ вложенном экране, подсказки строк — на трёх
 * конкретных списках. С общим слотом кто угодно из строк мог отнять запуск у
 * навигации, хотя навигация нужнее: без неё человек не знает, как уйти с
 * экрана вообще.
 *
 * Чего здесь СОЗНАТЕЛЬНО нет — глобальной проверки «не поверх контекстной
 * подсказки». Она была и молча выключала фичу: `coachSpotlight` — один флаг на
 * всё приложение, гаснет он при закрытии подсказки или размонтировании её
 * экрана, а вкладки остаются смонтированными. Не закрытая крестиком `scan-ways`
 * на вкладке сканера держала флаг поднятым весь запуск, и подсказка про возврат
 * не появлялась ни на одном экране (проверено на живом аккаунте 13.09.2026).
 * Точечные запреты вместо этого — через `blockedWhile` у вызывающего.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export type GestureHintKey =
  | 'swipe-back'
  | 'notification-delete'
  | 'conversation-actions'
  | 'chat-reply';

/**
 * Слот «одна подсказка за запуск». Навигация и строки не конкурируют.
 */
export type GestureHintSlot = 'nav' | 'row';

export interface GestureHintMeta {
  key: GestureHintKey;
  /** По умолчанию 'row'. */
  slot?: GestureHintSlot;
  /** Человеческое описание — для экрана «Как это работает». */
  label: string;
  /**
   * Куда и насколько тянуть цель, в точках. Знак = направление жеста.
   * Не «сколько нужно протянуть, чтобы сработало»: подсказка показывает
   * ВОЗМОЖНОСТЬ движения, а не выполняет действие за человека. Поэтому
   * дистанция заведомо меньше порога срабатывания каждой поверхности.
   *
   * Пусто у подсказок, которые двигать нечего: свайп «назад» везёт ЭКРАН, а
   * на iOS его тащит нативный стек — своей shared value там нет. Такие
   * подсказки рисуют себя сами (см. components/onboarding/SwipeBackHint.tsx).
   */
  distance?: number;
  /**
   * Меньше — важнее. Нужен на случай, когда две поверхности всё-таки сошлись
   * на одном экране: без явного порядка выигрывала бы та, чей эффект успел
   * первым, то есть случайная.
   */
  priority: number;
}

export const GESTURE_HINTS: GestureHintMeta[] = [
  {
    key: 'swipe-back',
    // Самый высокий приоритет: это единственный жест, который живёт на КАЖДОМ
    // вложенном экране, а не на одном списке. Не зная его, человек ищет
    // стрелку в шапке на каждой странице приложения.
    label: 'С любой страницы можно вернуться свайпом вправо',
    slot: 'nav',
    priority: 5,
  },
  {
    key: 'notification-delete',
    label: 'Уведомление можно смахнуть влево, чтобы удалить',
    // 26 из 88 порога (30%): баннер корзины уже виден краем, но до удаления
    // (50%) далеко — подсказка физически не может ничего стереть.
    distance: -26,
    priority: 10,
  },
  {
    key: 'conversation-actions',
    label: 'Диалог можно смахнуть влево — там кнопки действий',
    distance: -30,
    priority: 20,
  },
  {
    key: 'chat-reply',
    label: 'Сообщение можно смахнуть, чтобы ответить на него',
    distance: 24,
    priority: 30,
  },
];

const META_BY_KEY = new Map(GESTURE_HINTS.map((m) => [m.key, m]));

export const getGestureHint = (key: GestureHintKey): GestureHintMeta => {
  const meta = META_BY_KEY.get(key);
  if (!meta) throw new Error(`Unknown gesture hint: ${key}`);
  return meta;
};

const storageKey = (userId: string, key: GestureHintKey) =>
  `@vertushka:gesture:${userId}:${key}`;

/**
 * Сколько раз подсказываем, пока человек не сделал жест сам.
 *
 * Два — по той же причине, что и у контекстных подсказок: первый раз можно не
 * заметить (смотрел в другую часть экрана), третий уже читается как глюк
 * интерфейса — строка дёргается сама по себе.
 */
const MAX_SHOWS = 2;

export interface GestureHintState {
  /** Человек сделал жест сам — подсказка больше не нужна никогда. */
  performed: boolean;
  /** Сколько раз подсказывали, пока жест не освоен. */
  shows: number;
}

const EMPTY_STATE: GestureHintState = { performed: false, shows: 0 };

/**
 * Формат значения в хранилище:
 *   'done'  — жест освоен;
 *   's<N>'  — подсказывали N раз.
 */
function parseState(raw: string | null): GestureHintState {
  if (!raw) return { ...EMPTY_STATE };
  if (raw === 'done') return { performed: true, shows: 0 };
  if (raw.startsWith('s')) {
    const n = Number(raw.slice(1));
    return { performed: false, shows: Number.isFinite(n) ? n : 0 };
  }
  return { ...EMPTY_STATE };
}

export const isGestureHintSuppressed = (state: GestureHintState | undefined): boolean => {
  if (!state) return false;
  return state.performed || state.shows >= MAX_SHOWS;
};

/** Кэш в памяти: хук проверяется на каждом рендере списка. */
let stateCache: { userId: string; states: Map<GestureHintKey, GestureHintState> } | null = null;

export async function loadGestureHintStates(
  userId: string,
): Promise<Map<GestureHintKey, GestureHintState>> {
  if (stateCache?.userId === userId) return stateCache.states;
  const states = new Map<GestureHintKey, GestureHintState>();
  try {
    const pairs = await AsyncStorage.multiGet(
      GESTURE_HINTS.map((m) => storageKey(userId, m.key)),
    );
    pairs.forEach(([storeKey, value]) => {
      const key = storeKey.split(':').pop() as GestureHintKey;
      states.set(key, parseState(value));
    });
  } catch {
    // Не прочитали — считаем, что не показывали. Один лишний нудж безобиднее
    // жеста, о котором человек так и не узнал.
  }
  stateCache = { userId, states };
  return states;
}

/** Слоты «одна жест-подсказка за запуск» — свой у навигации и у строк. */
const slotTaken: Record<GestureHintSlot, boolean> = { nav: false, row: false };

export const slotOf = (key: GestureHintKey): GestureHintSlot =>
  getGestureHint(key).slot ?? 'row';

export const isGestureSlotTaken = (slot: GestureHintSlot = 'row') => slotTaken[slot];

/**
 * Занять слот. Возвращает false, если его уже забрали, — тогда подсказка
 * молчит до следующего запуска.
 */
export function takeGestureSlot(slot: GestureHintSlot = 'row'): boolean {
  if (slotTaken[slot]) return false;
  slotTaken[slot] = true;
  return true;
}

/**
 * Вернуть слот: победитель не смог показаться (экран ушёл, пока шла пауза).
 * Без этого запуск остался бы вообще без подсказки.
 */
export function releaseGestureSlot(slot: GestureHintSlot = 'row') {
  slotTaken[slot] = false;
}

/**
 * Ревизия правил — на неё подписаны хуки, чтобы «Повторить подсказки жестов»
 * из настроек срабатывало на уже смонтированных экранах. Ровно та же проблема,
 * что решена в coachMarks: сброс менял хранилище, но ни одна зависимость
 * эффекта не двигалась.
 */
let revision = 0;
const revisionListeners = new Set<() => void>();

export const subscribeGestureHints = (listener: () => void) => {
  revisionListeners.add(listener);
  return () => {
    revisionListeners.delete(listener);
  };
};

export const getGestureHintRevision = () => revision;

function bumpRevision() {
  revision += 1;
  revisionListeners.forEach((l) => l());
}

/** Подсказали — увеличиваем счётчик показов. */
export async function markGestureHintShown(userId: string, key: GestureHintKey) {
  const states = await loadGestureHintStates(userId);
  const prev = states.get(key) ?? { ...EMPTY_STATE };
  if (prev.performed) return;
  const next: GestureHintState = { performed: false, shows: prev.shows + 1 };
  states.set(key, next);
  try {
    await AsyncStorage.setItem(storageKey(userId, key), `s${next.shows}`);
  } catch {
    // Молча: в этом запуске подсказка всё равно уже не повторится.
  }
}

/**
 * Человек сделал жест сам. Вызывается из onStart жеста — намерения достаточно,
 * доводить до срабатывания не нужно: тот, кто потянул строку, уже знает, что
 * она тянется.
 */
export async function markGesturePerformed(userId: string, key: GestureHintKey) {
  const states = await loadGestureHintStates(userId);
  if (states.get(key)?.performed) return;
  states.set(key, { performed: true, shows: 0 });
  try {
    await AsyncStorage.setItem(storageKey(userId, key), 'done');
  } catch {
    // Молча.
  }
}

/** Сброс из «Как это работает»: вернуть одну подсказку или все сразу. */
export async function resetGestureHints(userId: string, key?: GestureHintKey) {
  const targets = key ? [key] : GESTURE_HINTS.map((m) => m.key);
  try {
    await AsyncStorage.multiRemove(targets.map((k) => storageKey(userId, k)));
  } catch {
    // Молча.
  }
  if (stateCache?.userId === userId) {
    targets.forEach((k) => stateCache!.states.delete(k));
  }
  // Сброс — явный запрос увидеть подсказки снова, поэтому освобождаем и слоты:
  // иначе пришлось бы перезапускать приложение.
  slotTaken.nav = false;
  slotTaken.row = false;
  bumpRevision();
}
