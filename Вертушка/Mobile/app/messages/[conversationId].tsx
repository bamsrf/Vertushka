/**
 * Экран одного диалога (V2.3).
 *
 * - Группировка сообщений того же sender ≤5 минут (Telegram-style).
 * - Date-разделители («Сегодня», «Вчера», конкретная дата).
 * - Read-receipt галочки на своих сообщениях.
 * - Composer: paperclip (заглушка под share record), TextInput до 5 строк,
 *   круглая send-кнопка с плавным переходом disabled ↔ active.
 * - Empty state: карточка с аватаркой собеседника.
 *
 * Поллинг 8с пока экран открыт (заменится на WS в M2).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  TouchableOpacity,
  Platform,
  ActivityIndicator,
  AppState,
  AppStateStatus,
  ListRenderItem,
  ActionSheetIOS,
  Alert,
  Keyboard,
  Share,
  NativeScrollEvent,
  NativeSyntheticEvent,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  runOnJS,
  interpolate,
  Extrapolation,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';
import {
  MessageContextMenu,
  type MenuAction,
} from '../../components/messages/MessageContextMenu';
import { Colors, Spacing, BorderRadius } from '../../constants/theme';
import { ms } from '../../lib/responsive';
import { useAuthStore } from '../../lib/store';
import { useMessagesStore } from '../../lib/messagesStore';
import { api, resolveMediaUrl } from '../../lib/api';
import { messagesApi } from '../../lib/messagesApi';
import { toast } from '../../lib/toast';
import { cleanArtistName } from '../../lib/format';
import { messagesSocket } from '../../lib/messagesWs';
import type {
  AttachedRecord,
  Conversation,
  Message,
  MessageReaction,
  PresenceInfo,
} from '../../lib/messagesTypes';

const POLL_INTERVAL_MS = 8000;
const PRESENCE_INTERVAL_MS = 30_000;
const GROUP_GAP_MS = 5 * 60 * 1000; // сообщения подряд того же sender → одна группа
const EMPTY_MESSAGES: Message[] = [];

function formatLastSeen(iso: string | null): string {
  if (!iso) return 'был(а) в сети давно';
  const d = new Date(iso);
  const now = new Date();
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60_000);
  if (diffMin < 1) return 'был(а) только что';
  if (diffMin < 60) return `был(а) ${diffMin} мин назад`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `был(а) ${diffH} ч назад`;
  return `был(а) ${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}`;
}

function formatBubbleTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function formatDateLabel(d: Date): string {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());

  if (target.getTime() === today.getTime()) return 'Сегодня';
  if (target.getTime() === yesterday.getTime()) return 'Вчера';

  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: sameYear ? undefined : 'numeric',
  });
}

type FeedItem =
  | { type: 'date'; key: string; date: Date }
  | { type: 'unread-divider'; key: string }
  | {
      type: 'message';
      key: string;
      message: Message;
      isMine: boolean;
      isLastInGroup: boolean;
      isFirstInGroup: boolean;
    };

function buildFeed(
  messages: Message[],
  meId: string | null,
  unreadFirstMsgId: string | null,
): FeedItem[] {
  if (messages.length === 0) return [];
  const sorted = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  const items: FeedItem[] = [];
  let prevDayKey: string | null = null;
  let prevMsg: Message | null = null;
  let unreadInserted = false;

  for (let i = 0; i < sorted.length; i++) {
    const m = sorted[i];
    const date = new Date(m.created_at);
    const dayKey = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;

    if (dayKey !== prevDayKey) {
      items.push({ type: 'date', key: `date-${dayKey}`, date });
      prevDayKey = dayKey;
      prevMsg = null;
    }

    const isMine = !!meId && m.sender_id === meId;

    if (!unreadInserted && unreadFirstMsgId && m.id === unreadFirstMsgId) {
      items.push({ type: 'unread-divider', key: 'unread-divider' });
      unreadInserted = true;
    }

    const isFirstInGroup =
      !prevMsg ||
      prevMsg.sender_id !== m.sender_id ||
      new Date(m.created_at).getTime() - new Date(prevMsg.created_at).getTime() > GROUP_GAP_MS;

    const next = sorted[i + 1];
    const isLastInGroup =
      !next ||
      next.sender_id !== m.sender_id ||
      new Date(next.created_at).getTime() - new Date(m.created_at).getTime() > GROUP_GAP_MS;

    items.push({
      type: 'message',
      key: m.id,
      message: m,
      isMine,
      isFirstInGroup,
      isLastInGroup,
    });
    prevMsg = m;
  }
  return items;
}

function ReadMark({
  status,
  isRead,
}: {
  status: Message['_local_status'];
  isRead: boolean;
}) {
  if (status === 'sending') {
    return <ActivityIndicator size="small" color="rgba(255,255,255,0.7)" />;
  }
  // Двойная галка — собеседник прочитал; одинарная — отправлено.
  if (isRead) {
    return (
      <View style={{ flexDirection: 'row' }}>
        <Icon name="check" size={12} color="#7AE2FF" />
        <View style={{ marginLeft: -6 }}>
          <Icon name="check" size={12} color="#7AE2FF" />
        </View>
      </View>
    );
  }
  return <Icon name="check" size={12} color="rgba(255,255,255,0.75)" />;
}

function aggregateReactions(
  reactions: MessageReaction[] | undefined,
  myId: string | null,
): { emoji: string; count: number; mine: boolean }[] {
  if (!reactions || reactions.length === 0) return [];
  const byEmoji = new Map<string, { emoji: string; count: number; mine: boolean }>();
  for (const r of reactions) {
    const cur = byEmoji.get(r.emoji);
    if (cur) {
      cur.count += 1;
      if (myId && r.user_id === myId) cur.mine = true;
    } else {
      byEmoji.set(r.emoji, {
        emoji: r.emoji,
        count: 1,
        mine: !!myId && r.user_id === myId,
      });
    }
  }
  return Array.from(byEmoji.values());
}

function ReactionsRow({
  reactions,
  isMine,
  meId,
  onPress,
}: {
  reactions: MessageReaction[] | undefined;
  isMine: boolean;
  meId: string | null;
  onPress: (emoji: string) => void;
}) {
  const items = aggregateReactions(reactions, meId);
  if (items.length === 0) return null;
  return (
    <View
      style={[
        styles.reactionsRow,
        isMine ? styles.reactionsRowMine : styles.reactionsRowOther,
      ]}
    >
      {items.map((it) => (
        <TouchableOpacity
          key={it.emoji}
          activeOpacity={0.7}
          onPress={() => onPress(it.emoji)}
          style={[
            styles.reactionChip,
            it.mine && styles.reactionChipMine,
          ]}
        >
          <Text style={styles.reactionChipEmoji}>{it.emoji}</Text>
          {it.count > 1 ? (
            <Text style={[styles.reactionChipCount, it.mine && styles.reactionChipCountMine]}>
              {it.count}
            </Text>
          ) : null}
        </TouchableOpacity>
      ))}
    </View>
  );
}

function MessageBubble({
  message,
  isMine,
  isLastInGroup,
  isFirstInGroup,
  isRead,
  isSelected,
  selectionMode,
  isHighlighted,
  meId,
  onLongPress,
  onPress,
  onOpenRecord,
  onJumpToReply,
  onToggleReaction,
}: {
  message: Message;
  isMine: boolean;
  isLastInGroup: boolean;
  isFirstInGroup: boolean;
  isRead: boolean;
  isSelected: boolean;
  selectionMode: boolean;
  isHighlighted: boolean;
  meId: string | null;
  onLongPress: () => void;
  onPress: () => void;
  onOpenRecord?: (recordId: string) => void;
  onJumpToReply?: (messageId: string) => void;
  onToggleReaction?: (messageId: string, emoji: string) => void;
}) {
  if (message.deleted_at) {
    return (
      <View
        style={[
          styles.bubbleRow,
          isFirstInGroup && styles.bubbleRowFirstInGroup,
          isLastInGroup && styles.bubbleRowLastInGroup,
          isMine ? styles.bubbleRowMine : styles.bubbleRowOther,
        ]}
      >
        <View style={[styles.bubble, styles.bubbleDeleted]}>
          <Text style={styles.bubbleDeletedTxt}>Сообщение удалено</Text>
        </View>
      </View>
    );
  }

  const isFailed = message._local_status === 'failed';
  const hasBody = !!(message.body && message.body.trim().length > 0);
  const recordCard = message.attached_record ? (
    <TouchableOpacity
      activeOpacity={0.85}
      onPress={() => {
        if (selectionMode) {
          onPress();
          return;
        }
        if (message.attached_record) onOpenRecord?.(message.attached_record.id);
      }}
      onLongPress={onLongPress}
      delayLongPress={300}
      style={[
        styles.bubbleRecord,
        isMine ? styles.bubbleRecordMine : styles.bubbleRecordOther,
        !hasBody && { marginBottom: 0 },
      ]}
    >
      {message.attached_record.cover_image_url ? (
        <Image
          source={resolveMediaUrl(message.attached_record.cover_image_url)}
          style={styles.bubbleRecordCover}
          cachePolicy="disk"
        />
      ) : (
        <View
          style={[
            styles.bubbleRecordCover,
            { alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.05)' },
          ]}
        >
          <Icon name="disc" size={18} color={Colors.textMuted} />
        </View>
      )}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text
          style={[
            styles.bubbleRecordTitle,
            { color: isMine ? '#fff' : Colors.text },
          ]}
          numberOfLines={1}
        >
          {message.attached_record.title}
        </Text>
        <Text
          style={[
            styles.bubbleRecordSub,
            { color: isMine ? 'rgba(255,255,255,0.75)' : Colors.textMuted },
          ]}
          numberOfLines={1}
        >
          {cleanArtistName(message.attached_record.artist) || message.attached_record.artist}
          {message.attached_record.year ? ` · ${message.attached_record.year}` : ''}
        </Text>
      </View>
    </TouchableOpacity>
  ) : null;

  return (
    <View
      style={[
        styles.bubbleRow,
        isFirstInGroup && styles.bubbleRowFirstInGroup,
        isLastInGroup && styles.bubbleRowLastInGroup,
        isMine ? styles.bubbleRowMine : styles.bubbleRowOther,
        isSelected && styles.bubbleRowSelected,
        isHighlighted && styles.bubbleRowHighlighted,
      ]}
    >
      <TouchableOpacity
        activeOpacity={0.85}
        onLongPress={onLongPress}
        onPress={onPress}
        delayLongPress={300}
        style={[
          styles.bubble,
          isMine ? styles.bubbleMine : styles.bubbleOther,
          isMine && !isLastInGroup && { borderBottomRightRadius: 18 },
          !isMine && !isLastInGroup && { borderBottomLeftRadius: 18 },
          isSelected && styles.bubbleSelected,
        ]}
      >
        {message.reply_to ? (
          <TouchableOpacity
            activeOpacity={0.7}
            disabled={selectionMode || !onJumpToReply}
            onPress={() => {
              if (message.reply_to) onJumpToReply?.(message.reply_to.id);
            }}
            style={[
              styles.bubbleReply,
              isMine ? styles.bubbleReplyMineLine : styles.bubbleReplyOtherLine,
            ]}
          >
            <Text
              numberOfLines={2}
              style={[
                styles.bubbleReplyText,
                isMine ? styles.bubbleReplyTextMine : styles.bubbleReplyTextOther,
              ]}
            >
              {message.reply_to.deleted_at ? 'Сообщение удалено' : message.reply_to.body}
            </Text>
          </TouchableOpacity>
        ) : null}
        {recordCard}
        {message.media_url ? (
          <Image
            source={resolveMediaUrl(message.media_url)}
            style={[
              styles.bubbleMedia,
              !hasBody && !message.edited_at ? { marginBottom: 4 } : null,
            ]}
            contentFit="cover"
            cachePolicy="disk"
          />
        ) : null}
        {hasBody ? (
          <Text style={[styles.bubbleBody, isMine && styles.bubbleBodyMine]}>
            {message.body}
          </Text>
        ) : null}
        {isLastInGroup ? (
          <View style={styles.bubbleMeta}>
            {message.edited_at ? (
              <Text
                style={[
                  styles.bubbleEdited,
                  isMine && styles.bubbleEditedMine,
                ]}
              >
                ред.
              </Text>
            ) : null}
            <Text style={[styles.bubbleTime, isMine && styles.bubbleTimeMine]}>
              {formatBubbleTime(message.created_at)}
            </Text>
            {isMine && !isFailed ? (
              <ReadMark status={message._local_status} isRead={isRead} />
            ) : null}
            {isMine && isFailed ? (
              <Icon name="warning-circle" size={12} color="#FCD2D4" />
            ) : null}
          </View>
        ) : null}
      </TouchableOpacity>
      <ReactionsRow
        reactions={message.reactions}
        isMine={isMine}
        meId={meId}
        onPress={(emoji) => onToggleReaction?.(message.id, emoji)}
      />
    </View>
  );
}

function DateDivider({ date }: { date: Date }) {
  return (
    <View style={styles.dateDivider}>
      <View style={styles.dateChip}>
        <Text style={styles.dateChipTxt}>{formatDateLabel(date)}</Text>
      </View>
    </View>
  );
}

function UnreadDivider() {
  return (
    <View style={styles.unreadDividerWrap}>
      <View style={styles.unreadDividerLine} />
      <Text style={styles.unreadDividerTxt}>Непрочитанные сообщения</Text>
      <View style={styles.unreadDividerLine} />
    </View>
  );
}

const SWIPE_REPLY_THRESHOLD = 56;
const SWIPE_REPLY_LIMIT = 90;

/**
 * Telegram-style swipe-to-reply: тащим бабл в сторону (свои — влево, чужие —
 * вправо). Когда переход через threshold — haptic + onReply, бабл пружинит
 * обратно. Активная зона жеста узкая (горизонтальные movement), вертикальный
 * скролл FlatList не блокируется.
 */
