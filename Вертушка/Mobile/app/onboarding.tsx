/**
 * Welcome — три слайда обещания и развилка «с чего начнём».
 *
 * Было: четыре слайда фич + сразу за ними десятишаговый spotlight-тур, то есть
 * четырнадцать экранов до первого собственного действия. К середине их
 * пролистывали не читая.
 *
 * Стало: три слайда про то, ЗАЧЕМ приложение, и финальный экран, который
 * спрашивает, с чего начать. Дальше человек попадает не в пустую коллекцию,
 * а в конкретный сценарий; всё остальное объясняют чеклист «Первые шаги» и
 * контекстные подсказки — тогда, когда фича становится доступной.
 *
 * Импорт из Discogs вынесен сюда из «Настроек» намеренно: человек с уже
 * перенесённой коллекцией сразу получает работающие папки, ценность, zoom и
 * Радар, тогда как пустой аккаунт всему этому не рад.
 */
import { useEffect, useMemo, useState } from 'react';
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
  useAnimatedReaction,
  SharedValue,
} from 'react-native-reanimated';
import { useOnboardingStore } from '../lib/store';
import { analytics } from '../lib/analytics';
import { Colors } from '../constants/theme';
import { ms } from '../lib/responsive';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

interface WelcomeStep {
  icon: string;
  eyebrow: string;
  title: string;
  body: string;
}

/**
 * Три слайда — про обещание, а не про кнопки. Каталог и сканер склеены в один:
 * для новичка это одна мысль «найти пластинку», а не две разные фичи.
 */
const STEPS: WelcomeStep[] = [
  {
    icon: 'disc-outline',
    eyebrow: 'Знакомство',
    title: 'Вертушка',
    body: 'Твоя коллекция винила, CD и кассет — в одном месте',
  },
  {
    icon: 'scan-outline',
    eyebrow: 'Каталог 15M+ релизов',
    title: 'Найди что угодно',
    body: 'Наведи камеру на штрихкод или обложку — или ищи по базе Discogs руками',
  },
  {
    icon: 'gift-outline',
    eyebrow: 'Вишлист, который работает',
    title: 'Не только список',
    body: 'Радар ловит падение цены, Маркет показывает, где купить, а друзья заберут пластинку тебе в подарок',
  },
];

/** Варианты старта. `route === null` — «осмотреться», просто уходим в табы. */
interface StartOption {
  icon: string;
  title: string;
  subtitle: string;
  route: string | null;
  analyticsId: 'scan' | 'discogs_import' | 'search';
}

