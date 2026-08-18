/**
 * OfflineBanner — плашка «нет сети».
 *
 * Живёт в RootOverlay, а не в потоке над `<Stack>`, по двум причинам:
 *
 *  1. В потоке её не было видно из-под нативных модалок (profile,
 *     notifications, legal/*) — ровно та же беда, что у тостов,
 *     см. components/ToastHost.tsx.
 *  2. Появляясь, она сдвигала вниз весь стек разом: у пользователя дёргался
 *     весь экран, а не всплывала плашка.
 *
 * Смонтирована только пока сети нет, поэтому оверлей не висит постоянно. Но
 * `accessibilityIsModal` всё равно выключен: пропажа сети не должна прятать
 * приложение от VoiceOver, плашка тут — справочная.
 *
 * Тост при совпадении ляжет поверх: его оверлей создаётся позже, а значит его
 * UIWindow выше. Так и надо — тост острее и живёт секунды.
 */
import { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import NetInfo from '@react-native-community/netinfo';
import { Icon, RootOverlay } from '@/components/ui';
import { Colors, Typography, Spacing } from '../constants/theme';

export function OfflineBanner() {
  const insets = useSafeAreaInsets();
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOffline(state.isConnected === false);
    });
    return unsubscribe;
  }, []);

  if (!isOffline) return null;

  return (
    <RootOverlay accessibilityIsModal={false}>
      <View pointerEvents="none" style={[styles.banner, { top: insets.top }]}>
        <Icon name="cloud-offline-outline" size={16} color={Colors.background} />
        <Text style={styles.text}>Нет подключения к интернету</Text>
      </View>
    </RootOverlay>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: 'absolute',
    left: 0,
    right: 0,
    backgroundColor: Colors.textSecondary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.xs,
    paddingHorizontal: Spacing.md,
    gap: Spacing.xs,
  },
  text: {
    ...Typography.caption,
    color: Colors.background,
    fontFamily: 'Inter_500Medium',
  },
});
