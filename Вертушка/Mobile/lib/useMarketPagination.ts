/**
 * useMarketPagination — постраничная подгрузка витрин Маркета.
 *
 * Зачем: и общая витрина, и витрина магазина должны листаться до конца. Раньше
 * общая витрина брала ровно одну страницу (limit=50) и на этом останавливалась,
 * хотя под фильтром «Цветной винил» в наличии сотни карточек — юзер упирался в
 * искусственный потолок. Логика подгрузки одна на оба экрана, чтобы они не
 * разъехались в поведении.
 *
 * Контракт:
 *   • `resetKey` — сериализованные фильтры/запрос. Меняется → список
 *     сбрасывается и грузится с нуля.
 *   • `enabled` — false очищает список и ничего не грузит (например, на общей
 *     витрине, когда фильтры не заданы и вместо сетки показываем карусели).
 *   • `loadMore` — дёргается из onEndReached; сам защищён от повторных вызовов.
 *
 * Гонки: у каждого сброса своё «поколение» (genRef). Ответ от устаревшего
 * поколения молча выбрасывается — иначе результат прошлого фильтра догоняет и
 * подменяет текущий.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import type { MarketSearchItem } from './types';

export const MARKET_PAGE_SIZE = 30;

interface UseMarketPaginationOptions {
  enabled: boolean;
  /** Сериализованные фильтры + запрос. Изменение = полный сброс списка. */
  resetKey: string;
  /** Загрузчик одной страницы. Читается через ref — можно не мемоизировать. */
  fetchPage: (offset: number, limit: number) => Promise<MarketSearchItem[]>;
  pageSize?: number;
}

interface UseMarketPaginationResult {
  items: MarketSearchItem[];
  /** Загрузка первой страницы (показываем спиннер вместо сетки). */
  loading: boolean;
  /** Догрузка следующей страницы (спиннер в футере, сетка на месте). */
  loadingMore: boolean;
  /** Список дочитан до конца — можно показать «это все». */
  reachedEnd: boolean;
  loadMore: () => void;
}

export function useMarketPagination({
  enabled,
  resetKey,
  fetchPage,
  pageSize = MARKET_PAGE_SIZE,
}: UseMarketPaginationOptions): UseMarketPaginationResult {
  const [items, setItems] = useState<MarketSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const fetchRef = useRef(fetchPage);
  fetchRef.current = fetchPage;

  const genRef = useRef(0);
  const offsetRef = useRef(0);
  // Зеркала стейта в ref'ах: loadMore живёт в onEndReached и не должен
  // пересоздаваться на каждую загрузку, иначе FlatList теряет колбэк.
  const busyRef = useRef(false);
  const hasMoreRef = useRef(true);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  useEffect(() => {
    genRef.current += 1;
    const gen = genRef.current;
    offsetRef.current = 0;
    busyRef.current = false;

    if (!enabled) {
      setItems([]);
      setLoading(false);
      setLoadingMore(false);
      setHasMore(true);
      hasMoreRef.current = true;
      return;
    }

    busyRef.current = true;
    setLoading(true);
    setHasMore(true);
    hasMoreRef.current = true;

    fetchRef.current(0, pageSize)
      .then((res) => {
        if (gen !== genRef.current) return;
        setItems(res);
        offsetRef.current = res.length;
        hasMoreRef.current = res.length === pageSize;
        setHasMore(hasMoreRef.current);
      })
      .catch(() => {
        if (gen !== genRef.current) return;
        setItems([]);
        hasMoreRef.current = false;
        setHasMore(false);
      })
      .finally(() => {
        if (gen !== genRef.current) return;
        busyRef.current = false;
        setLoading(false);
      });
  }, [enabled, resetKey, pageSize]);

  const loadMore = useCallback(() => {
    if (!enabledRef.current || busyRef.current || !hasMoreRef.current) return;

    const gen = genRef.current;
    busyRef.current = true;
    setLoadingMore(true);

    fetchRef.current(offsetRef.current, pageSize)
      .then((res) => {
        if (gen !== genRef.current) return;
        // Дедуп по record_id: страховка от пограничных случаев offset-пагинации
        // (склад обновился между страницами → карточка сдвинулась и повторилась).
        // Без него React упадёт на дубликатах ключей в FlatList.
        setItems((cur) => {
          const seen = new Set(cur.map((i) => i.record_id));
          const fresh = res.filter((i) => !seen.has(i.record_id));
          return fresh.length > 0 ? [...cur, ...fresh] : cur;
        });
        // Сдвиг — на размер СЕРВЕРНОЙ страницы, не на число новых после дедупа.
        offsetRef.current += res.length;
        hasMoreRef.current = res.length === pageSize;
        setHasMore(hasMoreRef.current);
      })
      .catch(() => {
        // Сеть моргнула — не считаем список законченным, дадим повторить
        // следующим скроллом.
      })
      .finally(() => {
        busyRef.current = false;
        if (gen === genRef.current) setLoadingMore(false);
      });
  }, [pageSize]);

  return {
    items,
    loading,
    loadingMore,
    reachedEnd: !hasMore && items.length > 0,
    loadMore,
  };
}

export default useMarketPagination;
