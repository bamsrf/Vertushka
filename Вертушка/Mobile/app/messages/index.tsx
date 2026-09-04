/**
 * Инбокс сообщений (V2.3).
 *
 * - Сегмент Личные / Запросы внутри экрана (Instagram-style).
 * - Список диалогов: gradient-аватар, имя, mute-иконка, превью, time, read-mark / unread badge.
 * - Если есть pending-запросы — в баннере сверху стек 3 аватарок и «От @a, @b и ещё N».
 * - Скелетоны на первой загрузке; пересортировка диалогов (новое сообщение
 *   поднимает тред) анимируется через itemLayoutAnimation.
 * - Свайп-действия — собственный SwipeableActionsRow (Gesture.Pan): якорь на
 *   25% хода с хаптикой, squeeze-панель, без measure-магии ReanimatedSwipeable.
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
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
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
  withSpring,
  withTiming,
  cancelAnimation,
  runOnJS,
  type SharedValue,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
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

const SWIPE_BTN_W = 68;
// Якорь фиксации шторки: достаточно протянуть 25% её ширины (~51px),
// дальше отпускание защёлкивает панель полностью.
const SWIPE_OPEN_FRACTION = 0.25;
// Флик быстрее этой скорости решает сам, независимо от пройденной дистанции.
const SWIPE_FLING_VELOCITY = 500;
// Почти критическое затухание — фиксация одним движением, без «желе».
const CALM_SPRING = { damping: 26, stiffness: 300, overshootClamping: true };

function swipeAnchorHaptic() {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
}

interface SwipeActionSpec {
  key: string;
  icon: string;
  label: string;
  bg: string;
  onPress: () => void;
}

/**
 * Шторка свайпа (iOS-style squeeze): панель всегда заполняет открытую часть
 * строки от края до края — кнопки равными долями растут вслед за пальцем и
 * доезжают до полной ширины при фиксации. Геометрически исключает щели и
 * наезды кнопок при частичном открытии.
 *
 * Внешний View фиксированной ширины — по нему Swipeable меряет точку
 * фиксации; внутренняя панель прижата к правому краю и ведома translation.
 */
function SwipeActionsPanel({
  specs,
  translation,
  onPressItem,
}: {
  specs: SwipeActionSpec[];
  translation: SharedValue<number>;
  onPressItem: (spec: SwipeActionSpec) => void;
}) {
  const fullW = specs.length * SWIPE_BTN_W;
  const panelStyle = useAnimatedStyle(() => ({
    width: Math.min(fullW, Math.max(0, -translation.value)),
  }));
  return (
    <Animated.View style={[styles.swipePanel, panelStyle]}>
      {specs.map((spec) => (
        <TouchableOpacity
          key={spec.key}
          style={[styles.swipeBtn, { backgroundColor: spec.bg }]}
          onPress={() => onPressItem(spec)}
          activeOpacity={0.8}
        >
          <View style={styles.swipeBtnContent}>
            <Icon name={spec.icon} size={18} color="#fff" />
            <Text style={styles.swipeBtnTxt} numberOfLines={1}>
              {spec.label}
            </Text>
          </View>
        </TouchableOpacity>
      ))}
    </Animated.View>
  );
}

// Одновременно открыта максимум одна шторка: открывшаяся строка закрывает
// предыдущую (Telegram-паттерн).
let closeOpenSwipeRow: (() => void) | null = null;

/**
 * Собственный swipe-row вместо ReanimatedSwipeable: тот меряет ширину панели
 * невидимым маркером через measure(), и на new arch измерение периодически
 * срывается. Здесь геометрия задана константами, без измерений:
 *
 * - контент строки следует за пальцем 1:1 (кламп 0…-ширина панели);
 * - на 25% хода — хаптика-якорь; отпускание после якоря защёлкивает панель;
 * - быстрый флик решает сам, независимо от дистанции;
 * - панель отрисована ПОВЕРХ контента: тапы по кнопкам не может перехватить
 *   сдвинутая строка, чем бы ни считал её hit-test;
 * - доводка в onFinalize: даже отменённый жест (перехват скролла) не бросает
 *   шторку на полпути;
 * - тап по строке сразу после свайпа игнорируется — Touchable внутри
 *   детектора может выстрелить фантомным press после жеста и тут же закрыть
 *   только что открытую панель.
 */
