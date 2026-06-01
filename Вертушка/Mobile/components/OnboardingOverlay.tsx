/**
 * Interactive Tour Overlay — 10-step spotlight tour driven by tourTargets in store.
 * Renders four dark regions around the spotlight, a pulsing border, and a
 * tooltip card that auto-positions above or below the spotlight.
 */
import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Platform,
  Dimensions,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { Icon } from '@/components/ui';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withRepeat,
  withSequence,
  Easing,
  interpolate,
} from 'react-native-reanimated';
import { useOnboardingStore, useCollectionStore, TourTargetKey } from '../lib/store';
import { Colors } from '../constants/theme';
import { ms } from '../lib/responsive';

const SCREEN = Dimensions.get('window');

interface TourStepConfig {
  target: TourTargetKey;
  route: string;
  title: string;
  body: string;
  radius: number;
  pad: number;
}

const TOUR_STEPS: TourStepConfig[] = [
  {
    target: 'tab-index',
    route: '/(tabs)',
    title: 'Сканер',
    body: 'Наведи камеру на штрихкод или обложку — мы определим пластинку и формат за секунду',
    radius: 30,
    pad: 8,
  },
  {
    target: 'scan-segments',
    route: '/(tabs)',
    title: 'Два режима',
    body: 'Штрихкод для нового, фото обложки — для старого винила без баркода',
    radius: 16,
    pad: 8,
  },
  {
    target: 'tab-search',
    route: '/(tabs)/search',
    title: 'Поиск по Discogs',
    body: '15 миллионов релизов. Ищи по артисту, альбому, треку',
    radius: 30,
    pad: 8,
  },
  {
    target: 'search-filters',
    route: '/(tabs)/search',
    title: 'Фильтры',
    body: 'Винил, CD, кассета, бокс-сет — переключай формат прямо в результатах',
    radius: 22,
    pad: 8,
  },
  {
    target: 'tab-collection',
    route: '/(tabs)/collection',
    title: 'Твоя коллекция',
    body: 'В наличии и вишлист — две вкладки. Свайпай между ними',
    radius: 30,
    pad: 8,
  },
  {
    target: 'collection-view-toggle',
    route: '/(tabs)/collection',
    title: 'Сетка или список',
    body: 'Переключай вид одним тапом',
    radius: 16,
    pad: 6,
  },
  {
    target: 'collection-record-card',
    route: '/(tabs)/collection',
    title: 'Удерживай — выбираешь несколько',
    body: 'Long-press по карточке включит режим выбора — для папок, удаления и подарков сразу пачкой',
    radius: 18,
    pad: 6,
  },
  {
    target: 'collection-folders',
    route: '/(tabs)/collection',
    title: 'Папки',
    body: 'Раскладывай по жанрам, эпохам или своей логике — создавай, переименовывай, удаляй',
    radius: 22,
    pad: 6,
  },
  {
    target: 'collection-value',
    route: '/(tabs)/collection',
    title: 'Сколько стоит твоя коллекция',
    body: 'Тапни по иконке — посчитаем сумму по Discogs marketplace и конвертируем USD → RUB по курсу ЦБ',
    radius: 16,
    pad: 6,
  },
  {
    target: 'profile-share',
    route: '/profile',
    title: 'Публичный профиль',
    body: 'Открой @username — друзья смотрят коллекцию, подписываются и бронируют подарки из вишлиста',
    radius: 22,
    pad: 8,
  },
];

