/**
 * Блокирующий экран принудительного обновления.
 *
 * Показывается, когда версия билда ниже `min_supported_version` из
 * GET /api/config. Выхода нет намеренно: этот экран — аварийная кнопка,
 * которой мы выгоняем сломанный билд, не дожидаясь нового ревью в App Store.
 *
 * См. lib/remoteConfig.ts, docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.2.
 */
import { useCallback } from 'react';
import { Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { BorderRadius, Colors, Spacing, Typography } from '../constants/theme';

interface ForceUpdateScreenProps {
  message: string;
  storeUrl: string;
}

export function ForceUpdateScreen({ message, storeUrl }: ForceUpdateScreenProps) {
  const handleOpenStore = useCallback(() => {
    Linking.openURL(storeUrl).catch(() => {
      // Ссылка не открылась — экран остаётся на месте, пользователь может
      // обновиться из App Store вручную. Падать тут нечему.
    });
  }, [storeUrl]);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.emoji}>💿</Text>
        <Text style={styles.title}>Нужно обновление</Text>
        <Text style={styles.message}>{message}</Text>

        <TouchableOpacity
          style={styles.button}
          onPress={handleOpenStore}
          accessibilityRole="button"
          accessibilityLabel="Открыть App Store"
        >
          <Text style={styles.buttonText}>Обновить</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.xl,
  },
  emoji: {
    fontSize: 64,
    marginBottom: Spacing.lg,
  },
  title: {
    ...Typography.h1,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.md,
  },
  message: {
    ...Typography.body,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginBottom: Spacing.xl,
  },
  button: {
    backgroundColor: Colors.royalBlue,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.xl,
    borderRadius: BorderRadius.full,
    minWidth: 200,
    alignItems: 'center',
  },
  buttonText: {
    ...Typography.button,
    color: '#FFFFFF',
  },
});
