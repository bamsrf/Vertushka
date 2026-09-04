/**
 * /market — standalone Маркет (direct entry).
 *
 * Используется при прямой навигации (например с детальной записи через
 * OffersBlock). На (tabs)/search Маркет живёт как нижний слой curtain'ы —
 * туда сюда не попасть.
 *
 * Жест выхода: overdrag сверху → router.back(). См. MarketMain + curtain.
 */
import React, { useCallback, useEffect, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  runOnJS,
  useAnimatedScrollHandler,
  useDerivedValue,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';

import { MarketPalette } from '../../constants/theme';
import MarketBackground from '../../components/market/MarketBackground';
import MarketMain from '../../components/market/MarketMain';
import { useMarketStore } from '../../lib/marketStore';
import { analytics } from '../../lib/analytics';

const EXIT_COMMIT_DISTANCE = 110;

export default function MarketIndexScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const setMarketCommitted = useMarketStore((s) => s.setCommitted);
  useEffect(() => {
    setMarketCommitted(true);
    return () => setMarketCommitted(false);
  }, [setMarketCommitted]);

  // Точка входа приезжает в `from` — но само событие шлёт тот, кто нажал (см.
  // MarketEntry в lib/analytics.ts). Здесь ловим только заход, который никто
  // не объявил: диплинк, пуш, ручной ввод роута. Без этой ветки такие сессии
  // выпадали бы из воронки целиком.
  const { from } = useLocalSearchParams<{ from?: string }>();
  useEffect(() => {
    if (!from) analytics.viewMarket('deeplink');
    // Mount-only. Экран живёт с тем `from`, с которым открылся, а повторный
    // прогон эффекта дал бы второе событие на тот же самый заход.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exitProgress = useSharedValue(0);
  const dragging = useSharedValue(0);
  const lastHapticStep = useSharedValue(-1);
  const committingRef = useRef(false);

  const fireTick = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  }, []);
  const fireCommitHaptic = useCallback(() => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
  }, []);
  const fireMiss = useCallback(() => {
    Haptics.selectionAsync().catch(() => {});
  }, []);

  useDerivedValue(() => {
    if (dragging.value === 0) return;
    const p = exitProgress.value;
    let step = 0;
    if (p >= 1) step = 3;
    else if (p >= 0.66) step = 2;
    else if (p >= 0.33) step = 1;
    if (step > lastHapticStep.value) {
      lastHapticStep.value = step;
      if (step === 3) runOnJS(fireCommitHaptic)();
      else if (step > 0) runOnJS(fireTick)();
    } else if (step < lastHapticStep.value) {
      lastHapticStep.value = step;
    }
  });

  const handleCurtainExit = useCallback(() => {
    if (committingRef.current) return;
    committingRef.current = true;
    // Жест называется pull-to-search → всегда ведём в Поиск, а не back()
    // к экрану, что запушил Маркет (запись/коллекция).
    //
    // /market — root-route поверх (tabs). replace монтирует СВЕЖИЙ search-
    // таб, который читает committed из persisted marketStore. Сбрасываем
    // committed=false ДО навигации, иначе search re-открывает Маркет-слой.
    setMarketCommitted(false);
    router.replace('/(tabs)/search');
  }, [router, setMarketCommitted]);

  const onScroll = useAnimatedScrollHandler({
    onScroll: (e) => {
      if (dragging.value === 0) return;
      const overdrag = Math.max(0, -e.contentOffset.y);
      exitProgress.value = Math.min(1.25, overdrag / EXIT_COMMIT_DISTANCE);
    },
    onBeginDrag: () => {
      dragging.value = 1;
      lastHapticStep.value = -1;
    },
    onEndDrag: () => {
      dragging.value = 0;
      if (exitProgress.value >= 1) {
        exitProgress.value = withSpring(
          1,
          { damping: 22, stiffness: 220, mass: 0.6, overshootClamping: true },
          (done) => { if (done) runOnJS(handleCurtainExit)(); },
        );
      } else {
        if (exitProgress.value > 0.2) runOnJS(fireMiss)();
        exitProgress.value = withTiming(0, { duration: 260 });
      }
    },
  });

  return (
    <View style={styles.root}>
      <MarketBackground forcedMode="market" />
      <MarketMain onScroll={onScroll} paddingTop={insets.top + 16} pullFraction={exitProgress} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: MarketPalette.void,
  },
});
