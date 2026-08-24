/**
 * PriceHistorySheet — шторка динамики цены (макет 1d). Оверлей по тапу обложки на радаре.
 * Переиспользует PriceSparkline + /records/{id}/price-history. Кнопки «В магазин»/«Порог».
 */
import React, { forwardRef, useImperativeHandle, useRef, useState, useCallback } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, Image, Alert } from 'react-native';
import {
  BottomSheetModal,
  BottomSheetScrollView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { useRouter } from 'expo-router';
import { Colors, Typography, Spacing, BorderRadius } from '../../constants/theme';
import { PriceSparkline } from '../PriceSparkline';
import { RadarIcon } from '../RadarIcon';
import { Icon } from '@/components/ui';
import { api } from '../../lib/api';
import { toast } from '../../lib/toast';
import { useCollectionStore } from '../../lib/store';
import { PriceHistoryResponse, RadarStatus, RadarEvent } from '../../lib/types';

const RADAR_EVENT_LABEL: Record<string, string> = {
  available: 'Появилась в продаже',
  match: 'Подошла под порог',
  alt: 'Появилась альтернатива',
  price_drop: 'Подешевела',
  absent: 'Пропала из продажи',
};

export interface PriceHistorySheetData {
  itemId: string;
  recordId: string;
  title: string;
  artist?: string | null;
  coverUrl?: string | null;
  currentPrice?: number | null;
  threshold?: number | null;
  /** Задан → порог относительный («дешевле обычного»), threshold уже посчитан. */
  thresholdPct?: number | null;
  status: RadarStatus;
  buyUrl?: string | null;
  /** id листинга под buyUrl — родитель шлёт по нему POST /offers/{id}/click. */
  buyListingId?: string | null;
  /** discogs_id записи — нужен родителю для offer_click в аналитике. */
  discogsId?: string | null;
  offersCount?: number;
  /**
   * Цена и наличие относятся к ДРУГОМУ прессингу, принятому юзером как
   * подходящий (accept_alt). Раньше принятый аналог вёл в шит подтверждения и
   * при каждом тапе переспрашивал «считать подходящим?», хотя решение уже
   * принято. Теперь ведёт сюда, а отмена решения — строкой внутри.
   */
  isAcceptedAlt?: boolean;
  /** Название принятого прессинга — чтобы было видно, за чем следим. */
  altTitle?: string | null;
  /** Сколько версий скрыто через «не предлагать» (путь назад из бана). */
  rejectedAltCount?: number;
}

export interface PriceHistorySheetRef {
  present: (data: PriceHistorySheetData) => void;
}

interface Props {
  onOpenStore?: (data: PriceHistorySheetData) => void;
  onEditThreshold?: (data: PriceHistorySheetData) => void;
  onRemoved?: () => void;
  /** Решение по аналогу изменилось — родителю надо перезагрузить радар. */
  onAltChanged?: () => void;
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
  ({ onOpenStore, onEditThreshold, onRemoved, onAltChanged }, ref) => {
    const sheetRef = useRef<BottomSheetModal>(null);
    const router = useRouter();
    const removeRadar = useCollectionStore((s) => s.removeWishlistRadar);
    const setAcceptAlt = useCollectionStore((s) => s.setWishlistAcceptAlt);
    // Побочные эффекты — только после закрытия шита: перерисовка родителя во
    // время анимации dismiss её обрывает (ловили это на шите аналога).
    const pendingRef = useRef<(() => void) | null>(null);
    const closeThen = useCallback((fn?: () => void) => {
      pendingRef.current = fn ?? null;
      sheetRef.current?.dismiss();
    }, []);
    const runPending = useCallback(() => {
      const fn = pendingRef.current;
      pendingRef.current = null;
      fn?.();
    }, []);
    const [data, setData] = useState<PriceHistorySheetData | null>(null);
    const [history, setHistory] = useState<PriceHistoryResponse | null>(null);
    const [radarEvents, setRadarEvents] = useState<RadarEvent[]>([]);

    const present = useCallback((d: PriceHistorySheetData) => {
      setData(d);
      setHistory(null);
      setRadarEvents([]);
      sheetRef.current?.present();
      api.getPriceHistory(d.recordId, 90).then(setHistory).catch(() => {});
      api.getRadarEvents(d.itemId, 20).then((r) => setRadarEvents(r.events)).catch(() => {});
    }, []);

    useImperativeHandle(ref, () => ({ present }), [present]);

    // Переход в карточку релиза (по тапу на обложку и по кнопке «Открыть релиз»).
    const openRelease = useCallback(() => {
      const rid = data?.recordId;
      if (!rid) return;
      sheetRef.current?.dismiss();
      router.push(`/record/${rid}` as any);
    }, [data?.recordId, router]);

    // Удаление прямо из карточки радара — с подтверждением.
    const handleRemove = useCallback(() => {
      if (!data) return;
      Alert.alert(
        'Убрать с радара?',
        `«${data.title}» перестанет отслеживаться.`,
        [
          { text: 'Отмена', style: 'cancel' },
          {
            text: 'Убрать',
            style: 'destructive',
            onPress: () => {
              closeThen(() => {
                removeRadar(data.itemId)
                  .then(() => { toast.success('Убрали с радара'); onRemoved?.(); })
                  .catch(() => toast.error('Не удалось убрать радар'));
              });
            },
          },
        ],
      );
    }, [data, removeRadar, onRemoved]);

    // «Только моя версия»: снимаем accept_alt и НЕ баним прессинг. Раньше это
    // делалось через reject, который заносил версию в rejected_alt_record_ids
    // навсегда — айтем падал в absent, хотя аналог остался в продаже, и пути
    // назад из интерфейса не было вовсе. Теперь аналог просто возвращается в
    // статус «альтернатива», и его можно принять снова.
    const onOwnVersionOnly = useCallback(() => {
      if (!data) return;
      const { itemId } = data;
      closeThen(() => {
        setAcceptAlt(itemId, false)
          .then(() => { toast.success('Следим только за своей версией'); onAltChanged?.(); })
          .catch(() => toast.error('Не удалось сохранить'));
      });
    }, [data, closeThen, setAcceptAlt, onAltChanged]);

    // Путь назад из «не предлагать»: возвращаем все скрытые прессинги.
    const onRestoreHidden = useCallback(() => {
      if (!data) return;
      const { itemId } = data;
      closeThen(() => {
        api
          .updateWishlistItem(itemId, { restore_rejected_alts: true })
          .then(() => { toast.success('Скрытые версии возвращены'); onAltChanged?.(); })
          .catch(() => toast.error('Не удалось вернуть'));
      });
    }, [data, closeThen, onAltChanged]);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.5} />
      ),
      [],
    );

    // Хронология статусов радара (реальные события из radar_status_events).
    const events = radarEvents.slice(0, 6).map((e) => ({
      label: RADAR_EVENT_LABEL[e.status] ?? 'Обновление',
      date: dm(e.created_at),
      price: e.price_rub,
      store: e.store_name,
      drop: e.status === 'price_drop' || e.status === 'match',
    }));

    const pill = data ? STATUS_PILL[data.status] : STATUS_PILL.available;
    const cover = data?.coverUrl ?? null;
    // buyUrl приходит только когда на бэке нашёлся подходящий in_stock листинг
    // (для accept_alt — ссылка на принятый аналог). Нет ссылки = купить негде.
    const canBuy = !!data?.buyUrl;

    return (
      <BottomSheetModal
        ref={sheetRef}
        snapPoints={['82%']}
        onDismiss={runPending}
        backdropComponent={renderBackdrop}
        handleIndicatorStyle={styles.handle}
        backgroundStyle={styles.sheetBg}
      >
        <BottomSheetScrollView contentContainerStyle={styles.container}>
          <View style={styles.headerRow}>
            <TouchableOpacity activeOpacity={0.8} onPress={openRelease}>
              {cover ? (
                <Image source={{ uri: cover }} style={styles.cover} />
              ) : (
                <View style={[styles.cover, styles.coverPlaceholder]} />
              )}
            </TouchableOpacity>
            <View style={styles.headerText}>
              {data?.artist ? <Text style={styles.artist}>{data.artist.toUpperCase()}</Text> : null}
              <Text style={styles.title} numberOfLines={2}>{data?.title}</Text>
              <TouchableOpacity style={styles.openRelease} onPress={openRelease} activeOpacity={0.7} hitSlop={8}>
                <Text style={styles.openReleaseTxt}>Открыть релиз</Text>
                <Icon name="chevron-forward" size={13} color={Colors.royalBlue} />
              </TouchableOpacity>
            </View>
            <TouchableOpacity style={styles.deleteBtn} onPress={handleRemove} activeOpacity={0.8} hitSlop={8}>
              <Icon name="trash-outline" size={20} color={Colors.error} />
            </TouchableOpacity>
          </View>

          <View style={styles.priceRow}>
            {data?.currentPrice != null ? (
              <Text style={styles.price}>{fmt(data.currentPrice)} ₽</Text>
            ) : null}
            {data?.threshold != null ? (
              <View style={styles.thChip}>
                <RadarIcon size={14} color={Colors.royalBlue} />
                <Text style={styles.thChipTxt}>
                  {data.thresholdPct
                    ? `на ${data.thresholdPct}% дешевле обычного · ${fmt(data.threshold)} ₽`
                    : `дешевле ${fmt(data.threshold)} ₽`}
                </Text>
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

          {data?.isAcceptedAlt ? (
            <View style={styles.altCard}>
              <Text style={styles.altTitle}>Следим за другой версией</Text>
              <Text style={styles.altBody}>
                {data.altTitle
                  ? `Подходящим считается «${data.altTitle}» — другой прессинг этого альбома.`
                  : 'Подходящим считается другой прессинг этого альбома.'}
              </Text>
              <TouchableOpacity style={styles.altBtn} onPress={onOwnVersionOnly} activeOpacity={0.7}>
                <Text style={styles.altBtnTxt}>Следить только за своей версией</Text>
              </TouchableOpacity>
            </View>
          ) : null}

          {data?.rejectedAltCount ? (
            <TouchableOpacity style={styles.hiddenRow} onPress={onRestoreHidden} activeOpacity={0.7}>
              <Text style={styles.hiddenTxt}>
                Скрыто версий: {data.rejectedAltCount}
              </Text>
              <Text style={styles.hiddenAction}>Вернуть</Text>
            </TouchableOpacity>
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
                  <View style={styles.histLeft}>
                    <Text style={styles.histLabel}>{e.label}</Text>
                    {e.store ? <Text style={styles.histStore}>{e.store}</Text> : null}
                  </View>
                  <Text style={styles.histMeta}>
                    {e.date}
                    {e.price != null ? (
                      <> · <Text style={{ color: e.drop ? Colors.success : Colors.textSecondary, fontWeight: '700' }}>{fmt(e.price)} ₽</Text></>
                    ) : null}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.btnRow}>
            {/* Купить можно только если есть живой листинг. Раньше кнопка была
                активна всегда и на absent-релизе уводила в карточку — обещала
                магазин там, где его нет. Пользователь не заперт: «Открыть
                релиз» в шапке никуда не делось. */}
            <TouchableOpacity
              style={[styles.primaryBtn, !canBuy && styles.primaryBtnOff]}
              activeOpacity={0.9}
              disabled={!canBuy}
              onPress={() => { sheetRef.current?.dismiss(); data && onOpenStore?.(data); }}
            >
              <Text style={[styles.primaryTxt, !canBuy && styles.primaryTxtOff]}>
                {canBuy ? 'Заказать в магазине' : 'Сейчас нет в продаже'}
              </Text>
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
  deleteBtn: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(229,72,77,0.10)' },
  artist: { fontSize: 11, fontFamily: 'Inter_600SemiBold', letterSpacing: 1, color: Colors.textSecondary },
  title: { ...Typography.h3, color: Colors.text, marginTop: 2 },
  openRelease: { flexDirection: 'row', alignItems: 'center', gap: 2, marginTop: 6, alignSelf: 'flex-start' },
  openReleaseTxt: { fontSize: 13, fontFamily: 'Inter_600SemiBold', color: Colors.royalBlue },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 18 },
  price: { fontFamily: 'Inter_800ExtraBold', fontSize: 28, color: Colors.text, fontVariant: ['tabular-nums'] },
  priceHint: { fontSize: 12, color: Colors.textSecondary, marginTop: 6 },
  thChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, backgroundColor: '#E8EBFA', borderRadius: 9999 },
  thChipTxt: { fontSize: 13, fontFamily: 'Inter_600SemiBold', color: Colors.royalBlue },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 9999 },
  pillDot: { width: 7, height: 7, borderRadius: 9999 },
  pillTxt: { fontSize: 13, fontFamily: 'Inter_700Bold' },
  altCard: { marginTop: 16, padding: 16, borderRadius: 16, backgroundColor: 'rgba(244,160,106,0.14)' },
  altTitle: { ...Typography.bodyBold, color: '#8A5326' },
  altBody: { fontSize: 13, lineHeight: 18, color: '#8A5326', marginTop: 4 },
  altBtn: { marginTop: 12, paddingVertical: 12, borderRadius: 12, backgroundColor: '#fff', alignItems: 'center' },
  altBtnTxt: { fontSize: 14, fontFamily: 'Inter_600SemiBold', color: '#8A5326' },
  hiddenRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 14, backgroundColor: Colors.surfaceHover },
  hiddenTxt: { fontSize: 13, color: Colors.textSecondary },
  hiddenAction: { fontSize: 14, fontFamily: 'Inter_600SemiBold', color: Colors.royalBlue },
  chartCard: { marginTop: 18, backgroundColor: '#fff', borderRadius: 14, paddingVertical: 4 },
  histBlock: { marginTop: 16 },
  histTitle: { ...Typography.bodyBold, color: Colors.text, marginBottom: 8 },
  histRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 11 },
  histRowBorder: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  histLeft: { flex: 1 },
  histLabel: { fontSize: 14, color: Colors.text },
  histStore: { fontSize: 12, color: Colors.textMuted, marginTop: 1 },
  histMeta: { fontSize: 13, color: Colors.textSecondary, fontVariant: ['tabular-nums'] },
  btnRow: { flexDirection: 'row', gap: 12, marginTop: 22 },
  primaryBtn: { flex: 1, alignItems: 'center', paddingVertical: 17, backgroundColor: Colors.royalBlue, borderRadius: 16 },
  primaryTxt: { ...Typography.button, color: '#fff' },
  primaryBtnOff: { backgroundColor: Colors.surfaceHover },
  primaryTxtOff: { color: Colors.textMuted },
  secondaryBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 17, paddingHorizontal: 20, backgroundColor: '#E8EBFA', borderRadius: 16 },
  secondaryTxt: { ...Typography.button, color: Colors.royalBlue },
});
