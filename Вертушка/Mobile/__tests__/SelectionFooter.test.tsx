/// <reference types="jest" />
/**
 * Гейт «панель выделения не разъезжается на узком экране».
 *
 * Регрессия, от которой этот тест защищает: кнопка была строкой
 * (иконка + подпись рядом) со счётчиком внутри каждой подписи —
 * «В коллекцию (1)». На iPhone SE/Mini трём таким кнопкам не хватало ширины,
 * подпись переносилась, кнопка распухала и вылезала за панель.
 *
 * Проверяем то, что этот слом и вызывало: подписи без счётчика, счётчик один
 * на панель, у кнопки нет `flexDirection: 'row'`, высота нигде не зафиксирована.
 */
import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { StyleSheet, Text, TouchableOpacity } from 'react-native';
import { SelectionFooter, type SelectionAction } from '@/components/SelectionFooter';

jest.mock('@/components/ui/Icon', () => ({
  Icon: () => null,
}));

const actions: SelectionAction[] = [
  { key: 'to-collection', icon: 'arrow-forward-circle', label: 'В коллекцию', onPress: () => {} },
  { key: 'to-folder', icon: 'folder-outline', label: 'В папку', onPress: () => {} },
  { key: 'delete', icon: 'trash-outline', label: 'Удалить', onPress: () => {}, destructive: true },
];

function render(selectedCount: number) {
  let tree!: renderer.ReactTestRenderer;
  act(() => {
    tree = renderer.create(
      <SelectionFooter actions={actions} selectedCount={selectedCount} bottom={96} />,
    );
  });
  return tree;
}

/** Все строки текста в дереве. */
function texts(tree: renderer.ReactTestRenderer): string[] {
  return tree.root.findAllByType(Text).map((n) => {
    const children = Array.isArray(n.props.children) ? n.props.children : [n.props.children];
    return children.filter((c: unknown) => typeof c === 'string').join('');
  });
}

/** Плоский стиль кнопки. */
function buttonStyles(tree: renderer.ReactTestRenderer) {
  return tree.root
    .findAllByType(TouchableOpacity)
    .map((n) => StyleSheet.flatten(n.props.style) as Record<string, unknown>);
}

describe('SelectionFooter', () => {
  it('счётчик один на панель, в подписях цифр нет', () => {
    const all = texts(render(3));

    expect(all).toContain('Выбрано: 3');
    expect(all.filter((t) => t.includes('Выбрано')).length).toBe(1);

    for (const label of ['В коллекцию', 'В папку', 'Удалить']) {
      expect(all).toContain(label);
    }
    for (const label of all.filter((t) => !t.includes('Выбрано'))) {
      expect(label).not.toMatch(/\d/);
    }
  });

  it('кнопка — колонка без фиксированной высоты, подпись не более 2 строк', () => {
    const tree = render(1);

    for (const style of buttonStyles(tree)) {
      expect(style.flexDirection).toBeUndefined(); // column по умолчанию
      expect(style.height).toBeUndefined();
      expect(style.flex).toBe(1);
      expect(style.minWidth).toBe(0);
    }

    const labels = tree.root
      .findAllByType(Text)
      .filter((n) => typeof n.props.children === 'string' && !n.props.children.includes('Выбрано'));
    expect(labels.length).toBe(actions.length);
    for (const label of labels) {
      expect(label.props.numberOfLines).toBe(2);
    }
  });

  it('панель тоже без фиксированной высоты — растёт от крупного шрифта', () => {
    const tree = render(1);
    const footer = tree.root.findAllByType(Text)[0].parent!.parent!;
    const style = StyleSheet.flatten(footer.props.style) as Record<string, unknown>;
    expect(style.height).toBeUndefined();
    expect(style.bottom).toBe(96);
  });

  it('при нуле выбранных кнопки выключены и подсказка вместо счётчика', () => {
    const tree = render(0);

    expect(texts(tree)).toContain('Выберите пластинки');
    for (const node of tree.root.findAllByType(TouchableOpacity)) {
      expect(node.props.disabled).toBe(true);
      expect(node.props.accessibilityState).toEqual({ disabled: true });
    }
  });

  it('нажатие зовёт обработчик своего действия', () => {
    const onPress = jest.fn();
    let tree!: renderer.ReactTestRenderer;
    act(() => {
      tree = renderer.create(
        <SelectionFooter
          actions={[{ key: 'x', icon: 'trash-outline', label: 'Удалить', onPress }]}
          selectedCount={2}
          bottom={40}
        />,
      );
    });

    act(() => {
      tree.root.findByType(TouchableOpacity).props.onPress();
    });
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
