/**
 * Инбокс сообщений (V2.3).
 *
 * - Сегмент Личные / Запросы внутри экрана (Instagram-style).
 * - Список диалогов: gradient-аватар, имя, mute-иконка, превью, time, read-mark / unread badge.
 * - Если есть pending-запросы — в баннере сверху стек 3 аватарок и «От @a, @b и ещё N».
 * - Скелетоны на первой загрузке; пересортировка диалогов (новое сообщение
 *   поднимает тред) анимируется через itemLayoutAnimation.
 * - Свайп-действия на ReanimatedSwipeable (плавнее старого Swipeable).
 * - Empty state — карточкой с подсказкой.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import ReanimatedSwipeable, {
  type SwipeableMethods,
} from 'react-native-gesture-handler/ReanimatedSwipeable';
import Animated, {
  LinearTransition,
  FadeIn,
  FadeOut,
  FadeInDown,
  ZoomIn,
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  cancelAnimation,
} from 'react-native-reanimated';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon, SegmentedControl } from '@/components/ui';
import { Colors, Spacing, BorderRadius } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import { useAuthStore } from '../../lib/store';
import { useMessagesStore } from '../../lib/messagesStore';
import { resolveMediaUrl } from '../../lib/api';
import { registerPushToken } from '../../lib/push';
import type { Conversation } from '../../lib/messagesTypes';
import { Header } from '../../components/Header';

type Folder = 'primary' | 'requests';

const SEGMENTS: { key: Folder; label: string }[] = [
  { key: 'primary', label: 'Личные' },
  { key: 'requests', label: 'Запросы' },
];

function formatTime(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000);
  if (diffDays < 7) {
    return d.toLocaleDateString('ru-RU', { weekday: 'short' });
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
}

function Avatar({
  url,
  username,
  size = 52,
}: {
  url?: string | null;
  username: string;
  size?: number;
}) {
  const initials = username.slice(0, 2).toUpperCase();
  if (url) {
    return (
      <Image
        source={resolveMediaUrl(url)}
        style={{ width: size, height: size, borderRadius: size / 2 }}
        cachePolicy="disk"
      />
    );
  }
  return (
    <LinearGradient
      colors={[Colors.royalBlue, Colors.periwinkle]}
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Text style={[styles.avatarInitials, { fontSize: size * 0.34 }]}>
        {initials}
      </Text>
    </LinearGradient>
  );
}

function ConversationRow({
  item,
  isMine,
  onPress,
  onAccept,
  onReject,
  onTogglePin,
  onToggleMute,
  onArchive,
}: {
  item: Conversation;
  isMine: boolean;
  onPress: () => void;
  onAccept?: () => void;
  onReject?: () => void;
  onTogglePin?: () => void;
  onToggleMute?: () => void;
  onArchive?: () => void;
}) {
  const previewPrefix = isMine ? 'Вы: ' : '';
  const preview = item.last_message_preview ?? 'Нет сообщений';
  const unread = item.unread_count;
  const isRequest = item.request_status === 'pending';
  const swipeRef = useRef<SwipeableMethods>(null);

  const renderRightActions = () => (
    <View style={styles.swipeActions}>
      {!isRequest && onTogglePin ? (
        <TouchableOpacity
          style={[styles.swipeBtn, styles.swipeBtnPin]}
          onPress={() => {
            swipeRef.current?.close();
            onTogglePin();
          }}
        >
          <Icon name="star" size={18} color="#fff" />
          <Text style={styles.swipeBtnTxt}>{item.pinned ? 'Открепить' : 'Закрепить'}</Text>
        </TouchableOpacity>
      ) : null}
      {!isRequest && onToggleMute ? (
        <TouchableOpacity
          style={[styles.swipeBtn, styles.swipeBtnMute]}
          onPress={() => {
            swipeRef.current?.close();
            onToggleMute();
          }}
        >
          <Icon
            name={item.muted ? 'bell' : 'bell-slash'}
            size={18}
            color="#fff"
          />
          <Text style={styles.swipeBtnTxt}>{item.muted ? 'Звук' : 'Mute'}</Text>
        </TouchableOpacity>
      ) : null}
      {onArchive ? (
        <TouchableOpacity
          style={[styles.swipeBtn, styles.swipeBtnArchive]}
          onPress={() => {
            swipeRef.current?.close();
            onArchive();
          }}
        >
          <Icon name="trash" size={18} color="#fff" />
          <Text style={styles.swipeBtnTxt}>Удалить</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );

  const content = (
    <TouchableOpacity activeOpacity={0.7} style={[styles.row, item.pinned && styles.rowPinned]} onPress={onPress}>
      <Avatar url={item.partner.avatar_url} username={item.partner.username} size={52} />
      <View style={styles.rowMain}>
        <View style={styles.rowTop}>
          <View style={styles.rowNameWrap}>
            <Text style={styles.rowName} numberOfLines={1}>
              {item.partner.display_name || `@${item.partner.username}`}
            </Text>
            {item.muted ? (
              <Icon name="bell-slash" size={12} color={Colors.textMuted} />
            ) : null}
          </View>
          <Text style={[styles.rowTime, unread > 0 && styles.rowTimeUnread]}>
            {formatTime(item.last_message_at)}
          </Text>
        </View>
        <View style={styles.rowBottom}>
          <Text
            style={[
              styles.rowPreview,
              unread > 0 && styles.rowPreviewUnread,
              item.muted && unread > 0 && styles.rowPreviewMutedUnread,
            ]}
            numberOfLines={isRequest ? 2 : 1}
          >
            {previewPrefix}
            {preview}
          </Text>
          {!isRequest && unread > 0 ? (
            <Animated.View
              entering={ZoomIn.springify().damping(14).stiffness(260)}
              exiting={FadeOut.duration(120)}
              style={[styles.unreadDot, item.muted && styles.unreadDotMuted]}
            >
              <Text style={styles.unreadTxt}>{unread > 99 ? '99+' : unread}</Text>
            </Animated.View>
          ) : null}
        </View>
        {isRequest && (onAccept || onReject) ? (
          <View style={styles.requestActions}>
            <TouchableOpacity
              style={[styles.reqBtn, styles.reqBtnAccept]}
              onPress={onAccept}
              activeOpacity={0.8}
            >
              <Text style={styles.reqBtnAcceptTxt}>Принять</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.reqBtn, styles.reqBtnReject]}
              onPress={onReject}
              activeOpacity={0.8}
            >
              <Text style={styles.reqBtnRejectTxt}>Удалить</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {item.pinned ? (
          <View style={styles.pinnedBadge}>
            <Icon name="star" size={10} color={Colors.royalBlue} />
          </View>
        ) : null}
      </View>
    </TouchableOpacity>
  );

  if (isRequest) return content;

  return (
    <ReanimatedSwipeable
      ref={swipeRef}
      renderRightActions={renderRightActions}
      friction={2}
      rightThreshold={40}
    >
      {content}
    </ReanimatedSwipeable>
  );
}

/** Пульсирующий скелетон диалога — первая загрузка вместо пустого экрана. */
function SkeletonRow() {
  const pulse = useSharedValue(0.5);

  useEffect(() => {
    pulse.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 600 }),
        withTiming(0.5, { duration: 600 }),
      ),
      -1,
    );
    return () => cancelAnimation(pulse);
  }, [pulse]);

  const style = useAnimatedStyle(() => ({ opacity: pulse.value }));

  return (
    <Animated.View style={[styles.row, style]}>
      <View style={styles.skelAvatar} />
      <View style={styles.rowMain}>
        <View style={styles.skelLineWide} />
        <View style={styles.skelLineNarrow} />
      </View>
    </Animated.View>
  );
}

