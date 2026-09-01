/**
 * MarketBackground — двухслойный анимированный фон с magic-transition.
 *
 * Концепция «потайная дверь»:
 *   - Юзер скроллит экран поиска вниз.
 *   - В диапазоне scrollY ∈ [400, 700] фон Discogs (светлый) гаснет,
 *     фон Маркета (тёмно-насыщенный + grain) зажигается.
 *   - Между [400, 700] оба слоя одновременно частично видны → физическое
 *     смешение двух миров.
 *   - Полностью в Маркете (scrollY ≥ 700): только market-фон.
 *
 * Использование:
 *   const scrollY = useSharedValue(0);
 *   const onScroll = useAnimatedScrollHandler(e => { scrollY.value = e.contentOffset.y });
 *
 *   <MarketBackground scrollY={scrollY} />
 *   <Animated.ScrollView onScroll={onScroll} scrollEventThrottle={16}>
 *     ...
 *   </Animated.ScrollView>
 *
 * Источник: docs/plans/market/MARKET_AND_PRICE_DRAWER.md §1.3 +
 *           magic-transition.jsx из Design Claude handoff (frames 0/400/550/700/1250).
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  type SharedValue,
} from 'react-native-reanimated';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';

import { MarketPalette } from '../../constants/theme';
import Grain from './Grain';

/**
 * Default transition zone (раньше — static).
 * Сейчас START/END рассчитываются ДИНАМИЧЕСКИ от parent через
 * `transitionStartY/transitionEndY` props (parent знает реальное место
 * MarketSection через onLayout). Эти константы оставлены как fallback
 * для случая когда parent не передал ничего.
 *
 * Static zone убивает UX когда content above Маркета меняется (например,
 * юзер раскрыл длинный список истории) — фон Маркета начинает зажигаться
 * пока юзер ещё в истории, что выглядит как баг.
 */
export const TRANSITION_START_Y = 400;
export const TRANSITION_END_Y = 700;

interface MarketBackgroundProps {
  /** SharedValue со scrollY экрана. Если не передан — фон статичный, mode forced. */
  scrollY?: SharedValue<number>;
  /**
   * Принудительный режим (для preview/skeleton). Если задано — игнорирует scrollY.
   *   - 'search'  — только Discogs-мир
   *   - 'market'  — только market-мир
   *   - 'mid'     — оба слоя по 0.5 (для design preview)
   */
  forcedMode?: 'search' | 'market' | 'mid';
  /**
   * Динамический Y начала transition zone. Parent передаёт scrollY-позицию
   * MarketSection минус buffer (например 100 px). Используется когда parent
   * знает РЕАЛЬНОЕ место MarketSection (через onLayout).
   * Если не передано — fallback на статический TRANSITION_START_Y.
   * SharedValue (а не number) чтобы изменение в parent re-rendered'ило
   * worklet без mount-cycle'а.
   */
  transitionStartY?: SharedValue<number>;
  transitionEndY?: SharedValue<number>;
  /**
   * Альтернатива scrollY: прогресс curtain'а 0..1 (0=поиск, 1=маркет).
   * Когда передан — переопределяет scrollY-логику. Используется в (tabs)/search
   * после перехода на commit-жест: фон Маркета зажигается по progress'у самого
   * жеста, а не по scroll-позиции FlatList'а.
   */
  progress?: SharedValue<number>;
}

/**
 * Главный экспорт. Рендерит два absolute слоя на весь предок (StyleSheet.absoluteFill).
 * Размещать первым ребёнком в контейнере с position: relative.
 */
