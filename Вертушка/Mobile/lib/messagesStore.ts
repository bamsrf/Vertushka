/**
 * Zustand-стор личных сообщений. Вынесен из `store.ts` в отдельный файл,
 * чтобы избежать конфликтов авто-линтера `store.ts`.
 *
 * Содержит:
 * - список диалогов primary / requests
 * - сообщения каждого треда с оптимистичным UI и идемпотентностью по client_nonce
 * - openOrCreate — get-or-create диалога с пользователем
 * - refreshUnread — фоновый счётчик непрочитанного
 */
import { create } from 'zustand';
import { messagesApi } from './messagesApi';
import { messagesSocket } from './messagesWs';
import { useAuthStore } from './store';
import { toast } from './toast';
import type {
  Conversation,
  Message,
  MessageFolder,
  MuteDuration,
  UnreadCount,
} from './messagesTypes';

interface MessagesState {
  conversationsPrimary: Conversation[];
  conversationsRequests: Conversation[];
  threads: Record<string, Message[]>;
  hasMoreBefore: Record<string, boolean>;
  unread: UnreadCount;
  isLoadingList: boolean;
  isLoadingThread: Record<string, boolean>;

  loadConversations: (folder: MessageFolder) => Promise<void>;
  loadThread: (conversationId: string) => Promise<void>;
  loadMore: (conversationId: string) => Promise<void>;
  send: (
    conversationId: string,
    body: string,
    replyToMessageId?: string | null,
    attachedRecord?: { id: string; title: string; artist: string; year: number | null; cover_image_url: string | null; cover_url: string | null } | null,
    media?: { url: string; type: string } | null,
  ) => Promise<Message | null>;
  retrySend: (conversationId: string, localId: string) => Promise<void>;
  markRead: (conversationId: string) => Promise<void>;
  refreshUnread: () => Promise<void>;
  openOrCreate: (recipientUserId: string) => Promise<Conversation>;
  acceptRequest: (conversationId: string) => Promise<void>;
  rejectRequest: (conversationId: string) => Promise<void>;
  toggleMute: (conversationId: string) => Promise<void>;
  archive: (conversationId: string) => Promise<void>;
  clearHistory: (conversationId: string) => Promise<void>;
  blockUser: (userId: string, conversationId?: string) => Promise<void>;
  togglePin: (conversationId: string) => Promise<void>;
  toggleReaction: (conversationId: string, messageId: string, emoji: string) => Promise<void>;
  editMessage: (conversationId: string, messageId: string, body: string) => Promise<void>;
  pinMessage: (conversationId: string, messageId: string) => Promise<void>;
  unpinMessage: (conversationId: string) => Promise<void>;
  setMuteDuration: (conversationId: string, duration: MuteDuration) => Promise<void>;
  hideMessageForMe: (conversationId: string, messageId: string) => Promise<void>;
  reset: () => void;
}

