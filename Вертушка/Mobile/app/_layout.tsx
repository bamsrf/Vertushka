/**
 * Root Layout - проверка авторизации и роутинг
 */
import { useEffect, useRef, useState } from 'react';
import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import * as SplashScreen from 'expo-splash-screen';
import * as Notifications from 'expo-notifications';
import * as Updates from 'expo-updates';
import Constants from 'expo-constants';
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
} from '@expo-google-fonts/inter';
import { AppState, AppStateStatus, Platform } from 'react-native';
import { useAuthStore, useOnboardingStore } from '../lib/store';
import {
  useMessagesStore,
  initMessagesRealtime,
  teardownMessagesRealtime,
} from '../lib/messagesStore';
import { useNotificationsStore } from '../lib/notificationsStore';
import { api } from '../lib/api';
import { registerPushToken } from '../lib/push';
import { routeForPush } from '../lib/pushRouting';

// Sentry загружается только если пакет установлен (не в Expo Go)
type SentryStub = {
  init: (c: object) => void;
  wrap: <T>(c: T) => T;
  setTags: (tags: Record<string, string>) => void;
  setUser: (user: { id: string } | null) => void;
};
let Sentry: SentryStub = {
  init: () => {},
  wrap: (c) => c,
  setTags: () => {},
  setUser: () => {},
};
try {
  Sentry = require('@sentry/react-native');
} catch {
  // Expo Go — Sentry недоступен, используем заглушку
}
import { Colors } from '../constants/theme';
import { OfflineBanner } from '../components/OfflineBanner';
import {
  AchievementUnlockHost,
  notifyAchievementUnlocked,
} from '../components/AchievementUnlockOverlay';
import { GiftMatchModal } from '../components/GiftMatchModal';
import { MascotIntro } from '../components/MascotIntro';
import { initFirstStepsWatcher } from '../lib/onboardingProgress';
import { InAppNotificationToastHost, inAppToast } from '../components/notifications/InAppNotificationToast';
import { ToastHost } from '../components/ToastHost';
import { analytics, initAmplitude } from '../lib/analytics';
import { initDeviceMetrics } from '../lib/deviceMetrics';
import { useRemoteConfigStore } from '../lib/remoteConfig';
import { ForceUpdateScreen } from '../components/ForceUpdateScreen';
import { clampSystemFontScale } from '../lib/responsive';

// Ограничиваем системный font-scale до старта рендера — крупный «Размер текста»
// в настройках устройства не должен ломать верстку (ms() уже даёт нужный размер).
clampSystemFontScale();

Notifications.setNotificationHandler({
  handleNotification: async () => {
    // В foreground мы показываем свой in-app toast и подавляем OS-баннер
    const inForeground = AppState.currentState === 'active';
    return {
      shouldShowAlert: !inForeground,
      shouldPlaySound: !inForeground,
      shouldSetBadge: false,
      shouldShowBanner: !inForeground,
      shouldShowList: true,
    };
  },
});

/**
 * Ошибки, которые не являются багами: обрыв связи, таймаут, отменённый
 * запрос, протухший токен. Их сотни в сутки на живой аудитории, и они
 * топят реальные краши — после чего Sentry перестают читать вообще.
 */
const EXPECTED_ERROR_PATTERNS = [
  /Network Error/i,
  /timeout of \d+ms exceeded/i,
  /ECONNABORTED/i,
  /AbortError/i,
  /Request aborted/i,
  /UnauthorizedError/i,
];

function isExpectedError(event: any, hint: any): boolean {
  const error = hint?.originalException;
  const message: string =
    (typeof error === 'string' ? error : error?.message) ?? event?.message ?? '';

  if (EXPECTED_ERROR_PATTERNS.some((re) => re.test(message))) return true;
  // 401 — штатное протухание access-токена, его чинит refresh-интерцептор.
  if (error?.response?.status === 401) return true;

  return false;
}

