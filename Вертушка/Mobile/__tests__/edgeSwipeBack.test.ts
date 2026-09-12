/// <reference types="jest" />
/**
 * Пороги Android-свайпа «назад» от левого края (lib/edgeSwipeBack.ts).
 * Сам жест — RNGH, в jest не гоняется; здесь только решающая логика.
 */
import {
  COMMIT_DISTANCE,
  COMMIT_VELOCITY,
  FOLLOW_FACTOR,
  followShift,
  isEdgeSwipeEnabledForSegment,
  shouldCommitSwipeBack,
} from '@/lib/edgeSwipeBack';

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
