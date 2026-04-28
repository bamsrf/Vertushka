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

const RUSSIAN_NAMES: Record<string, string> = {
  '#E53935': 'Красный',
  '#C62828': 'Тёмно-красный',
  '#880E4F': 'Бордовый',
  '#D32F2F': 'Алый',
  '#1E88E5': 'Синий',
  '#1565C0': 'Кобальт',
  '#0D47A1': 'Тёмно-синий',
  '#1A237E': 'Сапфир',
  '#3949AB': 'Индиго',
  '#B3E5FC': 'Ледяной',
  '#4FC3F7': 'Голубой',
  '#43A047': 'Зелёный',
  '#2E7D32': 'Изумрудный',
  '#C6FF00': 'Лаймовый',
  '#4DB6AC': 'Морской',
  '#00897B': 'Бирюзовый',
  '#827717': 'Оливковый',
  '#00BCD4': 'Аквамарин',
  '#A5D6A7': 'Мятный',
  '#FDD835': 'Жёлтый',
  '#FFEE58': 'Лимонный',
  '#FFF8E1': 'Кремовый',
  '#FFFFF0': 'Слоновая кость',
  '#FFF9C4': 'Масляный',
  '#FB8C00': 'Оранжевый',
  '#FF8F00': 'Янтарный',
  '#FFD600': 'Золотой',
  '#CD7F32': 'Бронзовый',
  '#B87333': 'Медный',
  '#C68642': 'Карамельный',
  '#9E9E9E': 'Дымчатый',
  '#EC407A': 'Розовый',
  '#E040FB': 'Маджента',
  '#F06292': 'Розово-красный',
  '#FF7043': 'Коралловый',
  '#FF8A65': 'Лососевый',
  '#FFAB91': 'Персиковый',
  '#F8BBD9': 'Нежно-розовый',
  '#8E24AA': 'Пурпурный',
  '#7B1FA2': 'Фиолетовый',
  '#CE93D8': 'Лавандовый',
  '#6A1B9A': 'Сливовый',
  '#AB47BC': 'Мальва',
  '#F5F5F5': 'Белый',
  '#F0EBE3': 'Жемчужный',
  '#B0BEC5': 'Серебристый',
  '#616161': 'Тёмно-серый',
  '#CFD8DC': 'Светло-серый',
  '#455A64': 'Графитовый',
  '#E3F2FD': 'Прозрачный',
  '#76FF03': 'Неоновый',
  '#F4FF81': 'Неон-жёлтый',
  '#FF4081': 'Неон-розовый',
  '#FF6D00': 'Неон-оранжевый',
  '#FF1744': 'Неон-красный',
  '#2979FF': 'Неон-синий',
};

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
  const label = RUSSIAN_NAMES[primaryColor] ?? (vinylColorRaw ?? '').split(/[\s,/[]/)[0].slice(0, 14);

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
