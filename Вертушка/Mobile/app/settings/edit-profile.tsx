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
  Alert,
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

export default function EditProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user, setUser } = useAuthStore();
  const { settings, fetchSettings, updateSettings } = useProfileStore();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  useEffect(() => {
    const nameChanged = displayName !== (user?.display_name ?? '');
    setHasChanges(nameChanged);
  }, [displayName, user?.display_name]);

  const handleSave = useCallback(async () => {
    if (!hasChanges) return;
    setIsSaving(true);
    try {
      const updated = await api.updateMe({ display_name: displayName || undefined });
      setUser(updated);
      setHasChanges(false);
      Alert.alert('Сохранено', 'Профиль обновлён');
    } catch {
      Alert.alert('Ошибка', 'Не удалось сохранить изменения');
    } finally {
      setIsSaving(false);
    }
  }, [displayName, hasChanges, setUser]);

  const handleTogglePrivate = useCallback(async (value: boolean) => {
    try {
      await updateSettings({ is_private_profile: value });
    } catch {
      Alert.alert('Ошибка', 'Не удалось сохранить настройку');
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
          disabled={!hasChanges || isSaving}
        >
          {isSaving ? (
            <ActivityIndicator size="small" color={Colors.royalBlue} />
          ) : (
            <Text style={[
              styles.saveButtonText,
              (!hasChanges) && styles.saveButtonTextDisabled,
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
              maxLength={100}
              autoCapitalize="words"
              returnKeyType="done"
            />
          </View>
          <Text style={styles.hint}>
            Это имя будет отображаться на вашем профиле
          </Text>

          {/* Приватность */}
          <Text style={[styles.sectionTitle, { marginTop: Spacing.xl }]}>Приватность</Text>
          <View style={styles.section}>
            <View style={styles.settingRow}>
              <View style={styles.settingInfo}>
                <Text style={styles.settingLabel}>Приватный профиль</Text>
                <Text style={styles.settingDescription}>
                  Только одобренные подписчики видят контент
                </Text>
              </View>
              <VinylToggle
                value={settings?.is_private_profile ?? false}
                onValueChange={handleTogglePrivate}
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
