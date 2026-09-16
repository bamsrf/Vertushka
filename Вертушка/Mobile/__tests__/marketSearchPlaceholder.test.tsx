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
  // Контейнер-пилюля: родитель инпута, против высоты которого резолвится
  // процентная высота ребёнка.
  const container = tree.root.findAllByType(TextInput)[0].parent!;
  return {
    style: StyleSheet.flatten(node.props.style),
    props: node.props,
    containerStyle: StyleSheet.flatten(container.props.style),
  };
}

describe('MarketSearchInput', () => {
  it('задаёт инпуту явную высоту, а не полагается на измерение текста', () => {
    expect(inputStyleAndProps().style.height).toBe('100%');
  });

  // Сторож против регресса 16.09.2026. Прежний тест выше проверял только
  // «высота задана явно» — и проходил на сломанном коде: `height: '100%'` ему
  // удовлетворяет буквально, но процент резолвится ТОЛЬКО против определённой
  // высоты родителя. Родитель тогда высоты не имел (был paddingVertical), из-за
  // чего инпут схлопывался в ноль и текст срезало `overflow: 'hidden'`.
  it('процентная высота инпута опирается на числовую высоту контейнера', () => {
    const { style, containerStyle } = inputStyleAndProps();
    if (typeof style.height === 'string' && style.height.endsWith('%')) {
      expect(typeof containerStyle.height).toBe('number');
      expect(containerStyle.height).toBeGreaterThan(0);
    }
  });

  it('контейнер не задаёт высоту вертикальными паддингами вместо height', () => {
    const { containerStyle } = inputStyleAndProps();
    expect(containerStyle.paddingVertical).toBeUndefined();
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
