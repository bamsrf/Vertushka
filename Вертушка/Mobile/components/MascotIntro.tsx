/**
 * MascotIntro — полноэкранная заставка маскота, играет ОДИН раз при старте
 * (после native splash). Источник — `assets/video/intro-mascot.mp4` (expo-video).
 *
 * Native splash (app.json) анимировать нельзя — платформенное ограничение, см.
 * docs/plans/design/MASCOT_ANIMATION_SPEC.md §6. Поэтому «живое» интро живёт здесь, уже
 * внутри приложения, поверх остального UI.
 *
 * Раньше интро было на Lottie (`assets/animations/intro-mascot.json`) — растровые
 * кадры внутри JSON давали ~2 класса немых поломок (webp-кадры, пропавшее поле
 * "u" у ассетов) и белый экран на старте вместо анимации. Видео этих граблей
 * лишено; Lottie остался только для лоадера (`MascotLoader`).
 *
 * Устойчивость: `expo-video` — нативный модуль; в Expo Go до SDK 57 его не было
 * (с SDK 57 — есть, интро играет и там). Если модуль не подгрузился — интро тихо
 * пропускается (onFinish зовётся сразу), пользователь просто попадает в
 * приложение без заставки.
 *
 * История (SDK 57): RN 0.86 удалил StyleSheet.absoluteFillObject. Спред
 * `...absoluteFillObject` молча давал {} — оверлей терял position:absolute,
 * вставал В ПОТОК под корневой Stack и на время интро сжимал всё приложение
 * ровно на высоту квадрата видео (82% ширины). Отсюда же «пропавшая камера»
 * на скане: её style стал undefined. Лечится absoluteFill (с 0.86 это
 * обычный объект, годится и для спреда).
 *
 * Фон интро = Colors.background — тот же цвет, что у splash.backgroundColor
 * (app.json) и у контента приложения, и тот же, что у фона кадров ролика: он
 * прибит к #FAFBFF скриптом scripts/normalize_intro_video.sh. Совпадать должны
 * все трое, иначе видно либо квадрат видео на подложке, либо вспышку на стыке
 * «splash → интро». Прогонять скрипт при каждой замене ролика.
 */
import { useEffect, useRef, useState } from 'react';
import { StyleSheet } from 'react-native';
// Reanimated вместо легаси Animated — приведение к домашнему стилю проекта
// (все остальные анимации на reanimated) при починке SDK 57.
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { Colors } from '../constants/theme';

/**
 * Подложка под квадратом видео. Ровно фон приложения: фон кадров ролика приведён
 * к нему же, так что край кадра на подложке не читается. Проверка после замены
 * ролика — вывод scripts/normalize_intro_video.sh, там должно быть fafbff.
 */
const INTRO_BACKDROP = Colors.background;
/** Длительность intro-mascot.mp4 ≈ 5.7с. Safety-timeout берётся с запасом. */
const INTRO_DURATION_MS = 5710;
/** Затухание перед снятием интро — чтобы стык с UI приложения не мигал. */
const FADE_OUT_MS = 250;

// Грузим лениво: если нативного expo-video нет (старые окружения) — не ронять бандл.
let videoModule: typeof import('expo-video') | null = null;
try {
  videoModule = require('expo-video');
} catch {
  videoModule = null;
}

const INTRO_SOURCE = require('../assets/video/intro-mascot.mp4');

interface MascotIntroProps {
  /** Вызывается когда интро отыграло (или сразу, если expo-video недоступен). */
  onFinish: () => void;
}

export function MascotIntro({ onFinish }: MascotIntroProps) {
  if (!videoModule) return <IntroSkipped onFinish={onFinish} />;
  return <IntroVideo onFinish={onFinish} video={videoModule} />;
}

/** Ветка «модуля нет» — отдельным компонентом, чтобы хуки ниже вызывались безусловно. */
function IntroSkipped({ onFinish }: MascotIntroProps) {
  useEffect(() => {
    onFinish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

function IntroVideo({
  onFinish,
  video,
}: MascotIntroProps & { video: typeof import('expo-video') }) {
  const { VideoView, useVideoPlayer } = video;
  // Гарантия, что onFinish не выстрелит дважды (статус playToEnd + safety-timeout).
  const finished = useRef(false);
  // onFinish зовётся ровно один раз — либо колбэком анимации, либо страховочным
  // таймером ниже. Двойной канал не паранойя: однажды колбэк анимации уже
  // замолчал на апгрейде RN, и приложение осталось жить под вечным интро.
  const onFinishFired = useRef(false);
  const opacity = useSharedValue(1);
  // Пока первый кадр не отрисован, видео не показываем: иначе на стыке со splash
  // мелькает пустой прямоугольник плеера.
  const [ready, setReady] = useState(false);

  const player = useVideoPlayer(INTRO_SOURCE, (p) => {
    p.loop = false;
    p.muted = true;
    // Без явного mixWithOthers холодный старт ставит на паузу музыку в чужих
    // приложениях: нативный дефолт audioMixingMode на iOS — doNotMix (вопреки
    // доке expo-video, где обещан 'auto'), а он переводит AVAudioSession в
    // .playback и активирует её даже для немого плеера. У ролика нет звуковой
    // дорожки вовсе, так что уступать чужому звуку нам нечего.
    p.audioMixingMode = 'mixWithOthers';
    p.play();
  });

  // Гасим интро и только потом отдаём экран приложению.
  const fireOnFinish = () => {
    if (onFinishFired.current) return;
    onFinishFired.current = true;
    onFinish();
  };

  const finish = () => {
    if (finished.current) return;
    finished.current = true;
    opacity.value = withTiming(0, { duration: FADE_OUT_MS }, () => {
      runOnJS(fireOnFinish)();
    });
    // Страховка: если колбэк withTiming не придёт, снимаем интро таймером.
    setTimeout(fireOnFinish, FADE_OUT_MS + 200);
  };

  useEffect(() => {
    const sub = player.addListener('statusChange', ({ status, error }) => {
      if (status === 'readyToPlay') setReady(true);
      if (status === 'error') {
        console.warn(`[MascotIntro] expo-video сообщил об ошибке: ${error?.message ?? 'unknown'}`);
        finish();
      }
    });
    const end = player.addListener('playToEnd', finish);
    // Safety-net: если playToEnd не прилетит (прерывание, битый ассет), всё равно
    // закрываемся с запасом ~1с к длине ролика. Он же — единственный надёжный
    // детектор немых поломок: пустой чёрный/белый экран весь таймаут ищется часами.
    const t = setTimeout(() => {
      if (!finished.current) {
        console.warn(
          `[MascotIntro] интро не доиграло за ${INTRO_DURATION_MS + 1000}мс — вероятно, ` +
            'плеер не смог прочитать assets/video/intro-mascot.mp4',
        );
      }
      finish();
    }, INTRO_DURATION_MS + 1000);
    return () => {
      clearTimeout(t);
      sub.remove();
      end.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fadeStyle = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.View style={[styles.fill, fadeStyle]} pointerEvents="auto">
      {ready && (
        <VideoView
          player={player}
          style={styles.video}
          contentFit="contain"
          nativeControls={false}
          allowsFullscreen={false}
          allowsPictureInPicture={false}
        />
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  fill: {
    ...StyleSheet.absoluteFill,
    backgroundColor: INTRO_BACKDROP,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  video: {
    width: '82%',
    aspectRatio: 1,
  },
});
