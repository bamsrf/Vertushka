/**
 * Полноэкранный просмотр фото из чата.
 *
 * - pinch-to-zoom (1x…4x) + pan в зуме;
 * - double-tap — переключение 1x ↔ 2.5x;
 * - свайп вниз в 1x — закрытие с затуханием фона (Telegram-style);
 * - все жесты на UI-потоке (reanimated + RNGH).
 */
import React, { useEffect } from 'react';
import { Modal, StyleSheet, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { Image } from 'expo-image';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  runOnJS,
  interpolate,
  Extrapolation,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon } from '@/components/ui';

const SPRING = { damping: 20, stiffness: 220 };
const MAX_SCALE = 4;
const DOUBLE_TAP_SCALE = 2.5;
const DISMISS_THRESHOLD = 110;

interface Props {
  visible: boolean;
  uri: string | null;
  onClose: () => void;
}

export function ImageLightbox({ visible, uri, onClose }: Props) {
  const { width: screenW, height: screenH } = useWindowDimensions();
  const insets = useSafeAreaInsets();

  const scale = useSharedValue(1);
  const savedScale = useSharedValue(1);
  const tx = useSharedValue(0);
  const ty = useSharedValue(0);
  const savedTx = useSharedValue(0);
  const savedTy = useSharedValue(0);
  const dismissY = useSharedValue(0);

  useEffect(() => {
    if (visible) {
      scale.value = 1;
      savedScale.value = 1;
      tx.value = 0;
      ty.value = 0;
      savedTx.value = 0;
      savedTy.value = 0;
      dismissY.value = 0;
    }
  }, [visible, scale, savedScale, tx, ty, savedTx, savedTy, dismissY]);

  const clampPan = (v: number, s: number, size: number) => {
    'worklet';
    const overflow = Math.max(0, (size * s - size) / 2);
    return Math.min(overflow, Math.max(-overflow, v));
  };

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = Math.min(MAX_SCALE, Math.max(1, savedScale.value * e.scale));
    })
    .onEnd(() => {
      savedScale.value = scale.value;
      if (scale.value <= 1.02) {
        scale.value = withSpring(1, SPRING);
        savedScale.value = 1;
        tx.value = withSpring(0, SPRING);
        ty.value = withSpring(0, SPRING);
        savedTx.value = 0;
        savedTy.value = 0;
      }
    });

  const pan = Gesture.Pan()
    .onUpdate((e) => {
      if (savedScale.value > 1.02) {
        tx.value = clampPan(savedTx.value + e.translationX, savedScale.value, screenW);
        ty.value = clampPan(savedTy.value + e.translationY, savedScale.value, screenH);
      } else {
        dismissY.value = e.translationY;
      }
    })
    .onEnd((e) => {
      if (savedScale.value > 1.02) {
        savedTx.value = tx.value;
        savedTy.value = ty.value;
        return;
      }
      if (Math.abs(dismissY.value) > DISMISS_THRESHOLD || Math.abs(e.velocityY) > 900) {
        runOnJS(onClose)();
      } else {
        dismissY.value = withSpring(0, SPRING);
      }
    });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      if (savedScale.value > 1.02) {
        scale.value = withSpring(1, SPRING);
        savedScale.value = 1;
        tx.value = withSpring(0, SPRING);
        ty.value = withSpring(0, SPRING);
        savedTx.value = 0;
        savedTy.value = 0;
      } else {
        scale.value = withSpring(DOUBLE_TAP_SCALE, SPRING);
        savedScale.value = DOUBLE_TAP_SCALE;
      }
    });

  const composed = Gesture.Simultaneous(pinch, pan, doubleTap);

  const imageStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: tx.value },
      { translateY: ty.value + dismissY.value },
      {
        scale:
          scale.value *
          interpolate(
            Math.abs(dismissY.value),
            [0, 320],
            [1, 0.82],
            Extrapolation.CLAMP,
          ),
      },
    ],
  }));

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: interpolate(
      Math.abs(dismissY.value),
      [0, 260],
      [1, 0.3],
      Extrapolation.CLAMP,
    ),
  }));

  if (!uri) return null;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <View style={styles.root}>
        <Animated.View style={[StyleSheet.absoluteFill, styles.backdrop, backdropStyle]} />
        <GestureDetector gesture={composed}>
          <Animated.View style={[styles.imageWrap, imageStyle]}>
            <Image
              source={{ uri }}
              style={{ width: screenW, height: screenH }}
              contentFit="contain"
              cachePolicy="disk"
            />
          </Animated.View>
        </GestureDetector>
        <TouchableOpacity
          onPress={onClose}
          style={[styles.closeBtn, { top: insets.top + 8 }]}
          activeOpacity={0.8}
          accessibilityLabel="Закрыть просмотр фото"
        >
          <Icon name="close" size={20} color="#fff" />
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  backdrop: { backgroundColor: '#000' },
  imageWrap: { alignItems: 'center', justifyContent: 'center' },
  closeBtn: {
    position: 'absolute',
    right: 16,
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
