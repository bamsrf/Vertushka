/**
 * OffersBottomSheet — sheet «Все варианты» с группировкой exact / alt-version.
 *
 * Snaps: 60% / 92% (стандарт @gorhom/bottom-sheet v5).
 * Структура:
 *   - Drag handle (auto)
 *   - Title block: caption «ВСЕ ВАРИАНТЫ» + «{artist} · {title}» + HotStockTag + meta
 *   - List: N × OfferDetailCard exact-match, отсортированные по цене
 *   - Separator «── ДРУГАЯ ВЕРСИЯ МАСТЕРА ──» (если есть alt offers)
 *   - List: M × OfferDetailCard alt-version (isAlt=true)
 *
 * Использует BottomSheetModal — рендерится в Provider (нужно обернуть root
 * приложения в BottomSheetModalProvider). Ref выставляется наружу.
 *
 * Источник: screens-drawer-b.jsx (ScreenBottomSheet60/92) +
 *           docs/plans/MARKET_AND_PRICE_DRAWER.md §2.3.
 */
import { api } from '@/lib/api';
import React, { forwardRef, useImperativeHandle, useMemo, useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import {
  BottomSheetModal,
  BottomSheetScrollView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';

import HotStockTag, { formatPrice } from '../HotStockTag';
import OfferDetailCard, { type OfferDetailData } from './OfferDetailCard';
import { ms } from '../../lib/responsive';

export interface OffersBottomSheetData {
  artist: string;
  title: string;
  /** Минимальная цена exact-match (для HotStockTag в header'е). */
  minPriceRub: number;
  /** Exact-match listing'и того же release. Отсортируйте по цене перед передачей. */
  exactOffers: readonly OfferDetailData[];
  /** Alt-version listing'и (другой pressing того же мастера). Отсортированы по цене. */
  altOffers?: readonly OfferDetailData[];
}

interface OffersBottomSheetProps {
  /** Колбэк при тапе «КУПИТЬ» на любой карточке. Родитель делает affiliate-click. */
  onBuyPress: (offer: OfferDetailData) => void;
  /** Тап на КОРПУС карточки (не «Купить») — обычно navigate к /record/{discogs_id}.
   *  Для alt-version карточек критично — юзер хочет посмотреть подробности
   *  другого pressing'а. Если не задан — корпус не нажимается. */
  onCardPress?: (offer: OfferDetailData) => void;
  /** Loading-флаг для конкретного listingId — на CTA рисуется spinner. */
  buyingListingId?: string;
}

export interface OffersBottomSheetRef {
  /** Открыть с данными конкретного record. */
  present: (data: OffersBottomSheetData) => void;
  dismiss: () => void;
}

export const OffersBottomSheet = forwardRef<OffersBottomSheetRef, OffersBottomSheetProps>(
  function OffersBottomSheet({ onBuyPress, onCardPress, buyingListingId }, ref) {
    const sheetRef = useRef<BottomSheetModal>(null);
    const [data, setData] = React.useState<OffersBottomSheetData | null>(null);

    useImperativeHandle(ref, () => ({
      present: (d: OffersBottomSheetData) => {
        setData(d);
        sheetRef.current?.present();
        // Ачивка M1 «Прицениться»: факт открытия карточки цен в БД не виден,
        // сообщаем о нём явно. Промис не ждём — шторка открывается сразу.
        void api.trackAchievementEvent('price_drawer_opened');
      },
      dismiss: () => {
        sheetRef.current?.dismiss();
      },
    }));

    const snapPoints = useMemo(() => ['60%', '92%'], []);

    const renderBackdrop = (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...props}
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        opacity={0.55}
      />
    );

    const totalCount = (data?.exactOffers.length ?? 0) + (data?.altOffers?.length ?? 0);

    return (
      <BottomSheetModal
        ref={sheetRef}
        snapPoints={snapPoints}
        index={0}
        backdropComponent={renderBackdrop}
        handleIndicatorStyle={styles.handleIndicator}
        backgroundStyle={styles.background}
        enableDynamicSizing={false}
        enablePanDownToClose
      >
        <BottomSheetScrollView
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator={false}
        >
          {data && (
            <>
              {/* Title block */}
              <View style={styles.titleBlock}>
                <Text style={styles.caption}>ВСЕ ВАРИАНТЫ</Text>
                <Text style={styles.title} numberOfLines={2}>
                  {data.artist} · {data.title}
                </Text>
                <View style={styles.summaryRow}>
                  <HotStockTag
                    variant="inStockMulti"
                    price={data.minPriceRub}
                    size="sm"
                    showArrow={false}
                    showShadow={false}
                  />
                  <Text style={styles.summaryText}>
                    {totalCount} {pluralizeOffer(totalCount)} · от {formatPrice(data.minPriceRub)}
                  </Text>
                </View>
              </View>

              {/* Exact-match offers (cheapest first highlighted) */}
              <View style={styles.list}>
                {data.exactOffers.map((offer, idx) => (
                  <OfferDetailCard
                    key={offer.listingId}
                    data={offer}
                    highlighted={idx === 0} // cheapest подсвечен
                    onBuyPress={() => onBuyPress(offer)}
                    onCardPress={onCardPress ? () => onCardPress(offer) : undefined}
                    buyLoading={buyingListingId === offer.listingId}
                  />
                ))}
              </View>

              {/* Separator + alt-version offers */}
              {data.altOffers && data.altOffers.length > 0 && (
                <>
                  <View style={styles.separator}>
                    <View style={styles.separatorLine} />
                    <Text style={styles.separatorText}>Пресс может отличаться</Text>
                    <View style={styles.separatorLine} />
                  </View>
                  <View style={styles.list}>
                    {data.altOffers.map((offer) => (
                      <OfferDetailCard
                        key={offer.listingId}
                        data={offer}
                        onBuyPress={() => onBuyPress(offer)}
                        onCardPress={onCardPress ? () => onCardPress(offer) : undefined}
                        buyLoading={buyingListingId === offer.listingId}
                      />
                    ))}
                  </View>
                </>
              )}

              {/* Bottom safety padding */}
              <View style={{ height: 48 }} />
            </>
          )}
        </BottomSheetScrollView>
      </BottomSheetModal>
    );
  },
);

function pluralizeOffer(n: number): string {
  const n10 = n % 10;
  const n100 = n % 100;
  if (n10 === 1 && n100 !== 11) return 'предложение';
  if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return 'предложения';
  return 'предложений';
}

const styles = StyleSheet.create({
  background: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  handleIndicator: {
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: '#DEE2EB',
  },
  content: {
    paddingBottom: 24,
  },
  titleBlock: {
    paddingHorizontal: 18,
    paddingTop: 8,
    paddingBottom: 16,
  },
  caption: {
    fontFamily: 'Inter_700Bold',
    fontSize: 11,
    fontWeight: '700',
    color: '#9A9EBF',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    includeFontPadding: false,
  },
  title: {
    fontFamily: 'Inter_800ExtraBold',
    fontSize: ms(19),
    fontWeight: '800',
    color: '#0E121C',
    letterSpacing: -0.3,
    lineHeight: ms(22),
    marginTop: 4,
    includeFontPadding: false,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 8,
  },
  summaryText: {
    fontFamily: 'Inter_400Regular',
    fontSize: ms(12),
    color: '#4D5263',
    includeFontPadding: false,
  },
  list: {
    paddingHorizontal: 14,
    gap: 10,
  },
  separator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  separatorLine: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: '#ECEEF7',
  },
  separatorText: {
    fontFamily: 'Inter_700Bold',
    fontSize: 10,
    fontWeight: '700',
    color: '#E85A2A',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    includeFontPadding: false,
  },
});

export default OffersBottomSheet;
