/**
 * Контекстные подсказки — замена пошагового spotlight-тура.
 *
 * Принцип: фича объясняется не «в начале», а в момент, когда ею стало можно
 * воспользоваться. Радар бессмысленен без вишлиста, папки — без пары десятков
 * пластинок, pinch-zoom — без плотной сетки. До разблокировки молчим.
 *
 * Ни одна подсказка НИЧЕГО не измеряет: все формы позиционируются из потока
 * вёрстки (inline-карточка, шторка, тост, оверлей внутри своего контейнера).
 * Именно measureInWindow в старом туре давал рамки, висящие в пустоте.
 *
 * Правила показа:
 *   - каждая подсказка ровно один раз на аккаунт (ключ в AsyncStorage);
 *   - не больше ОДНОЙ подсказки за запуск приложения — иначе новичка засыпает;
 *   - если условие сошлось у нескольких сразу, выигрывает меньший `priority`
 *     (см. requestCoachMark); раньше побеждала та, чей хук объявлен выше в
 *     компоненте, — то есть выбор был случайным побочным эффектом;
 *   - закрытие необратимо (вернуть можно только через «Как это работает»).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

export type CoachMarkKey =
  | 'pinch-zoom'
  | 'collection-value'
  | 'folders'
  | 'multi-select'
  | 'radar'
  | 'market'
  | 'gifts-incoming';

export interface CoachMarkMeta {
  key: CoachMarkKey;
  /** Заголовок — и в самой подсказке, и в списке «Как это работает». */
  title: string;
  body: string;
  /** Человеческое описание триггера — только для экрана «Как это работает». */
  unlock: string;
  /**
   * Маршрут до фичи: «Коллекция → шапка → ₽». Без него подсказка называет
   * фичу, но не отвечает на вопрос «а где это». Кольцо (CoachPulse) зажигает
   * цель, только если она на текущем экране; для всего остального маршрут —
   * единственный способ объяснить место.
   */
  where: string;
  icon: string;
  /**
   * Форма подсветки цели. Различается НЕ цветом, а повторяемостью — именно
   * повтор читается как «непрочитанное уведомление»:
   *   'pulse' — расходящееся кольцо. Для статичных целей;
   *   'glow'  — ровный ореол, проявляется один раз и держится. Для целей,
   *             которые уже сами анимируются, иначе две пульсации сливаются
   *             в одну и юзер начинает читать собственную анимацию элемента
   *             как непрочитанный шаг онбординга.
   * По умолчанию 'pulse'.
   */
  spotlight?: 'pulse' | 'glow';
  /**
   * Меньше — важнее. Разрешает конкуренцию, когда условия сошлись у нескольких
   * подсказок в один момент. Порядок задан ценностью для новичка: сначала то,
   * без чего интерфейс непонятен (жест зума), затем то, что он всё равно
   * найдёт сам.
   */
  priority: number;
}

/**
 * Каталог подсказок. Единственный источник правды: и рантайм, и экран
 * «Как это работает» читают отсюда, поэтому тексты не разъезжаются.
 */
