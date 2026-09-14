/// <reference types="jest" />
/**
 * Итоговая сумма на экране «Оценка стоимости» не должна сбрасываться в ноль.
 *
 * Баг 14.09.2026: цифры бежали в TextInput, куда текст писался с UI-потока
 * через useAnimatedProps. В React-пропсах его нет, поэтому любой повторный
 * рендер (а компонент живёт в ListHeaderComponent у FlatList и
 * перерисовывается по ходу скролла) возвращал нативному полю `defaultValue`,
 * то есть «~0 ₽». Анимация к тому моменту уже кончилась, переписать текст было
 * некому, и сумма застревала на нуле навсегда.
 */
// Общий мок reanimated (jest.setup) не отдаёт withDelay: эффект компонента
// падал на нём, React сносил поддерево, и тест «доказывал» баг, которого нет.
// Здесь свой минимальный стаб — ровно то, что нужно бегущим цифрам.
jest.mock('react-native-reanimated', () => {
  const { useRef } = require('react');
  const passthrough = (component: unknown) => component;
  const identityEasing = (fn?: unknown) => fn ?? ((t: number) => t);
  return {
    __esModule: true,
    default: { createAnimatedComponent: passthrough },
    createAnimatedComponent: passthrough,
    // Ссылка обязана быть СТАБИЛЬНОЙ, как в настоящем reanimated: она стоит в
    // зависимостях эффекта. Новый объект на каждый рендер запускал эффект по
    // кругу, тот сбрасывал флаг и чистил свой же таймер — счёт не завершался
    // никогда, и тест «видел» баг, которого в приложении нет.
    useSharedValue: (initial: number) => useRef({ value: initial }).current,
    useAnimatedProps: (fn: () => unknown) => fn(),
    useAnimatedStyle: (fn: () => unknown) => fn(),
    withTiming: (value: number) => value,
    withDelay: (_delay: number, value: unknown) => value,
    withRepeat: (value: unknown) => value,
    Easing: {
      out: identityEasing,
      in: identityEasing,
      inOut: identityEasing,
      cubic: (t: number) => t,
      ease: (t: number) => t,
      linear: (t: number) => t,
    },
  };
});

import { act, create } from 'react-test-renderer';
import { TextInput } from 'react-native';

import { formatGroupedWorklet } from '@/lib/format';
import { AnimatedValue } from '@/app/collection/value';

const TOTAL = 1234567;
// Сравниваем с самим форматтером, а не с литералом: разделитель разрядов там
// не обычный пробел, и глазами эту разницу в тесте не видно.
const TOTAL_TEXT = formatGroupedWorklet(TOTAL);

/** Весь отрисованный текст одной строкой: children у Text — это узлы, не строки. */
function renderedText(tree: ReturnType<typeof create>): string {
  return JSON.stringify(tree.toJSON());
}

/**
 * Ждём НАСТОЯЩЕЕ время, а не jest.advanceTimersByTime: под пресетом jest-expo
 * фейковые таймеры до эффекта не доезжают, флаг «досчитали» так и остаётся
 * поднятым в false, и тест врёт про баг, которого нет. Счёт длится 2.3 с,
 * запас небольшой.
 */
const SETTLE_MS = 300 + 2000 + 200;

async function letItSettle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, SETTLE_MS));
  });
}

describe('бегущая сумма', () => {

  it('после анимации число живёт в обычном Text, а не в нативном поле', async () => {
    let tree: ReturnType<typeof create>;
    await act(async () => {
      tree = create(<AnimatedValue targetValue={TOTAL} prefix="~" suffix=" ₽" />);
    });

    await letItSettle();

    // TextInput'а больше нет — сбрасывать нечего.
    expect(tree!.root.findAllByType(TextInput)).toHaveLength(0);
    expect(renderedText(tree!)).toContain(TOTAL_TEXT);
  });

  it('досчитанное число переживает повторные рендеры родителя', async () => {
    let tree: ReturnType<typeof create>;
    await act(async () => {
      tree = create(<AnimatedValue targetValue={TOTAL} prefix="~" suffix=" ₽" />);
    });
    await letItSettle();

    // Ровно то, что делал скролл: родитель перерисовывается теми же пропсами.
    await act(async () => {
      tree!.update(<AnimatedValue targetValue={TOTAL} prefix="~" suffix=" ₽" />);
    });

    expect(renderedText(tree!)).toContain(TOTAL_TEXT);
    expect(renderedText(tree!)).not.toContain('~0 ₽');
  });

  it('пока цифры бегут, поле не подставляет ноль вместо суммы', async () => {
    // defaultValue — то, к чему нативное поле откатывается при перетирании.
    // Ноль там означал бы, что сбой посреди анимации показывает «~0 ₽».
    let tree: ReturnType<typeof create>;
    await act(async () => {
      tree = create(<AnimatedValue targetValue={TOTAL} prefix="~" suffix=" ₽" />);
    });

    const input = tree!.root.findAllByType(TextInput)[0];
    expect(input.props.defaultValue).toContain(TOTAL_TEXT);
  });

  it('новая сумма перезапускает счёт и досчитывает до неё', async () => {
    let tree: ReturnType<typeof create>;
    await act(async () => {
      tree = create(<AnimatedValue targetValue={TOTAL} prefix="~" suffix=" ₽" />);
    });
    await letItSettle();

    await act(async () => {
      tree!.update(<AnimatedValue targetValue={99} prefix="~" suffix=" ₽" />);
    });
    await letItSettle();

    expect(renderedText(tree!)).toContain(formatGroupedWorklet(99));
    // Два полных цикла счёта подряд не влезают в дефолтные 5 с jest.
  }, 15000);
});
