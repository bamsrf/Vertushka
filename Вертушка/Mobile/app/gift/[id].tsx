/**
 * Превью бронирования: обложка, метаданные, цена (для дарителя), кнопка действия
 */
import { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Dimensions,
} from 'react-native';
import { Image } from 'expo-image';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Icon } from '@/components/ui';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../../lib/api';
import { analytics } from '../../lib/analytics';
import { cleanArtistName } from '../../lib/format';
import { toast } from '../../lib/toast';
import { useGiftStore, useCollectionStore } from '../../lib/store';
import { GiftGivenItem, GiftReceivedItem } from '../../lib/types';
import { Colors, Typography, Spacing, BorderRadius, Shadows } from '../../constants/theme';

type Direction = 'given' | 'received';
type GiftStatus = 'pending' | 'booked' | 'completed' | 'cancelled';

const STATUS_LABEL: Record<GiftStatus, string> = {
  pending: 'Ждёт подтверждения',
  booked: 'Забронировано',
  completed: 'Доставлено',
  cancelled: 'Отменено',
};

const STATUS_COLOR: Record<GiftStatus, string> = {
  pending: Colors.warning,
  booked: Colors.royalBlue,
  completed: Colors.success,
  cancelled: Colors.textMuted,
};

const { width: SCREEN_W } = Dimensions.get('window');
const COVER_SIZE = SCREEN_W - Spacing.lg * 2;

function formatPrice(value: number | undefined, currency: string | undefined): string | null {
  if (!value) return null;
  const rounded = Math.round(value);
  const formatted = rounded.toLocaleString('ru-RU');
  if (currency === 'RUB') return `${formatted} ₽`;
  if (currency === 'USD') return `$${formatted}`;
  if (currency === 'EUR') return `€${formatted}`;
  return `${formatted} ${currency ?? ''}`.trim();
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
}

