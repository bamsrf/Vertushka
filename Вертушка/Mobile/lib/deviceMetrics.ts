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
 * Гистограммы MetricKit — это объект вида
 * `{ histogramValue: { "0": { bucketCount, bucketStart, bucketEnd }, ... } }`.
 * Целиком они длинные, а нам от них нужны две вещи: сколько раз событие
 * случилось и насколько плохим был худший случай.
 *
 * Ключи бакетов — целочисленные строки, JS перечисляет их по возрастанию,
 * поэтому последний непустой бакет и есть худший.
 */
function histogramDigest(node: any): { count: number; worst: string } | undefined {
  const buckets = node?.histogramValue;
  if (!buckets || typeof buckets !== 'object') return undefined;

  let count = 0;
  let worst: string | undefined;
  for (const key of Object.keys(buckets)) {
    const bucket = buckets[key];
    const n = typeof bucket?.bucketCount === 'number' ? bucket.bucketCount : 0;
    if (n <= 0) continue;
    count += n;
    worst = bucket?.bucketEnd ?? bucket?.bucketStart ?? worst;
  }
  return count > 0 ? { count, worst: worst ?? 'н/д' } : undefined;
}

/**
 * Из пейлоада MetricKit достаём выжимку для тела события Sentry.
 *
 * ВАЖНО: выжимка — единственное, что доедает. GlitchTip (наш бэкенд) принимает
 * вложения с кодом 200 и молча их выбрасывает: проверено 2026-08-04 тестовым
 * envelope'ом — событие сохранилось, таблицы files_file / files_fileblob
 * остались пустыми. Поэтому всё, что нужно для разбора, обязано лежать здесь,
 * а не во вложении.
 *
 * Состав подобран под две задачи, ради которых модуль и делался: НАГРЕВ и
 * ЗАВИСАНИЯ. Отсюда cpu/gpu time и disk/network (греют), hang time и hitch
 * ratio (тормоза), luminance и peak memory (косвенные потребители).
 * Намеренно НЕ тащим signpost- и location-метрики: объём большой, к нагреву
 * отношения мало, а событие не резиновое — GlitchTip живёт на той же
 * двухгиговой машине, что и API.
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

  // Зависания. Главный сигнал «приложение подтормаживает», и до сих пор он
  // терялся целиком: histogrammedApplicationHangTime жил только во вложении.
  const hangs = histogramDigest(pick(['applicationResponsivenessMetrics', 'histogrammedApplicationHangTime']));
  const firstDraw = histogramDigest(pick(['applicationLaunchMetrics', 'histogrammedTimeToFirstDraw']));

  const summary: Record<string, unknown> = {
    app_version: pick(['appVersion']),
    period_begin: pick(['timeStampBegin']),
    period_end: pick(['timeStampEnd']),

    // Кто греет процессор и видеоядро.
    cpu_time: pick(['cpuMetrics', 'cumulativeCPUTime']),
    cpu_instructions: pick(['cpuMetrics', 'cumulativeCPUInstructions']),
    gpu_time: pick(['gpuMetrics', 'cumulativeGPUTime']),

    // Зависания и плавность.
    hang_count: hangs?.count,
    hang_worst: hangs?.worst,
    scroll_hitch_ratio: pick(['animationMetrics', 'scrollHitchTimeRatio']),
    launch_first_draw_worst: firstDraw?.worst,

    // Время работы — знаменатель для всего остального: 5 секунд CPU за минуту
    // и за час это принципиально разные истории.
    foreground_time: pick(['applicationTimeMetrics', 'cumulativeForegroundTime']),
    background_time: pick(['applicationTimeMetrics', 'cumulativeBackgroundTime']),

    // Радио и диск — вторые по вкладу в нагрев после CPU/GPU.
    cellular_download: pick(['networkTransferMetrics', 'cumulativeCellularDownload']),
    cellular_upload: pick(['networkTransferMetrics', 'cumulativeCellularUpload']),
    disk_writes: pick(['diskIOMetrics', 'cumulativeLogicalWrites']),

    // Экран и память.
    avg_pixel_luminance: pick(['displayMetrics', 'averagePixelLuminance', 'averageValue']),
    peak_memory: pick(['memoryMetrics', 'peakMemoryUsage']),
    avg_suspended_memory: pick(['memoryMetrics', 'averageSuspendedMemory', 'averageValue']),

    // Без этого выжимку не с чем сопоставить: разные модели греются по-разному.
    device: pick(['metaData', 'deviceType']),
    os: pick(['metaData', 'osVersion']),
    build: pick(['metaData', 'appBuildVersion']),
  };

  for (const key of Object.keys(summary)) {
    if (summary[key] === undefined) delete summary[key];
  }
  return summary;
}

/**
 * Выжимка диагностического пейлоада (MXDiagnosticPayload).
 *
 * Раньше сюда уходило `{ diagnostic: true }`, а всё содержимое — во вложение.
 * С GlitchTip, который вложения выбрасывает, это означало событие с нулём
 * информации: «диагностика пришла», и всё. Между тем именно здесь лежат
 * зависания (hangDuration) и CPU-исключения — то, ради чего модуль и писался.
 *
 * callStackTree намеренно не тащим: это десятки килобайт на один инцидент.
 * Для «что и насколько плохо» хватает счётчиков и метаданных; когда понадобится
 * конкретный стек, будет ясно, какой именно инцидент воспроизводить.
 */
function summarizeDiagnostic(payload: Record<string, any>): Record<string, unknown> {
  const summary: Record<string, unknown> = {
    device: payload?.metaData?.deviceType,
    os: payload?.metaData?.osVersion,
    build: payload?.metaData?.appBuildVersion,
  };

  // [ключ в пейлоаде, префикс в выжимке, какие поля метаданных интересны]
  const groups: Array<[string, string, string[]]> = [
    ['hangDiagnostics', 'hang', ['hangDuration']],
    ['cpuExceptionDiagnostics', 'cpu_exception', ['totalCPUTime', 'totalSampledTime']],
    ['diskWriteExceptionDiagnostics', 'disk_write_exception', ['writesCaused']],
    ['appLaunchDiagnostics', 'app_launch', ['launchDuration']],
    ['crashDiagnostics', 'crash', ['exceptionType', 'exceptionCode', 'signal', 'terminationReason']],
  ];

  for (const [key, prefix, fields] of groups) {
    const list = payload?.[key];
    if (!Array.isArray(list) || list.length === 0) continue;

    summary[`${prefix}_count`] = list.length;
    // Метаданные берём у первого инцидента: в одном пейлоаде они однотипны,
    // а разбирать нужно всё равно по одному.
    const meta = list[0]?.diagnosticMetaData ?? {};
    for (const field of fields) {
      if (meta[field] !== undefined) summary[`${prefix}_${field}`] = meta[field];
    }
  }

  // Так же, как в summarize(): пустые ключи не тащим, чтобы событие не
  // распухало от undefined-полей на пейлоадах без метаданных.
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

  const summary = kind === 'metric' ? summarize(parsed) : summarizeDiagnostic(parsed);
  if (kind === 'metric') lastMetricSummary = summary;

  if (__DEV__) {
    console.log(`[DeviceMetrics] пейлоад ${kind}`, summary);
  }

  Sentry.withScope((scope: any) => {
    scope.setLevel('info');
    scope.setContext('metrickit', summary);
    // Полный пейлоад вложением. На GlitchTip это пустая формальность — он
    // отвечает 200 и выбрасывает вложение молча (проверено 2026-08-04), — но
    // вызов оставлен: он ничего не стоит, а при переезде на настоящий Sentry
    // сразу даст полные данные без правки кода.
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
