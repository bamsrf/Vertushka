/**
 * Радар — экран отслеживания цены (макет 1b/1c).
 *
 * Тёмный MarketPalette-мир. Subscribed-пластинки как кружки-обложки. Слои по статусу:
 * подходит — ближе к центру (зона покупки), в продаже — следующее кольцо, альтернатива
 * дальше, отсутствует — на внешнем кольце (не мешает). Вращающийся sweep, аватар юзера
 * в центре с softPulse. Тап по кружку → шторка истории; peach → alt-подтверждение.
 */
import { useCallback, useRef, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { Image } from 'expo-image';
import { useRouter, useFocusEffect } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, {
  Path,
  Defs,
  LinearGradient as SvgGradient,
  RadialGradient,
  Stop,
  Circle,
} from 'react-native-svg';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  withSequence,
  Easing,
} from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Colors, Typography } from '../constants/theme';
import { Icon } from '@/components/ui';
import { RadarIcon } from '../components/RadarIcon';
import { PriceHistorySheet, type PriceHistorySheetRef, type PriceHistorySheetData } from '../components/wishlist/PriceHistorySheet';
import { AltVersionSheet, type AltVersionSheetRef } from '../components/wishlist/AltVersionSheet';
import { ThresholdSheet, type ThresholdSheetRef } from '../components/wishlist/ThresholdSheet';
import { api, getCoverUrl, resolveMediaUrl } from '../lib/api';
import { useAuthStore } from '../lib/store';
import { RadarItem, RadarResponse, RadarStatus } from '../lib/types';

const STAGE = 320;
const MAX_R = 150;

const STATUS_COLOR: Record<RadarStatus, string> = {
  match: '#30A46C',
  available: '#5B6AF5',
  alt: '#F4A06A',
  absent: '#9A9EBF',
};

// Радиус-полоса на статус (доля 0..1 от MAX_R) — гарантирует слои.
const STATUS_BAND: Record<RadarStatus, [number, number]> = {
  match: [0.14, 0.32],
  available: [0.4, 0.58],
  alt: [0.64, 0.8],
  absent: [0.86, 0.96],
};

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');

// Стабильный угол из record.id — чтобы позиция не прыгала между рефрешами.
function angleOf(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360;
  return h;
}

function coverPos(item: RadarItem) {
  const [lo, hi] = STATUS_BAND[item.status];
  const t = Math.min(1, Math.max(0, item.radius));
  const frac = lo + t * (hi - lo);
  const r = frac * MAX_R;
  const a = (angleOf(item.record.id) * Math.PI) / 180;
  return { x: Math.cos(a) * r, y: Math.sin(a) * r };
}

