/**
 * Onboarding Welcome Carousel — 4 steps with swipe + paginator
 */
import { useEffect, useMemo } from 'react';
import { View, Text, StyleSheet, Pressable, Dimensions, Platform } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { BlurView } from 'expo-blur';
import { Icon } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withRepeat,
  withSequence,
  Easing,
  runOnJS,
  interpolate,
  SharedValue,
} from 'react-native-reanimated';
import { useOnboardingStore } from '../lib/store';
import { Colors } from '../constants/theme';
import { ms } from '../lib/responsive';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface WelcomeStep {
  icon: string;
  eyebrow: string;
  title: string;
  body: string;
}

const STEPS: WelcomeStep[] = [
  {
    icon: 'disc-outline',
    eyebrow: 'Знакомство',
    title: 'Вертушка',
    body: 'Твоя коллекция винила, CD и кассет — в одном месте',
  },
  {
    icon: 'search-outline',
    eyebrow: 'Каталог 15M+ релизов',
    title: 'Найди что угодно',
    body: 'База Discogs прямо в приложении — артисты, альбомы, версии релизов',
  },
  {
    icon: 'scan-outline',
    eyebrow: 'Сканируй вместо ввода',
    title: 'Просто наведи камеру',
    body: 'Штрихкод или фото обложки — мы сами найдём пластинку и определим формат',
  },
  {
    icon: 'gift-outline',
    eyebrow: 'Делись и собирай подарки',
    title: 'Профиль и вишлист',
    body: 'Поделись ссылкой @username — друзья забронируют подарок одной кнопкой',
  },
];

function Blob({
  color,
  size,
  initialX,
  initialY,
  duration,
}: {
  color: string;
  size: number;
  initialX: number;
  initialY: number;
  duration: number;
}) {
  const t = useSharedValue(0);

  useEffect(() => {
    t.value = withRepeat(
      withSequence(
        withTiming(1, { duration, easing: Easing.inOut(Easing.quad) }),
        withTiming(0, { duration, easing: Easing.inOut(Easing.quad) }),
      ),
      -1,
      false,
    );
  }, [duration, t]);

  const style = useAnimatedStyle(() => ({
    transform: [
      { translateX: interpolate(t.value, [0, 1], [0, 40]) },
      { translateY: interpolate(t.value, [0, 1], [0, -40]) },
      { scale: interpolate(t.value, [0, 1], [1, 1.15]) },
    ],
  }));

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.blob,
        {
          backgroundColor: color,
          width: size,
          height: size,
          left: initialX,
          top: initialY,
        },
        style,
      ]}
    />
  );
}

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { completeWelcome, startTour, completeTour } = useOnboardingStore();

  const step = useSharedValue(0);
  const dragX = useSharedValue(0);

  const goToTabs = (skipTour: boolean) => {
    completeWelcome();
    if (skipTour) {
      completeTour();
    } else {
      startTour();
    }
    router.replace('/(tabs)');
  };

  const goNext = () => {
    Haptics.selectionAsync();
    const current = Math.round(step.value);
    if (current >= STEPS.length - 1) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      goToTabs(false);
    } else {
      step.value = withTiming(current + 1, {
        duration: 360,
        easing: Easing.bezier(0.22, 0.61, 0.36, 1),
      });
    }
  };

  const onSkip = () => {
    Haptics.selectionAsync();
    goToTabs(true);
  };

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activeOffsetX([-10, 10])
        .onChange((e) => {
          dragX.value = e.translationX;
        })
        .onEnd((e) => {
          const current = Math.round(step.value);
          let next = current;
          if (e.translationX < -60 && current < STEPS.length - 1) next = current + 1;
          else if (e.translationX > 60 && current > 0) next = current - 1;
          dragX.value = withTiming(0, { duration: 200 });
          if (next !== current) {
            step.value = withTiming(next, {
              duration: 360,
              easing: Easing.bezier(0.22, 0.61, 0.36, 1),
            });
            runOnJS(Haptics.selectionAsync)();
          }
        }),
    [dragX, step],
  );

  const trackStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: -step.value * SCREEN_WIDTH + dragX.value }],
  }));

  return (
    <View style={styles.root}>
      <LinearGradient
        colors={['#0F1B4C', '#3B4BF5', '#C5B8F2', '#F0C4D8']}
        locations={[0, 0.38, 0.72, 1]}
        start={{ x: 0.05, y: 0 }}
        end={{ x: 0.95, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      {/* Animated blobs */}
      <View style={StyleSheet.absoluteFill} pointerEvents="none">
        <Blob color="#C5B8F2" size={380} initialX={-100} initialY={-120} duration={7000} />
        <Blob color="#F0C4D8" size={380} initialX={SCREEN_WIDTH - 260} initialY={500} duration={8000} />
        <Blob color="#5B6AF5" size={300} initialX={SCREEN_WIDTH * 0.3} initialY={300} duration={6000} />
      </View>

      <SkipButton visible insets={insets} onPress={onSkip} stepShared={step} totalSteps={STEPS.length} />

      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.track, { width: SCREEN_WIDTH * STEPS.length }, trackStyle]}>
          {STEPS.map((s, i) => (
            <View key={i} style={[styles.slide, { width: SCREEN_WIDTH }]}>
              <View style={[styles.cardWrap, { paddingTop: insets.top + 60 }]}>
                <BlurViewCompat>
                  <View style={styles.card}>
                    <View style={styles.iconRing}>
                      <Icon name={s.icon} size={56} color="#fff" />
                    </View>
                    <Text style={styles.eyebrow}>{s.eyebrow}</Text>
                    <Text style={styles.title}>{s.title}</Text>
                    <Text style={styles.body}>{s.body}</Text>
                  </View>
                </BlurViewCompat>
              </View>
            </View>
          ))}
        </Animated.View>
      </GestureDetector>

      <View style={[styles.foot, { paddingBottom: insets.bottom + 24 }]} pointerEvents="box-none">
        <Dots step={step} total={STEPS.length} />
        <Pressable
          style={({ pressed }) => [styles.cta, pressed && styles.ctaPressed]}
          onPress={goNext}
        >
          <CtaLabel step={step} totalSteps={STEPS.length} />
        </Pressable>
      </View>
    </View>
  );
}