function SwipeableMessage({
  children,
  isMine,
  onReply,
}: {
  children: React.ReactNode;
  isMine: boolean;
  onReply: () => void;
}) {
  const tx = useSharedValue(0);
  const triggered = useSharedValue(false);

  const triggerReply = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    onReply();
  }, [onReply]);

  const pan = Gesture.Pan()
    .activeOffsetX(isMine ? [-12, 9999] : [-9999, 12])
    .failOffsetY([-12, 12])
    .onUpdate((e) => {
      const dx = e.translationX;
      if (isMine) {
        tx.value = Math.min(0, Math.max(-SWIPE_REPLY_LIMIT, dx));
      } else {
        tx.value = Math.max(0, Math.min(SWIPE_REPLY_LIMIT, dx));
      }
      if (!triggered.value && Math.abs(tx.value) >= SWIPE_REPLY_THRESHOLD) {
        triggered.value = true;
        runOnJS(triggerReply)();
      }
    })
    .onEnd(() => {
      tx.value = withSpring(0, { damping: 18, stiffness: 220 });
      triggered.value = false;
    });

  const rowStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: tx.value }],
  }));

  const iconStyle = useAnimatedStyle(() => {
    const progress = Math.min(1, Math.abs(tx.value) / SWIPE_REPLY_THRESHOLD);
    return {
      opacity: progress,
      transform: [
        { scale: interpolate(progress, [0, 1], [0.6, 1], Extrapolation.CLAMP) },
      ],
    };
  });

  return (
    <View style={styles.swipeOuter}>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.swipeReplyIcon,
          isMine ? styles.swipeReplyIconMine : styles.swipeReplyIconOther,
          iconStyle,
        ]}
      >
        <Icon name="arrow-clockwise" size={16} color={Colors.royalBlue} />
      </Animated.View>
      <GestureDetector gesture={pan}>
        <Animated.View style={rowStyle}>{children}</Animated.View>
      </GestureDetector>
    </View>
  );
}

