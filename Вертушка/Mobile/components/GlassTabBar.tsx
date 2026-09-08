/**
 * Floating Pill Tab Bar — Editorial Gradient Edition
 * По референсу Trove: floating pill, равные табы, spring zoom, indicator
 */
import React from 'react';
import {
  View,
  TouchableOpacity,
  StyleSheet,
  Platform,
  useWindowDimensions,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { BlurViewCompat } from '@/components/ui/BlurViewCompat';
import { LinearGradient } from 'expo-linear-gradient';
import { Icon } from '@/components/ui';
import * as Haptics from 'expo-haptics';
import Animated, {
  useAnimatedStyle,
  withSpring,
  withTiming,
  useSharedValue,
  useDerivedValue,
} from 'react-native-reanimated';
import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { Colors, Shadows, Gradients, androidShadow } from '../constants/theme';
// Единое имя на таб; визуальная разница inactive ↔ active — через weight в <Icon>.
const TAB_ICONS: Record<string, string> = {
  search: 'magnifying-glass',
  index: 'scan',
  collection: 'disc',
};

const ICON_SIZE = 26;
const BAR_HEIGHT = 64;
const INDICATOR_WIDTH = 28;
const INDICATOR_HEIGHT = 3;

function TabIcon({
  routeName,
  isFocused,
  onPress,
  onLongPress,
}: {
  routeName: string;
  isFocused: boolean;
  onPress: () => void;
  onLongPress: () => void;
}) {
  const iconName = TAB_ICONS[routeName] || TAB_ICONS.search;

  const animatedIcon = useAnimatedStyle(() => {
    const scale = withSpring(isFocused ? 1.25 : 1.0, {
      damping: 12,
      stiffness: 180,
    });
    return { transform: [{ scale }] };
  }, [isFocused]);

  const animatedOpacity = useAnimatedStyle(() => {
    const opacity = withTiming(isFocused ? 1 : 0.5, { duration: 200 });
    return { opacity };
  }, [isFocused]);

  return (
    <TouchableOpacity
      style={styles.tabItem}
      onPress={onPress}
      onLongPress={onLongPress}
      activeOpacity={0.7}
    >
      <Animated.View style={[animatedIcon, animatedOpacity]}>
        <Icon
          name={iconName}
          size={ICON_SIZE}
          color={isFocused ? Colors.royalBlue : Colors.textMuted}
          weight={isFocused ? 'fill' : 'duotone'}
        />
      </Animated.View>
    </TouchableOpacity>
  );
}

export function GlassTabBar({ state, descriptors, navigation, insets }: BottomTabBarProps) {
  const tabCount = state.routes.length;
  const { width: screenWidth } = useWindowDimensions();

  // Edge-to-edge на Android: бар висит над системной панелью (жесты ~24dp,
  // 3-кнопочная навигация 48dp). iOS — прежний хардкод `bottom: 28`, объект
  // стиля тот же (snapshot-гейт __tests__/GlassTabBar.ios.test.tsx).
  const containerStyle = Platform.select<StyleProp<ViewStyle>>({
    ios: styles.container,
    default: [
      styles.container,
      styles.containerAndroid,
      { bottom: Math.max(insets.bottom, 16) + 12 },
    ],
  });

  const indicatorPosition = useDerivedValue(() => {
    return withTiming(state.index, { duration: 250 });
  }, [state.index]);

  const indicatorStyle = useAnimatedStyle(() => {
    const tabWidth = 100 / tabCount;
    const barWidthPx = screenWidth * 0.65;
    const iconOffsetPct = (ICON_SIZE / 2 / barWidthPx) * 100;
    const left = `${indicatorPosition.value * tabWidth + tabWidth / 2 - iconOffsetPct}%`;
    return {
      left: left as unknown as number,
    };
  });

  return (
    <View style={containerStyle}>
      <BlurViewCompat
        intensity={60}
        tint="light"
        style={styles.blurContainer}
      >
        <View style={styles.glassOverlay} />

        {/* Индикатор сверху активного таба */}
        <Animated.View style={[styles.indicator, indicatorStyle]}>
          <LinearGradient
            colors={Gradients.blue as [string, string]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
            style={styles.indicatorGradient}
          />
        </Animated.View>

        <View style={styles.tabsRow}>
          {state.routes.map((route, index) => {
            const isFocused = state.index === index;

            const onPress = () => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              const event = navigation.emit({
                type: 'tabPress',
                target: route.key,
                canPreventDefault: true,
              });
              if (!isFocused && !event.defaultPrevented) {
                navigation.navigate(route.name, route.params);
              }
            };

            const onLongPress = () => {
              navigation.emit({
                type: 'tabLongPress',
                target: route.key,
              });
            };

            return (
              <TabIcon
                key={route.key}
                routeName={route.name}
                isFocused={isFocused}
                onPress={onPress}
                onLongPress={onLongPress}
              />
            );
          })}
        </View>
      </BlurViewCompat>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: 28,
    alignSelf: 'center',
    width: '65%',
    ...Shadows.tabBar,
  },
  // Android: у контейнера нет фона, elevation без него тень не рисует —
  // тень через boxShadow (те же цвет/offset/радиус, что у Shadows.tabBar).
  // borderRadius нужен и самому контейнеру: на Fabric boxShadow берёт форму
  // с view, на котором объявлен, — без радиуса тень рисовалась прямоугольником
  // и её угол читался как «квадратный» угол пилюли (A8 в docs/BUGS.md).
  containerAndroid: {
    elevation: 0,
    borderRadius: 36,
    ...androidShadow({ color: '#3B4BF5', opacity: 0.12, radius: 24, offsetY: -4 }),
  },
  blurContainer: {
    borderRadius: 36,
    overflow: 'hidden',
    height: 60,
  },
  glassOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: Colors.glassBg,
  },
  indicator: {
    position: 'absolute',
    top: 0,
    width: INDICATOR_WIDTH,
    height: INDICATOR_HEIGHT,
    zIndex: 10,
  },
  indicatorGradient: {
    width: '100%',
    height: '100%',
    borderBottomLeftRadius: 2,
    borderBottomRightRadius: 2,
  },
  tabsRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
  },
});

export default GlassTabBar;
