/**
 * WavesBg — «живые» канавки: кольца непрерывно расходятся от центра, как волна
 * от иглы. Одно кольцо уходит за край ровно тогда, когда следующее занимает его
 * место, — поток без пауз и без мигания.
 *
 * Как получается бесшовность. Радиусы идут геометрической прогрессией
 * (r, r·k, r·k², …). Увеличение всей картинки в k раз переводит каждое кольцо
 * ровно на место соседнего, поэтому в конце периода кадр совпадает с начальным
 * — петлю не видно. При равномерных радиусах так не получится (кольцу i нужен
 * свой коэффициент (i+1)/i), и стык приходится прятать гашением — от него мы
 * здесь и ушли.
 *
 * Важно: RN масштабирует View относительно ЕЁ центра. Поэтому слой — квадрат,
 * центр которого выведен в точку истока (по умолчанию правый нижний угол
 * карточки), а кольца нарисованы вокруг нуля вьюбокса. Иначе картинка не только
 * росла бы, но и ехала, и совпадения кадров не было бы.
 *
 * Анимируется только transform → нативный драйвер, JS-поток свободен под
 * скролл грида ачивок.
 */
import { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { M_IVORY } from './palette';

/** Шаг прогрессии. 1.16 — в видимой полосе кольца читаются почти равномерными. */
const RATIO = 1.16;
/** Радиус самого маленького кольца. */
const R0 = 8;
/** Полуразмер слоя: до какого радиуса рисуем кольца. */
const R_MAX = 700;

interface Props {
  /** Прозрачность линий (на тёмном фоне — 0.05..0.12). */
  opacity?: number;
  /** Исток волн в координатах карточки. По умолчанию — правый нижний угол. */
  originLeft?: number | string;
  originTop?: number | string;
  /** Цвет линий. */
  color?: string;
  /** Время, за которое кольцо доходит до места соседнего, мс. */
  duration?: number;
  /** false — статика (скриншоты, «уменьшить движение»). */
  animated?: boolean;
}

export function WavesBg({
  opacity = 0.07,
  originLeft = '100%',
  originTop = '100%',
  color = M_IVORY,
  duration = 2600,
  animated = true,
}: Props) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!animated) return;
    t.setValue(0);
    // Строго линейно: любая easing даёт рывок в момент перезапуска петли.
    const loop = Animated.loop(
      Animated.timing(t, {
        toValue: 1,
        duration,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    loop.start();
    return () => loop.stop();
  }, [animated, duration, t]);

  const circles = useMemo(() => {
    const out = [];
    let r = R0;
    let i = 0;
    while (r < R_MAX) {
      out.push(
        <Circle
          key={i}
          cx={0}
          cy={0}
          r={r}
          fill="none"
          stroke={color}
          strokeOpacity={opacity}
          strokeWidth={1}
        />,
      );
      r *= RATIO;
      i += 1;
    }
    return out;
  }, [color, opacity]);

  const svg = (
    <Svg
      width={R_MAX * 2}
      height={R_MAX * 2}
      viewBox={`${-R_MAX} ${-R_MAX} ${R_MAX * 2} ${R_MAX * 2}`}
    >
      {circles}
    </Svg>
  );

  const layer = [
    styles.layer,
    { left: originLeft as number, top: originTop as number },
  ];

  if (!animated) {
    return (
      <Animated.View style={layer} pointerEvents="none">
        {svg}
      </Animated.View>
    );
  }

  return (
    <Animated.View
      style={[
        layer,
        {
          transform: [
            { scale: t.interpolate({ inputRange: [0, 1], outputRange: [1, RATIO] }) },
          ],
        },
      ]}
      pointerEvents="none"
    >
      {svg}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  layer: {
    position: 'absolute',
    width: R_MAX * 2,
    height: R_MAX * 2,
    // Центр слоя выводим в точку истока — под неё считается scale.
    marginLeft: -R_MAX,
    marginTop: -R_MAX,
  },
});