const START_OPTIONS: StartOption[] = [
  {
    icon: 'scan-outline',
    title: 'Отсканировать пластинку',
    subtitle: 'Штрихкод или обложка — определим за секунду',
    route: '/(tabs)',
    analyticsId: 'scan',
  },
  {
    icon: 'disc-outline',
    title: 'Перенести коллекцию из Discogs',
    subtitle: 'Подключи аккаунт — заберём всё разом',
    route: '/settings/discogs',
    analyticsId: 'discogs_import',
  },
  {
    icon: 'search-outline',
    title: 'Найти вручную',
    subtitle: 'Артист, альбом или трек',
    route: '/(tabs)/search',
    analyticsId: 'search',
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

/** Последний экран карусели — развилка, а не ещё один слайд. */
const FORK_INDEX = STEPS.length;
const TOTAL_SCREENS = STEPS.length + 1;

export default function OnboardingScreen() {
  const insets = useSafeAreaInsets();
  const { completeWelcome } = useOnboardingStore();

  const step = useSharedValue(0);
  const dragX = useSharedValue(0);

  // Прозрачный подвал всё равно перехватывает касания, а на развилке под ним
  // лежит «Осмотреться самому». pointerEvents из useAnimatedStyle задать
  // нельзя, поэтому дублируем позицию в React-стейт.
  const [atFork, setAtFork] = useState(false);
  useAnimatedReaction(
    () => step.value >= FORK_INDEX - 0.5,
    (isFork, prev) => {
      if (isFork !== prev) runOnJS(setAtFork)(isFork);
    },
    [],
  );

  const finish = (option: StartOption | null) => {
    completeWelcome();
    analytics.onboardingStartChoice(option?.analyticsId ?? 'explore');
    // Всегда сначала табы: экран импорта Discogs — модалка поверх них, и без
    // этого «назад» из неё вело бы обратно в онбординг.
    router.replace('/(tabs)');
    if (option?.route && option.route !== '/(tabs)') {
      router.push(option.route as never);
    }
  };

  const goNext = () => {
    Haptics.selectionAsync();
    const current = Math.round(step.value);
    if (current >= FORK_INDEX) return;
    step.value = withTiming(current + 1, {
      duration: 360,
      easing: Easing.bezier(0.22, 0.61, 0.36, 1),
    });
  };

  const onSkip = () => {
    Haptics.selectionAsync();
    // «Пропустить» ведёт на развилку, а не мимо неё: вопрос «с чего начать»
    // и есть самая полезная часть онбординга.
    step.value = withTiming(FORK_INDEX, {
      duration: 320,
      easing: Easing.bezier(0.22, 0.61, 0.36, 1),
    });
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
          if (e.translationX < -60 && current < TOTAL_SCREENS - 1) next = current + 1;
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

  // Подвал (точки + «Далее») не нужен на развилке — там свои кнопки.
  const footStyle = useAnimatedStyle(() => ({
    opacity: withTiming(step.value >= FORK_INDEX - 0.5 ? 0 : 1, { duration: 200 }),
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

      <SkipButton insets={insets} onPress={onSkip} stepShared={step} forkIndex={FORK_INDEX} />

      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.track, { width: SCREEN_WIDTH * TOTAL_SCREENS }, trackStyle]}>
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

          <View style={[styles.slide, styles.forkSlide, { width: SCREEN_WIDTH }]}>
            <View style={{ paddingTop: insets.top + 40, width: '100%' }}>
              <Text style={styles.forkTitle}>С чего начнём?</Text>
              <Text style={styles.forkSubtitle}>
                Полка заполняется быстрее, чем кажется
              </Text>

              <View style={styles.forkOptions}>
                {START_OPTIONS.map((option) => (
                  <Pressable
                    key={option.analyticsId}
                    style={({ pressed }) => [styles.forkOption, pressed && styles.forkOptionPressed]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                      finish(option);
                    }}
                    accessibilityRole="button"
                    accessibilityLabel={option.title}
                  >
                    <View style={styles.forkIcon}>
                      <Icon name={option.icon} size={24} color="#fff" />
                    </View>
                    <View style={styles.forkTextWrap}>
                      <Text style={styles.forkOptionTitle}>{option.title}</Text>
                      <Text style={styles.forkOptionSubtitle}>{option.subtitle}</Text>
                    </View>
                    <Icon name="chevron-forward" size={18} color="rgba(255,255,255,0.7)" />
                  </Pressable>
                ))}
              </View>

              <Pressable
                onPress={() => {
                  Haptics.selectionAsync();
                  finish(null);
                }}
                style={styles.forkExplore}
                hitSlop={10}
                accessibilityRole="button"
              >
                <Text style={styles.forkExploreText}>Осмотреться самому</Text>
              </Pressable>
            </View>
          </View>
        </Animated.View>
      </GestureDetector>

      <Animated.View
        style={[styles.foot, { paddingBottom: insets.bottom + 24 }, footStyle]}
        pointerEvents={atFork ? 'none' : 'box-none'}
      >
        <Dots step={step} total={TOTAL_SCREENS} />
        <Pressable
          style={({ pressed }) => [styles.cta, pressed && styles.ctaPressed]}
          onPress={goNext}
        >
          <Text style={styles.ctaText}>Далее</Text>
        </Pressable>
      </Animated.View>
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
  forkIndex,
}: {
  insets: { top: number };
  onPress: () => void;
  stepShared: SharedValue<number>;
  forkIndex: number;
}) {
  const style = useAnimatedStyle(() => ({
    opacity: withTiming(stepShared.value >= forkIndex - 0.5 ? 0 : 1, { duration: 200 }),
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
  forkSlide: {
    // У развилки нет подвала с «Далее», поэтому нижний отступ ей не нужен —
    // иначе кнопки уезжают вверх и на маленьких экранах жмутся друг к другу.
    paddingBottom: 40,
    justifyContent: 'center',
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
  forkTitle: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(32),
    lineHeight: ms(36),
    letterSpacing: -0.8,
    color: '#fff',
    textAlign: 'center',
  },
  forkSubtitle: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(15),
    lineHeight: ms(21),
    color: 'rgba(255,255,255,0.8)',
    textAlign: 'center',
    marginTop: 8,
    marginBottom: 28,
  },
  forkOptions: {
    gap: 12,
  },
  forkOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.16)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.26)',
  },
  forkOptionPressed: {
    transform: [{ scale: 0.98 }],
    backgroundColor: 'rgba(255,255,255,0.24)',
  },
  forkIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.18)',
  },
  forkTextWrap: {
    flex: 1,
  },
  forkOptionTitle: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: ms(16),
    color: '#fff',
    marginBottom: 2,
  },
  forkOptionSubtitle: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(13),
    lineHeight: ms(17),
    color: 'rgba(255,255,255,0.76)',
  },
  forkExplore: {
    alignSelf: 'center',
    marginTop: 22,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  forkExploreText: {
    fontFamily: 'Inter_500Medium',
    fontSize: ms(15),
    color: 'rgba(255,255,255,0.88)',
    textDecorationLine: 'underline',
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
  ctaText: {
    fontFamily: 'Inter_700Bold',
    fontSize: ms(17),
    letterSpacing: -0.2,
    color: Colors.royalBlue,
    textAlign: 'center',
  },
});
