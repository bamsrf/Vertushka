/**
 * MascotLoader — луп-лоадер маскота на Lottie.
 *
 * Показывается там, где грузятся данные (замена ActivityIndicator/VinylSpinner
 * в лоадер-сценариях). Анимация — `assets/animations/loader-mascot.json`.
 *
 * Устойчивость (паттерн как у Sentry/view-shot в этом проекте): нативный модуль
 * `lottie-react-native` есть только в dev-build/проде, в Expo Go его нет. Поэтому
 * подключаем его через ленивый require и при отсутствии — падаем на существующий
 * `VinylSpinner`. Ничего не ломается, лоадер всегда что-то показывает.
 *
 * ТЗ на .json: docs/plans/MASCOT_ANIMATION_SPEC.md (сейчас там PLACEHOLDER).
 */
import { View, StyleSheet } from 'react-native';
import { VinylSpinner } from './VinylSpinner';
import { Colors } from '../constants/theme';

// Ленивый require нативного модуля. В Expo Go бросит — ловим, ставим null.
let LottieView: React.ComponentType<Record<string, unknown>> | null = null;
try {
  LottieView = require('lottie-react-native').default;
} catch {
  LottieView = null;
}

// Fallback-конфиг для VinylSpinner (бренд-cobalt диск).
import type { VinylColorConfig } from '../lib/vinylColor';
const FALLBACK_VINYL: VinylColorConfig = {
  type: 'solid',
  primaryColor: Colors.royalBlue,
  opacity: 1,
  isColored: true,
};

interface MascotLoaderProps {
  /** Размер квадрата анимации, px. По умолчанию 120. */
  size?: number;
}

export function MascotLoader({ size = 120 }: MascotLoaderProps) {
  if (!LottieView) {
    // Expo Go / модуль ещё не собран — крутим существующий винил.
    return (
      <View style={[styles.wrap, { width: size, height: size }]}>
        <VinylSpinner colorConfig={FALLBACK_VINYL} size={size} />
      </View>
    );
  }

  return (
    <View style={[styles.wrap, { width: size, height: size }]}>
      <LottieView
        source={require('../assets/animations/loader-mascot.json')}
        autoPlay
        loop
        style={{ width: size, height: size }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
