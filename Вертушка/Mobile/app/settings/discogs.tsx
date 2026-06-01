/**
 * Подключение Discogs-аккаунта (OAuth 1.0a).
 *
 * Зачем: запросы к Discogs API идут под персональным токеном юзера — свой
 * лимит 60 req/min вместо общего app-токена. Опционально: без подключения
 * приложение работает на общем токене как раньше.
 *
 * Flow: connect → backend отдаёт authorize_url → открываем в WebBrowser →
 * Discogs редиректит на backend /callback → тот меняет verifier на токен,
 * шифрует, сохраняет и редиректит обратно в приложение по deep-link
 * vertushka://discogs-callback?status=connected|expired|error.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import { Icon } from '@/components/ui';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { Colors, Spacing, BorderRadius, Typography } from '../../constants/theme';

const REDIRECT = 'vertushka://discogs-callback';

export default function DiscogsSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.getDiscogsStatus();
      setConnected(s.connected);
      setUsername(s.username);
    } catch {
      toast.error('Не удалось загрузить статус Discogs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleConnect = useCallback(async () => {
    setBusy(true);
    try {
      const { authorize_url } = await api.connectDiscogs();
      const result = await WebBrowser.openAuthSessionAsync(authorize_url, REDIRECT);

      if (result.type !== 'success' || !result.url) {
        // Юзер закрыл окно — тихо выходим.
        return;
      }

      const { queryParams } = Linking.parse(result.url);
      const status = queryParams?.status;

      if (status === 'connected') {
        toast.success('Discogs подключён');
        await loadStatus();
      } else if (status === 'expired') {
        toast.error('Сессия истекла, попробуйте снова');
      } else {
        toast.error('Не удалось подключить Discogs');
      }
    } catch {
      toast.error('Не удалось начать подключение');
    } finally {
      setBusy(false);
    }
  }, [loadStatus]);

  const handleDisconnect = useCallback(() => {
    Alert.alert(
      'Отключить Discogs?',
      'Запросы снова пойдут под общим токеном приложения.',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Отключить',
          style: 'destructive',
          onPress: async () => {
            setBusy(true);
            try {
              await api.disconnectDiscogs();
              setConnected(false);
              setUsername(null);
              toast.success('Discogs отключён');
            } catch {
              toast.error('Не удалось отключить');
            } finally {
              setBusy(false);
            }
          },
        },
      ]
    );
  }, []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Discogs</Text>
        <View style={styles.placeholder} />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={Colors.royalBlue} />
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <View style={styles.card}>
            <Icon
              name={connected ? 'checkmark-circle' : 'disc-outline'}
              size={48}
              color={connected ? Colors.success : Colors.royalBlue}
            />
            <Text style={styles.cardTitle}>
              {connected ? 'Аккаунт подключён' : 'Discogs не подключён'}
            </Text>
            {connected && username ? (
              <Text style={styles.cardUsername}>@{username}</Text>
            ) : null}
            <Text style={styles.cardDescription}>
              {connected
                ? 'Запросы к Discogs идут под вашим персональным токеном — это снимает общий лимит и ускоряет поиск.'
                : 'Подключите свой Discogs-аккаунт, чтобы запросы шли под вашим токеном с личным лимитом. Это необязательно — без подключения всё работает как раньше.'}
            </Text>
          </View>

          {connected ? (
            <TouchableOpacity
              style={[styles.button, styles.buttonDanger]}
              onPress={handleDisconnect}
              disabled={busy}
            >
              {busy ? (
                <ActivityIndicator size="small" color={Colors.warning} />
              ) : (
                <Text style={[styles.buttonText, styles.buttonTextDanger]}>Отключить</Text>
              )}
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              style={styles.button}
              onPress={handleConnect}
              disabled={busy}
            >
              {busy ? (
                <ActivityIndicator size="small" color="#FFF" />
              ) : (
                <Text style={styles.buttonText}>Подключить Discogs</Text>
              )}
            </TouchableOpacity>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  backButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { ...Typography.h3, color: Colors.text },
  placeholder: { width: 40 },
  content: { padding: Spacing.lg },
  card: {
    alignItems: 'center',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.lg,
    marginBottom: Spacing.lg,
  },
  cardTitle: { ...Typography.h3, color: Colors.text, marginTop: Spacing.md, textAlign: 'center' },
  cardUsername: { ...Typography.body, color: Colors.royalBlue, marginTop: Spacing.xs },
  cardDescription: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginTop: Spacing.sm,
    lineHeight: 20,
  },
  button: {
    backgroundColor: Colors.royalBlue,
    borderRadius: BorderRadius.md,
    paddingVertical: Spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
  },
  buttonText: { ...Typography.button, color: '#FFF' },
  buttonDanger: { backgroundColor: 'transparent', borderWidth: 1, borderColor: Colors.warning },
  buttonTextDanger: { color: Colors.warning },
});
