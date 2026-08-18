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

    const perms = await Notifications.getPermissionsAsync();
    let granted = perms.status === 'granted';

    // Спрашиваем, пока система вообще разрешает спрашивать. Раньше условие было
    // `status === 'undetermined'`, и Android 13+ выпадал: там первый отказ даёт
    // status='denied' при canAskAgain=true — то есть промпт ещё можно показать,
    // а мы уже молча сдавались.
    if (!granted && requestIfNeeded && perms.canAskAgain !== false) {
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
