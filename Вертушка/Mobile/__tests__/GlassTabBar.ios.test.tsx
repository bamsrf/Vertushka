/// <reference types="jest" />
/**
 * Snapshot-гейт «iOS-дерево GlassTabBar не меняется».
 *
 * Пресет jest-expo/ios мокает Platform.OS = 'ios'. Снимок снят ДО введения
 * BlurViewCompat (Android-порт, WS5a) — любое расхождение означает, что
 * alias-паттерн П7 нарушен и iOS-ветка изменилась.
 */
import React from 'react';
import { Platform } from 'react-native';
import renderer, { act } from 'react-test-renderer';
import { GlassTabBar } from '@/components/GlassTabBar';

jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 59, bottom: 34, left: 0, right: 0 }),
}));

const routes = [
  { key: 'search-1', name: 'search' },
  { key: 'index-1', name: 'index' },
  { key: 'collection-1', name: 'collection' },
];

const state = {
  index: 1,
  routes,
  routeNames: routes.map((r) => r.name),
  key: 'tab-1',
  type: 'tab',
  stale: false,
  history: [],
  preloadedRouteKeys: [],
};

const descriptors = Object.fromEntries(
  routes.map((r) => [r.key, { options: {}, route: r, navigation: {}, render: () => null }]),
);

const navigation = {
  emit: () => ({ defaultPrevented: false }),
  navigate: () => undefined,
};

describe('GlassTabBar (iOS)', () => {
  it('Platform.OS замокан как ios', () => {
    expect(Platform.OS).toBe('ios');
  });

  it('дерево совпадает со снимком', () => {
    let tree: renderer.ReactTestRenderer | undefined;
    act(() => {
      tree = renderer.create(
        <GlassTabBar
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          state={state as any}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          descriptors={descriptors as any}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          navigation={navigation as any}
          insets={{ top: 59, bottom: 34, left: 0, right: 0 }}
        />,
      );
    });
    expect(tree!.toJSON()).toMatchSnapshot();
  });
});