export function OnboardingOverlay() {
  const tourStep = useOnboardingStore((s) => s.tourStep);
  const targets = useOnboardingStore((s) => s.tourTargets);
  const nextStep = useOnboardingStore((s) => s.nextStep);
  const completeTour = useOnboardingStore((s) => s.completeTour);
  const skipTour = useOnboardingStore((s) => s.skipTour);

  // Drive route from current step. Also force collection segment to "В наличии"
  // for steps that highlight folders/value-button — those only render when the
  // collection segment is active.
  useEffect(() => {
    if (tourStep === null) return;
    const step = TOUR_STEPS[tourStep];
    if (!step) return;
    if (step.route.includes('/collection')) {
      useCollectionStore.getState().setActiveTab('collection');
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    router.navigate(step.route as any);
  }, [tourStep]);

  if (tourStep === null) return null;

  const step = TOUR_STEPS[tourStep];
  const target = targets[step.target];
  const isLast = tourStep === TOUR_STEPS.length - 1;

  const handleNext = () => {
    Haptics.selectionAsync();
    if (isLast) {
      completeTour();
      router.replace('/(tabs)');
    } else {
      nextStep();
    }
  };

  const handleSkip = () => {
    Haptics.selectionAsync();
    skipTour();
    router.replace('/(tabs)');
  };

  // While we wait for the target to be measured (after navigation), render a
  // dim screen with the tooltip centered — keeps the tour visible.
  if (!target) {
    return (
      <View style={[StyleSheet.absoluteFill, styles.zTop]} pointerEvents="box-none">
        <View style={[StyleSheet.absoluteFill, styles.dim]} />
        <View style={styles.tipCenter} pointerEvents="box-none">
          <TooltipCard
            stepIndex={tourStep}
            total={TOUR_STEPS.length}
            title={step.title}
            body={step.body}
            onSkip={handleSkip}
            onNext={handleNext}
            isLast={isLast}
          />
        </View>
      </View>
    );
  }

  return (
    <Spotlight
      target={target}
      step={step}
      stepIndex={tourStep}
      total={TOUR_STEPS.length}
      isLast={isLast}
      onSkip={handleSkip}
      onNext={handleNext}
    />
  );
}

interface SpotlightProps {
  target: { x: number; y: number; w: number; h: number };
  step: TourStepConfig;
  stepIndex: number;
  total: number;
  isLast: boolean;
  onSkip: () => void;
  onNext: () => void;
}

function Spotlight({ target, step, stepIndex, total, isLast, onSkip, onNext }: SpotlightProps) {
  const pad = step.pad;
  const sx = Math.max(0, target.x - pad);
  const sy = Math.max(0, target.y - pad);
  const sw = target.w + pad * 2;
  const sh = target.h + pad * 2;

  const screenH = SCREEN.height;
  const screenW = SCREEN.width;

  const centerY = sy + sh / 2;
  const placeAbove = centerY > screenH * 0.55;

  const pulse = useSharedValue(0);
  useEffect(() => {
    pulse.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 800, easing: Easing.inOut(Easing.quad) }),
        withTiming(0, { duration: 800, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      false,
    );
  }, [pulse]);

  const pulseStyle = useAnimatedStyle(() => ({
    shadowOpacity: interpolate(pulse.value, [0, 1], [0.45, 0.85]),
    shadowRadius: interpolate(pulse.value, [0, 1], [12, 22]),
  }));

  return (
    <View style={[StyleSheet.absoluteFill, styles.zTop]} pointerEvents="box-none">
      {/* Four dark regions around spotlight */}
      <View style={[styles.dim, { top: 0, left: 0, right: 0, height: sy }]} pointerEvents="auto" />
      <View
        style={[styles.dim, { top: sy, left: 0, width: sx, height: sh }]}
        pointerEvents="auto"
      />
      <View
        style={[styles.dim, { top: sy, left: sx + sw, right: 0, height: sh }]}
        pointerEvents="auto"
      />
      <View
        style={[styles.dim, { top: sy + sh, left: 0, right: 0, bottom: 0 }]}
        pointerEvents="auto"
      />

      {/* Spotlight border (pulsing) */}
      <Animated.View
        style={[
          styles.spotlightBorder,
          {
            top: sy,
            left: sx,
            width: sw,
            height: sh,
            borderRadius: step.radius,
          },
          pulseStyle,
        ]}
        pointerEvents="auto"
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onNext} />
      </Animated.View>

      {/* Tooltip */}
      <View
        style={[
          styles.tipWrap,
          placeAbove
            ? { top: Math.max(60, sy - 200) }
            : { top: Math.min(screenH - 240, sy + sh + 16) },
          { width: screenW - 32 },
        ]}
        pointerEvents="box-none"
      >
        <TooltipCard
          stepIndex={stepIndex}
          total={total}
          title={step.title}
          body={step.body}
          onSkip={onSkip}
          onNext={onNext}
          isLast={isLast}
        />
      </View>
    </View>
  );
}

interface TooltipCardProps {
  stepIndex: number;
  total: number;
  title: string;
  body: string;
  onSkip: () => void;
  onNext: () => void;
  isLast: boolean;
}

