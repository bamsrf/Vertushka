/**
 * Регистрация Expo push-токена.
 *
 * Системный промпт разрешения НЕ показываем на холодном старте (низкий opt-in,
 * плохо смотрится на App Review). requestIfNeeded=true — только из контекстных
 * точек: экран сообщений, настройки уведомлений.
 */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { api } from './api';

export async function registerPushToken(
  { requestIfNeeded }: { requestIfNeeded: boolean },
): Promise<boolean> {
  try {
    if (Platform.OS !== 'ios' && Platform.OS !== 'android') return false;

    const { status: existing } = await Notifications.getPermissionsAsync();
    let granted = existing === 'granted';

    if (!granted && requestIfNeeded && existing === 'undetermined') {
      const { status } = await Notifications.requestPermissionsAsync();
      granted = status === 'granted';
    }
    if (!granted) return false;

    const projectId =
      (Constants.expoConfig?.extra?.eas as { projectId?: string } | undefined)?.projectId ||
      (Constants as unknown as { easConfig?: { projectId?: string } }).easConfig?.projectId;
    const tokenResp = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    if (tokenResp?.data) {
      await api.savePushToken(tokenResp.data);
      return true;
    }
    return false;
  } catch {
    // push не критичны
    return false;
  }
}
