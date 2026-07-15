/**
 * Сетка пластинок с pinch-to-zoom между 6 уровнями (2 / 3 / 4 / 5 / 7 / 10 колонок).
 *
 * Поведение:
 *   - Pinch (2 пальца): живой scale вокруг focal point, по отпусканию — снап до соседнего
 *     уровня (с учётом velocity, чтобы лёгкий жест уже срабатывал в нужную сторону).
 *   - На крайних уровнях (L0 и L_MAX) pinch в "стену" — резиновый rubber band, без коммита.
 *   - Single-tap на не-максимальном уровне: открыть карточку записи.
 *   - Single-tap на максимальном уровне аутзума: zoom-in до L0 с точным якорением на
 *     тапнутую ячейку (scrollTo сохраняет её под пальцем).
 *   - Long-press: переход в selection mode.
 *
 * Уровни:
 *   - L0 (2 кол.): полный RecordCard с rarity aura, типом, годом, форматом.
 *   - L1 (3 кол.): обложка + двухстрочная подпись (artist / title).
 *   - L2–L5: только обложки, всё мельче. Коллекционки блестят на любом уровне.
 *
 * Гладкость:
 *   - Во время жеста меняется только transform контейнера (UI thread), без re-layout.
 *   - На коммите уровня scale сразу выставляется в (currentScale * oldCellSize/newCellSize),
 *     так что визуально ячейки остаются того же размера, что были под пальцами, и затем
 *     спрингом доезжают до 1.0 — без рывка-зайчика.
 *   - expo-image с disk-кэшем и recyclingKey, на L4+ берётся thumb_image_url.
 */
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Dimensions,
  Text,
  ScrollView,
  RefreshControl,
  Pressable,
  ActivityIndicator,
  LayoutChangeEvent,
  NativeScrollEvent,
  NativeSyntheticEvent,
} from 'react-native';
import { Image } from 'expo-image';
import { GestureDetector, Gesture } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  runOnJS,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Colors, Spacing, BorderRadius, Typography } from '../constants/theme';
import { CollectionItem, WishlistItem } from '../lib/types';
import { getCoverUrl } from '../lib/api';
import { RecordCard } from './RecordCard';
import {
  RarityContext,
  RarityFlags,
  pickRarityTier,
  TierCoverEffects,
} from './RarityAura';

function cleanArtistName(name: string | null | undefined): string {
  if (!name) return '';
  return name.replace(/\s*\(\d+\)\s*$/, '').trim();
}

type ZoomItem = CollectionItem | WishlistItem;

const ZOOM_COLS = [2, 3, 4, 5, 7, 10] as const;
type ZoomLevel = 0 | 1 | 2 | 3 | 4 | 5;
const MAX_LEVEL: ZoomLevel = (ZOOM_COLS.length - 1) as ZoomLevel;

const { width: SCREEN_W } = Dimensions.get('window');
const H_PADDING = Spacing.md;
const COL_GAPS = [Spacing.md, 8, 6, 5, 4, 3] as const;
const ROW_GAPS = [Spacing.md, 12, 8, 6, 5, 4] as const;
const RADIUS_LIST = [BorderRadius.md, 10, 8, 6, 4, 4] as const;
const CAPTION_H_L1 = 38;
// Должно совпадать со styles.expandedInfo.height в RecordCard.tsx — иначе scrollTo
// после коммита L0 промахивается и ячейки «прыгают».
const RECORD_CARD_EXTRA_H = 92;

// Пороги pinch — мягче, чтобы лёгкое движение уже срабатывало.
const SCALE_IN_HARD = 1.18;
const SCALE_OUT_HARD = 0.86;
const VELOCITY_IN = 0.45;
const VELOCITY_OUT = -0.45;

// Spring для коммита уровня — слегка overdamped (ζ ≈ 1.05), чтобы НЕ было
// overshoot за 1.0: иначе после коммита виден лишний кадр, в котором ячейки
// «проскакивают» за финальный размер и затем оседают.
// Критическое демпфирование при mass=0.55, stiffness=280 → c = 2·√(km) ≈ 24.83.
// SNAP оставляем чуть бойчее — это snap-back, тонкий отскок там подсказывает, что
// жест зарегистрирован, но уровень не изменился.
const COMMIT_SPRING = { damping: 26, stiffness: 280, mass: 0.55 };
const SNAP_SPRING = { damping: 22, stiffness: 320, mass: 0.5 };