function EmptyState({ partner }: { partner: Conversation['partner'] | null }) {
  if (!partner) {
    return (
      <View style={styles.emptyConv}>
        <ActivityIndicator size="small" color={Colors.royalBlue} />
      </View>
    );
  }
  const initials = partner.username.slice(0, 2).toUpperCase();
  return (
    <View style={styles.emptyConv}>
      <View style={styles.emptyAvatar}>
        {partner.avatar_url ? (
          <Image
            source={resolveMediaUrl(partner.avatar_url)}
            style={{ width: 72, height: 72, borderRadius: 36 }}
            cachePolicy="disk"
          />
        ) : (
          <LinearGradient
            colors={[Colors.royalBlue, Colors.periwinkle]}
            style={{
              width: 72,
              height: 72,
              borderRadius: 36,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Text style={styles.emptyAvatarTxt}>{initials}</Text>
          </LinearGradient>
        )}
      </View>
      <Text style={styles.emptyName}>
        {partner.display_name || `@${partner.username}`}
      </Text>
      <Text style={styles.emptyHint}>Это начало вашей беседы</Text>
    </View>
  );
}

export default function ConversationScreen() {
  const params = useLocalSearchParams<{
    conversationId: string;
    attach_record_id?: string;
    attach_title?: string;
    attach_artist?: string;
    attach_year?: string;
    attach_cover?: string;
  }>();
  const { conversationId } = params;
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const me = useAuthStore((s) => s.user);

  const messages = useMessagesStore(
    (s) => s.threads[conversationId ?? ''] ?? EMPTY_MESSAGES
  );
  const conversation = useMessagesStore((s) => {
    const id = conversationId;
    if (!id) return null;
    return (
      s.conversationsPrimary.find((c) => c.id === id) ||
      s.conversationsRequests.find((c) => c.id === id) ||
      null
    );
  });
  const isLoading = useMessagesStore(
    (s) => !!s.isLoadingThread[conversationId ?? '']
  );
  const loadThread = useMessagesStore((s) => s.loadThread);
  const loadMore = useMessagesStore((s) => s.loadMore);
  const sendMessage = useMessagesStore((s) => s.send);
  const markRead = useMessagesStore((s) => s.markRead);
  const retrySend = useMessagesStore((s) => s.retrySend);
  const toggleMute = useMessagesStore((s) => s.toggleMute);
  const clearHistory = useMessagesStore((s) => s.clearHistory);
  const archive = useMessagesStore((s) => s.archive);
  const blockUser = useMessagesStore((s) => s.blockUser);

  const [draft, setDraft] = useState('');
  const [partner, setPartner] = useState<Conversation['partner'] | null>(
    conversation?.partner ?? null
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [presence, setPresence] = useState<PresenceInfo | null>(null);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [attachedRecord, setAttachedRecord] = useState<AttachedRecord | null>(null);
  // Локальное превью выбранного фото до отправки. localUri для немедленного
  // отображения; remoteUrl заполнится после успешного upload; uploading —
  // флаг для блокировки send-кнопки во время загрузки.
  const [pendingMedia, setPendingMedia] = useState<{
    localUri: string;
    remoteUrl: string | null;
    remoteType: string | null;
    uploading: boolean;
  } | null>(null);
  const [partnerTyping, setPartnerTyping] = useState(false);
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [unreadAccum, setUnreadAccum] = useState(0);
  const [menuTarget, setMenuTarget] = useState<{
    message: Message;
    isMine: boolean;
  } | null>(null);
  const [editTarget, setEditTarget] = useState<Message | null>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTypingSentRef = useRef<number>(0);
  const listRef = useRef<FlatList<FeedItem>>(null);
  // ID первого непрочитанного входящего сообщения, перед которым рисуем
  // unread-divider. Фиксируется один раз при входе в тред (на момент, когда
  // unread_count > 0 и сообщения уже подгружены).
  const [unreadFirstMsgId, setUnreadFirstMsgId] = useState<string | null>(null);
  const unreadCapturedRef = useRef(false);
  const isAtBottomRef = useRef<boolean>(true);

  useEffect(() => {
    const showEvt = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvt = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const s = Keyboard.addListener(showEvt, (e) => {
      setKeyboardVisible(true);
      setKeyboardHeight(e.endCoordinates?.height ?? 0);
    });
    const h = Keyboard.addListener(hideEvt, () => {
      setKeyboardVisible(false);
      setKeyboardHeight(0);
    });
    return () => {
      s.remove();
      h.remove();
    };
  }, []);

  // Когда возвращаемся со share-record экрана с params — подхватим выбор
  useEffect(() => {
    if (params.attach_record_id && params.attach_title && params.attach_artist) {
      setAttachedRecord({
        id: params.attach_record_id,
        title: params.attach_title,
        artist: params.attach_artist,
        year: params.attach_year ? Number(params.attach_year) : null,
        cover_image_url: params.attach_cover || null,
        cover_url: null,
      });
      // очистим query чтобы не повторно срабатывало
      router.setParams({
        attach_record_id: '',
        attach_title: '',
        attach_artist: '',
        attach_year: '',
        attach_cover: '',
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.attach_record_id]);

  const selectionMode = selected.size > 0;
  const partnerLastReadAt = conversation?.partner_last_read_at
    ? new Date(conversation.partner_last_read_at).getTime()
    : 0;

  const toggleSelection = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  const handleDeleteSelected = useCallback(() => {
    if (!conversationId || selected.size === 0) return;
    const count = selected.size;
    Alert.alert(
      'Удалить сообщения?',
      `Удалить ${count} ${count === 1 ? 'сообщение' : count < 5 ? 'сообщения' : 'сообщений'} у всех?`,
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Удалить',
          style: 'destructive',
          onPress: async () => {
            const ids = Array.from(selected);
            await Promise.all(
              ids.map((id) =>
                messagesApi.deleteMessage(id).catch(() => null),
              ),
            );
            clearSelection();
            loadThread(conversationId);
          },
        },
      ],
    );
  }, [conversationId, selected, clearSelection, loadThread]);

  useEffect(() => {
    if (conversation?.partner) setPartner(conversation.partner);
  }, [conversation?.partner]);

  useEffect(() => {
    if (!conversationId) return;
    (async () => {
      try {
        const detail = await messagesApi.getConversation(conversationId);
        setPartner(detail.conversation.partner);
        await loadThread(conversationId);
      } catch {
        // молча
      }
    })();
  }, [conversationId, loadThread]);

  useEffect(() => {
    if (!conversationId) return undefined;
    let timer: ReturnType<typeof setInterval> | null = null;
    let appState: AppStateStatus = AppState.currentState;

    const start = () => {
      if (timer) return;
      timer = setInterval(() => loadThread(conversationId), POLL_INTERVAL_MS);
    };
    const stop = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };

    start();
    const sub = AppState.addEventListener('change', (next) => {
      if (appState.match(/inactive|background/) && next === 'active') {
        loadThread(conversationId);
        start();
      } else if (next.match(/inactive|background/)) {
        stop();
      }
      appState = next;
    });

    return () => {
      stop();
      sub.remove();
    };
  }, [conversationId, loadThread]);

  useEffect(() => {
    if (!conversationId || messages.length === 0) return;
    if (!conversation || conversation.unread_count === 0) return;
    markRead(conversationId);
  }, [conversationId, messages.length, conversation, markRead]);

  // Подписка на WS-typing для этого треда
  useEffect(() => {
    if (!conversationId) return undefined;
    const unsub = messagesSocket.subscribe((e) => {
      if (e.type !== 'typing') return;
      if (e.conversation_id !== conversationId) return;
      if (me && e.user_id === me.id) return;
      setPartnerTyping(true);
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => setPartnerTyping(false), 3000);
    });
    return () => {
      unsub();
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, [conversationId, me]);

  const handleTextChange = useCallback(
    (t: string) => {
      setDraft(t);
      if (!conversationId) return;
      const now = Date.now();
      // Дросселим typing до 1 раза в 1.5 секунды
      if (now - lastTypingSentRef.current > 1500) {
        lastTypingSentRef.current = now;
        messagesSocket.sendTyping(conversationId);
      }
    },
    [conversationId],
  );

  // Presence: подгружаем статус собеседника каждые 30с пока экран открыт.
  useEffect(() => {
    if (!partner?.id) return undefined;
    let cancelled = false;
    const refresh = async () => {
      try {
        const p = await messagesApi.getPresence(partner.id);
        if (!cancelled) setPresence(p);
      } catch {
        // тихо
      }
    };
    refresh();
    const t = setInterval(refresh, PRESENCE_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [partner?.id]);

  // Захват unread-границы один раз: когда сообщения подгрузились и unread_count > 0,
  // фиксируем ID первого непрочитанного входящего (= unread_count-й с конца среди
  // входящих) — он становится якорем для divider'а.
  useEffect(() => {
    if (unreadCapturedRef.current) return;
    if (!conversation || conversation.unread_count <= 0) return;
    if (messages.length === 0) return;
    const incoming = messages
      .filter((m) => m.sender_id !== me?.id && !m.id.startsWith('local-'))
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      );
    const need = Math.min(conversation.unread_count, incoming.length);
    if (need === 0) return;
    const first = incoming[incoming.length - need];
    if (first) {
      setUnreadFirstMsgId(first.id);
      unreadCapturedRef.current = true;
    }
  }, [conversation, messages, me?.id]);

  const feed = useMemo(
    () => buildFeed(messages, me?.id ?? null, unreadFirstMsgId),
    [messages, me?.id, unreadFirstMsgId],
  );

  // Sticky-индексы для date-разделителей.
  const stickyHeaderIndices = useMemo(() => {
    const idx: number[] = [];
    feed.forEach((it, i) => {
      if (it.type === 'date') idx.push(i);
    });
    return idx;
  }, [feed]);

  const jumpToMessage = useCallback((messageId: string) => {
    const idx = feed.findIndex(
      (it) => it.type === 'message' && it.message.id === messageId,
    );
    if (idx < 0) return;
    try {
      listRef.current?.scrollToIndex({ index: idx, animated: true, viewPosition: 0.3 });
    } catch {
      // тихо — иногда scrollToIndex кидает, если viewability ещё не готов
    }
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    setHighlightedMessageId(messageId);
    highlightTimerRef.current = setTimeout(() => {
      setHighlightedMessageId(null);
    }, 1500);
  }, [feed]);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    };
  }, []);

  const handleScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
      const distanceFromBottom =
        contentSize.height - (contentOffset.y + layoutMeasurement.height);
      const atBottom = distanceFromBottom < 80;
      isAtBottomRef.current = atBottom;
      if (atBottom) {
        if (showScrollToBottom) setShowScrollToBottom(false);
        if (unreadAccum > 0) setUnreadAccum(0);
      } else if (distanceFromBottom > 240 && !showScrollToBottom) {
        setShowScrollToBottom(true);
      }
    },
    [showScrollToBottom, unreadAccum],
  );

  const scrollToBottom = useCallback(() => {
    listRef.current?.scrollToEnd({ animated: true });
    setShowScrollToBottom(false);
    setUnreadAccum(0);
  }, []);

  // Накапливаем счётчик новых входящих, пока пользователь скроллит вверх.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || !me) return;
    if (last.sender_id === me.id) return;
    if (isAtBottomRef.current) return;
    setUnreadAccum((n) => n + 1);
    // ловим момент прихода нового — без идеала, может посчитать пере-загрузку
    // как «новое»; для надёжности можно хранить lastSeenMessageId, но в рамках
    // фазы 1 этого достаточно.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length]);

  const editMessageAction = useMessagesStore((s) => s.editMessage);

  const handleSend = useCallback(async () => {
    if (!conversationId) return;
    if (editTarget) {
      const text = draft.trim();
      if (!text) return;
      const tgt = editTarget;
      setDraft('');
      setEditTarget(null);
      await editMessageAction(conversationId, tgt.id, text).catch(() => {});
      return;
    }
    if (pendingMedia && (pendingMedia.uploading || !pendingMedia.remoteUrl)) return;
    const text = draft.trim();
    const ar = attachedRecord;
    const media = pendingMedia?.remoteUrl
      ? { url: pendingMedia.remoteUrl, type: pendingMedia.remoteType || 'image' }
      : null;
    if (!text && !ar && !media) return;
    const rt = replyTo?.id ?? null;
    setDraft('');
    setReplyTo(null);
    setAttachedRecord(null);
    setPendingMedia(null);
    await sendMessage(conversationId, text, rt, ar, media);
    setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
  }, [conversationId, draft, replyTo, attachedRecord, pendingMedia, editTarget, sendMessage, editMessageAction]);

  const handlePickMedia = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        toast.error('Нет доступа', 'Разрешите доступ к фото в настройках');
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.9,
        allowsEditing: false,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      const localUri = asset.uri;
      const mime = asset.mimeType || 'image/jpeg';
      const name = asset.fileName || `photo-${Date.now()}.jpg`;
      setPendingMedia({
        localUri,
        remoteUrl: null,
        remoteType: null,
        uploading: true,
      });
      try {
        const up = await messagesApi.uploadMedia(localUri, name, mime);
        setPendingMedia({
          localUri,
          remoteUrl: up.media_url,
          remoteType: up.media_type,
          uploading: false,
        });
      } catch (e: any) {
        setPendingMedia(null);
        const detail = e?.response?.data?.detail;
        toast.error('Не удалось загрузить', detail ? String(detail) : 'Попробуйте позже');
      }
    } catch {
      toast.error('Не удалось открыть галерею', 'Попробуйте позже');
    }
  }, []);

  const handleRetry = useCallback(
    (msg: Message) => {
      if (!conversationId) return;
      retrySend(conversationId, msg.id);
    },
    [conversationId, retrySend]
  );

  const openBubbleMenu = useCallback(
    (m: Message, isMine: boolean) => {
      setMenuTarget({ message: m, isMine });
    },
    [],
  );

  const menuActions = useMemo<MenuAction[]>(() => {
    if (!menuTarget) return [];
    const { message: m, isMine } = menuTarget;
    const hasBody = !!(m.body && m.body.trim().length > 0);
    const canEdit =
      isMine &&
      hasBody &&
      !m.deleted_at &&
      Date.now() - new Date(m.created_at).getTime() < 15 * 60 * 1000;
    const list: MenuAction[] = [
      {
        key: 'reply',
        label: 'Ответить',
        icon: 'arrow-clockwise',
        onPress: () => setReplyTo(m),
      },
    ];
    if (canEdit) {
      list.push({
        key: 'edit',
        label: 'Редактировать',
        icon: 'pencil',
        onPress: () => {
          setEditTarget(m);
          setReplyTo(null);
          setAttachedRecord(null);
          setDraft(m.body || '');
        },
      });
    }
    if (hasBody) {
      list.push({
        key: 'copy',
        label: 'Скопировать',
        icon: 'copy',
        onPress: () => {
          if (m.body) Clipboard.setStringAsync(m.body);
        },
      });
    }
    const isCurrentlyPinned = conversation?.pinned_message?.id === m.id;
    list.push({
      key: 'pin',
      label: isCurrentlyPinned ? 'Открепить в чате' : 'Закрепить в чате',
      icon: 'star',
      onPress: () => {
        if (!conversationId) return;
        if (isCurrentlyPinned) {
          useMessagesStore.getState().unpinMessage(conversationId).catch(() => {});
        } else {
          useMessagesStore.getState().pinMessage(conversationId, m.id).catch(() => {});
        }
      },
    });
    list.push({
      key: 'forward',
      label: 'Переслать',
      icon: 'arrow-right',
      onPress: () => {
        const senderUsername =
          isMine
            ? me?.username
            : partner?.username;
        router.push({
          pathname: '/messages/new' as any,
          params: {
            forward_body: m.body || '',
            forward_record_id: m.attached_record?.id || '',
            forward_from: senderUsername || '',
          },
        });
      },
    });
    list.push({
      key: 'share',
      label: 'Поделиться',
      icon: 'share',
      onPress: () => {
        const text = m.body
          ? m.body
          : m.attached_record
          ? `${m.attached_record.title} — ${cleanArtistName(m.attached_record.artist) || m.attached_record.artist}`
          : '';
        if (text) Share.share({ message: text }).catch(() => {});
      },
    });
    list.push({
      key: 'select',
      label: 'Выделить',
      icon: 'check-circle',
      onPress: () => toggleSelection(m.id),
    });
    list.push({
      key: 'hide',
      label: 'Удалить у себя',
      icon: 'eye-slash',
      destructive: true,
      onPress: () => {
        if (!conversationId) return;
        useMessagesStore
          .getState()
          .hideMessageForMe(conversationId, m.id)
          .catch(() => {});
      },
    });
    if (!isMine) {
      // UGC (App Store 1.2): жалоба именно на сообщение, а не только на
      // собеседника. Без неё модератор может лишь забанить автора, а сам
      // текст остаётся в чате — тейкдауна контента нет.
      list.push({
        key: 'report',
        label: 'Пожаловаться',
        icon: 'warning-circle',
        destructive: true,
        onPress: () => {
          Alert.alert(
            'Пожаловаться на сообщение?',
            'Сообщение будет отправлено на проверку модератору. Мы реагируем на жалобы в течение 24 часов.',
            [
              { text: 'Отмена', style: 'cancel' },
              {
                text: 'Пожаловаться',
                style: 'destructive',
                onPress: async () => {
                  try {
                    await api.reportContent({ target_type: 'message', target_id: m.id });
                    toast.success('Спасибо, жалоба отправлена');
                  } catch {
                    toast.error('Не удалось отправить жалобу');
                  }
                },
              },
            ],
          );
        },
      });
    }
    if (isMine) {
      list.push({
        key: 'delete',
        label: 'Удалить у всех',
        icon: 'trash',
        destructive: true,
        onPress: () => {
          Alert.alert('Удалить сообщение у всех?', 'Удаление будет видно собеседнику.', [
            { text: 'Отмена', style: 'cancel' },
            {
              text: 'Удалить',
              style: 'destructive',
              onPress: async () => {
                try {
                  await messagesApi.deleteMessage(m.id);
                  if (conversationId) loadThread(conversationId);
                } catch {
                  // тихо
                }
              },
            },
          ]);
        },
      });
    }
    return list;
  }, [
    menuTarget,
    conversationId,
    loadThread,
    toggleSelection,
    conversation?.pinned_message?.id,
    router,
    me?.username,
    partner?.username,
  ]);

  const toggleReactionAction = useMessagesStore((s) => s.toggleReaction);

  const handleQuickReact = useCallback(
    (emoji: string) => {
      if (!menuTarget || !conversationId) return;
      toggleReactionAction(conversationId, menuTarget.message.id, emoji).catch(() => {});
    },
    [menuTarget, conversationId, toggleReactionAction],
  );

  const handleToggleReaction = useCallback(
    (messageId: string, emoji: string) => {
      if (!conversationId) return;
      Haptics.selectionAsync().catch(() => {});
      toggleReactionAction(conversationId, messageId, emoji).catch(() => {});
    },
    [conversationId, toggleReactionAction],
  );

  const lastTapRef = useRef<{ id: string; ts: number } | null>(null);
  const handleBubbleTap = useCallback(
    (m: Message) => {
      // RNGH GestureDetector поглощает все касания, поэтому keyboardShouldPersistTaps
      // никогда не срабатывает. Закрываем явно при любом тапе по бабблу.
      Keyboard.dismiss();
      if (selectionMode) {
        toggleSelection(m.id);
        return;
      }
      const now = Date.now();
      const prev = lastTapRef.current;
      if (prev && prev.id === m.id && now - prev.ts < 280) {
        lastTapRef.current = null;
        if (conversationId) {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
          toggleReactionAction(conversationId, m.id, '❤️').catch(() => {});
        }
        return;
      }
      lastTapRef.current = { id: m.id, ts: now };
    },
    [selectionMode, conversationId, toggleSelection, toggleReactionAction],
  );

  const openAttachedRecord = useCallback(
    (recordId: string) => {
      router.push(`/record/${recordId}` as any);
    },
    [router],
  );

  const renderItem: ListRenderItem<FeedItem> = useCallback(
    ({ item }) => {
      if (item.type === 'date') return <DateDivider date={item.date} />;
      if (item.type === 'unread-divider') return <UnreadDivider />;
      const m = item.message;
      const isFailed = m._local_status === 'failed';
      const isRead =
        item.isMine &&
        partnerLastReadAt > 0 &&
        new Date(m.created_at).getTime() <= partnerLastReadAt;
      const isSelected = selected.has(m.id);
      const isHighlighted = highlightedMessageId === m.id;
      const longPressHandler = selectionMode
        ? () => toggleSelection(m.id)
        : () => openBubbleMenu(m, item.isMine);

      const bubble = (
        <MessageBubble
          message={m}
          isMine={item.isMine}
          isLastInGroup={item.isLastInGroup}
          isFirstInGroup={item.isFirstInGroup}
          isRead={isRead}
          isSelected={isSelected}
          isHighlighted={isHighlighted}
          selectionMode={selectionMode}
          meId={me?.id ?? null}
          onLongPress={longPressHandler}
          onPress={() => handleBubbleTap(m)}
          onOpenRecord={openAttachedRecord}
          onJumpToReply={jumpToMessage}
          onToggleReaction={handleToggleReaction}
        />
      );

      const wrapped = (
        <SwipeableMessage
          isMine={item.isMine}
          onReply={() => setReplyTo(m)}
        >
          {bubble}
        </SwipeableMessage>
      );

      if (isFailed && !selectionMode) {
        return (
          <TouchableOpacity activeOpacity={0.8} onPress={() => handleRetry(m)}>
            {wrapped}
            <Text style={styles.failedHint}>Не отправлено — нажмите, чтобы повторить</Text>
          </TouchableOpacity>
        );
      }
      return wrapped;
    },
    [
      handleRetry,
      partnerLastReadAt,
      selected,
      selectionMode,
      openBubbleMenu,
      openAttachedRecord,
      jumpToMessage,
      handleToggleReaction,
      handleBubbleTap,
      highlightedMessageId,
      me?.id,
    ]
  );

  const headerName = useMemo(() => {
    if (!partner) return '';
    return partner.display_name || `@${partner.username}`;
  }, [partner]);

  const partnerInitials = (partner?.username ?? '').slice(0, 2).toUpperCase();
  const canSend =
    !!draft.trim() ||
    !!attachedRecord ||
    !!(pendingMedia && pendingMedia.remoteUrl && !pendingMedia.uploading);
  const isMuted = !!conversation?.muted;

  const setMuteDurationAction = useMessagesStore((s) => s.setMuteDuration);

  const openMuteDurationSheet = useCallback(() => {
    if (!conversationId) return;
    const options = ['1 час', '8 часов', '1 день', 'Навсегда', 'Отмена'];
    const map: Array<'hour' | '8hours' | 'day' | 'forever'> = [
      'hour',
      '8hours',
      'day',
      'forever',
    ];
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: 4, title: 'Отключить уведомления' },
        (i) => {
          if (i < 4) setMuteDurationAction(conversationId, map[i]);
        },
      );
    } else {
      Alert.alert(
        'Отключить уведомления',
        undefined,
        options.slice(0, 4).map((label, i) => ({
          text: label,
          onPress: () => setMuteDurationAction(conversationId, map[i]),
        })),
      );
    }
  }, [conversationId, setMuteDurationAction]);

  const handleMenu = useCallback(() => {
    if (!conversationId || !partner) return;
    const muteLabel = isMuted ? 'Включить уведомления' : 'Отключить уведомления';
    const options = [muteLabel, 'Очистить историю', 'Пожаловаться', `Заблокировать @${partner.username}`, 'Удалить диалог', 'Отмена'];
    const cancel = 5;
    const destructive = [3, 4];

    const exec = (i: number) => {
      if (i === 0) {
        if (isMuted) {
          setMuteDurationAction(conversationId, 'off');
        } else {
          openMuteDurationSheet();
        }
      } else if (i === 1) {
        Alert.alert('Очистить историю?', 'Сообщения будут скрыты у вас, у собеседника останутся.', [
          { text: 'Отмена', style: 'cancel' },
          { text: 'Очистить', style: 'destructive', onPress: () => clearHistory(conversationId) },
        ]);
      } else if (i === 2) {
        // UGC (App Store 1.2): жалоба на собеседника.
        Alert.alert(
          `Пожаловаться на @${partner.username}?`,
          'Жалоба уйдёт модератору. Мы реагируем в течение 24 часов.',
          [
            { text: 'Отмена', style: 'cancel' },
            {
              text: 'Пожаловаться',
              style: 'destructive',
              onPress: async () => {
                try {
                  await api.reportContent({ target_type: 'user', target_id: partner.id });
                  toast.success('Спасибо, жалоба отправлена');
                } catch {
                  toast.error('Не удалось отправить жалобу');
                }
              },
            },
          ],
        );
      } else if (i === 3) {
        Alert.alert(
          `Заблокировать @${partner.username}?`,
          'Вы не сможете обмениваться сообщениями. Диалог исчезнет у вас.',
          [
            { text: 'Отмена', style: 'cancel' },
            {
              text: 'Заблокировать',
              style: 'destructive',
              onPress: async () => {
                await blockUser(partner.id, conversationId);
                router.back();
              },
            },
          ],
        );
      } else if (i === 4) {
        archive(conversationId).then(() => router.back());
      }
    };

    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        { options, cancelButtonIndex: cancel, destructiveButtonIndex: destructive },
        exec,
      );
    } else {
      Alert.alert(`@${partner.username}`, undefined, [
        { text: muteLabel, onPress: () => exec(0) },
        { text: 'Очистить историю', style: 'destructive', onPress: () => exec(1) },
        { text: 'Пожаловаться', onPress: () => exec(2) },
        { text: `Заблокировать @${partner.username}`, style: 'destructive', onPress: () => exec(3) },
        { text: 'Удалить диалог', style: 'destructive', onPress: () => exec(4) },
        { text: 'Отмена', style: 'cancel' },
      ]);
    }
  }, [
    conversationId,
    partner,
    isMuted,
    openMuteDurationSheet,
    setMuteDurationAction,
    clearHistory,
    archive,
    blockUser,
    router,
  ]);

  return (
    <View style={styles.container}>
      {/* Header — обычный, или action-bar при selection */}
      {selectionMode ? (
        <View
          style={[styles.topbar, styles.topbarSelection, { paddingTop: insets.top + 6 }]}
        >
          <TouchableOpacity onPress={clearSelection} style={styles.iconBtn}>
            <Icon name="close" size={20} color={Colors.text} />
          </TouchableOpacity>
          <Text style={styles.selectionCount}>{selected.size}</Text>
          <View style={{ flex: 1 }} />
          <TouchableOpacity onPress={handleDeleteSelected} style={styles.iconBtn}>
            <Icon name="trash" size={20} color="#E5484D" />
          </TouchableOpacity>
        </View>
      ) : (
        <View
          style={[styles.topbar, { paddingTop: insets.top + 6 }]}
        >
          <TouchableOpacity onPress={() => router.back()} style={styles.iconBtn}>
            <Icon name="arrow-left" size={22} color={Colors.text} />
          </TouchableOpacity>
          <TouchableOpacity
            activeOpacity={0.85}
            style={styles.partnerWrap}
            onPress={() => {
              if (partner) router.push(`/user/${partner.username}` as any);
            }}
            disabled={!partner}
          >
            {partner ? (
              <View style={styles.partnerAvatarWrap}>
                {partner.avatar_url ? (
                  <Image
                    source={resolveMediaUrl(partner.avatar_url)}
                    style={styles.partnerAvatarImg}
                    cachePolicy="disk"
                  />
                ) : (
                  <LinearGradient
                    colors={[Colors.royalBlue, Colors.periwinkle]}
                    style={styles.partnerAvatarImg}
                  >
                    <Text style={styles.partnerAvatarTxt}>{partnerInitials}</Text>
                  </LinearGradient>
                )}
              </View>
            ) : (
              <View style={[styles.partnerAvatarWrap, styles.partnerAvatarSkeleton]} />
            )}
            <View style={styles.partnerTextWrap}>
              <Text style={styles.partnerName} numberOfLines={1}>
                {partner ? headerName : 'Загрузка…'}
              </Text>
              {partner && (presence || partnerTyping) ? (
                <View style={styles.partnerStatusRow}>
                  {partnerTyping ? (
                    <Text style={styles.partnerStatusOnline}>печатает…</Text>
                  ) : presence?.online ? (
                    <>
                      <View style={styles.onlineDot} />
                      <Text style={styles.partnerStatusOnline}>в сети</Text>
                    </>
                  ) : (
                    <Text style={styles.partnerStatus}>
                      {formatLastSeen(presence?.last_seen_at ?? null)}
                    </Text>
                  )}
                </View>
              ) : null}
            </View>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={handleMenu}
            style={styles.iconBtn}
            disabled={!partner}
          >
            <Icon name="ellipsis-horizontal" size={20} color={Colors.text} />
          </TouchableOpacity>
        </View>
      )}

      {conversation?.pinned_message ? (
        <TouchableOpacity
          activeOpacity={0.7}
          style={styles.pinnedBanner}
          onPress={() => {
            if (conversation.pinned_message)
              jumpToMessage(conversation.pinned_message.id);
          }}
        >
          <View style={styles.pinnedBannerLine} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.pinnedBannerTitle}>Закреплённое сообщение</Text>
            <Text style={styles.pinnedBannerBody} numberOfLines={1}>
              {conversation.pinned_message.deleted_at
                ? 'Сообщение удалено'
                : conversation.pinned_message.body || ''}
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => {
              if (conversationId)
                useMessagesStore.getState().unpinMessage(conversationId).catch(() => {});
            }}
            style={styles.pinnedBannerClose}
          >
            <Icon name="close" size={16} color={Colors.textMuted} />
          </TouchableOpacity>
        </TouchableOpacity>
      ) : null}

      {/* Ручной keyboard-avoid: KeyboardAvoidingView ненадёжен на new arch +
          edge-to-edge. Поднимаем контент на реальную высоту клавиатуры из
          событий — детерминированно и одинаково на iOS/Android/Expo Go. */}
      <View style={[styles.kbWrap, { paddingBottom: keyboardHeight }]}>
        <View style={styles.listWrap}>
          <FlatList
            ref={listRef}
            data={feed}
            keyExtractor={(item) => item.key}
            renderItem={renderItem}
            contentContainerStyle={feed.length === 0 ? styles.listEmpty : styles.list}
            onContentSizeChange={() => {
              if (isAtBottomRef.current)
                listRef.current?.scrollToEnd({ animated: false });
            }}
            onLayout={() => listRef.current?.scrollToEnd({ animated: false })}
            onScroll={handleScroll}
            scrollEventThrottle={32}
            stickyHeaderIndices={stickyHeaderIndices}
            onEndReachedThreshold={0.1}
            onStartReached={() => conversationId && loadMore(conversationId)}
            onScrollToIndexFailed={({ index }) => {
              setTimeout(() => {
                try {
                  listRef.current?.scrollToIndex({ index, animated: true, viewPosition: 0.3 });
                } catch {
                  // тихо
                }
              }, 200);
            }}
            ListEmptyComponent={isLoading ? null : <EmptyState partner={partner} />}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="on-drag"
          />
          {showScrollToBottom ? (
            <TouchableOpacity
              activeOpacity={0.85}
              onPress={scrollToBottom}
              style={[
                styles.scrollFab,
                { bottom: Spacing.sm + (attachedRecord || replyTo || pendingMedia ? 70 : 0) },
              ]}
            >
              <Icon name="arrow-down" size={20} color={Colors.text} />
              {unreadAccum > 0 ? (
                <View style={styles.scrollFabBadge}>
                  <Text style={styles.scrollFabBadgeTxt}>
                    {unreadAccum > 99 ? '99+' : unreadAccum}
                  </Text>
                </View>
              ) : null}
            </TouchableOpacity>
          ) : null}
        </View>

        {pendingMedia ? (
          <View style={styles.attachBar}>
            <Image
              source={{ uri: pendingMedia.localUri }}
              style={styles.attachCover}
              cachePolicy="memory"
            />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.attachTitle} numberOfLines={1}>
                {pendingMedia.uploading ? 'Загружаем фото…' : 'Фото готово'}
              </Text>
              <Text style={styles.attachSub} numberOfLines={1}>
                {pendingMedia.uploading ? 'Подождите' : 'Можно отправить'}
              </Text>
            </View>
            <TouchableOpacity
              onPress={handleSend}
              disabled={!pendingMedia.remoteUrl || pendingMedia.uploading}
              style={[
                styles.attachSendBtn,
                (!pendingMedia.remoteUrl || pendingMedia.uploading) && styles.sendBtnDisabled,
              ]}
              activeOpacity={0.85}
              accessibilityLabel="Отправить фото"
            >
              {pendingMedia.uploading ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Icon name="arrow-up" size={18} color="#fff" />
              )}
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setPendingMedia(null)}
              style={styles.replyClose}
              accessibilityLabel="Убрать фото"
            >
              <Icon name="close" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        ) : null}

        {attachedRecord ? (
          <View style={styles.attachBar}>
            {attachedRecord.cover_image_url ? (
              <Image
                source={resolveMediaUrl(attachedRecord.cover_image_url)}
                style={styles.attachCover}
                cachePolicy="disk"
              />
            ) : (
              <View style={[styles.attachCover, styles.attachCoverPlaceholder]}>
                <Icon name="disc" size={16} color={Colors.textMuted} />
              </View>
            )}
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.attachTitle} numberOfLines={1}>
                {attachedRecord.title}
              </Text>
              <Text style={styles.attachSub} numberOfLines={1}>
                {cleanArtistName(attachedRecord.artist) || attachedRecord.artist}
                {attachedRecord.year ? ` · ${attachedRecord.year}` : ''}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => setAttachedRecord(null)}
              style={styles.replyClose}
            >
              <Icon name="close" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        ) : null}

        {replyTo ? (
          <View style={styles.replyBar}>
            <View style={styles.replyLine} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.replyTitle}>
                {replyTo.sender_id === me?.id
                  ? 'Ответ себе'
                  : `Ответ ${partner ? `@${partner.username}` : ''}`}
              </Text>
              <Text style={styles.replyBody} numberOfLines={1}>
                {replyTo.deleted_at ? 'Сообщение удалено' : replyTo.body}
              </Text>
            </View>
            <TouchableOpacity onPress={() => setReplyTo(null)} style={styles.replyClose}>
              <Icon name="close" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        ) : null}

        {editTarget ? (
          <View style={styles.replyBar}>
            <View style={[styles.replyLine, { backgroundColor: '#F59E0B' }]} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={[styles.replyTitle, { color: '#F59E0B' }]}>
                Редактирование
              </Text>
              <Text style={styles.replyBody} numberOfLines={1}>
                {editTarget.body || ''}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => {
                setEditTarget(null);
                setDraft('');
              }}
              style={styles.replyClose}
            >
              <Icon name="close" size={16} color={Colors.textMuted} />
            </TouchableOpacity>
          </View>
        ) : null}

        <View
          style={[
            styles.inputBar,
            { paddingBottom: keyboardVisible ? 8 : insets.bottom + 8 },
          ]}
        >
          <TouchableOpacity
            style={styles.attachBtn}
            activeOpacity={0.7}
            onPress={handlePickMedia}
            accessibilityLabel="Прикрепить фото"
          >
            <Icon name="paperclip" size={20} color={Colors.textMuted} />
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.attachBtn}
            activeOpacity={0.7}
            onPress={() => {
              if (!conversationId) return;
              router.push({
                pathname: '/messages/share-record' as any,
                params: {
                  conversationId,
                  partnerUsername: partner?.username || '',
                },
              });
            }}
            accessibilityLabel="Прикрепить пластинку"
          >
            <Icon name="disc" size={20} color={Colors.textMuted} />
          </TouchableOpacity>
          <TextInput
            style={styles.input}
            placeholder="Сообщение"
            placeholderTextColor={Colors.textMuted}
            value={draft}
            onChangeText={handleTextChange}
            multiline
            maxLength={4000}
          />
          <TouchableOpacity
            style={[styles.sendBtn, !canSend && styles.sendBtnDisabled]}
            onPress={handleSend}
            disabled={!canSend}
            activeOpacity={0.85}
          >
            <Icon
              name="arrow-up"
              size={18}
              color={canSend ? '#fff' : Colors.textMuted}
            />
          </TouchableOpacity>
        </View>
      </View>

      <MessageContextMenu
        visible={!!menuTarget}
        isMine={menuTarget?.isMine ?? false}
        bubbleSnapshot={
          menuTarget ? (
            <MessageBubble
              message={menuTarget.message}
              isMine={menuTarget.isMine}
              isLastInGroup
              isFirstInGroup
              isRead={false}
              isSelected={false}
              isHighlighted={false}
              selectionMode={false}
              meId={me?.id ?? null}
              onLongPress={() => {}}
              onPress={() => {}}
              onOpenRecord={openAttachedRecord}
              onJumpToReply={undefined}
              onToggleReaction={undefined}
            />
          ) : null
        }
        actions={menuActions}
        onClose={() => setMenuTarget(null)}
        onReact={handleQuickReact}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  kbWrap: { flex: 1 },

  topbar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
    backgroundColor: Colors.background,
    gap: Spacing.sm,
  },
  topbarSelection: {
    backgroundColor: Colors.surface,
  },
  selectionCount: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.text,
    marginLeft: 4,
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  partnerWrap: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  partnerAvatarWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  partnerAvatarImg: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  partnerAvatarSkeleton: { backgroundColor: Colors.surface },
  partnerAvatarTxt: {
    fontSize: 13,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.3,
  },
  partnerTextWrap: { flex: 1, minWidth: 0 },
  partnerName: { fontSize: ms(15), fontWeight: '600', color: Colors.text },
  partnerStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 1 },
  partnerStatus: { fontSize: ms(11), color: Colors.textMuted },
  partnerStatusOnline: { fontSize: ms(11), color: '#30A46C', fontWeight: '500' },
  onlineDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: '#30A46C',
  },

  listWrap: { flex: 1 },

  /* Pinned message banner под хедером */
  pinnedBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.md,
    paddingVertical: 8,
    backgroundColor: 'rgba(245,158,11,0.08)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(245,158,11,0.2)',
  },
  pinnedBannerLine: {
    width: 3,
    height: 28,
    borderRadius: 2,
    backgroundColor: '#F59E0B',
  },
  pinnedBannerTitle: {
    fontSize: 11,
    fontWeight: '600',
    color: '#F59E0B',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  pinnedBannerBody: { fontSize: ms(13), color: Colors.text, marginTop: 1 },
  pinnedBannerClose: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },
  list: { paddingHorizontal: Spacing.md, paddingTop: Spacing.sm, paddingBottom: Spacing.md },
  listEmpty: { flexGrow: 1, justifyContent: 'center' },

  /* Unread divider */
  unreadDividerWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: Spacing.md,
    gap: Spacing.sm,
  },
  unreadDividerLine: { flex: 1, height: 1, backgroundColor: 'rgba(59,75,245,0.2)' },
  unreadDividerTxt: {
    fontSize: 11,
    fontWeight: '600',
    color: Colors.royalBlue,
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },

  /* Swipe-to-reply */
  swipeOuter: { width: '100%', justifyContent: 'center' },
  swipeReplyIcon: {
    position: 'absolute',
    top: '50%',
    width: 32,
    height: 32,
    borderRadius: 16,
    marginTop: -16,
    backgroundColor: 'rgba(59,75,245,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  swipeReplyIconMine: { right: 8 },
  swipeReplyIconOther: { left: 8 },

  /* Scroll-to-bottom FAB */
  scrollFab: {
    position: 'absolute',
    right: Spacing.md,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  scrollFabBadge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 18,
    height: 18,
    paddingHorizontal: 5,
    borderRadius: 9,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrollFabBadgeTxt: { color: '#fff', fontSize: 10, fontWeight: '700' },

  /* Date divider */
  dateDivider: {
    alignItems: 'center',
    marginVertical: Spacing.md,
  },
  dateChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: 'rgba(154,168,255,0.15)',
  },
  dateChipTxt: {
    fontSize: ms(11),
    fontWeight: '600',
    color: Colors.royalBlue,
    letterSpacing: 0.2,
  },

  /* Bubble */
  bubbleRow: { width: '100%', marginVertical: 1 },
  bubbleRowFirstInGroup: { marginTop: 10 },
  bubbleRowLastInGroup: { marginBottom: 2 },
  bubbleRowMine: { alignItems: 'flex-end' },
  bubbleRowOther: { alignItems: 'flex-start' },
  bubbleRowSelected: {
    backgroundColor: 'rgba(59,75,245,0.06)',
  },
  bubbleRowHighlighted: {
    backgroundColor: 'rgba(59,75,245,0.12)',
    borderRadius: 12,
  },
  bubbleSelected: {
    borderWidth: 2,
    borderColor: Colors.royalBlue,
  },
  bubble: {
    maxWidth: '76%',
    paddingHorizontal: 14,
    paddingTop: 9,
    paddingBottom: 7,
    borderRadius: 20,
  },
  bubbleMine: {
    backgroundColor: Colors.royalBlue,
    borderBottomRightRadius: 4,
  },
  bubbleOther: {
    backgroundColor: Colors.surface,
    borderBottomLeftRadius: 4,
  },
  bubbleDeleted: {
    backgroundColor: Colors.surfaceHover,
    borderStyle: 'dashed',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  bubbleBody: { fontSize: ms(14), color: Colors.text, lineHeight: ms(19) },
  bubbleBodyMine: { color: '#fff' },
  bubbleMedia: {
    width: 240,
    height: 240,
    borderRadius: 12,
    marginBottom: 6,
    backgroundColor: 'rgba(0,0,0,0.04)',
  },
  bubbleDeletedTxt: {
    fontSize: ms(12),
    color: Colors.textMuted,
    fontStyle: 'italic',
  },
  bubbleMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginTop: 2,
    alignSelf: 'flex-end',
  },
  bubbleTime: { fontSize: 10, color: Colors.textMuted },
  bubbleTimeMine: { color: 'rgba(255,255,255,0.75)' },
  bubbleEdited: {
    fontSize: 10,
    color: Colors.textMuted,
    fontStyle: 'italic',
  },
  bubbleEditedMine: { color: 'rgba(255,255,255,0.65)' },

  /* Reactions row под баблом */
  reactionsRow: {
    flexDirection: 'row',
    gap: 4,
    marginTop: 4,
    flexWrap: 'wrap',
  },
  reactionsRowMine: { alignSelf: 'flex-end' },
  reactionsRowOther: { alignSelf: 'flex-start' },
  reactionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  reactionChipMine: {
    backgroundColor: 'rgba(59,75,245,0.12)',
    borderColor: 'rgba(59,75,245,0.3)',
  },
  reactionChipEmoji: { fontSize: 13 },
  reactionChipCount: { fontSize: 11, fontWeight: '600', color: Colors.text },
  reactionChipCountMine: { color: Colors.royalBlue },

  failedHint: {
    fontSize: 11,
    color: '#E5484D',
    textAlign: 'right',
    marginTop: 2,
    marginRight: 4,
  },

  /* Empty state */
  emptyConv: {
    alignItems: 'center',
    paddingHorizontal: Spacing.lg,
    gap: 8,
  },
  emptyAvatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    overflow: 'hidden',
    marginBottom: 4,
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
  },
  emptyAvatarTxt: {
    fontSize: 22,
    fontWeight: '700',
    color: '#fff',
    letterSpacing: 0.5,
  },
  emptyName: { fontSize: ms(16), fontWeight: '600', color: Colors.text },
  emptyHint: { fontSize: ms(13), color: Colors.textMuted },

  /* Attach (record) preview над composer */
  attachBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    backgroundColor: Colors.background,
    gap: Spacing.sm,
  },
  attachCover: {
    width: 36,
    height: 36,
    borderRadius: 6,
    backgroundColor: Colors.surface,
  },
  attachCoverPlaceholder: { alignItems: 'center', justifyContent: 'center' },
  attachTitle: { fontSize: ms(13), fontWeight: '600', color: Colors.text },
  attachSub: { fontSize: ms(11), color: Colors.textMuted, marginTop: 1 },

  /* Attached-record card внутри bubble */
  bubbleRecord: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
    padding: 6,
    borderRadius: 10,
  },
  bubbleRecordMine: { backgroundColor: 'rgba(255,255,255,0.18)' },
  bubbleRecordOther: { backgroundColor: 'rgba(59,75,245,0.08)' },
  bubbleRecordCover: { width: 44, height: 44, borderRadius: 4 },
  bubbleRecordTitle: { fontSize: ms(13), fontWeight: '600' },
  bubbleRecordSub: { fontSize: ms(11), marginTop: 1 },

  /* Reply preview над composer */
  replyBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    backgroundColor: Colors.background,
    gap: Spacing.sm,
  },
  replyLine: {
    width: 3,
    alignSelf: 'stretch',
    borderRadius: 2,
    backgroundColor: Colors.royalBlue,
  },
  replyTitle: { fontSize: ms(12), fontWeight: '600', color: Colors.royalBlue },
  replyBody: { fontSize: ms(12), color: Colors.textMuted, marginTop: 1 },
  replyClose: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: Colors.surface,
  },

  /* Reply preview внутри bubble */
  bubbleReply: {
    flexDirection: 'row',
    alignSelf: 'stretch',
    marginBottom: 6,
    paddingLeft: 8,
    borderLeftWidth: 3,
  },
  bubbleReplyMineLine: { borderLeftColor: 'rgba(255,255,255,0.7)' },
  bubbleReplyOtherLine: { borderLeftColor: Colors.royalBlue },
  bubbleReplyText: { fontSize: ms(12), lineHeight: ms(16) },
  bubbleReplyTextMine: { color: 'rgba(255,255,255,0.85)' },
  bubbleReplyTextOther: { color: Colors.textMuted },

  /* Composer */
  inputBar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    paddingHorizontal: Spacing.md,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
    backgroundColor: Colors.background,
    gap: Spacing.sm,
  },
  attachBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    paddingHorizontal: 14,
    paddingVertical: Platform.OS === 'ios' ? 10 : 6,
    borderRadius: BorderRadius.md,
    backgroundColor: Colors.surface,
    fontSize: ms(14),
    color: Colors.text,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: Colors.surface,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  attachSendBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 4,
  },
});