const sentryDsn = Constants.expoConfig?.extra?.sentryDsn as string | undefined;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: __DEV__ ? 'development' : 'production',
    tracesSampleRate: 0.2,
    attachScreenshot: false,
    // Явно, а не полагаясь на дефолт: с setUser по id в Sentry не должно
    // попадать ничего сверх идентификатора — ни IP, ни данных устройства,
    // которые SDK добавляет в PII-режиме.
    sendDefaultPii: false,
    beforeSend: (event: any, hint: any) => (isExpectedError(event, hint) ? null : event),
  });

  // OTA-теги. Sentry сам проставляет release/dist из нативного билда, но при
  // EAS Update номер билда не меняется — без updateId нельзя понять, на какой
  // именно версии JS упало и помог ли выкаченный фикс.
  try {
    Sentry.setTags({
      app_version: (Constants.expoConfig?.version as string | undefined) ?? 'unknown',
      ota_update_id: Updates.updateId ?? 'embedded',
      ota_channel: Updates.channel ?? 'unknown',
      ota_runtime_version: Updates.runtimeVersion ?? 'unknown',
    });
  } catch {
    // expo-updates недоступен (Expo Go) — теги не критичны.
  }

  // Термальное состояние и MetricKit. Строго после Sentry.init — обработчики
  // внутри сразу пишут теги и breadcrumb'ы, до инициализации они пропадут.
  // И как можно раньше в целом: iOS отдаёт накопленные пейлоады вскоре после
  // запуска, опоздавшая подписка их не увидит. Без нативного модуля (Expo Go,
  // Android, web) вызов тихо ничего не делает.
  initDeviceMetrics();
}

const amplitudeApiKey = Constants.expoConfig?.extra?.amplitudeApiKey as string | undefined;
if (amplitudeApiKey) {
  initAmplitude(amplitudeApiKey)
    // app_opened шлём ТОЛЬКО после инициализации: до неё провайдер ещё null,
    // и track() молча выбрасывает событие. Потерянный app_opened — это
    // заниженный знаменатель во всех воронках и сломанный retention.
    .then(() => analytics.appOpened())
    .catch(() => {
      // тихо — аналитика не должна ломать загрузку приложения
    });
} else if (__DEV__) {
  // Ключ инлайнится в бандл на этапе сборки. Если AMPLITUDE_API_KEY не был
  // выставлен, аналитика отваливается целиком и совершенно беззвучно —
  // предупреждение делает это заметным до того, как кто-то пойдёт искать
  // события в дашборде.
  console.warn('[Analytics] AMPLITUDE_API_KEY не задан — аналитика отключена');
}

SplashScreen.preventAutoHideAsync();

