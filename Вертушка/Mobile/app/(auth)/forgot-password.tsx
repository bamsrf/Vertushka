/**
 * Экран "Забыли пароль?" — ввод email для получения кода сброса
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
import { router } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Button, Input } from '../../components/ui';
import { api } from '../../lib/api';
import { Colors, Typography, Spacing } from '../../constants/theme';

export default function ForgotPasswordScreen() {
  const insets = useSafeAreaInsets();

  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const validate = () => {
    if (!email.trim()) {
      setError('Введите email');
      return false;
    }
    if (!/\S+@\S+\.\S+/.test(email)) {
      setError('Некорректный email');
      return false;
    }
    setError('');
    return true;
  };

  const handleSubmit = async () => {
    if (!validate()) return;

    setIsLoading(true);
    try {
      await api.forgotPassword(email.trim().toLowerCase());
      router.push({
        pathname: '/(auth)/verify-code',
        params: { email: email.trim().toLowerCase() },
      });
    } catch (err: any) {
      toast.error('Ошибка', err.response?.data?.detail || 'Не удалось отправить код');
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
            <Ionicons name="mail-outline" size={48} color={Colors.background} />
          </LinearGradient>
        </View>

        {/* Форма */}
        <View style={styles.form}>
          <Text style={styles.title}>Забыли пароль?</Text>
          <Text style={styles.description}>
            Введите email, привязанный к аккаунту. Мы отправим код для сброса пароля.
          </Text>

          <Input
            label="Email"
            value={email}
            onChangeText={setEmail}
            placeholder="email@example.com"
            keyboardType="email-address"
            autoCapitalize="none"
            autoComplete="email"
            leftIcon="mail-outline"
            error={error}
          />

          <Button
            title="Отправить код"
            onPress={handleSubmit}
            loading={isLoading}
            fullWidth
            style={styles.button}
          />
        </View>

        {/* Назад */}
        <View style={styles.footer}>
          <Button
            title="Назад к входу"
            onPress={() => router.back()}
            variant="ghost"
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
  footer: {
    alignItems: 'center',
  },
});
