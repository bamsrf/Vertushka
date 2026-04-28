import React, { useEffect } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  interpolate,
} from 'react-native-reanimated';
import { BorderRadius, Typography } from '../constants/theme';
import { parseVinylColor } from '../lib/vinylColor';

interface VinylColorTagProps {
  vinylColorRaw: string | undefined | null;
}

export function VinylColorTag({ vinylColorRaw }: VinylColorTagProps) {
  const colorConfig = parseVinylColor(vinylColorRaw);
  const glow = useSharedValue(0);

  useEffect(() => {
    if (!colorConfig.isColored) return;
    glow.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 1200 }),
        withTiming(0, { duration: 1200 }),
      ),
      -1,
    );
  }, [colorConfig.isColored]);

  const animatedStyle = useAnimatedStyle(() => ({
    shadowOpacity: interpolate(glow.value, [0, 1], [0.1, 0.55]),
    shadowRadius: interpolate(glow.value, [0, 1], [2, 10]),
  }));

  if (!colorConfig.isColored) return null;

  const { primaryColor } = colorConfig;
  const label = (vinylColorRaw ?? '').split(/[\s,/[]/)[0].slice(0, 12);

  return (
    <Animated.View
      style={[
        styles.pill,
        {
          backgroundColor: `${primaryColor}26`,
          borderColor: `${primaryColor}80`,
          shadowColor: primaryColor,
          shadowOffset: { width: 0, height: 0 },
          elevation: 4,
        },
        animatedStyle,
      ]}
    >
      <View style={[styles.dot, { backgroundColor: primaryColor }]} />
      <Text style={[styles.label, { color: primaryColor }]}>{label}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: BorderRadius.full,
    borderWidth: 1,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  label: {
    ...Typography.caption,
    fontFamily: 'Inter_500Medium',
  },
});
