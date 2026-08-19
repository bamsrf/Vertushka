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
import { useCallback, useEffect, useRef, useState } from 'react';
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
import { analytics } from '../../lib/analytics';
import { useCollectionStore } from '../../lib/store';
import { setDiscogsConnected } from '../../lib/onboardingProgress';
import { Colors, Spacing, BorderRadius, Typography } from '../../constants/theme';
import type { DiscogsImportPhase, DiscogsPriceJobStatus } from '../../lib/types';

const REDIRECT = 'vertushka://discogs-callback';

export default function DiscogsSettings() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [importing, setImporting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  // Прогресс фоновой дозагрузки цен. null — показывать нечего.
  const [priceJob, setPriceJob] = useState<DiscogsPriceJobStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  /**
   * Поллинг прогресса цен.
   *
   * Раз в 5 секунд: воркер на бэкенде просыпается раз в минуту и берёт по 50
   * записей, так что чаще спрашивать бессмысленно, а реже — прогресс-бар
   * выглядит замершим.
   *
   * Экран можно закрыть и вернуться: статус живёт в БД, а не в стейте, поэтому
   * поллинг поднимается заново на маунте, если задача ещё в работе.
   */
  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getDiscogsImportStatus();
        setPriceJob(s);
        if (s.status === 'done' || s.status === 'failed' || s.status === 'idle') {
          stopPolling();
          // Цены приехали — полка их ещё не знает: экран коллекции
          // смонтирован и сам о фоновой задаче не узнает.
          if (s.updated > 0) {
            await useCollectionStore.getState().fetchCollectionItems();
          }
        }
      } catch {
        // Сеть моргнула — не срываем поллинг, следующий тик попробует снова.
      }
    }, 5000);
  }, [stopPolling]);

  useEffect(() => stopPolling, [stopPolling]);

  // Гард для await-циклов: экран могли закрыть, пока импорт шёл, — setState
  // после анмаунта не нужен, а сам импорт живёт на бэкенде и не пострадает.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /**
   * Ждёт финала фонового импорта (поле `import` статус-ручки), поллинг раз
   * в 3 секунды. null — экран закрыт или статус потерян (рестарт бэкенда).
   */
  const waitImportFinished = useCallback(async (): Promise<DiscogsImportPhase | null> => {
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      if (!mountedRef.current) return null;
      try {
        const s = await api.getDiscogsImportStatus();
        const phase = s.import;
        // idle после старта = бэкенд перезапустился и потерял задачу.
        if (!phase || phase.status === 'idle') return null;
        if (phase.status === 'done' || phase.status === 'failed') return phase;
      } catch {
        // Сеть моргнула — следующий тик попробует снова.
      }
    }
  }, []);

  /** Общий финал импорта: аналитика, рефетч полки, поллинг цен, алерт. */
  const finishImport = useCallback(
    async (imported: number, skipped: number, total: number) => {
      analytics.importCompleted({ imported, skipped, total });
      // Экран коллекции грузится один раз на маунте и остаётся
      // смонтированным, поэтому сам импорт он бы не заметил: до
      // pull-to-refresh полка выглядела бы пустой, а чеклист —
      // сломанным сразу после главного действия онбординга.
      await useCollectionStore.getState().fetchCollections();
      await useCollectionStore.getState().fetchCollectionItems();
      // Импорт — массовая смена владения: owned-ids теперь обновляются
      // только по мутациям, а не прицепом к fetchCollectionItems.
      useCollectionStore.getState().fetchOwnedIds();

      // Цены приезжают отдельно и минутами позже — без этого юзер видел бы
      // полку с прочерками вместо стоимости и считал бы это поломкой импорта.
      let pricesPending = 0;
      try {
        const s = await api.getDiscogsImportStatus();
        if (s.status === 'pending' || s.status === 'running') {
          pricesPending = s.total;
          setPriceJob(s);
          startPolling();
        }
      } catch {
        // Статус цен — не повод портить финал импорта.
      }

      // Alert, а не toast: итог импорта — это три числа плюс приписка
      // про фоновые цены, такое не влезает в плашку и его хочется
      // прочитать не спеша. (Тост тут теперь виден — корневой хост
      // живёт в RootOverlay, см. components/ToastHost.tsx.)
      Alert.alert(
        'Импорт завершён',
        `Добавлено: ${imported}, пропущено: ${skipped} из ${total}` +
          (pricesPending > 0
            ? `.\n\nЦены подтягиваются в фоне — это займёт несколько минут.`
            : '')
      );
    },
    [startPolling]
  );

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.getDiscogsStatus();
      setConnected(s.connected);
      setUsername(s.username);
      // Чеклист «Первые шаги» держит статус у себя — иначе узнал бы о
      // подключении только в следующую сессию.
      setDiscogsConnected(s.connected);

      // Импорт/дозагрузка могли остаться с прошлого захода: юзер импортнул,
      // вышел из экрана и вернулся. Подхватываем прогресс обоих.
      if (s.connected) {
        try {
          const job = await api.getDiscogsImportStatus();
          if (job.import?.status === 'running') {
            // Сам импорт ещё идёт — досиживаем его, финал покажем как обычно.
            setImporting(true);
            waitImportFinished()
              .then(async (phase) => {
                if (!mountedRef.current) return;
                if (phase && phase.status === 'done') {
                  await finishImport(phase.imported, phase.skipped, phase.total);
                }
              })
              .finally(() => {
                if (mountedRef.current) setImporting(false);
              });
          } else if (job.status === 'pending' || job.status === 'running') {
            setPriceJob(job);
            startPolling();
          }
        } catch {
          // Статус цен — не повод ронять весь экран.
        }
      }
    } catch {
      Alert.alert('Discogs', 'Не удалось загрузить статус Discogs');
    } finally {
      setLoading(false);
    }
  }, [startPolling, waitImportFinished, finishImport]);

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
        Alert.alert('Discogs', 'Аккаунт подключён');
        await loadStatus();
      } else if (status === 'expired') {
        Alert.alert('Discogs', 'Сессия истекла, попробуйте снова');
      } else {
        Alert.alert('Discogs', 'Не удалось подключить Discogs');
      }
    } catch {
      Alert.alert('Discogs', 'Не удалось начать подключение');
    } finally {
      setBusy(false);
    }
  }, [loadStatus]);

  const handleImport = useCallback(() => {
    Alert.alert(
      'Импортировать коллекцию?',
      'Все пластинки из вашей коллекции Discogs добавятся в основную коллекцию. Уже добавленные пропустятся.',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Импортировать',
          onPress: async () => {
            setImporting(true);
            try {
              const r = await api.importDiscogsCollection();

              if (r.status === 'started') {
                // Импорт ушёл в фон (202) — ждём финал через статус-ручку,
                // спиннер «Импортируем…» крутится всё это время.
                const phase = await waitImportFinished();
                if (!mountedRef.current) return;
                if (!phase || phase.status !== 'done') {
                  Alert.alert(
                    'Не удалось импортировать',
                    phase?.error || 'Попробуйте позже'
                  );
                  return;
                }
                await finishImport(phase.imported, phase.skipped, phase.total);
                return;
              }

              // Старый бэкенд: результат пришёл синхронно, прежний путь.
              await finishImport(r.imported, r.skipped, r.total);
            } catch (e: any) {
              Alert.alert('Не удалось импортировать', e?.response?.data?.detail || 'Попробуйте позже');
            } finally {
              if (mountedRef.current) setImporting(false);
            }
          },
        },
      ]
    );
  }, [finishImport, waitImportFinished]);

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
              setDiscogsConnected(false);
              setUsername(null);
              Alert.alert('Discogs', 'Аккаунт отключён');
            } catch {
              Alert.alert('Discogs', 'Не удалось отключить');
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
                : 'Подключите Discogs — и перенесите всю свою коллекцию в Вертушку за пару секунд. Заодно запросы пойдут под вашим личным токеном, без общих лимитов. Подключение необязательно: без него всё работает как раньше.'}
            </Text>
          </View>

          {priceJob && priceJob.status !== 'idle' ? (
            <View style={styles.priceCard}>
              <View style={styles.priceHeader}>
                <Icon
                  name={priceJob.status === 'failed' ? 'alert-circle' : 'pricetag-outline'}
                  size={18}
                  color={priceJob.status === 'failed' ? Colors.warning : Colors.royalBlue}
                />
                <Text style={styles.priceTitle}>
                  {priceJob.status === 'done'
                    ? 'Цены обновлены'
                    : priceJob.status === 'failed'
                      ? 'Цены обновятся позже'
                      : 'Подтягиваем цены'}
                </Text>
              </View>

              {priceJob.status === 'failed' ? (
                <Text style={styles.priceHint}>
                  {priceJob.error || 'Попробуем ещё раз при следующем обновлении.'}
                </Text>
              ) : (
                <>
                  {/* Ширина от processed, а не от updated: у части пластинок
                      на Discogs просто нет лотов, и цены у них не будет
                      никогда — прогресс по updated замирал бы, не доходя
                      до конца. */}
                  <View style={styles.progressTrack}>
                    <View
                      style={[
                        styles.progressFill,
                        {
                          width: `${Math.min(
                            100,
                            priceJob.total > 0
                              ? Math.round((priceJob.processed / priceJob.total) * 100)
                              : 0
                          )}%`,
                        },
                      ]}
                    />
                  </View>
                  <Text style={styles.priceHint}>
                    {priceJob.status === 'done'
                      ? `Цена появилась у ${priceJob.updated} из ${priceJob.total} пластинок.`
                      : `${priceJob.processed} из ${priceJob.total}. Можно закрыть экран — дозагрузка продолжится.`}
                  </Text>
                </>
              )}
            </View>
          ) : null}

          {connected ? (
            <>
              <TouchableOpacity
                style={styles.button}
                onPress={handleImport}
                disabled={importing || busy}
              >
                {importing ? (
                  <ActivityIndicator size="small" color="#FFF" />
                ) : (
                  <Text style={styles.buttonText}>Импортировать коллекцию</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.button, styles.buttonDanger, { marginTop: Spacing.md }]}
                onPress={handleDisconnect}
                disabled={busy || importing}
              >
                {busy ? (
                  <ActivityIndicator size="small" color={Colors.warning} />
                ) : (
                  <Text style={[styles.buttonText, styles.buttonTextDanger]}>Отключить</Text>
                )}
              </TouchableOpacity>
            </>
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
  priceCard: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    marginBottom: Spacing.lg,
  },
  priceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  priceTitle: { ...Typography.bodySmall, color: Colors.text, fontWeight: '600' },
  priceHint: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginTop: Spacing.sm,
    lineHeight: 18,
  },
  progressTrack: {
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.divider,
    marginTop: Spacing.md,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
    backgroundColor: Colors.royalBlue,
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
