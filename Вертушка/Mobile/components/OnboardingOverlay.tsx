/**
 * Onboarding Tooltip Tour Overlay
 * Полупрозрачный оверлей с подсказками поверх реального UI
 */
import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Dimensions,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { useOnboardingStore } from '../lib/store';
import { Colors, Typography, BorderRadius, Spacing } from '../constants/theme';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const SPOTLIGHT_HORIZONTAL_PADDING = 24;

interface TourStepConfig {
  title: string;
  description: string;
  /** Y offset from safe area top */
  spotlightOffsetY: number;
  spotlightHeight: number;
  route: string;
}

const TOUR_STEPS: TourStepConfig[] = [
  {
    title: 'Сканирование',
    description: 'Сканируй штрихкод или сфотографируй обложку — мы найдём пластинку автоматически',
    // Scan tab: title ~60px + gap → segmented control starts ~70px from safe area top
    spotlightOffsetY: 60,
    spotlightHeight: 60,
    route: '/(tabs)',
  },
  {
    title: 'Поиск',
    description: 'Ищи по каталогу: артисты, альбомы, релизы. Используй фильтры по формату, стране и десятилетию',
    // Search tab: title row ~60px → search bar starts ~70px
    spotlightOffsetY: 65,
    spotlightHeight: 58,
    route: '/(tabs)/search',
  },
  {
    title: 'Коллекция',
    description: 'Управляй коллекцией и вишлистом. Создавай папки, сортируй и следи за стоимостью пластинок',
    // Collection tab: title ~55px + toolbar ~50px → segment control starts ~115px, + folders ~130px
    spotlightOffsetY: 105,
    spotlightHeight: 200,
    route: '/(tabs)/collection',
  },
];

export function OnboardingOverlay() {
  const insets = useSafeAreaInsets();
  const { tourStep, nextStep, completeTour, skipTour } = useOnboardingStore();

  useEffect(() => {
    if (tourStep === null) return;
    const step = TOUR_STEPS[tourStep];
    router.navigate(step.route as any);
  }, [tourStep]);

  if (tourStep === null) return null;

  const currentStep = TOUR_STEPS[tourStep];
  const isLastStep = tourStep === TOUR_STEPS.length - 1;

  const handleNext = () => {
    if (isLastStep) {
      completeTour();
    } else {
      nextStep();
    }
  };

  const spotlightTop = insets.top + currentStep.spotlightOffsetY;
  const spotlightBottom = spotlightTop + currentStep.spotlightHeight;
  const spotlightLeft = SPOTLIGHT_HORIZONTAL_PADDING;
  const spotlightRight = SCREEN_WIDTH - SPOTLIGHT_HORIZONTAL_PADDING;
  const spotlightWidth = spotlightRight - spotlightLeft;

  return (
    <Animated.View
      entering={FadeIn.duration(300)}
      exiting={FadeOut.duration(200)}
      style={styles.overlay}
      pointerEvents="box-none"
    >
      {/* Top dark region */}
      <View style={[styles.dark, { top: 0, left: 0, right: 0, height: spotlightTop }]} />
      {/* Left dark region */}
      <View style={[styles.dark, { top: spotlightTop, left: 0, width: spotlightLeft, height: currentStep.spotlightHeight }]} />
      {/* Right dark region */}
      <View style={[styles.dark, { top: spotlightTop, right: 0, width: SCREEN_WIDTH - spotlightRight, height: currentStep.spotlightHeight }]} />
      {/* Bottom dark region */}
      <View style={[styles.dark, { top: spotlightBottom, left: 0, right: 0, bottom: 0 }]} />

      {/* Spotlight border */}
      <View
        style={[
          styles.spotlightBorder,
          {
            top: spotlightTop - 2,
            left: spotlightLeft - 2,
            width: spotlightWidth + 4,
            height: currentStep.spotlightHeight + 4,
          },
        ]}
      />

      {/* Tap catcher on dark areas */}
      <Pressable style={StyleSheet.absoluteFill} onPress={handleNext} />

      {/* Tooltip card */}
      <View style={[styles.tooltipContainer, { top: spotlightBottom + 20 }]}>
        <BlurView intensity={80} tint="light" style={styles.tooltipBlur}>
          <View style={styles.tooltipContent}>
            <View style={styles.stepIndicator}>
              {TOUR_STEPS.map((_, i) => (
                <View
                  key={i}
                  style={[styles.dot, i === tourStep && styles.dotActive]}
                />
              ))}
            </View>

            <Text style={styles.tooltipTitle}>{currentStep.title}</Text>
            <Text style={styles.tooltipDescription}>{currentStep.description}</Text>

            <View style={styles.tooltipActions}>
              <Pressable onPress={skipTour} style={styles.skipLink}>
                <Text style={styles.skipLinkText}>Пропустить</Text>
              </Pressable>
              <Pressable style={styles.nextButton} onPress={handleNext}>
                <Text style={styles.nextButtonText}>
                  {isLastStep ? 'Готово' : 'Далее'}
                </Text>
              </Pressable>
            </View>
          </View>
        </BlurView>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 9999,
  },
  dark: {
    position: 'absolute',
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
  },
  spotlightBorder: {
    position: 'absolute',
    borderRadius: BorderRadius.lg,
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.4)',
  },
  tooltipContainer: {
    position: 'absolute',
    left: Spacing.md,
    right: Spacing.md,
  },
  tooltipBlur: {
    borderRadius: BorderRadius.lg,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
  },
  tooltipContent: {
    padding: Spacing.lg,
    backgroundColor: 'rgba(250, 251, 255, 0.75)',
  },
  stepIndicator: {
    flexDirection: 'row',
    gap: 6,
    marginBottom: Spacing.md,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.border,
  },
  dotActive: {
    backgroundColor: Colors.royalBlue,
    width: 24,
  },
  tooltipTitle: {
    ...Typography.h4,
    color: Colors.text,
    marginBottom: Spacing.xs,
  },
  tooltipDescription: {
    ...Typography.body,
    color: Colors.textSecondary,
    marginBottom: Spacing.lg,
  },
  tooltipActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  skipLink: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.sm,
  },
  skipLinkText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  nextButton: {
    backgroundColor: Colors.royalBlue,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm + 2,
    borderRadius: BorderRadius.full,
  },
  nextButtonText: {
    ...Typography.button,
    color: '#fff',
    fontSize: 14,
  },
});
