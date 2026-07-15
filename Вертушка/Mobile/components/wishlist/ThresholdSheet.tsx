/**
 * ThresholdSheet — меню порога цены (макет 1f). Заменяет серый Alert.prompt.
 *
 * Сумма — дисплей, БЕЗ системной клавиатуры. Управление: слайдер (мин.90д → текущая)
 * с боковыми кнопками [−][+] (±100) + пресет-чипы. Плюс фильтр «Состояние релиза».
 * Слайдер на PanResponder (RN core) — надёжно внутри gorhom-портала, без gesture-handler.
 */
import React, { forwardRef, useImperativeHandle, useMemo, useRef, useState, useCallback } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  PanResponder,
  type LayoutChangeEvent,
} from 'react-native';
import {
  BottomSheetModal,
  BottomSheetView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { Colors, Typography } from '../../constants/theme';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { useCollectionStore } from '../../lib/store';
import { WishlistCondition } from '../../lib/types';

export interface ThresholdSheetData {
  itemId: string;
  recordId: string;
  currentPrice?: number | null;
  threshold?: number | null;
  conditions?: WishlistCondition[] | null;
}

export interface ThresholdSheetRef {
  present: (data: ThresholdSheetData) => void;
}

const CONDITION_OPTIONS: { key: WishlistCondition; label: string }[] = [
  { key: 'sealed', label: 'Запечатана' },
  { key: 'mint', label: 'Идеальная (M/NM)' },
  { key: 'vg_plus', label: 'Отличная (VG+)' },
  { key: 'vg', label: 'Хорошая (VG)' },
];

const DEFAULT_CONDITIONS: WishlistCondition[] = ['sealed', 'mint'];
const STEP = 100;

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');
const roundTo = (n: number, step: number) => Math.max(0, Math.round(n / step) * step);
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

export const ThresholdSheet = forwardRef<ThresholdSheetRef, {}>((_props, ref) => {
  const sheetRef = useRef<BottomSheetModal>(null);
  const insets = useSafeAreaInsets();
  const setThreshold = useCollectionStore((s) => s.setWishlistPriceThreshold);
  const setConditions = useCollectionStore((s) => s.setWishlistConditions);

  const [data, setData] = useState<ThresholdSheetData | null>(null);
  const [amount, setAmount] = useState(0);
  const [current, setCurrent] = useState<number | null>(null);
  const [low, setLow] = useState<number | null>(null);
  const [conds, setConds] = useState<WishlistCondition[]>(DEFAULT_CONDITIONS);
  const [trackW, setTrackW] = useState(260);

  // Границы слайдера: мин.90д … текущая (с запасом).
  const bounds = useMemo(() => {
    const hi = current ?? (amount > 0 ? amount * 1.5 : 5000);
    const lo = low ?? Math.min(hi * 0.4, hi - 500);
    return { lo: Math.max(0, Math.floor(lo)), hi: Math.max(hi, lo + 500) };
  }, [current, low, amount]);

  const amountRef = useRef(amount);
  amountRef.current = amount;
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const trackWRef = useRef(trackW);
  trackWRef.current = trackW;

  // px позиции thumb из текущего amount.
  const thumbPx = useMemo(() => {
    const { lo, hi } = bounds;
    const t = hi > lo ? (amount - lo) / (hi - lo) : 0.5;
    return clamp(t * trackW, 0, trackW);
  }, [amount, bounds, trackW]);

  const dragBase = useRef(0);
  const pan = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        const { lo, hi } = boundsRef.current;
        const w = trackWRef.current;
        const t = hi > lo ? (amountRef.current - lo) / (hi - lo) : 0.5;
        dragBase.current = clamp(t * w, 0, w);
      },
      onPanResponderMove: (_e, g) => {
        const w = trackWRef.current;
        const { lo, hi } = boundsRef.current;
        const px = clamp(dragBase.current + g.dx, 0, w);
        const v = lo + (px / w) * (hi - lo);
        setAmount(roundTo(v, 50));
      },
    }),
  ).current;

  const present = useCallback((d: ThresholdSheetData) => {
    setData(d);
    const initial = d.threshold ?? (d.currentPrice ? roundTo(d.currentPrice * 0.9, 100) : 0);
    setAmount(initial);
    setCurrent(d.currentPrice ?? null);
    setLow(null);
    setConds(d.conditions && d.conditions.length ? d.conditions : DEFAULT_CONDITIONS);
    sheetRef.current?.present();
    api
      .getPriceHistory(d.recordId, 90)
      .then((res) => {
        const pts = res.points.filter((p) => p.min_price_rub != null);
        const latest = pts.length ? pts[pts.length - 1].min_price_rub : d.currentPrice ?? null;
        setCurrent((prev) => prev ?? latest ?? null);
        setLow(res.historical_low_rub ?? null);
        if (!d.threshold && latest) setAmount(roundTo(latest * 0.9, 100));
      })
      .catch(() => {});
  }, []);

  useImperativeHandle(ref, () => ({ present }), [present]);

  const nudge = (delta: number) => {
    Haptics.selectionAsync().catch(() => {});
    setAmount((a) => clamp(roundTo(a + delta, STEP), 0, boundsRef.current.hi));
  };

  const presets = useMemo(() => {
    const base = current ?? amount ?? 0;
    return [
      { label: '−10%', value: roundTo(base * 0.9, 50) },
      { label: '−20%', value: roundTo(base * 0.8, 50) },
      { label: fmt(roundTo(base * 0.85, 500)), value: roundTo(base * 0.85, 500) },
      { label: fmt(roundTo(base * 0.7, 500)), value: roundTo(base * 0.7, 500) },
    ];
  }, [current, amount]);

  const toggleCond = (key: WishlistCondition) => {
    Haptics.selectionAsync().catch(() => {});
    setConds((prev) => (prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key]));
  };

  const onSave = async () => {
    if (!data) return;
    sheetRef.current?.dismiss();
    try {
      await setThreshold(data.itemId, amount > 0 ? amount : null);
      await setConditions(data.itemId, conds.length ? conds : null);
      toast.success(amount > 0 ? `Порог: дешевле ${fmt(amount)} ₽` : 'Порог снят');
    } catch {
      toast.error('Не удалось сохранить');
    }
  };

  const onRemove = async () => {
    if (!data) return;
    sheetRef.current?.dismiss();
    try {
      await setThreshold(data.itemId, null);
      await setConditions(data.itemId, null);
      toast.success('Радар снят');
    } catch {
      toast.error('Не удалось убрать радар');
    }
  };

  const onTrackLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    if (w > 0) setTrackW(w);
  };

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.5} />
    ),
    [],
  );

  return (
    <BottomSheetModal
      ref={sheetRef}
      enableDynamicSizing
      topInset={insets.top + 8}
      backdropComponent={renderBackdrop}
      handleIndicatorStyle={styles.handle}
      backgroundStyle={styles.sheetBg}
    >
      <BottomSheetView style={styles.container}>
        <Text style={styles.title}>Порог цены</Text>
        <Text style={styles.subtitle}>Пуш, когда цена опустится ниже</Text>

        <View style={styles.amountRow}>
          <Text style={styles.amount}>{fmt(amount)}</Text>
          <Text style={styles.rub}> ₽</Text>
        </View>
        <Text style={styles.context}>
          {current ? `сейчас ${fmt(current)} ₽` : 'цена уточняется'}
          {low ? ` · мин. за 90 дней: ${fmt(low)} ₽` : ''}
        </Text>

        <View style={styles.sliderRow}>
          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(-STEP)} hitSlop={8}>
            <Text style={styles.sideTxt}>−</Text>
          </TouchableOpacity>

          <View style={styles.trackWrap}>
            <View style={styles.track} onLayout={onTrackLayout}>
              <View style={[styles.fill, { width: thumbPx }]} />
              <View
                style={[styles.thumb, { left: thumbPx - 13 }]}
                {...pan.panHandlers}
                hitSlop={{ top: 14, bottom: 14, left: 14, right: 14 }}
              />
            </View>
            <View style={styles.sliderLabels}>
              <Text style={styles.sliderLabel}>{low ? `мин. ${fmt(low)} ₽` : ''}</Text>
              <Text style={styles.sliderLabel}>{current ? `текущая ${fmt(current)} ₽` : ''}</Text>
            </View>
          </View>

          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(STEP)} hitSlop={8}>
            <Text style={styles.sideTxt}>+</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.chipsRow}>
          {presets.map((p, i) => {
            const active = p.value === amount;
            return (
              <TouchableOpacity
                key={i}
                style={[styles.chip, active && styles.chipActive]}
                onPress={() => setAmount(p.value)}
              >
                <Text style={[styles.chipTxt, active && styles.chipTxtActive]}>{p.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={styles.condCard}>
          <Text style={styles.condTitle}>Состояние релиза</Text>
          <Text style={styles.condSub}>Какие копии считать</Text>
          {CONDITION_OPTIONS.map((opt) => {
            const checked = conds.includes(opt.key);
            return (
              <TouchableOpacity key={opt.key} style={styles.condRow} onPress={() => toggleCond(opt.key)}>
                <View style={[styles.checkbox, checked && styles.checkboxOn]}>
                  {checked ? <Text style={styles.checkMark}>✓</Text> : null}
                </View>
                <Text style={[styles.condLabel, !checked && styles.condLabelOff]}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <TouchableOpacity style={styles.saveBtn} onPress={onSave}>
          <Text style={styles.saveTxt}>Сохранить</Text>
        </TouchableOpacity>
        {(data?.threshold ?? amount) ? (
          <TouchableOpacity style={styles.removeBtn} onPress={onRemove}>
            <Text style={styles.removeTxt}>Убрать радар</Text>
          </TouchableOpacity>
        ) : null}
      </BottomSheetView>
    </BottomSheetModal>
  );
});

ThresholdSheet.displayName = 'ThresholdSheet';
export default ThresholdSheet;

const styles = StyleSheet.create({
  sheetBg: { backgroundColor: Colors.surface, borderRadius: 28 },
  handle: { backgroundColor: '#D3D7E6', width: 40 },
  container: { paddingHorizontal: 24, paddingBottom: 34, paddingTop: 6 },
  title: { ...Typography.h2, color: Colors.text, textAlign: 'center' },
  subtitle: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center', marginTop: 5 },
  amountRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', marginTop: 24 },
  amount: { fontFamily: 'Inter_800ExtraBold', fontSize: 52, color: Colors.royalBlue, fontVariant: ['tabular-nums'], letterSpacing: -1 },
  rub: { fontFamily: 'Inter_800ExtraBold', fontSize: 40, color: Colors.periwinkle },
  context: { ...Typography.caption, color: Colors.textSecondary, textAlign: 'center', marginTop: 4, fontVariant: ['tabular-nums'] },
  sliderRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 14, marginTop: 24 },
  sideBtn: { width: 44, height: 44, borderRadius: 14, backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.border, alignItems: 'center', justifyContent: 'center' },
  sideTxt: { fontFamily: 'Inter_700Bold', fontSize: 24, color: Colors.royalBlue, marginTop: -2 },
  trackWrap: { flex: 1 },
  track: { height: 44, justifyContent: 'center' },
  fill: { position: 'absolute', left: 0, height: 6, borderRadius: 9999, backgroundColor: Colors.royalBlue },
  thumb: { position: 'absolute', width: 26, height: 26, borderRadius: 13, backgroundColor: '#fff', borderWidth: 3, borderColor: Colors.royalBlue, shadowColor: Colors.royalBlue, shadowOpacity: 0.35, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  sliderLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  sliderLabel: { ...Typography.caption, color: Colors.textMuted, fontVariant: ['tabular-nums'] },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10, marginTop: 22 },
  chip: { paddingVertical: 11, paddingHorizontal: 18, borderRadius: 9999, backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.border },
  chipActive: { backgroundColor: Colors.royalBlue, borderColor: Colors.royalBlue },
  chipTxt: { fontFamily: 'Inter_600SemiBold', fontSize: 15, color: Colors.textSecondary, fontVariant: ['tabular-nums'] },
  chipTxtActive: { color: '#fff', fontFamily: 'Inter_700Bold' },
  condCard: { backgroundColor: '#fff', borderRadius: 16, padding: 18, marginTop: 22 },
  condTitle: { ...Typography.bodyBold, color: Colors.text },
  condSub: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2, marginBottom: 12 },
  condRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 7 },
  checkbox: { width: 24, height: 24, borderRadius: 7, borderWidth: 2, borderColor: '#D3D7E6', backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  checkboxOn: { backgroundColor: Colors.royalBlue, borderColor: Colors.royalBlue },
  checkMark: { color: '#fff', fontSize: 14, fontWeight: '900', marginTop: -1 },
  condLabel: { fontSize: 15, color: Colors.text },
  condLabelOff: { color: Colors.textSecondary },
  saveBtn: { marginTop: 22, paddingVertical: 18, borderRadius: 16, backgroundColor: Colors.royalBlue, alignItems: 'center' },
  saveTxt: { ...Typography.button, color: '#fff' },
  removeBtn: { paddingVertical: 14, alignItems: 'center', marginTop: 4 },
  removeTxt: { ...Typography.buttonSmall, color: Colors.error, fontFamily: 'Inter_600SemiBold' },
});
