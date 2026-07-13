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

// Sentry загружается только если пакет установлен (не в Expo Go)
type SentryStub = { init: (c: object) => void; wrap: <T>(c: T) => T };
let Sentry: SentryStub = { init: () => {}, wrap: (c) => c };
try {
  Sentry = require('@sentry/react-native');
} catch {
  // Expo Go — Sentry недоступен, используем заглушку
}
import { Colors } from '../constants/theme';
import { OfflineBanner } from '../components/OfflineBanner';
import { OnboardingOverlay } from '../components/OnboardingOverlay';
import { AchievementUnlockHost } from '../components/AchievementUnlockOverlay';
import { MascotIntro } from '../components/MascotIntro';
import { InAppNotificationToastHost, inAppToast } from '../components/notifications/InAppNotificationToast';
import Toast from 'react-native-toast-message';
import { toastConfig } from '../components/CustomToast';
import { initAmplitude } from '../lib/analytics';
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

const sentryDsn = Constants.expoConfig?.extra?.sentryDsn as string | undefined;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: __DEV__ ? 'development' : 'production',
    tracesSampleRate: 0.2,
    attachScreenshot: false,
  });
}

const amplitudeApiKey = Constants.expoConfig?.extra?.amplitudeApiKey as string | undefined;
if (amplitudeApiKey) {
  initAmplitude(amplitudeApiKey).catch(() => {
    // тихо — аналитика не должна ломать загрузку приложения
  });
}

SplashScreen.preventAutoHideAsync();

function RootLayout() {
  const { checkAuth, isLoading, isAuthenticated } = useAuthStore();
  const { checkOnboarding, isReady: onboardingReady } = useOnboardingStore();
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
    checkOnboarding();
  }, []);

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
        inAppToast.show({
          id: event.request.identifier,
          title: content.title || 'Уведомление',
          body: content.body || '',
          data,
        });
      }
    });

    // Tap: пользователь нажал на push
    responseListener.current = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response.notification.request.content.data as Record<string, unknown>;
      const type = data?.type as string | undefined;
      const recordId = (data?.record_id || data?.recordId) as string | undefined;
      const username = data?.username as string | undefined;
      const entityId = data?.entity_id as string | undefined;
      const code = data?.code as string | undefined;

      if (type === 'follow_request') {
        router.push('/social/follow-requests');
        return;
      }
      if (type === 'message' || type === 'message_request') {
        const convId = (data?.conversation_id as string | undefined) || entityId;
        router.push((convId ? `/messages/${convId}` : '/messages') as any);
        return;
      }
      if (type === 'digest_wishlist_in_stock') {
        router.push('/notifications');
        return;
      }
      if (type === 'achievement_unlocked' || type === 'milestone_unlocked') {
        router.push(code ? (`/achievements?code=${code}` as any) : '/achievements');
        return;
      }
      if ((type === 'gift_booked' || type === 'gift_confirmed') && entityId) {
        router.push(`/gift/${entityId}` as any);
        return;
      }
      if ((type === 'wishlist_in_stock' || type === 'wishlist_price_drop') && recordId) {
        router.push(`/record/${recordId}` as any);
        return;
      }
      if (type === 'new_follower' && username) {
        router.push(`/user/${username}` as any);
        return;
      }
      if (recordId) {
        router.push(`/record/${recordId}` as any);
        return;
      }
      if (username) {
        router.push(`/user/${username}` as any);
        return;
      }
      router.push('/notifications');
    });

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

    useNotificationsStore.getState().fetchUnreadCount();

    // Глобальный polling: пока приложение активно, раз в 30с подтягиваем unreadCount,
    // чтобы красная точка на аватаре появлялась даже без push (например, события без
    // push'а или quiet hours). При уходе в background — таймер останавливается.
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = setInterval(() => {
        useNotificationsStore.getState().fetchUnreadCount();
      }, 30_000);
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
      stopPolling();
      sub.remove();
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
        refresh();
        if (!timer) timer = setInterval(refresh, 60_000);
      } else if (next.match(/inactive|background/)) {
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

  if (!fontsLoaded || isLoading || !onboardingReady) {
    return null;
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <BottomSheetModalProvider>
        <SafeAreaProvider>
          <StatusBar style="dark" />
          <OfflineBanner />
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: Colors.background },
            animation: 'slide_from_right',
            gestureEnabled: true,
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
        <OnboardingOverlay />
        <AchievementUnlockHost />
        {!introDone && <MascotIntro onFinish={() => setIntroDone(true)} />}
        <InAppNotificationToastHost />
        <Toast config={toastConfig} topOffset={56} bottomOffset={100} />
        </SafeAreaProvider>
      </BottomSheetModalProvider>
    </GestureHandlerRootView>
  );
}

export default Sentry.wrap(RootLayout);
