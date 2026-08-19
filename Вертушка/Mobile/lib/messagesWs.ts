/**
 * WebSocket-клиент DM с реконнектом и экспоненциальным backoff.
 *
 * Подключаемся при наличии access-токена; auth — через query-параметр.
 * Слушатели подписываются на события типа `message.new`, `message.read`,
 * `message.deleted`, `typing`.
 */
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import { api } from './api';
import type { Message, MessageReaction, PinnedMessagePreview } from './messagesTypes';

const TOKEN_KEY = 'auth_token';

/**
 * Сколько соединение должно прожить, чтобы считаться «здоровым» и сбросить
 * backoff к 1с. Сброс прямо в onopen ломал экспоненту: цикл
 * connect→open→close стартовал каждую итерацию заново с 1с и долбил сервер.
 */
const BACKOFF_RESET_AFTER_MS = 15_000;
/** open→close быстрее этого порога = «короткая» сессия (нас отбрасывают). */
const QUICK_CLOSE_MS = 5_000;

const API_BASE_URL = __DEV__
  ? (Constants.expoConfig?.extra?.devApiUrl ?? 'http://localhost:8000/api')
  : 'https://api.vinyl-vertushka.ru/api';

function toWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/, 'ws');
}

export type WsEvent =
  | {
      type: 'message.new';
      conversation_id: string;
      message: Message;
    }
  | {
      type: 'message.read';
      conversation_id: string;
      reader_id: string;
      up_to_message_id: string;
      last_read_at: string | null;
    }
  | {
      type: 'message.deleted';
      conversation_id: string;
      message_id: string;
    }
  | {
      type: 'message.edited';
      conversation_id: string;
      message_id: string;
      body: string;
      edited_at: string | null;
    }
  | {
      type: 'conversation.pinned';
      conversation_id: string;
      pinned_message: PinnedMessagePreview | null;
    }
  | {
      type: 'message.reaction';
      conversation_id: string;
      message_id: string;
      user_id: string;
      emoji: string;
      added: boolean;
      reactions: MessageReaction[];
    }
  | {
      type: 'typing';
      conversation_id: string;
      user_id: string;
    };

type Listener = (e: WsEvent) => void;

class MessagesSocket {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private backoffMs = 1000;
  /** Таймер отложенного сброса backoff — отменяется, если close пришёл раньше. */
  private backoffResetTimer: ReturnType<typeof setTimeout> | null = null;
  /** Подряд идущие «короткие» сессии (open→close < QUICK_CLOSE_MS). */
  private quickCloseCount = 0;
  /** Перед следующим connect надо освежить access-токен. */
  private needsTokenRefresh = false;
  private connectedListeners = new Set<(connected: boolean) => void>();
  private wantConnected = false;

  async connect() {
    this.wantConnected = true;

    // Сервер закрыл прошлую сессию по auth (1008) или дважды подряд отбросил
    // нас сразу после open — почти наверняка протух access-токен. Освежаем
    // через single-flight refresh в api.ts до следующей попытки: иначе весь
    // backoff-цикл ходит к серверу с заведомо мёртвым токеном.
    if (this.needsTokenRefresh) {
      this.needsTokenRefresh = false;
      try {
        await api.ensureFreshAccessToken();
      } catch {
        // не вышло — пробуем со старым токеном, экспонента прикроет
      }
      // Пока ждали refresh, мог случиться disconnect() (logout).
      if (!this.wantConnected) return;
    }

    let token: string | null = null;
    try {
      // SecureStore на iOS требует разлоченный девайс ("User interaction is not
      // allowed"). На локскрине/фоне keychain недоступен — тогда просто откладываем
      // подключение до следующего цикла backoff.
      token = await SecureStore.getItemAsync(TOKEN_KEY);
    } catch {
      this.scheduleReconnect();
      return;
    }
    if (!token) {
      this.scheduleReconnect();
      return;
    }
    const url = `${toWsUrl(API_BASE_URL)}/messages/ws?token=${encodeURIComponent(token)}`;
    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    // Момент открытия именно ЭТОЙ сессии сокета (0 = open не случился):
    // нужен, чтобы отличать «упал коннект» от «сервер отбросил после open».
    let openedAt = 0;
    this.ws.onopen = () => {
      openedAt = Date.now();
      // backoff сбрасываем не сразу, а после 15с жизни соединения — см.
      // BACKOFF_RESET_AFTER_MS.
      if (this.backoffResetTimer) clearTimeout(this.backoffResetTimer);
      this.backoffResetTimer = setTimeout(() => {
        this.backoffResetTimer = null;
        this.backoffMs = 1000;
        this.quickCloseCount = 0;
      }, BACKOFF_RESET_AFTER_MS);
      this.notifyConnected(true);
    };
    this.ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as WsEvent;
        this.listeners.forEach((l) => {
          try {
            l(event);
          } catch {
            /* listener errors don't kill the bus */
          }
        });
      } catch {
        // тихо
      }
    };
    this.ws.onclose = (e) => {
      if (this.backoffResetTimer) {
        clearTimeout(this.backoffResetTimer);
        this.backoffResetTimer = null;
      }
      // 1008 — бэкенд закрывает так WS с невалидным/протухшим токеном
      // (Backend/app/api/messages.py, WS_1008_POLICY_VIOLATION).
      const authClose = (e as { code?: number } | undefined)?.code === 1008;
      if (openedAt > 0 && Date.now() - openedAt < QUICK_CLOSE_MS) {
        this.quickCloseCount += 1;
      } else if (openedAt > 0) {
        this.quickCloseCount = 0;
      }
      // Фолбэк на случай, если код close не доехал (RN его не всегда
      // прокидывает): два быстрых open→close подряд трактуем как auth-проблему.
      if (authClose || this.quickCloseCount >= 2) {
        this.needsTokenRefresh = true;
        this.quickCloseCount = 0;
      }
      this.notifyConnected(false);
      if (this.wantConnected) this.scheduleReconnect();
    };
    this.ws.onerror = () => {
      try {
        this.ws?.close();
      } catch {
        // тихо
      }
    };
  }

  disconnect() {
    this.wantConnected = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.backoffResetTimer) {
      clearTimeout(this.backoffResetTimer);
      this.backoffResetTimer = null;
    }
    this.quickCloseCount = 0;
    this.needsTokenRefresh = false;
    try {
      this.ws?.close();
    } catch {
      // тихо
    }
    this.ws = null;
    this.notifyConnected(false);
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return;
    // Джиттер ×(0.6..1.4): после деплоя/обрыва клиенты не возвращаются
    // синхронной волной на одну и ту же секунду.
    const delay = this.backoffMs * (0.6 + Math.random() * 0.8);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.backoffMs = Math.min(this.backoffMs * 2, 30_000);
      this.connect();
    }, delay);
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  onConnected(fn: (connected: boolean) => void): () => void {
    this.connectedListeners.add(fn);
    fn(this.ws?.readyState === WebSocket.OPEN);
    return () => this.connectedListeners.delete(fn);
  }

  private notifyConnected(connected: boolean) {
    this.connectedListeners.forEach((l) => l(connected));
  }

  isOpen(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  sendTyping(conversationId: string) {
    if (!this.isOpen()) return;
    try {
      this.ws?.send(JSON.stringify({ type: 'typing', conversation_id: conversationId }));
    } catch {
      // тихо
    }
  }
}

export const messagesSocket = new MessagesSocket();
