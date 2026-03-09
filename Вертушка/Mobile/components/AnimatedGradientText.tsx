/**
 * Анимированный градиентный текст — плавная смена цветов
 * MaskedView + AnimatedLinearGradient + Reanimated
 * Один shared value управляет всей анимацией — без рассинхрона.
 */
import React, { useEffect } from 'react';
import { TextStyle, Text } from 'react-native';
import MaskedView from '@react-native-masked-view/masked-view';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withRepeat,
  withTiming,
  Easing,
  interpolateColor,
} from 'react-native-reanimated';
import { AnimatedGradientPalette } from '../constants/theme';

const AnimatedLinearGradient = Animated.createAnimatedComponent(LinearGradient);

const { presets } = AnimatedGradientPalette;
const PRESET_COUNT = presets.length;

interface AnimatedGradientTextProps {
  children: React.ReactNode;
  style?: TextStyle | TextStyle[];
  duration?: number;
}

export const AnimatedGradientText = React.memo(function AnimatedGradientText({
  children,
  style,
  duration = 3500,
}: AnimatedGradientTextProps) {
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(PRESET_COUNT, {
        duration: duration * PRESET_COUNT,
        easing: Easing.linear,
      }),
      -1,
    );
  }, [duration]);

  const animatedProps = useAnimatedProps(() => {
    const raw = progress.value % PRESET_COUNT;
    const fromIdx = Math.floor(raw) % PRESET_COUNT;
    const toIdx = (fromIdx + 1) % PRESET_COUNT;
    const t = raw - Math.floor(raw);

    const c0 = interpolateColor(t, [0, 1], [presets[fromIdx][0], presets[toIdx][0]]);
    const c1 = interpolateColor(t, [0, 1], [presets[fromIdx][1], presets[toIdx][1]]);
    const c2 = interpolateColor(t, [0, 1], [presets[fromIdx][2], presets[toIdx][2]]);

    return {
      colors: [c0, c1, c2],
    };
  });

  return (
    <MaskedView
      maskElement={<Text style={style}>{children}</Text>}
    >
      <AnimatedLinearGradient
        animatedProps={animatedProps}
        colors={[...presets[0]] as unknown as string[]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
      >
        <Text style={[style, { opacity: 0 }]}>{children}</Text>
      </AnimatedLinearGradient>
    </MaskedView>
  );
});

export default AnimatedGradientText;
