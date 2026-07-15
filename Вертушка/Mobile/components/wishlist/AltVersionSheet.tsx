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
  BottomSheetView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { Colors, Typography } from '../../constants/theme';
import { useCollectionStore } from '../../lib/store';
import { toast } from '../../lib/toast';

export interface AltVersionSheetData {
  itemId: string;
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
}

export interface AltVersionSheetRef {
  present: (data: AltVersionSheetData) => void;
}

interface Props {
  onConfirm?: (data: AltVersionSheetData) => void;
}

const fmt = (n: number) => Math.round(n).toLocaleString('ru-RU');

export const AltVersionSheet = forwardRef<AltVersionSheetRef, Props>(({ onConfirm }, ref) => {
  const sheetRef = useRef<BottomSheetModal>(null);
  const [data, setData] = useState<AltVersionSheetData | null>(null);
  const setAcceptAlt = useCollectionStore((s) => s.setWishlistAcceptAlt);

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

  const onYes = () => {
    sheetRef.current?.dismiss();
    if (!data) return;
    setAcceptAlt(data.itemId, true)
      .then(() => { toast.success('Следим и за этой версией'); onConfirm?.(data); })
      .catch(() => toast.error('Не удалось сохранить'));
  };

  const cover = data?.altCoverUrl ?? null;

  // Отличия альт-версии от версии из вишлиста.
  const diffs: { label: string; value: string }[] = [];
  if (data?.altYear && data.altYear !== data.recordYear) diffs.push({ label: 'Год', value: String(data.altYear) });
  if (data?.altCountry && data.altCountry !== data.recordCountry) diffs.push({ label: 'Страна', value: data.altCountry });
  if (data?.altFormat) diffs.push({ label: 'Формат', value: data.altFormat });

  return (
    <BottomSheetModal
      ref={sheetRef}
      enableDynamicSizing
      backdropComponent={renderBackdrop}
      handleIndicatorStyle={styles.handle}
      backgroundStyle={styles.sheetBg}
    >
      <BottomSheetView style={styles.container}>
        {cover ? (
          <Image source={{ uri: cover }} style={styles.cover} />
        ) : (
          <View style={[styles.cover, styles.coverPlaceholder]} />
        )}
        <Text style={styles.title}>Другая версия в наличии</Text>
        <Text style={styles.body}>
          В продаже другой прессинг{data?.recordTitle ? ` «${data.recordTitle}»` : ''}. Считать его подходящим?
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

        <View style={styles.btns}>
          <TouchableOpacity style={styles.primaryBtn} onPress={onYes} activeOpacity={0.9}>
            <Text style={styles.primaryTxt}>Да, следить</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={() => sheetRef.current?.dismiss()} activeOpacity={0.7}>
            <Text style={styles.secondaryTxt}>Нет</Text>
          </TouchableOpacity>
        </View>
      </BottomSheetView>
    </BottomSheetModal>
  );
});

AltVersionSheet.displayName = 'AltVersionSheet';
export default AltVersionSheet;

const styles = StyleSheet.create({
  sheetBg: { backgroundColor: Colors.surface, borderRadius: 28 },
  handle: { backgroundColor: '#D3D7E6', width: 40 },
  container: { alignItems: 'center', paddingHorizontal: 24, paddingBottom: 34, paddingTop: 4 },
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
  btns: { alignSelf: 'stretch', gap: 12, marginTop: 24 },
  primaryBtn: { alignItems: 'center', paddingVertical: 18, backgroundColor: Colors.royalBlue, borderRadius: 16 },
  primaryTxt: { ...Typography.button, color: '#fff' },
  secondaryBtn: { alignItems: 'center', paddingVertical: 16, backgroundColor: '#E8EBFA', borderRadius: 16 },
  secondaryTxt: { ...Typography.button, color: Colors.royalBlue },
});