function cellSizeFor(level: ZoomLevel): number {
  const cols = ZOOM_COLS[level];
  const gap = COL_GAPS[level];
  return (SCREEN_W - H_PADDING * 2 - (cols - 1) * gap) / cols;
}

function cellTotalHeightFor(level: ZoomLevel): number {
  const cs = cellSizeFor(level);
  if (level === 0) return cs + RECORD_CARD_EXTRA_H;
  if (level === 1) return cs + CAPTION_H_L1;
  return cs;
}

interface Props {
  data: ZoomItem[];
  onRecordPress?: (item: ZoomItem) => void;
  onLongPress?: (itemId: string) => void;
  isSelectionMode?: boolean;
  selectedItems?: Set<string>;
  onToggleItemSelection?: (itemId: string) => void;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  onEndReached?: () => void;
  ListHeaderComponent?: React.ReactElement;
  isLoadingMore?: boolean;
  contentBottomPad?: number;
  rarityContext?: RarityContext;
  /**
   * Per-record HotStock summary map (discogs_id → ResolvedHotStock).
   * Передаётся из (tabs)/collection.tsx после `api.getOffersSummary`.
   * Прокидывается в карточку через `hotStock` prop (только в `expanded`
   * cardVariant — в tile-режиме без overlay'я нет места для pill'а).
   */
  hotStockMap?: Map<string, { variant: any; price: number } | null>;
  /** Wishlist tile/list badge-режим — см. RecordCard.useOfferBadge. */
  useOfferBadge?: boolean;
  /** record.id пластинок на радаре — бейдж на карточке. */
  radarRecordIds?: Set<string>;
  /** Pinch-зум сетки. false → жёстко отключить (напр. чужой профиль, пока не починим). */
  pinchEnabled?: boolean;
}

interface BareCellProps {
  item: ZoomItem;
  level: ZoomLevel;
  cellSize: number;
  radius: number;
  isSelected: boolean;
  isSelectionMode: boolean;
  rarityContext: RarityContext;
  onPress: (item: ZoomItem) => void;
  onLongPress?: (itemId: string) => void;
}

const BareCell = memo(function BareCell({
  item,
  level,
  cellSize,
  radius,
  isSelected,
  isSelectionMode,
  rarityContext,
  onPress,
  onLongPress,
}: BareCellProps) {
  const record = item.record;
  // Один и тот же URL для всех уровней — иначе при пересечении границы (L3↔L4)
  // expo-image видит смену source и кратко перерисовывает картинку, что выглядит
  // как «вставка кадра» между уровнями. С disk-кэшем bandwidth не страдает.
  const coverUrl = useMemo(() => getCoverUrl(record), [record]);

  // Только collectible получает визуальный сигнал на голых обложках —
  // блестит и переливается на всех уровнях.
  const tier = useMemo(
    () => pickRarityTier(record as unknown as RarityFlags, rarityContext),
    [record, rarityContext]
  );
  const showShimmer = tier === 'collectible';

  const handleLongPress = useCallback(() => {
    if (onLongPress) {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      onLongPress(item.id);
    }
  }, [item.id, onLongPress]);

  return (
    <Pressable
      onPress={() => onPress(item)}
      onLongPress={handleLongPress}
      delayLongPress={350}
      style={({ pressed }) => [
        styles.bareCellWrapper,
        { width: cellSize, opacity: pressed ? 0.85 : 1 },
      ]}
    >
      <View
        style={{
          width: cellSize,
          height: cellSize,
          borderRadius: radius,
          backgroundColor: Colors.surface,
          overflow: 'hidden',
        }}
      >
        {coverUrl ? (
          <Image
            source={coverUrl}
            style={{ width: '100%', height: '100%' }}
            contentFit="cover"
            cachePolicy="disk"
            recyclingKey={item.id}
            transition={0}
          />
        ) : null}
        {showShimmer && <TierCoverEffects tier="collectible" radius={radius} />}
        {isSelected && <View style={styles.selectedTint} pointerEvents="none" />}
      </View>
      {level === 1 && (
        <View style={styles.captionL1}>
          <Text style={styles.captionArtist} numberOfLines={1}>
            {cleanArtistName(record.artist)}
          </Text>
          <Text style={styles.captionTitle} numberOfLines={1}>
            {record.title}
          </Text>
        </View>
      )}
      {isSelectionMode && (
        <View
          style={[
            styles.selectionMark,
            isSelected ? styles.selectionMarkActive : styles.selectionMarkIdle,
          ]}
        >
          {isSelected && <View style={styles.selectionDot} />}
        </View>
      )}
    </Pressable>
  );
});

