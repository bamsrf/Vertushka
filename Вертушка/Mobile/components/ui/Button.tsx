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
import { Colors, Typography, BorderRadius, ComponentSizes, Spacing, Shadows } from '../../constants/theme';

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
        activeOpacity={0.8}
        style={[
          fullWidth && styles.fullWidth,
          isDisabled && styles.disabled,
          style,
        ]}
      >
        <LinearGradient
          colors={[Colors.royalBlue, Colors.electricBlue]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={[
            styles.base,
            size === 'small' && styles.small,
            Shadows.md,
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
  base: {
    height: ComponentSizes.buttonHeight,
    paddingHorizontal: Spacing.lg,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
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
    height: ComponentSizes.buttonHeightSmall,
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
