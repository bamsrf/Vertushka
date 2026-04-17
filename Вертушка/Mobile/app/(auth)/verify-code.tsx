/**
 * Экран ввода 6-значного кода сброса пароля
 */
import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  TextInput,
  TouchableOpacity,
} from 'react-native';
import { toast } from '../../lib/toast';
import { router, useLocalSearchParams } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Button } from '../../components/ui';
import { api } from '../../lib/api';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';

const CODE_LENGTH = 6;
const RESEND_COOLDOWN = 60; // секунд

export default function VerifyCodeScreen() {
  const insets = useSafeAreaInsets();
  const { email } = useLocalSearchParams<{ email: string }>();

  const [code, setCode] = useState<string[]>(Array(CODE_LENGTH).fill(''));
  const [isLoading, setIsLoading] = useState(false);
  const [resendTimer, setResendTimer] = useState(RESEND_COOLDOWN);

  const inputRefs = useRef<(TextInput | null)[]>([]);

  // Таймер для повторной отправки
  useEffect(() => {
    if (resendTimer <= 0) return;
    const interval = setInterval(() => {
      setResendTimer((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [resendTimer]);

  const handleChange = (text: string, index: number) => {
    // Поддержка вставки полного кода
    if (text.length > 1) {
      const digits = text.replace(/\D/g, '').slice(0, CODE_LENGTH).split('');
      const newCode = [...code];
      digits.forEach((digit, i) => {
        if (index + i < CODE_LENGTH) {
          newCode[index + i] = digit;
        }
      });
      setCode(newCode);
      const nextIndex = Math.min(index + digits.length, CODE_LENGTH - 1);
      inputRefs.current[nextIndex]?.focus();
      return;
    }

    const digit = text.replace(/\D/g, '');
    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    if (digit && index < CODE_LENGTH - 1) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyPress = (key: string, index: number) => {
    if (key === 'Backspace' && !code[index] && index > 0) {
      const newCode = [...code];
      newCode[index - 1] = '';
      setCode(newCode);
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleVerify = async () => {
    const fullCode = code.join('');
    if (fullCode.length !== CODE_LENGTH) {
      toast.error('Введите 6-значный код');
      return;
    }

    setIsLoading(true);
    try {
      const resetToken = await api.verifyResetCode(email!, fullCode);
      router.push({
        pathname: '/(auth)/reset-password',
        params: { resetToken },
      });
    } catch (err: any) {
      toast.error('Ошибка', err.response?.data?.detail || 'Неверный или просроченный код');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendTimer > 0) return;

    try {
      await api.forgotPassword(email!);
      setResendTimer(RESEND_COOLDOWN);
      setCode(Array(CODE_LENGTH).fill(''));
      inputRefs.current[0]?.focus();
      toast.success('Новый код отправлен на почту');
    } catch (err: any) {
      toast.error('Ошибка', err.response?.data?.detail || 'Не удалось отправить код');
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
            <Ionicons name="keypad-outline" size={48} color={Colors.background} />
          </LinearGradient>
        </View>

        {/* Описание */}
        <View style={styles.form}>
          <Text style={styles.title}>Введите код</Text>
          <Text style={styles.description}>
            Мы отправили 6-значный код на{'\n'}
            <Text style={styles.emailHighlight}>{email}</Text>
          </Text>

          {/* OTP поля */}
          <View style={styles.codeContainer}>
            {code.map((digit, index) => (
              <TextInput
                key={index}
                ref={(ref) => { inputRefs.current[index] = ref; }}
                style={[
                  styles.codeInput,
                  digit ? styles.codeInputFilled : null,
                ]}
                value={digit}
                onChangeText={(text) => handleChange(text, index)}
                onKeyPress={({ nativeEvent }) => handleKeyPress(nativeEvent.key, index)}
                keyboardType="number-pad"
                maxLength={index === 0 ? CODE_LENGTH : 1}
                selectTextOnFocus
              />
            ))}
          </View>

          <Button
            title="Подтвердить"
            onPress={handleVerify}
            loading={isLoading}
            fullWidth
            style={styles.button}
          />

          {/* Повторная отправка */}
          <TouchableOpacity
            onPress={handleResend}
            disabled={resendTimer > 0}
            style={styles.resendButton}
          >
            <Text style={[
              styles.resendText,
              resendTimer > 0 && styles.resendTextDisabled,
            ]}>
              {resendTimer > 0
                ? `Отправить повторно (${resendTimer}с)`
                : 'Отправить код повторно'}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Назад */}
        <View style={styles.footer}>
          <Button
            title="Назад"
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
    textAlign: 'center',
  },
  emailHighlight: {
    ...Typography.bodyBold,
    color: Colors.deepNavy,
  },
  codeContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 10,
    marginBottom: Spacing.lg,
  },
  codeInput: {
    width: 48,
    height: 56,
    borderWidth: 1.5,
    borderColor: Colors.border,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
    textAlign: 'center',
    fontSize: 24,
    fontFamily: 'Inter_600SemiBold',
    color: Colors.deepNavy,
  },
  codeInputFilled: {
    borderColor: Colors.royalBlue,
    backgroundColor: Colors.background,
  },
  button: {
    marginTop: Spacing.sm,
  },
  resendButton: {
    alignSelf: 'center',
    marginTop: Spacing.md,
    padding: Spacing.xs,
  },
  resendText: {
    ...Typography.bodySmall,
    color: Colors.royalBlue,
  },
  resendTextDisabled: {
    color: Colors.textMuted,
  },
  footer: {
    alignItems: 'center',
  },
});
