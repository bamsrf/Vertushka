/**
 * PromptSheet — Android-замена `Alert.prompt` (B5 в ANDROID_PORT_PLAN).
 *
 * `Alert.prompt` есть только на iOS; на Android он молча no-op, и создание/
 * переименование папок было мёртвым. Здесь — bottom sheet с `TextInput`,
 * в стиле `ThresholdSheet`. На iOS компонент не монтируется вовсе
 * (`PromptSheetHost` возвращает null), а `promptText()` из `lib/promptCompat`
 * зовёт прежний `Alert.prompt` — iOS-диф нулевой (решение Q6).
 *
 * Почему RN `<Modal>`, а не `@gorhom/bottom-sheet`: промпт вызывают из
 * `FolderPickerModal` / `WishlistFolderPickerModal`, которые сами — RN `Modal`.
 * Gorhom-шит рисуется в `BottomSheetModalProvider` у корня, то есть ПОД
 * открытым Dialog'ом, и его не видно. `Modal` на Android — всегда верхнее
 * окно, плюс `onRequestClose` бесплатно даёт закрытие кнопкой «Назад».
 *
 * `statusBarTranslucent` намеренно НЕ ставим: с ним окно модалки становится
 * полноэкранным и `adjustResize` перестаёт двигать контент от клавиатуры —
 * поле ввода уезжало бы под неё.
 *
 * Хост монтируется один раз в `app/_layout.tsx` через `AndroidSheetsHost`;
 * вызов идёт императивно, как у тостов: `presentPromptSheet(opts)`.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  Easing,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BorderRadius, Colors, Typography } from '../../constants/theme';

export interface PromptSheetOptions {
  title: string;
  message?: string;
  defaultValue?: string;
  placeholder?: string;
  submitLabel?: string;
  cancelLabel?: string;
}

interface PromptRequest extends PromptSheetOptions {
  resolve: (value: string | null) => void;
}

type Presenter = (req: PromptRequest) => void;

let presenter: Presenter | null = null;

/**
 * Показать промпт. Резолвится введённым текстом или `null` (отмена, тап по
 * фону, кнопка «Назад»). Без смонтированного хоста — сразу `null`, чтобы
 * вызывающий код не повис.
 */
export function presentPromptSheet(opts: PromptSheetOptions): Promise<string | null> {
  return new Promise((resolve) => {
    if (!presenter) {
      resolve(null);
      return;
    }
    presenter({ ...opts, resolve });
  });
}

const SLIDE_IN_MS = 220;
const SLIDE_OUT_MS = 160;

export function PromptSheetHost() {
  const insets = useSafeAreaInsets();
  const [req, setReq] = useState<PromptRequest | null>(null);
  const [value, setValue] = useState('');
  const progress = useRef(new Animated.Value(0)).current;
  const inputRef = useRef<TextInput>(null);
  // Результат фиксируем один раз: и «Готово», и закрытие фоном, и «Назад»
  // идут через finish(), но резолвить промис можно только единожды.
  const settled = useRef(false);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    presenter = (next) => {
      // Второй промпт поверх первого — первый отменяем, иначе его промис
      // никогда не резолвится.
      setReq((prev) => {
        prev?.resolve(null);
        return next;
      });
      setValue(next.defaultValue ?? '');
      settled.current = false;
      progress.setValue(0);
    };
    return () => {
      presenter = null;
    };
  }, [progress]);

  useEffect(() => {
    if (!req) return;
    Animated.timing(progress, {
      toValue: 1,
      duration: SLIDE_IN_MS,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    }).start();
  }, [req, progress]);

  const finish = useCallback(
    (result: string | null) => {
      if (!req || settled.current) return;
      settled.current = true;
      Animated.timing(progress, {
        toValue: 0,
        duration: SLIDE_OUT_MS,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }).start(() => {
        setReq(null);
        req.resolve(result);
      });
    },
    [req, progress],
  );

  const submit = useCallback(() => finish(value), [finish, value]);
  const cancel = useCallback(() => finish(null), [finish]);

  if (Platform.OS !== 'android' || !req) return null;

  const translateY = progress.interpolate({ inputRange: [0, 1], outputRange: [320, 0] });
  const canSubmit = value.trim().length > 0;

  return (
    <Modal
      visible
      transparent
      animationType="none"
      onRequestClose={cancel}
      // autoFocus внутри Android-Modal срабатывает не всегда — добираем фокус
      // после показа окна.
      onShow={() => inputRef.current?.focus()}
    >
      <Animated.View style={[styles.backdrop, { opacity: progress }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={cancel} accessibilityLabel="Закрыть" />
      </Animated.View>
      <View style={styles.root} pointerEvents="box-none">
        <Animated.View
          style={[
            styles.sheet,
            { paddingBottom: Math.max(insets.bottom, 12) + 12, transform: [{ translateY }] },
          ]}
        >
          <View style={styles.handle} />
          <Text style={styles.title}>{req.title}</Text>
          {req.message ? <Text style={styles.message}>{req.message}</Text> : null}
          <TextInput
            ref={inputRef}
            style={styles.input}
            value={value}
            onChangeText={setValue}
            placeholder={req.placeholder}
            placeholderTextColor={Colors.textMuted}
            autoFocus
            selectTextOnFocus
            returnKeyType="done"
            onSubmitEditing={canSubmit ? submit : undefined}
            maxLength={120}
          />
          <View style={styles.actions}>
            <TouchableOpacity style={styles.cancelBtn} onPress={cancel} activeOpacity={0.7}>
              <Text style={styles.cancelTxt}>{req.cancelLabel ?? 'Отмена'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.submitBtn, !canSubmit && styles.submitBtnDisabled]}
              onPress={submit}
              disabled={!canSubmit}
              activeOpacity={0.85}
            >
              <Text style={styles.submitTxt}>{req.submitLabel ?? 'Готово'}</Text>
            </TouchableOpacity>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  // Без StyleSheet.absoluteFillObject — его нет в RN 0.86 (см. SDK_UPGRADE_CHECKLIST).
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: Colors.overlay },
  root: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: Colors.surface,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 24,
    paddingTop: 8,
    elevation: 12,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D3D7E6',
    marginBottom: 14,
  },
  title: { ...Typography.h2, color: Colors.text, textAlign: 'center' },
  message: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center', marginTop: 5 },
  input: {
    ...Typography.body,
    color: Colors.text,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: BorderRadius.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginTop: 18,
  },
  actions: { flexDirection: 'row', gap: 10, marginTop: 16 },
  cancelBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cancelTxt: { ...Typography.button, color: Colors.textSecondary },
  submitBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    backgroundColor: Colors.royalBlue,
  },
  submitBtnDisabled: { opacity: 0.45 },
  submitTxt: { ...Typography.button, color: '#fff' },
});
