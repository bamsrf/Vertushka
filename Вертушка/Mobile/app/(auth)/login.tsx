/**
 * Экран входа — Blue Gradient Edition
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
import { Link } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Button, Input } from '../../components/ui';
import { useAuthStore } from '../../lib/store';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { login, isLoading } = useAuthStore();

  const [loginValue, setLoginValue] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ login?: string; password?: string }>({});

  const validate = () => {
    const newErrors: { login?: string; password?: string } = {};

    if (!loginValue.trim()) {
      newErrors.login = 'Введите email или имя пользователя';
    }

    if (!password) {
      newErrors.password = 'Введите пароль';
    } else if (password.length < 8) {
      newErrors.password = 'Пароль должен быть не менее 8 символов';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleLogin = async () => {
    if (!validate()) return;

    try {
      await login(loginValue, password);
    } catch (error: any) {
      toast.error('Ошибка входа', error.response?.data?.detail || 'Неверный логин или пароль');
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
        {/* Логотип */}
        <View style={styles.logoContainer}>
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            style={styles.logo}
          >
            <Ionicons name="disc" size={64} color={Colors.background} />
          </LinearGradient>
          <Text style={styles.appName}>Вертушка</Text>
          <Text style={styles.tagline}>Твоя коллекция винила</Text>
        </View>

        {/* Форма */}
        <View style={styles.form}>
          <Text style={styles.title}>Вход</Text>

          <Input
            label="Email или имя пользователя"
            value={loginValue}
            onChangeText={setLoginValue}
            placeholder="email@example.com или username"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="username"
            leftIcon="person-outline"
            error={errors.login}
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

          <Button
            title="Войти"
            onPress={handleLogin}
            loading={isLoading}
            fullWidth
            style={styles.button}
          />

          <Link href="/(auth)/forgot-password" style={styles.forgotLink}>
            <Text style={styles.forgotText}>Забыли пароль?</Text>
          </Link>
        </View>

        {/* Ссылка на регистрацию */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>Нет аккаунта?</Text>
          <Link href="/(auth)/register" style={styles.link}>
            <Text style={styles.linkText}>Создать</Text>
          </Link>
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
    marginBottom: Spacing.xxl,
  },
  logo: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  appName: {
    ...Typography.h1,
    color: Colors.deepNavy,
  },
  tagline: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginTop: Spacing.xs,
  },
  form: {
    marginBottom: Spacing.xl,
  },
  title: {
    ...Typography.h2,
    color: Colors.deepNavy,
    marginBottom: Spacing.lg,
  },
  button: {
    marginTop: Spacing.md,
  },
  forgotLink: {
    alignSelf: 'center',
    marginTop: Spacing.md,
    padding: Spacing.xs,
  },
  forgotText: {
    ...Typography.bodySmall,
    color: Colors.royalBlue,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: Spacing.xs,
  },
  footerText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  link: {
    padding: Spacing.xs,
  },
  linkText: {
    ...Typography.body,
    color: Colors.royalBlue,
    fontWeight: '600',
  },
});
