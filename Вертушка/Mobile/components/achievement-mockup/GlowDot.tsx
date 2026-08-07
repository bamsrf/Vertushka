/**
 * GlowDot — мягкий ореол вокруг маркера прогресса.
 *
 * Почему SVG-градиент, а не View с borderRadius: залитый круг с opacity даёт
 * резкую кромку, и на пульсации она читается как ступенчатое «пиксельное»
 * мигание. Радиальный градиент гаснет к краю плавно — кромки нет вообще.
 */
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

interface Props {
  size: number;
  color: string;
  /** Прозрачность в центре ореола. */
  intensity?: number;
}

export function GlowDot({ size, color, intensity = 0.42 }: Props) {
  // id уникален по цвету: два разных градиента с одним id в react-native-svg
  // склеиваются, и второй маркер получил бы чужой цвет.
  const id = `glow-${color.replace(/[^a-zA-Z0-9]/g, '')}`;
  return (
    <Svg width={size} height={size} viewBox="0 0 100 100">
      <Defs>
        <RadialGradient id={id} cx="50%" cy="50%" r="50%">
          {/* Много промежуточных стопов: на тёмном фоне пологий градиент из
              трёх точек даёт видимые полосы, из восьми — нет. */}
          <Stop offset="0" stopColor={color} stopOpacity={intensity} />
          <Stop offset="0.15" stopColor={color} stopOpacity={intensity * 0.82} />
          <Stop offset="0.3" stopColor={color} stopOpacity={intensity * 0.62} />
          <Stop offset="0.45" stopColor={color} stopOpacity={intensity * 0.43} />
          <Stop offset="0.6" stopColor={color} stopOpacity={intensity * 0.27} />
          <Stop offset="0.75" stopColor={color} stopOpacity={intensity * 0.14} />
          <Stop offset="0.88" stopColor={color} stopOpacity={intensity * 0.05} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      <Circle cx="50" cy="50" r="50" fill={`url(#${id})`} />
    </Svg>
  );
}
