/**
 * AltVersionSheet — подтверждение альтернативной версии (макет 1h).
 * Тап по peach-кружку «альтернатива» на радаре. Показывает другой прессинг того же
 * альбома и его отличия от версии из вишлиста. «Да, следить» → accept_alt=true:
 * дальше он считается подходящим (статус «в продаже»).
 */
import React, { forwardRef, useImperativeHandle, useRef, useState, useCallback } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, Image } from 'react-native';
import {
  BottomSheetModal,
  BottomSheetScrollView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Typography } from '../../constants/theme';
import { useCollectionStore } from '../../lib/store';
import { toast } from '../../lib/toast';

export interface AltVersionSheetData {
  itemId: string;
  altRecordId?: string | null;
  recordTitle?: string | null;
  recordArtist?: string | null;
  recordYear?: number | null;
  recordCountry?: string | null;
  altTitle?: string | null;
  altCoverUrl?: string | null;
  altYear?: number | null;
  altCountry?: string | null;
  altFormat?: string | null;
  altPrice?: number | null;
  // Аналог уже принят ранее (accept_alt=true) — шит работает как отмена.
  accepted?: boolean;
}

export interface AltVersionSheetRef {
  present: (data: AltVersionSheetData) => void;
}

interface Props {
  onConfirm?: (data: AltVersionSheetData) => void;
}

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');