function InboxSkeleton() {
  return (
    <Animated.View exiting={FadeOut.duration(160)}>
      {Array.from({ length: 6 }, (_, i) => (
        <SkeletonRow key={i} />
      ))}
    </Animated.View>
  );
}

function RequestsHint({ requests }: { requests: Conversation[] }) {
  const top3 = requests.slice(0, 3);
  const namesText = useMemo(() => {
    if (requests.length === 0) return '';
    if (requests.length === 1) return `От @${requests[0].partner.username}`;
    if (requests.length === 2) {
      return `От @${requests[0].partner.username} и @${requests[1].partner.username}`;
    }
    const rest = requests.length - 2;
    return `От @${requests[0].partner.username}, @${requests[1].partner.username} и ещё ${rest}`;
  }, [requests]);

  return (
    <View style={styles.requestsHint}>
      <View style={styles.avatarsStack}>
        {top3.map((r, i) => (
          <View
            key={r.id}
            style={[
              styles.stackedAvatar,
              { marginLeft: i === 0 ? 0 : -12, zIndex: 3 - i },
            ]}
          >
            <Avatar url={r.partner.avatar_url} username={r.partner.username} size={32} />
          </View>
        ))}
      </View>
      <View style={{ flex: 1, marginLeft: Spacing.sm }}>
        <Text style={styles.requestsHintTitle}>
          {requests.length} {requests.length === 1 ? 'запрос' : requests.length < 5 ? 'запроса' : 'запросов'}
        </Text>
        <Text style={styles.requestsHintSub} numberOfLines={1}>
          {namesText}
        </Text>
      </View>
    </View>
  );
}

