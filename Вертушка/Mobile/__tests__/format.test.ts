/// <reference types="jest" />
/**
 * formatGroupedWorklet — та же строка, что даёт `toLocaleString('ru-RU')`
 * (разделитель U+00A0), но без Intl: гоняется в worklet'е счётчика стоимости.
 */
import { formatGroupedWorklet } from '@/lib/format';

const NBSP = ' ';

test('группирует тысячи неразрывным пробелом', () => {
  expect(formatGroupedWorklet(0)).toBe('0');
  expect(formatGroupedWorklet(999)).toBe('999');
  expect(formatGroupedWorklet(1000)).toBe(`1${NBSP}000`);
  expect(formatGroupedWorklet(1234567)).toBe(`1${NBSP}234${NBSP}567`);
  expect(formatGroupedWorklet(1234567.6)).toBe(`1${NBSP}234${NBSP}568`);
  expect(formatGroupedWorklet(-1500)).toBe(`-1${NBSP}500`);
});

test('совпадает с toLocaleString("ru-RU") по цифрам', () => {
  for (const n of [7, 42, 1000, 87654, 1234567, 98765432]) {
    expect(formatGroupedWorklet(n).replace(/\s/g, '')).toBe(
      n.toLocaleString('ru-RU').replace(/\s/g, '')
    );
  }
});
