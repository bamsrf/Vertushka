/**
 * Кнопки социального входа: Apple (iOS) и Google.
 * Используется на экранах login и register.
 */
import { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View, ActivityIndicator } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import {
  GoogleSignin,
  statusCodes,
} from '@react-native-google-signin/google-signin';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import { toast } from '../lib/toast';
import { useAuthStore } from '../lib/store';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';

const googleWebClientId =
  (Constants.expoConfig?.extra?.googleWebClientId as string | undefined) ?? '';
const googleIosClientId =
  (Constants.expoConfig?.extra?.googleIosClientId as string | undefined) ?? '';

let googleConfigured = false;
function ensureGoogleConfigured() {
  if (googleConfigured || !googleWebClientId) return;
  GoogleSignin.configure({
    webClientId: googleWebClientId,
    iosClientId: googleIosClientId || undefined,
    offlineAccess: false,
  });
  googleConfigured = true;
}

interface Props {
  mode: 'login' | 'register';
}

export function SocialAuthButtons({ mode }: Props) {
  const { loginWithApple, loginWithGoogle } = useAuthStore();
  const [appleAvailable, setAppleAvailable] = useState(false);
  const [busy, setBusy] = useState<null | 'apple' | 'google'>(null);

  useEffect(() => {
    if (Platform.OS === 'ios') {
      AppleAuthentication.isAvailableAsync().then(setAppleAvailable).catch(() => setAppleAvailable(false));
    }
  }, []);

  const handleApple = async () => {
    if (busy) return;
    setBusy('apple');
    try {
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        ],
      });
      if (!credential.identityToken || !credential.authorizationCode) {
        throw new Error('Apple не вернул identity token');
      }
      const fullName = [credential.fullName?.givenName, credential.fullName?.familyName]
        .filter(Boolean)
        .join(' ')
        .trim() || null;
      await loginWithApple({
        identity_token: credential.identityToken,
        authorization_code: credential.authorizationCode,
        user_identifier: credential.user,
        email: credential.email ?? null,
        full_name: fullName,
      });
    } catch (error: any) {
      if (error?.code !== 'ERR_REQUEST_CANCELED') {
        toast.error('Ошибка Apple Sign In', error?.response?.data?.detail || error?.message || 'Не удалось войти через Apple');
      }
    } finally {
      setBusy(null);
    }
  };

  const handleGoogle = async () => {
    if (busy) return;
    if (!googleWebClientId) {
      toast.error('Google Sign In не настроен', 'Заполните googleWebClientId в app.json');
      return;
    }
    setBusy('google');
    try {
      ensureGoogleConfigured();
      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      const userInfo = await GoogleSignin.signIn();
      const idToken = (userInfo as any)?.data?.idToken ?? (userInfo as any)?.idToken;
      if (!idToken) throw new Error('Google не вернул id_token');
      await loginWithGoogle(idToken);
    } catch (error: any) {
      const code = error?.code;
      if (code === statusCodes.SIGN_IN_CANCELLED || code === statusCodes.IN_PROGRESS) {
        // тихо
      } else if (code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        toast.error('Google Play Services недоступны', 'Установите/обновите Google Play Services');
      } else {
        toast.error('Ошибка Google Sign In', error?.response?.data?.detail || error?.message || 'Не удалось войти через Google');
      }
    } finally {
      setBusy(null);
    }
  };

  const showApple = Platform.OS === 'ios' && appleAvailable;
  const showGoogle = Boolean(googleWebClientId);

  if (!showApple && !showGoogle) return null;

  const dividerLabel = mode === 'login' ? 'или войдите через' : 'или зарегистрируйтесь через';

  return (
    <View style={styles.wrap}>
      <View style={styles.divider}>
        <View style={styles.line} />
        <Text style={styles.dividerText}>{dividerLabel}</Text>
        <View style={styles.line} />
      </View>

      {showApple && (
        <AppleAuthentication.AppleAuthenticationButton
          buttonType={
            mode === 'login'
              ? AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN
              : AppleAuthentication.AppleAuthenticationButtonType.SIGN_UP
          }
          buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
          cornerRadius={BorderRadius.md}
          style={styles.appleButton}
          onPress={handleApple}
        />
      )}

      {showGoogle && (
        <TouchableOpacity
          style={styles.googleButton}
          onPress={handleGoogle}
          activeOpacity={0.8}
          disabled={busy !== null}
        >
          {busy === 'google' ? (
            <ActivityIndicator color={Colors.deepNavy} />
          ) : (
            <>
              <Ionicons name="logo-google" size={20} color={Colors.deepNavy} />
              <Text style={styles.googleText}>
                {mode === 'login' ? 'Войти через Google' : 'Создать через Google'}
              </Text>
            </>
          )}
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginTop: Spacing.lg,
    gap: Spacing.sm,
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.xs,
  },
  line: {
    flex: 1,
    height: 1,
    backgroundColor: Colors.border,
  },
  dividerText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
  },
  appleButton: {
    width: '100%',
    height: 48,
  },
  googleButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.background,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  googleText: {
    ...Typography.body,
    color: Colors.deepNavy,
    fontWeight: '600',
  },
});
