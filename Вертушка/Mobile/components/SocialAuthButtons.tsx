/**
 * Кнопки социального входа: Apple (iOS) и Google.
 * Используется на экранах login и register.
 */
import { useEffect, useState } from 'react';
import { Platform, StyleSheet, Text, TouchableOpacity, View, ActivityIndicator } from 'react-native';
import Constants from 'expo-constants';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import { Icon } from '@/components/ui';
import { toast } from '../lib/toast';
import { api } from '../lib/api';
import { useAuthStore } from '../lib/store';
import { Colors, Typography, Spacing, BorderRadius } from '../constants/theme';

const DISCOGS_REDIRECT = 'vertushka://discogs-callback';

// Нативные модули — недоступны в Expo Go, поэтому импорт ленивый
let AppleAuthentication: any = null;
try {
  AppleAuthentication = require('expo-apple-authentication');
} catch {
  // Expo Go — Apple Sign In кнопка не покажется
}

let GoogleSignin: any = null;
let statusCodes: any = {};
try {
  const mod = require('@react-native-google-signin/google-signin');
  GoogleSignin = mod.GoogleSignin;
  statusCodes = mod.statusCodes ?? {};
} catch {
  // Expo Go — модуль не собран, кнопка просто не покажется
}

const googleWebClientId =
  (Constants.expoConfig?.extra?.googleWebClientId as string | undefined) ?? '';
const googleIosClientId =
  (Constants.expoConfig?.extra?.googleIosClientId as string | undefined) ?? '';

let googleConfigured = false;
function ensureGoogleConfigured() {
  if (googleConfigured || !googleWebClientId || !GoogleSignin) return;
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
  const { loginWithApple, loginWithGoogle, loginWithDiscogs } = useAuthStore();
  const [appleAvailable, setAppleAvailable] = useState(false);
  const [busy, setBusy] = useState<null | 'apple' | 'google' | 'discogs'>(null);

  useEffect(() => {
    if (Platform.OS === 'ios' && AppleAuthentication) {
      AppleAuthentication.isAvailableAsync().then(setAppleAvailable).catch(() => setAppleAvailable(false));
    }
  }, []);

  const handleApple = async () => {
    if (busy || !AppleAuthentication) return;
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
    if (!GoogleSignin) {
      toast.error('Google Sign In недоступен', 'Нужен dev-build или production-сборка');
      return;
    }
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

  const handleDiscogs = async () => {
    if (busy) return;
    setBusy('discogs');
    try {
      const { authorize_url } = await api.discogsLoginStart();
      const result = await WebBrowser.openAuthSessionAsync(authorize_url, DISCOGS_REDIRECT);
      if (result.type !== 'success' || !result.url) {
        return; // юзер закрыл окно
      }
      const { queryParams } = Linking.parse(result.url);
      const status = queryParams?.status;
      const ticket = queryParams?.ticket;
      if (status === 'login' && typeof ticket === 'string') {
        await loginWithDiscogs(ticket);
      } else if (status === 'expired') {
        toast.error('Сессия истекла', 'Попробуйте снова');
      } else {
        toast.error('Не удалось войти через Discogs');
      }
    } catch (error: any) {
      toast.error('Ошибка входа через Discogs', error?.response?.data?.detail || error?.message || 'Попробуйте позже');
    } finally {
      setBusy(null);
    }
  };

  const showApple = Platform.OS === 'ios' && appleAvailable && AppleAuthentication;
  // Google Sign In скрыт: ФЗ о запрете авторизации через иностранные сервисы (ГД, 09.06.2026).
  // Код входа сохранён — снять флаг, чтобы вернуть кнопку.
  const showGoogle = false && Boolean(GoogleSignin && googleWebClientId);
  const showDiscogs = true; // OAuth через WebBrowser — без нативных модулей

  if (!showApple && !showGoogle && !showDiscogs) return null;

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
              <Icon name="logo-google" size={20} color={Colors.deepNavy} />
              <Text style={styles.googleText}>
                {mode === 'login' ? 'Войти через Google' : 'Создать через Google'}
              </Text>
            </>
          )}
        </TouchableOpacity>
      )}

      {showDiscogs && (
        <TouchableOpacity
          style={styles.discogsButton}
          onPress={handleDiscogs}
          activeOpacity={0.8}
          disabled={busy !== null}
        >
          {busy === 'discogs' ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Icon name="disc-outline" size={20} color="#FFF" />
              <Text style={styles.discogsText}>
                {mode === 'login' ? 'Войти через Discogs' : 'Создать через Discogs'}
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
  discogsButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    height: 48,
    borderRadius: BorderRadius.md,
    backgroundColor: '#333333',
  },
  discogsText: {
    ...Typography.body,
    color: '#FFF',
    fontWeight: '600',
  },
});
