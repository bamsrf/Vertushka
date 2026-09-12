/// <reference types="jest" />
/**
 * Пороги Android-свайпа «назад» с любого места экрана (lib/edgeSwipeBack.ts).
 * Сам жест — RNGH, в jest не гоняется; здесь только решающая логика и
 * инварианты порогов, от которых зависит приоритет соседних жестов.
 */
import {
  ACTIVE_OFFSET_X,
  BACKDROP_MAX_OPACITY,
  backdropOpacity,
  COMMIT_FRACTION,
  COMMIT_VELOCITY,
  FAIL_OFFSET_X,
  FAIL_OFFSET_Y,
  followShift,
  isEdgeSwipeEnabledForSegment,
  shouldCommitSwipeBack,
  swipeProgress,
  useSwipeBackPopStore,
} from '@/lib/edgeSwipeBack';

const WIDTH = 400;

describe('пороги активации', () => {
  it('активация позже любого своего Gesture.Pan (≤12dp) и touch-slop скролла (~8dp)', () => {
    // Иначе полноэкранный свайп начнёт перебивать карусели и свайп-строки:
    // в RNGH побеждает первый активировавшийся жест.
    expect(ACTIVE_OFFSET_X).toBeGreaterThan(12);
  });

  it('но не настолько поздно, чтобы старт ощущался задержкой', () => {
    expect(ACTIVE_OFFSET_X).toBeLessThanOrEqual(20);
  });

  it('движение влево и вертикаль сдают жест раньше, чем он активируется', () => {
    expect(FAIL_OFFSET_X).toBeGreaterThan(0);
    expect(FAIL_OFFSET_X).toBeLessThan(ACTIVE_OFFSET_X);
    expect(FAIL_OFFSET_Y).toBeLessThan(ACTIVE_OFFSET_X);
  });

  it('commit по дистанции дальше активации даже на узком окне', () => {
    expect(320 * COMMIT_FRACTION).toBeGreaterThan(ACTIVE_OFFSET_X);
  });
});

describe('shouldCommitSwipeBack', () => {
  const distance = WIDTH * COMMIT_FRACTION;

  it('дотянул дальше 35% ширины — уходим назад', () => {
    expect(shouldCommitSwipeBack({ translationX: distance + 1, velocityX: 0 }, WIDTH)).toBe(true);
  });

  it('короткий, но быстрый швырок — уходим назад', () => {
    expect(shouldCommitSwipeBack({ translationX: 30, velocityX: COMMIT_VELOCITY + 1 }, WIDTH)).toBe(true);
  });

  it('недотянул и медленно — остаёмся', () => {
    expect(shouldCommitSwipeBack({ translationX: distance, velocityX: COMMIT_VELOCITY }, WIDTH)).toBe(false);
  });

  it('порог зависит от ширины окна', () => {
    expect(shouldCommitSwipeBack({ translationX: 150, velocityX: 0 }, 400)).toBe(true);
    expect(shouldCommitSwipeBack({ translationX: 150, velocityX: 0 }, 800)).toBe(false);
  });

  it('движение влево не считается, даже быстрое', () => {
    expect(shouldCommitSwipeBack({ translationX: -200, velocityX: -2000 }, WIDTH)).toBe(false);
  });
});

describe('followShift', () => {
  it('едет за пальцем 1:1', () => {
    expect(followShift(100, 0)).toBe(100);
  });

  it('стартует с нуля: порог активации вычитается, прыжка нет', () => {
    expect(followShift(ACTIVE_OFFSET_X, ACTIVE_OFFSET_X)).toBe(0);
    expect(followShift(ACTIVE_OFFSET_X + 40, ACTIVE_OFFSET_X)).toBe(40);
  });

  it('влево контент не уезжает', () => {
    expect(followShift(-50, 0)).toBe(0);
    expect(followShift(5, ACTIVE_OFFSET_X)).toBe(0);
  });
});

describe('подложка', () => {
  it('прогресс ограничен 0..1 и не делит на ноль', () => {
    expect(swipeProgress(-10, WIDTH)).toBe(0);
    expect(swipeProgress(WIDTH / 2, WIDTH)).toBeCloseTo(0.5);
    expect(swipeProgress(WIDTH * 2, WIDTH)).toBe(1);
    expect(swipeProgress(100, 0)).toBe(0);
  });

  it('темнее в начале, прозрачна, когда экран уехал', () => {
    expect(backdropOpacity(0)).toBeCloseTo(BACKDROP_MAX_OPACITY);
    expect(backdropOpacity(1)).toBeCloseTo(0);
    expect(BACKDROP_MAX_OPACITY).toBeLessThan(0.5);
  });
});

describe('useSwipeBackPopStore', () => {
  it('по умолчанию pop анимируется нативно', () => {
    expect(useSwipeBackPopStore.getState().popWithoutAnimation).toBe(false);
  });

  it('флаг поднимается на время свайпа и опускается обратно', () => {
    useSwipeBackPopStore.getState().setPopWithoutAnimation(true);
    expect(useSwipeBackPopStore.getState().popWithoutAnimation).toBe(true);
    useSwipeBackPopStore.getState().setPopWithoutAnimation(false);
    expect(useSwipeBackPopStore.getState().popWithoutAnimation).toBe(false);
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
