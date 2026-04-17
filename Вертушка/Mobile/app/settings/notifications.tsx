/**
 * Настройки уведомлений
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  Animated,
  Pressable,
  Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Notifications from 'expo-notifications';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { NotificationSettings } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

const TRACK_W = 52;
const TRACK_H = 30;
const VINYL_SIZE = 26;
const TRACK_PAD = 2;
const SLIDE_DISTANCE = TRACK_W - VINYL_SIZE - TRACK_PAD * 2;

function VinylToggle({ value, onValueChange, disabled }: {
  value: boolean;
  onValueChange: (val: boolean) => void;
  disabled?: boolean;
}) {
  const anim = useRef(new Animated.Value(value ? 1 : 0)).current;

  useEffect(() => {
    Animated.spring(anim, {
      toValue: value ? 1 : 0,
      useNativeDriver: true,
      friction: 7,
      tension: 40,
    }).start();
  }, [value]);

  const translateX = anim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, SLIDE_DISTANCE],
  });

  const spin = anim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  const trackBg = anim.interpolate({
    inputRange: [0, 1],
    outputRange: [Colors.border, Colors.royalBlue],
  });

  return (
    <Pressable
      onPress={() => !disabled && onValueChange(!value)}
      hitSlop={8}
    >
      <Animated.View style={[
        vinylStyles.track,
        { backgroundColor: trackBg },
        disabled && { opacity: 0.5 },
      ]}>
        <Animated.View style={[
          vinylStyles.vinyl,
          { transform: [{ translateX }, { rotate: spin }] },
        ]}>
          <View style={vinylStyles.groove1} />
          <View style={vinylStyles.groove2} />
          <View style={vinylStyles.label} />
        </Animated.View>
      </Animated.View>
    </Pressable>
  );
}

const vinylStyles = StyleSheet.create({
  track: {
    width: TRACK_W,
    height: TRACK_H,
    borderRadius: TRACK_H / 2,
    paddingHorizontal: TRACK_PAD,
    justifyContent: 'center',
  },
  vinyl: {
    width: VINYL_SIZE,
    height: VINYL_SIZE,
    borderRadius: VINYL_SIZE / 2,
    backgroundColor: '#1A1A1A',
    alignItems: 'center',
    justifyContent: 'center',
  },
  groove1: {
    position: 'absolute',
    width: VINYL_SIZE - 4,
    height: VINYL_SIZE - 4,
    borderRadius: (VINYL_SIZE - 4) / 2,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  groove2: {
    position: 'absolute',
    width: VINYL_SIZE - 10,
    height: VINYL_SIZE - 10,
    borderRadius: (VINYL_SIZE - 10) / 2,
    borderWidth: 0.5,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  label: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.royalBlue,
  },
});

function SettingRow({ label, description, value, onToggle, disabled }: {
  label: string;
  description?: string;
  value: boolean;
  onToggle: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingInfo}>
        <Text style={styles.settingLabel}>{label}</Text>
        {description && <Text style={styles.settingDescription}>{description}</Text>}
      </View>
      <VinylToggle
        value={value}
        onValueChange={onToggle}
        disabled={disabled}
      />
    </View>
  );
}

export default function NotificationsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [osPermission, setOsPermission] = useState<boolean | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [notifSettings, permStatus] = await Promise.all([
        api.getNotificationSettings(),
        Notifications.getPermissionsAsync(),
      ]);
      setSettings(notifSettings);
      setOsPermission(permStatus.status === 'granted');
    } catch {
      toast.error('Не удалось загрузить настройки');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggle = useCallback(async (key: keyof NotificationSettings, value: boolean) => {
    if (!settings) return;

    const prev = { ...settings };
    setSettings({ ...settings, [key]: value });
    setIsSaving(true);

    try {
      const updated = await api.updateNotificationSettings({ [key]: value });
      setSettings(updated);
    } catch {
      setSettings(prev);
      toast.error('Не удалось сохранить настройку');
    } finally {
      setIsSaving(false);
    }
  }, [settings]);

  const handleRequestPermission = useCallback(async () => {
    const { status } = await Notifications.requestPermissionsAsync();
    if (status === 'granted') {
      setOsPermission(true);
      try {
        const tokenData = await Notifications.getExpoPushTokenAsync();
        await api.savePushToken(tokenData.data);
      } catch {
        // Token save failed silently
      }
    } else {
      setOsPermission(false);
    }
  }, []);

  if (isLoading) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Уведомления</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* OS permission banner */}
        {osPermission === false && (
          <View style={styles.permissionBanner}>
            <View style={styles.permissionIconContainer}>
              <Ionicons name="notifications-off-outline" size={24} color={Colors.warning} />
            </View>
            <View style={styles.permissionTextContainer}>
              <Text style={styles.permissionTitle}>Уведомления отключены</Text>
              <Text style={styles.permissionSubtitle}>
                Разрешите уведомления в настройках устройства
              </Text>
            </View>
            <TouchableOpacity
              style={styles.permissionButton}
              onPress={() => Linking.openSettings()}
            >
              <Text style={styles.permissionButtonText}>Открыть</Text>
            </TouchableOpacity>
          </View>
        )}

        {osPermission === null && (
          <View style={styles.permissionBanner}>
            <View style={styles.permissionIconContainer}>
              <Ionicons name="notifications-outline" size={24} color={Colors.royalBlue} />
            </View>
            <View style={styles.permissionTextContainer}>
              <Text style={styles.permissionTitle}>Разрешите уведомления</Text>
              <Text style={styles.permissionSubtitle}>
                Будьте в курсе новых подписчиков и подарков
              </Text>
            </View>
            <TouchableOpacity
              style={[styles.permissionButton, { backgroundColor: Colors.royalBlue }]}
              onPress={handleRequestPermission}
            >
              <Text style={[styles.permissionButtonText, { color: Colors.background }]}>Разрешить</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Toggles */}
        <Text style={styles.sectionTitle}>Типы уведомлений</Text>
        <View style={styles.section}>
          <SettingRow
            label="Новый подписчик"
            description="Когда кто-то подписывается на вас"
            value={settings?.notify_new_follower ?? true}
            onToggle={(val) => handleToggle('notify_new_follower', val)}
            disabled={isSaving}
          />
          <SettingRow
            label="Подарок забронирован"
            description="Когда кто-то бронирует пластинку из вашего вишлиста"
            value={settings?.notify_gift_booked ?? true}
            onToggle={(val) => handleToggle('notify_gift_booked', val)}
            disabled={isSaving}
          />
          <SettingRow
            label="Обновления приложения"
            description="Новые функции и улучшения"
            value={settings?.notify_app_updates ?? true}
            onToggle={(val) => handleToggle('notify_app_updates', val)}
            disabled={isSaving}
          />
        </View>

        <View style={{ height: insets.bottom + Spacing.xl }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
  },
  backButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: {
    width: 36,
    height: 36,
  },
  content: {
    padding: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
    marginBottom: Spacing.sm,
    marginTop: Spacing.md,
  },
  section: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
    marginBottom: Spacing.md,
  },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  settingInfo: {
    flex: 1,
    marginRight: Spacing.md,
  },
  settingLabel: {
    ...Typography.body,
    color: Colors.text,
  },
  settingDescription: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  permissionBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  permissionIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  permissionTextContainer: {
    flex: 1,
  },
  permissionTitle: {
    ...Typography.bodyBold,
    color: Colors.text,
    fontSize: 14,
  },
  permissionSubtitle: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: 1,
  },
  permissionButton: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.warning,
  },
  permissionButtonText: {
    ...Typography.buttonSmall,
    color: Colors.background,
  },
});
