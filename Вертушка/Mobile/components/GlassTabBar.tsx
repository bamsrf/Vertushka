/**
 * Floating Pill Tab Bar — Editorial Gradient Edition
 * По референсу Trove: floating pill, равные табы, spring zoom, indicator
 */
import React from 'react';
import { View, TouchableOpacity, StyleSheet, Platform, useWindowDimensions } from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import Animated, {
  useAnimatedStyle,
  withSpring,
  withTiming,
  useSharedValue,
  useDerivedValue,
} from 'react-native-reanimated';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Colors, Shadows, Gradients } from '../constants/theme';

const TAB_ICONS: Record<string, { outline: keyof typeof Ionicons.glyphMap; filled: keyof typeof Ionicons.glyphMap }> = {
  search: { outline: 'search-outline', filled: 'search' },
  index: { outline: 'scan-outline', filled: 'scan' },
  collection: { outline: 'disc-outline', filled: 'disc' },
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
  const icons = TAB_ICONS[routeName] || TAB_ICONS.search;

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
        <Ionicons
          name={isFocused ? icons.filled : icons.outline}
          size={ICON_SIZE}
          color={isFocused ? Colors.royalBlue : Colors.textMuted}
        />
      </Animated.View>
    </TouchableOpacity>
  );
}

export function GlassTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const tabCount = state.routes.length;
  const { width: screenWidth } = useWindowDimensions();

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
    <View style={styles.container}>
      <BlurView
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
      </BlurView>
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
  blurContainer: {
    borderRadius: 36,
    overflow: 'hidden',
    height: 60,
  },
  glassOverlay: {
    ...StyleSheet.absoluteFillObject,
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
