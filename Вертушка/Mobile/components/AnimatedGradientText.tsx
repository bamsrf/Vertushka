/**
 * Анимированный градиентный текст — плавная смена цветов
 * MaskedView + AnimatedLinearGradient + Reanimated
 * Один shared value управляет всей анимацией — без рассинхрона.
 */
import React, { useEffect } from 'react';
import { TextStyle, Text, StyleSheet } from 'react-native';
import MaskedView from '@react-native-masked-view/masked-view';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withRepeat,
  withTiming,
  cancelAnimation,
  Easing,
  interpolateColor,
} from 'react-native-reanimated';
import { useIsFocused } from 'expo-router';
import { AnimatedGradientPalette } from '../constants/theme';
import { resolveGradientFrame } from '../lib/gradientFrame';

const AnimatedLinearGradient = Animated.createAnimatedComponent(LinearGradient);

const { presets } = AnimatedGradientPalette;
const PRESET_COUNT = presets.length;

interface AnimatedGradientTextProps {
  children: React.ReactNode;
  style?: TextStyle | TextStyle[];
  duration?: number;
  /**
   * Ужимать в одну строку: `numberOfLines={1}` + `adjustsFontSizeToFit`.
   * Для hero-заголовков рядом с аватаром/кнопкой — на узких экранах
   * (Android 360dp, iPhone mini) «Коллекция» в RubikMonoOne 40pt иначе
   * переносится на две строки и выталкивает аватар. Там, где текст влезает,
   * ничего не меняет.
   */
  fit?: boolean;
}

/** Ниже 60% кегль уже читается как другой шрифт — лучше пусть обрежется. */
const FIT_MIN_FONT_SCALE = 0.6;

export const AnimatedGradientText = React.memo(function AnimatedGradientText({
  children,
  style,
  duration = 3500,
  fit = false,
}: AnimatedGradientTextProps) {
  const progress = useSharedValue(0);

  // Бесконечная анимация крутится только когда экран в фокусе. При уходе на
  // другой таб — cancelAnimation, чтобы не пересобирать нативный градиент
  // каждый кадр впустую (нагрев/разряд). Возврат в фокус перезапускает цикл.
  const focused = useIsFocused();

  useEffect(() => {
    if (!focused) {
      cancelAnimation(progress);
      return;
    }
    progress.value = 0;
    progress.value = withRepeat(
      withTiming(PRESET_COUNT, {
        duration: duration * PRESET_COUNT,
        easing: Easing.linear,
      }),
      -1,
    );
    return () => cancelAnimation(progress);
  }, [duration, focused]);

  const animatedProps = useAnimatedProps(() => {
    // Индексы всегда в диапазоне, прогресс-не-число → нулевой кадр
    // (A7: `presets[NaN]` ронял worklet на UI-потоке). См. lib/gradientFrame.ts.
    const { fromIdx, toIdx, t } = resolveGradientFrame(progress.value, PRESET_COUNT);
    const from = presets[fromIdx] ?? presets[0];
    const to = presets[toIdx] ?? presets[0];

    const c0 = interpolateColor(t, [0, 1], [from[0], to[0]]);
    const c1 = interpolateColor(t, [0, 1], [from[1], to[1]]);
    const c2 = interpolateColor(t, [0, 1], [from[2], to[2]]);

    return {
      // Tuple, а не string[]: expo-linear-gradient 15 требует минимум два
      // цвета на уровне типов (readonly [ColorValue, ColorValue, ...]).
      colors: [c0, c1, c2] as [string, string, string],
    };
  });

  // Маска и невидимый текст-распорка обязаны ужиматься одинаково — пропсы
  // одни на оба. flexShrink нужен самому MaskedView: в row-контейнере без
  // него текст не получает границ и ужиматься ему не во что.
  // `maxFontSizeMultiplier: 1` — только для `fit`-режима, где это название
  // экрана («ПОИСК», «КОЛЛЕКЦИЯ»): оно и так ужимается под ширину, поэтому от
  // системного увеличения не становится крупнее — зато его строчный бокс
  // вырастал, и аватар в том же ряду переставал стоять на одной линии с
  // буквами. Обычный текст (fit не задан) масштабируется как раньше.
  const fitProps = fit
    ? {
        numberOfLines: 1 as const,
        adjustsFontSizeToFit: true,
        minimumFontScale: FIT_MIN_FONT_SCALE,
        maxFontSizeMultiplier: 1,
      }
    : undefined;

  return (
    <MaskedView
      style={fit ? styles.fitContainer : undefined}
      maskElement={<Text style={style} {...fitProps}>{children}</Text>}
    >
      <AnimatedLinearGradient
        animatedProps={animatedProps}
        colors={[...presets[0]] as [string, string, string]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 0 }}
      >
        <Text style={[style, { opacity: 0 }]} {...fitProps}>{children}</Text>
      </AnimatedLinearGradient>
    </MaskedView>
  );
});

const styles = StyleSheet.create({
  fitContainer: {
    flexShrink: 1,
  },
});

export default AnimatedGradientText;
