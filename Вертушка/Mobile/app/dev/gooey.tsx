/**
 * PLAYGROUND — gooey-почкование (митоз) на Reanimated + react-native-svg.
 * Работает в Expo Go (без Skia/dev-build).
 *
 * Механика прототипа входа в «ручное добавление пластинки»:
 *   long-press по центральной кнопке туллбара + свайп вверх → из туллбара
 *   ПОЧКУЕТСЯ glass-капля, между ними тянется metaball-перемычка, она
 *   истончается и рвётся (деление клетки). Отпускание:
 *     — выше порога → «открытие» (тут просто вспышка + сброс)
 *     — ниже порога → упругое слияние почки назад в туллбар.
 *   Через 5с бездействия центральная иконка «стучится» о туллбар (attention).
 *
 * Маршрут: /dev/gooey
 * Тюнинг живьём: R_PARENT / R_BUD / CONNECT_K / BUD_MAX_LIFT / OPEN_THRESHOLD.
 */
import { useEffect } from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';
import Svg, { Path, Circle } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  useAnimatedStyle,
  withSpring,
  withRepeat,
  withSequence,
  withTiming,
  withDelay,
  cancelAnimation,
  runOnJS,
} from 'react-native-reanimated';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

const { width: SCREEN_W } = Dimensions.get('window');

// ─── Тюнинг-константы ────────────────────────────────────────────────────────
const R_PARENT = 30; // радиус «родителя» в туллбаре
const R_BUD = 26; // радиус почки
const CONNECT_K = 2.4; // кривизна перемычки (handleSize)
const BUD_MAX_LIFT = 200; // максимальный подъём почки пальцем
const OPEN_THRESHOLD = 130; // порог свайпа для «открытия»
const COBALT = '#3B4BF5';

// ─── Геометрия metaball (worklet) ────────────────────────────────────────────
// Классический metaball-коннектор: по двум кругам строит замкнутый path-мост
// с 4 касательными точками и 2 bezier-контролами. Возвращает '' когда круги
// слишком далеко (перемычка разорвана) или один внутри другого.

function dist(ax: number, ay: number, bx: number, by: number): number {
  'worklet';
  return Math.hypot(bx - ax, by - ay);
}

function ptStr(cx: number, cy: number, angle: number, r: number): [number, number] {
  'worklet';
  return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
}

function metaballPath(
  cx1: number,
  cy1: number,
  r1: number,
  cx2: number,
  cy2: number,
  r2: number,
  handleK: number,
  v: number,
): string {
  'worklet';
  const d = dist(cx1, cy1, cx2, cy2);
  if (r1 === 0 || r2 === 0) return '';
  // Разрыв: дальше суммы радиусов (с запасом) или один внутри другого.
  if (d > r1 + r2 || d <= Math.abs(r1 - r2)) return '';

  const u1 = Math.acos((r1 * r1 + d * d - r2 * r2) / (2 * r1 * d));
  const u2 = Math.acos((r2 * r2 + d * d - r1 * r1) / (2 * r2 * d));
  const angleBetween = Math.atan2(cy2 - cy1, cx2 - cx1);
  const maxSpread = Math.acos((r1 - r2) / d);

  const angle1 = angleBetween + u1 + (maxSpread - u1) * v;
  const angle2 = angleBetween - u1 - (maxSpread - u1) * v;
  const angle3 = angleBetween + Math.PI - u2 - (Math.PI - u2 - maxSpread) * v;
  const angle4 = angleBetween - Math.PI + u2 + (Math.PI - u2 - maxSpread) * v;

  const [p1x, p1y] = ptStr(cx1, cy1, angle1, r1);
  const [p2x, p2y] = ptStr(cx1, cy1, angle2, r1);
  const [p3x, p3y] = ptStr(cx2, cy2, angle3, r2);
  const [p4x, p4y] = ptStr(cx2, cy2, angle4, r2);

  const totalRadius = r1 + r2;
  const dBase = Math.min(v * handleK, dist(p1x, p1y, p3x, p3y) / totalRadius);
  const d2 = dBase * Math.min(1, (d * 2) / (r1 + r2));
  const r1h = r1 * d2;
  const r2h = r2 * d2;

  const [h1x, h1y] = ptStr(p1x, p1y, angle1 - Math.PI / 2, r1h);
  const [h2x, h2y] = ptStr(p2x, p2y, angle2 + Math.PI / 2, r1h);
  const [h3x, h3y] = ptStr(p3x, p3y, angle3 + Math.PI / 2, r2h);
  const [h4x, h4y] = ptStr(p4x, p4y, angle4 - Math.PI / 2, r2h);

  return (
    `M ${p1x},${p1y} ` +
    `C ${h1x},${h1y} ${h3x},${h3y} ${p3x},${p3y} ` +
    `L ${p4x},${p4y} ` +
    `C ${h4x},${h4y} ${h2x},${h2y} ${p2x},${p2y} Z`
  );
}

// ─── Экран ───────────────────────────────────────────────────────────────────

