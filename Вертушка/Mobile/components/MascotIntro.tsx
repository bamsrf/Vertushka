/**
 * MascotIntro — полноэкранная заставка маскота на Lottie, играет ОДИН раз
 * при старте (после native splash). Анимация — `assets/animations/intro-mascot.json`.
 *
 * Native splash (app.json) анимировать нельзя — платформенное ограничение, см.
 * docs/plans/MASCOT_ANIMATION_SPEC.md §6. Поэтому «живое» интро живёт здесь, уже
 * внутри приложения, поверх остального UI.
 *
 * Устойчивость: `lottie-react-native` есть только в dev-build/проде. Если модуля
 * нет (Expo Go) — интро тихо пропускается (onFinish вызывается сразу), пользователь
 * просто попадает в приложение без заставки. Никаких заглушек на весь экран.
 *
 * Placeholder-guard: пока в intro-mascot.json лежит заглушка (поле "nm" содержит
 * "-PLACEHOLDER"), интро НЕ показывается — синий кружок не должен утечь в релиз.
 * Как только дизайнер подложит финальный .json (без маркера), интро включится
 * само, править код не нужно. См. docs/plans/MASCOT_ANIMATION_SPEC.md §7.5.
 *
 * Фон интро = INTRO_BACKDROP (#000000). Тот же цвет должен стоять в трёх местах,
 * иначе на стыке видна ступенька: `splash.backgroundColor` в app.json, этот
 * контейнер и фон самих кадров внутри intro-mascot.json.
 *
 * Почему чёрный, а не Colors.background (#FAFBFF), как было раньше и как просит
 * §8 ТЗ: исходная анимация отрисована на чёрном, и осветлить её постобработкой
 * нельзя. Обводка маскота — почти чёрный тёмно-синий, поэтому colorkey по фону
 * съедает её вместе с фоном: контуры пропадают, по краям остаются ореолы. Кадры
 * идут как есть (JPEG, альфы нет), а под них подгоняется фон.
 */
import { useEffect, useRef } from 'react';
import { Animated, StyleSheet } from 'react-native';

/** Фон кадров intro-mascot.json. Держать в паре со splash.backgroundColor (app.json). */
const INTRO_BACKDROP = '#000000';
/** Длительность анимации: op(70) / fr(12) ≈ 5.83с. Safety-timeout берётся с запасом. */
const INTRO_DURATION_MS = 5830;
/**
 * Затухание перед снятием интро. Нужно, потому что интро чёрное, а приложение
 * под ним светлое (#FAFBFF): без него на стыке резкая вспышка. Убрать, если
 * интро перерисуют на светлом фоне и стык исчезнет сам.
 */
const FADE_OUT_MS = 250;

let LottieView: React.ComponentType<Record<string, unknown>> | null = null;
try {
  LottieView = require('lottie-react-native').default;
} catch {
  LottieView = null;
}

const INTRO_SOURCE = require('../assets/animations/intro-mascot.json');
// Заглушка? Не показываем интро вообще, пока не придёт финальная анимация.
const IS_PLACEHOLDER =
  typeof INTRO_SOURCE?.nm === 'string' && INTRO_SOURCE.nm.includes('PLACEHOLDER');

interface MascotIntroProps {
  /** Вызывается когда интро отыграло (или сразу, если lottie недоступен). */
  onFinish: () => void;
}

export function MascotIntro({ onFinish }: MascotIntroProps) {
  // Гарантия, что onFinish не выстрелит дважды (onAnimationFinish + safety-timeout).
  const finished = useRef(false);
  const opacity = useRef(new Animated.Value(1)).current;

  // Гасим интро и только потом отдаём экран приложению. Если анимацию оборвали
  // (unmount на полпути), колбэк придёт с finished: false — onFinish всё равно
  // зовём, иначе пользователь останется под чёрным слоем навсегда.
  const finish = () => {
    if (finished.current) return;
    finished.current = true;
    Animated.timing(opacity, {
      toValue: 0,
      duration: FADE_OUT_MS,
      useNativeDriver: true,
    }).start(() => onFinish());
  };

  // onAnimationFailure ловит только асинхронные сбои (например, загрузку по URL).
  // Ошибку разбора JSON он на iOS пропускает: она случается синхронно внутри
  // updateProps, когда Fabric ещё не выставил _eventEmitter, и событие молча
  // отбрасывается (LottieAnimationViewComponentView.mm, `if(!_eventEmitter) return`).
  // Оставляем как есть — лишним не будет, но полагаться на него нельзя.
  const handleFailure = (error: string) => {
    console.warn(`[MascotIntro] Lottie сообщил об ошибке: ${error}`);
    finish();
  };

  useEffect(() => {
    if (!LottieView || IS_PLACEHOLDER) {
      // Модуля нет ИЛИ в файле заглушка — интро пропускаем сразу. Гасить нечего
      // (ниже return null), поэтому мимо finish() с его затуханием.
      if (!finished.current) {
        finished.current = true;
        onFinish();
      }
      return;
    }
    // Safety-net: если onAnimationFinish не прилетит (редко на Android при
    // прерывании), всё равно закрываемся с запасом ~1с к длине анимации.
    //
    // Он же — единственный надёжный детектор немых поломок Lottie. Битый ассет
    // не роняет приложение и ничего не пишет в лог: контейнер просто стоит
    // пустым весь таймаут, что выглядит как «белый экран на старте» и ищется
    // часами. За историю intro-mascot.json так проявились уже две разные
    // причины — webp-кадры и пропавшее поле "u" у ассетов. Если сюда дошли,
    // значит анимация не доиграла до конца, и это стоит увидеть в логе.
    const t = setTimeout(() => {
      if (!finished.current) {
        console.warn(
          `[MascotIntro] интро не доиграло за ${INTRO_DURATION_MS + 1000}мс — вероятно, ` +
            'Lottie не смог разобрать assets/animations/intro-mascot.json ' +
            'и показывал пустой экран',
        );
      }
      finish();
    }, INTRO_DURATION_MS + 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!LottieView || IS_PLACEHOLDER) return null;

  return (
    <Animated.View style={[styles.fill, { opacity }]} pointerEvents="auto">
      <LottieView
        source={INTRO_SOURCE}
        autoPlay
        loop={false}
        onAnimationFinish={finish}
        onAnimationFailure={handleFailure}
        resizeMode="contain"
        style={styles.anim}
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  fill: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: INTRO_BACKDROP,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  anim: {
    width: '82%',
    aspectRatio: 1,
  },
});