export function ZoomableRecordGrid({
  data,
  onRecordPress,
  onLongPress,
  isSelectionMode = false,
  selectedItems,
  onToggleItemSelection,
  isRefreshing,
  onRefresh,
  onEndReached,
  ListHeaderComponent,
  isLoadingMore,
  contentBottomPad = 120,
  rarityContext = 'collection',
  hotStockMap,
  useOfferBadge = false,
  radarRecordIds,
  pinchEnabled = true,
}: Props) {
  const [level, setLevel] = useState<ZoomLevel>(0);

  const scrollRef = useRef<ScrollView>(null);
  const scrollY = useRef(0);
  const gridTopY = useRef(0);

  const scale = useSharedValue(1);
  const focalX = useSharedValue(SCREEN_W / 2);
  const focalY = useSharedValue(200);
  const levelSv = useSharedValue<number>(level);

  useEffect(() => {
    levelSv.value = level;
  }, [level, levelSv]);

  const cols = ZOOM_COLS[level];
  const cellSize = useMemo(() => cellSizeFor(level), [level]);
  const radius = RADIUS_LIST[level];
  const columnGap = COL_GAPS[level];
  const rowGap = ROW_GAPS[level];

  const commitLevelAnchored = useCallback(
    (newLevelNum: number, anchorIndex: number) => {
      const newLevel = newLevelNum as ZoomLevel;
      if (newLevel === level) {
        scale.value = withSpring(1, SNAP_SPRING);
        return;
      }
      const safeIdx = Math.max(0, Math.min(data.length - 1, anchorIndex));
      const oldCols = ZOOM_COLS[level];
      const newCols = ZOOM_COLS[newLevel];
      const oldRow = Math.floor(safeIdx / oldCols);
      const newRow = Math.floor(safeIdx / newCols);
      const oldCellHTotal = cellTotalHeightFor(level) + ROW_GAPS[level];
      const newCellHTotal = cellTotalHeightFor(newLevel) + ROW_GAPS[newLevel];

      const desiredScrollY = Math.max(
        0,
        newRow * newCellHTotal - oldRow * oldCellHTotal + scrollY.current
      );

      const oldCellSize = cellSizeFor(level);
      const newCellSize = cellSizeFor(newLevel);
      const ratio = oldCellSize / newCellSize;

      // Compensated scale: визуальный размер ячейки в момент коммита совпадает с тем,
      // что был под пальцами. Spring потом плавно доводит до 1.0.
      // Для multi-level прыжков (тап с MAX_LEVEL) capаем диапазон, иначе сетка
      // рендерится в ~10% и выглядит плавающим thumbnail'ом — мы хотим лёгкий
      // визуальный рост, а не телепортацию через крошечный размер.
      const currentScale = scale.value;
      let compensated = currentScale * ratio;
      const distance = Math.abs(newLevel - level);
      if (distance > 1) {
        compensated = Math.max(0.55, Math.min(1.8, compensated));
      }

      Haptics.selectionAsync().catch(() => undefined);
      scale.value = compensated;
      setLevel(newLevel);

      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ y: desiredScrollY, animated: false });
        scrollY.current = desiredScrollY;
        scale.value = withSpring(1, COMMIT_SPRING);
      });
    },
    [level, data.length, scale]
  );

  const indexFromFocal = useCallback(() => {
    const yInContent = focalY.value + scrollY.current;
    const yInGrid = Math.max(0, yInContent - gridTopY.current);
    const oldCellHTotal = cellTotalHeightFor(level) + ROW_GAPS[level];
    const row = Math.floor(yInGrid / Math.max(1, oldCellHTotal));
    const xInGrid = Math.max(0, focalX.value - H_PADDING);
    const oldCellW = cellSizeFor(level);
    const col = Math.min(
      ZOOM_COLS[level] - 1,
      Math.max(0, Math.floor(xInGrid / Math.max(1, oldCellW + COL_GAPS[level])))
    );
    return Math.min(data.length - 1, row * ZOOM_COLS[level] + col);
  }, [level, data.length, focalX, focalY]);

  const TAP_ZOOM_TARGET: ZoomLevel = 2; // 4 кол. — как в Фото на iPhone

  const handleCellPress = useCallback(
    (item: ZoomItem) => {
      if (isSelectionMode) {
        onToggleItemSelection?.(item.id);
        return;
      }
      if (level !== MAX_LEVEL) {
        onRecordPress?.(item);
        return;
      }
      const idx = data.findIndex((d) => d.id === item.id);
      if (idx < 0) {
        onRecordPress?.(item);
        return;
      }
      // Якорим focal на центр тапнутой ячейки на экране — иначе transform scale
      // считает по протухшим focalX/Y с прошлого жеста и грид болтается посреди экрана.
      const oldCols = ZOOM_COLS[level];
      const oldCellSize = cellSizeFor(level);
      const oldColGap = COL_GAPS[level];
      const oldRow = Math.floor(idx / oldCols);
      const oldCol = idx % oldCols;
      const cellLeft = H_PADDING + oldCol * (oldCellSize + oldColGap);
      const cellTopOnScreen =
        gridTopY.current + oldRow * (cellTotalHeightFor(level) + ROW_GAPS[level]) - scrollY.current;
      focalX.value = cellLeft + oldCellSize / 2;
      focalY.value = cellTopOnScreen + oldCellSize / 2;

      commitLevelAnchored(TAP_ZOOM_TARGET, idx);
    },
    [isSelectionMode, level, data, onToggleItemSelection, onRecordPress, commitLevelAnchored, focalX, focalY]
  );

  const pinchCommit = useCallback(
    (next: number) => {
      const idx = indexFromFocal();
      commitLevelAnchored(next, idx);
    },
    [indexFromFocal, commitLevelAnchored]
  );

  const snapBack = useCallback(() => {
    scale.value = withSpring(1, SNAP_SPRING);
  }, [scale]);

  // ─── Pinch ──────────────────────────────────────────────────────────────
  const pinch = Gesture.Pinch()
    .enabled(pinchEnabled)
    .onStart((event) => {
      'worklet';
      focalX.value = event.focalX;
      focalY.value = event.focalY;
    })
    .onUpdate((event) => {
      'worklet';
      const lvl = levelSv.value;
      let s = event.scale;
      // На крайних уровнях — жёсткий rubber band с самого scale=1.
      if (lvl <= 0 && s > 1) {
        s = 1 + (s - 1) * 0.18;
      } else if (lvl >= MAX_LEVEL && s < 1) {
        s = 1 - (1 - s) * 0.18;
      }
      // Мягкое сдерживание на экстремумах вне зависимости от уровня.
      if (s > 2.0) s = 2.0 + (s - 2.0) * 0.2;
      if (s < 0.45) s = 0.45 + (s - 0.45) * 0.25;
      scale.value = s;
      focalX.value = event.focalX;
      focalY.value = event.focalY;
    })
    .onEnd((event) => {
      'worklet';
      const lvl = levelSv.value;
      const s = scale.value;
      const v = (event as unknown as { velocity?: number }).velocity ?? 0;
      const goingIn = s > SCALE_IN_HARD || (s > 1.02 && v > VELOCITY_IN);
      const goingOut = s < SCALE_OUT_HARD || (s < 0.98 && v < VELOCITY_OUT);

      if (goingIn && lvl > 0) {
        runOnJS(pinchCommit)(lvl - 1);
      } else if (goingOut && lvl < MAX_LEVEL) {
        runOnJS(pinchCommit)(lvl + 1);
      } else {
        runOnJS(snapBack)();
      }
    });

  const animatedStyle = useAnimatedStyle(() => {
    const s = scale.value;
    return {
      transform: [
        { translateX: focalX.value * (1 - s) },
        { translateY: focalY.value * (1 - s) },
        { scale: s },
      ],
    };
  });

  const handleScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const ne = e.nativeEvent;
      scrollY.current = ne.contentOffset.y;
      if (!onEndReached) return;
      const distance = ne.contentSize.height - ne.contentOffset.y - ne.layoutMeasurement.height;
      if (distance < ne.layoutMeasurement.height * 0.5) {
        onEndReached();
      }
    },
    [onEndReached]
  );

  const handleGridLayout = useCallback((e: LayoutChangeEvent) => {
    gridTopY.current = e.nativeEvent.layout.y;
  }, []);

  return (
    <GestureDetector gesture={pinch}>
      <ScrollView
        ref={scrollRef}
        style={styles.flex}
        contentContainerStyle={[styles.scrollContent, { paddingBottom: contentBottomPad }]}
        showsVerticalScrollIndicator={false}
        scrollEventThrottle={32}
        onScroll={handleScroll}
        refreshControl={
          onRefresh ? (
            <RefreshControl refreshing={!!isRefreshing} onRefresh={onRefresh} tintColor={Colors.royalBlue} />
          ) : undefined
        }
      >
        {ListHeaderComponent}
        <Animated.View
          onLayout={handleGridLayout}
          style={[
            styles.grid,
            { columnGap, rowGap },
            animatedStyle,
          ]}
        >
          {data.map((item) => {
            const isSelected = isSelectionMode && !!selectedItems?.has(item.id);
            if (level === 0) {
              return (
                <View key={item.id} style={{ width: cellSize }}>
                  <RecordCard
                    record={item.record}
                    variant="expanded"
                    onPress={isSelectionMode ? undefined : () => handleCellPress(item)}
                    onToggleSelection={
                      isSelectionMode && onToggleItemSelection
                        ? () => onToggleItemSelection(item.id)
                        : undefined
                    }
                    onLongPress={onLongPress ? () => onLongPress(item.id) : undefined}
                    isSelectionMode={isSelectionMode}
                    hotStock={
                      hotStockMap && item.record.discogs_id
                        ? hotStockMap.get(item.record.discogs_id) ?? undefined
                        : undefined
                    }
                    useOfferBadge={useOfferBadge}
                    onRadar={radarRecordIds ? radarRecordIds.has(item.record.id) : false}
                    isSelected={isSelected}
                    rarityContext={rarityContext}
                    noRarityAura={false}
                  />
                </View>
              );
            }
            return (
              <BareCell
                key={item.id}
                item={item}
                level={level}
                cellSize={cellSize}
                radius={radius}
                isSelected={isSelected}
                isSelectionMode={isSelectionMode}
                rarityContext={rarityContext}
                onPress={handleCellPress}
                onLongPress={onLongPress}
              />
            );
          })}
        </Animated.View>
        {isLoadingMore && (
          <View style={styles.footer}>
            <ActivityIndicator color={Colors.royalBlue} />
          </View>
        )}
      </ScrollView>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  scrollContent: {
    paddingTop: Spacing.sm,
    paddingHorizontal: H_PADDING,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    transformOrigin: 'top left',
  },
  bareCellWrapper: {
    alignItems: 'flex-start',
  },
  captionL1: {
    height: CAPTION_H_L1,
    marginTop: 6,
    paddingHorizontal: 2,
  },
  captionArtist: {
    ...Typography.caption,
    color: Colors.textMuted,
    fontSize: 10,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  captionTitle: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontFamily: 'Inter_600SemiBold',
    fontSize: 12,
    marginTop: 2,
  },
  selectionMark: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  selectionMarkIdle: {
    backgroundColor: 'rgba(0,0,0,0.25)',
    borderColor: 'rgba(255,255,255,0.85)',
  },
  selectionMarkActive: {
    backgroundColor: Colors.royalBlue,
    borderColor: Colors.background,
  },
  selectionDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.background,
  },
  selectedTint: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(59,75,245,0.25)',
  },
  footer: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
});

export default ZoomableRecordGrid;
