/**
 * AutoRail — горизонтальный авто-скроллящийся рейл с обложками.
 * Используется на публичном профиле и на экране Поиска.
 *
 * Авто-движение и ручной свайп идут полностью на UI-треде (Reanimated 3
 * useFrameCallback + Gesture.Pan worklets), поэтому JS-тред свободен для
 * тапов в шапке, а сам свайп идёт за пальцем без срывов и поддерживает
 * инерцию через withDecay.
 */
import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Pressable,
  Platform,
  PixelRatio,
  LayoutChangeEvent,
} from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useFrameCallback,
  withDecay,
  cancelAnimation,
  runOnJS,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { useIsFocused } from '@react-navigation/native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { ms } from '../lib/responsive';
import { resolveMediaUrl, sizedCoverUrl } from '../lib/api';
import { cleanArtistName } from '../lib/format';
import { PublicProfileRecord } from '../lib/types';

const PALETTE = {
  ink: '#1B1D26',
  mute: '#9096A6',
  lavender: '#C9B8FF',
  periwinkle: '#9AA8FF',
  cobalt: '#3A4BE0',
};

const HORIZONTAL_PADDING = 20;
const RAIL_COVER = 108;
// Нарезка обложки под слот 108pt вместо мастера (~1000px): sizedCoverUrl
// округлит вверх до ступени 320/640 по DPR устройства.
const RAIL_COVER_PX = Math.ceil(RAIL_COVER * PixelRatio.get());
const ITEM_GAP = 12;
const FULL_LOOP_DURATION_MS = 30000;
// Абсолютная скорость авто-скролла (px/ms) — НЕ зависит от числа карточек.
// Калибрована под прежний рейл из 24 карточек (полный цикл ≈30с при 24 шт).
// Иначе при коротком рейле (топ-10) визуальная скорость падала, т.к. петля
// фиксирована в 30с независимо от ширины ряда.
const SCROLL_PX_PER_MS = (24 * (RAIL_COVER + ITEM_GAP)) / FULL_LOOP_DURATION_MS;
const HOVER_PAUSE_DELAY_MS = 200;
const IS_WEB = Platform.OS === 'web';

interface AutoRailProps {
  title: string;
  subtitle: string;
  items: PublicProfileRecord[];
  titleColor: string;
  showYear?: boolean;
  onPick?: (record: PublicProfileRecord) => void;
  /** Кнопка-ссылка справа от заголовка (например «Смотреть все →»). */
  headerActionLabel?: string;
  /** Хендлер тапа по кнопке-ссылке. Если не задан — кнопка не рендерится. */
  onHeaderActionPress?: () => void;
  /**
   * Кастомный рендерер для последней мета-строки карточки. Используется когда
   * карусель показывает не ♥ want-count, а, например, цену магазина
   * («◉ 4 990 ₽» для маркета). Если задан — заменяет дефолтную строку с
   * year/format/want. Получает PublicProfileRecord и возвращает любой ReactNode.
   */
  itemBadgeRenderer?: (record: PublicProfileRecord) => ReactNode;
  /**
   * Внешняя пауза авто-движения. Когда true — кадровый цикл полностью
   * деактивируется (`setActive(false)`), рейл замирает на текущей позиции.
   * Используется, например, когда рейл перекрыт другим слоем (Маркет).
   * Пауза строго обратима: снятие → рейл продолжает с той же позиции.
   */
  paused?: boolean;
}

