/**
 * Экран «Уведомления» — личные уведомления + лента подписок.
 *
 * Лента сгруппирована по дате (Сегодня/Вчера/На этой неделе/Ранее) через SectionList.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SectionList,
  RefreshControl,
  TouchableOpacity,
  ActivityIndicator,
  ActionSheetIOS,
  Alert,
  Platform,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { Colors, Spacing, Typography } from '@/constants/theme';
import { AnimatedGradientText } from '@/components/AnimatedGradientText';
import { SegmentedControl } from '@/components/ui';
import { XV2 } from '@/components/icons/v2';
import { NotificationItem } from '@/components/notifications/NotificationItem';
import { SocialFeedRow } from '@/components/notifications/SocialFeedRow';
import { NotificationsEmpty } from '@/components/notifications/NotificationsEmpty';
import { WishlistDigestSheet, type DigestRecord } from '@/components/notifications/WishlistDigestSheet';
import { useNotificationsStore } from '@/lib/notificationsStore';
import { prewarmAchievementPins } from '@/lib/achievementAssets';
import { groupByDateBucket } from '@/lib/notificationsGrouping';
import { api } from '@/lib/api';
import { toast } from '@/lib/toast';
import type { NotificationItem as NotificationItemType, SocialFeedItem } from '@/lib/types';

type Tab = 'personal' | 'social';

const MUTE_KEY_BY_TYPE: Record<string, string> = {
  follow_request: 'notify_follow_request',
  new_follower: 'notify_new_follower',
  gift_booked: 'notify_gift_booked',
  gift_confirmed: 'notify_gift_booked',
  wishlist_in_stock: 'notify_wishlist_in_stock',
  wishlist_price_drop: 'notify_wishlist_in_stock',
  achievement_unlocked: 'notify_achievement',
  level_up: 'notify_achievement',
  milestone_unlocked: 'notify_achievement',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>('personal');

  const {
    personalItems,
    personalLoading,
    personalRefreshing,
    personalNextCursor,
    socialItems,
    socialLoading,
    socialRefreshing,
    socialNextCursor,
    socialError,
    unreadCount,
    loadPersonal,
    loadMorePersonal,
    loadSocial,
    loadMoreSocial,
    markRead,
    markManyRead,
    mutatePersonal,
    removePersonal,
    snoozePersonal,
    pendingNew,
    clearPending,
    fetchUnreadCount,
  } = useNotificationsStore();
  const sectionListRef = useRef<SectionList<NotificationItemType> | null>(null);
  const socialSectionListRef = useRef<SectionList<SocialFeedItem> | null>(null);

  // «Seen = read» (Instagram-паттерн): копим id видимых непрочитанных, дебаунсим,
  // шлём батчем. Items ниже фолда в viewable не попадают → остаются непрочитанными.
  const pendingSeen = useRef<Set<string>>(new Set());
  const seenTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushSeen = useCallback(() => {
    const ids = Array.from(pendingSeen.current);
    pendingSeen.current.clear();
    if (ids.length > 0) markManyRead(ids);
  }, [markManyRead]);

  const viewabilityConfig = useRef({
    itemVisiblePercentThreshold: 60,
    minimumViewTime: 500,
  }).current;

  const onViewableItemsChanged = useRef(
    ({ viewableItems }: { viewableItems: Array<{ item: unknown }> }) => {
      let added = false;
      for (const v of viewableItems) {
        const it = v.item as NotificationItemType | undefined;
        if (it && typeof it.id === 'string' && it.id !== WL_DIGEST_ID && !it.read_at) {
          pendingSeen.current.add(it.id);
          added = true;
        }
      }
      if (!added) return;
      if (seenTimer.current) clearTimeout(seenTimer.current);
      seenTimer.current = setTimeout(flushSeen, 600);
    },
  ).current;

  useEffect(() => () => {
    if (seenTimer.current) clearTimeout(seenTimer.current);
    flushSeen();
  }, [flushSeen]);

  useEffect(() => {
    // Экран открыт → показываем свежий список сразу. Копившийся pendingNew
    // (пуши, пришедшие пока юзер был на других экранах) обнуляем — эти items
    // уже в загруженной ленте, отдельная плашка «Показать N новых» была бы
    // дублем. Плашка остаётся только для пушей, прилетевших ПРИ открытом экране.
    clearPending();
    loadPersonal();
  }, [loadPersonal, clearPending]);

  // Прогрев PNG-пинов ачивок: из уведомлений часто проваливаются в ачивку,
  // прогретый декод даёт мгновенную иконку и непустой шер.
  useEffect(() => {
    prewarmAchievementPins();
  }, []);

  useEffect(() => {
    if (tab === 'social' && socialItems.length === 0) {
      loadSocial();
    }
  }, [tab, socialItems.length, loadSocial]);

  // Пока экран открыт — каждые 30с подтягиваем unread, чтобы pendingNew рос
  // даже если push не пришёл (например, события без push-уведомления).
  useEffect(() => {
    const interval = setInterval(() => {
      fetchUnreadCount();
    }, 30_000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  const handleShowNew = useCallback(async () => {
    clearPending();
    if (tab === 'personal') {
      await loadPersonal({ refresh: true });
      sectionListRef.current?.scrollToLocation({
        sectionIndex: 0,
        itemIndex: 0,
        animated: true,
      });
    } else {
      await loadSocial({ refresh: true });
      socialSectionListRef.current?.scrollToLocation({
        sectionIndex: 0,
        itemIndex: 0,
        animated: true,
      });
    }
  }, [clearPending, tab, loadPersonal, loadSocial]);

  const handleClose = useCallback(() => router.back(), [router]);

  const handlePersonalPress = useCallback(
    async (item: NotificationItemType) => {
      Haptics.selectionAsync().catch(() => {});
      if (!item.read_at) {
        await markRead(item.id);
      }
      routeForPersonal(item, router);
    },
    [markRead, router],
  );

  const handleSocialPress = useCallback(
    (item: SocialFeedItem) => {
      Haptics.selectionAsync().catch(() => {});
      routeForSocial(item, router);
    },
    [router],
  );

  const handleAcceptFollow = useCallback(
    async (item: NotificationItemType) => {
      if (!item.entity_id) return;
      try {
        await api.approveFollowRequest(item.entity_id);
        mutatePersonal(item.id, {
          type: 'new_follower',
          data: { ...(item.data || {}), approved: true },
          read_at: new Date().toISOString(),
        });
      } catch {
        toast.error('Не удалось принять заявку');
      }
    },
    [mutatePersonal],
  );

  const handleRejectFollow = useCallback(
    async (item: NotificationItemType) => {
      if (!item.entity_id) return;
      try {
        await api.rejectFollowRequest(item.entity_id);
        await removePersonal(item.id);
      } catch {
        toast.error('Не удалось отклонить заявку');
      }
    },
    [removePersonal],
  );

  const muteType = useCallback(async (type: string) => {
    const settingKey = MUTE_KEY_BY_TYPE[type];
    if (!settingKey) return;
    try {
      await api.updateNotificationSettings({ [settingKey]: false } as Record<string, boolean>);
      toast.info('Отключено', 'Этот тип уведомлений больше не будет приходить');
    } catch {
      toast.error('Не удалось обновить настройки');
    }
  }, []);

  const handleLongPress = useCallback(
    (item: NotificationItemType) => {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
      const unread = !item.read_at;
      const muteOption = MUTE_KEY_BY_TYPE[item.type] ? 'Отключить тип уведомлений' : null;
      // Snooze — точечный «не напоминать про эту пластинку», без отключения типа
      // целиком. Применим только к wishlist-семейству, где dedup_key привязан к записи.
      const snoozable =
        item.type === 'wishlist_in_stock' ||
        item.type === 'wishlist_in_stock_alt' ||
        item.type === 'wishlist_price_drop';
      const recordTitle = (item.data?.record_title as string | undefined) ?? null;
      const snoozeLabel = snoozable
        ? recordTitle
          ? `Не напоминать про «${recordTitle}» 30 дней`
          : 'Не напоминать про эту пластинку 30 дней'
        : null;

      const actions: { label: string; destructive?: boolean; run: () => void }[] = [];
      if (unread) {
        actions.push({ label: 'Отметить прочитанным', run: () => markRead(item.id) });
      }
      if (snoozeLabel) {
        actions.push({ label: snoozeLabel, run: () => snoozePersonal(item.id, 30) });
      }
      actions.push({ label: 'Удалить', destructive: true, run: () => removePersonal(item.id) });
      if (muteOption) {
        actions.push({ label: muteOption, run: () => muteType(item.type) });
      }
      actions.push({ label: 'Отмена', run: () => {} });

      if (Platform.OS === 'ios') {
        const labels = actions.map((a) => a.label);
        ActionSheetIOS.showActionSheetWithOptions(
          {
            options: labels,
            cancelButtonIndex: labels.length - 1,
            destructiveButtonIndex: actions.findIndex((a) => a.destructive),
          },
          (idx) => actions[idx]?.run(),
        );
      } else {
        Alert.alert(
          'Уведомление',
          undefined,
          actions.map((a) => ({
            text: a.label,
            style: a.destructive ? 'destructive' : a.label === 'Отмена' ? 'cancel' : 'default',
            onPress: a.run,
          })),
        );
      }
    },
    [markRead, removePersonal, snoozePersonal, muteType],
  );

  const handleRefresh = useCallback(() => {
    if (tab === 'personal') loadPersonal({ refresh: true });
    else loadSocial({ refresh: true });
  }, [tab, loadPersonal, loadSocial]);

  const handleEndReached = useCallback(() => {
    if (tab === 'personal' && personalNextCursor) loadMorePersonal();
    else if (tab === 'social' && socialNextCursor) loadMoreSocial();
  }, [tab, personalNextCursor, socialNextCursor, loadMorePersonal, loadMoreSocial]);

  const [digestVisible, setDigestVisible] = useState(false);
  // Свёртка «липкая»: раз пластинка попала в дайджест, она остаётся в нём до
  // ухода с экрана — даже после markManyRead. Иначе открытие поп-апа гасит
  // unread → дайджест пересобирается пустым («0 пластинок») и лента взрывается
  // обратно на 14 отдельных строк.
  const digestSticky = useRef<Set<string>>(new Set());
  const { personalSections, digestRecords, digestCollapsedIds } = useMemo(() => {
    const { list, records, collapsedIds } = buildWishlistDigest(
      collapseByDedup(personalItems),
      digestSticky.current,
    );
    return {
      personalSections: groupByDateBucket(list),
      digestRecords: records,
      digestCollapsedIds: collapsedIds,
    };
  }, [personalItems]);

  const handleOpenDigest = useCallback(() => {
    Haptics.selectionAsync().catch(() => {});
    setDigestVisible(true);
    // Открыл дайджест = увидел все свёрнутые алерты → гасим их unread.
    if (digestCollapsedIds.length > 0) markManyRead(digestCollapsedIds);
  }, [digestCollapsedIds, markManyRead]);

  // Уход в релиз из дайджеста не должен «терять шаг»: закрываем шторку на
  // время навигации и поднимаем её обратно, когда юзер возвращается назад.
  const digestReopen = useRef(false);
  const handleOpenDigestRecord = useCallback(
    (recordId: string) => {
      digestReopen.current = true;
      router.push(`/record/${recordId}` as any);
    },
    [router],
  );

  useFocusEffect(
    useCallback(() => {
      if (digestReopen.current) {
        digestReopen.current = false;
        setDigestVisible(true);
      }
    }, []),
  );
  const socialSections = useMemo(() => groupByDateBucket(socialItems), [socialItems]);

  const renderPersonal = ({ item }: { item: NotificationItemType }) => {
    // Синтетическая дайджест-строка: тап открывает поп-ап с корешками, без
    // swipe-delete/long-press (удалять/снузить нечего — это виртуальная свёртка).
    if (item.id === WL_DIGEST_ID) {
      return <NotificationItem item={item} onPress={handleOpenDigest} />;
    }
    return (
      <NotificationItem
        item={item}
        onPress={handlePersonalPress}
        onAcceptFollow={handleAcceptFollow}
        onRejectFollow={handleRejectFollow}
        onMarkRead={(it) => markRead(it.id)}
        onDelete={(it) => removePersonal(it.id)}
        onLongPress={handleLongPress}
      />
    );
  };
  const renderSocial = ({ item }: { item: SocialFeedItem }) => (
    <SocialFeedRow item={item} onPress={handleSocialPress} />
  );

  const renderSectionHeader = ({ section }: { section: any }) => (
    <View style={styles.sectionHeader}>
      <Text style={styles.sectionHeaderText}>{section.title ?? ''}</Text>
    </View>
  );

  const showFooter =
    (tab === 'personal' && personalLoading && personalItems.length > 0) ||
    (tab === 'social' && socialLoading && socialItems.length > 0);

  const handleFindUsers = useCallback(() => {
    router.push('/(tabs)/search');
  }, [router]);

  return (
    // Своя GestureHandlerRootView: экран — нативный modal (presentation:'modal'),
    // куда корневой root-view из _layout не дотягивается → без неё Gesture.Pan
    // свайпа удаления не срабатывает на iOS.
    <GestureHandlerRootView style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View style={styles.headerTitleWrap}>
          <AnimatedGradientText style={styles.headerTitle}>Уведомления</AnimatedGradientText>
        </View>
        <TouchableOpacity onPress={handleClose} style={styles.closeBtn} hitSlop={12}>
          <XV2 size={24} color={Colors.text} />
        </TouchableOpacity>
      </View>

      <View style={styles.segmentWrap}>
        <SegmentedControl
          segments={[
            { key: 'personal', label: unreadCount > 0 ? `Ты (${unreadCount})` : 'Ты' },
            { key: 'social', label: 'Подписки' },
          ]}
          selectedKey={tab}
          onSelect={setTab}
        />
      </View>

      {pendingNew > 0 ? (
        <TouchableOpacity onPress={handleShowNew} style={styles.pill} activeOpacity={0.85}>
          <Text style={styles.pillText}>
            Показать {pendingNew} {pluralizeNew(pendingNew)}
          </Text>
        </TouchableOpacity>
      ) : null}

      {tab === 'personal' ? (
        <SectionList
          ref={sectionListRef}
          sections={personalSections}
          keyExtractor={(item) => item.id}
          renderItem={renderPersonal}
          renderSectionHeader={renderSectionHeader}
          stickySectionHeadersEnabled={false}
          viewabilityConfig={viewabilityConfig}
          onViewableItemsChanged={onViewableItemsChanged}
          contentContainerStyle={
            personalSections.length === 0 ? styles.emptyContainer : styles.listContainer
          }
          refreshControl={
            <RefreshControl
              refreshing={personalRefreshing}
              onRefresh={handleRefresh}
              tintColor={Colors.royalBlue}
            />
          }
          onEndReached={handleEndReached}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={
            !personalLoading ? (
              <NotificationsEmpty
                title="Пока тихо"
                subtitle="Подпишись на коллекционеров — будешь видеть новые подписки, бронирования подарков, ачивки и алерты вишлиста."
                ctaLabel="Найти коллекционеров"
                onCtaPress={handleFindUsers}
              />
            ) : (
              <View style={styles.spinner}><ActivityIndicator color={Colors.royalBlue} /></View>
            )
          }
          ListFooterComponent={
            showFooter ? <View style={styles.spinner}><ActivityIndicator color={Colors.royalBlue} /></View> : null
          }
        />
      ) : (
        <SectionList
          ref={socialSectionListRef}
          sections={socialSections}
          keyExtractor={(item, idx) => `${item.type}-${item.actor.id}-${item.created_at}-${idx}`}
          renderItem={renderSocial}
          renderSectionHeader={renderSectionHeader}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={
            socialSections.length === 0 ? styles.emptyContainer : styles.listContainer
          }
          refreshControl={
            <RefreshControl
              refreshing={socialRefreshing}
              onRefresh={handleRefresh}
              tintColor={Colors.royalBlue}
            />
          }
          onEndReached={handleEndReached}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={
            !socialLoading ? (
              socialError ? (
                <NotificationsEmpty
                  title="Не удалось загрузить"
                  subtitle="Проверь соединение и попробуй ещё раз."
                  ctaLabel="Обновить"
                  onCtaPress={() => loadSocial({ refresh: true })}
                />
              ) : (
                <NotificationsEmpty
                  title="Лента пуста"
                  subtitle="Подпишись на других коллекционеров, чтобы видеть их новые пластинки, подарки и ачивки."
                  ctaLabel="Найти коллекционеров"
                  onCtaPress={handleFindUsers}
                />
              )
            ) : (
              <View style={styles.spinner}><ActivityIndicator color={Colors.royalBlue} /></View>
            )
          }
          ListFooterComponent={
            showFooter ? <View style={styles.spinner}><ActivityIndicator color={Colors.royalBlue} /></View> : null
          }
        />
      )}

      <WishlistDigestSheet
        visible={digestVisible}
        onClose={() => setDigestVisible(false)}
        records={digestRecords}
        onOpenRecord={handleOpenDigestRecord}
      />
    </GestureHandlerRootView>
  );
}

// Синтетический id дайджест-строки + минимум пластинок для свёртки.
const WL_DIGEST_ID = '__wishlist_digest__';
const WL_DIGEST_MIN = 3;
// Окно свёртки: столько же дней, сколько бэкенд берёт в недельный дайджест
// (WEEKLY_DIGEST_LOOKBACK_DAYS в notification_tasks.py). Прочитанные алерты
// внутри окна остаются свёрнутыми — иначе после первого тапа лента при
// следующем заходе разворачивается обратно в 14 строк складского шума.
const WL_DIGEST_WINDOW_MS = 7 * 24 * 60 * 60 * 1000;

/** Собрать DigestRecord из wishlist_in_stock: самый дешёвый магазин как цель. */
function toDigestRecord(it: NotificationItemType): DigestRecord {
  const data = (it.data || {}) as Record<string, any>;
  const stores: any[] = Array.isArray(data.stores) ? data.stores : [];
  const priced = stores.filter((s) => s?.price_rub != null).sort((a, b) => a.price_rub - b.price_rub);
  const cheapest = priced[0] ?? stores[0] ?? null;
  return {
    record_id: String(data.record_id ?? it.entity_id ?? ''),
    title: String(data.record_title ?? 'Пластинка'),
    artist: (data.record_artist as string | undefined) ?? null,
    cover_url: (data.cover_url as string | undefined) ?? null,
    min_price_rub: (data.min_price_rub ?? data.price_rub ?? null) as number | null,
    store_count: (data.store_count as number | undefined) ?? (stores.length || 1),
    store: cheapest
      ? {
          listing_id: cheapest.listing_id ?? null,
          url: cheapest.url ?? null,
          name: cheapest.name ?? null,
          price_rub: cheapest.price_rub ?? null,
        }
      : null,
  };
}

