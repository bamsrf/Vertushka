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
  Alert,
} from 'react-native';
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

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});

  const validate = () => {
    const newErrors: { email?: string; password?: string } = {};

    if (!email.trim()) {
      newErrors.email = 'Введите email';
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      newErrors.email = 'Некорректный email';
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
      await login(email, password);
    } catch (error: any) {
      Alert.alert(
        'Ошибка входа',
        error.response?.data?.detail || 'Неверный email или пароль'
      );
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