export function MarketBackground({
  scrollY: externalScrollY,
  forcedMode,
  transitionStartY,
  transitionEndY,
  progress,
}: MarketBackgroundProps) {
  // Если scrollY не передан — создаём фейковый SharedValue,
  // чтобы хуки выше не нарушали правил React.
  const fallbackScrollY = useSharedValue(0);
  const scrollY = externalScrollY ?? fallbackScrollY;
  const fallbackStartY = useSharedValue(TRANSITION_START_Y);
  const fallbackEndY = useSharedValue(TRANSITION_END_Y);
  const startY = transitionStartY ?? fallbackStartY;
  const endY = transitionEndY ?? fallbackEndY;
  const fallbackProgress = useSharedValue(0);
  const progressSv = progress ?? fallbackProgress;
  const useProgress = progress !== undefined;

  const searchAnimStyle = useAnimatedStyle(() => {
    if (forcedMode === 'search') return { opacity: 1 };
    if (forcedMode === 'market') return { opacity: 0 };
    if (forcedMode === 'mid') return { opacity: 0.5 };
    if (useProgress) {
      return {
        opacity: interpolate(progressSv.value, [0, 1], [1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
      };
    }
    return {
      opacity: interpolate(
        scrollY.value,
        [startY.value, endY.value],
        [1, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
      ),
    };
  });

  const marketAnimStyle = useAnimatedStyle(() => {
    if (forcedMode === 'search') return { opacity: 0 };
    if (forcedMode === 'market') return { opacity: 1 };
    if (forcedMode === 'mid') return { opacity: 0.5 };
    if (useProgress) {
      return {
        opacity: interpolate(progressSv.value, [0, 1], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        }),
      };
    }
    return {
      opacity: interpolate(
        scrollY.value,
        [startY.value, endY.value],
        [0, 1],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
      ),
    };
  });

  // depth='soft' для transition-midpoint — добавляет cobalt-tint overlay.
  // В RN мы не можем дёргать isWorklet-флаг для conditional render, поэтому
  // оба варианта depth'а всегда отрендерены, opacity между ними плавно.
  const softOverlayStyle = useAnimatedStyle(() => {
    if (forcedMode === 'mid') return { opacity: 1 };
    if (forcedMode) return { opacity: 0 };
    if (useProgress) {
      // Cobalt-tint peak в середине жеста — добавляет глубины commit'у.
      return {
        opacity: interpolate(
          progressSv.value,
          [0, 0.5, 1],
          [0, 0.30, 0],
          { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
        ),
      };
    }
    // Soft cobalt-overlay видим только в transition-zone, peak в середине.
    const midY = (startY.value + endY.value) / 2;
    return {
      opacity: interpolate(
        scrollY.value,
        [startY.value, midY, endY.value],
        [0, 0.30, 0],
        { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
      ),
    };
  });

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {/* Layer 1: Discogs-мир (светлый) */}
      <Animated.View style={[StyleSheet.absoluteFill, searchAnimStyle]}>
        <SearchBgStatic />
      </Animated.View>

      {/* Layer 2: Market-мир (тёмно-насыщенный + grain) */}
      <Animated.View style={[StyleSheet.absoluteFill, marketAnimStyle]}>
        <MarketBgStatic />
      </Animated.View>

      {/* Layer 3: Cobalt-tint overlay в transition midpoint (soft depth) */}
      <Animated.View
        style={[
          StyleSheet.absoluteFill,
          { backgroundColor: 'rgba(11,20,56,0.30)' },
          softOverlayStyle,
        ]}
      />
    </View>
  );
}

// ────────────────────────────────────────────────────────────────────────
// SearchBgStatic — «Discogs-мир»: clean #FAFBFF + 2 мягких radial overlay'я.
// ────────────────────────────────────────────────────────────────────────

const SearchBgStatic = React.memo(function SearchBgStatic() {
  return (
    <View style={[StyleSheet.absoluteFill, { backgroundColor: '#FAFBFF' }]}>
      <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
        <Defs>
          {/* Top — periwinkle wash */}
          <RadialGradient
            id="search-top"
            cx="50%"
            cy="-10%"
            rx="120%"
            ry="60%"
            fx="50%"
            fy="-10%"
          >
            <Stop offset="0%" stopColor="#5B6AF5" stopOpacity="0.22" />
            <Stop offset="50%" stopColor="#5B6AF5" stopOpacity="0" />
          </RadialGradient>
          {/* Bottom-right — pink corner */}
          <RadialGradient
            id="search-corner"
            cx="100%"
            cy="100%"
            rx="80%"
            ry="50%"
            fx="100%"
            fy="100%"
          >
            <Stop offset="0%" stopColor="#F0C4D8" stopOpacity="0.45" />
            <Stop offset="60%" stopColor="#F0C4D8" stopOpacity="0" />
          </RadialGradient>
        </Defs>
        <Rect width="100%" height="100%" fill="url(#search-top)" />
        <Rect width="100%" height="100%" fill="url(#search-corner)" />
      </Svg>
    </View>
  );
});

// ────────────────────────────────────────────────────────────────────────
// MarketBgStatic — «Маркет-мир»: 5 radial-gradient слоёв + signature
// тёмное пятно + grain. Полностью соответствует market-bg.jsx из Design Claude.
// ────────────────────────────────────────────────────────────────────────

const MarketBgStatic = React.memo(function MarketBgStatic() {
  return (
    <View
      style={[StyleSheet.absoluteFill, { backgroundColor: MarketPalette.void }]}
    >
      <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
        <Defs>
          {/* Big purple-magenta wash bottom-left */}
          <RadialGradient
            id="m-magenta"
            cx="8%"
            cy="95%"
            rx="120%"
            ry="90%"
            fx="8%"
            fy="95%"
          >
            <Stop offset="0%" stopColor={MarketPalette.magenta} stopOpacity="1" />
            <Stop offset="22%" stopColor="#6E1F8F" stopOpacity="1" />
            <Stop offset="45%" stopColor={MarketPalette.plum} stopOpacity="1" />
            <Stop offset="70%" stopColor={MarketPalette.plum} stopOpacity="0" />
          </RadialGradient>
          {/* Cobalt sweep center-left */}
          <RadialGradient
            id="m-cobalt"
            cx="18%"
            cy="55%"
            rx="70%"
            ry="60%"
            fx="18%"
            fy="55%"
          >
            <Stop offset="0%" stopColor={MarketPalette.cobalt} stopOpacity="1" />
            <Stop offset="32%" stopColor="#1E2D8A" stopOpacity="1" />
            <Stop offset="60%" stopColor="#1E2D8A" stopOpacity="0" />
          </RadialGradient>
          {/* Azure crown top-right */}
          <RadialGradient
            id="m-azure"
            cx="90%"
            cy="18%"
            rx="80%"
            ry="70%"
            fx="90%"
            fy="18%"
          >
            <Stop offset="0%" stopColor={MarketPalette.azure} stopOpacity="1" />
            <Stop offset="28%" stopColor={MarketPalette.cobalt} stopOpacity="1" />
            <Stop offset="60%" stopColor={MarketPalette.cobalt} stopOpacity="0" />
          </RadialGradient>
          {/* Peach corner bottom-right */}
          <RadialGradient
            id="m-peach"
            cx="95%"
            cy="85%"
            rx="60%"
            ry="50%"
            fx="95%"
            fy="85%"
          >
            <Stop offset="0%" stopColor={MarketPalette.peach} stopOpacity="1" />
            <Stop offset="25%" stopColor="#E07442" stopOpacity="1" />
            <Stop offset="55%" stopColor="#E07442" stopOpacity="0" />
          </RadialGradient>
          {/* Dark void blob upper center — signature shadow */}
          <RadialGradient
            id="m-void"
            cx="52%"
            cy="28%"
            rx="38%"
            ry="32%"
            fx="52%"
            fy="28%"
          >
            <Stop offset="0%" stopColor={MarketPalette.darkVoid} stopOpacity="1" />
            <Stop offset="35%" stopColor={MarketPalette.darkVoid} stopOpacity="0.6" />
            <Stop offset="70%" stopColor={MarketPalette.darkVoid} stopOpacity="0" />
          </RadialGradient>
        </Defs>
        <Rect width="100%" height="100%" fill="url(#m-magenta)" />
        <Rect width="100%" height="100%" fill="url(#m-cobalt)" />
        <Rect width="100%" height="100%" fill="url(#m-azure)" />
        <Rect width="100%" height="100%" fill="url(#m-peach)" />
        <Rect width="100%" height="100%" fill="url(#m-void)" />
      </Svg>
      <Grain opacity={0.16} />
    </View>
  );
});

export default MarketBackground;