export const AltVersionSheet = forwardRef<AltVersionSheetRef, Props>(({ onConfirm }, ref) => {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const sheetRef = useRef<BottomSheetModal>(null);
  const [data, setData] = useState<AltVersionSheetData | null>(null);
  const setAcceptAlt = useCollectionStore((s) => s.setWishlistAcceptAlt);
  const rejectAlt = useCollectionStore((s) => s.rejectWishlistAlt);

  // Побочные эффекты запускаем строго ПОСЛЕ того, как шит закрылся. Раньше они
  // шли сразу за dismiss(), и родительский setState (перезагрузка радара) или
  // навигация перерисовывали дерево во время анимации закрытия — она обрывалась,
  // и шит оставался висеть. Копим колбэк здесь, выполняем по onDismiss.
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

  const present = useCallback((d: AltVersionSheetData) => {
    setData(d);
    sheetRef.current?.present();
  }, []);

  useImperativeHandle(ref, () => ({ present }), [present]);

  const renderBackdrop = useCallback(
    (props: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.5} />
    ),
    [],
  );

  const accepted = data?.accepted === true;

  const onYes = () => {
    if (!data) { closeThen(); return; }
    // «Продолжить следить» при уже принятом аналоге ничего не меняет — это
    // чистое подтверждение. Просто закрываемся: дёргать onConfirm (а он
    // перезагружает радар) тут не за чем, и именно этот лишний setState рвал
    // анимацию закрытия.
    if (accepted) { closeThen(); return; }
    closeThen(() => {
      setAcceptAlt(data.itemId, true)
        .then(() => { toast.success('Следим и за этой версией'); onConfirm?.(data); })
        .catch(() => toast.error('Не удалось сохранить'));
    });
  };

  // «Нет» — явный отказ: этот прессинг больше не предлагаем, радар снова
  // ищет ровно ту версию, которая в вишлисте.
  const onNo = () => {
    if (!data) { closeThen(); return; }
    const { itemId, altRecordId } = data;
    if (!altRecordId) {
      closeThen(
        accepted
          ? () => {
              setAcceptAlt(itemId, false)
                .then(() => { toast.success('Следим только за своей версией'); onConfirm?.(data); })
                .catch(() => toast.error('Не удалось сохранить'));
            }
          : undefined,
      );
      return;
    }
    closeThen(() => {
      rejectAlt(itemId, altRecordId)
        .then(() => { toast.success('Больше не предлагаем эту версию'); onConfirm?.(data); })
        .catch(() => toast.error('Не удалось сохранить'));
    });
  };

  // Открыть карточку самого прессинга: до этого решение «следить / не следить»
  // приходилось принимать по обложке и трём строчкам отличий.
  const onOpenRelease = () => {
    if (!data?.altRecordId) return;
    const params = new URLSearchParams();
    if (data.altTitle) params.set('previewTitle', data.altTitle);
    if (data.recordArtist) params.set('previewArtist', data.recordArtist);
    if (data.altCoverUrl) params.set('previewCover', data.altCoverUrl);
    if (data.altYear) params.set('previewYear', String(data.altYear));
    const qs = params.toString();
    const href = `/record/${data.altRecordId}${qs ? `?${qs}` : ''}`;
    closeThen(() => router.push(href as any));
  };

  const cover = data?.altCoverUrl ?? null;
  const canOpen = Boolean(data?.altRecordId);

  // Отличия альт-версии от версии из вишлиста.
  const diffs: { label: string; value: string }[] = [];
  if (data?.altYear && data.altYear !== data.recordYear) diffs.push({ label: 'Год', value: String(data.altYear) });
  if (data?.altCountry && data.altCountry !== data.recordCountry) diffs.push({ label: 'Страна', value: data.altCountry });
  if (data?.altFormat) diffs.push({ label: 'Формат', value: data.altFormat });

  return (
    <BottomSheetModal
      ref={sheetRef}
      enableDynamicSizing
      topInset={insets.top + 8}
      onDismiss={runPending}
      backdropComponent={renderBackdrop}
      handleIndicatorStyle={styles.handle}
      backgroundStyle={styles.sheetBg}
    >
      {/* Скроллящийся контент, а не BottomSheetView. Содержимое здесь высокое
          (обложка, четыре строки текста, цена, карточка отличий, ссылка и две
          кнопки), и на компактных экранах оно перерастало высоту листа. Дети,
          вылезшие за границы контейнера, на iOS продолжают РИСОВАТЬСЯ, но
          hit-test их отбрасывает: кнопка видна и не нажимается. Ровно та же
          болезнь, что была у «Сохранить» в шторке порога. */}
      <BottomSheetScrollView contentContainerStyle={styles.container}>
        <TouchableOpacity
          onPress={onOpenRelease}
          disabled={!canOpen}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel="Открыть карточку релиза"
        >
          {cover ? (
            <Image source={{ uri: cover }} style={styles.cover} />
          ) : (
            <View style={[styles.cover, styles.coverPlaceholder]} />
          )}
        </TouchableOpacity>
        <Text style={styles.title}>
          {accepted ? 'Следим за другой версией' : 'Другая версия в наличии'}
        </Text>
        <Text style={styles.body}>
          {accepted
            ? `Сейчас подходящим считается другой прессинг${data?.recordTitle ? ` «${data.recordTitle}»` : ''}. Вернуться к поиску только своей версии?`
            : `В продаже другой прессинг${data?.recordTitle ? ` «${data.recordTitle}»` : ''}. Считать его подходящим?`}
        </Text>

        {data?.altPrice != null ? <Text style={styles.price}>{fmt(data.altPrice)} ₽</Text> : null}

        {diffs.length > 0 ? (
          <View style={styles.diffCard}>
            {diffs.map((d, i) => (
              <View key={i} style={[styles.diffRow, i < diffs.length - 1 && styles.diffRowBorder]}>
                <Text style={styles.diffLabel}>{d.label}</Text>
                <Text style={styles.diffValue}>{d.value}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {canOpen ? (
          <TouchableOpacity
            style={styles.openLink}
            onPress={onOpenRelease}
            activeOpacity={0.7}
            accessibilityRole="button"
          >
            <Text style={styles.openTxt}>Посмотреть релиз</Text>
            <Ionicons name="chevron-forward" size={16} color={Colors.royalBlue} />
          </TouchableOpacity>
        ) : null}

        <View style={[styles.btns, canOpen && styles.btnsTight]}>
          <TouchableOpacity style={styles.primaryBtn} onPress={onYes} activeOpacity={0.9}>
            <Text style={styles.primaryTxt}>{accepted ? 'Продолжить следить' : 'Да, следить'}</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={onNo} activeOpacity={0.7}>
            <Text style={styles.secondaryTxt}>{accepted ? 'Нет, только моя версия' : 'Нет'}</Text>
          </TouchableOpacity>
        </View>
        <View style={{ height: Math.max(insets.bottom, 12) }} />
      </BottomSheetScrollView>
    </BottomSheetModal>
  );
});

AltVersionSheet.displayName = 'AltVersionSheet';
export default AltVersionSheet;

const styles = StyleSheet.create({
  sheetBg: { backgroundColor: Colors.surface, borderRadius: 28 },
  handle: { backgroundColor: '#D3D7E6', width: 40 },
  container: { alignItems: 'center', paddingHorizontal: 24, paddingBottom: 12, paddingTop: 4 },
  cover: { width: 76, height: 76, borderRadius: 16, marginBottom: 16, borderWidth: 2, borderColor: '#F4A06A' },
  coverPlaceholder: { backgroundColor: Colors.surfaceHover },
  title: { ...Typography.h2, color: Colors.text, textAlign: 'center' },
  body: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginTop: 8, maxWidth: 300 },
  price: { fontFamily: 'Inter_800ExtraBold', fontSize: 26, color: Colors.text, marginTop: 14, fontVariant: ['tabular-nums'] },
  diffCard: { alignSelf: 'stretch', backgroundColor: '#fff', borderRadius: 16, paddingHorizontal: 16, marginTop: 18 },
  diffRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 13 },
  diffRowBorder: { borderBottomWidth: 1, borderBottomColor: Colors.divider },
  diffLabel: { fontSize: 14, color: Colors.textSecondary },
  diffValue: { fontSize: 14, color: Colors.text, fontFamily: 'Inter_600SemiBold' },
  openLink: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 16, paddingVertical: 6 },
  openTxt: { fontSize: 15, fontFamily: 'Inter_600SemiBold', color: Colors.royalBlue },
  btns: { alignSelf: 'stretch', gap: 12, marginTop: 24 },
  btnsTight: { marginTop: 12 },
  primaryBtn: { alignItems: 'center', paddingVertical: 18, backgroundColor: Colors.royalBlue, borderRadius: 16 },
  primaryTxt: { ...Typography.button, color: '#fff' },
  secondaryBtn: { alignItems: 'center', paddingVertical: 16, backgroundColor: '#E8EBFA', borderRadius: 16 },
  secondaryTxt: { ...Typography.button, color: Colors.royalBlue },
});
