/**
 * Лёгкое конфетти на Animated API. Спавнит N частиц в цветах тира, каждая
 * с лёгким drift'ом и поворотом. Не зависит от Reanimated worklets — простой
 * `Animated.View` + `interpolate`.
 */
import { useEffect, useMemo, useRef } from 'react';
import { Animated, Dimensions, Easing, StyleSheet, View } from 'react-native';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

interface Props {
  /** Цвета частиц — массив hex */
  colors: string[];
  /** Сколько частиц */
  count?: number;
  /** Длительность падения */
  duration?: number;
  /** Запустить заново при каждом изменении этого ключа */
  triggerKey?: string;
}

interface ParticleSpec {
  startX: number;
  endX: number;
  size: number;
  color: string;
  delay: number;
  rotateDir: 1 | -1;
  /** Итоговый угол поворота в градусах — фиксируем в спеке, а не в render */
  spin: number;
  shape: 'square' | 'rect' | 'circle';
}

export function Confetti({ colors, count = 32, duration = 2200, triggerKey }: Props) {
  const specs = useMemo<ParticleSpec[]>(() => {
    const arr: ParticleSpec[] = [];
    for (let i = 0; i < count; i++) {
      arr.push({
        startX: Math.random() * SCREEN_W,
        endX: Math.random() * SCREEN_W,
        size: 6 + Math.random() * 10,
        color: colors[i % colors.length],
        delay: Math.random() * 400,
        rotateDir: Math.random() > 0.5 ? 1 : -1,
        spin: 360 + Math.floor(Math.random() * 360),
        shape: (['square', 'rect', 'circle'] as const)[Math.floor(Math.random() * 3)],
      });
    }
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerKey, count]);

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {specs.map((s, idx) => (
        <Particle key={`${triggerKey ?? ''}-${idx}`} spec={s} duration={duration} />
      ))}
    </View>
  );
}

function Particle({ spec, duration }: { spec: ParticleSpec; duration: number }) {
  const t = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Явный сброс: без него повторный запуск (следующая ачивка в очереди,
    // когда хост переиспользует смонтированные частицы) стартует с t=1 —
    // анимировать некуда, и конфетти просто не появляется.
    t.setValue(0);
    Animated.sequence([
      Animated.delay(spec.delay),
      Animated.timing(t, {
        toValue: 1,
        duration,
        easing: Easing.out(Easing.cubic),
        useNativeDriver: true,
      }),
    ]).start();
  }, [spec.delay, duration, t]);

  const translateX = t.interpolate({
    inputRange: [0, 1],
    outputRange: [0, spec.endX - spec.startX],
  });
  const translateY = t.interpolate({
    inputRange: [0, 1],
    outputRange: [-30, SCREEN_H + 40],
  });
  const rotate = t.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', `${spec.rotateDir * spec.spin}deg`],
  });
  const opacity = t.interpolate({
    inputRange: [0, 0.1, 0.85, 1],
    outputRange: [0, 1, 1, 0],
  });

  const shapeStyle = {
    width: spec.size,
    height: spec.shape === 'rect' ? spec.size * 0.5 : spec.size,
    borderRadius: spec.shape === 'circle' ? spec.size / 2 : 1.5,
    backgroundColor: spec.color,
  };

  return (
    <Animated.View
      style={[
        {
          position: 'absolute',
          left: spec.startX,
          top: 0,
          opacity,
          transform: [{ translateX }, { translateY }, { rotate }],
        },
        shapeStyle,
      ]}
    />
  );
}
