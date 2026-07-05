/**
 * Экран регистрации — Blue Gradient Edition
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
import { useRouter } from 'expo-router';
import { TouchableOpacity } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import { Button, Input } from '../../components/ui';
import { AuthHeader } from '../../components/AuthHeader';
import { SocialAuthButtons } from '../../components/SocialAuthButtons';
import { useAuthStore } from '../../lib/store';
import { Colors, Typography, Spacing } from '../../constants/theme';

export default function RegisterScreen() {
  const insets = useSafeAreaInsets();
  const { register, isLoading } = useAuthStore();

  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [errors, setErrors] = useState<{
    email?: string;
    username?: string;
    password?: string;
    confirmPassword?: string;
    terms?: string;
  }>({});
  const router = useRouter();

  const validate = () => {
    const newErrors: typeof errors = {};

    if (!email.trim()) {
      newErrors.email = 'Введите email';
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      newErrors.email = 'Некорректный email';
    }

    if (!username.trim()) {
      newErrors.username = 'Введите имя пользователя';
    } else if (username.length < 3) {
      newErrors.username = 'Минимум 3 символа';
    } else if (!/^[a-zA-Z0-9_]+$/.test(username)) {
      newErrors.username = 'Только буквы, цифры и _';
    }

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

    if (!termsAccepted) {
      newErrors.terms = 'Нужно принять условия использования';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleRegister = async () => {
    if (!validate()) return;

    try {
      await register(email, username, password);
    } catch (error: any) {
      toast.error('Ошибка регистрации', error.response?.data?.detail || 'Не удалось создать аккаунт');
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
        <AuthHeader mode="register" />

        {/* Форма */}
        <View style={styles.form}>
          <Input
            label="Email"
            value={email}
            onChangeText={setEmail}
            placeholder="email@example.com"
            keyboardType="email-address"
            autoComplete="email"
            leftIcon="mail-outline"
            error={errors.email}
          />

          <Input
            label="Имя пользователя"
            value={username}
            onChangeText={setUsername}
            placeholder="username"
            autoComplete="username"
            leftIcon="person-outline"
            error={errors.username}
          />

          <Input
            label="Пароль"
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            secureTextEntry
            autoComplete="password"
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

          {/* Принятие условий — обязательное для регистрации (App Store 1.2) */}
          <TouchableOpacity
            style={styles.termsRow}
            onPress={() => setTermsAccepted((v) => !v)}
            activeOpacity={0.7}
          >
            <View style={[styles.checkbox, termsAccepted && styles.checkboxChecked]}>
              {termsAccepted ? (
                <Icon name="checkmark" size={14} color={Colors.background} />
              ) : null}
            </View>
            <Text style={styles.termsText}>
              Принимаю{' '}
              <Text style={styles.termsLink} onPress={() => router.push('/legal/terms')}>
                Условия использования
              </Text>{' '}
              и{' '}
              <Text style={styles.termsLink} onPress={() => router.push('/legal/privacy')}>
                Политику конфиденциальности
              </Text>
            </Text>
          </TouchableOpacity>
          {errors.terms ? <Text style={styles.termsError}>{errors.terms}</Text> : null}

          <Button
            title="Создать аккаунт"
            onPress={handleRegister}
            loading={isLoading}
            fullWidth
            style={styles.button}
          />

          <SocialAuthButtons mode="register" />

          <Text style={styles.socialTermsNote}>
            Продолжая через Apple или Google, вы принимаете Условия использования и Политику
            конфиденциальности
          </Text>
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
  form: {
    marginBottom: Spacing.xl,
  },
  button: {
    marginTop: Spacing.md,
  },
  termsRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
    marginTop: Spacing.sm,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: Colors.textMuted,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  checkboxChecked: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.royalBlue,
  },
  termsText: {
    ...Typography.caption,
    color: Colors.textSecondary,
    flex: 1,
    lineHeight: 18,
  },
  termsLink: {
    color: Colors.royalBlue,
    fontWeight: '600',
  },
  termsError: {
    ...Typography.caption,
    color: Colors.error,
    marginTop: Spacing.xs,
  },
  socialTermsNote: {
    ...Typography.caption,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: Spacing.md,
  },
});
