/**
 * ThresholdSheet — меню порога цены (макет 1f). Заменяет серый Alert.prompt.
 *
 * Сумма — дисплей, БЕЗ системной клавиатуры. Управление: слайдер (мин.90д → выше
 * текущей) с боковыми кнопками [−][+] (±100). Плюс фильтр «Состояние релиза».
 * Слайдер гладкий: тянем на UI-потоке через reanimated sharedValue (без re-render),
 * сумма-дисплей — animated TextInput. Значение фиксируется в state только на отпускании.
 */
import React, { forwardRef, useImperativeHandle, useMemo, useRef, useState, useCallback, useEffect } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  Alert,
  type LayoutChangeEvent,
} from 'react-native';
import {
  BottomSheetModal,
  BottomSheetView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useAnimatedProps,
  runOnJS,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Colors, Typography } from '../../constants/theme';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { useCollectionStore } from '../../lib/store';
import { WishlistCondition } from '../../lib/types';

const AnimatedTextInput = Animated.createAnimatedComponent(TextInput);

export interface ThresholdSheetData {
  itemId: string;
  recordId: string;
  currentPrice?: number | null;
  threshold?: number | null;
  conditions?: WishlistCondition[] | null;
  subscribed?: boolean; // уже на радаре → показываем «Убрать радар»
}

export interface ThresholdSheetRef {
  present: (data: ThresholdSheetData) => void;
}

interface Props {
  onSaved?: () => void;
}

const CONDITION_OPTIONS: { key: WishlistCondition; label: string }[] = [
  { key: 'sealed', label: 'Запечатана' },
  { key: 'mint', label: 'Идеальная (M/NM)' },
  { key: 'vg_plus', label: 'Отличная (VG+)' },
  { key: 'vg', label: 'Хорошая (VG)' },
];

const DEFAULT_CONDITIONS: WishlistCondition[] = ['sealed', 'mint'];
const STEP = 100;

const fmt = (n: number) => (Number.isFinite(n) ? Math.round(n) : 0).toLocaleString('ru-RU');
const roundTo = (n: number, step: number) => Math.max(0, Math.round(n / step) * step);
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
// Цены с бэка могут приходить как NaN (absent-пластинки) — приводим к number|null,
// т.к. `??` ловит только null/undefined и NaN протекал бы во все расчёты границ.
const finite = (n: unknown): number | null =>
  typeof n === 'number' && Number.isFinite(n) ? n : null;

// Группировка разрядов пробелом — worklet-safe (без toLocaleString в UI-потоке).
function groupWorklet(n: number): string {
  'worklet';
  const r = Math.max(0, Math.round(n));
  const s = String(r);
  let out = '';
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += ' ';
    out += s[i];
  }
  return out;
}

