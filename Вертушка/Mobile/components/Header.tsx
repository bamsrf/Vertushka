/**
 * Хедер приложения — Editorial Gradient Edition
 * Huge left-aligned GradientText, аватар справа
 */
import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import { useRouter } from 'expo-router';
import { GradientText } from './GradientText';
import { Colors, Typography, Spacing } from '../constants/theme';
import { useAuthStore } from '../lib/store';
import { useNotificationsStore } from '../lib/notificationsStore';
import { useMessagesStore } from '../lib/messagesStore';
import { resolveMediaUrl } from '../lib/api';

interface HeaderProps {
  title?: string;
  showProfile?: boolean;
  showBack?: boolean;
  rightAction?: React.ReactNode;
}

export function Header({
  title = 'Вертушка',
  showProfile = true,
  showBack = false,
  rightAction,
}: HeaderProps) {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuthStore();
  const notifUnread = useNotificationsStore((s) => s.unreadCount);
  const msgUnread = useMessagesStore((s) => s.unread.primary + s.unread.requests);
  // Агрегат на аватарке профиля: непрочитанные уведомления + неотвеченные
  // личные сообщения. Юзер видит одну цифру → знает, что зайти в профиль.
  // Сами сообщения в ленту «Ты» не прокидываются — только в этот счётчик.
  const unreadCount = notifUnread + msgUnread;
  const badgeScale = useRef(new Animated.Value(1)).current;
  const prevUnreadRef = useRef(unreadCount);

  useEffect(() => {
    if (unreadCount > prevUnreadRef.current) {
      Animated.sequence([
        Animated.spring(badgeScale, { toValue: 1.25, useNativeDriver: true, friction: 5, tension: 100 }),
        Animated.spring(badgeScale, { toValue: 1, useNativeDriver: true, friction: 5, tension: 100 }),
      ]).start();
      Haptics.selectionAsync().catch(() => {});
    }
    prevUnreadRef.current = unreadCount;
  }, [unreadCount, badgeScale]);

  const handleProfilePress = () => {
    router.push('/profile');
  };

  const handleBackPress = () => {
    router.back();
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + 8 }]}>
      {/* Верхняя строка: back / пустота + аватар / rightAction */}
      <View style={styles.topRow}>
        <View style={styles.leftSection}>
          {showBack && (
            <TouchableOpacity style={styles.backButton} onPress={handleBackPress}>
              <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
            </TouchableOpacity>
          )}
          {showBack && title ? (
            <GradientText style={styles.inlineTitle}>{title}</GradientText>
          ) : null}
        </View>

        <View style={styles.rightSection}>
          {rightAction || (
            showProfile && (
              <TouchableOpacity style={styles.profileButton} onPress={handleProfilePress}>
                {user?.avatar_url ? (
                  <Image source={resolveMediaUrl(user.avatar_url)} style={styles.avatar} cachePolicy="disk" />
                ) : (
                  <LinearGradient
                    colors={[Colors.royalBlue, Colors.periwinkle]}
                    style={styles.avatarPlaceholder}
                  >
                    <Icon name="disc" size={20} color={Colors.background} />
                  </LinearGradient>
                )}
                {unreadCount > 0 ? (
                  <Animated.View style={[styles.badge, { transform: [{ scale: badgeScale }] }]}>
                    <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
                  </Animated.View>
                ) : null}
              </TouchableOpacity>
            )
          )}
        </View>
      </View>

      {/* Заголовок: huge, left-aligned, GradientText — только когда нет back */}
      {!showBack && title ? (
        <View style={styles.titleRow}>
          <GradientText style={Typography.display}>{title}</GradientText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 40,
  },
  leftSection: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 8,
  },
  rightSection: {
    alignItems: 'flex-end',
  },
  titleRow: {
    marginTop: 4,
  },
  profileButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 2,
    borderColor: Colors.lavender,
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 20,
    height: 20,
    borderRadius: 10,
    paddingHorizontal: 5,
    backgroundColor: Colors.error,
    borderWidth: 2,
    borderColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    color: Colors.background,
    fontSize: 11,
    lineHeight: 13,
    fontFamily: 'Inter_700Bold',
    textAlign: 'center',
  },
  avatar: {
    width: '100%',
    height: '100%',
    borderRadius: 18,
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 18,
  },
  backButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inlineTitle: {
    ...Typography.h2,
    flexShrink: 1,
  },
});

export default Header;
