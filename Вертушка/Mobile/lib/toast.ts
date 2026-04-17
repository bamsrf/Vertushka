/**
 * Утилита для показа тостов через react-native-toast-message.
 * Используй вместо Alert.alert для success/error/info сообщений.
 * Alert.alert оставляй только для подтверждений деструктивных действий.
 */
import Toast from 'react-native-toast-message';

export const toast = {
  success: (message: string, subtitle?: string) =>
    Toast.show({ type: 'success', text1: message, text2: subtitle, visibilityTime: 2500 }),

  error: (message: string, subtitle?: string) =>
    Toast.show({ type: 'error', text1: message, text2: subtitle, visibilityTime: 3000 }),

  info: (message: string, subtitle?: string) =>
    Toast.show({ type: 'info', text1: message, text2: subtitle, visibilityTime: 2500 }),
};
