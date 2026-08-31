/**
 * WishlistRowWithOffers — wrap-компонент для строки вишлиста со swipe-сравнением.
 *
 * Структура:
 *   - ReanimatedSwipeable из react-native-gesture-handler
 *   - В покое: рендерит children (карточка пластинки) + SwipeTab на правом краю
 *   - При swipe-left: открывает OffersDrawer как renderRightActions
 *   - Pulse-анимация язычка играет ОДИН РАЗ на первом mount вишлиста с offers
 *     (управляется через useMarketStore.hasSeenSwipeHint).
 *
 * Этот компонент НЕ знает что внутри children — родитель может передать любую
 * карточку (текущий WishlistRow из collection.tsx или новый дизайн).
 *
 * NB: для @gorhom/bottom-sheet интеграции — родитель должен предоставить
 * onSeeAll callback который зовёт ref.current?.present(...) на OffersBottomSheet.
 *
 * Источник: screens-drawer-a.jsx (WishlistRow + drawer композиция) +
 *           docs/plans/market/MARKET_AND_PRICE_DRAWER.md §2.1-2.2.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import ReanimatedSwipeable, {
  type SwipeableMethods,
} from 'react-native-gesture-handler/ReanimatedSwipeable';

import SwipeTab from './SwipeTab';
import OffersDrawer, { type DrawerOffer } from './OffersDrawer';
import { useMarketStore } from '../../lib/marketStore';

interface WishlistRowWithOffersProps {
  /** Сама карточка пластинки (любой компонент). Получает «язычок» как overlay. */
  children: React.ReactNode;

  /** Топ-3 офферов по цене (для drawer'а). Если массив пуст — drawer не открывается. */
  topOffers: readonly DrawerOffer[];
  /** Сколько ВСЕГО офферов (для footer'а «+N ещё»). */
  totalOffersCount: number;

  /** Callbacks */
  onOfferPress: (offer: DrawerOffer) => void;
  onSeeAllPress: () => void;

  /** Принудительно отключить pulse (для строк где офферов нет). */
  disablePulse?: boolean;

  style?: StyleProp<ViewStyle>;
}

const DRAWER_WIDTH = 264;
const PULSE_DURATION_MS = 800;

export function WishlistRowWithOffers({
  children,
  topOffers,
  totalOffersCount,
  onOfferPress,
  onSeeAllPress,
  disablePulse,
  style,
}: WishlistRowWithOffersProps) {
  const swipeableRef = useRef<SwipeableMethods>(null);
  const hasSeenHint = useMarketStore((s) => s.hasSeenSwipeHint);
  const markHintSeen = useMarketStore((s) => s.markSwipeHintSeen);

  const hasOffers = topOffers.length > 0;
  // Pulse играет только если: офферы есть, юзер ещё не видел подсказку,
  // и явно не отключено родителем.
  const shouldPulse = hasOffers && !hasSeenHint && !disablePulse;

  const [pulsing, setPulsing] = useState(shouldPulse);

  useEffect(() => {
    if (!shouldPulse) return;
    const t = setTimeout(() => {
      setPulsing(false);
      markHintSeen();
    }, PULSE_DURATION_MS);
    return () => clearTimeout(t);
  }, [shouldPulse, markHintSeen]);

  // Если оферов нет — рендерим просто children без язычка.
  if (!hasOffers) {
    return <View style={style}>{children}</View>;
  }

  const renderDrawer = () => (
    <View style={styles.drawerWrap}>
      <OffersDrawer
        topOffers={topOffers}
        totalCount={totalOffersCount}
        onOfferPress={(offer) => {
          onOfferPress(offer);
          // Закрываем drawer после тапа на оффер — родитель уйдёт в Linking.openURL
          swipeableRef.current?.close();
        }}
        onSeeAllPress={() => {
          onSeeAllPress();
          swipeableRef.current?.close();
        }}
        width={DRAWER_WIDTH}
      />
    </View>
  );

  return (
    <ReanimatedSwipeable
      ref={swipeableRef}
      renderRightActions={renderDrawer}
      friction={2}
      rightThreshold={40}
      overshootRight={false}
      containerStyle={style}
    >
      <View style={styles.rowWrap}>
        {children}
        {/* Язычок прибит к правому краю; pointerEvents=none — тап проваливается на children */}
        <SwipeTab pulse={pulsing} />
      </View>
    </ReanimatedSwipeable>
  );
}

const styles = StyleSheet.create({
  rowWrap: {
    position: 'relative',
  },
  drawerWrap: {
    width: DRAWER_WIDTH,
    paddingLeft: 8,
    // Тень drawer'а пробивается за пределы Swipeable'а
    overflow: 'visible',
  },
});

export default WishlistRowWithOffers;
