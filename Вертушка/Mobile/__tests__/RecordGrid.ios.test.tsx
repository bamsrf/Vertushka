/// <reference types="jest" />
/**
 * Snapshot-гейт «iOS-дерево RecordGrid не меняется».
 *
 * Пресет jest-expo/ios мокает Platform.OS = 'ios'. Снимок снят ДО
 * Android-overdrag'а Маркета (RNGH-обёртка вокруг списка, сдвиг контента):
 * любое расхождение означает, что iOS-ветка изменилась, а этого быть не
 * должно — на iOS новые пропы (`listGesture`, `contentShift`) игнорируются.
 *
 * Пропсы — как у home-view Поиска: пустые данные, шапка, compact-карточки,
 * клиренс под таб-бар и внешний onScroll.
 */
import React from 'react';
import { Platform, Text, View } from 'react-native';
import renderer, { act } from 'react-test-renderer';
import { RecordGrid } from '@/components/RecordGrid';
import { reactElementSerializer, serializeTree } from './helpers/reactElementSerializer';

expect.addSnapshotSerializer(reactElementSerializer);

jest.mock('react-native-safe-area-context', () => ({
  useSafeAreaInsets: () => ({ top: 59, bottom: 34, left: 0, right: 0 }),
}));

function renderGrid(extra: Record<string, unknown> = {}) {
  let tree!: renderer.ReactTestRenderer;
  act(() => {
    tree = renderer.create(
      <RecordGrid
        data={[]}
        showActions
        emptyMessage=""
        cardVariant="compact"
        contentBottomPad={112}
        onScroll={() => undefined}
        ListHeaderComponent={
          <View>
            <Text>Шапка</Text>
          </View>
        }
        {...extra}
      />,
    );
  });
  return tree;
}

describe('RecordGrid (iOS)', () => {
  it('Platform.OS замокан как ios', () => {
    expect(Platform.OS).toBe('ios');
  });

  it('дерево совпадает со снимком', () => {
    expect(renderGrid().toJSON()).toMatchSnapshot();
  });

  it('с переданными listGesture/contentShift дерево идентично', () => {
    // На iOS хук useAndroidOverdrag их не отдаёт, но и переданные вручную
    // они не должны ничего менять: ни GestureDetector, ни обёртки шапки.
    const withProps = renderGrid({
      listGesture: {},
      contentShift: { value: 0 },
      onListLayout: () => undefined,
      onContentSizeChange: () => undefined,
    }).toJSON();
    expect(serializeTree(withProps)).toBe(serializeTree(renderGrid().toJSON()));
  });
});
