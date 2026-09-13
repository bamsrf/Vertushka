// Общий setup для jest-expo.
// Reanimated 4 + worklets: нативный JSI-модуль в jest недоступен, берём mock-реализации.
jest.mock('react-native-worklets', () => require('react-native-worklets/lib/module/mock'));
jest.mock('react-native-reanimated', () => require('react-native-reanimated/mock'));
jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light' },
}));

// AsyncStorage: нативного модуля в jest нет, берём официальный in-memory mock
// из самого пакета. Нужен всему, что помнит состояние между запусками —
// онбординг-подсказки, жест-подсказки, кэши сторов.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'));
