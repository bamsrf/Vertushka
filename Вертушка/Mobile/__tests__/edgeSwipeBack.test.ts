/// <reference types="jest" />
/**
 * Пороги Android-свайпа «назад» с любого места экрана (lib/edgeSwipeBack.ts).
 * Сам жест — RNGH, в jest не гоняется; здесь только решающая логика и
 * инварианты порогов, от которых зависит приоритет соседних жестов.
 */
import {
  ACTIVE_OFFSET_X,
  COMMIT_DISTANCE,
  COMMIT_VELOCITY,
  FAIL_OFFSET_X,
  FAIL_OFFSET_Y,
  FOLLOW_FACTOR,
  followShift,
  isEdgeSwipeEnabledForSegment,
  shouldCommitSwipeBack,
} from '@/lib/edgeSwipeBack';

describe('пороги активации', () => {
  it('активация позже любого своего Gesture.Pan (≤12dp) и touch-slop скролла (~8dp)', () => {
    // Иначе полноэкранный свайп начнёт перебивать карусели и свайп-строки:
    // в RNGH побеждает первый активировавшийся жест.
    expect(ACTIVE_OFFSET_X).toBeGreaterThan(12);
  });

  it('движение влево и вертикаль сдают жест раньше, чем он активируется', () => {
    expect(FAIL_OFFSET_X).toBeGreaterThan(0);
    expect(FAIL_OFFSET_X).toBeLessThan(ACTIVE_OFFSET_X);
    expect(FAIL_OFFSET_Y).toBeLessThan(ACTIVE_OFFSET_X);
  });

  it('commit по дистанции дальше активации — случайное касание не уводит назад', () => {
    expect(COMMIT_DISTANCE).toBeGreaterThan(ACTIVE_OFFSET_X);
  });
});

describe('shouldCommitSwipeBack', () => {
  it('дотянул дальше порога — уходим назад', () => {
    expect(shouldCommitSwipeBack({ translationX: COMMIT_DISTANCE + 1, velocityX: 0 })).toBe(true);
  });

  it('короткий, но быстрый швырок — уходим назад', () => {
    expect(shouldCommitSwipeBack({ translationX: 30, velocityX: COMMIT_VELOCITY + 1 })).toBe(true);
  });

  it('недотянул и медленно — остаёмся', () => {
    expect(shouldCommitSwipeBack({ translationX: COMMIT_DISTANCE, velocityX: COMMIT_VELOCITY })).toBe(false);
  });

  it('движение влево не считается, даже быстрое', () => {
    expect(shouldCommitSwipeBack({ translationX: -200, velocityX: -2000 })).toBe(false);
  });
});

describe('followShift', () => {
  it('едет за пальцем с коэффициентом', () => {
    expect(followShift(100)).toBeCloseTo(100 * FOLLOW_FACTOR);
  });

  it('влево контент не уезжает', () => {
    expect(followShift(-50)).toBe(0);
  });
});

describe('isEdgeSwipeEnabledForSegment', () => {
  it('на табах, auth и онбординге выключен', () => {
    expect(isEdgeSwipeEnabledForSegment('(tabs)')).toBe(false);
    expect(isEdgeSwipeEnabledForSegment('(auth)')).toBe(false);
    expect(isEdgeSwipeEnabledForSegment('onboarding')).toBe(false);
  });

  it('на stack-экранах и модалках включен', () => {
    expect(isEdgeSwipeEnabledForSegment('record')).toBe(true);
    expect(isEdgeSwipeEnabledForSegment('artist')).toBe(true);
    expect(isEdgeSwipeEnabledForSegment('user')).toBe(true);
    expect(isEdgeSwipeEnabledForSegment('profile')).toBe(true);
  });

  it('пустые сегменты (ещё не смонтировано) — включен, гард canGoBack прикроет', () => {
    expect(isEdgeSwipeEnabledForSegment(undefined)).toBe(true);
  });
});
