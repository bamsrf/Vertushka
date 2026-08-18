/**
 * LevelUpIcon — иконка повышения уровня.
 *
 * До неё `level_up` рисовался ионик-глифом `trending-up` в общем ряду
 * системных типов: событие «ты взял новую ступень» выглядело так же, как
 * «пластинка подешевела». Иконка даёт ему собственный образ.
 *
 * Образ: пластинка (чёрный диск с канавками — базовая форма всей айдентики),
 * сквозь центр которой вверх уходит стрелка. Цвет стрелки, канавок и обода —
 * цвет взятой ступени (`LEVEL_ICON_ACCENT`), заливка диска — `discBg` той же
 * ступени. То есть иконка «Первозвука» и hero «Первозвука» — одна вещь.
 *
 * Анимация (`animated`): стрелка отрывается вверх, от обода расходятся две
 * волны — визуальный эквивалент того, что и означает уровень. Уважает
 * системный Reduce Motion и уход приложения в фон через useAnimationGate;
 * при выключенной анимации остаётся статичный кадр в покое, без «застывшего»
 * промежуточного состояния.
 */
import { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, View } from 'react-native';
import Svg, { Circle, Defs, Path, RadialGradient, Stop } from 'react-native-svg';

import { levelTheme, levelIconAccent } from './achievement-mockup/levelTheme';
import { LEVELS } from '../lib/archetype';
import { useAmbientAnimationsEnabled } from '../lib/useAnimationGate';

/** Ниже этого размера «следы» под стрелкой превращаются в грязь. */
const TRAILS_MIN_SIZE = 44;

/** id градиента должен быть уникален на всё дерево: одинаковые defs в
 *  react-native-svg перетирают друг друга, и вторая иконка берёт чужой диск. */
let gradientSeq = 0;

interface LevelUpIconProps {
  /** Ключ ступени из LEVELS (lib/archetype.ts). Неизвестный → «Эхо». */
  level: string;
  size?: number;
  /** Крутить ли отрыв стрелки и волны. */
  animated?: boolean;
}

export function LevelUpIcon({ level, size = 40, animated = false }: LevelUpIconProps) {
  const accent = levelIconAccent(level);
  const discBg = levelTheme(level).discBg;
  // Reduce Motion и уход в фон гасят движение независимо от желания вызывающего.
  const motionAllowed = useAmbientAnimationsEnabled();
  const moving = animated && motionAllowed;

  // Чем выше ступень, тем плотнее «звучат» канавки и ярче обод. Прогрессия
  // видна даже там, где соседние ступени близки по цвету (Тишь/Шорох).
  const depth = useMemo(() => {
    const idx = LEVELS.findIndex((l) => l.key === level);
    return idx < 0 ? 0 : idx / (LEVELS.length - 1);
  }, [level]);
  const grooveOpacity = 0.12 + depth * 0.16;
  const rimOpacity = 0.4 + depth * 0.35;

  const gradientId = useMemo(() => `levelup-${level}-${(gradientSeq += 1)}`, [level]);

  return (
    <View style={{ width: size, height: size }}>
      {moving ? <Waves size={size} accent={accent} /> : null}

      <Svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        style={StyleSheet.absoluteFill}
      >
        <Defs>
          <RadialGradient id={gradientId} cx="38%" cy="30%" r="78%">
            <Stop offset="0" stopColor={discBg} />
            <Stop offset="1" stopColor="#05070F" />
          </RadialGradient>
        </Defs>
        <Circle
          cx={32}
          cy={32}
          r={27}
          fill={`url(#${gradientId})`}
          stroke={accent}
          strokeOpacity={rimOpacity}
          strokeWidth={1.5}
        />
        <Circle
          cx={32}
          cy={32}
          r={22}
          stroke={accent}
          strokeOpacity={grooveOpacity}
          strokeWidth={1}
        />
        <Circle
          cx={32}
          cy={32}
          r={17.5}
          stroke={accent}
          strokeOpacity={grooveOpacity * 0.8}
          strokeWidth={1}
        />
      </Svg>

      <Arrow size={size} accent={accent} animated={moving} />
    </View>
  );
}

/** Стрелка сквозь центр диска; при animated — отрывается вверх и возвращается. */
function Arrow({ size, accent, animated }: { size: number; accent: string; animated: boolean }) {
  const lift = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!animated) {
      lift.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(lift, {
          toValue: 1,
          duration: 620,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true,
        }),
        Animated.timing(lift, {
          toValue: 0,
          duration: 520,
          easing: Easing.inOut(Easing.quad),
          useNativeDriver: true,
        }),
        Animated.delay(900),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [animated, lift]);

  const translateY = lift.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -size * 0.055],
  });

  return (
    <Animated.View style={[StyleSheet.absoluteFill, { transform: [{ translateY }] }]}>
      <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
        <Path d="M32 45.5 V22" stroke={accent} strokeWidth={5.2} strokeLinecap="round" />
        <Path
          d="M21.5 32 L32 21 L42.5 32"
          stroke={accent}
          strokeWidth={5.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {size >= TRAILS_MIN_SIZE ? (
          <Path
            d="M24 49.5 v3.5 M40 49.5 v3.5"
            stroke={accent}
            strokeOpacity={0.45}
            strokeWidth={3}
            strokeLinecap="round"
          />
        ) : null}
      </Svg>
    </Animated.View>
  );
}

/** Две волны, расходящиеся от обода со сдвигом по фазе. */
function Waves({ size, accent }: { size: number; accent: string }) {
  const a = useRef(new Animated.Value(0)).current;
  const b = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const ring = (value: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(value, {
            toValue: 1,
            duration: 1400,
            easing: Easing.out(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(value, { toValue: 0, duration: 0, useNativeDriver: true }),
          Animated.delay(640 - delay),
        ]),
      );
    const loops = [ring(a, 0), ring(b, 640)];
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [a, b]);

  return (
    <>
      {[a, b].map((value, i) => (
        <Animated.View
          key={i}
          style={[
            StyleSheet.absoluteFill,
            {
              opacity: value.interpolate({ inputRange: [0, 1], outputRange: [0.55, 0] }),
              // Потолок 1.17: при r=26.5 волна упирается ровно в край канвы
              // SVG (32). Больше — и react-native-svg срежет её по viewBox.
              transform: [
                { scale: value.interpolate({ inputRange: [0, 1], outputRange: [1, 1.17] }) },
              ],
            },
          ]}
        >
          <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
            <Circle cx={32} cy={32} r={26.5} stroke={accent} strokeWidth={1.5} />
          </Svg>
        </Animated.View>
      ))}
    </>
  );
}

export default LevelUpIcon;
