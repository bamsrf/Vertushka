/**
 * Текст с градиентом через MaskedView + LinearGradient
 */
import React from 'react';
import { TextStyle } from 'react-native';
import MaskedView from '@react-native-masked-view/masked-view';
import { LinearGradient } from 'expo-linear-gradient';
import Animated from 'react-native-reanimated';
import { Gradients } from '../constants/theme';
import { MAX_FONT_SCALE } from '../lib/fontScale/maxFontScale';

/**
 * Потолок системного шрифта приходится ставить руками: metro-шим
 * (lib/fontScale/reactNativeShim.js) подменяет только `Text` и `TextInput` из
 * `react-native`, а здесь текст рисует `Animated.Text` из reanimated — мимо
 * шима. Без этого при accessibility-масштабе XXXL «Выбрать» в шапке коллекции
 * вырастал вдвое и разносил ряд тулбара.
 */

interface GradientTextProps {
  children: React.ReactNode;
  // Tuple под контракт expo-linear-gradient 15: минимум два цвета.
  colors?: readonly [string, string, ...string[]];
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
        <Animated.Text style={style} maxFontSizeMultiplier={MAX_FONT_SCALE}>
          {children}
        </Animated.Text>
      }
    >
      <LinearGradient
        colors={colors}
        start={start}
        end={end}
      >
        <Animated.Text style={[style, { opacity: 0 }]} maxFontSizeMultiplier={MAX_FONT_SCALE}>
          {children}
        </Animated.Text>
      </LinearGradient>
    </MaskedView>
  );
}

export default GradientText;
