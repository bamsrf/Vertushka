/**
 * Экран установки нового пароля после верификации кода
 */
import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { toast } from '../../lib/toast';
import { router, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Button, Input } from '../../components/ui';
import { api } from '../../lib/api';
import { useAuthStore } from '../../lib/store';
import { Colors, Typography, Spacing } from '../../constants/theme';

export default function ResetPasswordScreen() {
  const insets = useSafeAreaInsets();
  const { resetToken } = useLocalSearchParams<{ resetToken: string }>();
  const { setUser } = useAuthStore();

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<{
    password?: string;
    confirmPassword?: string;
  }>({});

  const validate = () => {
    const newErrors: typeof errors = {};

    if (!password) {
      newErrors.password = 'Введите пароль';
    } else if (password.length < 8) {
      newErrors.password = 'Минимум 8 символов';
    }

    if (!confirmPassword) {
      newErrors.confirmPassword = 'Подтвердите пароль';
    } else if (password !== confirmPassword) {
      newErrors.confirmPassword = 'Пароли не совпадают';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleReset = async () => {
    if (!validate()) return;

    setIsLoading(true);
    try {
      await api.resetPassword(resetToken!, password);
      // Токены уже сохранены в api.resetPassword — загружаем пользователя
      const user = await api.getMe();
      setUser(user);
      // Переход на главный экран
      router.replace('/(tabs)');
    } catch (err: any) {
      toast.error('Ошибка', err.response?.data?.detail || 'Не удалось сбросить пароль');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingTop: insets.top + Spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Иконка */}
        <View style={styles.logoContainer}>
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            style={styles.logo}
          >
            <Ionicons name="lock-open-outline" size={48} color={Colors.background} />
          </LinearGradient>
        </View>

        {/* Форма */}
        <View style={styles.form}>
          <Text style={styles.title}>Новый пароль</Text>
          <Text style={styles.description}>
            Придумайте новый пароль для вашего аккаунта.
          </Text>

          <Input
            label="Новый пароль"
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            secureTextEntry
            autoComplete="password-new"
            leftIcon="lock-closed-outline"
            error={errors.password}
          />

          <Input
            label="Подтвердите пароль"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            placeholder="••••••••"
            secureTextEntry
            leftIcon="lock-closed-outline"
            error={errors.confirmPassword}
          />

          <Button
            title="Сохранить пароль"
            onPress={handleReset}
            loading={isLoading}
            fullWidth
            style={styles.button}
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: Spacing.lg,
    paddingBottom: Spacing.xl,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: Spacing.xl,
  },
  logo: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  form: {
    marginBottom: Spacing.xl,
  },
  title: {
    ...Typography.h2,
    color: Colors.deepNavy,
    marginBottom: Spacing.sm,
  },
  description: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginBottom: Spacing.lg,
  },
  button: {
    marginTop: Spacing.md,
  },
});