/**
 * Свёртка непрочитанных `wishlist_in_stock` в одну дайджест-строку
 * «N пластинок снова в продаже» (если их ≥WL_DIGEST_MIN). Убирает 12 отдельных
 * строк складского шума. Возвращает новый список + записи для поп-апа + id
 * свёрнутых уведомлений (чтобы пометить прочитанными при открытии).
 *
 * `sticky` — id уже свёрнутых на этом экране пластинок: они остаются в дайджесте
 * после того, как их погасил markManyRead. Мутируется здесь же (union).
 */
function buildWishlistDigest(
  items: NotificationItemType[],
  sticky: Set<string>,
): {
  list: NotificationItemType[];
  records: DigestRecord[];
  collapsedIds: string[];
} {
  const windowStart = Date.now() - WL_DIGEST_WINDOW_MS;
  const isCollapsible = (i: NotificationItemType) => {
    if (i.type !== 'wishlist_in_stock') return false;
    if (!i.read_at || sticky.has(i.id)) return true;
    // прочитанное сворачиваем, пока оно внутри недельного окна
    return new Date(i.bumped_at || i.created_at).getTime() >= windowStart;
  };

  const wl = items.filter(isCollapsible);
  if (wl.length < WL_DIGEST_MIN) return { list: items, records: [], collapsedIds: [] };

  for (const i of wl) sticky.add(i.id);
  const rest = items.filter((i) => !isCollapsible(i));
  const records = wl.map(toDigestRecord);
  const collapsedIds = wl.map((i) => i.id);
  const newest = wl.reduce((a, b) =>
    new Date(b.bumped_at || b.created_at).getTime() > new Date(a.bumped_at || a.created_at).getTime()
      ? b
      : a,
  );
  const digest: NotificationItemType = {
    id: WL_DIGEST_ID,
    type: 'digest_wishlist_in_stock',
    dedup_key: null,
    entity_type: null,
    entity_id: null,
    data: { count: wl.length },
    created_at: newest.created_at,
    bumped_at: newest.bumped_at || newest.created_at,
    occurrences: wl.length,
    // непрочитанным дайджест остаётся, только пока в нём есть непрочитанные
    read_at: wl.some((i) => !i.read_at) ? null : (newest.read_at ?? new Date().toISOString()),
    actor: null,
  };
  return { list: [digest, ...rest], records, collapsedIds };
}

