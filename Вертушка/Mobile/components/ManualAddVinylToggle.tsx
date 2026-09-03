/**
 * ManualAddVinylToggle — floating-вход в «Добавить вручную» (source='user').
 *
 * Дизайн: Design/manual-add-toggle/from-design/ManualAddVinylToggle.dc.html
 * Винил-кноб = реюз VinylSpinner (та же скорость 1800ms/оборот и вид, как в
 * карточке релиза — меняется только size). См. record/[id].tsx.
 *
 * collapsed (FAB 56, серый винил) → tap → expanded (pill 224×64, текст + цветной
 * винил-thumb справа) → тянем thumb влево (или tap) → открываем визард.
 * После открытия / на возврат фокуса состояние сбрасывается в collapsed.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, StyleSheet, Pressable, useWindowDimensions } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  cancelAnimation,
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  withSpring,
  runOnJS,
  interpolate,
  Extrapolation,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { VinylSpinner } from './VinylSpinner';
import { CoachPulse } from './onboarding/CoachPulse';
import { SwipeLeftHint, SWIPE_HINT_WIDTH } from './ui/SwipeLeftHint';
import type { VinylColorConfig } from '../lib/vinylColor';

const KNOB = 56;
const PILL_H = 64;
const FAB_W = PILL_H; // collapsed = круг
const RIGHT = 16; // правый отступ FAB
const HINT_GAP = 10; // просвет между шевронами и кнобом
const TEXT_LEFT = 18; // отступ текста от левого края пилюли
const TEXT_GAP = 8; // минимальный просвет между текстом и шевронами
/** Насколько кноб «клюёт» влево, показывая, что его тянут, а не жмут. */
const NUDGE = 9;

// Family-цвета кноба (как в dc-файле).
const FAMILY = ['#E53935', '#1E88E5', '#43A047', '#FDD835', '#FB8C00'];

// «Мешок»: при каждом заходе берём следующий цвет; не повторяется пока все 5 не
// переберутся, и новый круг не стартует с того же цвета. Состояние — на уровне
// модуля (живёт между фокусами экрана, переживает remount таба).
let _bag: string[] = [];
let _last: string | null = null;
function nextFamily(): string {
  if (_bag.length === 0) {
    _bag = [...FAMILY];
    for (let i = _bag.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [_bag[i], _bag[j]] = [_bag[j], _bag[i]];
    }
    // не дать новому кругу начаться с того же цвета, что был последним
    if (_bag[_bag.length - 1] === _last && _bag.length > 1) {
      [_bag[_bag.length - 1], _bag[0]] = [_bag[0], _bag[_bag.length - 1]];
    }
  }
  _last = _bag.pop() as string;
  return _last;
}

// Свёрнутый = «прозрачная»/бесцветная пластинка, но ПЛОТНАЯ (не просвечивает);
// раскрытый = плотный family-цвет.
const CLEAR = '#D9DCE3';
function knobCfg(hex: string, collapsed: boolean): VinylColorConfig {
  return collapsed
    ? { type: 'solid', primaryColor: CLEAR, opacity: 1, isColored: false }
    : { type: 'solid', primaryColor: hex, opacity: 1, isColored: true };
}

type Phase = 'collapsed' | 'expanded' | 'activated';

interface Props {
  onOpen: () => void;
  /** Низ-якорь. По умолчанию '14%' — одна линия с кнопкой затвора. */
  bottom?: number | string;
  /**
   * Подсветить кноб — для контекстной подсказки про способы добавления.
   * Ореол рисуется ВНУТРИ компонента: root позиционирован абсолютно, и обёртка
   * снаружи сломала бы привязку к правому нижнему углу.
   */
  highlighted?: boolean;
}

