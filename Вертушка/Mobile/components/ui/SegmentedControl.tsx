/**
 * Сегментированный контрол — Blue Gradient Edition
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ViewStyle,
  LayoutChangeEvent,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { Colors, Typography, BorderRadius, Spacing } from '../../constants/theme';

const PADDING = 4;

interface SegmentedControlProps<T extends string> {
  segments: { key: T; label: string }[];
  selectedKey: T;
  onSelect: (key: T) => void;
  style?: ViewStyle;
  disabled?: boolean;
}

export function SegmentedControl<T extends string>({
  segments,
  selectedKey,
  onSelect,
  style,
  disabled = false,
}: SegmentedControlProps<T>) {
  const [containerWidth, setContainerWidth] = useState(0);
  const selectedIndex = segments.findIndex((s) => s.key === selectedKey);
  const translateX = useSharedValue(0);

  const segmentWidth = containerWidth > 0
    ? (containerWidth - PADDING * 2) / segments.length
    : 0;

  React.useEffect(() => {
    if (segmentWidth > 0) {
      translateX.value = withTiming(selectedIndex * segmentWidth, {
        duration: 200,
      });
    }
  }, [selectedIndex, segmentWidth]);

  const indicatorStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: translateX.value }],
    width: segmentWidth,
  }));

  const handleLayout = (event: LayoutChangeEvent) => {
    setContainerWidth(event.nativeEvent.layout.width);
  };

  return (
    <View style={[styles.container, style]} onLayout={handleLayout}>
      {containerWidth > 0 && (
        <Animated.View style={[styles.indicator, indicatorStyle]} />
      )}

      {segments.map((segment) => {
        const isSelected = segment.key === selectedKey;

        return (
          <TouchableOpacity
            key={segment.key}
            style={styles.segment}
            onPress={() => !disabled && onSelect(segment.key)}
            activeOpacity={0.7}
            disabled={disabled}
          >
            <Text
              style={[
                styles.segmentText,
                isSelected && styles.segmentTextSelected,
                disabled && styles.segmentTextDisabled,
              ]}
            >
              {segment.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
    padding: PADDING,
    height: 48,
    position: 'relative',
  },
  indicator: {
    position: 'absolute',
    top: PADDING,
    bottom: PADDING,
    left: PADDING,
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.sm,
    shadowColor: '#3B4BF5',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  segment: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  segmentText: {
    ...Typography.buttonSmall,
    color: '#666666',
    fontFamily: 'Inter_500Medium',
  },
  segmentTextSelected: {
    color: Colors.text,
    fontFamily: 'Inter_700Bold',
  },
  segmentTextDisabled: {
    opacity: 0.5,
  },
});

export default SegmentedControl;
