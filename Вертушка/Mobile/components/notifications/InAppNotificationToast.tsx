/**
 * In-app toast для push-уведомлений, прилетевших в foreground.
 *
 * - Slide-down 250ms сверху (под status-bar).
 * - Auto-dismiss через 3.5с.
 * - Swipe-up — скрыть, tap — открыть соответствующий контент.
 * - OS-баннер в foreground подавляется в _layout.tsx, мы показываем свой.
 */
import React, { useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  PanResponder,
  TouchableWithoutFeedback,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Image } from 'expo-image';
import { Colors, Spacing, Typography, BorderRadius } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { resolveMediaUrl } from '@/lib/api';
import { useNotificationsStore } from '@/lib/notificationsStore';
import { DESIGN_PNGS } from '@/assets/achievements/designs';
import { routeForPush } from '@/lib/pushRouting';

export interface ToastPayload {
  id: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
}

type Listener = (toast: ToastPayload) => void;

class ToastEmitter {
  private listeners = new Set<Listener>();

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => {
      this.listeners.delete(l);
    };
  }

  show(toast: ToastPayload): void {
    this.listeners.forEach((l) => l(toast));
  }
}

export const inAppToast = new ToastEmitter();

const AUTO_DISMISS_MS = 3500;
const ANIM_MS = 250;

export const InAppNotificationToastHost: React.FC = () => {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [current, setCurrent] = React.useState<ToastPayload | null>(null);
  const translateY = useRef(new Animated.Value(-200)).current;
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (dismissTimer.current) {
      clearTimeout(dismissTimer.current);
      dismissTimer.current = null;
    }
    Animated.timing(translateY, {
      toValue: -200,
      duration: ANIM_MS,
      useNativeDriver: true,
    }).start(() => setCurrent(null));
  }, [translateY]);

  const show = useCallback(
    (toast: ToastPayload) => {
      setCurrent(toast);
      Animated.timing(translateY, {
        toValue: 0,
        duration: ANIM_MS,
        useNativeDriver: true,
      }).start();
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
      dismissTimer.current = setTimeout(dismiss, AUTO_DISMISS_MS);
    },
    [translateY, dismiss],
  );

  useEffect(() => {
    const unsub = inAppToast.subscribe(show);
    return () => {
      unsub();
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
    };
  }, [show]);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dy) > 4 && g.dy < 0,
      onPanResponderMove: (_, g) => {
        if (g.dy < 0) translateY.setValue(g.dy);
      },
      onPanResponderRelease: (_, g) => {
        if (g.dy < -40) {
          dismiss();
        } else {
          Animated.timing(translateY, {
            toValue: 0,
            duration: 150,
            useNativeDriver: true,
          }).start();
        }
      },
    }),
  ).current;

  const handleTap = useCallback(() => {
    if (!current) return;
    useNotificationsStore.getState().fetchUnreadCount();
    dismiss();
    // Единая маршрутизация с OS-пушем — тап по тосту ведёт в тот же раздел.
    router.push(routeForPush(current.data || {}) as any);
  }, [current, dismiss, router]);

  if (!current) return null;

  const avatarUrl = current.data?.avatar_url
    ? resolveMediaUrl(current.data.avatar_url as string)
    : undefined;

  // Ачивка показывает свой пин, а не общий колокольчик: в тосте про ачивку
  // важен сам трофей. icon_slug кладёт бэкенд в data при создании нотификации.
  const type = current.data?.type as string | undefined;
  const slug = current.data?.icon_slug as string | undefined;
  const pin =
    (type === 'achievement_unlocked' || type === 'milestone_unlocked') && slug
      ? (DESIGN_PNGS as Record<string, number>)[slug]
      : undefined;

  return (
    <Animated.View
      pointerEvents="box-none"
      style={[
        styles.host,
        {
          paddingTop: insets.top + 8,
          transform: [{ translateY }],
        },
      ]}
      {...panResponder.panHandlers}
    >
      <TouchableWithoutFeedback onPress={handleTap}>
        <View style={styles.card}>
          <View style={[styles.iconWrap, pin ? styles.iconWrapPin : null]}>
            {pin ? (
              <Image source={pin} style={styles.pin} contentFit="contain" />
            ) : avatarUrl ? (
              <Image source={avatarUrl} style={styles.avatar} cachePolicy="disk" />
            ) : (
              <Icon name="notifications" size={22} color={Colors.background} />
            )}
          </View>
          <View style={styles.body}>
            <Text style={styles.title} numberOfLines={1}>
              {current.title}
            </Text>
            <Text style={styles.bodyText} numberOfLines={2}>
              {current.body}
            </Text>
          </View>
        </View>
      </TouchableWithoutFeedback>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  host: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingHorizontal: Spacing.md,
    zIndex: 9999,
    elevation: Platform.OS === 'android' ? 12 : 0,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.deepNavy,
    borderRadius: BorderRadius.lg,
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
  },
  // Пин рисуется на прозрачном фоне: синий кружок под ним съедал бы контур.
  iconWrapPin: {
    backgroundColor: 'transparent',
  },
  pin: {
    width: 40,
    height: 40,
  },
  body: {
    flex: 1,
    gap: 2,
  },
  title: {
    ...Typography.bodyBold,
    color: Colors.background,
    fontSize: 14,
  },
  bodyText: {
    ...Typography.caption,
    color: Colors.lavender,
  },
});

export default InAppNotificationToastHost;
