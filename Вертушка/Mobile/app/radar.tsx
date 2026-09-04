/**
 * Радар — экран отслеживания цены (макет 1b/1c).
 *
 * Тёмный MarketPalette-мир. Пластинки-кружки раскладываются по зонам статуса без
 * наложений (равномерные углы + радиус по полосе). Луч вращается; когда проходит
 * сквозь обложку — она подсвечивается и «дышит». Аватар юзера в центре. Тап по
 * кружку → шторка истории; peach → alt-подтверждение.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, useWindowDimensions, Linking, PixelRatio } from 'react-native';
import { Image } from 'expo-image';
import { useRouter, useFocusEffect } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path, Defs, LinearGradient as SvgGradient, RadialGradient, Stop, Circle } from 'react-native-svg';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing,
  interpolate,
  type SharedValue,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Colors, Typography } from '../constants/theme';
import { Icon } from '@/components/ui';
import { RadarIcon } from '../components/RadarIcon';
import { PriceHistorySheet, type PriceHistorySheetRef, type PriceHistorySheetData } from '../components/wishlist/PriceHistorySheet';
import { AltVersionSheet, type AltVersionSheetRef } from '../components/wishlist/AltVersionSheet';
import { ThresholdSheet, type ThresholdSheetRef } from '../components/wishlist/ThresholdSheet';
import { api, getCoverUrl, resolveMediaUrl, sizedCoverUrl } from '../lib/api';
import { analytics } from '../lib/analytics';
import { useAuthStore } from '../lib/store';
import { useRadarReopen } from '../lib/radarReopen';
import { RadarItem, RadarResponse, RadarStatus } from '../lib/types';

const STATUS_COLOR: Record<RadarStatus, string> = {
  match: '#30A46C',
  available: '#5B6AF5',
  alt: '#F4A06A',
  absent: '#9A9EBF',
};

const STATUS_LABEL: Record<RadarStatus, string> = {
  match: 'подходит',
  available: 'в продаже',
  alt: 'альтернатива',
  absent: 'отсутствует',
};

// Порядок раскладки: подходит ближе к центру → отсутствует у края.
const BAND_ORDER: RadarStatus[] = ['match', 'available', 'alt', 'absent'];
const COVER = 50;

// Компактный формат: 3990 → «4к», 3500 → «3,5к», 990 → «990», 1 250 000 → «1,3 млн»
const fmt = (n: number) => {
  const abs = Math.abs(n);
  if (abs < 1000) return String(Math.round(n));
  const compact = (value: number, suffix: string) => {
    const rounded = Math.round(value * 10) / 10;
    const str = (Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)).replace('.', ',');
    return `${str} ${suffix}`;
  };
  if (abs < 1_000_000) return compact(n / 1000, 'к').replace(' к', 'к');
  return compact(n / 1_000_000, 'млн');
};

// «Пропала N дней назад» — при заполненных 5 слотах экран не помогал решить,
// кого выселить. Бэкенд отдаёт absent_since (начало текущей серии absent);
// в первые сутки давность не пишем — «пропала сегодня» ничего не решает.
function absentAge(iso?: string | null): string | null {
  if (!iso) return null;
  const ts = Date.parse(iso.endsWith('Z') ? iso : `${iso}Z`);
  if (!Number.isFinite(ts)) return null;
  const days = Math.floor((Date.now() - ts) / 86_400_000);
  if (days < 1) return null;
  if (days < 30) return `${days} дн.`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} мес.` : '> года';
}

interface Placed {
  item: RadarItem;
  x: number;
  y: number;
  angleDeg: number; // экранные градусы (0 = вправо, по часовой)
}

/** Раскладка без наложений: полоса радиуса по статусу + равномерные углы. */
function layout(items: RadarItem[], C: number): Placed[] {
  // Полосы радиуса (px от центра). Match начинается за пределами аватара.
  const BAND: Record<RadarStatus, [number, number]> = {
    match: [C * 0.34, C * 0.5],
    available: [C * 0.56, C * 0.74],
    alt: [C * 0.78, C * 0.9],
    absent: [C * 0.9, C * 0.99],
  };
  const ordered = [...items].sort((a, b) => {
    const d = BAND_ORDER.indexOf(a.status) - BAND_ORDER.indexOf(b.status);
    return d !== 0 ? d : a.record.id.localeCompare(b.record.id);
  });
  const n = ordered.length || 1;
  return ordered.map((item, i) => {
    const [lo, hi] = BAND[item.status];
    const frac = Math.min(1, Math.max(0, item.radius));
    const r = lo + frac * (hi - lo);
    // Равномерный угол по глобальному индексу → кружки не пересекаются.
    const deg = -90 + (360 / n) * i + 26;
    const rad = (deg * Math.PI) / 180;
    return { item, x: Math.cos(rad) * r, y: Math.sin(rad) * r, angleDeg: (deg + 360) % 360 };
  });
}