function makeMessageNonce(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function upsertConversation(list: Conversation[], conv: Conversation): Conversation[] {
  const idx = list.findIndex((c) => c.id === conv.id);
  if (idx === -1) return [conv, ...list];
  const next = [...list];
  next[idx] = conv;
  return next;
}

export const useMessagesStore = create<MessagesState>((set, get) => ({
  conversationsPrimary: [],
  conversationsRequests: [],
  threads: {},
  hasMoreBefore: {},
  unread: { primary: 0, requests: 0 },
  isLoadingList: false,
  isLoadingThread: {},

  loadConversations: async (folder) => {
    set({ isLoadingList: true });
    try {
      const items = await messagesApi.listConversations(folder);
      if (folder === 'primary') set({ conversationsPrimary: items });
      else set({ conversationsRequests: items });
    } catch (e) {
      console.warn('loadConversations failed', e);
    } finally {
      set({ isLoadingList: false });
    }
  },

  loadThread: async (conversationId) => {
    set((s) => ({ isLoadingThread: { ...s.isLoadingThread, [conversationId]: true } }));
    try {
      const detail = await messagesApi.getConversation(conversationId);
      set((s) => {
        const existing = s.threads[conversationId] ?? [];
        const localPending = existing.filter(
          (m) =>
            m.id.startsWith('local-') &&
            !detail.messages.some(
              (sm) => sm.client_nonce && sm.client_nonce === m.client_nonce
            )
        );
        const serverMessages = detail.messages.map<Message>((m) => {
          const wasLocal = existing.find(
            (e) => e.client_nonce && e.client_nonce === m.client_nonce
          );
          return wasLocal ? { ...m, _local_status: 'sent' } : m;
        });
        const merged = [...serverMessages, ...localPending].sort(
          (a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
        return {
          threads: { ...s.threads, [conversationId]: merged },
          hasMoreBefore: {
            ...s.hasMoreBefore,
            [conversationId]: detail.messages.length >= 50,
          },
          conversationsPrimary:
            detail.conversation.request_status === 'accepted'
              ? upsertConversation(s.conversationsPrimary, detail.conversation)
              : s.conversationsPrimary,
          conversationsRequests:
            detail.conversation.request_status === 'pending'
              ? upsertConversation(s.conversationsRequests, detail.conversation)
              : s.conversationsRequests,
        };
      });
    } catch (e) {
      console.warn('loadThread failed', e);
    } finally {
      set((s) => ({
        isLoadingThread: { ...s.isLoadingThread, [conversationId]: false },
      }));
    }
  },

  loadMore: async (conversationId) => {
    const existing = get().threads[conversationId] ?? [];
    if (existing.length === 0) return;
    const oldest = existing.find((m) => !m.id.startsWith('local-'));
    if (!oldest) return;
    try {
      const older = await messagesApi.listMessages(conversationId, oldest.id, 50);
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: [...older, ...(s.threads[conversationId] ?? [])],
        },
        hasMoreBefore: {
          ...s.hasMoreBefore,
          [conversationId]: older.length >= 50,
        },
      }));
    } catch (e) {
      console.warn('loadMore failed', e);
    }
  },

  send: async (conversationId, body, replyToMessageId, attachedRecord, media) => {
    const text = body.trim();
    if (!text && !attachedRecord && !media) return null;
    const me = useAuthStore.getState().user;
    if (!me) return null;

    const nonce = makeMessageNonce();
    const localId = `local-${nonce}`;
    const existingReplyTarget = replyToMessageId
      ? (get().threads[conversationId] ?? []).find((m) => m.id === replyToMessageId)
      : undefined;
    const optimistic: Message = {
      id: localId,
      conversation_id: conversationId,
      sender_id: me.id,
      body: text,
      created_at: new Date().toISOString(),
      edited_at: null,
      deleted_at: null,
      client_nonce: nonce,
      reply_to_message_id: replyToMessageId ?? null,
      reply_to: existingReplyTarget
        ? {
            id: existingReplyTarget.id,
            sender_id: existingReplyTarget.sender_id,
            body: existingReplyTarget.body,
            deleted_at: existingReplyTarget.deleted_at,
          }
        : null,
      attached_record_id: attachedRecord?.id ?? null,
      attached_record: attachedRecord ?? null,
      media_url: media?.url ?? null,
      media_type: media?.type ?? null,
      _local_status: 'sending',
    };
    set((s) => ({
      threads: {
        ...s.threads,
        [conversationId]: [...(s.threads[conversationId] ?? []), optimistic],
      },
    }));

    try {
      const saved = await messagesApi.sendMessage(
        conversationId,
        text,
        nonce,
        replyToMessageId,
        attachedRecord?.id ?? null,
        media?.url ?? null,
        media?.type ?? null,
      );
      set((s) => {
        const patch = (c: Conversation): Conversation => ({
          ...c,
          last_message_preview: text.slice(0, 160),
          last_message_at: saved.created_at,
          last_message_sender_id: me.id,
        });
        // Ответ в треде = неявное принятие: моя сторона переходит в primary.
        // Сервер делает тот же флип (pending→accepted), здесь — чтобы UI не
        // оставил тред висеть в «Запросах» (иначе он дублируется в обеих папках).
        const reqHit = s.conversationsRequests.find((c) => c.id === conversationId);
        const conversationsRequests = reqHit
          ? s.conversationsRequests.filter((c) => c.id !== conversationId)
          : s.conversationsRequests;
        const conversationsPrimary = reqHit
          ? upsertConversation(s.conversationsPrimary, patch({ ...reqHit, request_status: 'accepted' }))
          : s.conversationsPrimary.map((c) => (c.id === conversationId ? patch(c) : c));
        return {
          threads: {
            ...s.threads,
            [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
              m.id === localId ? { ...saved, _local_status: 'sent' } : m
            ),
          },
          conversationsPrimary,
          conversationsRequests,
        };
      });
      return saved;
    } catch (e: any) {
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
            m.id === localId ? { ...m, _local_status: 'failed' } : m
          ),
        },
      }));
      const detail = e?.response?.data?.detail;
      if (detail) toast.error('Не отправлено', String(detail));
      return null;
    }
  },

  retrySend: async (conversationId, localId) => {
    const list = get().threads[conversationId] ?? [];
    const target = list.find((m) => m.id === localId);
    if (!target || !target.body || !target.client_nonce) return;
    set((s) => ({
      threads: {
        ...s.threads,
        [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
          m.id === localId ? { ...m, _local_status: 'sending' } : m
        ),
      },
    }));
    try {
      const saved = await messagesApi.sendMessage(
        conversationId,
        target.body,
        target.client_nonce
      );
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
            m.id === localId ? { ...saved, _local_status: 'sent' } : m
          ),
        },
      }));
    } catch {
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
            m.id === localId ? { ...m, _local_status: 'failed' } : m
          ),
        },
      }));
    }
  },

  markRead: async (conversationId) => {
    const messages = get().threads[conversationId] ?? [];
    const last = [...messages].reverse().find((m) => !m.id.startsWith('local-'));
    if (!last) return;
    try {
      await messagesApi.markRead(conversationId, last.id);
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === conversationId ? { ...c, unread_count: 0 } : c
        ),
        conversationsRequests: s.conversationsRequests.map((c) =>
          c.id === conversationId ? { ...c, unread_count: 0 } : c
        ),
      }));
      get().refreshUnread();
    } catch (e) {
      console.warn('markRead failed', e);
    }
  },

  refreshUnread: async () => {
    try {
      const u = await messagesApi.getUnreadCount();
      set({ unread: u });
    } catch {
      // тихо — фоновый запрос
    }
  },

  openOrCreate: async (recipientUserId) => {
    const conv = await messagesApi.createConversation(recipientUserId);
    set((s) => {
      const accepted = conv.request_status === 'accepted';
      return {
        conversationsPrimary: accepted
          ? upsertConversation(s.conversationsPrimary, conv)
          : s.conversationsPrimary,
        // Когда я инициатор — бэкенд возвращает accepted. Чистим возможную
        // устаревшую копию из «Запросов», чтобы тред не висел в двух папках.
        conversationsRequests: accepted
          ? s.conversationsRequests.filter((c) => c.id !== conv.id)
          : upsertConversation(s.conversationsRequests, conv),
      };
    });
    return conv;
  },

  acceptRequest: async (conversationId) => {
    try {
      await messagesApi.acceptConversation(conversationId);
      set((s) => {
        const req = s.conversationsRequests.find((c) => c.id === conversationId);
        if (!req) return s;
        const accepted: Conversation = { ...req, request_status: 'accepted' };
        return {
          conversationsRequests: s.conversationsRequests.filter((c) => c.id !== conversationId),
          conversationsPrimary: upsertConversation(s.conversationsPrimary, accepted),
        };
      });
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const status = e?.response?.status;
      if (status === 404) {
        toast.error(
          'Не удалось принять',
          'Сервер ещё не задеплоен с новым эндпоинтом. Обновите бекенд.',
        );
      } else {
        toast.error('Не удалось принять', String(detail || 'Попробуйте позже'));
      }
      throw e;
    }
  },

  rejectRequest: async (conversationId) => {
    try {
      await messagesApi.rejectConversation(conversationId);
      set((s) => ({
        conversationsRequests: s.conversationsRequests.filter((c) => c.id !== conversationId),
      }));
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const status = e?.response?.status;
      if (status === 404) {
        toast.error(
          'Не удалось отклонить',
          'Сервер ещё не задеплоен с новым эндпоинтом.',
        );
      } else {
        toast.error('Не удалось отклонить', String(detail || 'Попробуйте позже'));
      }
      throw e;
    }
  },

  toggleMute: async (conversationId) => {
    try {
      const { muted } = await messagesApi.toggleMute(conversationId);
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === conversationId ? { ...c, muted } : c
        ),
        conversationsRequests: s.conversationsRequests.map((c) =>
          c.id === conversationId ? { ...c, muted } : c
        ),
      }));
    } catch (e: any) {
      toast.error('Не удалось', String(e?.response?.data?.detail || 'Попробуйте позже'));
    }
  },

  archive: async (conversationId) => {
    try {
      await messagesApi.archiveConversation(conversationId);
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.filter((c) => c.id !== conversationId),
        conversationsRequests: s.conversationsRequests.filter((c) => c.id !== conversationId),
      }));
    } catch (e: any) {
      toast.error('Не удалось удалить', String(e?.response?.data?.detail || 'Попробуйте позже'));
      throw e;
    }
  },

  clearHistory: async (conversationId) => {
    try {
      await messagesApi.clearHistory(conversationId);
      set((s) => ({
        threads: { ...s.threads, [conversationId]: [] },
      }));
    } catch (e: any) {
      toast.error('Не удалось очистить', String(e?.response?.data?.detail || 'Попробуйте позже'));
    }
  },

  blockUser: async (userId, conversationId) => {
    try {
      await messagesApi.blockUser(userId);
      if (conversationId) {
        set((s) => ({
          conversationsPrimary: s.conversationsPrimary.filter((c) => c.id !== conversationId),
          conversationsRequests: s.conversationsRequests.filter((c) => c.id !== conversationId),
        }));
      }
    } catch (e: any) {
      toast.error('Не удалось заблокировать', String(e?.response?.data?.detail || 'Попробуйте позже'));
      throw e;
    }
  },

  togglePin: async (conversationId) => {
    try {
      const { pinned } = await messagesApi.togglePin(conversationId);
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === conversationId ? { ...c, pinned } : c
        ),
      }));
    } catch (e: any) {
      toast.error(
        'Не удалось закрепить',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
    }
  },

  setMuteDuration: async (conversationId, duration) => {
    try {
      const { muted, muted_until } = await messagesApi.setMuteDuration(
        conversationId,
        duration,
      );
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === conversationId ? { ...c, muted, muted_until } : c,
        ),
        conversationsRequests: s.conversationsRequests.map((c) =>
          c.id === conversationId ? { ...c, muted, muted_until } : c,
        ),
      }));
    } catch (e: any) {
      toast.error(
        'Не удалось',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
    }
  },

  hideMessageForMe: async (conversationId, messageId) => {
    try {
      await messagesApi.hideMessageForMe(messageId);
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).filter(
            (m) => m.id !== messageId,
          ),
        },
      }));
    } catch (e: any) {
      toast.error(
        'Не удалось скрыть',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
    }
  },

  pinMessage: async (conversationId, messageId) => {
    try {
      await messagesApi.pinMessage(conversationId, messageId);
      // WS conversation.pinned обновит превью; для уверенности ставим оптимистично:
      const list = get().threads[conversationId] ?? [];
      const target = list.find((m) => m.id === messageId);
      if (target) {
        const preview = {
          id: target.id,
          sender_id: target.sender_id,
          body: target.body,
          deleted_at: target.deleted_at,
        };
        set((s) => ({
          conversationsPrimary: s.conversationsPrimary.map((c) =>
            c.id === conversationId ? { ...c, pinned_message: preview } : c,
          ),
          conversationsRequests: s.conversationsRequests.map((c) =>
            c.id === conversationId ? { ...c, pinned_message: preview } : c,
          ),
        }));
      }
    } catch (e: any) {
      toast.error(
        'Не удалось закрепить',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
    }
  },

  unpinMessage: async (conversationId) => {
    try {
      await messagesApi.unpinMessage(conversationId);
      set((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === conversationId ? { ...c, pinned_message: null } : c,
        ),
        conversationsRequests: s.conversationsRequests.map((c) =>
          c.id === conversationId ? { ...c, pinned_message: null } : c,
        ),
      }));
    } catch (e: any) {
      toast.error(
        'Не удалось открепить',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
    }
  },

  editMessage: async (conversationId, messageId, body) => {
    try {
      const updated = await messagesApi.editMessage(messageId, body);
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
            m.id === messageId ? { ...m, body: updated.body, edited_at: updated.edited_at } : m,
          ),
        },
      }));
    } catch (e: any) {
      toast.error(
        'Не удалось отредактировать',
        String(e?.response?.data?.detail || 'Попробуйте позже'),
      );
      throw e;
    }
  },

  toggleReaction: async (conversationId, messageId, emoji) => {
    const me = useAuthStore.getState().user;
    if (!me) return;
    // Optimistic: переключаем реакцию локально, ждём ответ для авторитетного списка
    set((s) => ({
      threads: {
        ...s.threads,
        [conversationId]: (s.threads[conversationId] ?? []).map((m) => {
          if (m.id !== messageId) return m;
          const existing = m.reactions ?? [];
          const hit = existing.find(
            (r) => r.user_id === me.id && r.emoji === emoji,
          );
          const next = hit
            ? existing.filter((r) => !(r.user_id === me.id && r.emoji === emoji))
            : [...existing, { user_id: me.id, emoji }];
          return { ...m, reactions: next };
        }),
      },
    }));
    try {
      const { reactions } = await messagesApi.toggleReaction(messageId, emoji);
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) =>
            m.id === messageId ? { ...m, reactions } : m,
          ),
        },
      }));
    } catch (e: any) {
      // Откатим optimistic
      set((s) => ({
        threads: {
          ...s.threads,
          [conversationId]: (s.threads[conversationId] ?? []).map((m) => {
            if (m.id !== messageId) return m;
            const existing = m.reactions ?? [];
            const hit = existing.find(
              (r) => r.user_id === me.id && r.emoji === emoji,
            );
            const next = hit
              ? existing.filter((r) => !(r.user_id === me.id && r.emoji === emoji))
              : [...existing, { user_id: me.id, emoji }];
            return { ...m, reactions: next };
          }),
        },
      }));
      toast.error('Реакция не сохранилась', String(e?.response?.data?.detail || ''));
    }
  },

  reset: () =>
    set({
      conversationsPrimary: [],
      conversationsRequests: [],
      threads: {},
      hasMoreBefore: {},
      unread: { primary: 0, requests: 0 },
      isLoadingList: false,
      isLoadingThread: {},
    }),
}));


