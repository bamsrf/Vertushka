/**
 * Плейсхолдер поиска в Маркете не должен уезжать вниз.
 *
 * История. В поиске на главной `numberOfLines={1}` поставили с пометкой «на
 * iOS инертен» — это неверно: RN прокидывает проп и в iOS-ветку, где он
 * участвует в ИЗМЕРЕНИИ инпута, и текст встал на ~9pt ниже лупы (PR #241).
 * 16.09.2026 тот же симптом заметили в поиске внутри магазина: там длинный
 * плейсхолдер («Найти в Kultura Record Store…»), а у поля не было явной
 * высоты — положение текста определялось тем, как RN намерил строку.
 *
 * Тест сторожит оба вывода сразу: высота задана явно, а numberOfLines не
 * уходит на iOS.
 */
import { Platform, StyleSheet, TextInput } from 'react-native';
import renderer, { act } from 'react-test-renderer';
import React from 'react';

// expo-blur в jsdom рендерит нативный компонент, которого нет. Подменяем на
// View: тест про геометрию инпута, а не про стекло.
jest.mock('expo-blur', () => {
  const { View } = require('react-native');
  return { BlurView: View };
});
jest.mock('expo-linear-gradient', () => {
  const { View } = require('react-native');
  return { LinearGradient: View };
});

import MarketSearchInput from '../components/market/MarketSearchInput';

/** Рендер под act: без него react-test-renderer размонтирует дерево. */
function inputStyleAndProps(placeholder?: string) {
  let tree!: renderer.ReactTestRenderer;
  act(() => {
    tree = renderer.create(
      <MarketSearchInput value="" onChangeText={() => {}} placeholder={placeholder} />,
    );
  });
  // findAllByType, а не сравнение n.type со строкой: RN-типы host-элементов
  // не включают 'TextInput', и tsc справедливо ругается на невозможное
  // сравнение.
  const node = tree.root.findAllByType(TextInput)[0];
  return { style: StyleSheet.flatten(node.props.style), props: node.props };
}

describe('MarketSearchInput', () => {
  it('задаёт инпуту явную высоту, а не полагается на измерение текста', () => {
    expect(inputStyleAndProps().style.height).toBe('100%');
  });

  it('не ставит lineHeight — на iOS он сдвигает базовую линию', () => {
    expect(inputStyleAndProps().style.lineHeight).toBeUndefined();
  });

  it('на iOS не прокидывает numberOfLines даже с длинным плейсхолдером', () => {
    expect(Platform.OS).toBe('ios');
    const { props } = inputStyleAndProps('Найти в Kultura Record Store…');
    expect(props.numberOfLines).toBeUndefined();
  });
});
