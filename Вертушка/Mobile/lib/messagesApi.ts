/**
 * API-методы личных сообщений. Вынесено из `api.ts` в отдельный модуль —
 * автоформаттер `api.ts` сносит чужие добавления, поэтому держим здесь.
 *
 * Используем тот же axios-инстанс из `api` (private), но обращаемся к нему
 * через публичный фасад: ApiClient экспортирует только методы, поэтому
 * создаём свой axios c теми же базовыми настройками и общим токеном.
 */
import axios, { AxiosInstance } from 'axios';
import Constants from 'expo-constants';
import * as SecureStore from 'expo-secure-store';
import type {
  Conversation,
  ConversationDetail,
  Message,
  MessageFolder,
  MessageReaction,
  PresenceInfo,
  UnreadCount,
} from './messagesTypes';

const API_BASE_URL = __DEV__
  ? (Constants.expoConfig?.extra?.devApiUrl ?? 'http://localhost:8000/api')
  : 'https://api.vinyl-vertushka.ru/api';

const TOKEN_KEY = 'auth_token';

let _client: AxiosInstance | null = null;

function getClient(): AxiosInstance {
  if (_client) return _client;
  _client = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000,
    headers: { 'Content-Type': 'application/json' },
  });
  _client.interceptors.request.use(async (config) => {
    try {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (token) config.headers.Authorization = `Bearer ${token}`;
    } catch {
      // тихо
    }
    return config;
  });
  return _client;
}

export const messagesApi = {
  async listConversations(folder: MessageFolder = 'primary'): Promise<Conversation[]> {
    const r = await getClient().get('/messages/conversations/', { params: { folder } });
    return r.data;
  },

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    const r = await getClient().get(`/messages/conversations/${conversationId}/`);
    return r.data;
  },

  async listMessages(
    conversationId: string,
    before?: string,
    limit: number = 50,
  ): Promise<Message[]> {
    const r = await getClient().get(
      `/messages/conversations/${conversationId}/messages/`,
      { params: before ? { before, limit } : { limit } },
    );
    return r.data;
  },

  async createConversation(recipientUserId: string): Promise<Conversation> {
    const r = await getClient().post('/messages/conversations/', {
      recipient_user_id: recipientUserId,
    });
    return r.data;
  },

  async sendMessage(
    conversationId: string,
    body: string,
    clientNonce: string,
    replyToMessageId?: string | null,
    attachedRecordId?: string | null,
    mediaUrl?: string | null,
    mediaType?: string | null,
  ): Promise<Message> {
    const r = await getClient().post(
      `/messages/conversations/${conversationId}/messages/`,
      {
        body,
        client_nonce: clientNonce,
        reply_to_message_id: replyToMessageId ?? null,
        attached_record_id: attachedRecordId ?? null,
        media_url: mediaUrl ?? null,
        media_type: mediaType ?? null,
      },
    );
    return r.data;
  },

  async uploadMedia(
    uri: string,
    name: string = 'photo.jpg',
    mimeType: string = 'image/jpeg',
  ): Promise<{ media_url: string; media_type: string }> {
    const form = new FormData();
    // @ts-expect-error — RN FormData принимает {uri, name, type}
    form.append('file', { uri, name, type: mimeType });
    const r = await getClient().post('/messages/upload-media/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    });
    return r.data;
  },

  async markRead(conversationId: string, upToMessageId: string): Promise<void> {
    await getClient().post(`/messages/conversations/${conversationId}/read/`, {
      up_to_message_id: upToMessageId,
    });
  },

  async deleteMessage(messageId: string): Promise<void> {
    await getClient().delete(`/messages/messages/${messageId}/`);
  },

  async editMessage(messageId: string, body: string): Promise<Message> {
    const r = await getClient().patch(`/messages/messages/${messageId}/`, { body });
    return r.data;
  },

  async getUnreadCount(): Promise<UnreadCount> {
    const r = await getClient().get('/messages/unread-count/');
    return r.data;
  },

  async acceptConversation(conversationId: string): Promise<void> {
    await getClient().post(`/messages/conversations/${conversationId}/accept/`);
  },

  async rejectConversation(conversationId: string): Promise<void> {
    await getClient().post(`/messages/conversations/${conversationId}/reject/`);
  },

  async toggleMute(conversationId: string): Promise<{ muted: boolean }> {
    const r = await getClient().post(`/messages/conversations/${conversationId}/mute/`);
    return r.data;
  },

  async setMuteDuration(
    conversationId: string,
    duration: 'off' | 'hour' | '8hours' | 'day' | 'forever',
  ): Promise<{ muted: boolean; muted_until: string | null }> {
    const r = await getClient().post(
      `/messages/conversations/${conversationId}/mute-duration/`,
      { duration },
    );
    return r.data;
  },

  async hideMessageForMe(messageId: string): Promise<void> {
    await getClient().post(`/messages/messages/${messageId}/hide/`);
  },

  async clearHistory(conversationId: string): Promise<void> {
    await getClient().post(`/messages/conversations/${conversationId}/clear/`);
  },

  async archiveConversation(conversationId: string): Promise<void> {
    await getClient().delete(`/messages/conversations/${conversationId}/`);
  },

  async unarchiveConversation(conversationId: string): Promise<void> {
    await getClient().post(`/messages/conversations/${conversationId}/unarchive/`);
  },

  async blockUser(userId: string): Promise<void> {
    await getClient().post(`/messages/block/${userId}/`);
  },

  async unblockUser(userId: string): Promise<void> {
    await getClient().delete(`/messages/block/${userId}/`);
  },

  async listBlocks(): Promise<string[]> {
    const r = await getClient().get('/messages/blocks/');
    return r.data;
  },

  async togglePin(conversationId: string): Promise<{ pinned: boolean }> {
    const r = await getClient().post(`/messages/conversations/${conversationId}/pin/`);
    return r.data;
  },

  async getPresence(userId: string): Promise<PresenceInfo> {
    const r = await getClient().get(`/messages/presence/${userId}/`);
    return r.data;
  },

  async toggleReaction(
    messageId: string,
    emoji: string,
  ): Promise<{ added: boolean; reactions: MessageReaction[] }> {
    const r = await getClient().post(`/messages/messages/${messageId}/reactions/`, {
      emoji,
    });
    return r.data;
  },

  async pinMessage(conversationId: string, messageId: string): Promise<void> {
    await getClient().post(
      `/messages/conversations/${conversationId}/pin-message/${messageId}/`,
    );
  },

  async unpinMessage(conversationId: string): Promise<void> {
    await getClient().delete(
      `/messages/conversations/${conversationId}/pin-message/`,
    );
  },
};