export const COACH_MARKS: CoachMarkMeta[] = [
  {
    key: 'pinch-zoom',
    priority: 10,
    title: 'Вся полка на одном экране',
    body: 'Сожми сетку двумя пальцами — коллекция ужмётся до обложек. Разожми, чтобы вернуться.',
    unlock: 'от 12 пластинок в коллекции',
    where: 'Коллекция → сетка обложек, жест двумя пальцами',
    icon: 'grid-outline',
  },
  {
    key: 'collection-value',
    priority: 60,
    title: 'Сколько стоит коллекция',
    body: 'Считаем по Discogs marketplace и переводим в рубли по курсу ЦБ. Кнопка «₽» в шапке.',
    unlock: 'от 5 пластинок в коллекции',
    where: 'Коллекция → шапка списка → кнопка ₽ (между видом и фильтром)',
    icon: 'cash-outline',
  },
  {
    key: 'folders',
    priority: 50,
    title: 'Пора разложить по папкам',
    body: 'Жанры, эпохи, «на продажу» — любая своя логика. Папки живут над сеткой.',
    unlock: 'от 15 пластинок в коллекции',
    where: 'Коллекция → блок «Папки» над сеткой',
    icon: 'folder-outline',
  },
  {
    key: 'multi-select',
    priority: 70,
    title: 'Можно выбирать пачкой',
    body: 'Удерживай карточку — включится режим выбора. Папки, удаление и подарки сразу для нескольких.',
    unlock: 'после двух удалений подряд по одной',
    where: 'Коллекция → долгое нажатие на карточку, либо «Выбрать» в шапке',
    icon: 'checkmark-circle-outline',
  },
  {
    key: 'radar',
    priority: 20,
    title: 'Радар следит за ценой',
    body: 'Поставь порог — пришлём пуш, когда пластинка подешевеет или появится в наличии.',
    unlock: 'первая позиция в вишлисте',
    // Кнопка радара уже пульсирует собственным sonar'ом (два кольца,
    // opacity 0→0.55, scale до 2.6). Кольцо подсказки поверх него слилось бы
    // с ним в одно впечатление, и sonar — постоянная индикация работы радара —
    // начал бы читаться как «непрочитанный шаг онбординга». Поэтому ореол.
    spotlight: 'glow',
    where: 'Вишлист → шапка списка → кнопка радара справа',
    // Не 'options-outline': это ровно тот же глиф, что у кнопки фильтра в
    // соседней ячейке той же шапки. Подсказка, которая объясняет место, не
    // должна иконкой указывать на чужую кнопку. Ценник ближе к сути.
    icon: 'pricetag-outline',
  },
  {
    key: 'market',
    priority: 30,
    title: 'Маркет знает, где купить',
    body: 'Магазины с наличием и ценами прямо сейчас — по твоему вишлисту.',
    unlock: 'открыл карточку релиза с офферами или собрал 3 позиции в вишлисте',
    where: 'Поиск → прокрутить вниз до плашки Маркета; ещё вход — Профиль → Маркет',
    icon: 'business-outline',
  },
  {
    key: 'gifts-incoming',
    priority: 40,
    title: 'Из вишлиста можно дарить',
    body: 'Скинь ссылку на профиль — друзья забронируют подарок. Что именно забронировали, ты не увидишь.',
    unlock: 'вишлист не пуст и профиль публичный',
    where: 'Профиль → «Ваш профиль» → Поделиться',
    icon: 'gift-outline',
  },
];

const META_BY_KEY = new Map(COACH_MARKS.map((m) => [m.key, m]));

export const getCoachMark = (key: CoachMarkKey): CoachMarkMeta => {
  const meta = META_BY_KEY.get(key);
  if (!meta) throw new Error(`Unknown coach mark: ${key}`);
  return meta;
};

const storageKey = (userId: string, key: CoachMarkKey) =>
  `@vertushka:hint:${userId}:${key}`;

/**
 * Сколько раз показывать подсказку, если её так и не подтвердили.
 *
 * Раньше факт показа записывался ТОЛЬКО при закрытии крестиком или переходе
 * по действию. Кто уходил с экрана свайпом — не записывался никак, и подсказка
 * возвращалась при каждом следующем запуске бесконечно. Два показа — предел:
 * первый мог быть не замечен, третий уже назойлив.
 */
const MAX_SHOWS_WITHOUT_ACK = 2;

export interface CoachMarkState {
  /** Юзер подтвердил явно: закрыл крестиком или пошёл по действию. */
  acknowledged: boolean;
  /** Сколько раз показывали без подтверждения. */
  shows: number;
}

const EMPTY_STATE: CoachMarkState = { acknowledged: false, shows: 0 };

/** Больше не показываем: либо подтвердили, либо исчерпали лимит показов. */
export const isSuppressed = (state: CoachMarkState | undefined): boolean =>
  !!state && (state.acknowledged || state.shows >= MAX_SHOWS_WITHOUT_ACK);

/**
 * Формат значения в хранилище:
 *   'done'  — подтверждено;
 *   's<N>'  — показано N раз без подтверждения;
 *   '1'     — легаси: старый код писал это при закрытии. Читаем как 'done',
 *             поэтому у тех, кто уже закрывал подсказки, ничего не всплывёт.
 */
function parseState(raw: string | null): CoachMarkState {
  if (!raw) return { ...EMPTY_STATE };
  if (raw === 'done' || raw === '1') return { acknowledged: true, shows: 0 };
  if (raw.startsWith('s')) {
    const n = Number(raw.slice(1));
    return { acknowledged: false, shows: Number.isFinite(n) ? n : 0 };
  }
  return { ...EMPTY_STATE };
}

/**
 * Кэш состояний в памяти: подсказки проверяются на каждом рендере коллекции,
 * дёргать AsyncStorage столько раз незачем.
 */
let stateCache: { userId: string; states: Map<CoachMarkKey, CoachMarkState> } | null = null;

/** Лимит «одна подсказка за запуск». Сбрасывается только перезапуском приложения. */
let shownThisSession = false;

export const isSessionSlotTaken = () => shownThisSession;

/**
 * Окно арбитража. Хуки разных подсказок монтируются в одном рендере, но их
 * эффекты и чтение AsyncStorage разъезжаются на несколько тиков. Собираем
 * заявки в течение окна и только потом выбираем победителя — иначе слот
 * забирала бы просто самая быстрая.
 */
const ARBITRATION_MS = 150;