export default function GiftDetailScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ id: string; direction: string }>();
  const requestedDirection: Direction = params.direction === 'received' ? 'received' : 'given';

  const { given, received, isLoaded, loadAll, removeGiven, removeReceived } = useGiftStore();
  const { fetchCollectionItems, fetchWishlistItems } = useCollectionStore();
  const [isActing, setIsActing] = useState(false);

  // Локальный «снимок» gift'а: пока он null — рендерим из стора (быстрый путь на mount);
  // как только засняли — экран показывает снимок, не реагируя на последующие удаления
  // из стора (иначе после успешного действия до router.back() мелькает «не найден»).
  const [snapshot, setSnapshot] = useState<
    { direction: Direction; gift: GiftGivenItem | GiftReceivedItem } | null
  >(null);

  // Ищем бронь в обоих списках: направление из ссылки — только подсказка.
  // Если оно не совпало (например, пуш открыли не с той стороны), берём тот
  // список, где бронь реально есть, — иначе экран показывал «Подарок не найден».
  const givenMatch = given.find((g) => g.id === params.id) as GiftGivenItem | undefined;
  const receivedMatch = received.find((g) => g.id === params.id) as GiftReceivedItem | undefined;
  const preferred = requestedDirection === 'given' ? givenMatch : receivedMatch;
  const fallback = requestedDirection === 'given' ? receivedMatch : givenMatch;
  const giftFromStore = preferred ?? fallback;
  const directionFromStore: Direction = preferred
    ? requestedDirection
    : requestedDirection === 'given'
      ? 'received'
      : 'given';

  const direction: Direction = snapshot?.direction ?? directionFromStore;
  const gift = snapshot?.gift ?? giftFromStore ?? null;

  // Один принудительный refetch, если брони нет в уже загруженном сторе:
  // экран открывают из свежего пуша, а списки могли закешироваться до брони.
  const [didRefetch, setDidRefetch] = useState(false);
  const isRefetching = isLoaded && !giftFromStore && !snapshot && !didRefetch;

  useEffect(() => {
    if (!isLoaded) {
      loadAll();
      return;
    }
    if (isRefetching) {
      setDidRefetch(true);
      loadAll();
    }
  }, [isLoaded, isRefetching, loadAll]);

  useEffect(() => {
    // Сохраняем снимок при первом обнаружении gift'а в сторе.
    if (giftFromStore && !snapshot) {
      setSnapshot({ direction: directionFromStore, gift: giftFromStore });
    }
  }, [giftFromStore, directionFromStore, snapshot]);

  // Брони может не быть вовсе (отменена, пункт удалён из вишлиста). Вместо
  // тупика «Подарок не найден» уводим в нужный раздел подарков — «Мне дарят»
  // для брони на твой вишлист, «Я дарю» для своей.
  const notFound = isLoaded && !isRefetching && !snapshot && !giftFromStore;
  useEffect(() => {
    if (!notFound) return;
    router.replace(`/settings/wishlists?tab=${requestedDirection}` as any);
  }, [notFound, requestedDirection, router]);

  const handleCancel = () => {
    if (!gift || direction !== 'given') return;
    const givenGift = gift as GiftGivenItem;
    Alert.alert(
      'Отменить бронирование?',
      `${gift.record.artist} — ${gift.record.title}`,
      [
        { text: 'Нет', style: 'cancel' },
        {
          text: 'Отменить',
          style: 'destructive',
          onPress: async () => {
            setIsActing(true);
            try {
              await api.cancelGiftBooking(gift.id, givenGift.cancel_token);
              analytics.giftBookingCancelled(gift.record.discogs_id);
              removeGiven(gift.id);
              toast.success('Бронь отменена');
              router.back();
            } catch (error: any) {
              const isTimeout = error?.code === 'ECONNABORTED';
              const detail = error?.response?.data?.detail;
              toast.error(
                isTimeout ? 'Сервер не отвечает' : 'Не удалось отменить',
                isTimeout
                  ? 'Попробуй ещё раз через минуту'
                  : detail || 'Что-то пошло не так',
              );
            } finally {
              setIsActing(false);
            }
          },
        },
      ],
    );
  };

  const handleComplete = () => {
    if (!gift || direction !== 'received') return;
    Alert.alert(
      'Подарок получен?',
      `${gift.record.artist} — ${gift.record.title}\n\nПластинка добавится в твою коллекцию, дарителю придёт «спасибо».`,
      [
        { text: 'Ещё нет', style: 'cancel' },
        {
          text: 'Получено!',
          onPress: async () => {
            setIsActing(true);
            try {
              await api.completeGiftBooking(gift.id);
              analytics.giftCompleted({ via: 'gift_screen', discogs_id: gift.record.discogs_id });
              removeReceived(gift.id);
              await Promise.all([fetchCollectionItems(), fetchWishlistItems()]);
              // Подарок вошёл в коллекцию — owned-ids обновляются только по
              // мутациям, рефетч списков сет больше не трогает.
              useCollectionStore.getState().fetchOwnedIds();
              toast.success('Спасибо!', 'Пластинка теперь в твоей коллекции');
              router.back();
            } catch (error: any) {
              const isTimeout = error?.code === 'ECONNABORTED';
              const detail = error?.response?.data?.detail;
              toast.error(
                isTimeout ? 'Сервер не отвечает' : 'Не удалось',
                isTimeout
                  ? 'Попробуй ещё раз через минуту'
                  : detail || 'Что-то пошло не так',
              );
            } finally {
              setIsActing(false);
            }
          },
        },
      ],
    );
  };

  if (!isLoaded || isRefetching || notFound) {
    return (
      <View style={[styles.container, styles.center, { paddingTop: insets.top }]}>
        <ActivityIndicator size="large" color={Colors.royalBlue} />
      </View>
    );
  }

  // Практически недостижимо: при notFound выше уже показан лоадер и идёт
  // переход в раздел подарков. Оставлено как страховка на случай гонки.
  if (!gift) {
    return (
      <View style={[styles.container, { paddingTop: insets.top }]}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
            <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Подарок</Text>
          <View style={styles.placeholder} />
        </View>
        <View style={styles.center}>
          <Icon name="gift-outline" size={48} color={Colors.textMuted} />
          <Text style={styles.notFoundText}>Подарок не найден</Text>
        </View>
      </View>
    );
  }

  const status = gift.status as GiftStatus;
  const isGiven = direction === 'given';
  const givenGift = isGiven ? (gift as GiftGivenItem) : null;
  const cover = gift.record.cover_image_url || gift.record.thumb_image_url;
  const price = isGiven
    ? formatPrice(gift.record.estimated_price_median, gift.record.price_currency)
    : null;
  const formatChip = gift.record.format_type;
  const yearLabelChip = [gift.record.year, gift.record.label].filter(Boolean).join(' · ');

  // Кнопка действия
  let actionLabel: string | null = null;
  let actionStyle: 'primary' | 'destructive' | 'disabled' = 'primary';
  let onAction: (() => void) | null = null;

  if (isGiven) {
    if (status === 'booked') {
      actionLabel = 'Отменить бронь';
      actionStyle = 'destructive';
      onAction = handleCancel;
    } else if (status === 'completed') {
      actionLabel = 'Подарок вручён';
      actionStyle = 'disabled';
    }
  } else {
    if (status === 'booked') {
      actionLabel = 'Подарок получен!';
      actionStyle = 'primary';
      onAction = handleComplete;
    } else if (status === 'completed') {
      actionLabel = 'Уже в коллекции';
      actionStyle = 'disabled';
    } else if (status === 'pending') {
      actionLabel = 'Ждём подтверждения от дарителя';
      actionStyle = 'disabled';
    }
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Icon name="arrow-back" size={24} color={Colors.royalBlue} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Подарок</Text>
        <View style={styles.placeholder} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + 96 + Spacing.lg },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Обложка */}
        <View style={styles.coverWrap}>
          {cover ? (
            <Image
              source={cover}
              style={styles.cover}
              contentFit="cover"
              cachePolicy="disk"
            />
          ) : (
            <View style={[styles.cover, styles.coverPlaceholder]}>
              <Icon name="disc-outline" size={64} color={Colors.textMuted} />
            </View>
          )}
        </View>

        {/* Метаданные */}
        <Text style={styles.artist}>{cleanArtistName(gift.record.artist)}</Text>
        <Text style={styles.title}>{gift.record.title}</Text>

        <View style={styles.chipsRow}>
          {!!yearLabelChip && (
            <View style={styles.chip}>
              <Text style={styles.chipText}>{yearLabelChip}</Text>
            </View>
          )}
          {!!formatChip && (
            <View style={styles.chip}>
              <Text style={styles.chipText}>{formatChip}</Text>
            </View>
          )}
        </View>

        {/* Статус */}
        <View style={[styles.statusPill, { backgroundColor: STATUS_COLOR[status] + '15' }]}>
          <View style={[styles.statusDot, { backgroundColor: STATUS_COLOR[status] }]} />
          <Text style={[styles.statusText, { color: STATUS_COLOR[status] }]}>
            {STATUS_LABEL[status]}
          </Text>
        </View>

        {/* Цена (только если даритель и есть estimate) */}
        {!!price && (
          <View style={[styles.priceCard, Shadows.sm]}>
            <Text style={styles.priceLabel}>Предварительная стоимость</Text>
            <Text style={styles.priceValue}>≈ {price}</Text>
            <Text style={styles.priceHint}>
              Медианная цена с Discogs — ориентир для покупки
            </Text>
          </View>
        )}

        {/* Контекст бронирования */}
        <View style={[styles.metaCard, Shadows.sm]}>
          {isGiven && givenGift ? (
            <View style={styles.metaRow}>
              <Icon name="person-outline" size={18} color={Colors.textSecondary} />
              <Text style={styles.metaLabel}>Дарю</Text>
              <Text style={styles.metaValue}>@{givenGift.for_user.username}</Text>
            </View>
          ) : (
            <View style={styles.metaRow}>
              <Icon name="gift-outline" size={18} color={Colors.success} />
              <Text style={styles.metaLabel}>От</Text>
              <Text style={styles.metaValue}>тайного дарителя</Text>
            </View>
          )}

          <View style={styles.metaRow}>
            <Icon name="calendar-outline" size={18} color={Colors.textSecondary} />
            <Text style={styles.metaLabel}>Забронировано</Text>
            <Text style={styles.metaValue}>{formatDate(gift.booked_at)}</Text>
          </View>

          {!!gift.completed_at && (
            <View style={styles.metaRow}>
              <Icon name="checkmark-circle-outline" size={18} color={Colors.success} />
              <Text style={styles.metaLabel}>Доставлено</Text>
              <Text style={styles.metaValue}>{formatDate(gift.completed_at)}</Text>
            </View>
          )}
        </View>

        {/* Открыть полную карточку пластинки */}
        <TouchableOpacity
          style={styles.openRecordButton}
          activeOpacity={0.7}
          onPress={() => router.push(`/record/${gift.record.id}`)}
        >
          <Icon name="disc-outline" size={20} color={Colors.royalBlue} />
          <Text style={styles.openRecordText}>Открыть карточку пластинки</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Зафиксированная кнопка действия */}
      {actionLabel && (
        <View style={[styles.actionBar, { paddingBottom: insets.bottom + Spacing.md }]}>
          <TouchableOpacity
            style={[
              styles.actionButton,
              actionStyle === 'destructive' && styles.actionButtonDestructive,
              actionStyle === 'disabled' && styles.actionButtonDisabled,
            ]}
            onPress={onAction ?? undefined}
            disabled={actionStyle === 'disabled' || isActing}
            activeOpacity={0.8}
          >
            {isActing ? (
              <ActivityIndicator size="small" color={Colors.background} />
            ) : (
              <Text
                style={[
                  styles.actionButtonText,
                  actionStyle === 'disabled' && styles.actionButtonTextDisabled,
                ]}
              >
                {actionLabel}
              </Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.md,
  },
  notFoundText: {
    ...Typography.body,
    color: Colors.textSecondary,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    ...Typography.h4,
    color: Colors.royalBlue,
  },
  backButton: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholder: {
    width: 36,
    height: 36,
  },
  content: {
    padding: Spacing.lg,
  },
  coverWrap: {
    alignItems: 'center',
    marginBottom: Spacing.lg,
  },
  cover: {
    width: COVER_SIZE,
    height: COVER_SIZE,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.surface,
  },
  coverPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  artist: {
    ...Typography.h4,
    color: Colors.textSecondary,
    textAlign: 'center',
    marginBottom: 4,
  },
  title: {
    ...Typography.h2,
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.md,
  },
  chipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  chip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: BorderRadius.sm,
    backgroundColor: Colors.surface,
  },
  chipText: {
    ...Typography.caption,
    color: Colors.textSecondary,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'center',
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: BorderRadius.md,
    gap: 8,
    marginBottom: Spacing.lg,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    ...Typography.bodySmall,
    fontWeight: '600',
  },
  priceCard: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  priceLabel: {
    ...Typography.caption,
    color: Colors.textSecondary,
    marginBottom: 4,
  },
  priceValue: {
    ...Typography.h2,
    color: Colors.royalBlue,
    marginBottom: 4,
  },
  priceHint: {
    ...Typography.caption,
    color: Colors.textMuted,
  },
  metaCard: {
    backgroundColor: Colors.background,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.border,
    padding: Spacing.md,
    marginBottom: Spacing.md,
    gap: Spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
  },
  metaLabel: {
    ...Typography.body,
    color: Colors.textSecondary,
    flex: 1,
  },
  metaValue: {
    ...Typography.bodyBold,
    color: Colors.text,
  },
  openRecordButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.md,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.surface,
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  openRecordText: {
    ...Typography.body,
    color: Colors.royalBlue,
    flex: 1,
  },
  actionBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: Spacing.lg,
    paddingTop: Spacing.md,
    backgroundColor: Colors.background,
    borderTopWidth: 1,
    borderTopColor: Colors.divider,
  },
  actionButton: {
    height: 52,
    borderRadius: BorderRadius.lg,
    backgroundColor: Colors.royalBlue,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionButtonDestructive: {
    backgroundColor: Colors.error,
  },
  actionButtonDisabled: {
    backgroundColor: Colors.surface,
  },
  actionButtonText: {
    ...Typography.button,
    color: Colors.background,
  },
  actionButtonTextDisabled: {
    color: Colors.textMuted,
  },
});