function RootLayout() {
  const { checkAuth, isLoading, isAuthenticated, user } = useAuthStore();
  const { checkOnboarding, isReady: onboardingReady } = useOnboardingStore();
  const needsUpdate = useRemoteConfigStore((s) => s.needsUpdate);
  const remoteConfig = useRemoteConfigStore((s) => s.config);
  const loadRemoteConfig = useRemoteConfigStore((s) => s.load);
  const router = useRouter();
  const notificationListener = useRef<Notifications.EventSubscription | null>(null);
  const responseListener = useRef<Notifications.EventSubscription | null>(null);
  // Запоминаем, был ли пользователь когда-либо авторизован за время сессии,
  // чтобы редирект на /(auth)/login срабатывал только при потере авторизации,
  // а не на холодном старте (когда isAuthenticated изначально false).
  const wasAuthenticatedRef = useRef(false);
  // Интро-заставка маскота — играет один раз за холодный старт, поверх UI,
  // сразу после того как скрылся native splash. См. MascotIntro / ТЗ §6.
  const [introDone, setIntroDone] = useState(false);
  // Целевой путь тапнутого пуша, ожидающий готовности навигации/авторизации.
  // Стейт (не ref), чтобы установка из listener/cold-start триггерила flush-эффект.
  const [pendingRoute, setPendingRoute] = useState<string | null>(null);

  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    Inter_800ExtraBold,
    'RubikMonoOne-Regular': require('../assets/fonts/RubikMonoOne-Regular.ttf'),
  });

  useEffect(() => {
    checkAuth();
    loadRemoteConfig();
    // Шаги чеклиста закрываются на экранах, где самой карточки не видно
    // (профиль, поиск, настройки Discogs). Наблюдатель живёт в корне и
    // показывает тост там, где человек находится в этот момент.
    initFirstStepsWatcher();
  }, []);

  // Флаг онбординга живёт per-user, поэтому читается не на маунте, а когда
  // стал известен аккаунт — и перечитывается при смене аккаунта на устройстве.
  useEffect(() => {
    checkOnboarding(user?.id ?? null);
  }, [user?.id, checkOnboarding]);

  // Привязка событий Sentry к аккаунту.
  //
  // Зачем: MetricKit и термальные события (lib/deviceMetrics.ts) уезжают в
  // Sentry обезличенными, и «посмотреть метрики конкретного тестера» без этого
  // невозможно — в потоке событий нельзя отличить одного пользователя от
  // другого.
  //
  // Шлём ТОЛЬКО id. Ни username, ни email, ни IP: для разбора перф-жалобы
  // достаточно идентификатора, а Sentry — внешнее по отношению к базе
  // хранилище, и лишних персональных данных там быть не должно.
  //
  // Один эффект на весь стор вместо правки шести веток логина (пароль,
  // Google, Apple, Discogs, регистрация, восстановление сессии): здесь же
  // ловится и холодный старт через checkAuth, и разлогин.
  useEffect(() => {
    Sentry.setUser(user ? { id: user.id } : null);
  }, [user?.id]);

  // Перечитываем конфиг при возврате из фона: пользователь может держать
  // приложение открытым сутками, а рубильник должен доезжать до него без
  // перезапуска.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') loadRemoteConfig();
    });
    return () => sub.remove();
  }, [loadRemoteConfig]);

  useEffect(() => {
    // Foreground: уведомление пришло пока приложение открыто — рефрешим unread
    // и показываем in-app toast (OS-баннер подавлен через handleNotification).
    notificationListener.current = Notifications.addNotificationReceivedListener((event) => {
      const content = event.request.content;
      const data = (content.data || {}) as Record<string, unknown>;
      const type = data.type as string | undefined;

      // Личные сообщения (accepted) живут в чате, не в ленте «Ты» — они не
      // должны зажигать бейдж/pill уведомлений, только счётчик сообщений.
      if (type === 'message' || type === 'message_request') {
        useMessagesStore.getState().refreshUnread();
      }
      if (type !== 'message') {
        const store = useNotificationsStore.getState();
        store.bumpUnread();   // мгновенно зажечь бейдж на аватарке
        store.bumpPending();  // pill «Показать N новых», если экран открыт
        // Реконсиляция абсолютного значения после коммита на бэке (гонка).
        setTimeout(() => useNotificationsStore.getState().fetchUnreadCount(), 2000);
      }

      if (AppState.currentState === 'active') {
        // Ачивка празднуется одинаково, откуда бы ни пришла: пуш открывает тот
        // же overlay с конфетти, что и локальный diff. Раньше пуш давал только
        // тост — и эффект «то есть, то нет» в зависимости от источника.
        const achievementCode = data.code as string | undefined;
        const isAchievement =
          type === 'achievement_unlocked' || type === 'milestone_unlocked';

        if (isAchievement && achievementCode) {
          // notifyAchievementUnlocked дедуплицирует: если diff уже показал эту
          // ачивку, повтора не будет — и тост тоже не нужен.
          notifyAchievementUnlocked([achievementCode]);
        } else {
          inAppToast.show({
            id: event.request.identifier,
            title: content.title || 'Уведомление',
            body: content.body || '',
            data,
          });
        }
      }
    });

    // Tap по OS-пушу (warm): не навигируем сразу — кладём цель в pendingRoute,
    // flush-эффект доведёт до раздела, когда навигация/авторизация готовы.
    responseListener.current = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response.notification.request.content.data as Record<string, unknown>;
      setPendingRoute(routeForPush(data));
    });

    // Cold start: приложение запущено ТАПОМ по пушу (было закрыто). Живой listener
    // такой «запускающий» ответ не гарантирует — читаем его явно, иначе тап уводил
    // на дефолтный экран («бросало на полпути»).
    Notifications.getLastNotificationResponseAsync()
      .then((response) => {
        if (response) {
          const data = response.notification.request.content.data as Record<string, unknown>;
          setPendingRoute(routeForPush(data));
        }
      })
      .catch(() => {});

    return () => {
      notificationListener.current?.remove();
      responseListener.current?.remove();
    };
  }, []);

  // Регистрация Expo push-токена + рефреш unread на foreground.
  // Системный промпт здесь НЕ показываем (pre-permission UX): токен регистрируется
  // только если разрешение уже выдано. Сам запрос — из контекстных точек
  // (сообщения, настройки уведомлений), см. lib/push.ts.
  useEffect(() => {
    if (!isAuthenticated) return;

    registerPushToken({ requestIfNeeded: false });

    // Флаг обязан быть объявлен: без него колбэк ниже читает несуществующий
    // глобал и падает на Hermes с «Property 'cancelled' doesn't exist». То есть
    // ротация токена не просто не защищалась от гонки — она вообще не
    // доезжала до сохранения, и бэк продолжал слать на мёртвый токен ровно в
    // том сценарии, ради которого слушатель и заведён.
    let cancelled = false;

    // R3: APNs/FCM может сменить токен в любой момент — слушаем ротацию и
    // пересохраняем, иначе бэк продолжит слать на мёртвый токен.
    const tokenSub = Notifications.addPushTokenListener((t) => {
      if (t?.data && !cancelled) {
        api.savePushToken(t.data).catch(() => {});
      }
    });

    useNotificationsStore.getState().fetchUnreadCount();

    // Глобальный polling: пока приложение активно, раз в 60с подтягиваем unreadCount,
    // чтобы красная точка на аватаре появлялась даже без push (например, события без
    // push'а или quiet hours). При уходе в background — таймер останавливается.
    // 60с вместо 30с: badge — не realtime-фича, а основной канал всё равно push.
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = setInterval(() => {
        useNotificationsStore.getState().fetchUnreadCount();
      }, 60_000);
    };
    const stopPolling = () => {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    };
    if (AppState.currentState === 'active') startPolling();

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        useNotificationsStore.getState().fetchUnreadCount();
        startPolling();
      } else {
        stopPolling();
      }
    });

    return () => {
      cancelled = true;
      stopPolling();
      sub.remove();
      tokenSub.remove();
    };
  }, [isAuthenticated]);

  // Realtime + fallback polling unread-счётчика.
  // WS приоритетен; polling работает как safety-net (раз в 60с) если соединение
  // отвалилось — на WS-событиях счётчик обновляется в реальном времени.
  useEffect(() => {
    if (!isAuthenticated) {
      teardownMessagesRealtime();
      return;
    }

    initMessagesRealtime();
    const refresh = () => useMessagesStore.getState().refreshUnread();
    refresh();

    let timer: ReturnType<typeof setInterval> | null = setInterval(refresh, 60_000);
    let appState: AppStateStatus = AppState.currentState;

    const sub = AppState.addEventListener('change', (next) => {
      if (appState.match(/inactive|background/) && next === 'active') {
        // Сокет мог быть закрыт при уходе в фон — поднимаем заново.
        // initMessagesRealtime идемпотентен (гард _wsSubscribed).
        initMessagesRealtime();
        refresh();
        if (!timer) timer = setInterval(refresh, 60_000);
      } else if (next === 'background') {
        // Рвём WS: открытый сокет в фоне держит соединение и продолжает
        // крутить backoff-реконнекты, когда ОС его роняет. Это батарея и
        // нагрев без единого зрителя.
        //
        // Только 'background', НЕ 'inactive': на iOS 'inactive' прилетает от
        // шторки уведомлений, переключателя приложений и баннера звонка —
        // рвать сокет на каждое такое касание значит дёргать его впустую.
        teardownMessagesRealtime();
        if (timer) {
          clearInterval(timer);
          timer = null;
        }
      }
      appState = next;
    });

    return () => {
      if (timer) clearInterval(timer);
      sub.remove();
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (fontsLoaded && !isLoading && onboardingReady) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [fontsLoaded, isLoading, onboardingReady]);

  // Глобальный auth-watchdog: если пользователь был залогинен и потерял сессию
  // (refresh-токен невалиден) — уводим на login независимо от текущего экрана.
  useEffect(() => {
    if (isAuthenticated) {
      wasAuthenticatedRef.current = true;
      return;
    }
    if (wasAuthenticatedRef.current && !isLoading) {
      wasAuthenticatedRef.current = false;
      router.replace('/(auth)/login');
    }
  }, [isAuthenticated, isLoading, router]);

  // Flush pending deep-link из тапнутого пуша. Ждём готовности навигации (шрифты/
  // онбординг), окончания загрузки авторизации И самой авторизации — иначе
  // auth-redirect на /(auth)/login перебьёт push и юзер не доедет до раздела.
  // requestAnimationFrame — гарантия, что корневой Stack уже смонтирован.
  useEffect(() => {
    if (!pendingRoute) return;
    if (isAuthenticated && !isLoading && fontsLoaded && onboardingReady) {
      const target = pendingRoute;
      setPendingRoute(null);
      requestAnimationFrame(() => router.push(target as any));
    }
  }, [pendingRoute, isAuthenticated, isLoading, fontsLoaded, onboardingReady, router]);

  if (!fontsLoaded || isLoading || !onboardingReady) {
    return null;
  }

  // Версия ниже минимальной — дальше не пускаем. Проверка не блокирует
  // холодный старт (см. remoteConfig.load), поэтому экран может появиться
  // на мгновение позже сплэша — это осознанный размен в пользу скорости.
  if (needsUpdate && remoteConfig) {
    return (
      <SafeAreaProvider>
        <StatusBar style="dark" />
        <ForceUpdateScreen
          message={remoteConfig.update_message}
          storeUrl={remoteConfig.store_url}
        />
      </SafeAreaProvider>
    );
  }

  return (
    // Фон корневого view — тот же, что у splash и у контента: иначе в стыке
    // «скрылся splash → смонтировался Stack» проглядывает белая подложка
    // RN-окна и старт мигает.
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: Colors.background }}>
      <BottomSheetModalProvider>
        <SafeAreaProvider>
          <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: Colors.background },
            animation: 'slide_from_right',
            gestureEnabled: true,
            // Экран, перекрытый вышележащим, перестаёт ре-рендериться.
            // Без этого открытая карточка пластинки оставляла под собой живой
            // весь таб: сетку коллекции, авто-рейлы Поиска, градиент
            // collection/value. Тот же приём, что в (tabs)/_layout.tsx, но
            // покрывает Stack — а именно в нём живут экраны с бесконечными
            // анимациями мимо lib/useAnimationGate.ts.
            // См. docs/plans/appstore/APPSTORE_LAUNCH_PLAN.md §4.4.
            freezeOnBlur: true,
          }}
        >
          <Stack.Screen name="(auth)" />
          <Stack.Screen name="onboarding" options={{ animation: 'fade' }} />
          <Stack.Screen name="(tabs)" />
          <Stack.Screen
            name="profile"
            options={{
              presentation: 'modal',
              animation: 'slide_from_bottom',
            }}
          />
          <Stack.Screen name="record/[id]" />
          <Stack.Screen name="radar" />
          <Stack.Screen name="market/index" options={{ animation: 'fade' }} />
          <Stack.Screen name="market/store/[slug]" />
          <Stack.Screen name="folder/[id]" />
          <Stack.Screen name="wishlist-folder/[id]" />
          <Stack.Screen name="settings/edit-profile" />
          <Stack.Screen name="settings/share-profile" />
          <Stack.Screen name="user/[username]/index" />
          <Stack.Screen
            name="social/follow-requests"
            options={{ headerShown: true, title: 'Запросы на подписку' }}
          />
          <Stack.Screen name="collection/value" />
          <Stack.Screen name="settings/notifications" />
          <Stack.Screen name="settings/wishlists" />
          <Stack.Screen name="gift/[id]" />
          <Stack.Screen name="social/list" />
          <Stack.Screen name="dev/icons" />
          <Stack.Screen name="dev/thermal" options={{ headerShown: true, title: 'Термальное состояние' }} />
          <Stack.Screen name="achievements" options={{ headerShown: true, title: 'Ачивки' }} />
          <Stack.Screen name="user/[username]/achievements" options={{ headerShown: true, title: 'Ачивки' }} />
          <Stack.Screen name="messages/index" />
          <Stack.Screen name="messages/[conversationId]" />
          <Stack.Screen name="messages/new" options={{ presentation: 'modal', animation: 'slide_from_bottom' }} />
          <Stack.Screen
            name="notifications"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
          <Stack.Screen
            name="legal/index"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
          <Stack.Screen
            name="legal/terms"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
          <Stack.Screen
            name="legal/privacy"
            options={{ presentation: 'modal', animation: 'slide_from_bottom' }}
          />
        </Stack>
        <AchievementUnlockHost />
        {/* Спрашивает «это подарок?», когда добавленная пластинка совпала
            с забронированным пунктом вишлиста. Живёт здесь, а не на экранах:
            добавить в коллекцию можно из скана, поиска и карточки релиза. */}
        <GiftMatchModal />
        {!introDone && <MascotIntro onFinish={() => setIntroDone(true)} />}
        <InAppNotificationToastHost />
        {/* Порядок = z-order оверлеев: каждый следующий RootOverlay создаёт
            своё UIWindow выше предыдущего. Тост последний — он самый срочный
            и должен ложиться поверх плашки «нет сети». */}
        <OfflineBanner />
        <ToastHost />
        </SafeAreaProvider>
      </BottomSheetModalProvider>
    </GestureHandlerRootView>
  );
}

export default Sentry.wrap(RootLayout);
