/**
 * Редактирование профиля
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Animated,
  Pressable,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuthStore, useProfileStore } from '../../lib/store';
import api from '../../lib/api';
import { toast } from '../../lib/toast';
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

const USERNAME_REGEX = /^[a-z0-9_]{3,50}$/;
const DEBOUNCE_MS = 300;

type UsernameStatus = 'idle' | 'checking' | 'available' | 'taken' | 'invalid' | 'too_short';

export default function EditProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, setUser } = useAuthStore();
  const { settings, fetchSettings, updateSettings, isSaving: isToggleSaving } = useProfileStore();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [usernameStatus, setUsernameStatus] = useState<UsernameStatus>('idle');
  const [isSaving, setIsSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const usernameTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    const nameChanged = displayName !== (user?.display_name ?? '');
    const usernameChanged = username !== (user?.username ?? '');
    setHasChanges(nameChanged || usernameChanged);
  }, [displayName, username, user?.display_name, user?.username]);

  const checkUsername = useCallback((value: string) => {
    if (usernameTimerRef.current) clearTimeout(usernameTimerRef.current);

    if (value === user?.username) {
      setUsernameStatus('idle');
      return;
    }
    if (value.length < 3) {
      setUsernameStatus('too_short');
      return;
    }
    if (!USERNAME_REGEX.test(value)) {
      setUsernameStatus('invalid');
      return;
    }

    setUsernameStatus('checking');
    usernameTimerRef.current = setTimeout(async () => {
      try {
        const result = await api.checkUsername(value);
        if (result.available) {
          setUsernameStatus('available');
        } else {
          setUsernameStatus(result.reason as UsernameStatus);
        }
      } catch {
        setUsernameStatus('idle');
      }
    }, DEBOUNCE_MS);
  }, [user?.username]);

  const handleUsernameChange = useCallback((text: string) => {
    const normalized = text.toLowerCase().replace(/[^a-z0-9_]/g, '');
    setUsername(normalized);
    checkUsername(normalized);
  }, [checkUsername]);

  const canSave = hasChanges && usernameStatus !== 'checking' && usernameStatus !== 'taken' && usernameStatus !== 'invalid' && usernameStatus !== 'too_short';

  const handleSave = useCallback(async () => {
    if (!canSave) return;
    setIsSaving(true);
    try {
      const payload: { display_name?: string; username?: string } = {};
      if (displayName !== (user?.display_name ?? '')) {
        payload.display_name = displayName || undefined;
      }
      if (username !== (user?.username ?? '')) {
        payload.username = username;
      }
      const updated = await api.updateMe(payload);
      setUser(updated);
      setHasChanges(false);
      setUsernameStatus('idle');
      toast.success('Профиль обновлён');
    } catch {
      toast.error('Не удалось сохранить изменения');
    } finally {
      setIsSaving(false);
    }
  }, [displayName, username, canSave, setUser, user?.display_name, user?.username]);

  const handleToggle = useCallback(async (key: string, value: boolean) => {
    try {
      await updateSettings({ [key]: value });
    } catch {
      toast.error('Не удалось сохранить настройку');
    }
  }, [updateSettings]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Редактировать профиль</Text>
        <TouchableOpacity
          onPress={handleSave}
          style={styles.saveButton}
          disabled={!canSave || isSaving}
        >
          {isSaving ? (
            <ActivityIndicator size="small" color={Colors.royalBlue} />
          ) : (
            <Text style={[
              styles.saveButtonText,
              (!canSave) && styles.saveButtonTextDisabled,
            ]}>
              Сохранить
            </Text>
          )}
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Имя */}
          <Text style={styles.sectionTitle}>Имя</Text>
          <View style={styles.inputContainer}>
            <TextInput
              style={styles.input}
              value={displayName}
              onChangeText={setDisplayName}
              placeholder="Ваше имя"
              placeholderTextColor={Colors.textMuted}
              maxLength={20}
              autoCapitalize="words"
              returnKeyType="done"
            />
          </View>
          <Text style={styles.hint}>
            Это имя будет отображаться на вашем профиле
          </Text>

          {/* Юзернейм */}
          <Text style={[styles.sectionTitle, { marginTop: Spacing.xl }]}>Юзернейм</Text>
          <View style={[
            styles.inputContainer,
            usernameStatus === 'available' && styles.inputValid,
            (usernameStatus === 'taken' || usernameStatus === 'invalid' || usernameStatus === 'too_short') && styles.inputError,
          ]}>
            <View style={styles.usernameInputRow}>
              <Text style={styles.usernamePrefix}>@</Text>
              <TextInput
                style={[styles.input, { flex: 1, paddingLeft: 0 }]}
                value={username}
                onChangeText={handleUsernameChange}
                placeholder="username"
                placeholderTextColor={Colors.textMuted}
                maxLength={50}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="done"
              />
              {usernameStatus === 'checking' && (
                <ActivityIndicator size="small" color={Colors.royalBlue} />
              )}
              {usernameStatus === 'available' && (
                <Ionicons name="checkmark-circle" size={20} color={Colors.success} />
              )}
              {(usernameStatus === 'taken' || usernameStatus === 'invalid' || usernameStatus === 'too_short') && (
                <Ionicons name="close-circle" size={20} color={Colors.error} />
              )}
            </View>
          </View>
          <Text style={[
            styles.hint,
            (usernameStatus === 'taken' || usernameStatus === 'invalid' || usernameStatus === 'too_short') && styles.hintError,
          ]}>
            {usernameStatus === 'taken' && 'Этот юзернейм уже занят'}
            {usernameStatus === 'invalid' && 'Только строчные латинские буквы, цифры и _'}
            {usernameStatus === 'too_short' && 'Минимум 3 символа'}
            {usernameStatus === 'available' && 'Юзернейм свободен!'}
            {(usernameStatus === 'idle' || usernameStatus === 'checking') && 'Латинские буквы, цифры и подчёркивание (3–50 символов)'}
          </Text>

          {/* Приватность */}
          <Text style={[styles.sectionTitle, { marginTop: Spacing.xl }]}>Приватность</Text>
          <View style={styles.section}>
            <View style={[styles.settingRow, styles.settingRowLast]}>
              <View style={styles.settingInfo}>
                <Text style={styles.settingLabel}>Приватный профиль</Text>
                <Text style={styles.settingDescription}>
                  Только одобренные подписчики видят контент
                </Text>
              </View>
              <VinylToggle
                value={settings?.is_private_profile ?? false}
                onValueChange={(val) => handleToggle('is_private_profile', val)}
                disabled={isToggleSaving}
              />
            </View>
          </View>

          {/* Публичный профиль */}
          <Text style={[styles.sectionTitle, { marginTop: Spacing.xl }]}>Публичный профиль</Text>
          <View style={styles.section}>
            <View style={styles.settingRow}>
              <View style={styles.settingInfo}>
                <Text style={styles.settingLabel}>Активировать профиль</Text>
                <Text style={styles.settingDescription}>
                  Ваш профиль будет доступен по ссылке
                </Text>
              </View>
              <VinylToggle
                value={settings?.is_active ?? false}
                onValueChange={(val) => handleToggle('is_active', val)}
                disabled={isToggleSaving}
              />
            </View>
            <View style={[styles.settingRow, styles.settingRowLast]}>
              <View style={styles.settingInfo}>
                <Text style={styles.settingLabel}>Общая стоимость коллекции</Text>
                <Text style={styles.settingDescription}>
                  Видна посетителям профиля
                </Text>
              </View>
              <VinylToggle
                value={settings?.show_collection_value ?? false}
                onValueChange={(val) => handleToggle('show_collection_value', val)}
                disabled={isToggleSaving}
              />
            </View>
          </View>

          <View style={{ height: insets.bottom + Spacing.xl }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
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
  saveButton: {
    minWidth: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  saveButtonText: {
    ...Typography.bodyBold,
    color: Colors.royalBlue,
  },
  saveButtonTextDisabled: {
    opacity: 0.4,
  },
  content: {
    padding: Spacing.lg,
  },
  sectionTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
    marginBottom: Spacing.sm,
  },
  inputContainer: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.background,
  },
  input: {
    ...Typography.body,
    color: Colors.text,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
  },
  hint: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  hintError: {
    color: Colors.error,
  },
  inputValid: {
    borderColor: Colors.success,
  },
  inputError: {
    borderColor: Colors.error,
  },
  usernameInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
  },
  usernamePrefix: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginRight: 2,
  },
  section: {
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
  settingRowLast: {
    borderBottomWidth: 0,
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
});