export function AutoRail({
  title,
  subtitle,
  items,
  showYear,
  onPick,
  titleColor,
  headerActionLabel,
  onHeaderActionPress,
  itemBadgeRenderer,
  paused = false,
}: AutoRailProps) {
  const tx = useSharedValue(0);
  const startTx = useSharedValue(0);
  const isPanning = useSharedValue(false);
  const isPaused = useSharedValue(false);
  const halfWidthSV = useSharedValue(0);
  // Внешняя пауза (проп `paused`, напр. рейл перекрыт Маркет-слоем) — гейтим её
  // ВНУТРИ worklet'а через shared value, а НЕ через frameCb.setActive из JS.
  // Причина: `paused` флипается из worklet-жеста выхода из Маркета (runOnJS →
  // setState), а старт/стоп кадрового цикла из JS-эффекта в этот момент даёт
  // JS↔UI-гонку — иногда финально регистрируется stop, и рейл «залипает».
  // Запись shared value идемпотентна и гонок не создаёт. setActive оставляем
  // только под фокус таба (фокус не связан с жестом — гонки нет).
  const externallyPaused = useSharedValue(false);

  const [rowWidth, setRowWidth] = useState(0);

  useEffect(() => {
    halfWidthSV.value = rowWidth;
  }, [rowWidth, halfWidthSV]);

  const resumeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverPauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleResume = useCallback(() => {
    if (resumeTimer.current) clearTimeout(resumeTimer.current);
    resumeTimer.current = setTimeout(() => {
      resumeTimer.current = null;
      isPaused.value = false;
    }, 2500);
  }, [isPaused]);

  const handleMouseEnter = useCallback(() => {
    if (!IS_WEB) return;
    if (hoverPauseTimer.current) clearTimeout(hoverPauseTimer.current);
    hoverPauseTimer.current = setTimeout(() => {
      hoverPauseTimer.current = null;
      isPaused.value = true;
    }, HOVER_PAUSE_DELAY_MS);
  }, [isPaused]);

  const handleMouseLeave = useCallback(() => {
    if (!IS_WEB) return;
    if (hoverPauseTimer.current) {
      clearTimeout(hoverPauseTimer.current);
      hoverPauseTimer.current = null;
    }
    if (resumeTimer.current) {
      clearTimeout(resumeTimer.current);
      resumeTimer.current = null;
    }
    isPaused.value = false;
  }, [isPaused]);

  useEffect(() => {
    return () => {
      if (resumeTimer.current) {
        clearTimeout(resumeTimer.current);
        resumeTimer.current = null;
      }
      if (hoverPauseTimer.current) {
        clearTimeout(hoverPauseTimer.current);
        hoverPauseTimer.current = null;
      }
    };
  }, []);

  // UI-thread авто-движение: каждый кадр сдвигаем tx на speed * dt.
  // externallyPaused читаем ВНУТРИ worklet'а — пауза по `paused` не трогает
  // active-состояние кадрового цикла, поэтому гонки старт/стоп нет. Когда пауза,
  // tx замирает → useAnimatedStyle не пересчитывается → композитинг встаёт
  // (та же экономия, что и setActive), а на снятии рейл едет дальше с места.
  const frameCb = useFrameCallback((frame) => {
    if (isPanning.value || isPaused.value || externallyPaused.value) return;
    const w = halfWidthSV.value;
    if (!w) return;
    const dt = frame.timeSincePreviousFrame ?? 16;
    tx.value = tx.value - SCROLL_PX_PER_MS * dt;
  });

  const focused = useIsFocused();
  const hasItems = !!items && items.length > 0;

  // (1) Активация кадрового цикла — ТОЛЬКО по фокусу таба. Уход с таба целиком
  // гасит колбэк (экран невидим). Фокус меняется вне жестов → гонки нет.
  // НЕ вызываем cancelAnimation(tx): отмена withDecay-инерции убивает её
  // completion-колбэк scheduleResume, из-за чего isPaused залипает в true.
  useEffect(() => {
    frameCb.setActive(focused && hasItems);
  }, [focused, hasItems, frameCb]);

  // (2) Внешняя пауза (`paused`, напр. рейл перекрыт Маркет-слоем) — гейт в
  // worklet'е через shared value (без гонки старт/стоп).
  // На СНЯТИИ паузы форсим resume: сбрасываем залипшую gesture-паузу. isPaused
  // мог остаться true, если пользователь флик­нул рейл перед входом в Маркет —
  // тогда withDecay-инерция была отменена, а её scheduleResume не вызвался.
  // Без этого сброса витрина замирает навсегда после выхода из Маркета.
  useEffect(() => {
    externallyPaused.value = paused;
    if (!paused) {
      if (resumeTimer.current) {
        clearTimeout(resumeTimer.current);
        resumeTimer.current = null;
      }
      isPaused.value = false;
    }
  }, [paused, externallyPaused, isPaused]);

  // Визуальная нормализация в [-w, 0] — даёт бесшовный цикл и работает
  // одинаково для авто-движения, драга и инерции.
  const animStyle = useAnimatedStyle(() => {
    const w = halfWidthSV.value;
    if (!w) return { transform: [{ translateX: 0 }] };
    let v = tx.value % w;
    if (v > 0) v -= w;
    return { transform: [{ translateX: v }] };
  });

  const panGesture = useMemo(
    () =>
      Gesture.Pan()
        .activeOffsetX([-6, 6])
        .failOffsetY([-12, 12])
        .onBegin(() => {
          'worklet';
          // На вебе пауза управляется hover-таймером, а не нажатием:
          // mouse-down не должен мгновенно останавливать карусель.
          if (IS_WEB) return;
          isPaused.value = true;
          cancelAnimation(tx);
        })
        .onStart(() => {
          'worklet';
          isPanning.value = true;
          startTx.value = tx.value;
          if (IS_WEB) {
            // Реальный drag начался — теперь пауза нужна, чтобы авто-кадр
            // не дрался с translation и инерцией.
            isPaused.value = true;
            cancelAnimation(tx);
          }
        })
        .onUpdate((e) => {
          'worklet';
          tx.value = startTx.value + e.translationX;
        })
        .onEnd((e) => {
          'worklet';
          isPanning.value = false;
          // Инерция после флика. Пока decay едет — isPaused=true, авто-кадр
          // не дописывает поверх. Когда инерция закончится, через 2.5с
          // карусель сама поедет дальше.
          tx.value = withDecay(
            {
              velocity: e.velocityX,
              deceleration: 0.997,
            },
            () => {
              'worklet';
              runOnJS(scheduleResume)();
            },
          );
        })
        .onFinalize((_, success) => {
          'worklet';
          if (!success) {
            // Просто тап / гесчур не активировался — резюмим автокарусель.
            isPanning.value = false;
            runOnJS(scheduleResume)();
          }
        }),
    [tx, startTx, isPanning, isPaused, scheduleResume],
  );

  if (!items || items.length === 0) return null;

  const renderCard = (r: PublicProfileRecord, key: string) => (
    <TouchableOpacity
      key={key}
      activeOpacity={0.85}
      onPress={() => onPick?.(r)}
      style={{ width: RAIL_COVER }}
    >
      <View style={styles.railCover}>
        {r.cover_image_url ? (
          <Image
            source={sizedCoverUrl(resolveMediaUrl(r.cover_image_url), RAIL_COVER_PX)}
            style={{ width: RAIL_COVER, height: RAIL_COVER }}
            cachePolicy="disk"
          />
        ) : (
          <LinearGradient
            colors={[PALETTE.lavender, PALETTE.periwinkle]}
            style={{ width: RAIL_COVER, height: RAIL_COVER }}
          />
        )}
      </View>
      <Text
        numberOfLines={1}
        style={[
          styles.railArtist,
          { color: titleColor === PALETTE.cobalt ? PALETTE.cobalt : PALETTE.mute },
        ]}
      >
        {cleanArtistName(r.artist)}
      </Text>
      <Text numberOfLines={1} style={styles.railTitleSmall}>
        {r.title}
      </Text>
      {itemBadgeRenderer ? (
        // Кастомная мета-строка (например, цена магазина для маркет-карусели).
        // Заменяет дефолтный «year · format · ♥ want».
        <View style={{ marginTop: 2 }}>{itemBadgeRenderer(r)}</View>
      ) : showYear && r.year ? (
        <>
          <Text style={styles.railYear}>
            {r.year}
            {r.format_type ? ` · ${r.format_type}` : ''}
          </Text>
          {r.discogs_want ? (
            <Text style={styles.railWant}>♥ {r.discogs_want}</Text>
          ) : null}
        </>
      ) : null}
    </TouchableOpacity>
  );

  const handleRowLayout = (e: LayoutChangeEvent) => {
    // Ширина одной половины + один gap (между последней карточкой первой
    // половины и первой второй) — для бесшовного шва.
    const w = e.nativeEvent.layout.width + ITEM_GAP;
    if (Math.abs(w - rowWidth) > 0.5) {
      setRowWidth(w);
    }
  };

  return (
    <View>
      <View style={styles.railHead}>
        <View style={styles.railHeadLeft}>
          <Text
            style={[styles.railTitle, { color: titleColor }]}
            numberOfLines={1}
          >
            {title.toUpperCase()}
          </Text>
          <Text style={styles.railSub} numberOfLines={1} ellipsizeMode="tail">
            {subtitle}
          </Text>
        </View>
        {headerActionLabel && onHeaderActionPress ? (
          <Pressable
            onPress={onHeaderActionPress}
            hitSlop={12}
            style={({ pressed }) => [
              styles.railHeadAction,
              pressed && { opacity: 0.6 },
            ]}
          >
            <Text
              style={[styles.railHeadActionText, { color: titleColor }]}
              numberOfLines={1}
            >
              {headerActionLabel}
            </Text>
          </Pressable>
        ) : null}
      </View>
      <GestureDetector gesture={panGesture}>
        <View
          style={styles.viewport}
          {...(IS_WEB
            ? ({ onMouseEnter: handleMouseEnter, onMouseLeave: handleMouseLeave } as object)
            : null)}
        >
          <Animated.View style={[styles.track, animStyle]}>
            <View style={styles.row} onLayout={handleRowLayout}>
              {items.map((r, i) => renderCard(r, `a-${r.id}-${i}`))}
            </View>
            <View style={[styles.row, { marginLeft: ITEM_GAP }]}>
              {items.map((r, i) => renderCard(r, `b-${r.id}-${i}`))}
            </View>
          </Animated.View>
        </View>
      </GestureDetector>
    </View>
  );
}

