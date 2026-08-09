/**
 * WishlistDigestSheet — bottom-sheet «N пластинок из вишлиста снова в продаже».
 *
 * Открывается тапом по свёрнутой дайджест-строке в ленте «Ты». Показывает все
 * пластинки списком:
 *  - тап по строке → проваливаешься в релиз (/record/[id]) со всеми листингами;
 *  - тап по стрелке → поп-ап «Где купить»: все магазины с ценами, покупка
 *    уходит по affiliate-ссылке (POST /offers/{id}/click), как в OffersBlock.
 *
 * Свайпа тут нет намеренно: жест конфликтовал с вертикальным скроллом списка и
 * вслепую вёл в «какой-то» магазин при нескольких офферах.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Modal,
  View,
  Text,
  StyleSheet,
  FlatList,
  ScrollView,
  ActivityIndicator,
  Pressable,
  Linking,
  TouchableOpacity,
  type LayoutChangeEvent,
} from 'react-native';
import { Image } from 'expo-image';
import * as Haptics from 'expo-haptics';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Colors, MarketPalette, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { XV2 } from '@/components/icons/v2';
import StoreLogo from '@/components/market/StoreLogo';
import { api, getCoverUrl } from '@/lib/api';
import { toast } from '@/lib/toast';
import type { Offer } from '@/lib/types';

/** Акцент Маркета — стрелка «в магазин» и цена живут в цвете маркета. */
const ACCENT = MarketPalette.cobalt;

/** Одна пластинка дайджеста — собирается из data.stores[] wishlist_in_stock. */
export interface DigestRecord {
  record_id: string;
  title: string;
  artist?: string | null;
  cover_url?: string | null;
  min_price_rub?: number | null;
  store_count?: number;
  /** Самый дешёвый магазин — fallback, если полный список офферов не пришёл. */
  store?: {
    listing_id?: string | null;
    url?: string | null;
    name?: string | null;
    price_rub?: number | null;
  } | null;
}

interface Props {
  visible: boolean;
  onClose: () => void;
  records: DigestRecord[];
  onOpenRecord: (recordId: string) => void;
}

function formatPrice(p: number | null | undefined): string {
  if (typeof p !== 'number') return '';
  return `${Math.round(p).toLocaleString('ru-RU')} ₽`;
}

function pluralRecords(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'пластинок';
  if (mod10 === 1) return 'пластинка';
  if (mod10 >= 2 && mod10 <= 4) return 'пластинки';
  return 'пластинок';
}

function pluralStores(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return 'магазинов';
  if (mod10 === 1) return 'магазин';
  if (mod10 >= 2 && mod10 <= 4) return 'магазина';
  return 'магазинов';
}

/** Открыть магазин с affiliate-трекингом; на ошибке — preview-URL листинга. */
async function openStoreUrl(listingId?: string | null, previewUrl?: string | null): Promise<void> {
  if (!listingId && !previewUrl) {
    toast.error('Ссылка на магазин недоступна');
    return;
  }
  let urlToOpen = previewUrl ?? '';
  if (listingId) {
    try {
      const { url } = await api.trackOfferClick(listingId);
      urlToOpen = url;
    } catch {
      // network/server — fallback на preview-URL, переход не блокируем
    }
  }
  if (!urlToOpen) return;
  try {
    await Linking.openURL(urlToOpen);
  } catch {
    // невалидный URL — аналитику уже отправили
  }
}

/** Строка дайджеста: тап → релиз; стрелка → поп-ап «Где купить». */
const SpineRow: React.FC<{
  record: DigestRecord;
  onOpenRecord: (id: string) => void;
  onOpenOffers: (record: DigestRecord) => void;
}> = ({ record, onOpenRecord, onOpenOffers }) => {
  const cover = getCoverUrl({ cover_url: record.cover_url ?? undefined });

  return (
    <View style={styles.spineWrap}>
      <Pressable
        style={styles.spine}
        onPress={() => onOpenRecord(record.record_id)}
        accessibilityLabel={`${record.title} — открыть релиз`}
      >
        {cover ? (
          <Image source={cover} style={styles.cover} cachePolicy="disk" contentFit="cover" />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]}>
            <Icon name="disc" size={20} color={Colors.textMuted} />
          </View>
        )}

        <View style={styles.info}>
          <Text style={styles.title} numberOfLines={1}>
            {record.title}
          </Text>
          {record.artist ? (
            <Text style={styles.artist} numberOfLines={1}>
              {record.artist}
            </Text>
          ) : null}
          <Text style={styles.price}>
            {record.min_price_rub != null ? `от ${formatPrice(record.min_price_rub)}` : 'в наличии'}
            {record.store_count && record.store_count > 1
              ? ` · ${record.store_count} ${pluralStores(record.store_count)}`
              : ''}
          </Text>
        </View>

        <TouchableOpacity
          style={styles.storeBtn}
          onPress={() => onOpenOffers(record)}
          hitSlop={10}
          accessibilityLabel="Где купить"
        >
          <Icon name="arrow-up-right" size={16} color={Colors.background} />
        </TouchableOpacity>
      </Pressable>
    </View>
  );
};