export function ManualAddVinylToggle({ onOpen, bottom = '14%', highlighted = false }: Props) {
  const [phase, setPhase] = useState<Phase>('collapsed');
  const [famHex, setFamHex] = useState(() => nextFamily());

  // Ход кноба: от FAB справа до центра экрана (= кнопка затвора).
  const { width: W } = useWindowDimensions();
  const SLIDE = Math.max(80, W / 2 - RIGHT - 32); // knob center: (W−RIGHT−32) → W/2
  const PILL_W = SLIDE + KNOB + 8; // трек вмещает полный ход кноба
  /**
   * Шевроны не расширяют пилюлю — они делят с текстом её собственную ширину.
   * Поэтому текст получает ровно остаток: пилюля минус кноб, минус группа
   * шевронов, минус просветы. Ширина фиксированная, а не flex: pill меняет
   * ширину анимацией, и flex-контент пересчитывал бы раскладку каждый кадр.
   */
  const TEXT_W =
    PILL_W - TEXT_LEFT - (KNOB + 4) - HINT_GAP - SWIPE_HINT_WIDTH - TEXT_GAP;

  const expand = useSharedValue(0); // 0 collapsed → 1 expanded (ширина pill + текст)
  const knobX = useSharedValue(0); // [-SLIDE..0]
  const nudge = useSharedValue(0); // подсказка: кноб сам подаётся влево

  // Подсказку глушим на время перетаскивания: иначе кноб «дрожит» под пальцем.
  const [hinting, setHinting] = useState(false);

  const reset = useCallback(() => {
    setPhase('collapsed');
    setHinting(false);
    expand.value = withTiming(0, { duration: 200 });
    knobX.value = withTiming(0, { duration: 200 });
  }, [expand, knobX]);

  // На каждый заход: новый цвет из мешка (не повторяется). На выход: сброс в
  // collapsed (нет фриза). useFocusEffect фокус-колбэк — первый маунт пропускаем
  // (цвет уже выбран в useState), меняем со второго фокуса.
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) firstFocus.current = false;
      else setFamHex(nextFamily());
      return () => reset();
    }, [reset]),
  );

  const open = useCallback(() => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    onOpen();
    // снап обратно в collapsed (экран уходит push'ем — не мелькнёт)
    setPhase('collapsed');
    setHinting(false);
    expand.value = 0;
    knobX.value = 0;
  }, [onOpen, expand, knobX]);

  const activate = useCallback(() => {
    setPhase('activated');
    setHinting(false);
    knobX.value = withTiming(-SLIDE, { duration: 200 });
    setTimeout(open, 260);
  }, [knobX, open]);

  const toExpanded = useCallback(() => {
    setPhase('expanded');
    setHinting(true);
    expand.value = withSpring(1, { damping: 16, stiffness: 180 });
    Haptics.selectionAsync();
  }, [expand]);

  /**
   * Кноб раз в пару секунд коротко клюёт влево и возвращается пружиной.
   * Шевроны показывают направление, а этот «клевок» — что двигают именно
   * пластинку: без него раскрытую пилюлю продолжают жать как кнопку.
   */
  useEffect(() => {
    if (phase !== 'expanded' || !hinting) {
      cancelAnimation(nudge);
      nudge.value = withTiming(0, { duration: 120 });
      return;
    }
    nudge.value = withRepeat(
      withSequence(
        withTiming(0, { duration: 1100 }), // пауза между показами
        withTiming(-NUDGE, { duration: 240, easing: Easing.out(Easing.cubic) }),
        withSpring(0, { damping: 11, stiffness: 210 }),
      ),
      -1,
      false,
    );
    return () => {
      cancelAnimation(nudge);
      nudge.value = 0;
    };
  }, [phase, hinting, nudge]);

  // Тап переключает раскрытие (undo): collapsed→expanded, expanded→collapsed.
  // Открытие визарда — только слайдом кноба влево.
  const onPress = useCallback(() => {
    if (phase === 'collapsed') toExpanded();
    else if (phase === 'expanded') reset();
  }, [phase, toExpanded, reset]);

  const pan = useMemo(
    () =>
      Gesture.Pan()
        .enabled(phase === 'expanded')
        .onBegin(() => {
          runOnJS(setHinting)(false);
        })
        .onUpdate((e) => {
          knobX.value = Math.max(-SLIDE, Math.min(0, e.translationX));
        })
        .onEnd((e) => {
          if (e.translationX <= -SLIDE * 0.6) {
            runOnJS(activate)();
          } else {
            knobX.value = withSpring(0, { damping: 18, stiffness: 200 });
          }
        })
        .onFinalize(() => {
          // Именно onFinalize, а не onEnd: при обычном тапе по кнобу жест не
          // активируется и onEnd не придёт — подсказка бы погасла навсегда.
          // После активации phase уже 'activated', и эффект её не поднимет.
          runOnJS(setHinting)(true);
        }),
    [phase, activate, knobX, SLIDE],
  );

  const pillStyle = useAnimatedStyle(() => ({
    width: interpolate(expand.value, [0, 1], [FAB_W, PILL_W], Extrapolation.CLAMP),
    backgroundColor: `rgba(236,237,240,${expand.value})`,
  }));

  // Текст и шевроны гаснут одинаково: видны в expanded, тают по мере ухода
  // thumb влево — к моменту активации в пилюле остаётся только пластинка.
  const fadeStyle = useAnimatedStyle(() => {
    const slideP = interpolate(knobX.value, [-SLIDE, 0], [0, 1], Extrapolation.CLAMP);
    return { opacity: expand.value * slideP };
  });

  const knobStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: knobX.value + nudge.value }],
  }));

  return (
    <View style={[styles.root, { bottom: bottom as any }]} pointerEvents="box-none">
      <CoachPulse active={highlighted} variant="glow" radius={PILL_H / 2} inset={5}>
      <Pressable onPress={onPress}>
        <Animated.View style={[styles.pill, pillStyle]}>
          <Animated.Text
            style={[styles.text, { left: TEXT_LEFT, width: TEXT_W }, fadeStyle]}
            numberOfLines={2}
            // На узких экранах остаток под текст ужимается до ~88pt — страховка
            // от многоточия в «Добавить», без неё подсказка ломает надпись.
            adjustsFontSizeToFit
            minimumFontScale={0.85}
          >
            Добавить{'\n'}вручную
          </Animated.Text>

          <Animated.View style={[styles.hint, fadeStyle]} pointerEvents="none">
            <SwipeLeftHint active={phase === 'expanded'} />
          </Animated.View>

          <GestureDetector gesture={pan}>
            <Animated.View style={[styles.knob, knobStyle]}>
              <VinylSpinner size={KNOB} colorConfig={knobCfg(famHex, phase === 'collapsed')} />
            </Animated.View>
          </GestureDetector>
        </Animated.View>
      </Pressable>
      </CoachPulse>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    position: 'absolute',
    right: 16, // правый нижний угол — стартовая точка свайпа справа-налево
    height: 72, // = высота затвора: тоггл на одной линии с кнопкой фото
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  pill: {
    height: PILL_H,
    borderRadius: PILL_H / 2,
    justifyContent: 'center',
    overflow: 'hidden',
    shadowColor: '#1C1D3A',
    shadowOffset: { width: 0, height: 14 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 10,
  },
  text: {
    position: 'absolute',
    fontWeight: '800',
    fontSize: 18,
    lineHeight: 19,
    color: '#23244D',
  },
  hint: {
    position: 'absolute',
    right: KNOB + 4 + HINT_GAP, // кноб прижат к правому краю с отступом 4
    top: 0,
    bottom: 0,
    justifyContent: 'center',
  },
  knob: {
    position: 'absolute',
    right: 4,
    top: 4,
    width: KNOB,
    height: KNOB,
  },
});