function SwipeableActionsRow({
  specs,
  onRowPress,
  children,
}: {
  specs: SwipeActionSpec[];
  onRowPress: () => void;
  children: React.ReactNode;
}) {
  const fullW = specs.length * SWIPE_BTN_W;
  const tx = useSharedValue(0);
  const startX = useSharedValue(0);
  const crossed = useSharedValue(false);
  const lastSwipeEndRef = useRef(0);

  const close = useCallback(() => {
    tx.value = withSpring(0, CALM_SPRING);
  }, [tx]);

  // Фиксация результата жеста на JS-стороне: метка времени против фантомного
  // press и регистрация «единственной открытой» строки.
  const noteSettled = useCallback(
    (opened: boolean) => {
      lastSwipeEndRef.current = Date.now();
      if (opened) {
        if (closeOpenSwipeRow && closeOpenSwipeRow !== close) closeOpenSwipeRow();
        closeOpenSwipeRow = close;
      } else if (closeOpenSwipeRow === close) {
        closeOpenSwipeRow = null;
      }
    },
    [close],
  );

  useEffect(
    () => () => {
      if (closeOpenSwipeRow === close) closeOpenSwipeRow = null;
    },
    [close],
  );

  const handleRowPress = useCallback(() => {
    if (Date.now() - lastSwipeEndRef.current < 300) return;
    if (Math.abs(tx.value) > 4) {
      close();
      closeOpenSwipeRow = null;
      return;
    }
    onRowPress();
  }, [tx, close, onRowPress]);

  const handleItemPress = useCallback(
    (spec: SwipeActionSpec) => {
      // Быстрое закрытие таймингом: пружина не успевала досесть до
      // пересортировки списка, и строка ехала с полуоткрытой панелью.
      tx.value = withTiming(0, { duration: 120 });
      closeOpenSwipeRow = null;
      spec.onPress();
    },
    [tx],
  );

  const pan = Gesture.Pan()
    .activeOffsetX([-12, 12])
    .failOffsetY([-10, 10])
    .onStart(() => {
      startX.value = tx.value;
      crossed.value = -tx.value >= fullW * SWIPE_OPEN_FRACTION;
    })
    .onUpdate((e) => {
      const next = Math.min(0, Math.max(-fullW, startX.value + e.translationX));
      tx.value = next;
      const isCrossed = -next >= fullW * SWIPE_OPEN_FRACTION;
      if (isCrossed && !crossed.value) {
        crossed.value = true;
        runOnJS(swipeAnchorHaptic)();
      } else if (!isCrossed) {
        crossed.value = false;
      }
    })
    .onFinalize((e) => {
      const pastAnchor = -tx.value >= fullW * SWIPE_OPEN_FRACTION;
      const shouldOpen = pastAnchor
        ? e.velocityX < SWIPE_FLING_VELOCITY // отменит только явный флик вправо
        : e.velocityX < -SWIPE_FLING_VELOCITY; // короткий, но резкий флик влево — открыть
      tx.value = withSpring(shouldOpen ? -fullW : 0, CALM_SPRING);
      runOnJS(noteSettled)(shouldOpen);
    });

  const contentStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }],
  }));

  return (
    <GestureDetector gesture={pan}>
      <View style={styles.swipeRowWrap}>
        {/* Непрозрачный фон обязателен: сквозь полупрозрачный tint
            закреплённой строки просвечивала бы панель под ней. */}
        <Animated.View style={[styles.swipeRowContent, contentStyle]}>
          <TouchableOpacity activeOpacity={0.7} onPress={handleRowPress}>
            {children}
          </TouchableOpacity>
        </Animated.View>
        <View style={styles.swipePanelHost} pointerEvents="box-none">
          <SwipeActionsPanel
            specs={specs}
            translation={tx}
            onPressItem={handleItemPress}
          />
        </View>
      </View>
    </GestureDetector>
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

  const actionSpecs: SwipeActionSpec[] = [];
  if (!isRequest && onTogglePin) {
    actionSpecs.push({
      key: 'pin',
      icon: 'star',
      label: item.pinned ? 'Открепить' : 'Закрепить',
      bg: '#FBBF24',
      onPress: onTogglePin,
    });
  }
  if (!isRequest && onToggleMute) {
    actionSpecs.push({
      key: 'mute',
      icon: item.muted ? 'bell' : 'bell-slash',
      label: item.muted ? 'Звук' : 'Тихо',
      bg: '#94A3B8',
      onPress: onToggleMute,
    });
  }
  if (onArchive) {
    actionSpecs.push({
      key: 'hide',
      icon: 'eye-slash',
      label: 'Скрыть',
      bg: '#E5484D',
      onPress: onArchive,
    });
  }

  const content = (
    <View style={[styles.row, item.pinned && styles.rowPinned]}>
      <Avatar url={item.partner.avatar_url} username={item.partner.username} size={52} />
      <View style={styles.rowMain}>
        <View style={styles.rowTop}>
          <View style={styles.rowNameWrap}>
            <Text style={styles.rowName} numberOfLines={1}>
              {item.partner.display_name || `@${item.partner.username}`}
            </Text>
            {item.pinned ? (
              <Icon name="star" size={12} color={Colors.royalBlue} />
            ) : null}
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
              entering={ZoomIn.duration(140).withInitialValues({
                transform: [{ scale: 0.85 }],
              })}
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
      </View>
    </View>
  );

  if (isRequest) {
    return (
      <TouchableOpacity activeOpacity={0.7} onPress={onPress}>
        {content}
      </TouchableOpacity>
    );
  }

  return (
    <SwipeableActionsRow specs={actionSpecs} onRowPress={onPress}>
      {content}
    </SwipeableActionsRow>
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
          entering={FadeInDown.duration(180)}
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
        // плавно вместо телепорта.
        itemLayoutAnimation={LinearTransition.duration(220)}
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
  swipeRowWrap: {
    overflow: 'hidden',
  },
  swipeRowContent: {
    backgroundColor: Colors.background,
  },
  swipePanelHost: {
    ...StyleSheet.absoluteFill,
  },
  swipePanel: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  swipeBtn: {
    flex: 1,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  swipeBtnContent: {
    width: SWIPE_BTN_W,
    alignItems: 'center',
    gap: 4,
  },
  swipeBtnTxt: { color: '#fff', fontSize: ms(11), fontWeight: '600' },

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
