/**
 * device-metrics — термальное состояние устройства и метрики MetricKit.
 *
 * Нативная часть: ios/DeviceMetricsModule.swift. Здесь только типизированная
 * обёртка; вся логика отправки в Sentry живёт в lib/deviceMetrics.ts, чтобы
 * модуль оставался переиспользуемым и ничего не знал про приёмник данных.
 *
 * Модуль существует только на iOS и только в нативных сборках. В Expo Go и на
 * web requireNativeModule бросит — вызывающая сторона обязана это учитывать
 * (см. lib/deviceMetrics.ts, там ленивый require в try/catch).
 */
import { requireNativeModule, NativeModule } from 'expo-modules-core';

/** Значения совпадают с thermalStateName() в DeviceMetricsModule.swift. */
export type ThermalState = 'nominal' | 'fair' | 'serious' | 'critical' | 'unknown';

export interface ThermalStateChangeEvent {
  state: ThermalState;
  /** Миллисекунды epoch, как Date.now(). */
  timestamp: number;
}

export interface MetricPayloadEvent {
  /** MXMetricPayload.jsonRepresentation() как строка. Десятки килобайт. */
  json: string;
}

type DeviceMetricsEvents = {
  onThermalStateChange: (event: ThermalStateChangeEvent) => void;
  onMetricPayload: (event: MetricPayloadEvent) => void;
  onDiagnosticPayload: (event: MetricPayloadEvent) => void;
};

declare class DeviceMetricsModuleType extends NativeModule<DeviceMetricsEvents> {
  getThermalState(): ThermalState;
  /**
   * Отдать пейлоады, пришедшие до подписки. Вызывать сразу после навешивания
   * слушателей — иначе первая (самая интересная) доставка теряется.
   */
  flushBufferedPayloads(): void;
  /** История за последние сутки — чтобы не ждать первой доставки. */
  getPastPayloads(): string[];
  getPastDiagnosticPayloads(): string[];
}

export default requireNativeModule<DeviceMetricsModuleType>('DeviceMetrics');
