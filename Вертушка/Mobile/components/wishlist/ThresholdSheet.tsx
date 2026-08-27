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
  BottomSheetScrollView,
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
import { router } from 'expo-router';
import { Colors, Typography } from '../../constants/theme';
import { RadarIcon } from '../RadarIcon';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { useCollectionStore } from '../../lib/store';
import { useRadarReopen } from '../../lib/radarReopen';
import { WishlistCondition } from '../../lib/types';

const AnimatedTextInput = Animated.createAnimatedComponent(TextInput);

export interface ThresholdSheetData {
  itemId: string;
  recordId: string;
  /**
   * ЖИВАЯ цена маркета (самый дешёвый in_stock листинг). Показывается как
   * «сейчас» и по ней считается предупреждение «порог выше текущей цены».
   * Не путать с priceHint: оценку Discogs сюда класть нельзя — она не имеет
   * отношения к тому, за сколько пластинку реально продают.
   */
  currentPrice?: number | null;
  /**
   * Оценка Discogs — только чтобы задать разумные границы слайдера, пока не
   * приехала цена маркета. Как «сейчас» НЕ показывается.
   */
  priceHint?: number | null;
  threshold?: number | null;
  /** Задан → открываемся в режиме «дешевле обычного» с этой скидкой. */
  thresholdPct?: number | null;
  conditions?: WishlistCondition[] | null;
  subscribed?: boolean; // уже на радаре → показываем «Убрать радар»
}

export interface ThresholdSheetRef {
  present: (data: ThresholdSheetData) => void;
}

interface Props {
  onSaved?: () => void;
  onOpenRadar?: () => void;
}

const CONDITION_OPTIONS: { key: WishlistCondition; label: string }[] = [
  { key: 'sealed', label: 'Запечатана' },
  { key: 'mint', label: 'Идеальная (M/NM)' },
  { key: 'vg_plus', label: 'Отличная (VG+)' },
  { key: 'vg', label: 'Хорошая (VG)' },
];

const DEFAULT_CONDITIONS: WishlistCondition[] = ['sealed', 'mint'];
const STEP = 100;
// Нижняя граница порога. Раньше низ считался от текущей цены (40% / −500), и на
// дорогих релизах ползунок упирался в 4—5 тысяч: ставку «жду до 100 ₽» выставить
// было нечем. Плюс кнопка [−] клампилась по 0, а дисплей — по lo, поэтому ниже lo
// цифра замирала, а в сохранение уходило другое число.
const MIN_THRESHOLD = 100;
// Цвета засечек-ориентиров на треке (текущая цена / исторический минимум).
const TICK_CURRENT = '#9A9EBF';
const TICK_LOW = '#30A46C';

// Режим «дешевле обычного»: скидка от медианы дневных минимумов за 90 дней.
// Абсолютный порог протухает — рынок дорожает, число остаётся, радар молчит.
const PCT_PRESETS = [10, 15, 20, 25, 30, 40];
const DEFAULT_PCT = 20;
// Паритет с MIN_BASELINE_DAYS на бэке: на двух точках «обычная цена» — это
// просто последняя цена, обещать по ней «дешевле обычного» нельзя.
const MIN_BASELINE_POINTS = 5;

type ThresholdMode = 'fixed' | 'relative';

/** Медиана — как percentile_cont(0.5) на бэке (чётная длина → среднее середин). */
function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const fmt = (n: number) => (Number.isFinite(n) ? Math.round(n) : 0).toLocaleString('ru-RU');
const roundTo = (n: number, step: number) => Math.max(0, Math.round(n / step) * step);
const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));
// Приводим к number|null. Два источника мусора:
//  1) NaN у absent-пластинок — `??` ловит только null/undefined, и NaN протекал
//     бы во все расчёты границ;
//  2) СТРОКИ — Pydantic сериализует Decimal в JSON строкой, поэтому цена и
//     порог из /wishlists/radar приходят как "5000.00". Гард пропускал только
//     number, и сохранённый порог молча терялся: шторка открывалась со 100 ₽
//     вместо зафиксированной суммы. Пустую строку не пускаем — Number('') = 0.
const finite = (n: unknown): number | null => {
  const v = typeof n === 'string' ? (n.trim() === '' ? NaN : Number(n)) : n;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
};

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