/**
 * Схлопывает дубликаты одной «нити» (один dedup_key — одна пластинка/ачивка),
 * которые backend мог наплодить через read→new-row. Оставляем самую свежую запись:
 * непрочитанную в приоритете, иначе по bumped_at. Записи без dedup_key не трогаем.
 */
function collapseByDedup(items: NotificationItemType[]): NotificationItemType[] {
  const byKey = new Map<string, NotificationItemType>();
  const passthrough: NotificationItemType[] = [];
  for (const it of items) {
    const key = it.dedup_key;
    if (!key) {
      passthrough.push(it);
      continue;
    }
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, it);
      continue;
    }
    byKey.set(key, pickFresher(prev, it));
  }
  return [...passthrough, ...byKey.values()];
}

function pickFresher(a: NotificationItemType, b: NotificationItemType): NotificationItemType {
  const aUnread = !a.read_at;
  const bUnread = !b.read_at;
  if (aUnread !== bUnread) return aUnread ? a : b;
  const at = new Date(a.bumped_at || a.created_at).getTime();
  const bt = new Date(b.bumped_at || b.created_at).getTime();
  return bt > at ? b : a;
}

function pluralizeNew(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'новых';
  if (mod10 === 1) return 'новое';
  if (mod10 >= 2 && mod10 <= 4) return 'новых';
  return 'новых';
}

