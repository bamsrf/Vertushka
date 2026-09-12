/// <reference types="jest" />
/**
 * Compact-boost (+12% к шрифтам на ширине ≤ 375) — только iOS.
 *
 * iPhone Mini/SE в 375pt — физически маленький экран, буст там лечит мелкий
 * текст. Android-телефон в 360dp (realme/oppo/samsung) — это 6.5" экран, буст
 * раздувал текст и ломал слова по слогам («Разреши те уведо мления»).
 *
 * Гейт «iOS не меняется»: цифры для iOS при 360 обязаны совпадать с прежней
 * формулой `(size + (size*scale - size)*factor) * 1.12`.
 */
import { compactBoostFor, moderateScaleFor, widthScaleFor } from '@/lib/responsive';

const NARROW = 360;
const REFERENCE = 393;

/** Прежняя формула ms() до правки — эталон для iOS. */
function legacyMs(size: number, factor: number, screenWidth: number): number {
  const scale = Math.min(Math.max(screenWidth / REFERENCE, 0.9), 1.3);
  const boost = screenWidth <= 375 ? 1.12 : 1;
  return (size + (size * scale - size) * factor) * boost;
}

describe('compactBoostFor', () => {
  it('iOS при 360 и 375 — буст 1.12, шире — нет', () => {
    expect(compactBoostFor('ios', NARROW)).toBe(1.12);
    expect(compactBoostFor('ios', 375)).toBe(1.12);
    expect(compactBoostFor('ios', REFERENCE)).toBe(1);
  });

  it('Android при 360 — буста нет', () => {
    expect(compactBoostFor('android', NARROW)).toBe(1);
    expect(compactBoostFor('android', 375)).toBe(1);
    expect(compactBoostFor('android', 412)).toBe(1);
  });
});

describe('moderateScaleFor при ширине 360', () => {
  it('iOS: совпадает с прежней формулой (буст остался)', () => {
    for (const size of [10.5, 12, 14, 17, 18]) {
      expect(moderateScaleFor(size, 0.5, { os: 'ios', screenWidth: NARROW })).toBeCloseTo(
        legacyMs(size, 0.5, NARROW),
        6,
      );
    }
  });

  it('Android: только clamp-скейл ширины, без буста', () => {
    const scale = widthScaleFor(NARROW);
    expect(scale).toBeCloseTo(360 / 393, 6);
    for (const size of [10.5, 12, 14, 17, 18]) {
      const expected = size + (size * scale - size) * 0.5;
      expect(moderateScaleFor(size, 0.5, { os: 'android', screenWidth: NARROW })).toBeCloseTo(expected, 6);
    }
  });

  it('Android при 360 меньше iOS при 360 ровно на буст', () => {
    const ios = moderateScaleFor(14, 0.5, { os: 'ios', screenWidth: NARROW });
    const android = moderateScaleFor(14, 0.5, { os: 'android', screenWidth: NARROW });
    expect(ios / android).toBeCloseTo(1.12, 6);
  });

  it('на эталонной ширине 393 обе платформы отдают size как есть', () => {
    expect(moderateScaleFor(14, 0.5, { os: 'ios', screenWidth: REFERENCE })).toBe(14);
    expect(moderateScaleFor(14, 0.5, { os: 'android', screenWidth: REFERENCE })).toBe(14);
  });
});

describe('ms() на живом модуле под мок Dimensions/Platform (ширина 360)', () => {
  function loadMs(os: 'ios' | 'android'): (size: number, factor?: number) => number {
    let ms: (size: number, factor?: number) => number = () => NaN;
    jest.isolateModules(() => {
      jest.doMock('react-native/Libraries/Utilities/Dimensions', () => ({
        __esModule: true,
        default: {
          get: () => ({ width: NARROW, height: 800, scale: 2, fontScale: 1 }),
          addEventListener: () => ({ remove: () => {} }),
        },
      }));
      jest.doMock('react-native/Libraries/Utilities/Platform', () => ({
        __esModule: true,
        default: {
          OS: os,
          select: (spec: Record<string, unknown>) => (os in spec ? spec[os] : spec.default),
          isTV: false,
          constants: {},
        },
      }));
      ms = require('@/lib/responsive').ms;
    });
    return ms;
  }

  afterEach(() => {
    jest.dontMock('react-native/Libraries/Utilities/Dimensions');
    jest.dontMock('react-native/Libraries/Utilities/Platform');
  });

  /** Как ms(): PixelRatio.roundToNearestPixel при scale 2, затем Math.round. */
  const roundPx = (v: number) => Math.round(Math.round(v * 2) / 2);

  it('iOS 360: ms(14) с бустом = 15 (как раньше)', () => {
    expect(loadMs('ios')(14)).toBe(roundPx(legacyMs(14, 0.5, NARROW)));
    expect(loadMs('ios')(14)).toBe(15);
  });

  it('Android 360: ms(14) без буста = 14 (13.41 → ближайший пиксель 13.5 → 14)', () => {
    expect(loadMs('android')(14)).toBe(roundPx(moderateScaleFor(14, 0.5, { os: 'android', screenWidth: NARROW })));
    expect(loadMs('android')(14)).toBe(14);
    expect(loadMs('android')(18)).toBeLessThan(loadMs('ios')(18));
  });
});