export default function RadarScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const user = useAuthStore((s) => s.user);
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const historyRef = useRef<PriceHistorySheetRef>(null);
  const altRef = useRef<AltVersionSheetRef>(null);
  const thresholdRef = useRef<ThresholdSheetRef>(null);

  const sweep = useSharedValue(0);
  const pulse = useSharedValue(0);

  const load = useCallback(() => {
    api
      .getRadar()
      .then((res) => setData(res))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      sweep.value = 0;
      sweep.value = withRepeat(withTiming(360, { duration: 4000, easing: Easing.linear }), -1, false);
      pulse.value = withRepeat(withSequence(withTiming(1, { duration: 1400 }), withTiming(0, { duration: 1400 })), -1, false);
    }, [load]),
  );

  const sweepStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${sweep.value}deg` }] }));
  const pulseStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + pulse.value * 0.16 }], opacity: 0.7 - pulse.value * 0.5 }));
  const avatarStyle = useAnimatedStyle(() => ({ transform: [{ scale: 1 + pulse.value * 0.04 }] }));

  const items = data?.items ?? [];
  const isEmpty = !loading && items.length === 0;
  const avatarSrc = user?.avatar_url ? resolveMediaUrl(user.avatar_url) : undefined;

  const onCoverPress = (item: RadarItem) => {
    Haptics.selectionAsync().catch(() => {});
    if (item.status === 'alt' && item.alt) {
      altRef.current?.present({
        itemId: item.wishlist_item_id,
        altTitle: item.alt.title,
        altCoverUrl: item.alt.cover_url ? getCoverUrl({ cover_image_url: item.alt.cover_url }) : null,
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
      status: item.status,
    });
  };

  const onEditThreshold = (d: PriceHistorySheetData) => {
    thresholdRef.current?.present({
      itemId: d.itemId,
      recordId: d.recordId,
      currentPrice: d.currentPrice,
      threshold: d.threshold,
    });
  };

  const onAltConfirm = () => {
    load();
  };

  return (
    <View style={styles.root}>
      <StatusBar style="light" />
      {/* радиальный фон */}
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%">
        <Defs>
          <RadialGradient id="bg" cx="50%" cy="34%" r="75%">
            <Stop offset="0" stopColor="#2A1466" />
            <Stop offset="0.5" stopColor="#170A3A" />
            <Stop offset="1" stopColor="#0A0218" />
          </RadialGradient>
        </Defs>
        <Path d={`M0 0 H2000 V2000 H0 Z`} fill="url(#bg)" />
      </Svg>

      {/* header */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()} hitSlop={8}>
          <Icon name="chevron-back" size={22} color="#fff" />
        </TouchableOpacity>
        <View>
          <Text style={styles.hTitle}>Радар</Text>
          <Text style={styles.hSub}>
            {isEmpty ? 'Пока пусто' : `Следим за ${items.length} ${plural(items.length)}`}
          </Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.stage}>
          {/* rings */}
          {[STAGE, STAGE * 0.77, STAGE * 0.53, STAGE * 0.3].map((d, i) => (
            <View
              key={i}
              style={[styles.ring, { width: d, height: d, borderRadius: d / 2, opacity: 0.1 + i * 0.05 }]}
            />
          ))}
          {/* buy zone */}
          <View style={styles.buyZone} />

          {/* sweep */}
          <Animated.View style={[styles.sweep, sweepStyle]} pointerEvents="none">
            <Svg width={STAGE} height={STAGE}>
              <Defs>
                <SvgGradient id="sw" x1="0.5" y1="0.5" x2="0.92" y2="0.08">
                  <Stop offset="0" stopColor="#6B8AFF" stopOpacity="0.5" />
                  <Stop offset="1" stopColor="#6B8AFF" stopOpacity="0" />
                </SvgGradient>
              </Defs>
              <Path
                d={`M${STAGE / 2} ${STAGE / 2} L${STAGE / 2} 0 A${STAGE / 2} ${STAGE / 2} 0 0 1 ${STAGE / 2 + Math.sin((55 * Math.PI) / 180) * (STAGE / 2)} ${STAGE / 2 - Math.cos((55 * Math.PI) / 180) * (STAGE / 2)} Z`}
                fill="url(#sw)"
              />
            </Svg>
          </Animated.View>

          {/* covers */}
          {items.map((item) => {
            const { x, y } = coverPos(item);
            const color = STATUS_COLOR[item.status];
            const price = item.status === 'alt' ? item.alt?.price_rub : item.lowest_price_rub;
            const cover = getCoverUrl(item.record);
            const absent = item.status === 'absent';
            return (
              <TouchableOpacity
                key={item.wishlist_item_id}
                activeOpacity={0.85}
                onPress={() => onCoverPress(item)}
                style={[styles.coverWrap, { left: STAGE / 2 + x - 27, top: STAGE / 2 + y - 27 }]}
              >
                {item.status === 'match' ? <View style={[styles.buyGlow, { shadowColor: color }]} /> : null}
                <View style={[styles.coverRing, { borderColor: color, shadowColor: color, opacity: absent ? 0.55 : 1 }]}>
                  {cover ? (
                    <Image source={cover} style={styles.cover} contentFit="cover" cachePolicy="disk" transition={150} />
                  ) : (
                    <View style={[styles.cover, styles.coverPh]} />
                  )}
                </View>
                {price != null ? (
                  <View style={[styles.priceChip, { borderColor: color }]}>
                    <Text style={[styles.priceTxt, { color }]}>{fmt(price)} ₽</Text>
                  </View>
                ) : null}
              </TouchableOpacity>
            );
          })}

          {/* center avatar + soft pulse */}
          <Animated.View style={[styles.avatarPulse, pulseStyle]} pointerEvents="none" />
          <Animated.View style={[styles.avatarWrap, avatarStyle]}>
            {avatarSrc ? (
              <Image source={avatarSrc} style={styles.avatarImg} contentFit="cover" cachePolicy="disk" />
            ) : (
              <View style={[styles.avatarImg, styles.avatarFallback]}>
                <RadarIcon size={26} color="#fff" />
              </View>
            )}
          </Animated.View>
          {!isEmpty ? <Text style={styles.scanTxt}>сканирую цены…</Text> : null}
        </View>

        {isEmpty ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Поставь пластинку на радар</Text>
            <Text style={styles.emptyBody}>
              Задай желаемую цену — сообщим, когда пластинка появится в продаже.
            </Text>
            <TouchableOpacity style={styles.cta} onPress={() => router.replace('/(tabs)/collection')}>
              <RadarIcon size={20} color="#fff" />
              <Text style={styles.ctaTxt}>Открыть вишлист</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.legend}>
            {(['match', 'available', 'alt', 'absent'] as RadarStatus[]).map((s) => (
              <View key={s} style={[styles.legendChip, { borderColor: hexA(STATUS_COLOR[s], 0.55) }]}>
                <View style={[styles.legendDot, { backgroundColor: STATUS_COLOR[s] }]} />
                <Text style={[styles.legendTxt, { color: STATUS_COLOR[s] }]}>{STATUS_LABEL[s]}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      <PriceHistorySheet
        ref={historyRef}
        onEditThreshold={onEditThreshold}
        onOpenStore={(d) => router.push(`/record/${d.recordId}` as any)}
      />
      <AltVersionSheet ref={altRef} onConfirm={onAltConfirm} />
      <ThresholdSheet ref={thresholdRef} />
    </View>
  );
}

const STATUS_LABEL: Record<RadarStatus, string> = {
  match: 'подходит',
  available: 'в продаже',
  alt: 'альтернатива',
  absent: 'отсутствует',
};

function plural(n: number): string {
  const m10 = n % 10, m100 = n % 100;
  if (m100 >= 11 && m100 <= 14) return 'пластинок';
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
  scroll: { alignItems: 'center', paddingBottom: 40 },
  stage: { width: STAGE, height: STAGE, marginTop: 44, alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute', borderWidth: 1, borderColor: '#4A5FD8' },
  buyZone: { position: 'absolute', width: 108, height: 108, borderRadius: 54, borderWidth: 1.5, borderColor: 'rgba(48,164,108,0.5)', borderStyle: 'dashed', backgroundColor: 'rgba(48,164,108,0.09)' },
  sweep: { position: 'absolute', width: STAGE, height: STAGE },
  avatarPulse: { position: 'absolute', width: 96, height: 96, borderRadius: 48, backgroundColor: '#6B7BE8' },
  avatarWrap: { position: 'absolute', width: 58, height: 58, borderRadius: 29, borderWidth: 3, borderColor: '#5568F0', shadowColor: '#3B4BF5', shadowOpacity: 0.9, shadowRadius: 14, shadowOffset: { width: 0, height: 0 }, elevation: 10, backgroundColor: '#241057' },
  avatarImg: { width: '100%', height: '100%', borderRadius: 29 },
  avatarFallback: { backgroundColor: '#3B4BF5', alignItems: 'center', justifyContent: 'center' },
  scanTxt: { position: 'absolute', top: STAGE / 2 + 44, fontSize: 11, color: 'rgba(255,255,255,0.42)' },
  coverWrap: { position: 'absolute', alignItems: 'center', justifyContent: 'center' },
  buyGlow: { position: 'absolute', width: 62, height: 62, borderRadius: 31, top: -4, left: -4, shadowOpacity: 0.9, shadowRadius: 12, shadowOffset: { width: 0, height: 0 }, elevation: 8, backgroundColor: 'rgba(48,164,108,0.25)' },
  coverRing: { width: 54, height: 54, borderRadius: 27, borderWidth: 2.5, overflow: 'hidden', shadowOpacity: 0.55, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 5 },
  cover: { width: '100%', height: '100%' },
  coverPh: { backgroundColor: '#33333f' },
  priceChip: { position: 'absolute', top: 58, paddingVertical: 2.5, paddingHorizontal: 8, borderRadius: 9999, borderWidth: 1, backgroundColor: 'rgba(6,2,18,0.85)' },
  priceTxt: { fontSize: 10, fontFamily: 'Inter_700Bold', fontVariant: ['tabular-nums'] },
  empty: { alignItems: 'center', paddingHorizontal: 40, marginTop: 30 },
  emptyTitle: { ...Typography.h2, color: '#fff', textAlign: 'center' },
  emptyBody: { fontSize: 14, color: 'rgba(255,255,255,0.6)', textAlign: 'center', lineHeight: 20, marginTop: 8 },
  cta: { flexDirection: 'row', alignItems: 'center', gap: 9, paddingVertical: 15, paddingHorizontal: 26, backgroundColor: Colors.royalBlue, borderRadius: 9999, marginTop: 24, shadowColor: '#3B4BF5', shadowOpacity: 0.6, shadowRadius: 16, shadowOffset: { width: 0, height: 4 }, elevation: 8 },
  ctaTxt: { color: '#fff', fontFamily: 'Inter_600SemiBold', fontSize: 16 },
  legend: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginTop: 34, paddingHorizontal: 24 },
  legendChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 9999, borderWidth: 1 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendTxt: { fontSize: 11 },
});
