/**
 * MascotIntro — полноэкранная заставка маскота на Lottie, играет ОДИН раз
 * при старте (после native splash). Анимация — `assets/animations/intro-mascot.json`.
 *
 * Native splash (app.json) анимировать нельзя — платформенное ограничение, см.
 * docs/plans/MASCOT_ANIMATION_SPEC.md §6. Поэтому «живое» интро живёт здесь, уже
 * внутри приложения, поверх остального UI.
 *
 * Устойчивость: `lottie-react-native` есть только в dev-build/проде. Если модуля
 * нет (Expo Go) — интро тихо пропускается (onFinish вызывается сразу), пользователь
 * просто попадает в приложение без заставки. Никаких заглушек на весь экран.
 *
 * Placeholder-guard: пока в intro-mascot.json лежит заглушка (поле "nm" содержит
 * "-PLACEHOLDER"), интро НЕ показывается — синий кружок не должен утечь в релиз.
 * Как только дизайнер подложит финальный .json (без маркера), интро включится
 * само, править код не нужно. См. docs/plans/MASCOT_ANIMATION_SPEC.md §7.5.
 *
 * Фон интро = Colors.background (#FAFBFF) — совпадает с фоном splash-стыка (§8 ТЗ).
 */
import { useEffect, useRef } from 'react';
import { View, StyleSheet } from 'react-native';
import { Colors } from '../constants/theme';

let LottieView: React.ComponentType<Record<string, unknown>> | null = null;
try {
  LottieView = require('lottie-react-native').default;
} catch {
  LottieView = null;
}

const INTRO_SOURCE = require('../assets/animations/intro-mascot.json');
// Заглушка? Не показываем интро вообще, пока не придёт финальная анимация.
const IS_PLACEHOLDER =
  typeof INTRO_SOURCE?.nm === 'string' && INTRO_SOURCE.nm.includes('PLACEHOLDER');

interface MascotIntroProps {
  /** Вызывается когда интро отыграло (или сразу, если lottie недоступен). */
  onFinish: () => void;
}

export function MascotIntro({ onFinish }: MascotIntroProps) {
  // Гарантия, что onFinish не выстрелит дважды (onAnimationFinish + safety-timeout).
  const finished = useRef(false);

  const finish = () => {
    if (finished.current) return;
    finished.current = true;
    onFinish();
  };

  useEffect(() => {
    if (!LottieView || IS_PLACEHOLDER) {
      // Модуля нет ИЛИ в файле заглушка — интро пропускаем сразу.
      finish();
      return;
    }
    // Safety-net: если onAnimationFinish не прилетит (редко на Android при
    // прерывании), всё равно закрываемся через ~4с — дольше самой анимации (3с).
    const t = setTimeout(finish, 4000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!LottieView || IS_PLACEHOLDER) return null;

  return (
    <View style={styles.fill} pointerEvents="auto">
      <LottieView
        source={INTRO_SOURCE}
        autoPlay
        loop={false}
        onAnimationFinish={finish}
        resizeMode="contain"
        style={styles.anim}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: Colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  anim: {
    width: '82%',
    aspectRatio: 1,
  },
});
