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

  it('дистанция ненулевая — подсказка обязана быть заметной', () => {
    GESTURE_HINTS.forEach((m) => expect(Math.abs(m.distance)).toBeGreaterThanOrEqual(20));
  });

  it('свайп-удаление не дотягивает до порога срабатывания', () => {
    // Порог удаления в NotificationSwipe — 50% от 88pt. Подсказка обязана
    // остаться заметно ниже: она показывает возможность, а не удаляет за
    // человека.
    expect(Math.abs(getGestureHint('notification-delete').distance)).toBeLessThan(88 * 0.5);
  });

  it('свайп-ответ не дотягивает до порога ответа', () => {
    // SWIPE_REPLY_THRESHOLD в чате — 56pt.
    expect(Math.abs(getGestureHint('chat-reply').distance)).toBeLessThan(56);
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

describe('слот «одна подсказка за запуск»', () => {
  it('второй претендент уходит ни с чем', () => {
    expect(takeGestureSlot()).toBe(true);
    expect(takeGestureSlot()).toBe(false);
    expect(isGestureSlotTaken()).toBe(true);
  });

  it('возврат слота даёт запуску второй шанс', () => {
    takeGestureSlot();
    releaseGestureSlot();
    expect(isGestureSlotTaken()).toBe(false);
    expect(takeGestureSlot()).toBe(true);
  });

  it('сброс из настроек освобождает слот — без перезапуска приложения', async () => {
    takeGestureSlot();
    await resetGestureHints(USER);
    expect(isGestureSlotTaken()).toBe(false);
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
