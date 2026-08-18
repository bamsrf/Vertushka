/**
 * Превью-карточка «Активность» для экрана профиля.
 *
 * Показывает unread-pill и 2-3 последних personal-уведомления. Тап → /notifications.
 */
import React, { useEffect, useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Colors, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { BellV2, CaretRightV2 } from '@/components/icons/v2';
import { useNotificationsStore } from '@/lib/notificationsStore';

function formatRelative(iso: string): string {
  const diffSec = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return 'только что';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} мин`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} ч`;
  return `${Math.floor(diffSec / 86400)} д`;
}

export const ActivityCard: React.FC = () => {
  const router = useRouter();
  const { unreadCount, personalItems, personalLoaded, fetchUnreadCount, loadPersonal } =
    useNotificationsStore();

  useEffect(() => {
    fetchUnreadCount();
    if (!personalLoaded) loadPersonal();
  }, [fetchUnreadCount, loadPersonal, personalLoaded]);

  const preview = useMemo(() => personalItems.slice(0, 2), [personalItems]);

  const handleOpen = () => {
    router.push('/notifications');
  };

  return (
    <TouchableOpacity activeOpacity={0.85} style={styles.card} onPress={handleOpen}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <BellV2 size={18} color={Colors.royalBlue} weight="regular" />
          <Text style={styles.title}>Уведомления</Text>
          {unreadCount > 0 ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
            </View>
          ) : null}
        </View>
        <CaretRightV2 size={18} color={Colors.textMuted} weight="regular" />
      </View>

      {preview.length === 0 ? (
        <Text style={styles.empty}>
          Здесь появятся новые подписчики, бронирования подарков и алерты вишлиста.
        </Text>
      ) : (
        <View style={styles.previewList}>
          {preview.map((item) => {
            const previewLine = buildPreviewLine(item);
            return (
              <View key={item.id} style={styles.previewRow}>
                {!item.read_at ? <View style={styles.unreadDot} /> : <View style={styles.unreadDotPlaceholder} />}
                <Text style={styles.previewText} numberOfLines={1}>
                  {previewLine.actorPrefix ? (
                    <>
                      <Text style={styles.previewActor}>{previewLine.actorPrefix}</Text>
                      {' '}
                    </>
                  ) : null}
                  {previewLine.body}
                </Text>
                <Text style={styles.previewTime}>{formatRelative(item.created_at)}</Text>
              </View>
            );
          })}
        </View>
      )}
    </TouchableOpacity>
  );
};

function buildPreviewLine(item: {
  type: string;
  data: Record<string, unknown>;
  actor?: { display_name?: string | null; username?: string | null } | null;
}): { actorPrefix: string | null; body: string } {
  const actor =
    (item.actor?.display_name as string | undefined) ||
    (item.actor?.username as string | undefined) ||
    null;
  const data = item.data || {};
  const recordTitle = (data.record_title as string | undefined) ?? 'пластинка';

  switch (item.type) {
    case 'follow_request':
      return { actorPrefix: actor ?? 'Кто-то', body: 'хочет подписаться' };
    case 'message_request':
      return { actorPrefix: actor ?? 'Кто-то', body: 'хочет тебе написать' };
    case 'new_follower':
      return {
        actorPrefix: actor ?? 'Кто-то',
        body: data.approved ? 'принял(а) подписку' : 'подписался(ась) на тебя',
      };
    case 'gift_booked':
      return data.anonymous
        ? { actorPrefix: null, body: `Кто-то забронировал «${recordTitle}»` }
        : { actorPrefix: actor ?? 'Кто-то', body: `забронировал(а) «${recordTitle}»` };
    case 'gift_confirmed':
      return { actorPrefix: actor ?? 'Кто-то', body: `получил(а) «${recordTitle}»` };
    case 'wishlist_in_stock':
      return { actorPrefix: null, body: `«${recordTitle}» снова в продаже` };
    case 'wishlist_in_stock_alt':
      return { actorPrefix: null, body: `Другая версия «${recordTitle}» в продаже` };
    case 'wishlist_price_drop':
      return { actorPrefix: null, body: `«${recordTitle}» подешевела` };
    case 'digest_wishlist_in_stock': {
      const count = (data.count as number | undefined) ?? 0;
      return { actorPrefix: null, body: `${count} пластинок из вишлиста снова в продаже` };
    }
    case 'level_up': {
      const label = (data.level_label as string | undefined) || '';
      return { actorPrefix: null, body: label ? `Новый уровень: ${label}` : 'Новый уровень' };
    }
    case 'achievement_unlocked': {
      const title = (data.title as string | undefined) || (data.code as string | undefined) || '';
      return { actorPrefix: null, body: `Новая ачивка: ${title}` };
    }
    case 'milestone_unlocked': {
      const title = (data.title as string | undefined) ?? 'Новая веха';
      return { actorPrefix: null, body: title };
    }
    default:
      // Незнакомый тип не должен рисовать пустую строку с одним «1 д»: пока
      // сюда не добавили кейс, показываем хотя бы нейтральный текст.
      return { actorPrefix: actor, body: actor ? 'новое событие' : 'Новое уведомление' };
  }
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.lg,
    padding: Spacing.md,
    gap: Spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  title: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  badge: {
    minWidth: 20,
    height: 20,
    paddingHorizontal: 6,
    borderRadius: 10,
    backgroundColor: Colors.error,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },
  badgeText: {
    ...Typography.caption,
    color: Colors.background,
    fontFamily: 'Inter_700Bold',
    fontSize: 11,
    lineHeight: 14,
  },
  empty: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  previewList: {
    gap: 6,
  },
  previewRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  unreadDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: Colors.royalBlue,
  },
  unreadDotPlaceholder: {
    width: 6,
    height: 6,
  },
  previewText: {
    ...Typography.bodySmall,
    color: Colors.textSecondary,
    flex: 1,
  },
  previewActor: {
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
  },
  previewTime: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
});

export default ActivityCard;