interface PendingRequest {
  priority: number;
  resolve: (won: boolean) => void;
}

const pending = new Map<CoachMarkKey, PendingRequest>();
let arbitrationTimer: ReturnType<typeof setTimeout> | null = null;

function settleArbitration() {
  arbitrationTimer = null;
  const entries = [...pending.entries()];
  pending.clear();
  if (entries.length === 0) return;

  entries.sort((a, b) => a[1].priority - b[1].priority);
  const [, winner] = entries[0];

  // Слот мог уйти, пока шло окно (например, подсказку сбросили из настроек и
  // тут же показали) — тогда не выигрывает никто.
  if (shownThisSession) {
    entries.forEach(([, req]) => req.resolve(false));
    return;
  }

  shownThisSession = true;
  winner.resolve(true);
  entries.slice(1).forEach(([, req]) => req.resolve(false));
}

/**
 * Подать заявку на показ. Возвращает true ровно одной подсказке за сессию —
 * той, у которой меньше `priority` среди заявившихся в окне арбитража.
 */
export function requestCoachMark(key: CoachMarkKey): Promise<boolean> {
  if (shownThisSession) return Promise.resolve(false);

  const existing = pending.get(key);
  // Повторная заявка тем же ключом (перерендер) — не плодим промисы.
  if (existing) return new Promise((resolve) => existing.resolve = chain(existing.resolve, resolve));

  return new Promise<boolean>((resolve) => {
    pending.set(key, { priority: getCoachMark(key).priority, resolve });
    if (!arbitrationTimer) {
      arbitrationTimer = setTimeout(settleArbitration, ARBITRATION_MS);
    }
  });
}

/**
 * Вернуть слот, если победитель не смог показаться (компонент размонтировался,
 * пока шёл арбитраж). Без этого сессия осталась бы вовсе без подсказки.
 */
export function releaseSessionSlot() {
  shownThisSession = false;
}

/** Разрешить обе заявки одним результатом. */
function chain(a: (won: boolean) => void, b: (won: boolean) => void) {
  return (won: boolean) => {
    a(won);
    b(won);
  };
}

export async function loadCoachMarkStates(
  userId: string,
): Promise<Map<CoachMarkKey, CoachMarkState>> {
  if (stateCache?.userId === userId) return stateCache.states;
  const states = new Map<CoachMarkKey, CoachMarkState>();
  try {
    const pairs = await AsyncStorage.multiGet(
      COACH_MARKS.map((m) => storageKey(userId, m.key)),
    );
    pairs.forEach(([storeKey, value]) => {
      const key = storeKey.split(':').pop() as CoachMarkKey;
      states.set(key, parseState(value));
    });
  } catch {
    // Не прочитали — считаем, что ничего не показывали. Лишняя подсказка
    // безобиднее молчания на пустом аккаунте.
  }
  stateCache = { userId, states };
  return states;
}

/** Показали, но подтверждения ещё нет. Увеличивает счётчик показов. */
export async function markCoachMarkShown(userId: string, key: CoachMarkKey) {
  const states = await loadCoachMarkStates(userId);
  const prev = states.get(key) ?? { ...EMPTY_STATE };
  if (prev.acknowledged) return;
  const next: CoachMarkState = { acknowledged: false, shows: prev.shows + 1 };
  states.set(key, next);
  try {
    await AsyncStorage.setItem(storageKey(userId, key), `s${next.shows}`);
  } catch {
    // Молча: в этой сессии подсказка всё равно уже не повторится.
  }
}

/** Подтвердили явно — закрыли крестиком или пошли по действию. */
export async function markCoachMarkAcknowledged(userId: string, key: CoachMarkKey) {
  const states = await loadCoachMarkStates(userId);
  states.set(key, { acknowledged: true, shows: 0 });
  try {
    await AsyncStorage.setItem(storageKey(userId, key), 'done');
  } catch {
    // Молча.
  }
}

/** Сброс из «Как это работает» — вернуть одну подсказку или все сразу. */
export async function resetCoachMarks(userId: string, key?: CoachMarkKey) {
  const targets = key ? [key] : COACH_MARKS.map((m) => m.key);
  try {
    await AsyncStorage.multiRemove(targets.map((k) => storageKey(userId, k)));
  } catch {
    // Молча.
  }
  if (stateCache?.userId === userId) {
    targets.forEach((k) => stateCache!.states.delete(k));
  }
  // Сброс — это явный запрос увидеть подсказку снова, поэтому освобождаем и
  // слот сессии: иначе пришлось бы перезапускать приложение.
  shownThisSession = false;
  if (arbitrationTimer) {
    clearTimeout(arbitrationTimer);
    arbitrationTimer = null;
  }
  pending.forEach((req) => req.resolve(false));
  pending.clear();
}
