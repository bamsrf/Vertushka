/**
 * Карточка уведомления в ленте «Ты».
 *
 * Поддерживает:
 * - превью обложки релиза справа (если в data.cover_url / data.record)
 * - inline accept/reject для follow_request
 * - tap → переход (отмечает прочитанным)
 */
import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Image } from 'expo-image';
import { Colors, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { RadarIcon } from '@/components/RadarIcon';

const RADAR_TINT: Record<string, string> = {
  match: Colors.success,
  available: Colors.royalBlue,
  alt: '#F4A06A',
  price_drop: Colors.success,
  absent: Colors.textMuted,
};
import { resolveMediaUrl, getCoverUrl } from '@/lib/api';
import { DESIGN_PNGS } from '@/assets/achievements/designs';
import type { NotificationItem as NotificationItemType, NotificationType } from '@/lib/types';
import { FollowRequestActions } from './FollowRequestActions';
import { NotificationSwipe } from './NotificationSwipe';

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
    case 'message_request':
      return { name: 'chatbubble', tint: Colors.royalBlue };
    case 'new_follower':
      return { name: 'person-add', tint: Colors.success };
    case 'gift_booked':
    case 'gift_confirmed':
      return { name: 'gift', tint: Colors.royalBlue };
    case 'wishlist_in_stock':
    case 'digest_wishlist_in_stock':
      return { name: 'disc', tint: Colors.success };
    case 'wishlist_in_stock_alt':
    case 'digest_wishlist_in_stock_alt':
      return { name: 'disc', tint: Colors.royalBlue };
    case 'wishlist_price_drop':
      return { name: 'pricetag', tint: Colors.success };
    case 'achievement_unlocked':
    case 'milestone_unlocked':
      return { name: 'trophy', tint: Colors.warning };
    case 'level_up':
      return { name: 'trending-up', tint: Colors.warning };
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
    type === 'level_up' ||
    type === 'digest_wishlist_in_stock' ||
    type === 'digest_wishlist_in_stock_alt'
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

function pluralVersions(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'других версий';
  if (mod10 === 1) return 'другая версия';
  if (mod10 >= 2 && mod10 <= 4) return 'другие версии';
  return 'других версий';
}

function formatPrice(p: unknown): string {
  if (typeof p !== 'number') return '';
  return `${Math.round(p)}₽`;
}

// «Почти дошло до порога» — бэкенд кладёт зазор в data тихой нити. Без этого
// строка «подешевела · 5 200 ₽» ничем не отличалась от цены вдвое выше порога.
function nearThresholdTail(data: Record<string, unknown>): string {
  if (!data.near_threshold || typeof data.to_threshold_rub !== 'number') return '';
  return ` · до порога ${formatPrice(data.to_threshold_rub)}`;
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
    case 'message_request': {
      const preview = (data.preview as string | undefined)?.trim();
      return preview
        ? `${actorName} пишет тебе: ${preview}`
        : `${actorName} хочет тебе написать`;
    }
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
      return `«${title}» снова в продаже${priceTail ? ` · ${priceTail}` : ''}${nearThresholdTail(data)}`;
    }
    case 'wishlist_in_stock_alt': {
      const title = (data.record_title as string | undefined) ?? 'пластинка';
      return `Другая версия «${title}» появилась в продаже`;
    }
    case 'wishlist_price_drop': {
      const title = (data.record_title as string | undefined) ?? 'пластинка';
      const priceTail = formatPrice(data.min_price_rub ?? data.price_rub);
      return `«${title}» подешевела${priceTail ? ` · ${priceTail}` : ''}${nearThresholdTail(data)}`;
    }
    case 'digest_wishlist_in_stock': {
      const count = (data.count as number | undefined) ?? 0;
      return `${count} ${pluralRecords(count)} из вишлиста снова в продаже`;
    }
    case 'digest_wishlist_in_stock_alt': {
      const count = (data.count as number | undefined) ?? 0;
      const verb = count % 10 === 1 && count % 100 !== 11 ? 'появилась' : 'появились';
      return `${count} ${pluralVersions(count)} ${verb} в продаже`;
    }
    case 'achievement_unlocked': {
      const title = (data.title as string | undefined) || (data.code as string | undefined) || '';
      return `Новая ачивка: ${title}`;
    }
    case 'milestone_unlocked': {
      const title = (data.title as string | undefined) ?? 'Новая веха';
      return title;
    }
    case 'level_up': {
      const label = (data.level_label as string | undefined) || '';
      return label ? `Новый уровень: ${label}` : 'Новый уровень';
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
  onDelete,
}) => {
  const unread = !item.read_at;
  const text = useMemo(() => buildText(item), [item]);
  const onRadar = !!(item.data as any)?.on_radar;
  const radarStatus = (item.data as any)?.radar_status as string | undefined;
  const baseMeta = useMemo(() => iconForType(item.type), [item.type]);
  const meta = onRadar
    ? { name: baseMeta.name, tint: RADAR_TINT[radarStatus ?? 'available'] ?? Colors.royalBlue }
    : baseMeta;
  const avatarUrl = item.actor?.avatar_url ? resolveMediaUrl(item.actor.avatar_url) : undefined;
  const initials = useMemo(() => actorInitials(item), [item]);
  const coverUrl = useMemo(() => getCoverFromData(item.data || {}), [item.data]);
  const showInlineActions = item.type === 'follow_request' && onAcceptFollow && onRejectFollow;
  const isMilestone = item.type === 'milestone_unlocked';
  const pinSource = useMemo(() => getAchievementPin(item), [item]);

  const row = (
    <TouchableOpacity
      activeOpacity={0.7}
      style={[styles.row, unread && styles.rowUnread, isMilestone && styles.rowMilestone]}
      onPress={() => onPress(item)}
      onLongPress={onLongPress ? () => onLongPress(item) : undefined}
      delayLongPress={350}
    >
      <View style={styles.avatarWrap}>
        {unread ? <View style={styles.unreadDot} /> : null}
        {pinSource ? (
          <Image source={pinSource} style={styles.pin} contentFit="contain" cachePolicy="memory-disk" />
        ) : avatarUrl ? (
          <>
            <Image source={avatarUrl} style={styles.avatar} cachePolicy="disk" />
            <View style={[styles.iconBadge, { backgroundColor: meta.tint }]}>
              {onRadar ? (
                <RadarIcon size={11} color={Colors.background} variant="on" />
              ) : (
                <Icon name={meta.name as any} size={10} color={Colors.background} />
              )}
            </View>
          </>
        ) : initials ? (
          <>
            <View style={[styles.avatar, styles.initialsAvatar]}>
              <Text style={styles.initialsText}>{initials}</Text>
            </View>
            <View style={[styles.iconBadge, { backgroundColor: meta.tint }]}>
              {onRadar ? (
                <RadarIcon size={11} color={Colors.background} variant="on" />
              ) : (
                <Icon name={meta.name as any} size={10} color={Colors.background} />
              )}
            </View>
          </>
        ) : (
          <View style={[styles.systemIcon, { backgroundColor: meta.tint }]}>
            {onRadar ? (
              <RadarIcon size={24} color={Colors.background} variant="on" />
            ) : (
              <Icon name={meta.name as any} size={22} color={Colors.background} />
            )}
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
  );

  if (!onDelete) return row;

  return <NotificationSwipe onDelete={() => onDelete(item)}>{row}</NotificationSwipe>;
};

/** Инициалы актора для fallback-аватара (когда есть actor, но нет фото). */
function actorInitials(item: NotificationItemType): string | undefined {
  if (!item.actor) return undefined;
  const src = (item.actor.display_name || item.actor.username || '').trim();
  if (!src) return undefined;
  const parts = src.split(/\s+/).filter(Boolean);
  const chars = parts.length >= 2 ? parts[0][0] + parts[1][0] : src.slice(0, 2);
  return chars.toUpperCase();
}

/** Мини-имидж пина для ачивок (по icon_slug из data). Иначе undefined → fallback на иконку. */
function getAchievementPin(item: NotificationItemType): number | undefined {
  if (item.type !== 'achievement_unlocked' && item.type !== 'milestone_unlocked') return undefined;
  const slug = (item.data?.icon_slug as string | undefined) || undefined;
  if (!slug) return undefined;
  return (DESIGN_PNGS as Record<string, number>)[slug];
}

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
  unreadDot: {
    position: 'absolute',
    left: -14,
    top: 18,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.royalBlue,
    zIndex: 1,
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
  initialsAvatar: {
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  initialsText: {
    ...Typography.bodySmall,
    color: Colors.background,
    fontWeight: '700',
  },
  pin: {
    width: 44,
    height: 44,
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
});

export default NotificationItem;