const styles = StyleSheet.create({
  railHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    paddingHorizontal: HORIZONTAL_PADDING,
    marginBottom: 12,
    gap: 12,
  },
  railHeadLeft: {
    flexDirection: 'row',
    alignItems: 'baseline',
    flex: 1,            // занимает доступное место → action не перекрывает
    minWidth: 0,        // даёт детям сжиматься (numberOfLines+ellipsize работают)
    gap: 8,
  },
  railHeadAction: {
    paddingVertical: 2,
    flexShrink: 0,      // action не сжимается, subtitle обрезается раньше
  },
  railHeadActionText: {
    fontSize: ms(12),
    fontWeight: '600',
  },
  railTitle: {
    fontSize: ms(11),
    letterSpacing: 1.2,
    fontWeight: '600',
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
  },
  railSub: { fontSize: ms(13), color: PALETTE.mute, flexShrink: 1, minWidth: 0 },
  viewport: {
    overflow: 'hidden',
  },
  track: {
    flexDirection: 'row',
    paddingHorizontal: HORIZONTAL_PADDING,
  },
  row: {
    flexDirection: 'row',
    gap: ITEM_GAP,
  },
  railCover: {
    width: RAIL_COVER,
    height: RAIL_COVER,
    borderRadius: 13,
    overflow: 'hidden',
    backgroundColor: PALETTE.lavender,
    shadowColor: PALETTE.ink,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 14,
  },
  railArtist: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: ms(10),
    letterSpacing: 0.6,
    marginTop: 8,
  },
  railTitleSmall: { fontSize: ms(12), fontWeight: '600', color: PALETTE.ink, marginTop: 2 },
  railYear: { fontSize: ms(12), color: PALETTE.periwinkle, marginTop: 2 },
  railWant: { fontSize: ms(12), color: PALETTE.periwinkle, marginTop: 1, fontWeight: '600' },
});