/** Одна обложка + «дыхание» при проходе луча. */
function RadarCover({
  placed,
  C,
  sweep,
  onPress,
}: {
  placed: Placed;
  C: number;
  sweep: SharedValue<number>;
  onPress: () => void;
}) {
  const { item, x, y, angleDeg } = placed;
  const color = STATUS_COLOR[item.status];
  const absent = item.status === 'absent';
  const price = item.status === 'alt' ? item.alt?.price_rub : item.lowest_price_rub;
  const age = absent ? absentAge(item.absent_since) : null;
  // Кружок радара — 50pt: нарезка 320 вместо мастера (~1000px). Внешние URL
  // sizedCoverUrl вернёт как есть.
  const cover = sizedCoverUrl(getCoverUrl(item.record), Math.ceil(COVER * PixelRatio.get()));

  // Луч (передняя кромка + центр клина ~+27°) в экранных градусах.
  const beam = useAnimatedStyle(() => {
    const lead = (270 + sweep.value + 27) % 360;
    let diff = Math.abs(lead - angleDeg);
    if (diff > 180) diff = 360 - diff;
    const near = diff < 34 ? 1 - diff / 34 : 0;
    return {
      transform: [{ scale: 1 + near * 0.14 }],
      shadowOpacity: (absent ? 0.35 : 0.55) + near * 0.4,
      shadowRadius: 8 + near * 8,
    };
  });

  return (
    <TouchableOpacity
      activeOpacity={0.85}
      onPress={onPress}
      hitSlop={8}
      style={[styles.coverWrap, { left: C + x - COVER / 2, top: C + y - COVER / 2 }]}
    >
      {item.status === 'match' ? <View style={[styles.buyGlow, { shadowColor: color }]} /> : null}
      <Animated.View style={[styles.coverRing, { borderColor: color, shadowColor: color, opacity: absent ? 0.6 : 1 }, beam]}>
        {cover ? (
          <Image source={cover} style={styles.cover} contentFit="cover" cachePolicy="disk" transition={150} />
        ) : (
          <View style={[styles.cover, styles.coverPh]} />
        )}
        {/* absent → приглушаем до ч/б-подобного серого */}
        {absent ? <View style={styles.absentScrim} pointerEvents="none" /> : null}
      </Animated.View>
      {price != null ? (
        <View style={[styles.priceChip, { borderColor: color }]} pointerEvents="none">
          <Text style={[styles.priceTxt, { color }]} numberOfLines={1}>{fmt(price)} ₽</Text>
        </View>
      ) : age ? (
        // У absent цены нет, слот чипа свободен — занимаем его давностью.
        <View style={[styles.priceChip, { borderColor: color }]} pointerEvents="none">
          <Text style={[styles.priceTxt, { color }]} numberOfLines={1}>{age}</Text>
        </View>
      ) : null}
    </TouchableOpacity>
  );
}

