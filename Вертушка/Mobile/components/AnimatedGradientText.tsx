/**
 * Анимированный градиентный текст — плавная смена цветов
 * MaskedView + AnimatedLinearGradient + Reanimated
 */
import React, { useState, useEffect } from 'react';
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
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(1, { duration, easing: Easing.inOut(Easing.ease) }),
      -1,
    );
  }, [duration]);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % presets.length);
    }, duration);
    return () => clearInterval(interval);
  }, [duration]);

  const nextIndex = (currentIndex + 1) % presets.length;
  const fromColors = presets[currentIndex];
  const toColors = presets[nextIndex];

  const animatedProps = useAnimatedProps(() => {
    const c0 = interpolateColor(progress.value, [0, 1], [fromColors[0], toColors[0]]);
    const c1 = interpolateColor(progress.value, [0, 1], [fromColors[1], toColors[1]]);
    const c2 = interpolateColor(progress.value, [0, 1], [fromColors[2], toColors[2]]);
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
        colors={fromColors as unknown as string[]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
      >
        <Text style={[style, { opacity: 0 }]}>{children}</Text>
      </AnimatedLinearGradient>
    </MaskedView>
  );
});

export default AnimatedGradientText;