// =========================================================================
// WebSocket realtime integration
// =========================================================================

let _wsSubscribed = false;

/** Подключить WS и подписать стор на server-events. Идемпотентно. */
export function initMessagesRealtime(): void {
  if (_wsSubscribed) return;
  _wsSubscribed = true;

  messagesSocket.subscribe((e) => {
    if (e.type === 'message.new') {
      const me = useAuthStore.getState().user;
      useMessagesStore.setState((s) => {
        const existing = s.threads[e.conversation_id] ?? [];
        // дедупликация по client_nonce (наш optimistic) или по id
        const idx = existing.findIndex(
          (m) =>
            (e.message.client_nonce &&
              m.client_nonce === e.message.client_nonce) ||
            m.id === e.message.id,
        );
        let nextThread = existing;
        if (idx >= 0) {
          nextThread = existing.map((m, i) =>
            i === idx ? { ...e.message, _local_status: 'sent' as const } : m,
          );
        } else {
          nextThread = [...existing, e.message];
        }

        // Обновляем превью в списке диалогов
        const updateList = (list: typeof s.conversationsPrimary) =>
          list.map((c) =>
            c.id === e.conversation_id
              ? {
                  ...c,
                  last_message_preview: e.message.body
                    ? e.message.body.slice(0, 160)
                    : c.last_message_preview,
                  last_message_at: e.message.created_at,
                  last_message_sender_id: e.message.sender_id,
                  unread_count:
                    me && e.message.sender_id !== me.id
                      ? (c.unread_count ?? 0) + 1
                      : c.unread_count,
                }
              : c,
          );

        return {
          threads: { ...s.threads, [e.conversation_id]: nextThread },
          conversationsPrimary: updateList(s.conversationsPrimary),
          conversationsRequests: updateList(s.conversationsRequests),
        };
      });
      useMessagesStore.getState().refreshUnread();
    } else if (e.type === 'message.read') {
      useMessagesStore.setState((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === e.conversation_id
            ? { ...c, partner_last_read_at: e.last_read_at }
            : c,
        ),
      }));
    } else if (e.type === 'message.deleted') {
      useMessagesStore.setState((s) => ({
        threads: {
          ...s.threads,
          [e.conversation_id]: (s.threads[e.conversation_id] ?? []).map((m) =>
            m.id === e.message_id
              ? { ...m, body: null, deleted_at: new Date().toISOString() }
              : m,
          ),
        },
      }));
    } else if (e.type === 'message.reaction') {
      useMessagesStore.setState((s) => ({
        threads: {
          ...s.threads,
          [e.conversation_id]: (s.threads[e.conversation_id] ?? []).map((m) =>
            m.id === e.message_id ? { ...m, reactions: e.reactions } : m,
          ),
        },
      }));
    } else if (e.type === 'message.edited') {
      useMessagesStore.setState((s) => ({
        threads: {
          ...s.threads,
          [e.conversation_id]: (s.threads[e.conversation_id] ?? []).map((m) =>
            m.id === e.message_id
              ? { ...m, body: e.body, edited_at: e.edited_at }
              : m,
          ),
        },
      }));
    } else if (e.type === 'conversation.pinned') {
      useMessagesStore.setState((s) => ({
        conversationsPrimary: s.conversationsPrimary.map((c) =>
          c.id === e.conversation_id
            ? { ...c, pinned_message: e.pinned_message }
            : c,
        ),
        conversationsRequests: s.conversationsRequests.map((c) =>
          c.id === e.conversation_id
            ? { ...c, pinned_message: e.pinned_message }
            : c,
        ),
      }));
    }
    // 'typing' обрабатывается в экране треда через отдельный subscribe
  });

  messagesSocket.connect();
}

/** Отключить WS и сбросить флаг — при logout. */
export function teardownMessagesRealtime(): void {
  if (!_wsSubscribed) return;
  _wsSubscribed = false;
  messagesSocket.disconnect();
}
