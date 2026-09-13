/// <reference types="jest" />
/**
 * Snapshot-гейт «iOS-дерево MarketMain не меняется».
 *
 * Пресет jest-expo/ios мокает Platform.OS = 'ios'. Снимок снят ДО
 * Android-overdrag'а Маркета (RNGH-обёртка вокруг списка, сдвиг шапки):
 * любое расхождение означает, что iOS-ветка изменилась, а этого быть не
 * должно — на iOS новые пропы (`listGesture`, `headerShift`) игнорируются.
 *
 * Пропсы — как у слоя Маркета в (tabs)/search: внешний onScroll,
 * pullFraction (рендерит exit-hint), paddingTop под статус-бар. Сеть замокана
 * вечно висящими промисами: магазинов нет, шапка — пустое состояние.
 */
import React from 'react';
import { Platform } from 'react-native';
import renderer, { act } from 'react-test-renderer';
import MarketMain from '@/components/market/MarketMain';
import { reactElementSerializer, serializeTree } from './helpers/reactElementSerializer';

expect.addSnapshotSerializer(reactElementSerializer);

jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 59, bottom: 34, left: 0, right: 0 }),
}));

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), navigate: jest.fn() }),
}));

// Промисы намеренно не резолвятся: снимок фиксирует первый кадр без
// асинхронных setState после act().
jest.mock('@/lib/api', () => ({
  api: {
    getMarketStores: () => new Promise(() => undefined),
    getStoreListings: () => new Promise(() => undefined),
    getMarketFacets: () => new Promise(() => undefined),
    searchMarket: () => new Promise(() => undefined),
  },
  resolveMediaUrl: (u: string) => u,
}));

function renderMarket(extra: Record<string, unknown> = {}) {
  let tree!: renderer.ReactTestRenderer;
  act(() => {
    tree = renderer.create(
      <MarketMain
        onScroll={() => undefined}
        scrollEnabled
        paddingTop={67}
        pullFraction={{ value: 0 } as any}
        {...extra}
      />,
    );
  });
  return tree;
}

describe('MarketMain (iOS)', () => {
  // Debounce поиска и батчинг VirtualizedList живут на setTimeout — без
  // фейковых таймеров они стреляют после teardown'а окружения.
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  it('Platform.OS замокан как ios', () => {
    expect(Platform.OS).toBe('ios');
  });

  it('дерево совпадает со снимком', () => {
    expect(renderMarket().toJSON()).toMatchSnapshot();
  });

  it('с переданными listGesture/headerShift дерево идентично', () => {
    // На iOS хук useAndroidOverdrag их не отдаёт, но и переданные вручную
    // они не должны ничего менять: ни GestureDetector, ни обёртки шапки.
    const withProps = renderMarket({
      listGesture: {},
      headerShift: { value: 0 },
      onListLayout: () => undefined,
      onContentSizeChange: () => undefined,
    }).toJSON();
    expect(serializeTree(withProps)).toBe(serializeTree(renderMarket().toJSON()));
  });
});
