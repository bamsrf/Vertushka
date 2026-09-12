/// <reference types="jest" />
/**
 * Чистая логика Android-overdrag'а Маркета (lib/androidOverdrag.ts).
 * Сам жест — RNGH, в jest не гоняется; здесь резинка, порог commit'а,
 * гейт «у края» и инварианты констант.
 */
import {
  contentShiftOf,
  fingerPull,
  isAtEdge,
  MAX_PULL_FRACTION,
  MISS_MIN_FRACTION,
  PAN_ACTIVE_OFFSET_Y,
  pullFractionOf,
  RUBBER_BAND_COEFF,
  rubberBand,
  shouldCommit,
  shouldFireMiss,
} from '@/lib/androidOverdrag';

const H = 800;
const COMMIT_DISTANCE = 110;

describe('rubberBand', () => {
  it('формула UIScrollView: (1 − 1/(x·c/H + 1))·H', () => {
    const x = 150;
    const expected = (1 - 1 / ((x * RUBBER_BAND_COEFF) / H + 1)) * H;
    expect(rubberBand(x, H)).toBeCloseTo(expected, 6);
  });

  it('вьюпорт не измерен (H <= 0) → 0, а не NaN/Infinity', () => {
    expect(rubberBand(100, 0)).toBe(0);
    expect(rubberBand(100, -1)).toBe(0);
    expect(Number.isNaN(rubberBand(100, 0))).toBe(false);
  });

  it('нет хода или откат → 0', () => {
    expect(rubberBand(0, H)).toBe(0);
    expect(rubberBand(-40, H)).toBe(0);
  });

  it('монотонно растёт и не достигает высоты вьюпорта', () => {
    let prev = 0;
    for (let x = 1; x <= 3000; x += 7) {
      const y = rubberBand(x, H);
      expect(y).toBeGreaterThan(prev);
      expect(y).toBeLessThan(H);
      prev = y;
    }
  });

  it('сопротивление: overdrag всегда меньше хода пальца', () => {
    expect(rubberBand(100, H)).toBeLessThan(100);
    expect(rubberBand(1000, H)).toBeLessThan(1000);
  });

  it('порог 110 offset-единиц при H≈800 — порядка 230dp хода после активации', () => {
    // Первые PAN_ACTIVE_OFFSET_Y dp теряются до активации Pan, реальный ход
    // ≈ 240dp; ровно 230 не обещаем — только коридор.
    const reach = (target: number) => {
      let x = 0;
      while (rubberBand(x, H) < target) x += 1;
      return x;
    };
    const finger = reach(COMMIT_DISTANCE);
    expect(finger).toBeGreaterThan(200);
    expect(finger).toBeLessThan(260);
    expect(finger + PAN_ACTIVE_OFFSET_Y).toBeLessThan(300);
  });
});

describe('pullFractionOf', () => {
  it('overdrag / distance, ограничен сверху MAX_PULL_FRACTION', () => {
    expect(pullFractionOf(55, COMMIT_DISTANCE)).toBeCloseTo(0.5);
    expect(pullFractionOf(110, COMMIT_DISTANCE)).toBeCloseTo(1);
    expect(pullFractionOf(10000, COMMIT_DISTANCE)).toBe(MAX_PULL_FRACTION);
  });

  it('отрицательный overdrag и нулевая дистанция → 0', () => {
    expect(pullFractionOf(-5, COMMIT_DISTANCE)).toBe(0);
    expect(pullFractionOf(50, 0)).toBe(0);
  });
});

describe('порог commit / miss', () => {
  it('commit ровно с 1', () => {
    expect(shouldCommit(0.99)).toBe(false);
    expect(shouldCommit(1)).toBe(true);
    expect(shouldCommit(MAX_PULL_FRACTION)).toBe(true);
  });

  it('miss — тянул всерьёз, но не дотянул', () => {
    expect(shouldFireMiss(MISS_MIN_FRACTION)).toBe(false);
    expect(shouldFireMiss(MISS_MIN_FRACTION + 0.01)).toBe(true);
    expect(shouldFireMiss(0.9)).toBe(true);
    expect(shouldFireMiss(1)).toBe(false);
  });

  it('commit и miss взаимоисключающи на всём диапазоне', () => {
    for (let p = 0; p <= MAX_PULL_FRACTION; p += 0.01) {
      expect(shouldCommit(p) && shouldFireMiss(p)).toBe(false);
    }
  });
});

describe('isAtEdge', () => {
  const CONTENT = 2000;
  const MAX_Y = CONTENT - H;

  it('вьюпорт не измерен — края нет', () => {
    expect(isAtEdge('bottom', 0, CONTENT, 0)).toBe(false);
    expect(isAtEdge('top', 0, CONTENT, 0)).toBe(false);
  });

  it('низ: только у maxY с допуском 1px', () => {
    expect(isAtEdge('bottom', MAX_Y, CONTENT, H)).toBe(true);
    expect(isAtEdge('bottom', MAX_Y - 1, CONTENT, H)).toBe(true);
    expect(isAtEdge('bottom', MAX_Y - 2, CONTENT, H)).toBe(false);
    expect(isAtEdge('bottom', 0, CONTENT, H)).toBe(false);
  });

  it('верх: только у нуля с допуском 1px', () => {
    expect(isAtEdge('top', 0, CONTENT, H)).toBe(true);
    expect(isAtEdge('top', 1, CONTENT, H)).toBe(true);
    expect(isAtEdge('top', 2, CONTENT, H)).toBe(false);
    expect(isAtEdge('top', MAX_Y, CONTENT, H)).toBe(false);
  });

  it('контент короче вьюпорта — тянуть нельзя (как iOS без alwaysBounceVertical)', () => {
    expect(isAtEdge('bottom', 0, H - 100, H)).toBe(false);
    expect(isAtEdge('top', 0, H - 100, H)).toBe(false);
    expect(isAtEdge('bottom', 0, H, H)).toBe(false);
  });

  it('контент ещё не измерен (Infinity): низ недостижим, верх — по scrollY', () => {
    expect(isAtEdge('bottom', 0, Infinity, H)).toBe(false);
    expect(isAtEdge('top', 0, Infinity, H)).toBe(true);
  });

  it('рост контента во время тяги (пагинация) выбивает из края', () => {
    expect(isAtEdge('bottom', MAX_Y, CONTENT, H)).toBe(true);
    expect(isAtEdge('bottom', MAX_Y, CONTENT + 600, H)).toBe(false);
  });
});

describe('fingerPull / contentShiftOf', () => {
  it('низ: тянут вверх — translationY убывает', () => {
    expect(fingerPull('bottom', -120, -20)).toBe(100);
    expect(fingerPull('bottom', 30, -20)).toBe(-50);
  });

  it('верх: тянут вниз — translationY растёт', () => {
    expect(fingerPull('top', 120, 20)).toBe(100);
    expect(fingerPull('top', -30, 20)).toBe(-50);
  });

  it('контент уезжает от края: вверх у низа, вниз у верха', () => {
    expect(contentShiftOf('bottom', 40)).toBe(-40);
    expect(contentShiftOf('top', 40)).toBe(40);
  });
});

describe('константы', () => {
  it('активация Pan не раньше touch-slop OEM (8–12dp), но без ощутимой задержки', () => {
    expect(PAN_ACTIVE_OFFSET_Y).toBeGreaterThanOrEqual(8);
    expect(PAN_ACTIVE_OFFSET_Y).toBeLessThanOrEqual(16);
  });

  it('коэффициент резинки — как у UIScrollView', () => {
    expect(RUBBER_BAND_COEFF).toBeCloseTo(0.55);
  });
});
