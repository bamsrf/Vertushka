/**
 * RadarIcon — иконка радара, заменяет звоночек в вишлист-фиче.
 *
 * Геометрия из макета (radar_icon.jpeg): внешнее кольцо r10, внутреннее r6,
 * центр r2.8, симметричный клин ±27° строго вверх.
 * - variant 'on'  → с клином (следим)
 * - variant 'off' → без клина, приглушённое (не следим)
 */
import Svg, { Circle, Path } from 'react-native-svg';

interface RadarIconProps {
  size?: number;
  color?: string;
  variant?: 'on' | 'off';
}

export function RadarIcon({ size = 24, color = '#3B4BF5', variant = 'on' }: RadarIconProps) {
  const on = variant === 'on';
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx={12} cy={12} r={10} stroke={color} strokeWidth={1.5} />
      <Circle cx={12} cy={12} r={6} stroke={color} strokeWidth={1.5} opacity={on ? 1 : 0.6} />
      {on ? <Path d="M12 12 L7.46 3.09 A10 10 0 0 1 16.54 3.09 Z" fill={color} /> : null}
      <Circle cx={12} cy={12} r={2.8} fill={color} />
    </Svg>
  );
}

export default RadarIcon;
