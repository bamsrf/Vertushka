/**
 * BlurViewCompat — платформенный alias для expo-blur (П7 из ANDROID_PORT_PLAN).
 *
 * iOS: ровно `BlurView` из expo-blur, без обёрток — дерево байт-в-байт прежнее.
 * Android: `AndroidGlass` — полупрозрачный `View` по `tint` + тонкий градиент
 * у верхней кромки, чтобы «стекло» читалось на любом фоне. `intensity`
 * (1–100) масштабирует непрозрачность подложки. Принимает полный
 * `BlurViewProps`, `style` и `children` пробрасываются как есть.
 *
 * `@react-native-community/blur` намеренно не подключаем (решение Q4).
 */
import type { ComponentType } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import { BlurView, type BlurTint, type BlurViewProps } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';

interface GlassRecipe {
  rgb: string;
  /** Непрозрачность подложки при intensity=100 */
  maxAlpha: number;
  edge: [string, string];
}

const RECIPES: Record<'light' | 'dark' | 'default', GlassRecipe> = {
  light: {
    rgb: '250, 251, 255',
    maxAlpha: 0.92,
    edge: ['rgba(255,255,255,0.35)', 'rgba(255,255,255,0)'],
  },
  dark: {
    rgb: '14, 7, 38',
    maxAlpha: 0.88,
    edge: ['rgba(255,255,255,0.10)', 'rgba(255,255,255,0)'],
  },
  default: {
    rgb: '128, 128, 136',
    maxAlpha: 0.80,
    edge: ['rgba(255,255,255,0.18)', 'rgba(255,255,255,0)'],
  },
};

function pickRecipe(tint: BlurTint | undefined): GlassRecipe {
  if (!tint || tint === 'default') return RECIPES.default;
  if (tint.includes('dark')) return RECIPES.dark;
  return RECIPES.light;
}

function clampIntensity(intensity: number | undefined): number {
  if (intensity == null || Number.isNaN(intensity)) return 50;
  return Math.min(100, Math.max(1, intensity));
}

function AndroidGlass({
  tint,
  intensity,
  style,
  children,
  blurTarget: _blurTarget,
  blurReductionFactor: _blurReductionFactor,
  experimentalBlurMethod: _experimentalBlurMethod,
  blurMethod: _blurMethod,
  ...viewProps
}: BlurViewProps) {
  const recipe = pickRecipe(tint);
  const alpha = recipe.maxAlpha * (0.25 + 0.75 * (clampIntensity(intensity) / 100));
  const backgroundColor = `rgba(${recipe.rgb}, ${alpha.toFixed(3)})`;

  return (
    <View {...viewProps} style={[{ backgroundColor }, style]}>
      <LinearGradient
        pointerEvents="none"
        colors={recipe.edge}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={styles.edge}
      />
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  edge: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: 1.5,
  },
});

export const BlurViewCompat: ComponentType<BlurViewProps> =
  Platform.OS === 'ios' ? BlurView : AndroidGlass;

export type { BlurViewProps } from 'expo-blur';