/** Поп-ап «Где купить» — слой поверх шторки, без вложенного Modal. */
const OffersPopup: React.FC<{
  record: DigestRecord;
  onClose: () => void;
  bottomInset: number;
}> = ({ record, onClose, bottomInset }) => {
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [buyingId, setBuyingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setOffers(null);
    setFailed(false);
    (async () => {
      try {
        const full = await api.getOfferDetailsFullByRecordId(record.record_id);
        if (cancelled) return;
        const list = [...(full?.offers ?? [])].sort(
          (a, b) => Number(a.price_rub) - Number(b.price_rub),
        );
        setOffers(list);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [record.record_id]);

  const handleBuy = useCallback(async (listingId: string, url?: string | null) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    setBuyingId(listingId);
    await openStoreUrl(listingId, url);
    setBuyingId(null);
  }, []);

  // Бэк упал или офферов нет — уводим в единственный известный магазин.
  const fallbackStore = record.store;
  const showFallback = failed || (offers != null && offers.length === 0);

  return (
    <View style={styles.popupLayer}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Закрыть" />
      <View style={[styles.popup, { paddingBottom: bottomInset + Spacing.md }]}>
        <View style={styles.handle} />
        <View style={styles.header}>
          <View style={styles.popupTitleBox}>
            <Text style={styles.sheetTitle} numberOfLines={1}>
              Где купить
            </Text>
            <Text style={styles.popupSubtitle} numberOfLines={1}>
              {record.artist ? `${record.artist} · ` : ''}
              {record.title}
            </Text>
          </View>
          <TouchableOpacity onPress={onClose} hitSlop={12} accessibilityLabel="Закрыть">
            <XV2 size={22} color={Colors.text} />
          </TouchableOpacity>
        </View>

        {offers == null && !failed ? (
          <View style={styles.popupLoading}>
            <ActivityIndicator color={ACCENT} />
          </View>
        ) : showFallback ? (
          <View style={styles.popupLoading}>
            {fallbackStore?.listing_id || fallbackStore?.url ? (
              <TouchableOpacity
                style={styles.fallbackBtn}
                onPress={() => handleBuy(fallbackStore.listing_id ?? '', fallbackStore.url)}
              >
                <Text style={styles.fallbackBtnText}>
                  {fallbackStore.name ?? 'В магазин'}
                  {fallbackStore.price_rub != null
                    ? ` · ${formatPrice(fallbackStore.price_rub)}`
                    : ''}
                </Text>
              </TouchableOpacity>
            ) : (
              <Text style={styles.emptyText}>Предложения пропали из наличия</Text>
            )}
          </View>
        ) : (
          <ScrollView
            style={styles.popupList}
            contentContainerStyle={styles.listInner}
            showsVerticalScrollIndicator={false}
          >
            {offers!.map((o) => (
              <TouchableOpacity
                key={o.listing_id}
                style={styles.offerRow}
                onPress={() => handleBuy(o.listing_id, o.url)}
                activeOpacity={0.8}
              >
                <StoreLogo slug={o.store.slug} size={36} fallbackName={o.store.name} />
                <View style={styles.info}>
                  <Text style={styles.title} numberOfLines={1}>
                    {o.store.name}
                  </Text>
                  <Text style={styles.artist} numberOfLines={1}>
                    {[
                      o.status === 'preorder' ? 'предзаказ' : 'в наличии',
                      o.condition,
                      o.vinyl_color,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </Text>
                </View>
                {buyingId === o.listing_id ? (
                  <ActivityIndicator color={ACCENT} />
                ) : (
                  <Text style={styles.offerPrice}>{formatPrice(Number(o.price_rub))}</Text>
                )}
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}
      </View>
    </View>
  );
};

const IN_DURATION = 240;
const OUT_DURATION = 180;
const SHEET_TRAVEL_FALLBACK = 420; // до первого onLayout

export const WishlistDigestSheet: React.FC<Props> = ({
  visible,
  onClose,
  records,
  onOpenRecord,
}) => {
  const insets = useSafeAreaInsets();

  // Своя анимация вместо animationType="slide": затемнение должно проявляться
  // фейдом на всём экране, а не выезжать снизу вместе со шторкой.
  const [mounted, setMounted] = useState(visible);
  const [offersFor, setOffersFor] = useState<DigestRecord | null>(null);
  const progress = useSharedValue(0);
  const sheetHeight = useSharedValue(SHEET_TRAVEL_FALLBACK);
  const listRef = useRef<FlatList<DigestRecord>>(null);

  useEffect(() => {
    if (visible) {
      setMounted(true);
      progress.value = withTiming(1, { duration: IN_DURATION, easing: Easing.out(Easing.cubic) });
    } else {
      setOffersFor(null);
      progress.value = withTiming(
        0,
        { duration: OUT_DURATION, easing: Easing.in(Easing.cubic) },
        (finished) => {
          if (finished) runOnJS(setMounted)(false);
        },
      );
    }
  }, [visible, progress]);

  const backdropStyle = useAnimatedStyle(() => ({ opacity: progress.value }));
  const sheetStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: (1 - progress.value) * sheetHeight.value }],
  }));

  const onSheetLayout = useCallback(
    (e: LayoutChangeEvent) => {
      const h = e.nativeEvent.layout.height;
      if (h > 0) sheetHeight.value = h;
    },
    [sheetHeight],
  );

  const handleOpenRecord = useCallback(
    (id: string) => {
      onClose();
      onOpenRecord(id);
    },
    [onClose, onOpenRecord],
  );

  const handleOpenOffers = useCallback((record: DigestRecord) => {
    Haptics.selectionAsync().catch(() => {});
    setOffersFor(record);
  }, []);

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={offersFor ? () => setOffersFor(null) : onClose}
      statusBarTranslucent
    >
      <View style={styles.flex}>
        <Animated.View style={[styles.backdrop, backdropStyle]}>
          <Pressable style={styles.flex} onPress={onClose} accessibilityLabel="Закрыть" />
        </Animated.View>
        <Animated.View
          onLayout={onSheetLayout}
          style={[styles.sheet, sheetStyle, { paddingBottom: insets.bottom + Spacing.md }]}
        >
          <View style={styles.handle} />
          <View style={styles.header}>
            <Text style={styles.sheetTitle}>
              {records.length} {pluralRecords(records.length)} снова в продаже
            </Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} accessibilityLabel="Закрыть">
              <XV2 size={22} color={Colors.text} />
            </TouchableOpacity>
          </View>
          <Text style={styles.hint}>Тап по строке → релиз · тап по стрелке → где купить</Text>

          <FlatList
            ref={listRef}
            data={records}
            keyExtractor={(r) => r.record_id}
            renderItem={({ item }) => (
              <SpineRow
                record={item}
                onOpenRecord={handleOpenRecord}
                onOpenOffers={handleOpenOffers}
              />
            )}
            style={styles.list}
            contentContainerStyle={styles.listInner}
            showsVerticalScrollIndicator={false}
          />
        </Animated.View>

        {offersFor ? (
          <OffersPopup
            record={offersFor}
            onClose={() => setOffersFor(null)}
            bottomInset={insets.bottom}
          />
        ) : null}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  flex: { flex: 1 },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '78%',
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    paddingTop: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  popupLayer: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end',
  },
  popup: {
    maxHeight: '70%',
    backgroundColor: Colors.background,
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    paddingTop: Spacing.sm,
    paddingHorizontal: Spacing.md,
  },
  popupTitleBox: { flex: 1 },
  popupSubtitle: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 1,
  },
  popupList: { flexGrow: 0, marginTop: Spacing.sm },
  popupLoading: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: {
    ...Typography.bodySmall,
    color: Colors.textMuted,
  },
  fallbackBtn: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: BorderRadius.md,
    backgroundColor: ACCENT,
  },
  fallbackBtnText: {
    ...Typography.bodySmall,
    color: Colors.background,
    fontWeight: '600',
  },
  offerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.xs + 2,
    paddingHorizontal: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  offerPrice: {
    ...Typography.bodySmall,
    color: ACCENT,
    fontWeight: '700',
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: Colors.border,
    marginBottom: Spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheetTitle: {
    ...Typography.h3,
    color: Colors.text,
    flex: 1,
  },
  hint: {
    ...Typography.caption,
    color: Colors.textMuted,
    marginTop: 2,
    marginBottom: Spacing.sm,
  },
  list: { flexGrow: 0 },
  listInner: {
    paddingBottom: Spacing.md,
    gap: Spacing.xs,
  },
  spineWrap: {
    position: 'relative',
    overflow: 'hidden',
    borderRadius: BorderRadius.md,
  },
  spine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingVertical: Spacing.xs + 2,
    paddingHorizontal: Spacing.sm,
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.md,
  },
  cover: {
    width: 48,
    height: 48,
    borderRadius: BorderRadius.sm,
  },
  coverPlaceholder: {
    backgroundColor: Colors.surfaceHover,
    alignItems: 'center',
    justifyContent: 'center',
  },
  info: {
    flex: 1,
    gap: 1,
  },
  title: {
    ...Typography.bodySmall,
    color: Colors.text,
    fontWeight: '600',
  },
  artist: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  price: {
    ...Typography.caption,
    color: ACCENT,
  },
  storeBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: ACCENT,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default WishlistDigestSheet;
