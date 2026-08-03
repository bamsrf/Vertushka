//
//  DeviceMetricsModule.swift
//  Локальный модуль Вертушки: термальное состояние + MetricKit.
//
//  Зачем он есть. Нагрев устройства нельзя померить снаружи: Power Profiler в
//  Instruments по симулятору отдаёт пустой трейс, а к TestFlight-сборке вообще
//  не подключается — дистрибутивная подпись ставит get-task-allow = false.
//  Поэтому данные забираем изнутри приложения: ProcessInfo.thermalState даёт
//  состояние немедленно, MetricKit — суточную агрегацию CPU/GPU/анимаций с
//  боевых устройств.
//
//  Тонкость с доставкой. iOS отдаёт накопленные пейлоады вскоре после запуска —
//  раньше, чем JS успевает навесить слушателей. События, отправленные до этого
//  момента, теряются молча. Поэтому подписчик регистрируется в OnCreate (как
//  можно раньше), а всё пришедшее складывается в буфер и выдаётся по явному
//  flushBufferedPayloads() с JS-стороны.
//

import ExpoModulesCore
import MetricKit

/// Человекочитаемое имя термального состояния. Значения совпадают с типом
/// ThermalState в index.ts — при правке менять обе стороны.
private func thermalStateName(_ state: ProcessInfo.ThermalState) -> String {
  switch state {
  case .nominal: return "nominal"
  case .fair: return "fair"
  case .serious: return "serious"
  case .critical: return "critical"
  @unknown default: return "unknown"
  }
}

/// Подписчик MetricKit вынесен в отдельный класс: MXMetricManagerSubscriber
/// требует NSObject, а Module им не является.
private final class MetricsCollector: NSObject, MXMetricManagerSubscriber {
  /// Отправка события в JS. nil до OnCreate и после OnDestroy.
  private var emit: ((String, [String: Any]) -> Void)?

  /// Пейлоады, пришедшие до того, как JS подписался. Отдаются при flush().
  private var buffered: [(event: String, body: [String: Any])] = []
  private var didFlush = false

  /// MetricKit зовёт колбэки с фонового потока, JS-подписка живёт на главном.
  private let lock = NSLock()

  func start(emit: @escaping (String, [String: Any]) -> Void) {
    self.emit = emit
    MXMetricManager.shared.add(self)
    NotificationCenter.default.addObserver(
      self,
      selector: #selector(thermalStateChanged),
      name: ProcessInfo.thermalStateDidChangeNotification,
      object: nil
    )
  }

  func stop() {
    MXMetricManager.shared.remove(self)
    NotificationCenter.default.removeObserver(self)
    lock.lock()
    emit = nil
    buffered.removeAll()
    lock.unlock()
  }

  /// Выдать накопленное. Вызывается из JS сразу после навешивания слушателей.
  func flush() {
    lock.lock()
    let pending = buffered
    buffered.removeAll()
    didFlush = true
    let send = emit
    lock.unlock()

    guard let send else { return }
    DispatchQueue.main.async {
      for item in pending {
        send(item.event, item.body)
      }
    }
  }

  /// До flush() складываем в буфер, после — отправляем сразу.
  private func deliver(_ event: String, _ body: [String: Any]) {
    lock.lock()
    let flushed = didFlush
    let send = emit
    if !flushed {
      buffered.append((event: event, body: body))
    }
    lock.unlock()

    guard flushed, let send else { return }
    DispatchQueue.main.async { send(event, body) }
  }

  @objc private func thermalStateChanged() {
    let state = thermalStateName(ProcessInfo.processInfo.thermalState)
    // Термальные переходы не буферизуем: интересно текущее состояние, а не
    // то, каким оно было до подписки. Актуальное JS берёт через getThermalState().
    guard let send = emit else { return }
    DispatchQueue.main.async {
      send("onThermalStateChange", ["state": state, "timestamp": Date().timeIntervalSince1970 * 1000])
    }
  }

  // MARK: - MXMetricManagerSubscriber

  func didReceive(_ payloads: [MXMetricPayload]) {
    for payload in payloads {
      guard let json = String(data: payload.jsonRepresentation(), encoding: .utf8) else { continue }
      deliver("onMetricPayload", ["json": json])
    }
  }

  func didReceive(_ payloads: [MXDiagnosticPayload]) {
    for payload in payloads {
      guard let json = String(data: payload.jsonRepresentation(), encoding: .utf8) else { continue }
      deliver("onDiagnosticPayload", ["json": json])
    }
  }
}

public class DeviceMetricsModule: Module {
  private let collector = MetricsCollector()

  public func definition() -> ModuleDefinition {
    Name("DeviceMetrics")

    Events("onThermalStateChange", "onMetricPayload", "onDiagnosticPayload")

    OnCreate {
      self.collector.start { [weak self] event, body in
        self?.sendEvent(event, body)
      }
    }

    OnDestroy {
      self.collector.stop()
    }

    Function("getThermalState") { () -> String in
      thermalStateName(ProcessInfo.processInfo.thermalState)
    }

    Function("flushBufferedPayloads") {
      self.collector.flush()
    }

    /// Пейлоады за прошедшие сутки, которые система уже отдавала. Позволяет не
    /// ждать сутки до первой доставки: на устройстве, которым пользовались,
    /// история обычно уже есть.
    Function("getPastPayloads") { () -> [String] in
      MXMetricManager.shared.pastPayloads.compactMap {
        String(data: $0.jsonRepresentation(), encoding: .utf8)
      }
    }

    Function("getPastDiagnosticPayloads") { () -> [String] in
      MXMetricManager.shared.pastDiagnosticPayloads.compactMap {
        String(data: $0.jsonRepresentation(), encoding: .utf8)
      }
    }
  }
}
