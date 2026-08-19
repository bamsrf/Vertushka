/**
 * Карточка события в социальной ленте «Подписки».
 *
 * Поддерживает агрегированные события (payload.aggregated=true) — показывает
 * текст «alex добавил 10 пластинок» + carousel из 3 первых обложек.
 */
import React, { useMemo } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, PixelRatio } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { resolveMediaUrl, getCoverUrl, sizedCoverUrl } from '@/lib/api';
import type { SocialFeedItem, SocialFeedRecord } from '@/lib/types';

interface Props {
  item: SocialFeedItem;
  onPress: (item: SocialFeedItem) => void;
}

function formatRelative(iso: string): string {
  const diffSec = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diffSec < 60) return 'только что';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} мин`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} ч`;
  return `${Math.floor(diffSec / 86400)} д`;
}

function pluralRecords(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'пластинок';
  if (mod10 === 1) return 'пластинку';
  if (mod10 >= 2 && mod10 <= 4) return 'пластинки';
  return 'пластинок';
}

function pluralAchievements(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'ачивок';
  if (mod10 === 1) return 'ачивку';
  if (mod10 >= 2 && mod10 <= 4) return 'ачивки';
  return 'ачивок';
}

function buildText(item: SocialFeedItem): string {
  const actor = item.actor.display_name || item.actor.username;
  const payload = item.payload as Record<string, unknown>;
  const aggregated = payload?.aggregated === true;
  const count = (payload?.count as number) ?? 1;

  if (aggregated) {
    switch (item.type) {
      case 'collection_add':
        return `${actor} добавил(а) ${count} ${pluralRecords(count)} в коллекцию`;
      case 'wishlist_add':
        return `${actor} добавил(а) ${count} ${pluralRecords(count)} в вишлист`;
      case 'friend_achievement':
        return `${actor} получил(а) ${count} ${pluralAchievements(count)}`;
      default:
        break;
    }
  }

  const recTitle = item.record?.title ?? '';
  switch (item.type) {
    case 'collection_add':
      return `${actor} добавил(а) «${recTitle}» в коллекцию`;
    case 'wishlist_add':
      return `${actor} добавил(а) «${recTitle}» в вишлист`;
    case 'gift_completed': {
      const target = item.target_user?.display_name || item.target_user?.username || 'друга';
      return `${actor} подарил(а) «${recTitle}» — ${target}`;
    }
    case 'friend_achievement':
      return `${actor} получил(а) новую ачивку`;
    case 'friend_new_following': {
      const target = item.target_user?.display_name || item.target_user?.username || 'кого-то';
      return `${actor} подписался(ась) на ${target}`;
    }
    default:
      return `${actor}`;
  }
}

function recordCover(r: SocialFeedRecord | null | undefined): string | undefined {
  if (!r) return undefined;
  // Слоты в ленте мелкие (44/56pt) — просим нарезку 320 вместо мастера.
  // Внешние (не наши /covers/*.jpg) URL sizedCoverUrl возвращает как есть.
  return sizedCoverUrl(
    getCoverUrl({ cover_url: r.cover_url ?? undefined }),
    Math.ceil(56 * PixelRatio.get())
  );
}

export const SocialFeedRow: React.FC<Props> = ({ item, onPress }) => {
  const text = useMemo(() => buildText(item), [item]);
  const avatarUrl = item.actor.avatar_url ? resolveMediaUrl(item.actor.avatar_url) : undefined;
  const payload = item.payload as Record<string, unknown>;
  const aggregated = payload?.aggregated === true;
  const aggRecords = (payload?.records as SocialFeedRecord[] | undefined) || [];
  const count = (payload?.count as number) ?? 1;
  const singleCover = recordCover(item.record);

  return (
    <TouchableOpacity activeOpacity={0.7} style={styles.row} onPress={() => onPress(item)}>
      <View style={styles.topRow}>
        <View style={styles.avatarWrap}>
          {avatarUrl ? (
            <Image source={avatarUrl} style={styles.avatar} cachePolicy="disk" />
          ) : (
            <LinearGradient colors={[Colors.royalBlue, Colors.periwinkle]} style={styles.avatar}>
              <Icon name="person" size={18} color={Colors.background} />
            </LinearGradient>
          )}
        </View>

        <View style={styles.body}>
          <Text style={styles.text} numberOfLines={2}>{text}</Text>
          <Text style={styles.time}>{formatRelative(item.created_at)}</Text>
        </View>

        {!aggregated && singleCover ? (
          <Image source={singleCover} style={styles.singleCover} cachePolicy="disk" />
        ) : null}
      </View>

      {aggregated && aggRecords.length > 0 ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.coverStrip}
          contentContainerStyle={styles.coverStripInner}
        >
          {aggRecords.slice(0, 3).map((r, idx) => {
            const cu = recordCover(r);
            return cu ? (
              <Image
                key={r.id ?? idx}
                source={cu}
                style={styles.smallCover}
                cachePolicy="disk"
                contentFit="cover"
              />
            ) : null;
          })}
          {count > 3 ? (
            <View style={styles.more}>
              <Text style={styles.moreText}>+{count - 3}</Text>
            </View>
          ) : null}
        </ScrollView>
      ) : null}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  row: {
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  avatarWrap: {
    width: 40,
    height: 40,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
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
  singleCover: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.sm,
  },
  coverStrip: {
    marginTop: Spacing.sm,
    marginLeft: 40 + Spacing.sm,
  },
  coverStripInner: {
    gap: Spacing.xs + 2,
  },
  smallCover: {
    width: 56,
    height: 56,
    borderRadius: BorderRadius.sm,
  },
  more: {
    width: 56,
    height: 56,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  moreText: {
    ...Typography.bodyBold,
    color: Colors.textSecondary,
  },
});

export default SocialFeedRow;