export const ThresholdSheet = forwardRef<ThresholdSheetRef, Props>(({ onSaved }, ref) => {
  const sheetRef = useRef<BottomSheetModal>(null);
  const insets = useSafeAreaInsets();
  const saveRadar = useCollectionStore((s) => s.saveWishlistRadar);
  const removeRadar = useCollectionStore((s) => s.removeWishlistRadar);

  const [data, setData] = useState<ThresholdSheetData | null>(null);
  const [amount, setAmount] = useState(0);
  const [current, setCurrent] = useState<number | null>(null);
  const [low, setLow] = useState<number | null>(null);
  const [conds, setConds] = useState<WishlistCondition[]>(DEFAULT_CONDITIONS);
  const [trackW, setTrackW] = useState(260);

  // Границы: мин.90д … выше текущей (порог можно и выше цены).
  const bounds = useMemo(() => {
    const amt = Number.isFinite(amount) ? amount : 0;
    const base = current ?? (amt > 0 ? amt : 5000);
    const hi = Math.max(base * 1.6, base + 3000, amt + 100);
    const lo = low ?? Math.min(base * 0.4, base - 500);
    const loF = Math.max(0, Math.floor(lo));
    return { lo: loF, hi: Math.max(Math.ceil(hi), loF + 500) };
  }, [current, low, amount]);

  // UI-поток: позиция thumb (px) + зеркала границ/ширины для worklet'ов.
  const thumbX = useSharedValue(0);
  const sLo = useSharedValue(0);
  const sHi = useSharedValue(1);
  const sW = useSharedValue(260);
  const dragging = useRef(false);
  const dragBase = useSharedValue(0);

  // Синхра thumb из state (кроме момента перетаскивания).
  useEffect(() => {
    sLo.value = bounds.lo;
    sHi.value = bounds.hi;
    sW.value = trackW;
    if (!dragging.current) {
      const t = bounds.hi > bounds.lo ? (amount - bounds.lo) / (bounds.hi - bounds.lo) : 0.5;
      thumbX.value = clamp(t * trackW, 0, trackW);
    }
  }, [amount, bounds, trackW]);

  // Жест на react-native-gesture-handler (как у самого bottom-sheet), чтобы
  // вертикальный джиттер при зажатии не «угонял» касание в свайп-закрытие листа.
  // activeOffsetX — заявляем горизонтальное намерение; failOffsetY НЕ задаём, поэтому
  // дрожь по вертикали не отменяет перетаскивание.
  const setDragging = useCallback((v: boolean) => {
    dragging.current = v;
  }, []);
  const commitAmount = useCallback((v: number) => {
    setAmount(roundTo(Number.isFinite(v) ? v : 0, 50));
  }, []);
  const pan = useMemo(
    () =>
      Gesture.Pan()
        .activeOffsetX([-6, 6])
        .onBegin(() => {
          dragBase.value = thumbX.value;
          runOnJS(setDragging)(true);
        })
        .onUpdate((e) => {
          const w = sW.value || 1;
          thumbX.value = Math.max(0, Math.min(w, dragBase.value + e.translationX));
        })
        .onEnd(() => {
          const w = sW.value || 1;
          const v = sLo.value + (thumbX.value / w) * (sHi.value - sLo.value);
          runOnJS(commitAmount)(v);
        })
        .onFinalize(() => {
          runOnJS(setDragging)(false);
        }),
    [setDragging, commitAmount],
  );

  const thumbStyle = useAnimatedStyle(() => ({ transform: [{ translateX: Math.round(thumbX.value) - 13 }] }));
  const fillStyle = useAnimatedStyle(() => ({ width: Math.round(thumbX.value) }));
  const amountProps = useAnimatedProps(() => {
    const w = sW.value || 1;
    const v = sLo.value + (thumbX.value / w) * (sHi.value - sLo.value);
    const safe = Number.isFinite(v) ? Math.round(v / 50) * 50 : 0;
    return { text: groupWorklet(safe) } as any;
  });

  const present = useCallback((d: ThresholdSheetData) => {
    setData(d);
    const cp = finite(d.currentPrice);
    const th = finite(d.threshold);
    const amt0 = th ?? (cp ? roundTo(cp * 0.9, 100) : 0);
    setAmount(amt0);
    setCurrent(cp);
    setLow(null);
    setConds(d.conditions && d.conditions.length ? d.conditions : DEFAULT_CONDITIONS);
    // Синхронно засеваем sharedValue'ы границ/позиции ДО показа листа — иначе первый
    // кадр считает по дефолтам (sLo=0/sHi=1) и мелькают «единичные цифры» до useEffect.
    const base0 = cp ?? (amt0 > 0 ? amt0 : 5000);
    const lo0 = Math.max(0, Math.floor(Math.min(base0 * 0.4, base0 - 500)));
    const hi0 = Math.max(Math.ceil(Math.max(base0 * 1.6, base0 + 3000, amt0 + 100)), lo0 + 500);
    sLo.value = lo0;
    sHi.value = hi0;
    thumbX.value = clamp(hi0 > lo0 ? ((amt0 - lo0) / (hi0 - lo0)) * sW.value : sW.value / 2, 0, sW.value);
    sheetRef.current?.present();
    api
      .getPriceHistory(d.recordId, 90)
      .then((res) => {
        const pts = res.points.filter((p) => finite(p.min_price_rub) != null);
        const latest = pts.length ? finite(pts[pts.length - 1].min_price_rub) : cp;
        setCurrent((prev) => prev ?? latest);
        setLow(finite(res.historical_low_rub));
        if (th == null && latest != null) setAmount(roundTo(latest * 0.9, 100));
      })
      .catch(() => {});
  }, []);

  useImperativeHandle(ref, () => ({ present }), [present]);

  const nudge = (delta: number) => {
    Haptics.selectionAsync().catch(() => {});
    setAmount((a) => clamp(roundTo(a + delta, STEP), 0, bounds.hi));
  };

  const toggleCond = (key: WishlistCondition) => {
    Haptics.selectionAsync().catch(() => {});
    setConds((prev) => (prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key]));
  };

  const onSave = async () => {
    if (!data) return;
    sheetRef.current?.dismiss();
    try {
      await saveRadar(data.itemId, {
        threshold: amount > 0 ? amount : null,
        conditions: conds.length ? conds : null,
      });
      toast.success(amount > 0 ? `Радар: дешевле ${fmt(amount)} ₽` : 'На радаре');
      onSaved?.();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409 && detail?.code === 'radar_limit') {
        Alert.alert(
          'Радар заполнен',
          `Можно добавить максимум ${detail.limit ?? 5} релизов. Убери один, чтобы добавить новый.`,
        );
      } else {
        toast.error('Не удалось сохранить');
      }
    }
  };

  const onRemove = async () => {
    if (!data) return;
    sheetRef.current?.dismiss();
    try {
      await removeRadar(data.itemId);
      toast.success('Убрали с радара');
      onSaved?.();
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
          <AnimatedTextInput
            style={styles.amount}
            editable={false}
            animatedProps={amountProps}
            defaultValue={fmt(amount)}
            underlineColorAndroid="transparent"
          />
          <Text style={styles.rub}> ₽</Text>
        </View>
        {low ? (
          <Text style={styles.context}>мин. за 90 дней: {fmt(low)} ₽</Text>
        ) : null}

        <View style={styles.sliderRow}>
          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(-STEP)} hitSlop={8} activeOpacity={0.7}>
            <Text style={styles.sideTxt}>−</Text>
          </TouchableOpacity>

          <View style={styles.trackWrap}>
            <View style={styles.track} onLayout={onTrackLayout}>
              <View style={styles.trackBg} />
              <Animated.View style={[styles.fill, fillStyle]} />
              <GestureDetector gesture={pan}>
                <Animated.View
                  style={[styles.thumb, thumbStyle]}
                  hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }}
                />
              </GestureDetector>
            </View>
            <View style={styles.sliderLabels}>
              <Text style={styles.sliderLabel}>{low ? `мин. ${fmt(low)} ₽` : ''}</Text>
              <Text style={styles.sliderLabel} />
            </View>
          </View>

          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(STEP)} hitSlop={8} activeOpacity={0.7}>
            <Text style={styles.sideTxt}>+</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.condCard}>
          <Text style={styles.condTitle}>Состояние релиза</Text>
          <Text style={styles.condSub}>Какие копии считать</Text>
          {CONDITION_OPTIONS.map((opt) => {
            const checked = conds.includes(opt.key);
            return (
              <TouchableOpacity key={opt.key} style={styles.condRow} onPress={() => toggleCond(opt.key)} activeOpacity={0.7}>
                <View style={[styles.checkbox, checked && styles.checkboxOn]}>
                  {checked ? <Text style={styles.checkMark}>✓</Text> : null}
                </View>
                <Text style={[styles.condLabel, !checked && styles.condLabelOff]}>{opt.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <TouchableOpacity style={styles.saveBtn} onPress={onSave} activeOpacity={0.9}>
          <Text style={styles.saveTxt}>Сохранить</Text>
        </TouchableOpacity>
        {data?.subscribed ? (
          <TouchableOpacity style={styles.removeBtn} onPress={onRemove} activeOpacity={0.7}>
            <Text style={styles.removeTxt}>Убрать радар</Text>
          </TouchableOpacity>
        ) : null}
        <View style={{ height: Math.max(insets.bottom, 12) }} />
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
  amountRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', marginTop: 20 },
  amount: { fontFamily: 'Inter_800ExtraBold', fontSize: 52, color: Colors.royalBlue, fontVariant: ['tabular-nums'], letterSpacing: -1, padding: 0, textAlign: 'center', minWidth: 120 },
  rub: { fontFamily: 'Inter_800ExtraBold', fontSize: 40, color: Colors.periwinkle },
  context: { ...Typography.caption, color: Colors.textSecondary, textAlign: 'center', marginTop: 4, fontVariant: ['tabular-nums'] },
  sliderRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 14, marginTop: 24 },
  sideBtn: { width: 44, height: 44, borderRadius: 14, backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.border, alignItems: 'center', justifyContent: 'center' },
  sideTxt: { fontFamily: 'Inter_700Bold', fontSize: 24, color: Colors.royalBlue, marginTop: -2 },
  trackWrap: { flex: 1 },
  track: { height: 44, justifyContent: 'center' },
  trackBg: { position: 'absolute', left: 0, right: 0, height: 6, borderRadius: 3, backgroundColor: '#E3E6F3' },
  fill: { position: 'absolute', left: 0, height: 6, borderRadius: 3, backgroundColor: Colors.royalBlue },
  thumb: { position: 'absolute', left: 0, width: 26, height: 26, borderRadius: 13, backgroundColor: '#fff', borderWidth: 3, borderColor: Colors.royalBlue, shadowColor: Colors.royalBlue, shadowOpacity: 0.35, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  sliderLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
  sliderLabel: { ...Typography.caption, color: Colors.textMuted, fontVariant: ['tabular-nums'] },
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
  removeBtn: { paddingVertical: 16, alignItems: 'center', marginTop: 6 },
  removeTxt: { ...Typography.buttonSmall, color: Colors.error, fontFamily: 'Inter_600SemiBold' },
});
