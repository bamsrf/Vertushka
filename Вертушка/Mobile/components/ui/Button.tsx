/**
 * Кнопка — Blue Gradient Edition
 */
import React from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors, Typography, ComponentSizes, Spacing } from '../../constants/theme';

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  size?: 'default' | 'small';
  disabled?: boolean;
  loading?: boolean;
  fullWidth?: boolean;
  style?: ViewStyle;
  textStyle?: TextStyle;
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  size = 'default',
  disabled = false,
  loading = false,
  fullWidth = false,
  style,
  textStyle,
}: ButtonProps) {
  const isDisabled = disabled || loading;

  const content = loading ? (
    <ActivityIndicator
      color={variant === 'primary' ? Colors.background : Colors.royalBlue}
      size="small"
    />
  ) : (
    <Text
      style={[
        styles.text,
        styles[`${variant}Text`],
        size === 'small' && styles.smallText,
        isDisabled && styles.disabledText,
        textStyle,
      ]}
    >
      {title}
    </Text>
  );

  if (variant === 'primary') {
    return (
      <TouchableOpacity
        onPress={onPress}
        disabled={isDisabled}
        activeOpacity={0.85}
        style={[
          fullWidth && styles.fullWidth,
          isDisabled && styles.disabled,
          styles.primaryGlow,
          style,
        ]}
      >
        <LinearGradient
          // Polish Vertushka v4 — 3-stop cobalt gradient (135deg, deep → mid → soft).
          colors={['#1B2E78', '#2A4BD7', '#5C7AE8']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[
            styles.base,
            size === 'small' && styles.small,
          ]}
        >
          {content}
        </LinearGradient>
      </TouchableOpacity>
    );
  }

  return (
    <TouchableOpacity
      style={[
        styles.base,
        styles[variant],
        size === 'small' && styles.small,
        fullWidth && styles.fullWidth,
        isDisabled && styles.disabled,
        style,
      ]}
      onPress={onPress}
      disabled={isDisabled}
      activeOpacity={0.8}
    >
      {content}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  // Высота — МИНИМУМ, не фикс: при крупном системном «Размере текста» подпись
  // в две строки должна растягивать кнопку, а не обрезаться внутри 56pt.
  // paddingVertical подобран так, что при 100% масштабе высота ровно прежняя.
  base: {
    minHeight: ComponentSizes.buttonHeight,
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    overflow: 'hidden',
  },

  // Polish v4 glow для primary.
  //
  // Тонкости:
  // 1. Свой `backgroundColor` на shadow-обёртке обязателен — иначе iOS не
  //    знает, какой shape использовать для тени, и фолбэчит на bounding-rect
  //    с резкими углами. Цвет совпадает с серединой градиента, поэтому он
  //    не виден из-под LinearGradient (который сидит сверху и closeup-перекрыт
  //    через `overflow: hidden`).
  // 2. `shadowOffset.height = 8` + `shadowRadius = 22` — диффузный glow,
  //    почти симметричный сверху и снизу. На `height = 4 / radius = 16`
  //    сверху появлялась чёткая горизонтальная линия отсечения.
  // 3. `shadowOpacity` снижен до 0.28 — общий эффект мягче, без «штампа».
  primaryGlow: {
    borderRadius: 18,
    backgroundColor: '#2A4BD7',
    shadowColor: '#2A4BD7',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.28,
    shadowRadius: 22,
    elevation: 10,
  },

  // Варианты (primary handled via LinearGradient)
  primary: {
    backgroundColor: Colors.royalBlue,
  },
  secondary: {
    backgroundColor: Colors.surface,
  },
  outline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: Colors.royalBlue,
  },
  ghost: {
    backgroundColor: 'transparent',
  },

  // Размеры
  small: {
    minHeight: ComponentSizes.buttonHeightSmall,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },

  // Ширина
  fullWidth: {
    width: '100%',
  },

  // Состояния
  disabled: {
    opacity: 0.5,
  },

  // Текст
  text: {
    ...Typography.button,
    textAlign: 'center',
    // Даём тексту сжиматься и переноситься внутри кнопки, а не выезжать за неё.
    flexShrink: 1,
  },
  primaryText: {
    color: Colors.background,
  },
  secondaryText: {
    color: Colors.royalBlue,
  },
  outlineText: {
    color: Colors.royalBlue,
  },
  ghostText: {
    color: Colors.royalBlue,
  },
  smallText: {
    ...Typography.buttonSmall,
  },
  disabledText: {
    // opacity handled by container
  },
});

export default Button;
