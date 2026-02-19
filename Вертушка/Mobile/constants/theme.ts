/**
 * Дизайн-система Вертушка — Blue Gradient Edition
 * Сине-розовый градиент, Inter font, glass morphism
 */

export const Colors = {
  // Основная градиентная палитра
  deepNavy: '#0A0B3B',
  royalBlue: '#3B4BF5',
  electricBlue: '#5B6AF5',
  periwinkle: '#8B9CF7',
  lavender: '#C5B8F2',
  softPink: '#F0C4D8',
  blushPink: '#F8E4EE',

  // Нейтральные
  background: '#FAFBFF',
  surface: '#F0F2FA',
  surfaceHover: '#E8EBFA',

  // Текст
  text: '#0A0B3B',
  textSecondary: '#5A5F8A',
  textMuted: '#9A9EBF',

  // Состояния
  error: '#E5484D',
  success: '#30A46C',
  warning: '#F5A623',

  // Границы и разделители
  border: '#E0E3F0',
  divider: '#ECEEF7',

  // Специальные
  overlay: 'rgba(10, 11, 59, 0.5)',
  cardShadow: 'rgba(59, 75, 245, 0.08)',
  glassBg: 'rgba(250, 251, 255, 0.85)',

};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const BorderRadius = {
  sm: 10,
  md: 14,
  lg: 18,
  xl: 26,
  full: 9999,
};

export const Gradients = {
  blue: ['#3B4BF5', '#5B6AF5'] as const,
  bluePink: ['#3B4BF5', '#8B9CF7', '#F0C4D8'] as const,
  blueLight: ['#5B6AF5', '#8B9CF7'] as const,
  overlay: ['transparent', 'rgba(10, 11, 59, 0.7)'] as const,
};

export const Typography = {
  heroTitle: {
    fontSize: 46,
    fontFamily: 'Arial Black',
    lineHeight: 50,
    letterSpacing: -1.5,
  },
  display: {
    fontSize: 36,
    fontFamily: 'Arial Black',
    lineHeight: 40,
    letterSpacing: -1,
  },
  h1: {
    fontSize: 34,
    fontFamily: 'Inter_800ExtraBold',
    lineHeight: 40,
    letterSpacing: -1,
  },
  h2: {
    fontSize: 28,
    fontFamily: 'Inter_700Bold',
    lineHeight: 34,
    letterSpacing: -0.5,
  },
  h3: {
    fontSize: 22,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 28,
  },
  h4: {
    fontSize: 18,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 24,
  },

  body: {
    fontSize: 16,
    fontFamily: 'Inter_400Regular',
    lineHeight: 24,
  },
  bodyBold: {
    fontSize: 16,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 24,
  },
  bodySmall: {
    fontSize: 14,
    fontFamily: 'Inter_400Regular',
    lineHeight: 20,
  },

  caption: {
    fontSize: 12,
    fontFamily: 'Inter_400Regular',
    lineHeight: 16,
  },

  button: {
    fontSize: 16,
    fontFamily: 'Inter_600SemiBold',
    lineHeight: 24,
    letterSpacing: 0.3,
  },
  buttonSmall: {
    fontSize: 14,
    fontFamily: 'Inter_500Medium',
    lineHeight: 20,
    letterSpacing: 0.2,
  },
};

export const Shadows = {
  sm: {
    shadowColor: '#3B4BF5',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  md: {
    shadowColor: '#3B4BF5',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
  },
  lg: {
    shadowColor: '#3B4BF5',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.15,
    shadowRadius: 32,
    elevation: 12,
  },
  tabBar: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.14,
    shadowRadius: 24,
    elevation: 14,
  },
};

export const ComponentSizes = {
  buttonHeight: 56,
  buttonHeightSmall: 44,
  inputHeight: 56,
  cardPadding: Spacing.md,
  tabBarHeight: 84,
  headerHeight: 56,
  iconSm: 20,
  iconMd: 24,
  iconLg: 32,
};

export const AnimatedGradientPalette = {
  colors: [
    '#2D3E8F',  // Тёмно-синий
    '#4A6FDB',  // Насыщенный синий
    '#6B9EF5',  // Средне-синий
    '#93C4FF',  // Светло-синий
    '#C8D9F7',  // Очень светло-синий
    '#E8CEEB',  // Светло-розово-фиолетовый
    '#F5B5D8',  // Светло-розовый
  ] as const,
  presets: [
    ['#2D3E8F', '#4A6FDB', '#6B9EF5'],
    ['#4A6FDB', '#6B9EF5', '#93C4FF'],
    ['#6B9EF5', '#93C4FF', '#C8D9F7'],
    ['#93C4FF', '#C8D9F7', '#E8CEEB'],
    ['#C8D9F7', '#E8CEEB', '#F5B5D8'],
    ['#E8CEEB', '#F5B5D8', '#93C4FF'],
    ['#F5B5D8', '#6B9EF5', '#2D3E8F'],
  ] as const,
};

export default {
  Colors,
  Spacing,
  BorderRadius,
  Typography,
  Shadows,
  ComponentSizes,
  Gradients,
  AnimatedGradientPalette,
};
