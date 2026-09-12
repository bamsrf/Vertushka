import { useCallback, useState } from 'react';
import { ActivityIndicator, Platform, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import Constants from 'expo-constants';
import * as Updates from 'expo-updates';
import { toast } from '../lib/toast';
import { Colors, Spacing, Typography } from '../constants/theme';

/**
 * Футер профиля: реальная версия бинарника и OTA-состояние вместо
 * захардкоженной строки. На Android — кнопка ручной проверки обновлений:
 * с реального телефона нет logcat, и без неё нельзя понять, долетел ли
 * `eas update`. На iOS только текст, поведение экрана не меняется.
 */
export function AppVersionFooter() {
  const [checking, setChecking] = useState(false);
  const version = Constants.expoConfig?.version ?? '?';
  const build = Platform.select({
    ios: Constants.expoConfig?.ios?.buildNumber,
    android: Constants.expoConfig?.android?.versionCode?.toString(),
  });
  const updateLabel = describeUpdate();

  const checkForUpdate = useCallback(async () => {
    if (checking) return;
    setChecking(true);
    try {
      const result = await Updates.checkForUpdateAsync();
      if (!result.isAvailable) {
        toast.info('Обновлений нет', `Стоит актуальная версия · ${updateLabel}`);
        return;
      }
      toast.info('Загружаю обновление…');
      await Updates.fetchUpdateAsync();
      await Updates.reloadAsync();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      toast.error('Не удалось проверить', message.slice(0, 120));
    } finally {
      setChecking(false);
    }
  }, [checking, updateLabel]);

  return (
    <View style={styles.wrap}>
      <Text style={styles.version}>
        Вертушка v{version}
        {build ? ` (${build})` : ''} · {updateLabel}
      </Text>
      {Platform.OS === 'android' && (
        <TouchableOpacity
          onPress={checkForUpdate}
          disabled={checking}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          style={styles.button}
        >
          {checking ? (
            <ActivityIndicator size="small" color={Colors.textSecondary} />
          ) : (
            <Text style={styles.buttonText}>Проверить обновления</Text>
          )}
        </TouchableOpacity>
      )}
    </View>
  );
}

/** «встроенный бандл» либо дата OTA-апдейта + короткий id. */
function describeUpdate(): string {
  try {
    if (Updates.isEmbeddedLaunch || !Updates.updateId) return 'встроенный бандл';
    const date = Updates.createdAt
      ? Updates.createdAt.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) +
        ' ' +
        Updates.createdAt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
      : '';
    return `OTA ${date} ${Updates.updateId.slice(0, 8)}`.trim();
  } catch {
    return 'без OTA';
  }
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    gap: Spacing.xs,
  },
  version: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
  },
  button: {
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.sm,
  },
  buttonText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    textDecorationLine: 'underline',
  },
});
