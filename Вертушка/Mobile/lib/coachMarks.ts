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
  | 'gifts-incoming'
  | 'scan-ways'
  // Подсказки карточки релиза. Их условие — свойство КОНКРЕТНОЙ пластинки
  // (цветной винил, ярлык редкости, живая цена магазина), а не состояние
  // аккаунта, поэтому срабатывают на первом релизе, где такое встретилось.
  | 'vinyl-color'
  | 'rarity-tiers'
  | 'offer-price'
  | 'other-versions';

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
   * Группа лимита «одна за запуск». По умолчанию 'app'. Подсказки карточки
   * релиза живут в своей группе — иначе слот всегда забирала бы коллекция,
   * стартовый экран. См. CoachMarkGroup.
   */
  group?: CoachMarkGroup;
  /**
   * Сколько раз показывать без подтверждения. По умолчанию MAX_SHOWS_DEFAULT.
   * Единица — для подсказок, которые и так попадаются на глаза сразу: второй
   * показ там читается не как напоминание, а как навязчивость.
   */
  maxShows?: number;
  /**
   * Пауза перед показом. Нужна там, где подсказка иначе появляется
   * одновременно с самим экраном и накрывает его прежде, чем человек успел
   * посмотреть, куда попал.
   */
  delayMs?: number;
  /**
   * Куда идти из «Как это работает», когда подсказку возвращают вручную.
   * Без этого «Показать снова» оставляло человека в настройках гадать, где
   * теперь искать обещанное.
   */
  goTo?: {
    route: string;
    /** Вкладка внутри коллекции, если фича живёт на вишлисте. */
    tab?: 'collection' | 'wishlist';
    /** Что сказать, если точное место открыть нельзя (карточка любого релиза). */
    note?: string;
  };
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
    key: 'scan-ways',
    // Самый высокий приоритет: это первый экран после регистрации, и на нём
    // человек делает первое действие в приложении. Остальные подсказки к этому
    // моменту всё равно заблокированы — коллекция пустая.
    priority: 5,
    // Один показ, а не два: подсказка появляется на стартовом экране сразу
    // после регистрации, и повторить её на следующем запуске — значит встретить
    // человека тем же текстом дважды подряд.
    maxShows: 1,
    // Пауза, чтобы экран сканера успел показаться первым. Без неё карточка
    // выезжала одновременно с камерой и читалась как перехват управления.
    delayMs: 1400,
    title: 'Как добавить пластинку',
    body: 'Сверху выбираешь: сканировать штрихкод или сфотографировать обложку. Если пластинки нет ни в Discogs, ни в Маркете — добавь вручную, кружком справа внизу.',
    unlock: 'первый заход на экран сканирования',
    where: 'Сканер → переключатель сверху, ручной ввод — кружок справа внизу',
    goTo: { route: '/(tabs)' },
    icon: 'plus',
  },
  {
    key: 'pinch-zoom',
    goTo: { route: '/(tabs)/collection', tab: 'collection' },
    priority: 10,
    title: 'Вся полка на одном экране',
    body: 'Сожми сетку двумя пальцами — останутся одни обложки, влезет вся полка. Разожми, чтобы вернуть подписи.',
    unlock: 'от 12 пластинок в коллекции',
    where: 'Коллекция → сетка',
    icon: 'grid-outline',
  },
  {
    key: 'collection-value',
    goTo: { route: '/(tabs)/collection', tab: 'collection' },
    priority: 60,
    title: 'Сколько стоит коллекция',
    body: 'Смотрим, почём такие же пластинки продают на Discogs, и переводим в рубли по курсу ЦБ.',
    unlock: 'от 5 пластинок в коллекции',
    where: 'Коллекция → шапка → ₽',
    icon: 'currency-rub',
  },
  {
    key: 'folders',
    goTo: { route: '/(tabs)/collection', tab: 'collection' },
    priority: 50,
    title: 'Пора разложить по папкам',
    body: 'Жанры, эпохи, «на продажу» — раскладывай как удобно тебе. Пластинка может лежать в нескольких папках.',
    unlock: 'от 15 пластинок в коллекции',
    where: 'Коллекция → блок «Папки»',
    icon: 'folder-outline',
  },
  {
    key: 'multi-select',
    goTo: { route: '/(tabs)/collection', tab: 'collection' },
    priority: 70,
    title: 'Можно выбирать пачкой',
    body: 'Задержи палец на обложке — включится выбор. Дальше папки, удаление и подарки сразу для нескольких.',
    unlock: 'после двух удалений подряд по одной',
    where: 'Коллекция → «Выбрать» в шапке',
    icon: 'checkmark-circle-outline',
  },
  {
    key: 'radar',
    goTo: { route: '/(tabs)/collection', tab: 'wishlist' },
    priority: 20,
    title: 'Радар следит за ценой',
    body: 'Назови цену, за которую готов купить. Пришлём пуш, когда пластинка до неё подешевеет или просто появится в продаже.',
    unlock: 'первая позиция в вишлисте',
    // Кнопка радара уже пульсирует собственным sonar'ом (два кольца,
    // opacity 0→0.55, scale до 2.6). Кольцо подсказки поверх него слилось бы
    // с ним в одно впечатление, и sonar — постоянная индикация работы радара —
    // начал бы читаться как «непрочитанный шаг онбординга». Поэтому ореол.
    spotlight: 'glow',
    where: 'Вишлист → шапка → радар',
    // Не 'options-outline': это ровно тот же глиф, что у кнопки фильтра в
    // соседней ячейке той же шапки. Подсказка, которая объясняет место, не
    // должна иконкой указывать на чужую кнопку. Ценник ближе к сути.
    icon: 'pricetag-outline',
  },
  {
    key: 'market',
    goTo: { route: '/(tabs)/collection', tab: 'wishlist' },
    priority: 30,
    title: 'Маркет знает, где купить',
    body: 'Собираем магазины, где твои пластинки есть в наличии прямо сейчас, и показываем цены рядом.',
    unlock: 'открыл карточку релиза с офферами или собрал 3 позиции в вишлисте',
    where: 'Поиск → вниз до плашки «Маркет»',
    icon: 'business-outline',
  },
  // --- Подсказки карточки релиза ---------------------------------------
  //
  // Приоритеты подобраны по «насколько непонятно без объяснения»: ярлык
  // редкости человек видит как цветную плашку без единого слова, цвет винила
  // читается как опечатка в названии, цена магазина спорит с оценкой Discogs,
  // а «другие версии» хотя бы честно подписаны кнопкой.
  {
    key: 'rarity-tiers',
    goTo: { route: '/(tabs)/collection', tab: 'collection', note: 'Открой любую пластинку с ярлыком' },
    group: 'record',
    priority: 22,
    title: 'Что значат ярлыки',
    body: 'Коллекционка — дороже $100 и почти не появляется в продаже. Лимитка — специальное издание. Популярно — на неё высокий спрос на Discogs прямо сейчас.',
    unlock: 'открыл релиз с ярлыком редкости',
    where: 'Карточка релиза → блок «Особенности»',
    icon: 'sparkle',
  },
  {
    key: 'vinyl-color',
    goTo: { route: '/(tabs)/collection', tab: 'collection', note: 'Открой любую пластинку с цветным винилом' },
    group: 'record',
    priority: 26,
    title: 'Цвет винила',
    body: 'Один и тот же альбом печатают на чёрном, цветном и прозрачном виниле. Цвет — часть конкретного издания и заметно влияет на цену.',
    unlock: 'открыл релиз с цветным винилом',
    where: 'Карточка релиза → плашка с цветом под обложкой',
    icon: 'disc-outline',
  },
  {
    key: 'offer-price',
    goTo: { route: '/(tabs)/collection', tab: 'wishlist', note: 'Открой пластинку, которая есть в магазине' },
    group: 'record',
    priority: 38,
    title: 'Цена магазина',
    body: 'Это реальный ценник конкретного магазина сейчас, а не оценка Discogs выше. Поэтому числа отличаются: одно — сколько просят, другое — сколько такие пластинки обычно стоят.',
    unlock: 'открыл релиз, который есть в наличии в магазине',
    where: 'Карточка релиза → блок «Где купить»',
    icon: 'currency-rub',
  },
  {
    key: 'other-versions',
    goTo: { route: '/(tabs)/collection', tab: 'collection', note: 'Открой любую пластинку с переизданиями' },
    group: 'record',
    priority: 44,
    title: 'Другие версии',
    body: 'Один альбом переиздают десятки раз: разные годы, страны, цвет винила. Здесь все издания этого релиза — сравни и добавь именно своё.',
    unlock: 'открыл релиз, у которого есть переиздания',
    where: 'Карточка релиза → «Смотреть другие версии релиза»',
    icon: 'grid-outline',
  },
  {
    key: 'gifts-incoming',
    // Не '/profile': карточка этой подсказки живёт в шапке вишлиста, а в
    // профиле её рисовать некому — «Показать» открывало профиль, где ничего
    // не происходило. Ведём туда, где подсказка есть; кнопку в профиле она
    // подсветит сама, когда человек нажмёт её действие.
    goTo: { route: '/(tabs)/collection', tab: 'wishlist' },
    priority: 40,
    title: 'Из вишлиста можно дарить',
    body: 'Скинь друзьям ссылку на профиль — они забронируют пластинку из вишлиста. Что именно выбрали, ты не узнаешь: сюрприз остаётся сюрпризом.',
    unlock: 'вишлист не пуст и профиль публичный',
    where: 'Профиль → Поделиться',
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
const MAX_SHOWS_DEFAULT = 2;

export interface CoachMarkState {
  /** Юзер подтвердил явно: закрыл крестиком или пошёл по действию. */
  acknowledged: boolean;
  /** Сколько раз показывали без подтверждения. */
  shows: number;
}

const EMPTY_STATE: CoachMarkState = { acknowledged: false, shows: 0 };

/** Больше не показываем: либо подтвердили, либо исчерпали лимит показов. */
export const isSuppressed = (
  state: CoachMarkState | undefined,
  key?: CoachMarkKey,
): boolean => {
  if (!state) return false;
  if (state.acknowledged) return true;
  const limit = (key && META_BY_KEY.get(key)?.maxShows) ?? MAX_SHOWS_DEFAULT;
  return state.shows >= limit;
};

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

/**
 * Группа подсказки — у каждой свой лимит «одна за запуск».
 *
 * Зачем группы. Пока слот был общий, подсказки коллекции забирали его первыми:
 * коллекция — стартовый экран, её условия сходятся раньше, чем человек вообще
 * откроет карточку релиза. В итоге подсказки самой карточки (цвет винила,
 * ярлыки, цена магазина) почти никогда не доходили до очереди — а объясняют они
 * то, что видно прямо сейчас и больше нигде не объясняется.
 *
 * Группы независимы, поэтому за запуск можно увидеть максимум две подсказки:
 * одну «про приложение» и одну «про эту пластинку». Это всё ещё не залп.
 */
export type CoachMarkGroup = 'app' | 'record';

/** Лимит «одна подсказка за запуск» — свой на каждую группу. */
const shownThisSession: Record<CoachMarkGroup, boolean> = { app: false, record: false };

export const isSessionSlotTaken = (group: CoachMarkGroup = 'app') => shownThisSession[group];

/**
 * Ревизия правил показа. Хуки подсказок подписаны на неё и перезапускают свою
 * проверку, когда правила поменялись извне.
 *
 * Зачем. Экран коллекции смонтирован всё время, пока приложение открыто.
 * Сброс подсказки из «Как это работает» менял только AsyncStorage и модульные
 * флаги — ни одна зависимость эффекта в useCoachMark при этом не двигалась,
 * эффект не перезапускался, и «Показать снова» приводило человека на экран,
 * где молча ничего не происходило.
 */
let revision = 0;
const revisionListeners = new Set<() => void>();

export const subscribeCoachMarks = (listener: () => void) => {
  revisionListeners.add(listener);
  return () => {
    revisionListeners.delete(listener);
  };
};

export const getCoachMarkRevision = () => revision;

function bumpRevision() {
  revision += 1;
  revisionListeners.forEach((l) => l());
}

/**
 * Подсказка, которую попросили показать вручную из «Как это работает».
 *
 * Ручной запрос сильнее всех обычных правил: он игнорирует лимит показов,
 * слот сессии и арбитраж приоритетов. Не игнорирует он ровно одно — наличие
 * самой цели на экране (`place` в useCoachMark): подсказка про цвет винила на
 * чёрной пластинке указывала бы в пустоту.
 *
 * Ключ живёт, пока его не заберёт подходящий экран. Поэтому «Покажи про
 * ярлыки» работает и тогда, когда нужную пластинку человек откроет через
 * минуту, а не сразу.
 */
let forcedKey: CoachMarkKey | null = null;

export function forceCoachMark(key: CoachMarkKey) {
  forcedKey = key;
  // Слот группы, наоборот, ЗАНИМАЕМ. Ручной показ проверку слота не проходит
  // (он её пропускает), а вот автоподсказки той же группы должны замолчать:
  // resetCoachMarks прямо перед этим освободил слоты, и без захвата на экран
  // приехали бы сразу две карточки — запрошенная и случайная.
  shownThisSession[getCoachMark(key).group ?? 'app'] = true;
  bumpRevision();
}

export const isForcedCoachMark = (key: CoachMarkKey) => forcedKey === key;

/** Есть ли вообще ждущий ручной запрос — и какой. */
export const getForcedCoachMark = () => forcedKey;

/** Забрать ручной запрос: показываем его ровно один раз. */
export function consumeForcedCoachMark(key: CoachMarkKey) {
  if (forcedKey !== key) return false;
  forcedKey = null;
  return true;
}

/**
 * Окно арбитража. Хуки разных подсказок монтируются в одном рендере, но их
 * эффекты и чтение AsyncStorage разъезжаются на несколько тиков. Собираем
 * заявки в течение окна и только потом выбираем победителя — иначе слот
 * забирала бы просто самая быстрая.
 */
const ARBITRATION_MS = 150;

interface PendingRequest {
  priority: number;
  group: CoachMarkGroup;
  resolve: (won: boolean) => void;
}

const pending = new Map<CoachMarkKey, PendingRequest>();
let arbitrationTimer: ReturnType<typeof setTimeout> | null = null;

function settleArbitration() {
  arbitrationTimer = null;
  const entries = [...pending.entries()];
  pending.clear();
  if (entries.length === 0) return;

  // Арбитраж идёт внутри группы: заявки из разных групп не конкурируют, у
  // каждой свой слот.
  const byGroup = new Map<CoachMarkGroup, typeof entries>();
  for (const entry of entries) {
    const group = entry[1].group;
    const bucket = byGroup.get(group);
    if (bucket) bucket.push(entry);
    else byGroup.set(group, [entry]);
  }

  for (const [group, groupEntries] of byGroup) {
    // Слот мог уйти, пока шло окно (например, подсказку сбросили из настроек и
    // тут же показали) — тогда не выигрывает никто.
    if (shownThisSession[group]) {
      groupEntries.forEach(([, req]) => req.resolve(false));
      continue;
    }
    groupEntries.sort((a, b) => a[1].priority - b[1].priority);
    shownThisSession[group] = true;
    groupEntries[0][1].resolve(true);
    groupEntries.slice(1).forEach(([, req]) => req.resolve(false));
  }
}

/**
 * Подать заявку на показ. Возвращает true ровно одной подсказке за сессию —
 * той, у которой меньше `priority` среди заявившихся в окне арбитража.
 */
export function requestCoachMark(key: CoachMarkKey): Promise<boolean> {
  const meta = getCoachMark(key);
  const group = meta.group ?? 'app';
  if (shownThisSession[group]) return Promise.resolve(false);

  const existing = pending.get(key);
  // Повторная заявка тем же ключом (перерендер) — не плодим промисы.
  if (existing) return new Promise((resolve) => existing.resolve = chain(existing.resolve, resolve));

  return new Promise<boolean>((resolve) => {
    pending.set(key, { priority: meta.priority, group, resolve });
    if (!arbitrationTimer) {
      arbitrationTimer = setTimeout(settleArbitration, ARBITRATION_MS);
    }
  });
}

/**
 * Вернуть слот, если победитель не смог показаться (компонент размонтировался,
 * пока шёл арбитраж). Без этого сессия осталась бы вовсе без подсказки.
 */
export function releaseSessionSlot(group: CoachMarkGroup = 'app') {
  shownThisSession[group] = false;
}

/** Занять слот в обход арбитража — только для ручного показа из настроек. */
export function markSessionSlot(group: CoachMarkGroup = 'app') {
  shownThisSession[group] = true;
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
  // слоты сессии: иначе пришлось бы перезапускать приложение.
  shownThisSession.app = false;
  shownThisSession.record = false;
  if (arbitrationTimer) {
    clearTimeout(arbitrationTimer);
    arbitrationTimer = null;
  }
  pending.forEach((req) => req.resolve(false));
  pending.clear();
  bumpRevision();
}
