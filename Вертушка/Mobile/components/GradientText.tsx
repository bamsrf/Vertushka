/**
 * Текст с градиентом через MaskedView + LinearGradient
 */
import React from 'react';
import { TextStyle } from 'react-native';
import MaskedView from '@react-native-masked-view/masked-view';
import { LinearGradient } from 'expo-linear-gradient';
import Animated from 'react-native-reanimated';
import { Gradients } from '../constants/theme';

interface GradientTextProps {
  children: React.ReactNode;
  colors?: readonly string[];
  style?: TextStyle | TextStyle[];
  start?: { x: number; y: number };
  end?: { x: number; y: number };
}

export function GradientText({
  children,
  colors = Gradients.blue,
  style,
  start = { x: 0, y: 0 },
  end = { x: 1, y: 0 },
}: GradientTextProps) {
  return (
    <MaskedView
      maskElement={
        <Animated.Text style={style}>{children}</Animated.Text>
      }
    >
      <LinearGradient
        colors={colors as string[]}
        start={start}
        end={end}
      >
        <Animated.Text style={[style, { opacity: 0 }]}>
          {children}
        </Animated.Text>
      </LinearGradient>
    </MaskedView>
  );
}

export default GradientText;
