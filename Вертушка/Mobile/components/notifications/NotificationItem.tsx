/**
 * Карточка уведомления в ленте «Ты».
 *
 * Поддерживает:
 * - превью обложки релиза справа (если в data.cover_url / data.record)
 * - inline accept/reject для follow_request
 * - tap → переход (отмечает прочитанным)
 */
import React, { useMemo, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Swipeable } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import { Colors, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { resolveMediaUrl, getCoverUrl } from '@/lib/api';
import type { NotificationItem as NotificationItemType, NotificationType } from '@/lib/types';
import { FollowRequestActions } from './FollowRequestActions';

interface Props {
  item: NotificationItemType;
  onPress: (item: NotificationItemType) => void;
  onAcceptFollow?: (item: NotificationItemType) => Promise<void> | void;
  onRejectFollow?: (item: NotificationItemType) => Promise<void> | void;
  onLongPress?: (item: NotificationItemType) => void;
  onMarkRead?: (item: NotificationItemType) => void;
  onDelete?: (item: NotificationItemType) => void;
}

function formatRelativeTime(iso: string): string {
  const created = new Date(iso).getTime();
  const diffSec = Math.max(0, (Date.now() - created) / 1000);
  if (diffSec < 60) return 'только что';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} мин`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} ч`;
  const days = Math.floor(diffSec / 86400);
  if (days < 7) return `${days} д`;
  if (days < 30) return `${Math.floor(days / 7)} нед`;
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function iconForType(type: NotificationType): { name: string; tint: string } {
  switch (type) {
    case 'follow_request':
      return { name: 'person-add', tint: Colors.royalBlue };
    case 'new_follower':
      return { name: 'person-add', tint: Colors.success };
    case 'gift_booked':
    case 'gift_confirmed':
      return { name: 'gift', tint: Colors.royalBlue };
    case 'wishlist_in_stock':
    case 'digest_wishlist_in_stock':
      return { name: 'disc', tint: Colors.success };
    case 'wishlist_in_stock_alt':
      return { name: 'disc', tint: Colors.royalBlue };
    case 'wishlist_price_drop':
      return { name: 'pricetag', tint: Colors.success };
    case 'achievement_unlocked':
    case 'milestone_unlocked':
      return { name: 'trophy', tint: Colors.warning };
    default:
      return { name: 'notifications', tint: Colors.royalBlue };
  }
}

/** Системные уведомления без actor (триггерятся бэкендом, а не другим юзером). */
function isSystemType(type: NotificationType): boolean {
  return (
    type === 'wishlist_in_stock' ||
    type === 'wishlist_in_stock_alt' ||
    type === 'wishlist_price_drop' ||
    type === 'milestone_unlocked' ||
    type === 'digest_wishlist_in_stock'
  );
}

function pluralStores(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'магазинах';
  if (mod10 === 1) return 'магазине';
  if (mod10 >= 2 && mod10 <= 4) return 'магазинах';
  return 'магазинах';
}

function pluralRecords(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'пластинок';
  if (mod10 === 1) return 'пластинка';
  if (mod10 >= 2 && mod10 <= 4) return 'пластинки';
  return 'пластинок';
}

function formatPrice(p: unknown): string {
  if (typeof p !== 'number') return '';
  return `${Math.round(p)}₽`;
}

function buildText(item: NotificationItemType): string {
  const actorName =
    (item.actor?.display_name as string | undefined) ||
    (item.actor?.username as string | undefined) ||
    'Кто-то';
  const data = item.data || {};

  switch (item.type) {
    case 'follow_request':
      return `${actorName} хочет на тебя подписаться`;
    case 'new_follower':
      return data.approved
        ? `${actorName} принял(а) твою подписку`
        : `${actorName} подписался(ась) на тебя`;
    case 'gift_booked': {
      const title = (data.record_title as string | undefined) ?? 'пластинку';
      return data.anonymous
        ? `Кто-то забронировал «${title}» из твоего вишлиста`
        : `${actorName} забронировал(а) «${title}»`;
    }
    case 'gift_confirmed': {
      const title = (data.record_title as string | undefined) ?? 'пластинку';
      return `${actorName} получил(а) твой подарок «${title}»`;
    }
    case 'wishlist_in_stock': {
      const title = (data.record_title as string | undefined) ?? 'пластинка';
      const storeCount = (data.store_count as number | undefined) ?? 1;
      const minPrice = data.min_price_rub ?? data.price_rub;
      const priceTail = formatPrice(minPrice);
      // Bumped multi-store: «"Mordechai" в 3 магазинах · от 4 490 ₽»
      if ((item.occurrences ?? 1) > 1 && storeCount > 1) {
        return `«${title}» в ${storeCount} ${pluralStores(storeCount)}${priceTail ? ` · от ${priceTail}` : ''}`;
      }
      return `«${title}» снова в продаже${priceTail ? ` · ${priceTail}` : ''}`;
    }
    case 'wishlist_in_stock_alt': {
      const title = (data.record_title as string | undefined) ?? 'пластинка';
      return `Другая версия «${title}» появилась в продаже`;
    }
    case 'wishlist_price_drop': {
      const title = (data.record_title as string | undefined) ?? 'пластинка';
      const priceTail = formatPrice(data.min_price_rub ?? data.price_rub);
      return `«${title}» подешевела${priceTail ? ` · ${priceTail}` : ''}`;
    }
    case 'digest_wishlist_in_stock': {
      const count = (data.count as number | undefined) ?? 0;
      return `${count} ${pluralRecords(count)} из вишлиста снова в продаже`;
    }
    case 'achievement_unlocked': {
      const title = (data.title as string | undefined) || (data.code as string | undefined) || '';
      return `Новая ачивка: ${title}`;
    }
    case 'milestone_unlocked': {
      const title = (data.title as string | undefined) ?? 'Новая веха';
      return title;
    }
    default:
      return 'Новое уведомление';
  }
}

function getCoverFromData(data: Record<string, unknown>): string | undefined {
  return getCoverUrl({
    cover_url: data.cover_url as string | undefined,
    cover_image_url: data.cover_image_url as string | undefined,
    thumb_image_url: data.thumb_image_url as string | undefined,
  });
}

export const NotificationItem: React.FC<Props> = ({
  item,
  onPress,
  onAcceptFollow,
  onRejectFollow,
  onLongPress,
  onMarkRead,
  onDelete,
}) => {
  const unread = !item.read_at;
  const text = useMemo(() => buildText(item), [item]);
  const meta = useMemo(() => iconForType(item.type), [item.type]);
  const avatarUrl = item.actor?.avatar_url ? resolveMediaUrl(item.actor.avatar_url) : undefined;
  const coverUrl = useMemo(() => getCoverFromData(item.data || {}), [item.data]);
  const showInlineActions = item.type === 'follow_request' && onAcceptFollow && onRejectFollow;
  const isMilestone = item.type === 'milestone_unlocked';
  const swipeRef = useRef<Swipeable>(null);
  // Флаг «только что свайпнули» — гасит ложный onPress, который иначе открывал
  // /record даже при свайпе-удалении.
  const swipedRef = useRef(false);

  const renderRightActions = (
    _: Animated.AnimatedInterpolation<number>,
    drag: Animated.AnimatedInterpolation<number>,
  ) => {
    if (!onDelete) return null;
    const scale = drag.interpolate({
      inputRange: [-100, 0],
      outputRange: [1, 0.6],
      extrapolate: 'clamp',
    });
    return (
      <View style={styles.actionContainer}>
        <Animated.View style={[styles.actionCard, styles.deleteAction, { transform: [{ scale }] }]}>
          <Icon name="trash" size={22} color={Colors.background} />
          <Text style={styles.actionText}>Удалить</Text>
        </Animated.View>
      </View>
    );
  };

  const renderLeftActions = (
    _: Animated.AnimatedInterpolation<number>,
    drag: Animated.AnimatedInterpolation<number>,
  ) => {
    if (!onMarkRead || !unread) return null;
    const scale = drag.interpolate({
      inputRange: [0, 100],
      outputRange: [0.6, 1],
      extrapolate: 'clamp',
    });
    return (
      <View style={styles.actionContainer}>
        <Animated.View style={[styles.actionCard, styles.readAction, { transform: [{ scale }] }]}>
          <Icon name="checkmark" size={22} color={Colors.background} />
          <Text style={styles.actionText}>Прочитано</Text>
        </Animated.View>
      </View>
    );
  };

  const handleSwipeOpen = (direction: 'left' | 'right') => {
    swipedRef.current = true;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    if (direction === 'left' && onMarkRead) {
      onMarkRead(item);
    } else if (direction === 'right' && onDelete) {
      onDelete(item);
    }
    swipeRef.current?.close();
  };

  const handlePress = () => {
    // Гасим тап, прилетевший на отпускании свайпа (иначе откроется /record при удалении).
    if (swipedRef.current) {
      swipedRef.current = false;
      return;
    }
    onPress(item);
  };

  return (
    <Swipeable
      ref={swipeRef}
      renderLeftActions={renderLeftActions}
      renderRightActions={renderRightActions}
      onSwipeableWillOpen={() => {
        swipedRef.current = true;
      }}
      onSwipeableOpen={handleSwipeOpen}
      onSwipeableClose={() => {
        // Сброс с задержкой — чтобы onPress, прилетевший сразу после, успел погаситься.
        setTimeout(() => {
          swipedRef.current = false;
        }, 50);
      }}
      friction={2}
      leftThreshold={60}
      rightThreshold={60}
      overshootLeft={false}
      overshootRight={false}
    >
    <TouchableOpacity
      activeOpacity={0.7}
      style={[styles.row, unread && styles.rowUnread, isMilestone && styles.rowMilestone]}
      onPress={handlePress}
      onLongPress={onLongPress ? () => onLongPress(item) : undefined}
      delayLongPress={350}
    >
      <View style={styles.unreadCol}>
        {unread ? <View style={styles.unreadDot} /> : null}
      </View>

      <View style={styles.avatarWrap}>
        {avatarUrl ? (
          <>
            <Image source={avatarUrl} style={styles.avatar} cachePolicy="disk" />
            <View style={[styles.iconBadge, { backgroundColor: meta.tint }]}>
              <Icon name={meta.name as any} size={10} color={Colors.background} />
            </View>
          </>
        ) : (
          <View style={[styles.systemIcon, { backgroundColor: meta.tint }]}>
            <Icon name={meta.name as any} size={22} color={Colors.background} />
          </View>
        )}
      </View>

      <View style={styles.body}>
        <Text style={styles.text} numberOfLines={2}>
          {text}
        </Text>
        <Text style={styles.time}>
          {formatRelativeTime(item.bumped_at || item.created_at)}
          {(item.occurrences ?? 1) > 1 ? ` · обновлено ${item.occurrences}×` : ''}
        </Text>
        {showInlineActions ? (
          <FollowRequestActions
            onAccept={() => onAcceptFollow!(item)}
            onReject={() => onRejectFollow!(item)}
          />
        ) : null}
      </View>

      {coverUrl ? (
        <Image source={coverUrl} style={styles.cover} cachePolicy="disk" contentFit="cover" />
      ) : null}
    </TouchableOpacity>
    </Swipeable>
  );
};

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  rowUnread: {
    backgroundColor: 'rgba(59, 75, 245, 0.04)',
  },
  rowMilestone: {
    backgroundColor: 'rgba(248, 228, 238, 0.5)',
  },
  unreadCol: {
    width: 10,
    alignItems: 'center',
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.royalBlue,
  },
  avatarWrap: {
    width: 44,
    height: 44,
    position: 'relative',
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
  },
  avatarPlaceholder: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  systemIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconBadge: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: Colors.background,
  },
  body: {
    flex: 1,
    gap: 2,
  },
  text: {
    ...Typography.bodySmall,
    color: Colors.text,
  },
  time: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  cover: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.sm,
  },
  actionContainer: {
    width: 96,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.sm,
  },
  actionCard: {
    flex: 1,
    alignSelf: 'stretch',
    marginVertical: 6,
    borderRadius: BorderRadius.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  deleteAction: {
    backgroundColor: Colors.error,
  },
  readAction: {
    backgroundColor: Colors.royalBlue,
  },
  actionText: {
    ...Typography.caption,
    color: Colors.background,
    marginTop: 4,
    fontFamily: 'Inter_600SemiBold',
  },
});

export default NotificationItem;
