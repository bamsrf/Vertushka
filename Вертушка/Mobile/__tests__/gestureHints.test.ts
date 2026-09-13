/// <reference types="jest" />
/**
 * Правила показа жест-подсказок (lib/gestureHints.ts).
 *
 * Сам нудж — Reanimated поверх RNGH, в jest не гоняется. Здесь проверяется то,
 * из-за чего подсказка становится назойливой или, наоборот, немой: счётчик
 * показов, гашение по освоенному жесту, единственный слот на запуск и
 * возврат слота, когда показать не удалось.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  GESTURE_HINTS,
  getGestureHint,
  isGestureHintSuppressed,
  isGestureSlotTaken,
  loadGestureHintStates,
  markGestureHintShown,
  markGesturePerformed,
  releaseGestureSlot,
  resetGestureHints,
  slotOf,
  takeGestureSlot,
} from '@/lib/gestureHints';

const USER = 'user-1';

beforeEach(async () => {
  await AsyncStorage.clear();
  await resetGestureHints(USER);
});

describe('каталог', () => {
  it('ключи уникальны, приоритеты различаются', () => {
    const keys = GESTURE_HINTS.map((m) => m.key);
    const priorities = GESTURE_HINTS.map((m) => m.priority);
    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(priorities).size).toBe(priorities.length);
  });

  it('заданная дистанция ненулевая — подсказка обязана быть заметной', () => {
    GESTURE_HINTS.filter((m) => m.distance !== undefined).forEach((m) =>
      expect(Math.abs(m.distance as number)).toBeGreaterThanOrEqual(20),
    );
  });

  it('свайп «назад» дистанции не имеет — двигать нечего, он рисует себя сам', () => {
    // На iOS экран везёт нативный стек, своей shared value нет. Появление
    // здесь числа означало бы, что кто-то попробовал нуджить весь Stack.
    expect(getGestureHint('swipe-back').distance).toBeUndefined();
  });

  it('свайп «назад» важнее остальных: он живёт на каждом вложенном экране', () => {
    const others = GESTURE_HINTS.filter((m) => m.key !== 'swipe-back');
    others.forEach((m) =>
      expect(getGestureHint('swipe-back').priority).toBeLessThan(m.priority),
    );
  });

  it('нудж-подсказки объявляют дистанцию — иначе показывать нечего', () => {
    GESTURE_HINTS.filter((m) => m.key !== 'swipe-back').forEach((m) =>
      expect(typeof m.distance).toBe('number'),
    );
  });

  it('свайп-удаление не дотягивает до порога срабатывания', () => {
    // Порог удаления в NotificationSwipe — 50% от 88pt. Подсказка обязана
    // остаться заметно ниже: она показывает возможность, а не удаляет за
    // человека.
    expect(Math.abs(getGestureHint('notification-delete').distance!)).toBeLessThan(88 * 0.5);
  });

  it('свайп-ответ не дотягивает до порога ответа', () => {
    // SWIPE_REPLY_THRESHOLD в чате — 56pt.
    expect(Math.abs(getGestureHint('chat-reply').distance!)).toBeLessThan(56);
  });

  it('неизвестный ключ — явная ошибка, а не молчаливый undefined', () => {
    expect(() => getGestureHint('nope' as never)).toThrow();
  });
});

describe('счётчик показов', () => {
  it('гаснет после второго показа', async () => {
    await markGestureHintShown(USER, 'notification-delete');
    let states = await loadGestureHintStates(USER);
    expect(isGestureHintSuppressed(states.get('notification-delete'))).toBe(false);

    await markGestureHintShown(USER, 'notification-delete');
    states = await loadGestureHintStates(USER);
    expect(isGestureHintSuppressed(states.get('notification-delete'))).toBe(true);
  });

  it('чистое состояние подсказку не глушит', () => {
    expect(isGestureHintSuppressed(undefined)).toBe(false);
  });
});

describe('освоенный жест', () => {
  it('гасит подсказку сразу, не дожидаясь лимита показов', async () => {
    await markGesturePerformed(USER, 'chat-reply');
    const states = await loadGestureHintStates(USER);
    expect(isGestureHintSuppressed(states.get('chat-reply'))).toBe(true);
  });

  it('не откатывается обратно поздним показом', async () => {
    // Гонка реальна: нудж уже стартовал, человек тронул строку в ту же
    // миллисекунду. Победить обязано «освоено» — иначе счётчик перезапишет
    // 'done' на 's1', и подсказка вернётся к тому, кто жест уже знает.
    await markGesturePerformed(USER, 'chat-reply');
    await markGestureHintShown(USER, 'chat-reply');
    const states = await loadGestureHintStates(USER);
    expect(states.get('chat-reply')?.performed).toBe(true);
  });

  it('состояния разных ключей не влияют друг на друга', async () => {
    await markGesturePerformed(USER, 'chat-reply');
    const states = await loadGestureHintStates(USER);
    expect(isGestureHintSuppressed(states.get('conversation-actions'))).toBe(false);
  });

  it('состояния разных аккаунтов не пересекаются', async () => {
    await markGesturePerformed(USER, 'chat-reply');
    const other = await loadGestureHintStates('user-2');
    expect(isGestureHintSuppressed(other.get('chat-reply'))).toBe(false);
  });
});

describe('слоты «одна подсказка за запуск»', () => {
  it('второй претендент в том же слоте уходит ни с чем', () => {
    expect(takeGestureSlot('row')).toBe(true);
    expect(takeGestureSlot('row')).toBe(false);
    expect(isGestureSlotTaken('row')).toBe(true);
  });

  it('навигация и строки не отнимают запуск друг у друга', () => {
    // Регресс: с общим слотом любая строка могла съесть запуск у подсказки про
    // возврат назад, хотя та нужнее — без неё человек не знает, как уйти с
    // экрана вообще.
    takeGestureSlot('row');
    expect(isGestureSlotTaken('nav')).toBe(false);
    expect(takeGestureSlot('nav')).toBe(true);
  });

  it('свайп назад сидит в слоте навигации, остальные — в строках', () => {
    expect(slotOf('swipe-back')).toBe('nav');
    ['notification-delete', 'conversation-actions', 'chat-reply'].forEach((k) =>
      expect(slotOf(k as never)).toBe('row'),
    );
  });

  it('возврат слота даёт запуску второй шанс', () => {
    takeGestureSlot('row');
    releaseGestureSlot('row');
    expect(isGestureSlotTaken('row')).toBe(false);
    expect(takeGestureSlot('row')).toBe(true);
  });

  it('сброс из настроек освобождает оба слота — без перезапуска приложения', async () => {
    takeGestureSlot('row');
    takeGestureSlot('nav');
    await resetGestureHints(USER);
    expect(isGestureSlotTaken('row')).toBe(false);
    expect(isGestureSlotTaken('nav')).toBe(false);
  });
});

describe('сброс', () => {
  it('по одному ключу не трогает соседей', async () => {
    await markGesturePerformed(USER, 'chat-reply');
    await markGesturePerformed(USER, 'notification-delete');
    await resetGestureHints(USER, 'chat-reply');

    const states = await loadGestureHintStates(USER);
    expect(isGestureHintSuppressed(states.get('chat-reply'))).toBe(false);
    expect(isGestureHintSuppressed(states.get('notification-delete'))).toBe(true);
  });

  it('без ключа возвращает все', async () => {
    await markGesturePerformed(USER, 'chat-reply');
    await markGesturePerformed(USER, 'notification-delete');
    await resetGestureHints(USER);

    const states = await loadGestureHintStates(USER);
    GESTURE_HINTS.forEach((m) => {
      expect(isGestureHintSuppressed(states.get(m.key))).toBe(false);
    });
  });
});

describe('мостик «свайп назад сделан»', () => {
  it('без подписчика вызов безопасен — подсказки на экране может не быть', () => {
    const { notifySwipeBackPerformed } = require('@/lib/swipeBackPerformed');
    expect(() => notifySwipeBackPerformed()).not.toThrow();
  });

  it('подписчика зовут, отписка его снимает', () => {
    const {
      notifySwipeBackPerformed,
      setSwipeBackPerformedHandler,
    } = require('@/lib/swipeBackPerformed');

    const seen = jest.fn();
    const off = setSwipeBackPerformedHandler(seen);
    notifySwipeBackPerformed();
    expect(seen).toHaveBeenCalledTimes(1);

    off();
    notifySwipeBackPerformed();
    expect(seen).toHaveBeenCalledTimes(1);
  });

  it('второй подписчик перетирает первого — хост в приложении один', () => {
    const {
      notifySwipeBackPerformed,
      setSwipeBackPerformedHandler,
    } = require('@/lib/swipeBackPerformed');

    const stale = jest.fn();
    const fresh = jest.fn();
    setSwipeBackPerformedHandler(stale);
    const off = setSwipeBackPerformedHandler(fresh);
    notifySwipeBackPerformed();

    expect(stale).not.toHaveBeenCalled();
    expect(fresh).toHaveBeenCalledTimes(1);
    off();
  });

  it('отписка мёртвого хоста не гасит живого', () => {
    const {
      notifySwipeBackPerformed,
      setSwipeBackPerformedHandler,
    } = require('@/lib/swipeBackPerformed');

    const stale = jest.fn();
    const fresh = jest.fn();
    const offStale = setSwipeBackPerformedHandler(stale);
    const offFresh = setSwipeBackPerformedHandler(fresh);
    // Порядок эффектов при hot-reload: сначала подписался новый, потом
    // отписался старый. Его отписка не должна снимать чужой колбэк.
    offStale();
    notifySwipeBackPerformed();

    expect(fresh).toHaveBeenCalledTimes(1);
    offFresh();
  });
});

describe('экраны, где свайп «назад» имеет смысл', () => {
  it('подсказка молчит там же, где выключен сам жест', () => {
    const { isEdgeSwipeEnabledForSegment } = require('@/lib/edgeSwipeBack');
    // Условие показа подсказки — ровно этот предикат (SwipeBackHintHost).
    ['(tabs)', '(auth)', 'onboarding'].forEach((seg) =>
      expect(isEdgeSwipeEnabledForSegment(seg)).toBe(false),
    );
    ['record', 'master', 'messages', 'settings'].forEach((seg) =>
      expect(isEdgeSwipeEnabledForSegment(seg)).toBe(true),
    );
  });
});