export default function RadarScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const user = useAuthStore((s) => s.user);
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const reopenPending = useRadarReopen((s) => s.pending);

  const historyRef = useRef<PriceHistorySheetRef>(null);
  const altRef = useRef<AltVersionSheetRef>(null);
  const thresholdRef = useRef<ThresholdSheetRef>(null);

  const sweep = useSharedValue(0);
  const pulse = useSharedValue(0);

  const STAGE = Math.min(width - 24, 400);
  const C = STAGE / 2;

  const load = useCallback(() => {
    api.getRadar().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      sweep.value = 0;
      sweep.value = withRepeat(withTiming(360, { duration: 4200, easing: Easing.linear }), -1, false);
      // Пинг-понг одним таймингом (reverse=true), а не withSequence(0→1, 1→0).
      // У последовательности easing применялся к КАЖДОЙ ноге отдельно: на
      // pulse=1 и на стыке цикла анимация тормозила в ноль и тут же
      // разгонялась заново — два мёртвых стопа за цикл, и на сжатии к центру
      // это читалось как подскок аватарки. Синус даёт нулевую скорость на
      // краях без шва, репульсация выходит мягче.
      pulse.value = withRepeat(
        withTiming(1, { duration: 1800, easing: Easing.inOut(Easing.sin) }),
        -1,
        true,
      );
    }, [load]),
  );

  const sweepStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${sweep.value}deg` }] }));
  const haloStyle = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + pulse.value * 0.35 }],
    opacity: interpolate(pulse.value, [0, 1], [0.5, 0]),
  }));
  const avatarStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + pulse.value * 0.025 }] }));

  const items = data?.items ?? [];
  const limit = data?.limit ?? 5;
  const isEmpty = !loading && items.length === 0;
  const avatarSrc = user?.avatar_url ? resolveMediaUrl(user.avatar_url) : undefined;
  const placed = useMemo(() => layout(items, C), [items, C]);

  const onCoverPress = (item: RadarItem) => {
    Haptics.selectionAsync().catch(() => {});
    // Шит подтверждения — ТОЛЬКО для нерешённого предложения. Принятый аналог
    // ведёт в шторку цены, как обычная «в продаже»: раньше он открывал этот же
    // шит и при каждом тапе переспрашивал «считать подходящим?», хотя юзер уже
    // согласился. Отмена решения теперь живёт внутри шторки цены.
    if (item.alt && item.status === 'alt' && !item.accept_alt) {
      altRef.current?.present({
        itemId: item.wishlist_item_id,
        altRecordId: item.alt.record_id,
        recordTitle: item.record.title,
        recordArtist: item.record.artist,
        recordYear: (item.record as any).year ?? null,
        recordCountry: (item.record as any).country ?? null,
        altTitle: item.alt.title,
        altCoverUrl: item.alt.cover_url ? getCoverUrl({ cover_image_url: item.alt.cover_url }) : null,
        altYear: item.alt.year ?? null,
        altCountry: item.alt.country ?? null,
        altFormat: item.alt.format ?? null,
        altPrice: item.alt.price_rub ?? null,
      });
      return;
    }
    historyRef.current?.present({
      itemId: item.wishlist_item_id,
      recordId: item.record.id,
      title: item.record.title,
      artist: item.record.artist,
      coverUrl: getCoverUrl(item.record),
      currentPrice: item.lowest_price_rub,
      threshold: item.threshold_rub,
      thresholdPct: item.threshold_pct ?? null,
      isAcceptedAlt: item.accept_alt === true && !!item.alt,
      altTitle: item.alt?.title ?? null,
      rejectedAltCount: item.rejected_alt_count ?? 0,
      status: item.status,
      buyUrl: item.buy_url ?? null,
      buyListingId: item.buy_listing_id ?? null,
      discogsId: item.record.discogs_id ?? null,
      offersCount: item.offers_count ?? 0,
    });
  };

  const onEditThreshold = (d: PriceHistorySheetData) => {
    thresholdRef.current?.present({
      itemId: d.itemId,
      recordId: d.recordId,
      currentPrice: d.currentPrice,
      threshold: d.threshold,
      thresholdPct: d.thresholdPct ?? null,
      subscribed: true,
    });
  };

  const onOpenStore = async (d: PriceHistorySheetData) => {
    if (!d.buyUrl) {
      router.push(`/record/${d.recordId}` as any);
      return;
    }
    // Идём через POST /offers/{id}/click: он проставляет affiliate-subid и
    // кормит серию «Рыночный нюх». Прямой openURL терял и комиссию, и ачивки.
    let urlToOpen = d.buyUrl;
    if (d.buyListingId) {
      // Amplitude раньше про радар не знал вовсе: серверный клик тут был, а
      // продуктовое событие — нет, и канал выглядел мёртвым при живых
      // переходах. Шлём до сетевого запроса, как и в остальных трёх точках:
      // упавший бэкенд не должен съедать аналитику.
      analytics.offerClick({
        listing_id: d.buyListingId,
        source: 'radar_price_history',
        ...(d.discogsId ? { discogs_id: d.discogsId } : {}),
        // Number() обязателен: тип обещает number, но бэкенд отдаёт цену
        // строкой ("3990.0"). Строковое свойство в Amplitude не усредняется
        // и не суммируется — средний чек по радару считался бы мимо.
        ...(d.currentPrice != null && Number.isFinite(Number(d.currentPrice))
          ? { price_rub: Number(d.currentPrice) }
          : {}),
      });
      try {
        const { url } = await api.trackOfferClick(d.buyListingId, 'radar_price_history');
        urlToOpen = url;
      } catch {
        // backend недоступен — уходим по прямой ссылке, лишь бы юзер дошёл
      }
    }
    Linking.openURL(urlToOpen).catch(() => router.push(`/record/${d.recordId}` as any));
  };

  return (
    <View style={styles.root}>
      <StatusBar style="light" />
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
        <Defs>
          <RadialGradient id="bg" cx="50%" cy="32%" r="80%">
            <Stop offset="0" stopColor="#2A1466" />
            <Stop offset="0.5" stopColor="#170A3A" />
            <Stop offset="1" stopColor="#0A0218" />
          </RadialGradient>
        </Defs>
        <Path d="M0 0 H2000 V2000 H0 Z" fill="url(#bg)" />
      </Svg>

      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()} hitSlop={8}>
          <Icon name="chevron-back" size={22} color="#fff" />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.hTitle}>Радар</Text>
          <Text style={styles.hSub}>
            {isEmpty ? 'Пока пусто' : `Следим за ${items.length} ${plural(items.length)}`}
          </Text>
        </View>
        {!isEmpty ? (
          <View style={styles.slots}>
            <Text style={styles.slotsTxt}>{items.length}/{limit}</Text>
          </View>
        ) : null}
      </View>

      {reopenPending ? (
        <View style={styles.reopenBar}>
          <Text style={styles.reopenTxt}>
            {items.length >= limit
              ? 'Радар заполнен. Убери один релиз, чтобы вернуться и добавить новый.'
              : 'Место освободилось — можно вернуться и добавить релиз.'}
          </Text>
          {items.length < limit ? (
            <TouchableOpacity
              style={styles.reopenBtn}
              onPress={() => {
                Haptics.selectionAsync().catch(() => {});
                router.back();
              }}
              activeOpacity={0.9}
            >
              <Icon name="arrow-back" size={16} color="#fff" />
              <Text style={styles.reopenBtnTxt}>Вернуться и добавить</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : null}

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={[styles.stage, { width: STAGE, height: STAGE }]}>
          {[STAGE, STAGE * 0.78, STAGE * 0.56, STAGE * 0.34].map((d, i) => (
            <View key={i} style={[styles.ring, { width: d, height: d, borderRadius: d / 2, opacity: 0.1 + i * 0.045 }]} />
          ))}
          <View style={[styles.buyZone, { width: C * 1.0, height: C * 1.0, borderRadius: C * 0.5 }]} />

          <Animated.View style={[styles.sweep, { width: STAGE, height: STAGE }, sweepStyle]} pointerEvents="none">
            <Svg width={STAGE} height={STAGE}>
              <Defs>
                <SvgGradient id="sw" x1="0.5" y1="0.5" x2="0.92" y2="0.08">
                  <Stop offset="0" stopColor="#6B8AFF" stopOpacity="0.5" />
                  <Stop offset="1" stopColor="#6B8AFF" stopOpacity="0" />
                </SvgGradient>
              </Defs>
              <Path
                d={`M${C} ${C} L${C} 0 A${C} ${C} 0 0 1 ${C + Math.sin((52 * Math.PI) / 180) * C} ${C - Math.cos((52 * Math.PI) / 180) * C} Z`}
                fill="url(#sw)"
              />
            </Svg>
          </Animated.View>

          {placed.map((p) => (
            <RadarCover key={p.item.wishlist_item_id} placed={p} C={C} sweep={sweep} onPress={() => onCoverPress(p.item)} />
          ))}

          {/* halo + аватар (SVG-контур для чёткости) */}
          <Animated.View style={[styles.halo, haloStyle]} pointerEvents="none" />
          <Animated.View style={[styles.avatarWrap, avatarStyle]}>
            <Svg width={62} height={62} style={StyleSheet.absoluteFill}>
              <Circle cx={31} cy={31} r={29} fill="none" stroke="#5568F0" strokeWidth={3} />
            </Svg>
            {avatarSrc ? (
              <Image source={avatarSrc} style={styles.avatarImg} contentFit="cover" cachePolicy="disk" />
            ) : (
              <View style={[styles.avatarImg, styles.avatarFallback]}>
                <RadarIcon size={24} color="#fff" />
              </View>
            )}
          </Animated.View>
        </View>

        {isEmpty ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Поставь пластинку на радар</Text>
            <Text style={styles.emptyBody}>Задай желаемую цену — сообщим, когда пластинка появится в продаже.</Text>
            <TouchableOpacity style={styles.cta} onPress={() => router.replace('/(tabs)/collection')} activeOpacity={0.9}>
              <RadarIcon size={20} color="#fff" />
              <Text style={styles.ctaTxt}>Открыть вишлист</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </ScrollView>

      {/* Легенда — фиксированный подвал */}
      {!isEmpty ? (
        <View style={[styles.legend, { paddingBottom: insets.bottom + 14 }]}>
          {BAND_ORDER.map((s) => (
            <View key={s} style={[styles.legendChip, { borderColor: hexA(STATUS_COLOR[s], 0.5) }]}>
              <View style={[styles.legendDot, { backgroundColor: STATUS_COLOR[s] }]} />
              <Text style={[styles.legendTxt, { color: STATUS_COLOR[s] }]}>{STATUS_LABEL[s]}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <PriceHistorySheet
        ref={historyRef}
        onEditThreshold={onEditThreshold}
        onOpenStore={onOpenStore}
        onRemoved={() => load()}
        onAltChanged={() => load()}
      />
      <AltVersionSheet ref={altRef} onConfirm={() => load()} />
      <ThresholdSheet ref={thresholdRef} onSaved={() => load()} />
    </View>
  );
}

function plural(n: number): string {
  const m10 = n % 10, m100 = n % 100;
  if (m100 >= 11 && m100 <= 14) return 'пластинками';
  if (m10 === 1) return 'пластинкой';
  if (m10 >= 2 && m10 <= 4) return 'пластинками';
  return 'пластинками';
}

function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0218' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 22, paddingBottom: 10 },
  backBtn: { width: 40, height: 40, borderRadius: 9999, backgroundColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' },
  hTitle: { fontFamily: 'RubikMonoOne-Regular', fontSize: 26, color: '#fff', letterSpacing: -0.5 },
  hSub: { fontSize: 13, color: 'rgba(255,255,255,0.6)', marginTop: 3 },
  slots: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 9999, backgroundColor: 'rgba(91,106,245,0.18)', borderWidth: 1, borderColor: 'rgba(91,106,245,0.4)' },
  slotsTxt: { fontSize: 14, fontFamily: 'Inter_700Bold', color: '#B7C0FF', fontVariant: ['tabular-nums'] },
  reopenBar: { marginHorizontal: 16, marginBottom: 4, padding: 14, borderRadius: 16, backgroundColor: 'rgba(91,106,245,0.14)', borderWidth: 1, borderColor: 'rgba(91,106,245,0.35)', gap: 10 },
  reopenTxt: { fontSize: 13.5, lineHeight: 19, fontFamily: 'Inter_500Medium', color: '#D6DBFF' },
  reopenBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingVertical: 11, borderRadius: 9999, backgroundColor: Colors.royalBlue },
  reopenBtnTxt: { color: '#fff', fontFamily: 'Inter_600SemiBold', fontSize: 14.5 },
  scroll: { alignItems: 'center', paddingBottom: 20, flexGrow: 1, justifyContent: 'center' },
  stage: { marginTop: 20, alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute', borderWidth: 1, borderColor: '#4A5FD8' },
  buyZone: { position: 'absolute', borderWidth: 1.5, borderColor: 'rgba(48,164,108,0.5)', borderStyle: 'dashed', backgroundColor: 'rgba(48,164,108,0.08)' },
  sweep: { position: 'absolute' },
  halo: { position: 'absolute', width: 86, height: 86, borderRadius: 43, backgroundColor: '#6B7BE8' },
  avatarWrap: { position: 'absolute', width: 62, height: 62, borderRadius: 31, shadowColor: '#3B4BF5', shadowOpacity: 0.9, shadowRadius: 16, shadowOffset: { width: 0, height: 0 }, elevation: 12, backgroundColor: '#241057', alignItems: 'center', justifyContent: 'center' },
  avatarImg: { width: 54, height: 54, borderRadius: 27 },
  avatarFallback: { backgroundColor: '#3B4BF5', alignItems: 'center', justifyContent: 'center' },
  coverWrap: { position: 'absolute', alignItems: 'center', justifyContent: 'center', width: COVER, height: COVER },
  buyGlow: { position: 'absolute', width: COVER + 8, height: COVER + 8, borderRadius: (COVER + 8) / 2, top: -4, left: -4, shadowOpacity: 0.9, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 8, backgroundColor: 'rgba(48,164,108,0.22)' },
  coverRing: { width: COVER, height: COVER, borderRadius: COVER / 2, borderWidth: 2.5, overflow: 'hidden', shadowOffset: { width: 0, height: 2 }, elevation: 5 },
  cover: { width: '100%', height: '100%' },
  coverPh: { backgroundColor: '#33333f' },
  absentScrim: { ...StyleSheet.absoluteFill, backgroundColor: 'rgba(120,124,150,0.62)' },
  priceChip: { position: 'absolute', top: COVER + 5, minWidth: 62, paddingVertical: 3, paddingHorizontal: 9, borderRadius: 9999, borderWidth: 1, backgroundColor: 'rgba(6,2,18,0.9)', alignItems: 'center' },
  priceTxt: { fontSize: 11, fontFamily: 'Inter_700Bold', fontVariant: ['tabular-nums'] },
  empty: { alignItems: 'center', paddingHorizontal: 40, marginTop: 30 },
  emptyTitle: { ...Typography.h2, color: '#fff', textAlign: 'center' },
  emptyBody: { fontSize: 14, color: 'rgba(255,255,255,0.6)', textAlign: 'center', lineHeight: 20, marginTop: 8 },
  cta: { flexDirection: 'row', alignItems: 'center', gap: 9, paddingVertical: 15, paddingHorizontal: 26, backgroundColor: Colors.royalBlue, borderRadius: 9999, marginTop: 24, shadowColor: '#3B4BF5', shadowOpacity: 0.6, shadowRadius: 16, shadowOffset: { width: 0, height: 4 }, elevation: 8 },
  ctaTxt: { color: '#fff', fontFamily: 'Inter_600SemiBold', fontSize: 16 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, paddingTop: 14, paddingHorizontal: 20, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)' },
  legendChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 7, paddingHorizontal: 13, borderRadius: 9999, borderWidth: 1 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendTxt: { fontSize: 12 },
});