function routeForPersonal(item: NotificationItemType, router: ReturnType<typeof useRouter>) {
  const data = item.data || {};
  const recordId = data.record_id as string | undefined;
  switch (item.type) {
    case 'follow_request':
      router.push('/social/follow-requests');
      return;
    case 'message_request': {
      const convId = (data.conversation_id as string | undefined) || item.entity_id || undefined;
      if (convId) router.push(`/messages/${convId}` as any);
      return;
    }
    case 'new_follower':
      if (item.actor?.username) router.push(`/user/${item.actor.username}`);
      return;
    case 'gift_booked':
    case 'gift_confirmed':
      if (item.entity_id) {
        router.push(`/gift/${item.entity_id}` as any);
      } else if (recordId) {
        router.push(`/record/${recordId}` as any);
      }
      return;
    case 'wishlist_in_stock':
    case 'wishlist_in_stock_alt':
    case 'wishlist_price_drop':
      if (recordId) router.push(`/record/${recordId}` as any);
      return;
    case 'achievement_unlocked':
    case 'milestone_unlocked': {
      const code = data.code as string | undefined;
      router.push(code ? (`/achievements?code=${code}` as any) : '/achievements');
      return;
    }
    case 'level_up':
      router.push('/achievements?levelup=1' as any);
      return;
  }
}

