/**
 * AutoRail — горизонтальный авто-скроллящийся рейл с обложками.
 * Используется на публичном профиле и на экране Поиска.
 */
import { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Animated,
  Easing,
  Platform,
} from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { resolveMediaUrl } from '../lib/api';
import { PublicProfileRecord } from '../lib/types';

const PALETTE = {
  ink: '#1B1D26',
  mute: '#9096A6',
  lavender: '#C9B8FF',
  periwinkle: '#9AA8FF',
  cobalt: '#3A4BE0',
};

const HORIZONTAL_PADDING = 20;
const RAIL_COVER = 108;

interface AutoRailProps {
  title: string;
  subtitle: string;
  items: PublicProfileRecord[];
  titleColor: string;
  showYear?: boolean;
  onPick?: (record: PublicProfileRecord) => void;
}

export function AutoRail({
  title,
  subtitle,
  items,
  showYear,
  onPick,
  titleColor,
}: AutoRailProps) {
  const scrollRef = useRef<ScrollView>(null);
  const scrollX = useRef(new Animated.Value(0)).current;
  const [contentW, setContentW] = useState(0);
  const halfWidth = contentW / 2;

  useEffect(() => {
    if (!halfWidth || !scrollRef.current) return;
    let raf: number | null = null;
    const id = scrollX.addListener(({ value }) => {
      if (value >= halfWidth) {
        scrollRef.current?.scrollTo({ x: value - halfWidth, animated: false });
      }
    });
    const anim = Animated.loop(
      Animated.timing(scrollX, {
        toValue: halfWidth,
        duration: 30000,
        easing: Easing.linear,
        useNativeDriver: false,
      })
    );
    anim.start();
    const tick = () => {
      // @ts-ignore
      const v = scrollX.__getValue?.() ?? 0;
      scrollRef.current?.scrollTo({ x: v, animated: false });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      anim.stop();
      scrollX.removeListener(id);
      if (raf != null) cancelAnimationFrame(raf);
    };
  }, [halfWidth, scrollX]);

  if (!items.length) return null;
  const doubled = [...items, ...items];

  return (
    <View>
      <View style={styles.railHead}>
        <Text style={[styles.railTitle, { color: titleColor }]}>{title.toUpperCase()}</Text>
        <Text style={styles.railSub}>{subtitle}</Text>
      </View>
      <ScrollView
        ref={scrollRef}
        horizontal
        showsHorizontalScrollIndicator={false}
        scrollEnabled
        contentContainerStyle={{ paddingHorizontal: HORIZONTAL_PADDING, gap: 12 }}
        onContentSizeChange={(w) => setContentW(w)}
      >
        {doubled.map((r, i) => (
          <TouchableOpacity
            key={`${r.id}-${i}`}
            activeOpacity={0.85}
            onPress={() => onPick?.(r)}
            style={{ width: RAIL_COVER }}
          >
            <View style={styles.railCover}>
              {r.cover_image_url ? (
                <Image
                  source={resolveMediaUrl(r.cover_image_url)}
                  style={{ width: RAIL_COVER, height: RAIL_COVER }}
                  cachePolicy="disk"
                />
              ) : (
                <LinearGradient
                  colors={[PALETTE.lavender, PALETTE.periwinkle]}
                  style={{ width: RAIL_COVER, height: RAIL_COVER }}
                />
              )}
            </View>
            <Text
              numberOfLines={1}
              style={[
                styles.railArtist,
                { color: titleColor === PALETTE.cobalt ? PALETTE.cobalt : PALETTE.mute },
              ]}
            >
              {r.artist}
            </Text>
            <Text numberOfLines={1} style={styles.railTitleSmall}>
              {r.title}
            </Text>
            {showYear && r.year ? (
              <Text style={styles.railYear}>
                {r.year}
                {r.format_type ? ` · ${r.format_type}` : ''}
                {r.discogs_want ? ` · ♥ ${r.discogs_want}` : ''}
              </Text>
            ) : null}
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  railHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    paddingHorizontal: HORIZONTAL_PADDING,
    marginBottom: 12,
  },
  railTitle: {
    fontSize: 10,
    letterSpacing: 1.2,
    fontWeight: '600',
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
  },
  railSub: { fontSize: 11, color: PALETTE.mute },
  railCover: {
    width: RAIL_COVER,
    height: RAIL_COVER,
    borderRadius: 13,
    overflow: 'hidden',
    backgroundColor: PALETTE.lavender,
    shadowColor: PALETTE.ink,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 14,
  },
  railArtist: {
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    fontSize: 9,
    letterSpacing: 0.6,
    marginTop: 8,
  },
  railTitleSmall: { fontSize: 11.5, fontWeight: '600', color: PALETTE.ink, marginTop: 2 },
  railYear: { fontSize: 11, color: PALETTE.periwinkle, marginTop: 2 },
});
