/**
 * PriceHistorySheet — шторка динамики цены (макет 1d). Оверлей по тапу обложки на радаре.
 * Переиспользует PriceSparkline + /records/{id}/price-history. Кнопки «В магазин»/«Порог».
 */
import React, { forwardRef, useImperativeHandle, useRef, useState, useCallback } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, Image } from 'react-native';
import {
  BottomSheetModal,
  BottomSheetScrollView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { PriceSparkline } from '../PriceSparkline';
import { RadarIcon } from '../RadarIcon';
import { api } from '../../lib/api';
import { PriceHistoryResponse, RadarStatus } from '../../lib/types';

export interface PriceHistorySheetData {
  itemId: string;
  recordId: string;
  title: string;
  artist?: string | null;
  coverUrl?: string | null;
  currentPrice?: number | null;
  threshold?: number | null;
  status: RadarStatus;
  buyUrl?: string | null;
  offersCount?: number;
}

export interface PriceHistorySheetRef {
  present: (data: PriceHistorySheetData) => void;
}

interface Props {
  onOpenStore?: (data: PriceHistorySheetData) => void;
  onEditThreshold?: (data: PriceHistorySheetData) => void;
}

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const dm = (iso: string) => {
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
};

const STATUS_PILL: Record<RadarStatus, { label: string; color: string; bg: string }> = {
  match: { label: 'Подходит', color: Colors.success, bg: 'rgba(48,164,108,.14)' },
  available: { label: 'В продаже', color: Colors.royalBlue, bg: '#E8EBFA' },
  alt: { label: 'Альтернатива', color: '#C77A45', bg: 'rgba(244,160,106,.16)' },
  absent: { label: 'Отсутствует', color: Colors.textMuted, bg: Colors.surface },
};

export const PriceHistorySheet = forwardRef<PriceHistorySheetRef, Props>(
  ({ onOpenStore, onEditThreshold }, ref) => {
    const sheetRef = useRef<BottomSheetModal>(null);
    const [data, setData] = useState<PriceHistorySheetData | null>(null);
    const [history, setHistory] = useState<PriceHistoryResponse | null>(null);

    const present = useCallback((d: PriceHistorySheetData) => {
      setData(d);
      setHistory(null);
      sheetRef.current?.present();
      api.getPriceHistory(d.recordId, 90).then(setHistory).catch(() => {});
    }, []);

    useImperativeHandle(ref, () => ({ present }), [present]);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.5} />
      ),
      [],
    );

    // Минимальный «event feed» из точек истории (полноценные события — follow-up).
    const events = (() => {
      if (!history) return [];
      const pts = history.points.filter((p) => p.min_price_rub != null).slice(-4).reverse();
      return pts.map((p, i) => ({
        date: dm(p.date),
        price: p.min_price_rub as number,
        label: i === 0 ? 'Актуальная цена' : 'Цена была',
        drop: i === 0 && pts.length > 1 && (p.min_price_rub as number) < (pts[1].min_price_rub as number),
      }));
    })();

    const pill = data ? STATUS_PILL[data.status] : STATUS_PILL.available;
    const cover = data?.coverUrl ?? null;

    return (
      <BottomSheetModal
        ref={sheetRef}
        snapPoints={['82%']}
        backdropComponent={renderBackdrop}
        handleIndicatorStyle={styles.handle}
        backgroundStyle={styles.sheetBg}
      >
        <BottomSheetScrollView contentContainerStyle={styles.container}>
          <View style={styles.headerRow}>
            {cover ? (
              <Image source={{ uri: cover }} style={styles.cover} />
            ) : (
              <View style={[styles.cover, styles.coverPlaceholder]} />
            )}
            <View style={styles.headerText}>
              {data?.artist ? <Text style={styles.artist}>{data.artist.toUpperCase()}</Text> : null}
              <Text style={styles.title} numberOfLines={2}>{data?.title}</Text>
            </View>
          </View>

          <View style={styles.priceRow}>
            {data?.currentPrice != null ? (
              <Text style={styles.price}>{fmt(data.currentPrice)} ₽</Text>
            ) : null}
            {data?.threshold != null ? (
              <View style={styles.thChip}>
                <RadarIcon size={14} color={Colors.royalBlue} />
                <Text style={styles.thChipTxt}>дешевле {fmt(data.threshold)} ₽</Text>
              </View>
            ) : null}
            <View style={[styles.pill, { backgroundColor: pill.bg }]}>
              <View style={[styles.pillDot, { backgroundColor: pill.color }]} />
              <Text style={[styles.pillTxt, { color: pill.color }]}>{pill.label}</Text>
            </View>
          </View>

          {data?.currentPrice != null ? (
            <Text style={styles.priceHint}>
              {data.offersCount && data.offersCount > 1
                ? `Самое дешёвое из ${data.offersCount} подходящих предложений`
                : 'Самое дешёвое подходящее предложение'}
            </Text>
          ) : null}

          {history && history.points.length > 0 ? (
            <View style={styles.chartCard}>
              <PriceSparkline points={history.points} historicalLow={history.historical_low_rub} width={300} />
            </View>
          ) : null}

          {events.length > 0 ? (
            <View style={styles.histBlock}>
              <Text style={styles.histTitle}>История</Text>
              {events.map((e, i) => (
                <View key={i} style={[styles.histRow, i < events.length - 1 && styles.histRowBorder]}>
                  <Text style={styles.histLabel}>{e.drop ? 'Подешевела' : e.label}</Text>
                  <Text style={styles.histMeta}>
                    {e.date} · <Text style={{ color: e.drop ? Colors.success : Colors.textSecondary, fontWeight: '700' }}>{fmt(e.price)} ₽</Text>
                  </Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.btnRow}>
            <TouchableOpacity
              style={styles.primaryBtn}
              activeOpacity={0.9}
              onPress={() => { sheetRef.current?.dismiss(); data && onOpenStore?.(data); }}
            >
              <Text style={styles.primaryTxt}>{data?.buyUrl ? 'Заказать в магазине' : 'В магазин'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={() => { sheetRef.current?.dismiss(); data && onEditThreshold?.(data); }}>
              <RadarIcon size={16} color={Colors.royalBlue} />
              <Text style={styles.secondaryTxt}>Порог</Text>
            </TouchableOpacity>
          </View>
        </BottomSheetScrollView>
      </BottomSheetModal>
    );
  },
);

PriceHistorySheet.displayName = 'PriceHistorySheet';
export default PriceHistorySheet;

const styles = StyleSheet.create({
  sheetBg: { backgroundColor: Colors.surface, borderRadius: 28 },
  handle: { backgroundColor: '#D3D7E6', width: 40 },
  container: { paddingHorizontal: 22, paddingBottom: 40 },
  headerRow: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  cover: { width: 76, height: 76, borderRadius: 14, backgroundColor: Colors.surfaceHover },
  coverPlaceholder: { backgroundColor: Colors.surfaceHover },
  headerText: { flex: 1, paddingTop: 2 },
  artist: { fontSize: 11, fontFamily: 'Inter_600SemiBold', letterSpacing: 1, color: Colors.textSecondary },
  title: { ...Typography.h3, color: Colors.text, marginTop: 2 },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 18 },
  price: { fontFamily: 'Inter_800ExtraBold', fontSize: 28, color: Colors.text, fontVariant: ['tabular-nums'] },
  priceHint: { fontSize: 12, color: Colors.textSecondary, marginTop: 6 },
  thChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, backgroundColor: '#E8EBFA', borderRadius: 9999 },
  thChipTxt: { fontSize: 13, fontFamily: 'Inter_600SemiBold', color: Colors.royalBlue },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 9999 },
  pillDot: { width: 7, height: 7, borderRadius: 9999 },
  pillTxt: { fontSize: 13, fontFamily: 'Inter_700Bold' },
  chartCard: { marginTop: 18, backgroundColor: '#fff', borderRadius: 14, paddingVertical: 4 },
  histBlock: { marginTop: 16 },
  histTitle: { ...Typography.bodyBold, color: Colors.text, marginBottom: 8 },
  histRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 11 },
  histRowBorder: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  histLabel: { fontSize: 14, color: Colors.text },
  histMeta: { fontSize: 13, color: Colors.textSecondary, fontVariant: ['tabular-nums'] },
  btnRow: { flexDirection: 'row', gap: 12, marginTop: 22 },
  primaryBtn: { flex: 1, alignItems: 'center', paddingVertical: 17, backgroundColor: Colors.royalBlue, borderRadius: 16 },
  primaryTxt: { ...Typography.button, color: '#fff' },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 17, paddingHorizontal: 20, backgroundColor: '#E8EBFA', borderRadius: 16 },
  secondaryTxt: { ...Typography.button, color: Colors.royalBlue },
});
