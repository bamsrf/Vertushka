/**
 * Термальное состояние и метрики MetricKit → Sentry.
 *
 * Импорт нативного модуля ленивый и обёрнут в try/catch, как в lib/analytics.ts:
 * в Expo Go и на web modules/device-metrics отсутствует, и всё обязано тихо
 * превратиться в no-op, а не уронить старт приложения.
 *
 * Почему это вообще нужно: снаружи нагрев не померить — Power Profiler по
 * симулятору отдаёт пустой трейс, а к TestFlight-сборке Instruments не
 * подключается (get-task-allow = false у дистрибутивной подписи). MetricKit
 * работает изнутри, на боевых устройствах и без кабеля.
 */
import { Platform } from 'react-native';
import * as Sentry from '@sentry/react-native';
import type { ThermalState } from '../modules/device-metrics';

export type { ThermalState };

export interface ThermalEntry {
  state: ThermalState;
  timestamp: number;
}

/** Сколько переходов держим в памяти для /dev/thermal. */
const HISTORY_LIMIT = 100;

let native: typeof import('../modules/device-metrics').default | null = null;
let initialized = false;

const thermalHistory: ThermalEntry[] = [];
const thermalListeners = new Set<(entry: ThermalEntry) => void>();
let lastMetricSummary: Record<string, unknown> | null = null;

function loadNative() {
  if (native || Platform.OS !== 'ios') return native;
  try {
    native = require('../modules/device-metrics').default;
  } catch {
    native = null; // Expo Go или сборка без нативного модуля.
  }
  return native;
}

/**
 * Из пейлоада MetricKit достаём короткую выжимку для тела события Sentry.
 * Полный JSON весит десятки килобайт и уезжает вложением.
 *
 * Значения MetricKit сериализует строками с единицами измерения («1.5 sec»),
 * поэтому ничего не парсим в числа — кладём как есть. Все поля необязательные:
 * состав пейлоада зависит от версии iOS и от того, что реально происходило.
 */
function summarize(payload: Record<string, any>): Record<string, unknown> {
  const pick = (path: string[]): unknown => {
    let node: any = payload;
    for (const key of path) {
      if (node == null || typeof node !== 'object') return undefined;
      node = node[key];
    }
    return node;
  };

  const summary: Record<string, unknown> = {
    app_version: pick(['appVersion']),
    period_begin: pick(['timeStampBegin']),
    period_end: pick(['timeStampEnd']),
    cpu_time: pick(['cpuMetrics', 'cumulativeCPUTime']),
    cpu_instructions: pick(['cpuMetrics', 'cumulativeCPUInstructions']),
    gpu_time: pick(['gpuMetrics', 'cumulativeGPUTime']),
    scroll_hitch_ratio: pick(['animationMetrics', 'scrollHitchTimeRatio']),
    foreground_time: pick(['applicationTimeMetrics', 'cumulativeForegroundTime']),
    background_time: pick(['applicationTimeMetrics', 'cumulativeBackgroundTime']),
    avg_pixel_luminance: pick(['displayMetrics', 'averagePixelLuminance', 'averageValue']),
    peak_memory: pick(['memoryMetrics', 'peakMemoryUsage']),
  };

  for (const key of Object.keys(summary)) {
    if (summary[key] === undefined) delete summary[key];
  }
  return summary;
}

function reportMetricPayload(json: string, kind: 'metric' | 'diagnostic') {
  let parsed: Record<string, any>;
  try {
    parsed = JSON.parse(json);
  } catch {
    return; // Битый пейлоад — молча пропускаем, ронять приложение не за что.
  }

  const summary = kind === 'metric' ? summarize(parsed) : { diagnostic: true };
  if (kind === 'metric') lastMetricSummary = summary;

  if (__DEV__) {
    console.log(`[DeviceMetrics] пейлоад ${kind}`, summary);
  }

  Sentry.withScope((scope: any) => {
    scope.setLevel('info');
    scope.setContext('metrickit', summary);
    // Полный пейлоад вложением: в теле события ему не место из-за размера.
    // addAttachment есть не во всех версиях SDK — вызываем защищённо.
    if (typeof scope.addAttachment === 'function') {
      scope.addAttachment({
        filename: `metrickit-${kind}-${Date.now()}.json`,
        data: json,
        contentType: 'application/json',
      });
    }
    Sentry.captureMessage(`MetricKit ${kind} payload`, 'info');
  });
}

function recordThermal(entry: ThermalEntry) {
  thermalHistory.push(entry);
  if (thermalHistory.length > HISTORY_LIMIT) thermalHistory.shift();
  thermalListeners.forEach((cb) => cb(entry));

  if (__DEV__) {
    console.log(`[DeviceMetrics] термальное состояние: ${entry.state}`);
  }

  Sentry.setTag('thermal_state', entry.state);
  Sentry.addBreadcrumb({
    category: 'thermal',
    message: `Термальное состояние: ${entry.state}`,
    level: entry.state === 'serious' || entry.state === 'critical' ? 'warning' : 'info',
  });

  // serious/critical означают, что система уже троттлит CPU/GPU — это баг
  // производительности, а не фоновая телеметрия, и должно быть заметно.
  if (entry.state === 'serious' || entry.state === 'critical') {
    Sentry.captureMessage(`Устройство перегрелось: ${entry.state}`, 'warning');
  }
}

/**
 * Подписаться на метрики. Идемпотентно — повторные вызовы игнорируются.
 * Дёргать как можно раньше при старте: iOS отдаёт накопленные пейлоады вскоре
 * после запуска, и опоздавшая подписка их не увидит.
 */
export function initDeviceMetrics(): void {
  if (initialized) return;
  const mod = loadNative();
  if (!mod) return;
  initialized = true;

  try {
    recordThermal({ state: mod.getThermalState(), timestamp: Date.now() });

    mod.addListener('onThermalStateChange', (event) => {
      recordThermal({ state: event.state, timestamp: event.timestamp });
    });
    mod.addListener('onMetricPayload', (event) => reportMetricPayload(event.json, 'metric'));
    mod.addListener('onDiagnosticPayload', (event) => reportMetricPayload(event.json, 'diagnostic'));

    // Слушатели навешены — теперь можно забирать то, что пришло до них.
    mod.flushBufferedPayloads();

    // История за прошедшие сутки: на устройстве, которым пользовались, она
    // обычно уже есть, и ждать первой доставки не нужно.
    for (const json of mod.getPastPayloads()) {
      reportMetricPayload(json, 'metric');
    }
  } catch (error) {
    // Нативный модуль есть, но что-то пошло не так — телеметрия не тот повод,
    // чтобы ломать запуск.
    if (__DEV__) console.warn('[DeviceMetrics] инициализация не удалась', error);
  }
}

/** Текущее состояние. 'unknown', если нативного модуля нет. */
export function getCurrentThermalState(): ThermalState {
  const mod = loadNative();
  if (!mod) return 'unknown';
  try {
    return mod.getThermalState();
  } catch {
    return 'unknown';
  }
}

export function getThermalHistory(): ThermalEntry[] {
  return [...thermalHistory];
}

export function getLastMetricSummary(): Record<string, unknown> | null {
  return lastMetricSummary;
}

/** Подписка для /dev/thermal. Возвращает функцию отписки. */
export function subscribeThermal(cb: (entry: ThermalEntry) => void): () => void {
  thermalListeners.add(cb);
  return () => {
    thermalListeners.delete(cb);
  };
}

/** Есть ли нативный модуль в этой сборке — для подсказки на dev-экране. */
export function isDeviceMetricsAvailable(): boolean {
  return loadNative() !== null;
}
