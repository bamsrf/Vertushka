import { resolveGradientFrame } from '../lib/gradientFrame';

const COUNT = 7;

describe('resolveGradientFrame', () => {
  it('нормальный прогресс: соседние индексы и дробная доля', () => {
    expect(resolveGradientFrame(0, COUNT)).toEqual({ fromIdx: 0, toIdx: 1, t: 0 });
    expect(resolveGradientFrame(2.25, COUNT)).toEqual({ fromIdx: 2, toIdx: 3, t: 0.25 });
    expect(resolveGradientFrame(6.5, COUNT)).toEqual({ fromIdx: 6, toIdx: 0, t: 0.5 });
  });

  it('конец цикла и переполнение заворачиваются по модулю', () => {
    expect(resolveGradientFrame(COUNT, COUNT)).toEqual({ fromIdx: 0, toIdx: 1, t: 0 });
    expect(resolveGradientFrame(COUNT + 1.5, COUNT)).toEqual({ fromIdx: 1, toIdx: 2, t: 0.5 });
  });

  it('A7: NaN / undefined / Infinity не выходят за пределы пресетов', () => {
    for (const bad of [NaN, Infinity, -Infinity, undefined, null, 'x']) {
      const frame = resolveGradientFrame(bad as unknown as number, COUNT);
      expect(frame).toEqual({ fromIdx: 0, toIdx: 1, t: 0 });
    }
  });

  it('отрицательный прогресс сводится к нулевому кадру', () => {
    expect(resolveGradientFrame(-0.5, COUNT)).toEqual({ fromIdx: 0, toIdx: 1, t: 0 });
  });

  it('вырожденный набор пресетов не даёт индекс вне диапазона', () => {
    const single = resolveGradientFrame(3.7, 1);
    expect(single.fromIdx).toBe(0);
    expect(single.toIdx).toBe(0);
    expect(single.t).toBeCloseTo(0.7);
    expect(resolveGradientFrame(3.7, 0)).toEqual({ fromIdx: 0, toIdx: 0, t: 0 });
    expect(resolveGradientFrame(3.7, NaN)).toEqual({ fromIdx: 0, toIdx: 0, t: 0 });
  });

  it('индексы всегда целые в [0, count) на плотной сетке значений', () => {
    for (let p = -3; p < 20; p += 0.137) {
      const { fromIdx, toIdx, t } = resolveGradientFrame(p, COUNT);
      expect(Number.isInteger(fromIdx)).toBe(true);
      expect(fromIdx).toBeGreaterThanOrEqual(0);
      expect(fromIdx).toBeLessThan(COUNT);
      expect(toIdx).toBe((fromIdx + 1) % COUNT);
      expect(t).toBeGreaterThanOrEqual(0);
      expect(t).toBeLessThan(1);
    }
  });
});