export default function GooeyPlayground() {
  const insets = useSafeAreaInsets();

  // Геометрия: родитель — центр туллбара; почка едет вверх на `lift`.
  // baseY с запасом сверху, чтобы поднятая почка не обрезалась краем Svg.
  const cx = SCREEN_W / 2;
  const baseY = BUD_MAX_LIFT + R_BUD + 20; // 246
  const canvasH = baseY + R_PARENT + 8;

  const lift = useSharedValue(0); // 0..BUD_MAX_LIFT
  const bounce = useSharedValue(0); // attention-bounce центральной иконки
  const broke = useSharedValue(0); // 0/1 — флаг что перемычка уже рвалась (для haptic)

  // Attention: через 5с — серия «стуков», петля.
  useEffect(() => {
    bounce.value = withDelay(
      5000,
      withRepeat(
        withSequence(
          withTiming(-14, { duration: 180 }),
          withSpring(0, { damping: 6, stiffness: 220 }),
          withTiming(0, { duration: 3500 }),
        ),
        -1,
        false,
      ),
    );
    return () => cancelAnimation(bounce);
  }, [bounce]);

  const tickBreak = () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  const tickOpen = () =>
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

  const gesture = Gesture.Pan()
    .activateAfterLongPress(180)
    .onStart(() => {
      cancelAnimation(bounce);
      bounce.value = withTiming(0, { duration: 120 });
      broke.value = 0;
    })
    .onUpdate((e) => {
      const next = Math.max(0, Math.min(BUD_MAX_LIFT, -e.translationY));
      lift.value = next;
      // haptic в момент разрыва перемычки (один раз)
      const breakDist = R_PARENT + R_BUD;
      if (next > breakDist && broke.value === 0) {
        broke.value = 1;
        runOnJS(tickBreak)();
      }
    })
    .onEnd(() => {
      if (lift.value >= OPEN_THRESHOLD) {
        runOnJS(tickOpen)();
        // «Открытие»: добегаем вверх, затем сброс (в реале — morph в бар).
        lift.value = withSequence(
          withTiming(BUD_MAX_LIFT, { duration: 160 }),
          withDelay(220, withSpring(0, { damping: 14, stiffness: 120 })),
        );
      } else {
        // Слияние назад в туллбар.
        lift.value = withSpring(0, { damping: 13, stiffness: 160 });
      }
    });

  // Анимированный path перемычки.
  const bridgeProps = useAnimatedProps(() => {
    const budCy = baseY - lift.value;
    return {
      d: metaballPath(cx, baseY, R_PARENT, cx, budCy, R_BUD, CONNECT_K, 0.5),
    };
  });

  // Анимированная почка (круг).
  const budProps = useAnimatedProps(() => ({
    cy: baseY - lift.value,
    // почка проявляется по мере подъёма
    opacity: Math.min(1, lift.value / 18),
  }));

  // Центральная иконка: attention-bounce + прячется пока почка поднята.
  const centerStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: bounce.value }],
    opacity: lift.value > 6 ? 0 : 1,
  }));

  return (
    <View style={styles.root}>
      <LinearGradient
        colors={['#1A1248', '#3A1E6E', '#7A2E8E', '#2E4BD7']}
        start={{ x: 0.1, y: 0 }}
        end={{ x: 0.9, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      <Text style={[styles.hint, { top: insets.top + 40 }]}>
        Зажми центр и свайпни вверх
      </Text>

      {/* Туллбар-пилюля (визуальный макет) + жест на центре */}
      <View style={[styles.toolbar, { bottom: insets.bottom + 24 }]}>
        <View style={styles.sideIcon} />
        <GestureDetector gesture={gesture}>
          <Animated.View style={[styles.centerHit, centerStyle]}>
            <View style={styles.centerBtn} />
          </Animated.View>
        </GestureDetector>
        <View style={styles.sideIcon} />
      </View>

      {/* Svg-канва ПОВЕРХ туллбара (pointerEvents none — тапы идут в жест).
          Родитель совмещён с центр-кнопкой, почка растёт вверх. */}
      <View
        pointerEvents="none"
        style={[styles.canvasWrap, { bottom: insets.bottom + 18, height: canvasH }]}
      >
        <Svg width={SCREEN_W} height={canvasH}>
          <Circle cx={cx} cy={baseY} r={R_PARENT} fill={COBALT} />
          <AnimatedPath animatedProps={bridgeProps} fill={COBALT} />
          <AnimatedCircle animatedProps={budProps} cx={cx} r={R_BUD} fill={COBALT} />
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#1A1248' },
  hint: {
    position: 'absolute',
    alignSelf: 'center',
    color: 'rgba(255,255,255,0.85)',
    fontSize: 15,
    fontWeight: '600',
  },
  canvasWrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  toolbar: {
    position: 'absolute',
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: 240,
    height: 64,
    borderRadius: 9999,
    paddingHorizontal: 28,
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255,255,255,0.25)',
  },
  sideIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(255,255,255,0.35)',
  },
  centerHit: { width: 72, height: 72, alignItems: 'center', justifyContent: 'center' },
  centerBtn: {
    width: 60,
    height: 60,
    borderRadius: 18,
    backgroundColor: COBALT,
  },
});
