/**
 * Remote config — force-update gate и kill-switch фич.
 *
 * Главное правило: **fail-open**. Если конфиг не доехал (сеть моргнула,
 * бэкенд лёг, таймаут) — пускаем пользователя дальше и считаем все фичи
 * включёнными. Гейт, который блокирует людей при первой же сетевой ошибке,
 * вреднее, чем отсутствие гейта.
 *
 * См. Backend/app/api/app_config.py, docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.2.
 */
import { create } from 'zustand';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { api } from './api';
import { isVersionBelow } from './version';
import { AppConfig } from './types';

/** Версия текущего билда из app.json. Пустая строка = не смогли определить. */
export const APP_VERSION = (Constants.expoConfig?.version as string | undefined) ?? '';

/**
 * Свести конфиг к текущей платформе: `platforms[os] ?? legacy`.
 *
 * Возвращает тот же AppConfig, но с `min_supported_version` и `store_url`
 * своей платформы — так экран force-update и гейт читают привычные поля.
 * На iOS бэкенд гарантирует platforms.ios === legacy, то есть результат
 * совпадает с сырым ответом; на Android подставляется Play URL.
 */
export function resolveForPlatform(
  config: AppConfig,
  os: string = Platform.OS,
): AppConfig {
  const platform = os === 'ios' || os === 'android' ? config.platforms?.[os] : undefined;
  if (!platform) return config;
  return {
    ...config,
    min_supported_version: platform.min_supported_version || config.min_supported_version,
    store_url: platform.store_url || config.store_url,
  };
}

interface RemoteConfigState {
  /** Конфиг доехал; null — ещё не пробовали или не доехал (fail-open). */
  config: AppConfig | null;
  /** Проверка завершена (успехом или нет) — можно рендерить приложение. */
  isChecked: boolean;
  /** Версия ниже минимальной → показать блокирующий экран. */
  needsUpdate: boolean;
  load: () => Promise<void>;
  /** Включена ли фича. Неизвестная фича считается включённой. */
  isEnabled: (flag: string) => boolean;
}

export const useRemoteConfigStore = create<RemoteConfigState>((set, get) => ({
  config: null,
  isChecked: false,
  needsUpdate: false,

  load: async () => {
    try {
      const config = resolveForPlatform(await api.getAppConfig());
      set({
        config,
        isChecked: true,
        needsUpdate: isVersionBelow(APP_VERSION, config.min_supported_version),
      });
    } catch {
      // Fail-open: не знаем — значит не мешаем.
      set({ config: null, isChecked: true, needsUpdate: false });
    }
  },

  isEnabled: (flag: string) => {
    const flags = get().config?.flags;
    if (!flags || !(flag in flags)) return true;
    return flags[flag];
  },
}));

/** Хук для UI: `const marketOn = useFeatureFlag('market')`. */
export function useFeatureFlag(flag: string): boolean {
  return useRemoteConfigStore((state) => {
    const flags = state.config?.flags;
    if (!flags || !(flag in flags)) return true;
    return flags[flag];
  });
}
