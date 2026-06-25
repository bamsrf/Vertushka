/**
 * Toggle — iOS-style on/off переключатель Вертушки.
 *
 * Чистый pill-трек с белым кнобом. В off — нейтральная подложка (border),
 * в on — фирменный синий градиент (Gradients.blue), который проявляется
 * кроссфейдом поверх подложки. Кноб уезжает вправо пружиной.
 *
 * Анимация целиком на native driver (translateX + opacity), без
 * interpolate'а цвета — поэтому не дёргается и interruptible.
 */
import { useEffect, useRef } from 'react';
import { View, StyleSheet, Pressable, Animated } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Colors, Gradients } from '../../constants/theme';

const TRACK_W = 52;
const TRACK_H = 32;
const KNOB = 28;
const PAD = 2;
const SLIDE = TRACK_W - KNOB - PAD * 2;

interface ToggleProps {
  value: boolean;
  onValueChange: (val: boolean) => void;
  disabled?: boolean;
}

export function Toggle({ value, onValueChange, disabled }: ToggleProps) {
  const anim = useRef(new Animated.Value(value ? 1 : 0)).current;

  useEffect(() => {
    Animated.spring(anim, {
      toValue: value ? 1 : 0,
      useNativeDriver: true,
      friction: 8,
      tension: 70,
    }).start();
  }, [value, anim]);

  const translateX = anim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, SLIDE],
  });

  return (
    <Pressable
      onPress={() => !disabled && onValueChange(!value)}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      disabled={disabled}
    >
      <View style={styles.track}>
        {/* off-подложка */}
        <View style={[StyleSheet.absoluteFill, styles.trackOff]} />
        {/* on-градиент — проявляется кроссфейдом */}
        <Animated.View style={[StyleSheet.absoluteFill, { opacity: anim }]}>
          <LinearGradient
            colors={Gradients.blue}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.fill}
          />
        </Animated.View>

        <Animated.View style={[styles.knob, { transform: [{ translateX }] }]} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  track: {
    width: TRACK_W,
    height: TRACK_H,
    borderRadius: TRACK_H / 2,
    padding: PAD,
    justifyContent: 'center',
    overflow: 'hidden',
  },
  trackOff: {
    backgroundColor: Colors.border,
    borderRadius: TRACK_H / 2,
  },
  fill: {
    flex: 1,
    borderRadius: TRACK_H / 2,
  },
  knob: {
    width: KNOB,
    height: KNOB,
    borderRadius: KNOB / 2,
    backgroundColor: '#FFFFFF',
    shadowColor: Colors.deepNavy,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.18,
    shadowRadius: 3,
    elevation: 3,
  },
});
