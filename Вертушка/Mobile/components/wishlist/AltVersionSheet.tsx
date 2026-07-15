/**
 * AltVersionSheet — подтверждение альтернативной версии (макет 1h).
 * Тап по peach-кружку «альтернатива» на радаре. «Да, следить» → считать другой
 * прессинг подходящим.
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

export interface AltVersionSheetData {
  itemId: string;
  altTitle?: string | null;
  altCoverUrl?: string | null;
}

export interface AltVersionSheetRef {
  present: (data: AltVersionSheetData) => void;
}

interface Props {
  onConfirm?: (data: AltVersionSheetData) => void;
}

export const AltVersionSheet = forwardRef<AltVersionSheetRef, Props>(({ onConfirm }, ref) => {
  const sheetRef = useRef<BottomSheetModal>(null);
  const [data, setData] = useState<AltVersionSheetData | null>(null);

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

  const cover = data?.altCoverUrl ?? null;

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
        <Text style={styles.body}>В продаже другой прессинг этого альбома. Считать его подходящим?</Text>

        <View style={styles.btns}>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => { sheetRef.current?.dismiss(); data && onConfirm?.(data); }}
          >
            <Text style={styles.primaryTxt}>Да, следить</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={() => sheetRef.current?.dismiss()}>
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
  cover: { width: 72, height: 72, borderRadius: 16, marginBottom: 18, borderWidth: 2, borderColor: '#F4A06A' },
  coverPlaceholder: { backgroundColor: Colors.surfaceHover },
  title: { ...Typography.h2, color: Colors.text, textAlign: 'center' },
  body: { ...Typography.body, color: Colors.textSecondary, textAlign: 'center', marginTop: 8, maxWidth: 300 },
  btns: { alignSelf: 'stretch', gap: 12, marginTop: 26 },
  primaryBtn: { alignItems: 'center', paddingVertical: 18, backgroundColor: Colors.royalBlue, borderRadius: 16 },
  primaryTxt: { ...Typography.button, color: '#fff' },
  secondaryBtn: { alignItems: 'center', paddingVertical: 16, backgroundColor: '#E8EBFA', borderRadius: 16 },
  secondaryTxt: { ...Typography.button, color: Colors.royalBlue },
});