export const ThresholdSheet = forwardRef<ThresholdSheetRef, Props>(({ onSaved, onOpenRadar }, ref) => {
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
  const [mode, setMode] = useState<ThresholdMode>('fixed');
  const [pct, setPct] = useState(DEFAULT_PCT);
  const [baseline, setBaseline] = useState<number | null>(null);
  // Оценка Discogs: только для границ слайдера, в «сейчас» не попадает.
  const [hint, setHint] = useState<number | null>(null);

  // Во что превратится «на N% дешевле обычного» прямо сейчас. Без базы (мало
  // истории) бэкенд откатывается на абсолютный порог — так и пишем.
  const relativeTarget = baseline != null ? Math.round(baseline * (1 - pct / 100)) : null;

  // Границы: MIN_THRESHOLD … выше текущей (порог можно и выше цены).
  const bounds = useMemo(() => {
    const amt = Number.isFinite(amount) ? amount : 0;
    const base = current ?? hint ?? (amt > 0 ? amt : 5000);
    const hi = Math.max(base * 1.6, base + 3000, amt + STEP);
    return { lo: MIN_THRESHOLD, hi: Math.max(Math.ceil(hi), MIN_THRESHOLD + 500) };
  }, [current, hint, amount]);

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
  const commitAmount = useCallback((v: number, hi: number) => {
    setAmount(clamp(roundTo(Number.isFinite(v) ? v : 0, 50), MIN_THRESHOLD, hi));
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
          runOnJS(commitAmount)(v, sHi.value);
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
    const hint = finite(d.priceHint);
    const th = finite(d.threshold);
    const seed = cp ?? hint;
    const amt0 = Math.max(MIN_THRESHOLD, th ?? (seed ? roundTo(seed * 0.9, STEP) : 0));
    setAmount(amt0);
    setCurrent(cp);
    setHint(hint);
    setLow(null);
    setBaseline(null);
    setMode(d.thresholdPct ? 'relative' : 'fixed');
    setPct(d.thresholdPct ?? DEFAULT_PCT);
    setConds(d.conditions && d.conditions.length ? d.conditions : DEFAULT_CONDITIONS);
    // Синхронно засеваем sharedValue'ы границ/позиции ДО показа листа — иначе первый
    // кадр считает по дефолтам (sLo=0/sHi=1) и мелькают «единичные цифры» до useEffect.
    const base0 = seed ?? (amt0 > 0 ? amt0 : 5000);
    const lo0 = MIN_THRESHOLD;
    const hi0 = Math.max(Math.ceil(Math.max(base0 * 1.6, base0 + 3000, amt0 + STEP)), lo0 + 500);
    sLo.value = lo0;
    sHi.value = hi0;
    thumbX.value = clamp(hi0 > lo0 ? ((amt0 - lo0) / (hi0 - lo0)) * sW.value : sW.value / 2, 0, sW.value);
    sheetRef.current?.present();
    // Живая цена маркета — самый дешёвый in_stock листинг. Раньше с карточки
    // релиза сюда приезжала оценка Discogs (estimated_price_median_rub), и
    // «сейчас» вместе с предупреждением «сработает сразу» считались по числу,
    // которое к реальным продажам отношения не имеет.
    api
      .getOfferDetailsFullByRecordId(d.recordId)
      .then((res) => {
        const market = finite(res.summary?.min_price_rub);
        if (market != null) setCurrent(market);
      })
      .catch(() => {});
    api
      .getPriceHistory(d.recordId, 90)
      .then((res) => {
        const pts = res.points.filter((p) => finite(p.min_price_rub) != null);
        const latest = pts.length ? finite(pts[pts.length - 1].min_price_rub) : cp;
        setCurrent((prev) => prev ?? latest);
        setLow(finite(res.historical_low_rub));
        // База для «дешевле обычного». points — уже дневные минимумы, ровно то,
        // по чему бэкенд считает медиану: превью не должно расходиться с тем,
        // что реально сработает.
        const daily = pts.map((p) => finite(p.min_price_rub)!).filter((v) => v > 0);
        setBaseline(daily.length >= MIN_BASELINE_POINTS ? median(daily) : null);
        if (th == null && latest != null) {
          setAmount(Math.max(MIN_THRESHOLD, roundTo(latest * 0.9, STEP)));
        }
      })
      .catch(() => {});
  }, []);

  useImperativeHandle(ref, () => ({ present }), [present]);

  const nudge = (delta: number) => {
    Haptics.selectionAsync().catch(() => {});
    setAmount((a) => clamp(roundTo(a + delta, STEP), MIN_THRESHOLD, bounds.hi));
  };

  const toggleCond = (key: WishlistCondition) => {
    Haptics.selectionAsync().catch(() => {});
    setConds((prev) => (prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key]));
  };

  const onSave = async () => {
    if (!data) return;
    sheetRef.current?.dismiss();
    try {
      // Сумму отправляем и в относительном режиме: она остаётся запасным
      // порогом, если истории по записи не хватит на базу, и не теряется при
      // возврате к фиксированному режиму.
      await saveRadar(data.itemId, {
        threshold: amount > 0 ? amount : null,
        thresholdPct: mode === 'relative' ? pct : null,
        conditions: conds.length ? conds : null,
      });
      toast.success(
        mode === 'relative'
          ? `Радар: на ${pct}% дешевле обычного`
          : amount > 0
            ? `Радар: дешевле ${fmt(amount)} ₽`
            : 'На радаре',
      );
      onSaved?.();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409 && detail?.code === 'radar_limit') {
        Alert.alert(
          'Радар заполнен',
          `Можно добавить максимум ${detail.limit ?? 5} релизов. Открой радар и убери один, чтобы добавить новый.`,
          [
            { text: 'Отмена', style: 'cancel' },
            {
              text: 'Открыть радар',
              onPress: () => {
                // Запоминаем шторку, чтобы переоткрыть её после возврата с /radar.
                useRadarReopen.getState().set(data);
                router.push('/radar' as any);
              },
            },
          ],
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

  // Засечки-ориентиры на треке. Без них порог задавался вслепую: шкала 100…1.6×
  // цены линейная, и «дорого/дёшево» на глаз не читалось. Позиции статичные
  // (от bounds, не от thumbX), поэтому считаем на JS — воркеты тут не нужны.
  const tickX = (v: number | null) =>
    v == null || bounds.hi <= bounds.lo
      ? null
      : clamp(((v - bounds.lo) / (bounds.hi - bounds.lo)) * trackW, 0, trackW);
  const curX = tickX(current);
  const lowX = tickX(low);

  // Порог ≥ текущей цены бэкенд сразу отдаёт как status="match" и шлёт пуш
  // «подошла под порог» на пластинку, которая и так дешевле. Раньше это
  // сохранялось молча — предупреждаем до нажатия «Сохранить».
  const firesImmediately = current != null && amount >= current;

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
      {/* ScrollView, а не View: с enableDynamicSizing лист растёт по контенту,
          но упирается в topInset. В режиме «дешевле обычного» блок выше, и
          «Сохранить» уезжал за нижнюю кромку без единого способа доскроллить.
          Горизонтальный pan слайдера не конфликтует с вертикальным скроллом —
          у жеста заявлен activeOffsetX. */}
      <BottomSheetScrollView contentContainerStyle={styles.container}>
        {onOpenRadar ? (
          <TouchableOpacity
            style={styles.radarBtn}
            onPress={() => {
              Haptics.selectionAsync().catch(() => {});
              sheetRef.current?.dismiss();
              onOpenRadar();
            }}
            activeOpacity={0.8}
            hitSlop={8}
          >
            <RadarIcon size={20} color="#fff" />
          </TouchableOpacity>
        ) : null}
        <Text style={styles.title}>Порог цены</Text>
        <Text style={styles.subtitle}>Пуш, когда цена опустится ниже</Text>

        <View style={styles.modeRow}>
          {([
            ['fixed', 'Сумма'],
            ['relative', 'Дешевле обычного'],
          ] as [ThresholdMode, string][]).map(([key, label]) => (
            <TouchableOpacity
              key={key}
              style={[styles.modeBtn, mode === key && styles.modeBtnOn]}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                setMode(key);
              }}
              activeOpacity={0.8}
            >
              <Text style={[styles.modeTxt, mode === key && styles.modeTxtOn]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {mode === 'relative' ? (
          <>
            <View style={styles.amountRow}>
              <Text style={styles.amount}>−{pct}</Text>
              <Text style={styles.rub}> %</Text>
            </View>
            <Text style={styles.relHint}>
              {relativeTarget != null
                ? `обычно ${fmt(baseline!)} ₽ → сработает ниже ${fmt(relativeTarget)} ₽`
                : 'истории цен пока мало — пока следим по фиксированной сумме'}
            </Text>
            <View style={styles.pctRow}>
              {PCT_PRESETS.map((p) => (
                <TouchableOpacity
                  key={p}
                  style={[styles.pctChip, pct === p && styles.pctChipOn]}
                  onPress={() => {
                    Haptics.selectionAsync().catch(() => {});
                    setPct(p);
                  }}
                  activeOpacity={0.8}
                >
                  <Text style={[styles.pctTxt, pct === p && styles.pctTxtOn]}>−{p}%</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.relNote}>
              База — медиана цены за 90 дней, пересчитывается на каждой проверке. Рынок дорожает —
              порог едет за ним, и радар не протухает.
            </Text>
          </>
        ) : (
          <>
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
        {current != null || low != null ? (
          <View style={styles.ticksLegend}>
            {current != null ? (
              <View style={styles.ticksLegendItem}>
                <View style={[styles.legendDash, { backgroundColor: TICK_CURRENT }]} />
                <Text style={styles.context}>сейчас {fmt(current)} ₽</Text>
              </View>
            ) : null}
            {low != null ? (
              <View style={styles.ticksLegendItem}>
                <View style={[styles.legendDash, { backgroundColor: TICK_LOW }]} />
                <Text style={styles.context}>мин. за 90 дней {fmt(low)} ₽</Text>
              </View>
            ) : null}
          </View>
        ) : null}

        <View style={styles.sliderRow}>
          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(-STEP)} hitSlop={8} activeOpacity={0.7}>
            <Text style={styles.sideTxt}>−</Text>
          </TouchableOpacity>

          <View style={styles.trackWrap}>
            <View style={styles.track} onLayout={onTrackLayout}>
              <View style={styles.trackBg} />
              <Animated.View style={[styles.fill, fillStyle]} />
              {lowX != null ? (
                <View style={[styles.tick, { left: lowX - 1, backgroundColor: TICK_LOW }]} pointerEvents="none" />
              ) : null}
              {curX != null ? (
                <View style={[styles.tick, { left: curX - 1, backgroundColor: TICK_CURRENT }]} pointerEvents="none" />
              ) : null}
              <GestureDetector gesture={pan}>
                <Animated.View
                  style={[styles.thumb, thumbStyle]}
                  hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }}
                />
              </GestureDetector>
            </View>
            {/* Подписи = концы шкалы. Раньше слева стоял «мин. за 90 дней», который
                после снижения нижней границы перестал совпадать с началом трека. */}
            <View style={styles.sliderLabels}>
              <Text style={styles.sliderLabel}>{fmt(bounds.lo)} ₽</Text>
              <Text style={styles.sliderLabel}>{fmt(bounds.hi)} ₽</Text>
            </View>
          </View>

          <TouchableOpacity style={styles.sideBtn} onPress={() => nudge(STEP)} hitSlop={8} activeOpacity={0.7}>
            <Text style={styles.sideTxt}>+</Text>
          </TouchableOpacity>
        </View>

        {firesImmediately ? (
          <View style={styles.warnBox}>
            <Text style={styles.warnTxt}>
              Порог выше текущей цены — радар сработает сразу, пуш придёт на первой же проверке.
            </Text>
          </View>
        ) : null}
          </>
        )}

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
          {/* Две вещи, о которых UI молчал. Пустой набор уходит на бэк как
              conditions=null, то есть «любое состояние» — выглядело же это как
              «я ничего не выбрал». А _condition_ok пропускает лот с
              нераспознанным состоянием при любом фильтре (чтобы не прятать
              реальные предложения) — про это стоит предупредить заранее. */}
          <Text style={styles.condFootnote}>
            {conds.length === 0
              ? 'Ничего не отмечено — считаем копии в любом состоянии.'
              : 'Состояние берём из описания лота. Если магазин его не указал, лот всё равно учитываем.'}
          </Text>
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
      </BottomSheetScrollView>
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
  radarBtn: { position: 'absolute', top: 2, right: 24, zIndex: 10, width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.royalBlue },
  subtitle: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center', marginTop: 5 },
  modeRow: { flexDirection: 'row', gap: 6, padding: 4, marginTop: 16, borderRadius: 14, backgroundColor: '#E8EBFA' },
  modeBtn: { flex: 1, paddingVertical: 10, borderRadius: 11, alignItems: 'center' },
  modeBtnOn: { backgroundColor: '#fff' },
  modeTxt: { fontSize: 14, fontFamily: 'Inter_600SemiBold', color: Colors.textSecondary },
  modeTxtOn: { color: Colors.royalBlue },
  relHint: { ...Typography.caption, color: Colors.textSecondary, textAlign: 'center', marginTop: 6, fontVariant: ['tabular-nums'] },
  pctRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginTop: 20 },
  pctChip: { paddingVertical: 10, paddingHorizontal: 16, borderRadius: 9999, backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.border },
  pctChipOn: { backgroundColor: Colors.royalBlue, borderColor: Colors.royalBlue },
  pctTxt: { fontSize: 15, fontFamily: 'Inter_700Bold', color: Colors.royalBlue, fontVariant: ['tabular-nums'] },
  pctTxtOn: { color: '#fff' },
  relNote: { ...Typography.caption, color: Colors.textMuted, lineHeight: 16, marginTop: 14, textAlign: 'center' },
  amountRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', marginTop: 20 },
  amount: { fontFamily: 'Inter_800ExtraBold', fontSize: 52, color: Colors.royalBlue, fontVariant: ['tabular-nums'], letterSpacing: -1, padding: 0, textAlign: 'center', minWidth: 120 },
  rub: { fontFamily: 'Inter_800ExtraBold', fontSize: 40, color: Colors.periwinkle },
  context: { ...Typography.caption, color: Colors.textSecondary, fontVariant: ['tabular-nums'] },
  ticksLegend: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 14, marginTop: 6 },
  ticksLegendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendDash: { width: 9, height: 3, borderRadius: 2 },
  tick: { position: 'absolute', width: 2, height: 16, borderRadius: 1, top: 14 },
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
  warnBox: { marginTop: 16, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 14, backgroundColor: 'rgba(244,160,106,0.16)' },
  warnTxt: { fontSize: 13, lineHeight: 18, color: '#8A5326', fontFamily: 'Inter_500Medium' },
  condCard: { backgroundColor: '#fff', borderRadius: 16, padding: 18, marginTop: 22 },
  condTitle: { ...Typography.bodyBold, color: Colors.text },
  condSub: { ...Typography.caption, color: Colors.textSecondary, marginTop: 2, marginBottom: 12 },
  condRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 7 },
  checkbox: { width: 24, height: 24, borderRadius: 7, borderWidth: 2, borderColor: '#D3D7E6', backgroundColor: Colors.surface, alignItems: 'center', justifyContent: 'center' },
  checkboxOn: { backgroundColor: Colors.royalBlue, borderColor: Colors.royalBlue },
  checkMark: { color: '#fff', fontSize: 14, fontWeight: '900', marginTop: -1 },
  condFootnote: { ...Typography.caption, color: Colors.textMuted, lineHeight: 16, marginTop: 10 },
  condLabel: { fontSize: 15, color: Colors.text },
  condLabelOff: { color: Colors.textSecondary },
  saveBtn: { marginTop: 22, paddingVertical: 18, borderRadius: 16, backgroundColor: Colors.royalBlue, alignItems: 'center' },
  saveTxt: { ...Typography.button, color: '#fff' },
  removeBtn: { paddingVertical: 16, alignItems: 'center', marginTop: 6 },
  removeTxt: { ...Typography.buttonSmall, color: Colors.error, fontFamily: 'Inter_600SemiBold' },
});
