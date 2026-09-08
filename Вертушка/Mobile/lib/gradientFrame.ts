/**
 * Кадр анимированного градиента: по «сырому» прогрессу shared value выбрать
 * пару соседних пресетов и долю перехода между ними.
 *
 * Чистая функция без RN-зависимостей — крутится внутри worklet'а
 * `AnimatedGradientText`, поэтому помечена `'worklet'`.
 *
 * Зачем гвард (A7 в docs/BUGS.md): на Android после `cancelAnimation` при уходе
 * с таба worklet мог получить не-число (`NaN`/`undefined`) — `presets[NaN]`
 * давал `undefined`, и `interpolateColor` падал на UI-потоке с «Cannot convert
 * undefined value to object». Любой не-конечный или отрицательный прогресс
 * сводится к нулевому кадру, индексы всегда в диапазоне `[0, count)`.
 */
export interface GradientFrame {
  fromIdx: number;
  toIdx: number;
  /** Доля перехода от `fromIdx` к `toIdx`, в `[0, 1)`. */
  t: number;
}

export function resolveGradientFrame(progress: number, count: number): GradientFrame {
  'worklet';
  if (!(count >= 1) || !Number.isFinite(count)) {
    return { fromIdx: 0, toIdx: 0, t: 0 };
  }
  const size = Math.floor(count);
  if (typeof progress !== 'number' || !Number.isFinite(progress) || progress < 0) {
    return { fromIdx: 0, toIdx: size > 1 ? 1 : 0, t: 0 };
  }
  const raw = progress % size;
  const whole = Math.floor(raw);
  const fromIdx = Math.min(Math.max(whole, 0), size - 1);
  const toIdx = (fromIdx + 1) % size;
  const t = Math.min(Math.max(raw - whole, 0), 1);
  return { fromIdx, toIdx, t };
}