function routeForSocial(item: SocialFeedItem, router: ReturnType<typeof useRouter>) {
  switch (item.type) {
    case 'collection_add':
    case 'wishlist_add':
      if (item.record?.id) router.push(`/record/${item.record.id}`);
      return;
    case 'gift_completed':
      if (item.target_user?.username) router.push(`/user/${item.target_user.username}`);
      return;
    case 'friend_achievement':
    case 'friend_new_following':
      if (item.actor.username) router.push(`/user/${item.actor.username}`);
      return;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.sm,
    paddingBottom: Spacing.sm,
    gap: Spacing.sm,
  },
  headerTitleWrap: {
    flex: 1,
    flexShrink: 1,
  },
  headerTitle: {
    ...Typography.display,
  },
  closeBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentWrap: {
    paddingHorizontal: Spacing.md,
    paddingBottom: Spacing.sm,
  },
  pill: {
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.sm,
    paddingVertical: 8,
    paddingHorizontal: Spacing.md,
    borderRadius: 999,
    backgroundColor: Colors.royalBlue,
    alignSelf: 'center',
  },
  pillText: {
    ...Typography.buttonSmall,
    color: Colors.background,
  },
  sectionHeader: {
    paddingHorizontal: Spacing.md,
    paddingTop: Spacing.md,
    paddingBottom: Spacing.xs,
    backgroundColor: Colors.background,
  },
  sectionHeaderText: {
    ...Typography.overline,
    color: Colors.textMuted,
  },
  listContainer: {
    paddingBottom: Spacing.xxl,
  },
  emptyContainer: {
    flexGrow: 1,
    justifyContent: 'flex-start',
    paddingBottom: Spacing.xxl,
  },
  spinner: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
});
