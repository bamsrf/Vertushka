/**
 * Настройки уведомлений — группы по доменам + Quiet Hours (Не беспокоить).
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Animated,
  Pressable,
  Linking,
  Platform,
  ActionSheetIOS,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Icon, Toggle } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Notifications from 'expo-notifications';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { NotificationSettings } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { ms } from '../../lib/responsive';

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
        {description ? <Text style={styles.settingDescription}>{description}</Text> : null}
      </View>
      <Toggle value={value} onValueChange={onToggle} disabled={disabled} />
    </View>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <>
      <Text style={styles.groupTitle}>{title}</Text>
      <View style={styles.group}>{children}</View>
    </>
  );
}

const START_PRESETS = ['20:00', '21:00', '22:00', '23:00', '00:00'];
const END_PRESETS = ['06:00', '07:00', '08:00', '09:00', '10:00'];

/**
 * Backend хранит quiet_hours_* в UTC и сравнивает с datetime.utcnow().time().
 * UI оперирует локальным временем (пользователь не должен про UTC думать).
 * Конверсия учитывает текущий локальный offset (DST включён в JS Date).
 */
function localHHMMToUtc(local: string): string {
  const [h, m] = local.split(':').map(Number);
  const d = new Date();
  d.setHours(h || 0, m || 0, 0, 0);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

function utcHHMMToLocal(utc: string | null | undefined, fallbackLocal: string): string {
  if (!utc) return fallbackLocal;
  const [h, m] = utc.split(':').map(Number);
  const d = new Date();
  d.setUTCHours(h || 0, m || 0, 0, 0);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function pickPreset(
  title: string,
  presets: string[],
  current: string | null,
  onPick: (value: string) => void,
) {
  if (Platform.OS === 'ios') {
    ActionSheetIOS.showActionSheetWithOptions(
      {
        title,
        options: [...presets, 'Отмена'],
        cancelButtonIndex: presets.length,
      },
      (idx) => {
        if (idx >= 0 && idx < presets.length) onPick(presets[idx]);
      },
    );
  } else {
    Alert.alert(
      title,
      undefined,
      [
        ...presets.map((p) => ({
          text: p === current ? `✓ ${p}` : p,
          onPress: () => onPick(p),
        })),
        { text: 'Отмена', style: 'cancel' as const },
      ],
    );
  }
}

export default function NotificationsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [osPermission, setOsPermission] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [s, p] = await Promise.all([
          api.getNotificationSettings(),
          Notifications.getPermissionsAsync(),
        ]);
        setSettings(s);
        setOsPermission(p.status === 'granted');
      } catch {
        toast.error('Не удалось загрузить настройки');
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const persist = useCallback(async (patch: Partial<NotificationSettings>) => {
    if (!settings) return;
    const prev = settings;
    setSettings({ ...settings, ...patch } as NotificationSettings);
    setIsSaving(true);
    try {
      const updated = await api.updateNotificationSettings(patch);
      setSettings(updated);
    } catch {
      setSettings(prev);
      toast.error('Не удалось сохранить');
    } finally {
      setIsSaving(false);
    }
  }, [settings]);

  const handleToggle = useCallback((key: keyof NotificationSettings, value: boolean) => {
    persist({ [key]: value } as Partial<NotificationSettings>);
  }, [persist]);

  const handlePickStart = () =>
    pickPreset(
      'Начало тихих часов',
      START_PRESETS,
      utcHHMMToLocal(settings?.quiet_hours_start, '22:00'),
      (localValue) => persist({ quiet_hours_start: localHHMMToUtc(localValue) }),
    );

  const handlePickEnd = () =>
    pickPreset(
      'Окончание тихих часов',
      END_PRESETS,
      utcHHMMToLocal(settings?.quiet_hours_end, '08:00'),
      (localValue) => persist({ quiet_hours_end: localHHMMToUtc(localValue) }),
    );

  const handleRequestPermission = useCallback(async () => {
    const { status } = await Notifications.requestPermissionsAsync();
    if (status === 'granted') {
      setOsPermission(true);
      try {
        const tokenData = await Notifications.getExpoPushTokenAsync();
        await api.savePushToken(tokenData.data);
      } catch {/* silently */}
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

  const s = settings!;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Уведомления</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {osPermission === false ? (
          <View style={styles.permissionBanner}>
            <View style={styles.permissionIconContainer}>
              <Icon name="notifications-off-outline" size={24} color={Colors.warning} />
            </View>
            <View style={styles.permissionTextContainer}>
              <Text style={styles.permissionTitle}>Уведомления отключены</Text>
              <Text style={styles.permissionSubtitle}>Разрешите в настройках устройства</Text>
            </View>
            <TouchableOpacity style={styles.permissionButton} onPress={() => Linking.openSettings()}>
              <Text style={styles.permissionButtonText}>Открыть</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {osPermission === null ? (
          <View style={styles.permissionBanner}>
            <View style={styles.permissionIconContainer}>
              <Icon name="notifications-outline" size={24} color={Colors.royalBlue} />
            </View>
            <View style={styles.permissionTextContainer}>
              <Text style={styles.permissionTitle}>Разрешите уведомления</Text>
              <Text style={styles.permissionSubtitle}>Будете в курсе новых подписчиков и подарков</Text>
            </View>
            <TouchableOpacity
              style={[styles.permissionButton, { backgroundColor: Colors.royalBlue }]}
              onPress={handleRequestPermission}
            >
              <Text style={[styles.permissionButtonText, { color: Colors.background }]}>Разрешить</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <Group title="Социальные">
          <SettingRow
            label="Новый подписчик"
            description="Когда кто-то подписывается на вас"
            value={s.notify_new_follower}
            onToggle={(v) => handleToggle('notify_new_follower', v)}
            disabled={isSaving}
          />
          <SettingRow
            label="Запрос на подписку"
            description="Когда кто-то хочет подписаться на ваш приватный профиль"
            value={s.notify_follow_request}
            onToggle={(v) => handleToggle('notify_follow_request', v)}
            disabled={isSaving}
          />
        </Group>

        <Group title="Подарки">
          <SettingRow
            label="Подарок забронирован"
            description="Когда кто-то бронирует пластинку из вашего вишлиста"
            value={s.notify_gift_booked}
            onToggle={(v) => handleToggle('notify_gift_booked', v)}
            disabled={isSaving}
          />
          <SettingRow
            label="Подарок получен"
            description="Когда владелец подтверждает получение"
            value={s.notify_gift_confirmed}
            onToggle={(v) => handleToggle('notify_gift_confirmed', v)}
            disabled={isSaving}
          />
        </Group>

        <Group title="Вишлист">
          <SettingRow
            label="Снова в продаже"
            description="Когда пластинка из вашего вишлиста появляется у магазинов"
            value={s.notify_wishlist_in_stock}
            onToggle={(v) => handleToggle('notify_wishlist_in_stock', v)}
            disabled={isSaving}
          />
        </Group>

        <Group title="Достижения">
          <SettingRow
            label="Новая ачивка"
            description="Когда вы разблокировали достижение"
            value={s.notify_achievement}
            onToggle={(v) => handleToggle('notify_achievement', v)}
            disabled={isSaving}
          />
          <SettingRow
            label="Вехи"
            description="100 пластинок, годовщины и другие милстоуны"
            value={s.notify_milestone}
            onToggle={(v) => handleToggle('notify_milestone', v)}
            disabled={isSaving}
          />
        </Group>

        <Group title="Не беспокоить">
          <SettingRow
            label="Тихий режим"
            description="В заданные часы push не приходит, но появляется в ленте"
            value={s.quiet_hours_enabled}
            onToggle={(v) => handleToggle('quiet_hours_enabled', v)}
            disabled={isSaving}
          />
          {s.quiet_hours_enabled ? (
            <>
              <TouchableOpacity
                style={styles.settingRow}
                onPress={handlePickStart}
                disabled={isSaving}
              >
                <View style={styles.settingInfo}>
                  <Text style={styles.settingLabel}>Начало</Text>
                </View>
                <Text style={styles.timeValue}>{utcHHMMToLocal(s.quiet_hours_start, '22:00')}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.settingRow}
                onPress={handlePickEnd}
                disabled={isSaving}
              >
                <View style={styles.settingInfo}>
                  <Text style={styles.settingLabel}>Окончание</Text>
                </View>
                <Text style={styles.timeValue}>{utcHHMMToLocal(s.quiet_hours_end, '08:00')}</Text>
              </TouchableOpacity>
            </>
          ) : null}
        </Group>

        <Group title="Системное">
          <SettingRow
            label="Обновления приложения"
            description="Новые функции и улучшения"
            value={s.notify_app_updates}
            onToggle={(v) => handleToggle('notify_app_updates', v)}
            disabled={isSaving}
          />
        </Group>

        <View style={{ height: insets.bottom + Spacing.xl }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: { ...Typography.h4, fontSize: ms(17), color: Colors.royalBlue },
  backButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  placeholder: { width: 36, height: 36 },
  content: { padding: Spacing.lg },
  groupTitle: {
    ...Typography.overline,
    color: Colors.textMuted,
    marginTop: Spacing.lg,
    marginBottom: Spacing.sm,
    paddingHorizontal: Spacing.xs,
  },
  group: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    overflow: 'hidden',
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
  settingInfo: { flex: 1, marginRight: Spacing.md },
  settingLabel: { ...Typography.body, color: Colors.text },
  settingDescription: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2 },
  timeValue: { ...Typography.bodyBold, color: Colors.royalBlue },
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
  permissionTextContainer: { flex: 1 },
  permissionTitle: { ...Typography.bodyBold, color: Colors.text, fontSize: ms(14) },
  permissionSubtitle: { ...Typography.caption, color: Colors.textSecondary, marginTop: 1 },
  permissionButton: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.warning,
  },
  permissionButtonText: { ...Typography.buttonSmall, color: Colors.background },
});