function BlurViewCompat({ children }: { children: React.ReactNode }) {
  if (Platform.OS === 'android') {
    return <View style={styles.cardAndroidFallback}>{children}</View>;
  }
  return (
    <BlurView intensity={28} tint="light" style={styles.cardBlur}>
      {children}
    </BlurView>
  );
}

function SkipButton({
  insets,
  onPress,
  stepShared,
  totalSteps,
}: {
  visible: boolean;
  insets: { top: number };
  onPress: () => void;
  stepShared: SharedValue<number>;
  totalSteps: number;
}) {
  const style = useAnimatedStyle(() => ({
    opacity: withTiming(stepShared.value >= totalSteps - 1 ? 0 : 1, { duration: 200 }),
  }));
  return (
    <Animated.View style={[styles.skip, { top: insets.top + 14 }, style]} pointerEvents="box-none">
      <Pressable onPress={onPress} hitSlop={12} style={styles.skipPress}>
        <Text style={styles.skipText}>Пропустить</Text>
      </Pressable>
    </Animated.View>
  );
}

function Dots({ step, total }: { step: SharedValue<number>; total: number }) {
  return (
    <View style={styles.dots}>
      {Array.from({ length: total }).map((_, i) => (
        <Dot key={i} index={i} step={step} />
      ))}
    </View>
  );
}

function Dot({ index, step }: { index: number; step: SharedValue<number> }) {
  const style = useAnimatedStyle(() => {
    const distance = Math.abs(step.value - index);
    const active = Math.max(0, 1 - distance);
    return {
      width: 8 + 18 * active,
      backgroundColor: `rgba(255, 255, 255, ${0.35 + 0.65 * active})`,
    };
  });
  return <Animated.View style={[styles.dot, style]} />;
}

function CtaLabel({
  step,
  totalSteps,
}: {
  step: SharedValue<number>;
  totalSteps: number;
}) {
  // Two text layers cross-fade: "Далее" (index < last) → "Поехали!" (index === last)
  const nextStyle = useAnimatedStyle(() => ({
    opacity: withTiming(step.value < totalSteps - 1 ? 1 : 0, { duration: 180 }),
  }));
  const finalStyle = useAnimatedStyle(() => ({
    opacity: withTiming(step.value >= totalSteps - 1 ? 1 : 0, { duration: 180 }),
  }));
  return (
    <View style={styles.ctaLabelWrap}>
      <Animated.Text style={[styles.ctaText, nextStyle]}>Далее</Animated.Text>
      <Animated.Text style={[styles.ctaText, styles.ctaTextAbsolute, finalStyle]}>Поехали!</Animated.Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#0F1B4C',
    overflow: 'hidden',
  },
  blob: {
    position: 'absolute',
    borderRadius: 9999,
    opacity: 0.45,
  },
  skip: {
    position: 'absolute',
    right: 20,
    zIndex: 30,
  },
  skipPress: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: 'rgba(255,255,255,0.16)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.22)',
  },
  skipText: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(14),
    color: 'rgba(255,255,255,0.92)',
  },
  track: {
    flex: 1,
    flexDirection: 'row',
  },
  slide: {
    height: '100%',
    paddingHorizontal: 28,
    paddingBottom: 200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  cardWrap: {
    width: '100%',
    paddingHorizontal: 0,
  },
  cardBlur: {
    width: '100%',
    borderRadius: 26,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.28)',
  },
  cardAndroidFallback: {
    width: '100%',
    borderRadius: 26,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.28)',
    backgroundColor: 'rgba(255,255,255,0.18)',
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.16)',
    paddingHorizontal: 28,
    paddingTop: 36,
    paddingBottom: 32,
    alignItems: 'center',
    shadowColor: '#0F1B4C',
    shadowOpacity: 0.35,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: 24 },
  },
  iconRing: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: 'rgba(255,255,255,0.18)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.35)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 22,
  },
  eyebrow: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: ms(11),
    letterSpacing: 1.6,
    color: 'rgba(255,255,255,0.78)',
    textTransform: 'uppercase',
    marginBottom: 14,
  },
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(36),
    lineHeight: ms(38),
    letterSpacing: -1,
    color: '#fff',
    textAlign: 'center',
    marginBottom: 14,
  },
  body: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(16),
    lineHeight: ms(23),
    color: 'rgba(255,255,255,0.88)',
    textAlign: 'center',
    paddingHorizontal: 8,
  },
  foot: {
    position: 'absolute',
    bottom: 0,
    left: 24,
    right: 24,
    alignItems: 'center',
    gap: 22,
  },
  dots: {
    flexDirection: 'row',
    gap: 8,
    height: 8,
  },
  dot: {
    height: 8,
    borderRadius: 4,
  },
  cta: {
    width: '100%',
    height: 54,
    borderRadius: 18,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#0F1B4C',
    shadowOpacity: 0.35,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 14 },
    elevation: 8,
  },
  ctaPressed: {
    transform: [{ scale: 0.98 }],
  },
  ctaLabelWrap: {
    height: 22,
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 120,
  },
  ctaText: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(17),
    letterSpacing: -0.2,
    color: Colors.royalBlue,
    textAlign: 'center',
  },
  ctaTextAbsolute: {
    position: 'absolute',
  },
});
