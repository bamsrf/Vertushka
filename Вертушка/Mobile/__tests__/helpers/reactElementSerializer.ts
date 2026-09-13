/**
 * Snapshot-сериализатор React-элементов, лежащих в пропсах (например,
 * `ListHeaderComponent` у FlatList).
 *
 * Зачем: pretty-format узнаёт элементы только по `Symbol.for('react.element')`,
 * а React 19 помечает их `react.transitional.element`. Без плагина элемент
 * печатается как обычный объект вместе с `_owner` — ссылкой на Fiber, а это
 * циклический граф на мегабайты («RangeError: Invalid string length»).
 * Печатаем как `<Тип props>`: тип и пропсы — всё, что нужно снимку, сам
 * контент шапки в дереве и так отрендерен как children.
 */
import { format, plugins, type NewPlugin } from 'pretty-format';

const REACT_ELEMENT = Symbol.for('react.transitional.element');

interface ReactElementLike {
  $$typeof: symbol;
  type: string | { displayName?: string; name?: string };
  props: Record<string, unknown>;
}

function isReactElement(value: unknown): value is ReactElementLike {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { $$typeof?: unknown }).$$typeof === REACT_ELEMENT
  );
}

function elementName(type: ReactElementLike['type']): string {
  if (typeof type === 'string') return type;
  return type.displayName || type.name || 'Anonymous';
}

export const reactElementSerializer: NewPlugin = {
  test: isReactElement,
  serialize(value: ReactElementLike, config, indentation, depth, refs, printer) {
    const props = printer(value.props, config, indentation, depth, refs);
    return `<${elementName(value.type)} ${props}>`;
  },
};

/**
 * Дерево react-test-renderer → та же строка, что уходит в снимок. Нужна для
 * сравнения двух рендеров между собой: `toEqual` на JSON-дереве сравнивает
 * функции-пропсы по ссылке (они новые на каждый рендер) и обходит `_owner`.
 */
export function serializeTree(tree: unknown): string {
  return format(tree, {
    plugins: [reactElementSerializer, plugins.ReactTestComponent, plugins.ReactElement],
    printFunctionName: false,
  });
}
