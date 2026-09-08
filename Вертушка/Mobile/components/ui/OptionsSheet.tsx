/**
 * OptionsSheet — Android-замена `ActionSheetIOS.showActionSheetWithOptions`
 * (B6 в ANDROID_PORT_PLAN).
 *
 * Прежний фолбэк через `Alert.alert` на Android режет список до трёх кнопок:
 * в меню чата из шести пунктов пропадали «Пожаловаться» и «Заблокировать»,
 * что нарушает UGC-политику Play. Здесь — bottom sheet со списком без лимита,
 * теми же аргументами, что у `ActionSheetIOS`: `options`, `cancelButtonIndex`,
 * `destructiveButtonIndex` (число или массив), `title`, `message`.
 *
 * Семантика колбэка — как на iOS: индекс выбранного пункта; тап по фону и
 * кнопка «Назад» отдают `cancelButtonIndex` (или -1, если его нет).
 *
 * RN `<Modal>`, а не `@gorhom/bottom-sheet` — по той же причине, что и
 * `PromptSheet`: меню могут открывать поверх других RN-модалок, а Dialog
 * всегда сверху. Колбэк зовём ПОСЛЕ анимации закрытия: несколько пунктов
 * (жалоба, блок, очистка) тут же показывают `Alert.alert`, и он не должен
 * наезжать на ещё видимый шит.
 *
 * На iOS хост возвращает null; `showActionSheet()` из `lib/actionSheetCompat`
 * зовёт нативный `ActionSheetIOS` (решение Q6).
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  type ActionSheetIOSOptions,
  Animated,
  Easing,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { BorderRadius, Colors, Typography } from '../../constants/theme';

interface OptionsRequest {
  options: ActionSheetIOSOptions;
  callback: (buttonIndex: number) => void;
}

type Presenter = (req: OptionsRequest) => void;

let presenter: Presenter | null = null;

/** Показать меню. Без хоста — сразу «отмена», чтобы вызывающий код не повис. */
export function presentOptionsSheet(
  options: ActionSheetIOSOptions,
  callback: (buttonIndex: number) => void,
): void {
  if (!presenter) {
    callback(options.cancelButtonIndex ?? -1);
    return;
  }
  presenter({ options, callback });
}

const SLIDE_IN_MS = 220;
const SLIDE_OUT_MS = 160;

const isDestructive = (idx: number, d: ActionSheetIOSOptions['destructiveButtonIndex']): boolean =>
  Array.isArray(d) ? d.includes(idx) : d === idx;

export function OptionsSheetHost() {
  const insets = useSafeAreaInsets();
  const [req, setReq] = useState<OptionsRequest | null>(null);
  const progress = useRef(new Animated.Value(0)).current;
  const settled = useRef(false);

  useEffect(() => {
    if (Platform.OS !== 'android') return;
    presenter = (next) => {
      setReq((prev) => {
        // Новое меню поверх открытого — старое считаем отменённым.
        prev?.callback(prev.options.cancelButtonIndex ?? -1);
        return next;
      });
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
    (index: number) => {
      if (!req || settled.current) return;
      settled.current = true;
      Animated.timing(progress, {
        toValue: 0,
        duration: SLIDE_OUT_MS,
        easing: Easing.in(Easing.cubic),
        useNativeDriver: true,
      }).start(() => {
        setReq(null);
        req.callback(index);
      });
    },
    [req, progress],
  );

  const cancel = useCallback(() => finish(req?.options.cancelButtonIndex ?? -1), [finish, req]);

  if (Platform.OS !== 'android' || !req) return null;

  const { options: labels, cancelButtonIndex, destructiveButtonIndex, title, message } = req.options;
  const translateY = progress.interpolate({ inputRange: [0, 1], outputRange: [360, 0] });
  const items = labels
    .map((label, index) => ({ label, index }))
    .filter(({ index }) => index !== cancelButtonIndex);
  const cancelLabel = cancelButtonIndex != null ? labels[cancelButtonIndex] : null;

  return (
    <Modal
      visible
      transparent
      animationType="none"
      onRequestClose={cancel}
      statusBarTranslucent
      navigationBarTranslucent
    >
      <Animated.View style={[styles.backdrop, { opacity: progress }]}>
        <Pressable style={StyleSheet.absoluteFill} onPress={cancel} accessibilityLabel="Закрыть" />
      </Animated.View>
      <View style={styles.root} pointerEvents="box-none">
        <Animated.View
          style={[
            styles.sheet,
            {
              paddingBottom: Math.max(insets.bottom, 12) + 8,
              maxHeight: '80%',
              transform: [{ translateY }],
            },
          ]}
        >
          <View style={styles.handle} />
          {title ? <Text style={styles.title}>{title}</Text> : null}
          {message ? <Text style={styles.message}>{message}</Text> : null}
          <ScrollView bounces={false} style={styles.list}>
            {items.map(({ label, index }, i) => {
              const destructive = isDestructive(index, destructiveButtonIndex);
              return (
                <TouchableOpacity
                  key={`${index}-${label}`}
                  style={[styles.item, i === items.length - 1 && styles.itemLast]}
                  onPress={() => finish(index)}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel={label}
                >
                  <Text style={[styles.itemTxt, destructive && styles.itemTxtDestructive]}>{label}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
          {cancelLabel ? (
            <TouchableOpacity style={styles.cancelBtn} onPress={cancel} activeOpacity={0.7}>
              <Text style={styles.cancelTxt}>{cancelLabel}</Text>
            </TouchableOpacity>
          ) : null}
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
    paddingHorizontal: 16,
    paddingTop: 8,
    elevation: 12,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D3D7E6',
    marginBottom: 10,
  },
  title: { ...Typography.bodyBold, color: Colors.text, textAlign: 'center', marginTop: 4 },
  message: { ...Typography.bodySmall, color: Colors.textSecondary, textAlign: 'center', marginTop: 4 },
  list: { marginTop: 10, flexGrow: 0 },
  item: {
    paddingVertical: 15,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  itemLast: { borderBottomWidth: 0 },
  itemTxt: { ...Typography.body, color: Colors.text },
  itemTxtDestructive: { color: Colors.error },
  cancelBtn: {
    marginTop: 8,
    paddingVertical: 14,
    borderRadius: BorderRadius.md,
    alignItems: 'center',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  cancelTxt: { ...Typography.button, color: Colors.textSecondary },
});
