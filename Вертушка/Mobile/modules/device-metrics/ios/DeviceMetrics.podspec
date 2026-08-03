Pod::Spec.new do |s|
  s.name           = 'DeviceMetrics'
  s.version        = '1.0.0'
  s.summary        = 'Термальное состояние устройства и метрики MetricKit'
  s.description    = 'Локальный модуль Вертушки: ProcessInfo.thermalState + MXMetricManager.'
  s.author         = 'Вертушка'
  s.homepage       = 'https://vinyl-vertushka.ru'
  s.license        = { :type => 'MIT' }
  s.platforms      = { :ios => '15.1' }
  s.swift_version  = '5.9'
  s.source         = { git: '' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_COMPILATION_MODE' => 'wholemodule'
  }

  s.source_files = "**/*.{h,m,mm,swift,hpp,cpp}"
end