function TooltipCard({ stepIndex, total, title, body, onSkip, onNext, isLast }: TooltipCardProps) {
  const progress = useSharedValue(0);
  useEffect(() => {
    progress.value = withTiming((stepIndex + 1) / total, { duration: 280, easing: Easing.bezier(0.22, 0.61, 0.36, 1) });
  }, [stepIndex, total, progress]);

  const fillStyle = useAnimatedStyle(() => ({
    width: `${progress.value * 100}%` as `${number}%`,
  }));

  const Wrap = Platform.OS === 'android' ? AndroidTooltipWrap : IosTooltipWrap;

  return (
    <Wrap>
      <View style={styles.tipProgressRow}>
        <Text style={styles.tipProgressNum}>{stepIndex + 1}</Text>
        <Text style={styles.tipProgressSep}>/</Text>
        <Text style={styles.tipProgressTotal}>{total}</Text>
        <View style={styles.tipBar}>
          <Animated.View style={[styles.tipBarFill, fillStyle]} />
        </View>
      </View>
      <Text style={styles.tipTitle}>{title}</Text>
      <Text style={styles.tipBody}>{body}</Text>
      <View style={styles.tipActions}>
        <Pressable onPress={onSkip} hitSlop={10}>
          <Text style={styles.tipSkip}>Пропустить</Text>
        </Pressable>
        <Pressable onPress={onNext} style={({ pressed }) => [styles.tipNext, pressed && styles.tipNextPressed]}>
          <Text style={styles.tipNextText}>{isLast ? 'Готово!' : 'Дальше'}</Text>
        </Pressable>
      </View>
    </Wrap>
  );
}

function IosTooltipWrap({ children }: { children: React.ReactNode }) {
  return (
    <BlurView intensity={28} tint="light" style={styles.tipBlur}>
      <View style={styles.tipInner}>{children}</View>
    </BlurView>
  );
}

function AndroidTooltipWrap({ children }: { children: React.ReactNode }) {
  return (
    <View style={[styles.tipBlur, styles.tipAndroid]}>
      <View style={styles.tipInner}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  zTop: {
    zIndex: 9999,
  },
  dim: {
    position: 'absolute',
    backgroundColor: 'rgba(15, 27, 76, 0.6)',
  },
  spotlightBorder: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: 'rgba(255, 255, 255, 0.85)',
    backgroundColor: 'transparent',
    shadowColor: '#fff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.45,
    shadowRadius: 16,
  },
  tipWrap: {
    position: 'absolute',
    left: 16,
    right: 16,
  },
  tipCenter: {
    flex: 1,
    paddingHorizontal: 24,
    alignItems: 'stretch',
    justifyContent: 'center',
  },
  tipBlur: {
    borderRadius: 20,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.8)',
    shadowColor: '#0F1B4C',
    shadowOffset: { width: 0, height: 24 },
    shadowOpacity: 0.35,
    shadowRadius: 30,
    elevation: 12,
  },
  tipAndroid: {
    backgroundColor: 'rgba(250, 251, 255, 0.97)',
  },
  tipInner: {
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 16,
    backgroundColor: 'rgba(250, 251, 255, 0.92)',
  },
  tipProgressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  tipProgressNum: {
    fontFamily: 'Inter_700Bold',
    fontSize: 13,
    color: Colors.royalBlue,
    letterSpacing: -0.2,
  },
  tipProgressSep: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: '#8E97B5',
    marginHorizontal: 2,
  },
  tipProgressTotal: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 13,
    color: '#5A6585',
  },
  tipBar: {
    flex: 1,
    height: 4,
    backgroundColor: 'rgba(15, 27, 76, 0.08)',
    borderRadius: 2,
    overflow: 'hidden',
    marginLeft: 10,
  },
  tipBarFill: {
    height: '100%',
    backgroundColor: Colors.royalBlue,
    borderRadius: 2,
  },
  tipTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(19),
    lineHeight: ms(23),
    color: '#0F1B4C',
    letterSpacing: -0.4,
    marginBottom: 6,
  },
  tipBody: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(14),
    lineHeight: ms(20),
    color: '#5A6585',
    marginBottom: 14,
  },
  tipActions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  tipSkip: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(13),
    color: '#8E97B5',
    paddingHorizontal: 4,
    paddingVertical: 8,
  },
  tipNext: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: Colors.royalBlue,
    borderRadius: 9999,
    shadowColor: Colors.royalBlue,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 14,
  },
  tipNextPressed: {
    transform: [{ scale: 0.97 }],
  },
  tipNextText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: ms(14),
    color: '#fff',
  },
});
