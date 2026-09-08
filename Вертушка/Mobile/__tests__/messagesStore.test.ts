/// <reference types="jest" />
/**
 * BUGS A13: инбокс сообщений у нового аккаунта не должен зависать в skeleton.
 *
 * Экран грузит primary и requests параллельно и рисует skeleton по одному
 * флагу isLoadingList. Фиксируем: пустой ответ `[]` завершает загрузку,
 * ошибка тоже, а флаг гаснет только когда завершились ОБА запроса.
 */
import { useMessagesStore } from '@/lib/messagesStore';
import { messagesApi } from '@/lib/messagesApi';

jest.mock('@/lib/messagesApi', () => ({
  messagesApi: {
    listConversations: jest.fn(),
    unreadCount: jest.fn().mockResolvedValue({ primary: 0, requests: 0 }),
  },
}));
jest.mock('@/lib/messagesWs', () => ({
  messagesSocket: {
    subscribe: jest.fn(),
    onConnected: jest.fn(),
    connect: jest.fn(),
    disconnect: jest.fn(),
  },
}));
jest.mock('@/lib/store', () => ({
  useAuthStore: { getState: () => ({ user: { id: 'me' } }) },
}));
jest.mock('@/lib/toast', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}));

const listConversations = messagesApi.listConversations as jest.Mock;

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  useMessagesStore.getState().reset();
  listConversations.mockReset();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('пустой ответ [] по обеим папкам завершает загрузку и открывает пустое состояние', async () => {
  listConversations.mockResolvedValue([]);
  const { loadConversations } = useMessagesStore.getState();

  const pending = Promise.all([loadConversations('primary'), loadConversations('requests')]);
  expect(useMessagesStore.getState().isLoadingList).toBe(true);
  expect(useMessagesStore.getState().listLoadedOnce).toBe(false);

  await pending;

  const s = useMessagesStore.getState();
  expect(s.isLoadingList).toBe(false);
  expect(s.listLoadedOnce).toBe(true);
  expect(s.conversationsPrimary).toEqual([]);
  expect(s.conversationsRequests).toEqual([]);
});

test('флаг загрузки держится, пока не завершились оба параллельных запроса', async () => {
  const primary = deferred<never[]>();
  const requests = deferred<never[]>();
  listConversations.mockImplementation((folder: string) =>
    folder === 'primary' ? primary.promise : requests.promise,
  );
  const { loadConversations } = useMessagesStore.getState();
  const p1 = loadConversations('primary');
  const p2 = loadConversations('requests');

  primary.resolve([]);
  await p1;
  // Раньше здесь флаг уже гас — экран мигал пустым состоянием, пока
  // «Запросы» ещё летели.
  expect(useMessagesStore.getState().isLoadingList).toBe(true);

  requests.resolve([]);
  await p2;
  expect(useMessagesStore.getState().isLoadingList).toBe(false);
  expect(useMessagesStore.getState().listLoadedOnce).toBe(true);
});

test('ошибка сети/404 не оставляет skeleton навсегда и не бросает наружу', async () => {
  listConversations.mockRejectedValue(
    Object.assign(new Error('Request failed with status code 404'), {
      response: { status: 404, data: { detail: 'Not found' } },
    }),
  );
  const { loadConversations } = useMessagesStore.getState();

  await expect(
    Promise.all([loadConversations('primary'), loadConversations('requests')]),
  ).resolves.toBeDefined();

  const s = useMessagesStore.getState();
  expect(s.isLoadingList).toBe(false);
  expect(s.listLoadedOnce).toBe(true);
  expect(s.conversationsPrimary).toEqual([]);
});

test('reset сбрасывает listLoadedOnce — следующий аккаунт снова увидит skeleton до первого ответа', async () => {
  listConversations.mockResolvedValue([]);
  await useMessagesStore.getState().loadConversations('primary');
  expect(useMessagesStore.getState().listLoadedOnce).toBe(true);

  useMessagesStore.getState().reset();
  expect(useMessagesStore.getState().listLoadedOnce).toBe(false);
  expect(useMessagesStore.getState().isLoadingList).toBe(false);
});
