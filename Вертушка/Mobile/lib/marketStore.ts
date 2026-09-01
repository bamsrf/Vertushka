/**
 * Zustand-store для UX-состояний Маркета (раздел в (tabs)/search.tsx).
 *
 * Persisted через AsyncStorage:
 *   - committed — флаг «юзер сейчас в Маркете» (после curtain-commit'а).
 *     Используется для:
 *       a) тинта tab-иконки Search;
 *       b) восстановления режима при reopen экрана — если юзер закрыл
 *          приложение в Маркете, при следующем mount'е (tabs)/search
 *          сразу рендерит Маркет-слой без curtain-анимации.
 *
 *   - hasSeenSwipeHint — флаг, что юзер уже видел pulse-подсказку на язычке
 *     вишлиста (Фича 5 swipe-сравнения). Pulse анимация играет один раз
 *     при первом открытии вишлиста с offers, потом не повторяется.
 *
 *   - hasSeenCurtainHint — флаг, что юзер уже один раз успешно потянул
 *     curtain'у. Используется чтобы первая сессия показывала чуть более
 *     яркий tab-affordance, последующие — компактный.
 *
 * Источник: docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.4 + §2.1.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

import type { MarketStoreData } from '../components/market/MarketSection';

/** Кэш каруселей живёт STORES_TTL_MS, потом mount делает тихий re-fetch. */
export const STORES_TTL_MS = 10 * 60 * 1000;

interface MarketState {
  /**
   * In-memory кэш каруселей магазинов (не persisted): MarketMain монтируется
   * заново при каждом router.push('/market'), кэш даёт мгновенный рендер
   * вместо полного re-fetch'а. Свежесть — по storesFetchedAt + STORES_TTL_MS.
   */
  stores: MarketStoreData[];
  storesFetchedAt: number | null;
  setStores: (stores: MarketStoreData[]) => void;

  /** Юзер сейчас «в Маркете» (после успешного curtain-commit'а). */
  committed: boolean;
  setCommitted: (v: boolean) => void;

  /** Юзер уже видел pulse-анимацию язычка swipe-сравнения. */
  hasSeenSwipeHint: boolean;
  markSwipeHintSeen: () => void;

  /** Юзер уже хоть раз дёргал curtain'у — affordance можно сделать компактнее. */
  hasSeenCurtainHint: boolean;
  markCurtainHintSeen: () => void;

  /** Derived: alias для committed (сохраняем имя для существующих call-site'ов). */
  isInMarket: () => boolean;
}

export const useMarketStore = create<MarketState>()(
  persist(
    (set, get) => ({
      stores: [],
      storesFetchedAt: null,
      setStores: (stores: MarketStoreData[]) =>
        set({ stores, storesFetchedAt: Date.now() }),

      committed: false,
      hasSeenSwipeHint: false,
      hasSeenCurtainHint: false,

      setCommitted: (v: boolean) => {
        if (get().committed !== v) {
          set({ committed: v });
          if (v && !get().hasSeenCurtainHint) set({ hasSeenCurtainHint: true });
        }
      },

      markSwipeHintSeen: () => set({ hasSeenSwipeHint: true }),
      markCurtainHintSeen: () => set({ hasSeenCurtainHint: true }),

      isInMarket: () => get().committed,
    }),
    {
      name: 'vertushka-market',
      storage: createJSONStorage(() => AsyncStorage),
      // v2 — переход с searchScrollY-coupled модели на committed-флаг.
      // Старое поле searchScrollY больше не нужно, migrate его в committed:
      // если scrollY >= 900 → юзер был в Маркете → committed=true.
      version: 2,
      migrate: (persistedState: any, fromVersion) => {
        if (fromVersion < 2 && persistedState) {
          const oldScrollY = Number(persistedState.searchScrollY ?? 0);
          return {
            committed: oldScrollY >= 900,
            hasSeenSwipeHint: !!persistedState.hasSeenSwipeHint,
            hasSeenCurtainHint: false,
          };
        }
        return persistedState as MarketState;
      },
      partialize: (state) => ({
        // committed НЕ сохраняем — при каждом запуске приложения Поиск
        // открывается в базовом режиме, а не в Маркете.
        hasSeenSwipeHint: state.hasSeenSwipeHint,
        hasSeenCurtainHint: state.hasSeenCurtainHint,
      }),
    },
  ),
);
