/**
 * MascotIntro — полноэкранная заставка маскота, играет ОДИН раз при старте
 * (после native splash). Источник — `assets/video/intro-mascot.mp4` (expo-video).
 *
 * Native splash (app.json) анимировать нельзя — платформенное ограничение, см.
 * docs/plans/MASCOT_ANIMATION_SPEC.md §6. Поэтому «живое» интро живёт здесь, уже
 * внутри приложения, поверх остального UI.
 *
 * Раньше интро было на Lottie (`assets/animations/intro-mascot.json`) — растровые
 * кадры внутри JSON давали ~2 класса немых поломок (webp-кадры, пропавшее поле
 * "u" у ассетов) и белый экран на старте вместо анимации. Видео этих граблей
 * лишено; Lottie остался только для лоадера (`MascotLoader`).
 *
 * Устойчивость: `expo-video` — нативный модуль, его нет в Expo Go. Если модуль
 * не подгрузился — интро тихо пропускается (onFinish зовётся сразу), пользователь
 * просто попадает в приложение без заставки.
 *
 * Фон интро = INTRO_BACKDROP (#FAFAFA) — точный цвет фона кадров, чтобы квадрат
 * видео не проступал на подложке. Он же в паре пикселей от splash.backgroundColor
 * (#FAFBFF в app.json) и от фона приложения, так что на стыках ступеньки не видно.
 */
import { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet } from 'react-native';

/**
 * Фон кадров intro-mascot.mp4 — замерен по краю кадра (ffmpeg, crop по рамке):
 * ровно #FAFAFA и не плывёт по ходу ролика. Держать в паре с фоном кадров, иначе
 * квадрат видео проступает светлым прямоугольником поверх подложки — на чистом
 * белом это видно невооружённым глазом. При замене ролика замерять заново.
 */
const INTRO_BACKDROP = '#FAFAFA';
/** Длительность intro-mascot.mp4 ≈ 5.7с. Safety-timeout берётся с запасом. */
const INTRO_DURATION_MS = 5710;
/** Затухание перед снятием интро — чтобы стык с UI приложения не мигал. */
const FADE_OUT_MS = 250;

// expo-video отсутствует в Expo Go: грузим лениво, чтобы не ронять бандл.
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
  const opacity = useRef(new Animated.Value(1)).current;
  // Пока первый кадр не отрисован, видео не показываем: иначе на стыке со splash
  // мелькает пустой прямоугольник плеера.
  const [ready, setReady] = useState(false);

  const player = useVideoPlayer(INTRO_SOURCE, (p) => {
    p.loop = false;
    p.muted = true;
    p.play();
  });

  // Гасим интро и только потом отдаём экран приложению.
  const finish = () => {
    if (finished.current) return;
    finished.current = true;
    Animated.timing(opacity, {
      toValue: 0,
      duration: FADE_OUT_MS,
      useNativeDriver: true,
    }).start(() => onFinish());
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

  return (
    <Animated.View style={[styles.fill, { opacity }]} pointerEvents="auto">
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
    ...StyleSheet.absoluteFillObject,
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
