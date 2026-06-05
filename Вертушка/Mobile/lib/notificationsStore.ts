/**
 * Zustand store для уведомлений и социальной ленты.
 *
 * Личная лента ("Ты") живёт в БД, считается unreadCount.
 * Социальная лента ("Подписки") — сгенерированная на лету, без unread.
 */
import { create } from 'zustand';
import { api } from './api';
import type { NotificationItem, SocialFeedItem } from './types';

interface NotificationsState {
  unreadCount: number;
  /** Сколько новых уведомлений пришло в push'е пока экран открыт — для «Показать N новых» pill. */
  pendingNew: number;

  // Personal tab
  personalItems: NotificationItem[];
  personalNextCursor: string | null;
  personalLoading: boolean;
  personalRefreshing: boolean;
  personalLoaded: boolean;

  // Social tab
  socialItems: SocialFeedItem[];
  socialNextCursor: string | null;
  socialLoading: boolean;
  socialRefreshing: boolean;
  socialLoaded: boolean;

  fetchUnreadCount: () => Promise<number>;
  loadPersonal: (opts?: { refresh?: boolean }) => Promise<void>;
  loadMorePersonal: () => Promise<void>;
  loadSocial: (opts?: { refresh?: boolean }) => Promise<void>;
  loadMoreSocial: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markManyRead: (ids: string[]) => Promise<void>;
  markAllRead: () => Promise<void>;
  mutatePersonal: (id: string, patch: Partial<NotificationItem>) => void;
  removePersonal: (id: string) => Promise<void>;
  snoozePersonal: (id: string, days: number) => Promise<void>;
  bumpPending: () => void;
  clearPending: () => void;
  reset: () => void;
}

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  unreadCount: 0,
  pendingNew: 0,
  personalItems: [],
  personalNextCursor: null,
  personalLoading: false,
  personalRefreshing: false,
  personalLoaded: false,
  socialItems: [],
  socialNextCursor: null,
  socialLoading: false,
  socialRefreshing: false,
  socialLoaded: false,

  async fetchUnreadCount() {
    try {
      const count = await api.getUnreadNotificationsCount();
      set({ unreadCount: count });
      return count;
    } catch {
      return get().unreadCount;
    }
  },

  async loadPersonal({ refresh = false } = {}) {
    const state = get();
    if (state.personalLoading || state.personalRefreshing) return;
    set(refresh ? { personalRefreshing: true } : { personalLoading: true });
    try {
      const resp = await api.getPersonalNotifications(null, 20);
      set({
        personalItems: resp.items,
        personalNextCursor: resp.next_cursor ?? null,
        unreadCount: resp.unread_count,
        personalLoaded: true,
      });
    } catch {
      // ignore
    } finally {
      set({ personalLoading: false, personalRefreshing: false });
    }
  },

  async loadMorePersonal() {
    const state = get();
    if (state.personalLoading || !state.personalNextCursor) return;
    set({ personalLoading: true });
    try {
      const resp = await api.getPersonalNotifications(state.personalNextCursor, 20);
      set((prev) => ({
        personalItems: [...prev.personalItems, ...resp.items],
        personalNextCursor: resp.next_cursor ?? null,
        unreadCount: resp.unread_count,
      }));
    } catch {
      // ignore
    } finally {
      set({ personalLoading: false });
    }
  },

  async loadSocial({ refresh = false } = {}) {
    const state = get();
    if (state.socialLoading || state.socialRefreshing) return;
    set(refresh ? { socialRefreshing: true } : { socialLoading: true });
    try {
      const resp = await api.getSocialFeed(null, 20);
      set({
        socialItems: resp.items,
        socialNextCursor: resp.next_cursor ?? null,
        socialLoaded: true,
      });
    } catch {
      // ignore
    } finally {
      set({ socialLoading: false, socialRefreshing: false });
    }
  },

  async loadMoreSocial() {
    const state = get();
    if (state.socialLoading || !state.socialNextCursor) return;
    set({ socialLoading: true });
    try {
      const resp = await api.getSocialFeed(state.socialNextCursor, 20);
      set((prev) => ({
        socialItems: [...prev.socialItems, ...resp.items],
        socialNextCursor: resp.next_cursor ?? null,
      }));
    } catch {
      // ignore
    } finally {
      set({ socialLoading: false });
    }
  },

  async markRead(id: string) {
    const state = get();
    const target = state.personalItems.find((it) => it.id === id);
    if (!target || target.read_at) return;
    // Оптимистичный апдейт
    set((prev) => ({
      personalItems: prev.personalItems.map((it) =>
        it.id === id ? { ...it, read_at: new Date().toISOString() } : it,
      ),
      unreadCount: Math.max(0, prev.unreadCount - 1),
    }));
    try {
      const unread = await api.markNotificationRead(id);
      set({ unreadCount: unread });
    } catch {
      // откатываем при ошибке
      set((prev) => ({
        personalItems: prev.personalItems.map((it) =>
          it.id === id ? { ...it, read_at: target.read_at } : it,
        ),
        unreadCount: state.unreadCount,
      }));
    }
  },

  async markManyRead(ids: string[]) {
    // Instagram-паттерн «seen = read»: помечаем оптимистично только реально
    // видимые непрочитанные. Items ниже фолда сюда не попадают.
    const state = get();
    const fresh = ids.filter((id) => {
      const t = state.personalItems.find((it) => it.id === id);
      return t && !t.read_at;
    });
    if (fresh.length === 0) return;
    const now = new Date().toISOString();
    const freshSet = new Set(fresh);
    set((prev) => ({
      personalItems: prev.personalItems.map((it) =>
        freshSet.has(it.id) ? { ...it, read_at: it.read_at ?? now } : it,
      ),
      unreadCount: Math.max(0, prev.unreadCount - fresh.length),
    }));
    try {
      const unread = await api.markNotificationsRead(fresh);
      set({ unreadCount: unread });
    } catch {
      // откатываем при ошибке
      set((prev) => ({
        personalItems: prev.personalItems.map((it) =>
          freshSet.has(it.id) ? { ...it, read_at: null } : it,
        ),
      }));
      await get().fetchUnreadCount();
    }
  },

  async markAllRead() {
    const prevItems = get().personalItems;
    const now = new Date().toISOString();
    set((prev) => ({
      personalItems: prev.personalItems.map((it) => ({ ...it, read_at: it.read_at ?? now })),
      unreadCount: 0,
    }));
    try {
      await api.markAllNotificationsRead();
    } catch {
      set({ personalItems: prevItems });
      await get().fetchUnreadCount();
    }
  },

  mutatePersonal(id, patch) {
    set((prev) => ({
      personalItems: prev.personalItems.map((it) => (it.id === id ? { ...it, ...patch } : it)),
    }));
  },

  async removePersonal(id) {
    const prev = get();
    const target = prev.personalItems.find((it) => it.id === id);
    if (!target) return;
    // Оптимистично убираем из ленты
    set((s) => ({
      personalItems: s.personalItems.filter((it) => it.id !== id),
      unreadCount: target.read_at ? s.unreadCount : Math.max(0, s.unreadCount - 1),
    }));
    try {
      await api.deleteNotification(id);
    } catch {
      // revert при ошибке
      set({ personalItems: prev.personalItems, unreadCount: prev.unreadCount });
    }
  },

  async snoozePersonal(id, days) {
    // Snooze = «не напоминать про эту сущность N дней». Помечаем прочитанной и убираем
    // из ленты оптимистично. На бэкенде запись остаётся, но новые повторы по dedup_key
    // блокируются до snoozed_until.
    const prev = get();
    const target = prev.personalItems.find((it) => it.id === id);
    if (!target) return;
    set((s) => ({
      personalItems: s.personalItems.filter((it) => it.id !== id),
      unreadCount: target.read_at ? s.unreadCount : Math.max(0, s.unreadCount - 1),
    }));
    try {
      await api.snoozeNotification(id, days);
    } catch {
      set({ personalItems: prev.personalItems, unreadCount: prev.unreadCount });
    }
  },

  bumpPending() {
    set((s) => ({ pendingNew: s.pendingNew + 1 }));
  },

  clearPending() {
    set({ pendingNew: 0 });
  },

  reset() {
    set({
      unreadCount: 0,
      pendingNew: 0,
      personalItems: [],
      personalNextCursor: null,
      personalLoading: false,
      personalRefreshing: false,
      personalLoaded: false,
      socialItems: [],
      socialNextCursor: null,
      socialLoading: false,
      socialRefreshing: false,
      socialLoaded: false,
    });
  },
}));
