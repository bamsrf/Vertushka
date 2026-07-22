/**
 * WishlistDigestSheet — bottom-sheet «N пластинок из вишлиста снова в продаже».
 *
 * Открывается тапом по свёрнутой дайджест-строке в ленте «Ты». Показывает все
 * пластинки «полкой корешков»:
 *  - тап по обложке → проваливаешься в релиз (/record/[id]) со всеми листингами;
 *  - тянешь корешок вправо → открывается самый дешёвый магазин (с affiliate-
 *    трекингом через POST /offers/{id}/click), как в OffersBlock.
 */
import React, { useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Linking,
  TouchableOpacity,
} from 'react-native';
import { Image } from 'expo-image';
import * as Haptics from 'expo-haptics';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Gesture, GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { Colors, Spacing, BorderRadius, Typography } from '@/constants/theme';
import { Icon } from '@/components/ui';
import { XV2 } from '@/components/icons/v2';
import { api, getCoverUrl } from '@/lib/api';
import { toast } from '@/lib/toast';

/** Одна пластинка дайджеста — собирается из data.stores[] wishlist_in_stock. */
export interface DigestRecord {
  record_id: string;
  title: string;
  artist?: string | null;
  cover_url?: string | null;
  min_price_rub?: number | null;
  store_count?: number;
  /** Самый дешёвый магазин — цель «потянуть → в магазин». */
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

/** Открыть магазин с affiliate-трекингом; на ошибке — preview-URL из store.url. */
async function openStore(store: DigestRecord['store']): Promise<void> {
  if (!store?.url && !store?.listing_id) {
    toast.error('Ссылка на магазин недоступна');
    return;
  }
  let urlToOpen = store?.url ?? '';
  if (store?.listing_id) {
    try {
      const { url } = await api.trackOfferClick(store.listing_id);
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

const PULL_WIDTH = 96; // ширина баннера «в магазин» при полном раскрытии
const OPEN_RATIO = 0.5;
const VELOCITY_OPEN = 650;
const ACTIVE_OFFSET = 12;
const FAIL_OFFSET_Y = 14;

/** Строка-«корешок»: тянешь вправо → магазин; тап по обложке → релиз. */
const SpineRow: React.FC<{
  record: DigestRecord;
  onOpenRecord: (id: string) => void;
}> = ({ record, onOpenRecord }) => {
  const dragX = useSharedValue(0);
  const startX = useSharedValue(0);
  const cover = getCoverUrl({ cover_url: record.cover_url ?? undefined });

  const triggerStore = useCallback(() => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    openStore(record.store);
  }, [record.store]);

  const pan = Gesture.Pan()
    .activeOffsetX([-ACTIVE_OFFSET, ACTIVE_OFFSET])
    .failOffsetY([-FAIL_OFFSET_Y, FAIL_OFFSET_Y])
    .onStart(() => {
      startX.value = dragX.value;
    })
    .onUpdate((e) => {
      const next = startX.value + e.translationX;
      if (next < 0) {
        dragX.value = next * 0.12; // левый overscroll — упруго
      } else if (next > PULL_WIDTH) {
        dragX.value = PULL_WIDTH + (next - PULL_WIDTH) * 0.4;
      } else {
        dragX.value = next;
      }
    })
    .onEnd((e) => {
      const shouldOpen = dragX.value > PULL_WIDTH * OPEN_RATIO || e.velocityX > VELOCITY_OPEN;
      dragX.value = withTiming(0, { duration: 200, easing: Easing.out(Easing.cubic) });
      if (shouldOpen) runOnJS(triggerStore)();
    });

  const contentStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: dragX.value }],
  }));
  const bannerStyle = useAnimatedStyle(() => ({
    width: Math.max(0, dragX.value),
  }));

  return (
    <View style={styles.spineWrap}>
      <Animated.View style={[styles.banner, bannerStyle]} pointerEvents="box-none">
        <Pressable onPress={triggerStore} style={styles.bannerPress} accessibilityLabel="В магазин">
          <Icon name="arrow-up-right" size={20} color={Colors.background} />
        </Pressable>
      </Animated.View>

      <GestureDetector gesture={pan}>
        <Animated.View style={[styles.spine, contentStyle]}>
          <Pressable onPress={() => onOpenRecord(record.record_id)} hitSlop={4}>
            {cover ? (
              <Image source={cover} style={styles.cover} cachePolicy="disk" contentFit="cover" />
            ) : (
              <View style={[styles.cover, styles.coverPlaceholder]}>
                <Icon name="disc" size={20} color={Colors.textMuted} />
              </View>
            )}
          </Pressable>

          <Pressable style={styles.info} onPress={() => onOpenRecord(record.record_id)}>
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
                ? ` · ${record.store_count} магазинов`
                : ''}
            </Text>
          </Pressable>

          <TouchableOpacity
            style={styles.storeBtn}
            onPress={triggerStore}
            hitSlop={8}
            accessibilityLabel="Открыть магазин"
          >
            <Icon name="arrow-up-right" size={16} color={Colors.background} />
          </TouchableOpacity>
        </Animated.View>
      </GestureDetector>
    </View>
  );
};

export const WishlistDigestSheet: React.FC<Props> = ({
  visible,
  onClose,
  records,
  onOpenRecord,
}) => {
  const insets = useSafeAreaInsets();

  const handleOpenRecord = useCallback(
    (id: string) => {
      onClose();
      onOpenRecord(id);
    },
    [onClose, onOpenRecord],
  );

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={styles.flex}>
        <Pressable style={styles.backdrop} onPress={onClose} />
        <View style={[styles.sheet, { paddingBottom: insets.bottom + Spacing.md }]}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <Text style={styles.sheetTitle}>
              {records.length} {pluralRecords(records.length)} снова в продаже
            </Text>
            <TouchableOpacity onPress={onClose} hitSlop={12} accessibilityLabel="Закрыть">
              <XV2 size={22} color={Colors.text} />
            </TouchableOpacity>
          </View>
          <Text style={styles.hint}>Потяни корешок вправо → магазин · тап по обложке → релиз</Text>

          <FlatList
            data={records}
            keyExtractor={(r) => r.record_id}
            renderItem={({ item }) => (
              <SpineRow record={item} onOpenRecord={handleOpenRecord} />
            )}
            style={styles.list}
            contentContainerStyle={styles.listInner}
            showsVerticalScrollIndicator={false}
          />
        </View>
      </GestureHandlerRootView>
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
  banner: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: Colors.success,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    borderRadius: BorderRadius.md,
  },
  bannerPress: {
    width: PULL_WIDTH,
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
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
    color: Colors.success,
  },
  storeBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: Colors.success,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default WishlistDigestSheet;