export default function MessagesInboxScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const me = useAuthStore((s) => s.user);
  const primary = useMessagesStore((s) => s.conversationsPrimary);
  const requests = useMessagesStore((s) => s.conversationsRequests);
  const isLoading = useMessagesStore((s) => s.isLoadingList);
  const loadConversations = useMessagesStore((s) => s.loadConversations);
  const refreshUnread = useMessagesStore((s) => s.refreshUnread);
  const acceptRequest = useMessagesStore((s) => s.acceptRequest);
  const rejectRequest = useMessagesStore((s) => s.rejectRequest);
  const togglePin = useMessagesStore((s) => s.togglePin);
  const toggleMute = useMessagesStore((s) => s.toggleMute);
  const archive = useMessagesStore((s) => s.archive);

  const [folder, setFolder] = useState<Folder>('primary');

  const reload = useCallback(async () => {
    await Promise.all([
      loadConversations('primary'),
      loadConversations('requests'),
      refreshUnread(),
    ]);
  }, [loadConversations, refreshUnread]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Контекстная точка запроса push-разрешения: юзер открыл сообщения —
  // уведомления о новых сообщениях ему релевантны (см. lib/push.ts).
  useEffect(() => {
    registerPushToken({ requestIfNeeded: true });
  }, []);

  const segments = useMemo(() => {
    return SEGMENTS.map((s) =>
      s.key === 'requests' && requests.length > 0
        ? { ...s, label: `Запросы · ${requests.length}` }
        : s
    );
  }, [requests.length]);

  const data = folder === 'primary' ? primary : requests;

  const renderItem = useCallback(
    ({ item }: { item: Conversation }) => (
      <ConversationRow
        item={item}
        isMine={!!me && item.last_message_sender_id === me.id}
        onPress={() => router.push(`/messages/${item.id}` as any)}
        onAccept={
          item.request_status === 'pending'
            ? () => {
                acceptRequest(item.id)
                  .then(() => router.push(`/messages/${item.id}` as any))
                  .catch(() => {
                    // ошибка уже показана toast'ом в сторе
                  });
              }
            : undefined
        }
        onReject={
          item.request_status === 'pending'
            ? () => {
                rejectRequest(item.id).catch(() => {});
              }
            : undefined
        }
        onTogglePin={
          item.request_status === 'accepted' ? () => togglePin(item.id) : undefined
        }
        onToggleMute={
          item.request_status === 'accepted' ? () => toggleMute(item.id) : undefined
        }
        onArchive={() => archive(item.id).catch(() => {})}
      />
    ),
    [me, router, acceptRequest, rejectRequest, togglePin, toggleMute, archive]
  );

  const renderEmpty = () => {
    if (isLoading) return <InboxSkeleton />;
    if (folder === 'primary') {
      return (
        <Animated.View entering={FadeIn.duration(200)} style={styles.empty}>
          <View style={styles.emptyIconBg}>
            <Icon name="chat-circle" size={36} color={Colors.royalBlue} />
          </View>
          <Text style={styles.emptyTitle}>Пока никто не написал</Text>
          <Text style={styles.emptySub}>
            Откройте чей-нибудь профиль и нажмите «Написать», или начните диалог через кнопку ниже.
          </Text>
          <TouchableOpacity
            style={styles.emptyBtn}
            activeOpacity={0.85}
            onPress={() => router.push('/messages/new' as any)}
          >
            <Icon name="pencil" size={16} color="#fff" />
            <Text style={styles.emptyBtnTxt}>Новое сообщение</Text>
          </TouchableOpacity>
        </Animated.View>
      );
    }
    return (
      <Animated.View entering={FadeIn.duration(200)} style={styles.empty}>
        <Icon name="envelope" size={36} color={Colors.textMuted} />
        <Text style={styles.emptyTitle}>Запросов нет</Text>
        <Text style={styles.emptySub}>
          Здесь появятся первые сообщения от тех, на кого вы не подписаны.
        </Text>
      </Animated.View>
    );
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <Header title="Сообщения" showBack showProfile={false} />

      <SegmentedControl
        segments={segments}
        selectedKey={folder}
        onSelect={setFolder}
        style={styles.segmented}
      />

      {folder === 'primary' && requests.length > 0 ? (
        <Animated.View
          entering={FadeInDown.springify().damping(18)}
          exiting={FadeOut.duration(140)}
        >
          <TouchableOpacity
            activeOpacity={0.7}
            onPress={() => setFolder('requests')}
          >
            <RequestsHint requests={requests} />
          </TouchableOpacity>
        </Animated.View>
      ) : null}

      <Animated.FlatList
        data={data}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        ListEmptyComponent={renderEmpty}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
        // Пересортировка (новое сообщение поднимает диалог наверх) едет
        // пружиной вместо телепорта.
        itemLayoutAnimation={LinearTransition.springify().damping(18)}
        refreshControl={
          <RefreshControl
            refreshing={isLoading}
            onRefresh={reload}
            tintColor={Colors.royalBlue}
          />
        }
      />

      {folder === 'primary' && primary.length > 0 ? (
        <TouchableOpacity
          style={[styles.fab, { bottom: insets.bottom + 100 }]}
          activeOpacity={0.85}
          onPress={() => router.push('/messages/new' as any)}
        >
          <Icon name="pencil" size={20} color="#fff" />
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },

  segmented: {
    marginHorizontal: Spacing.md,
    marginTop: 4,
    marginBottom: Spacing.sm,
  },

  /* Requests preview banner (Instagram-style stacked avatars) */
  requestsHint: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: Spacing.md,
    marginBottom: Spacing.sm,
    paddingHorizontal: Spacing.md,
    paddingVertical: 10,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  avatarsStack: { flexDirection: 'row', alignItems: 'center' },
  stackedAvatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 2,
    borderColor: Colors.background,
    overflow: 'hidden',
  },
  requestsHintTitle: { fontSize: ms(13), fontWeight: '600', color: Colors.text },
  requestsHintSub: { fontSize: ms(12), color: Colors.textMuted, marginTop: 1 },

  listContent: { paddingBottom: 160 },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: 10,
    paddingHorizontal: Spacing.md,
    backgroundColor: Colors.background,
  },
  rowPinned: {
    backgroundColor: 'rgba(154,168,255,0.06)',
  },

  /* Swipe actions */
  swipeActions: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  swipeBtn: {
    width: 78,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  swipeBtnPin: { backgroundColor: '#FBBF24' },
  swipeBtnMute: { backgroundColor: '#94A3B8' },
  swipeBtnArchive: { backgroundColor: '#E5484D' },
  swipeBtnTxt: { color: '#fff', fontSize: ms(11), fontWeight: '600' },

  pinnedBadge: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: 'rgba(59,75,245,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitials: {
    color: '#fff',
    fontWeight: '700',
    letterSpacing: 0.3,
  },

  /* Skeleton первой загрузки */
  skelAvatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: Colors.surface,
  },
  skelLineWide: {
    height: 14,
    borderRadius: 7,
    backgroundColor: Colors.surface,
    alignSelf: 'stretch',
    marginRight: 60,
  },
  skelLineNarrow: {
    height: 11,
    borderRadius: 6,
    backgroundColor: Colors.surface,
    marginTop: 8,
    marginRight: 140,
  },

  rowMain: { flex: 1, minWidth: 0 },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.sm,
  },
  rowNameWrap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  rowName: {
    fontSize: ms(15),
    fontWeight: '600',
    color: Colors.text,
    flexShrink: 1,
  },
  rowTime: { fontSize: 11, color: Colors.textMuted },
  rowTimeUnread: { color: Colors.royalBlue, fontWeight: '600' },

  rowBottom: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 3,
    gap: Spacing.sm,
  },
  rowPreview: { fontSize: ms(13), color: Colors.textMuted, flex: 1 },
  rowPreviewUnread: { color: Colors.text, fontWeight: '500' },
  rowPreviewMutedUnread: { color: Colors.textMuted, fontWeight: '400' },

  unreadDot: {
    minWidth: 20,
    height: 20,
    paddingHorizontal: 6,
    borderRadius: 10,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  unreadDotMuted: { backgroundColor: Colors.textMuted },
  unreadTxt: { fontSize: 10, color: '#fff', fontWeight: '700' },

  /* Request action buttons */
  requestActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  reqBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: BorderRadius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reqBtnAccept: { backgroundColor: Colors.royalBlue },
  reqBtnAcceptTxt: { color: '#fff', fontSize: ms(13), fontWeight: '600' },
  reqBtnReject: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  reqBtnRejectTxt: { color: Colors.text, fontSize: ms(13), fontWeight: '600' },

  /* Empty state */
  empty: {
    alignItems: 'center',
    paddingTop: 60,
    paddingHorizontal: Spacing.lg,
    gap: 10,
  },
  emptyIconBg: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: Spacing.sm,
  },
  emptyTitle: { fontSize: ms(17), fontWeight: '700', color: Colors.text },
  emptySub: {
    fontSize: ms(13),
    color: Colors.textMuted,
    textAlign: 'center',
    lineHeight: 18,
  },
  emptyBtn: {
    marginTop: Spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: Colors.royalBlue,
    paddingHorizontal: 18,
    paddingVertical: 11,
    borderRadius: BorderRadius.full,
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
  },
  emptyBtnTxt: { color: '#fff', fontWeight: '600', fontSize: ms(14) },

  fab: {
    position: 'absolute',
    right: Spacing.lg,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },
});
