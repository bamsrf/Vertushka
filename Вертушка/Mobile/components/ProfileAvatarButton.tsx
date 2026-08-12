/**
 * Кнопка «профиль» с бейджем непрочитанного.
 *
 * Единственное место, где рисуется аватар-с-цифрой: и в Header (экраны с back),
 * и в кастомных хедерах табов (Поиск, Коллекция). Раньше бейдж жил только в
 * Header, поэтому счётчик пропадал при переходе на таб.
 */
import React, { useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, StyleProp, ViewStyle } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { Colors } from '../constants/theme';
import { useAuthStore } from '../lib/store';
import { useNotificationsStore } from '../lib/notificationsStore';
import { useMessagesStore } from '../lib/messagesStore';
import { resolveMediaUrl } from '../lib/api';

interface ProfileAvatarButtonProps {
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
}

export function ProfileAvatarButton({ style, onPress }: ProfileAvatarButtonProps) {
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

  const handlePress = () => {
    if (onPress) {
      onPress();
      return;
    }
    router.push('/profile');
  };

  return (
    <TouchableOpacity style={[styles.button, style]} onPress={handlePress} hitSlop={12}>
      {/* Внутренний круг обрезает картинку; бейдж живёт снаружи него,
          иначе overflow:'hidden' срезал бы его угол. */}
      <View style={styles.clip}>
        {user?.avatar_url ? (
          <Image source={resolveMediaUrl(user.avatar_url)} style={styles.avatar} cachePolicy="disk" />
        ) : (
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle] as [string, string]}
            style={styles.avatarPlaceholder}
          >
            <Icon name="disc" size={20} color={Colors.background} />
          </LinearGradient>
        )}
      </View>
      {unreadCount > 0 ? (
        <Animated.View style={[styles.badge, { transform: [{ scale: badgeScale }] }]}>
          <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : unreadCount}</Text>
        </Animated.View>
      ) : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 2,
    borderColor: Colors.lavender,
    position: 'relative',
  },
  clip: {
    width: '100%',
    height: '100%',
    borderRadius: 18,
    overflow: 'hidden',
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarPlaceholder: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
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
});

export default ProfileAvatarButton;
